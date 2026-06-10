"""Customer + briefing data layer for Catandary Trend-Radar.

Trend-Radar is the paid B2B product variant: customers subscribe to a
personalized weekly trend briefing (verticals + watchlist keywords),
delivered by email and through a token-gated portal.

Tables live alongside the existing pipeline schema (radar_ prefix) and
are created idempotently via init_radar_schema(). SQLite only — the
product variant ships on the SQLite stack.
"""

import json
import logging
import secrets

from pipeline.db import get_connection

logger = logging.getLogger(__name__)

VALID_TIERS = ("trial", "solo", "pro", "agency")
VALID_STATUS = ("active", "paused", "cancelled")

# Per-tier limits enforced at write time. Trials get pro limits so the
# trial experience matches what most prospects would buy.
TIER_LIMITS = {
    "trial": {"verticals": 8, "keywords": 30, "recipients": 5, "mandates": 0, "mrr": 0},
    "solo": {"verticals": 2, "keywords": 10, "recipients": 1, "mandates": 0, "mrr": 249},
    "pro": {"verticals": 8, "keywords": 30, "recipients": 5, "mandates": 0, "mrr": 490},
    "agency": {"verticals": 8, "keywords": 30, "recipients": 5, "mandates": 3, "mrr": 890},
}

VALID_VERTICALS = ("FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE")

RADAR_SCHEMA = """
CREATE TABLE IF NOT EXISTS radar_customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact_name TEXT,
    email TEXT NOT NULL,
    extra_recipients TEXT DEFAULT '[]',
    tier TEXT NOT NULL CHECK (tier IN ('trial','solo','pro','agency')),
    parent_id INTEGER REFERENCES radar_customers(id),
    token TEXT UNIQUE NOT NULL,
    verticals TEXT DEFAULT '[]',
    keywords TEXT DEFAULT '[]',
    language TEXT DEFAULT 'de' CHECK (language IN ('de','en')),
    brand_name TEXT,
    brand_color TEXT,
    brand_logo_url TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active','paused','cancelled')),
    trial_ends_at TEXT,
    mrr_eur REAL DEFAULT 0,
    stripe_customer_id TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS radar_briefings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES radar_customers(id),
    week_label TEXT NOT NULL,
    subject TEXT,
    html TEXT NOT NULL,
    trend_ids TEXT DEFAULT '[]',
    watchlist_hits TEXT DEFAULT '{}',
    sent_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(customer_id, week_label)
);

CREATE INDEX IF NOT EXISTS idx_radar_customers_token ON radar_customers(token);
CREATE INDEX IF NOT EXISTS idx_radar_customers_status ON radar_customers(status);
CREATE INDEX IF NOT EXISTS idx_radar_briefings_customer ON radar_briefings(customer_id);
"""


def init_radar_schema():
    """Create radar tables if missing. Safe to re-run."""
    with get_connection() as conn:
        conn.executescript(RADAR_SCHEMA)
    logger.info("radar schema initialized")


def generate_token() -> str:
    """URL-safe portal token, 32 chars."""
    return secrets.token_urlsafe(24)


def _validate_config(tier: str, verticals: list[str], keywords: list[str],
                     extra_recipients: list[str]):
    if tier not in VALID_TIERS:
        raise ValueError(f"invalid tier: {tier} (valid: {VALID_TIERS})")
    limits = TIER_LIMITS[tier]
    bad = [v for v in verticals if v not in VALID_VERTICALS]
    if bad:
        raise ValueError(f"invalid verticals: {bad} (valid: {VALID_VERTICALS})")
    if not verticals:
        raise ValueError("at least one vertical required")
    if len(verticals) > limits["verticals"]:
        raise ValueError(f"tier {tier} allows max {limits['verticals']} verticals")
    if len(keywords) > limits["keywords"]:
        raise ValueError(f"tier {tier} allows max {limits['keywords']} watchlist keywords")
    # primary email + extras
    if len(extra_recipients) > max(0, limits["recipients"] - 1):
        raise ValueError(f"tier {tier} allows max {limits['recipients']} recipients total")


def _row_to_customer(row) -> dict:
    d = dict(row)
    for field in ("extra_recipients", "verticals", "keywords"):
        d[field] = json.loads(d.get(field) or "[]")
    return d


def insert_customer(name: str, email: str, tier: str, verticals: list[str],
                    keywords: list[str] | None = None,
                    contact_name: str | None = None,
                    extra_recipients: list[str] | None = None,
                    language: str = "de",
                    brand_name: str | None = None,
                    brand_color: str | None = None,
                    brand_logo_url: str | None = None,
                    parent_id: int | None = None,
                    trial_ends_at: str | None = None,
                    mrr_eur: float | None = None,
                    stripe_customer_id: str | None = None,
                    notes: str | None = None) -> dict:
    """Create a customer (or agency mandate when parent_id is set).

    Returns the full customer dict including the generated portal token.
    """
    keywords = keywords or []
    extra_recipients = extra_recipients or []
    _validate_config(tier, verticals, keywords, extra_recipients)

    if parent_id is not None:
        with get_connection() as conn:
            parent = conn.execute(
                "SELECT tier FROM radar_customers WHERE id = ?", (parent_id,)
            ).fetchone()
            if parent is None:
                raise ValueError(f"parent customer {parent_id} not found")
            if parent["tier"] != "agency":
                raise ValueError("mandates can only be attached to agency-tier customers")
            count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM radar_customers "
                "WHERE parent_id = ? AND status != 'cancelled'",
                (parent_id,),
            ).fetchone()["cnt"]
            if count >= TIER_LIMITS["agency"]["mandates"]:
                raise ValueError("agency tier allows max 3 active mandates")

    if mrr_eur is None:
        # mandates are included in the agency price, so they carry 0 MRR
        mrr_eur = 0 if parent_id is not None else TIER_LIMITS[tier]["mrr"]

    token = generate_token()
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO radar_customers
               (name, contact_name, email, extra_recipients, tier, parent_id, token,
                verticals, keywords, language, brand_name, brand_color, brand_logo_url,
                trial_ends_at, mrr_eur, stripe_customer_id, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, contact_name, email, json.dumps(extra_recipients), tier, parent_id,
             token, json.dumps(verticals), json.dumps(keywords), language,
             brand_name, brand_color, brand_logo_url, trial_ends_at, mrr_eur,
             stripe_customer_id, notes),
        )
        customer_id = cursor.lastrowid
    logger.info("customer created: id=%s name=%s tier=%s", customer_id, name, tier)
    return get_customer(customer_id)


def get_customer(customer_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM radar_customers WHERE id = ?", (customer_id,)
        ).fetchone()
    return _row_to_customer(row) if row else None


def get_customer_by_token(token: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM radar_customers WHERE token = ?", (token,)
        ).fetchone()
    return _row_to_customer(row) if row else None


def list_customers(status: str | None = None, include_mandates: bool = True) -> list[dict]:
    query = "SELECT * FROM radar_customers"
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if not include_mandates:
        clauses.append("parent_id IS NULL")
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_customer(r) for r in rows]


UPDATABLE_FIELDS = {
    "name", "contact_name", "email", "extra_recipients", "tier", "verticals",
    "keywords", "language", "brand_name", "brand_color", "brand_logo_url",
    "status", "trial_ends_at", "mrr_eur", "stripe_customer_id", "notes",
}

JSON_FIELDS = {"extra_recipients", "verticals", "keywords"}


def update_customer(customer_id: int, **fields) -> dict:
    """Update customer fields. Re-validates tier limits on the merged result."""
    current = get_customer(customer_id)
    if current is None:
        raise ValueError(f"customer {customer_id} not found")

    bad = set(fields) - UPDATABLE_FIELDS
    if bad:
        raise ValueError(f"unknown fields: {sorted(bad)}")
    if "status" in fields and fields["status"] not in VALID_STATUS:
        raise ValueError(f"invalid status: {fields['status']}")

    merged = {**current, **fields}
    _validate_config(merged["tier"], merged["verticals"], merged["keywords"],
                     merged["extra_recipients"])

    # tier changes reprice unless mrr_eur is set explicitly in the same call
    if "tier" in fields and "mrr_eur" not in fields and current["parent_id"] is None:
        fields["mrr_eur"] = TIER_LIMITS[fields["tier"]]["mrr"]

    sets, params = [], []
    for key, val in fields.items():
        sets.append(f"{key} = ?")
        params.append(json.dumps(val) if key in JSON_FIELDS else val)
    sets.append("updated_at = datetime('now')")
    params.append(customer_id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE radar_customers SET {', '.join(sets)} WHERE id = ?", params
        )
    return get_customer(customer_id)


def rotate_token(customer_id: int) -> str:
    token = generate_token()
    with get_connection() as conn:
        conn.execute(
            "UPDATE radar_customers SET token = ?, updated_at = datetime('now') WHERE id = ?",
            (token, customer_id),
        )
    return token


def get_mrr_summary() -> dict:
    """Active MRR by tier plus total. Trials and mandates carry 0 MRR."""
    customers = list_customers(status="active")
    by_tier: dict[str, dict] = {}
    total = 0.0
    for c in customers:
        tier = c["tier"]
        entry = by_tier.setdefault(tier, {"count": 0, "mrr": 0.0})
        entry["count"] += 1
        entry["mrr"] += c["mrr_eur"] or 0
        total += c["mrr_eur"] or 0
    return {"by_tier": by_tier, "total_mrr": total, "active_customers": len(customers)}


# --- Briefings ---

def insert_briefing(customer_id: int, week_label: str, subject: str, html: str,
                    trend_ids: list[int], watchlist_hits: dict,
                    sent_at: str | None = None) -> int:
    """Store a generated briefing. Replaces an existing one for the same week."""
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO radar_briefings
               (customer_id, week_label, subject, html, trend_ids, watchlist_hits, sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(customer_id, week_label) DO UPDATE SET
                 subject = excluded.subject,
                 html = excluded.html,
                 trend_ids = excluded.trend_ids,
                 watchlist_hits = excluded.watchlist_hits,
                 sent_at = COALESCE(excluded.sent_at, radar_briefings.sent_at)""",
            (customer_id, week_label, subject, html, json.dumps(trend_ids),
             json.dumps(watchlist_hits), sent_at),
        )
        if cursor.lastrowid:
            return cursor.lastrowid
        row = conn.execute(
            "SELECT id FROM radar_briefings WHERE customer_id = ? AND week_label = ?",
            (customer_id, week_label),
        ).fetchone()
        return row["id"]


def mark_briefing_sent(briefing_id: int):
    with get_connection() as conn:
        conn.execute(
            "UPDATE radar_briefings SET sent_at = datetime('now') WHERE id = ?",
            (briefing_id,),
        )


def get_briefings(customer_id: int, limit: int = 26, with_html: bool = False) -> list[dict]:
    cols = "id, customer_id, week_label, subject, trend_ids, watchlist_hits, sent_at, created_at"
    if with_html:
        cols += ", html"
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT {cols} FROM radar_briefings WHERE customer_id = ? "
            "ORDER BY week_label DESC LIMIT ?",
            (customer_id, limit),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["trend_ids"] = json.loads(d.get("trend_ids") or "[]")
        d["watchlist_hits"] = json.loads(d.get("watchlist_hits") or "{}")
        result.append(d)
    return result


def get_briefing(briefing_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM radar_briefings WHERE id = ?", (briefing_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["trend_ids"] = json.loads(d.get("trend_ids") or "[]")
    d["watchlist_hits"] = json.loads(d.get("watchlist_hits") or "{}")
    return d


# --- Trend selection for briefings & portal ---

def get_top_trends(verticals: list[str], since: str, limit: int = 12,
                   exclude_ids: list[int] | None = None) -> list[dict]:
    """Top published trends for a set of verticals since an ISO date,
    ranked by trend_score. Matches primary_vertical OR the verticals JSON
    array, so cross-vertical trends surface in every relevant radar."""
    placeholders = ",".join("?" for _ in verticals)
    json_clauses = " OR ".join("verticals LIKE ?" for _ in verticals)
    params: list = [*verticals, *[f'%"{v}"%' for v in verticals], since]
    exclude_sql = ""
    if exclude_ids:
        exclude_sql = f" AND id NOT IN ({','.join('?' for _ in exclude_ids)})"
        params.extend(exclude_ids)
    params.append(limit)
    query = f"""
        SELECT id, title_de, title_en, slug, summary_de, summary_en,
               primary_vertical, verticals, pestel, tags, trend_signal_type,
               mega_trend, trend_score, source_url, source_name, published_at, created_at
        FROM trends
        WHERE status = 'published'
          AND (primary_vertical IN ({placeholders}) OR {json_clauses})
          AND COALESCE(published_at, created_at) >= ?
          {exclude_sql}
        ORDER BY trend_score DESC, COALESCE(published_at, created_at) DESC
        LIMIT ?
    """
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_trend_row(r) for r in rows]


def search_watchlist(keywords: list[str], since: str, limit_per_keyword: int = 3) -> dict:
    """FTS5 search per watchlist keyword over published trends since a date.

    Returns {keyword: [trend, ...]} for keywords with hits. Falls back to
    LIKE matching if the FTS table is missing (fresh DB without setup_fts5).
    """
    hits: dict[str, list[dict]] = {}
    with get_connection() as conn:
        has_fts = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trends_fts'"
        ).fetchone() is not None
        for kw in keywords:
            if has_fts:
                # quote each token to keep FTS5 syntax chars in user keywords inert
                fts_query = " ".join(f'"{tok}"' for tok in kw.split())
                rows = conn.execute(
                    """SELECT t.id, t.title_de, t.title_en, t.slug, t.summary_de,
                              t.summary_en, t.primary_vertical, t.verticals, t.pestel,
                              t.tags, t.trend_signal_type, t.mega_trend, t.trend_score,
                              t.source_url, t.source_name, t.published_at, t.created_at
                       FROM trends_fts f JOIN trends t ON t.id = f.rowid
                       WHERE trends_fts MATCH ? AND t.status = 'published'
                         AND COALESCE(t.published_at, t.created_at) >= ?
                       ORDER BY t.trend_score DESC LIMIT ?""",
                    (fts_query, since, limit_per_keyword),
                ).fetchall()
            else:
                like = f"%{kw}%"
                rows = conn.execute(
                    """SELECT id, title_de, title_en, slug, summary_de, summary_en,
                              primary_vertical, verticals, pestel, tags,
                              trend_signal_type, mega_trend, trend_score,
                              source_url, source_name, published_at, created_at
                       FROM trends
                       WHERE status = 'published'
                         AND COALESCE(published_at, created_at) >= ?
                         AND (title_de LIKE ? OR title_en LIKE ?
                              OR summary_de LIKE ? OR summary_en LIKE ?)
                       ORDER BY trend_score DESC LIMIT ?""",
                    (since, like, like, like, like, limit_per_keyword),
                ).fetchall()
            if rows:
                hits[kw] = [_trend_row(r) for r in rows]
    return hits


def _trend_row(row) -> dict:
    d = dict(row)
    for field in ("verticals", "pestel", "tags"):
        if field in d:
            d[field] = json.loads(d.get(field) or "[]")
    return d
