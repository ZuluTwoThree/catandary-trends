"""Weekly newsletter generator for Catandary Trends.

Generates an editorial newsletter with LLM-synthesized summaries:
- Overall editorial (EN → DE) — 3 paragraphs
- Per-vertical summaries (EN → DE) — 2-3 sentences each
- Mega-trend radar — top mega-trends by weekly signal count

Output: JSON + HTML preview. Published to frontend via newsletter_editions table.
Run weekly via cron: 0 9 * * 1
"""

import argparse
import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.config import DATA_DIR, LOG_LEVEL, MODEL_GENERATE, load_mega_trends
from pipeline import db as db_mod
from pipeline.db import get_connection
from pipeline.llm_processor import is_title_duplicate, normalize_title

import os as _os
if _os.getenv("NEWSLETTER_LLM_BACKEND") == "llamacpp":
    from pipeline.llamacpp_client import chat
else:
    from pipeline.ollama_client import chat

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_URL = "https://catandary.de"

# --- Site design tokens (frontend/src/app/globals.css) ----------------------
# The email must read as the same product as the website, so the palette is
# copied from the @theme block rather than re-invented. Keep in sync.
INK = "#0a0c0a"        # --color-background
SURFACE = "#111310"    # --color-card
EDGE = "#2a2d25"       # --color-border
PAPER = "#f4f1e8"      # bright text on dark
TEXT = "#d8d5c8"       # body copy
MUTED = "#8a8d82"      # --color-muted
ACCENT = "#d4ff3a"     # chartreuse

# Per-vertical hues, matching VERTICALS in frontend/src/lib/types.ts — the
# 3px left edge of a card is how the site signals which vertical it belongs to.
VERTICAL_COLORS = {
    "FOOD": "#f97316", "TECH": "#a78bfa", "HEALTH": "#34d399", "ECO": "#22d3ee",
    "DESIGN": "#f472b6", "FASHION": "#fb7185", "BIZ": "#60a5fa",
    "LIFESTYLE": "#c084fc",
}

VERTICAL_LABELS = {
    "FOOD": ("Food & Beverage", "\U0001f37d"),
    "TECH": ("Technology & AI", "\U0001f4bb"),
    "HEALTH": ("Health & Wellness", "\U0001f3e5"),
    "ECO": ("Sustainability", "\U0001f331"),
    "DESIGN": ("Design & Architecture", "\U0001f3a8"),
    "FASHION": ("Fashion & Beauty", "\U0001f457"),
    "BIZ": ("Business & Retail", "\U0001f4ca"),
    "LIFESTYLE": ("Lifestyle & Culture", "\U0001f3ad"),
}

VERTICAL_ORDER = ["TECH", "BIZ", "FOOD", "HEALTH", "ECO", "LIFESTYLE", "FASHION", "DESIGN"]

# ---------------------------------------------------------------------------
# System prompts (approved by user)
# ---------------------------------------------------------------------------

EDITORIAL_SYSTEM_PROMPT = (
    "You are the editorial voice of Catandary Trends, a cross-industry trend "
    "intelligence newsletter. Your tone is analytical, confident, concise — like "
    "a senior analyst briefing a board. Never use assistant language (\"Let's "
    "explore\", \"Here's what happened\"). Never end with rhetorical questions. "
    "State observations as facts. Technical terms stay in English."
)

VERTICAL_SYSTEM_PROMPT = (
    "You are a vertical analyst for Catandary Trends. You write per-vertical "
    "summaries for a weekly newsletter read by foresight professionals. Be "
    "concise and declarative. Every word must earn its place. Name specific "
    "companies and products — never stay abstract. No superlatives, no "
    "exclamation marks."
)


BANNED_PHRASES = (
    '"landscape", "paradigm shift", "game-changing", "reshaping the future", '
    '"it remains to be seen", "stakeholders", "navigate", '
    '"at the intersection of", "leveraging", "ecosystem", "doubling down", '
    '"amid growing concerns", "poised to", "underscores the importance of", '
    '"robust", "innovative", "in an era of"'
)


# ---------------------------------------------------------------------------
# 1. Data aggregation
# ---------------------------------------------------------------------------

# How many score-ordered candidates per vertical (and overall) we consider
# before de-duplication. Must exceed the final pick count so that dropping a
# duplicate is replaced by the next distinct signal instead of shortening the
# list.
TOP_CANDIDATE_POOL = 15

# Cosine similarity above which two published signals are treated as the SAME
# STORY for citation purposes.
#
# Why this differs from the ingest threshold: the pipeline de-duplicates at
# DUPLICATE_SIMILARITY_THRESHOLD (0.92) when deciding whether an article is
# worth publishing at all — deliberately strict, because two outlets covering
# one study with different angles are legitimately two articles. A weekly
# digest that cites only three signals per vertical has the opposite need:
# there, two write-ups of the same study read as sloppy, unchecked output.
# Measured on the 2026-W31 FOOD collision (two Campylobacter/poultry pieces
# from Food Safety News and Guardian Environment): the duplicate pair scored
# 0.845, while genuinely distinct signals in the same vertical scored 0.31-0.34
# — a wide, safe gap. 0.80 sits in the middle of it.
# NB: their titles only reach fuzz.ratio 0.667, so the title-level check alone
# (threshold 0.90) can never catch this class — the embedding is what works.
NEWSLETTER_DUP_THRESHOLD = float(
    _os.getenv("NEWSLETTER_DUP_THRESHOLD", "0.80")
)


def _duplicate_pairs(trend_ids: list[int]) -> set[tuple[int, int]]:
    """Pairs of trend ids whose embeddings are near-identical.

    Computed inside Postgres via pgvector, so no embedding ever crosses the
    wire — only the handful of colliding id pairs comes back. Returns an empty
    set (i.e. de-duplication silently disabled) on SQLite, on a missing
    embedding column, or on any query error: a newsletter must still be
    generated when the similarity lookup is unavailable.
    """
    ids = sorted({int(i) for i in trend_ids if i is not None})
    if len(ids) < 2 or not db_mod.USE_POSTGRES:
        return set()
    try:
        with get_connection() as conn:
            rows = conn.execute(
                # Aliased: the PG wrapper yields dict rows, and two columns both
                # named "id" would collapse into one key.
                "SELECT a.id AS a_id, b.id AS b_id FROM trends a JOIN trends b ON a.id < b.id "
                "WHERE a.id = ANY(?) AND b.id = ANY(?) "
                "  AND a.embedding_1024 IS NOT NULL AND b.embedding_1024 IS NOT NULL "
                "  AND (1 - (a.embedding_1024 <=> b.embedding_1024)) >= ?",
                (ids, ids, NEWSLETTER_DUP_THRESHOLD),
            ).fetchall()
    except Exception as e:  # noqa: BLE001 — never block the newsletter
        logger.warning("Duplicate check unavailable (%s) — citing unfiltered", e)
        return set()

    pairs = set()
    for r in rows:
        if hasattr(r, "keys"):
            a, b = r["a_id"], r["b_id"]
        else:
            a, b = r[0], r[1]
        pairs.add((int(a), int(b)))
    if pairs:
        logger.info("Duplicate check: %d near-identical pair(s) among %d candidates",
                    len(pairs), len(ids))
    return pairs


def _pick_distinct(candidates: list[dict], dup_pairs: set[tuple[int, int]],
                   limit: int) -> list[dict]:
    """Take up to `limit` candidates, skipping ones that duplicate an earlier
    pick. Candidates arrive score-ordered, so the stronger signal of a pair is
    always the one kept. Falls back to the title check for pairs the embedding
    lookup could not judge (missing vector, SQLite)."""
    picked: list[dict] = []
    picked_titles: list[str] = []
    for t in candidates:
        if len(picked) >= limit:
            break
        tid = t.get("id")
        if any((min(tid, p["id"]), max(tid, p["id"])) in dup_pairs for p in picked):
            logger.debug("Skipping near-duplicate signal %s: %s", tid, t.get("title_en"))
            continue
        is_dup, _ = is_title_duplicate(t.get("title_en") or "", picked_titles)
        if is_dup:
            continue
        picked.append(t)
        picked_titles.append(normalize_title(t.get("title_en") or ""))
    return picked


def get_weekly_newsletter_data(days: int = 7, week_start: str | None = None,
                               week_end: str | None = None) -> dict:
    """Fetch published trends for a date range and aggregate for editorial.

    If week_start/week_end are provided, use those instead of days-based cutoff.
    """
    if week_start and week_end:
        cutoff = week_start
        upper = week_end
    else:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        upper = None

    with get_connection() as conn:
        if upper:
            rows = conn.execute(
                "SELECT id, title_en, title_de, slug, summary_en, summary_de, "
                "primary_vertical, mega_trend, tags, pestel, trend_signal_type, "
                "trend_score, confidence, source_name, created_at "
                "FROM trends WHERE status = 'published' AND created_at > ? AND created_at < ? "
                "ORDER BY trend_score DESC, created_at DESC",
                (cutoff, upper),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title_en, title_de, slug, summary_en, summary_de, "
                "primary_vertical, mega_trend, tags, pestel, trend_signal_type, "
                "trend_score, confidence, source_name, created_at "
                "FROM trends WHERE status = 'published' AND created_at > ? "
                "ORDER BY trend_score DESC, created_at DESC",
                (cutoff,),
            ).fetchall()

    # Convert rows to dicts
    trends = []
    for row in rows:
        d = dict(row) if hasattr(row, "keys") else {
            "id": row[0], "title_en": row[1], "title_de": row[2],
            "slug": row[3], "summary_en": row[4], "summary_de": row[5],
            "primary_vertical": row[6], "mega_trend": row[7],
            "tags": row[8], "pestel": row[9], "trend_signal_type": row[10],
            "trend_score": row[11], "confidence": row[12],
            "source_name": row[13], "created_at": row[14],
        }
        # Parse JSON fields
        for field in ("tags", "pestel"):
            val = d.get(field)
            if isinstance(val, str):
                try:
                    d[field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    d[field] = []
        trends.append(d)

    # Aggregate
    mega_trend_map = {mt["key"]: mt for mt in load_mega_trends()}

    overall_mega_counts: Counter = Counter()
    overall_signal_types: Counter = Counter()
    verticals: dict[str, dict] = {}

    # Candidate pool per vertical: a generous slice of the score-ordered list,
    # from which _pick_distinct() then draws the final picks. Collecting more
    # than we need is what makes de-duplication possible — dropping a duplicate
    # must not shrink the citation list.
    for t in trends:
        v = t["primary_vertical"]
        if v not in verticals:
            verticals[v] = {
                "count": 0,
                "candidates": [],
                "top_trends": [],
                "mega_trend_counts": Counter(),
                "signal_types": Counter(),
            }
        vd = verticals[v]
        vd["count"] += 1
        if len(vd["candidates"]) < TOP_CANDIDATE_POOL:
            vd["candidates"].append(t)

        mt = t.get("mega_trend")
        if mt:
            vd["mega_trend_counts"][mt] += 1
            overall_mega_counts[mt] += 1

        st = t.get("trend_signal_type")
        if st:
            vd["signal_types"][st] += 1
            overall_signal_types[st] += 1

    # De-duplicate the cited signals (one similarity lookup for all candidates).
    overall_candidates = trends[:TOP_CANDIDATE_POOL]
    dup_pairs = _duplicate_pairs(
        [t["id"] for vd in verticals.values() for t in vd["candidates"]]
        + [t["id"] for t in overall_candidates]
    )
    for vd in verticals.values():
        vd["top_trends"] = _pick_distinct(vd["candidates"], dup_pairs, 5)
        del vd["candidates"]
    top_overall = _pick_distinct(overall_candidates, dup_pairs, 10)

    # Calendar week
    now = datetime.now(timezone.utc)
    iso_year, iso_week, _ = now.isocalendar()

    return {
        "total_count": len(trends),
        "period": f"{iso_year}-W{iso_week:02d}",
        "period_label": f"Week {iso_week}/{iso_year}",
        "verticals": verticals,
        "mega_trend_counts": overall_mega_counts,
        "mega_trend_map": mega_trend_map,
        "signal_types": overall_signal_types,
        "top_trends": top_overall,
    }


# ---------------------------------------------------------------------------
# 2. Format data for LLM prompts
# ---------------------------------------------------------------------------

def _format_vertical_counts(data: dict) -> str:
    """Format vertical counts as 'TECH (41), BIZ (24), ...'"""
    parts = []
    for v in VERTICAL_ORDER:
        if v in data["verticals"]:
            parts.append(f'{v} ({data["verticals"][v]["count"]})')
    return ", ".join(parts)


def _format_top_trends(trends: list[dict], max_summary: int = 120) -> str:
    """Format trends with titles and summaries for LLM context."""
    lines = []
    for t in trends:
        title = t["title_en"] or ""
        summary = (t["summary_en"] or "")[:max_summary]
        source = t.get("source_name") or ""
        lines.append(f'- "{title}" ({source}) — {summary}')
    return "\n".join(lines)


def _format_mega_trend_momentum(data: dict) -> str:
    """Format top mega-trends with human-readable names, counts and MEASURED
    momentum (pipeline.mega_momentum — 90d share vs the 90d before). The yaml
    momentum field was a hand-typed claim (19 of 26 contradicted the data,
    2026-08-08) and is deliberately not used; keys too thin for a directional
    call get no momentum word instead of a guess."""
    from pipeline.mega_momentum import measure
    try:
        measured = measure()
    except Exception:  # noqa: BLE001 — newsletter must not die on a DB hiccup
        measured = {}
    top_mts = data["mega_trend_counts"].most_common(7)
    parts = []
    for key, count in top_mts:
        mt_info = data["mega_trend_map"].get(key, {})
        name = mt_info.get("name_en", key.replace("_", " ").title())
        momentum = (measured.get(key) or {}).get("momentum")
        parts.append(f"{name} ({count} signals, {momentum})" if momentum
                     else f"{name} ({count} signals)")
    return ", ".join(parts)


def _format_signal_types(data: dict) -> str:
    """Format signal type distribution."""
    return ", ".join(f"{st}: {c}" for st, c in data["signal_types"].most_common(5))


def build_editorial_prompt(data: dict) -> str:
    """Build the user prompt for overall editorial generation."""
    return f"""Write the editorial summary for this week's Catandary Trends newsletter.

<data>
Period: {data["period_label"]}
Total new signals: {data["total_count"]}
Verticals: {_format_vertical_counts(data)}

Top signals:
{_format_top_trends(data["top_trends"])}

Mega-trend momentum: {_format_mega_trend_momentum(data)}
Signal types: {_format_signal_types(data)}
</data>

Structure your response as exactly 3 paragraphs:
1. DOMINANT THEME: What single pattern defined this week? Name the 1-2 mega-trends with strongest momentum. Do not open with "This week" — lead with the insight.
2. KEY SIGNALS: 2-3 specific signals that carry the most strategic weight. Name companies, products, or specific developments from the signal titles above. Weave them naturally into your sentences.
3. CROSS-CURRENTS: One unexpected cross-vertical connection or weak signal that deserves attention. Name the shared driver and the mechanism. End with one forward-looking implication — a concrete statement, not a question.

Constraints:
- Select 4-5 most significant signals. Do NOT cover every vertical.
- Use ONLY facts from the data above. Do not invent statistics or numbers.
- Use the full mega-trend names as provided (e.g., "Artificial Intelligence & Automation", not keys with underscores).
- Reference specific signals by weaving their topic or company name into prose — do NOT use bracketed IDs like [TECH-01]. Write grammatically correct flowing text.
- Each paragraph: 2-3 sentences. Total: 150-200 words.
- No bullet points, no headers, no lists. Flowing editorial prose only.

Banned phrases: {BANNED_PHRASES}"""


def build_vertical_prompt(data: dict) -> str:
    """Build the user prompt for per-vertical summaries."""
    sections = []
    for v in VERTICAL_ORDER:
        vd = data["verticals"].get(v)
        if not vd or vd["count"] < 3:
            continue
        label, _ = VERTICAL_LABELS.get(v, (v, ""))
        top_mt = vd["mega_trend_counts"].most_common(3)
        # Use human-readable mega-trend names
        mt_parts = []
        for k, c in top_mt:
            mt_info = data["mega_trend_map"].get(k, {})
            mt_name = mt_info.get("name_en", k.replace("_", " ").title())
            mt_parts.append(f"{mt_name} ({c})")
        mt_str = ", ".join(mt_parts) if mt_parts else "none"
        signal_str = ", ".join(f"{st}: {c}" for st, c in vd["signal_types"].most_common(3))
        trends_str = _format_top_trends(vd["top_trends"][:3], max_summary=80)

        sections.append(f"""{v} — {label} ({vd["count"]} signals)
Mega-trends: {mt_str}
Signal types: {signal_str}
Top signals:
{trends_str}""")

    return f"""Write per-vertical summaries for this week's newsletter.

<data>
{chr(10).join(sections)}
</data>

For each vertical, write exactly 2-3 sentences as one paragraph:
- Sentence 1: What defined this vertical's signals? Name the dominant signal type and direction.
- Sentence 2: Which mega-trend dominated? Connect it to a specific signal by naming the company, product, or development.
- Sentence 3 (only if warranted): An emerging pattern or cross-vertical connection. Omit if nothing genuinely noteworthy — do not pad.

Format:
TECH
[2-3 sentences]

FOOD
[2-3 sentences]

Order by signal count descending. Skip verticals with fewer than 3 signals.
For verticals with 3-5 signals, keep to 2 sentences.
Use full mega-trend names as provided (e.g., "Artificial Intelligence & Automation", not keys with underscores).
Reference specific signals by topic or company name in natural prose — do NOT use bracketed IDs like [TECH-01].
Do not add introduction or transitions between verticals."""



# ---------------------------------------------------------------------------
# 2b. Post-processing: linkify mega-trends and trend references
# ---------------------------------------------------------------------------

def linkify_editorial(text: str, data: dict) -> str:
    """Insert HTML links for mega-trend names and trend titles in editorial text.

    Mega-trends link to /trends/mega, trend titles link to /trends/[slug].
    Each match is linked only on first occurrence to avoid cluttered text.
    """
    linked = set()

    mt_links = {}
    for key, mt_info in data["mega_trend_map"].items():
        name = mt_info.get("name_en", "")
        if name and len(name) > 5:
            mt_links[name] = f"{BASE_URL}/trends/mega"

    trend_links = {}
    for v, vd in data["verticals"].items():
        for t in vd["top_trends"]:
            title = t.get("title_en", "")
            slug = t.get("slug", "")
            if title and slug and len(title) > 10:
                trend_links[title] = f"{BASE_URL}/trends/{slug}"

    for name in sorted(mt_links.keys(), key=len, reverse=True):
        if name in linked:
            continue
        url = mt_links[name]
        if name in text:
            link = f'<a href="{url}" style="color: {ACCENT}; text-decoration: none;">{name}</a>'
            text = text.replace(name, link, 1)
            linked.add(name)

    for title in sorted(trend_links.keys(), key=len, reverse=True):
        if title in linked:
            continue
        url = trend_links[title]
        if title in text:
            link = f'<a href="{url}" style="color: {ACCENT}; text-decoration: none;">{title}</a>'
            text = text.replace(title, link, 1)
            linked.add(title)

    return text


def linkify_editorial_md(text: str, data: dict) -> str:
    """Insert markdown links for mega-trends and trends (for frontend rendering).

    Returns text with [Name](/trends/mega) and [Title](/trends/slug) markdown links.
    """
    linked = set()

    mt_links = {}
    for key, mt_info in data["mega_trend_map"].items():
        name = mt_info.get("name_en", "")
        if name and len(name) > 5:
            mt_links[name] = "/trends/mega"

    trend_links = {}
    for v, vd in data["verticals"].items():
        for t in vd["top_trends"]:
            title = t.get("title_en", "")
            slug = t.get("slug", "")
            if title and slug and len(title) > 10:
                trend_links[title] = f"/trends/{slug}"

    for name in sorted(mt_links.keys(), key=len, reverse=True):
        if name in linked:
            continue
        if name in text:
            text = text.replace(name, f"[{name}]({mt_links[name]})", 1)
            linked.add(name)

    for title in sorted(trend_links.keys(), key=len, reverse=True):
        if title in linked:
            continue
        if title in text:
            text = text.replace(title, f"[{title}]({trend_links[title]})", 1)
            linked.add(title)

    return text


# ---------------------------------------------------------------------------
# 3. LLM editorial generation
# ---------------------------------------------------------------------------

def generate_editorial_en(data: dict) -> str:
    """Generate the overall editorial in English."""
    prompt = build_editorial_prompt(data)
    logger.info("Generating overall editorial (EN)...")
    result = chat(
        model=MODEL_GENERATE,
        prompt=prompt,
        system=EDITORIAL_SYSTEM_PROMPT,
        temperature=0.65,
    )
    logger.info("Editorial EN: %d words", len(result.split()))
    return result.strip()


def generate_vertical_summaries_en(data: dict) -> str:
    """Generate per-vertical summaries in English.

    Retries once if the model produces fewer than half the expected verticals.
    """
    expected_verticals = sum(
        1 for v in VERTICAL_ORDER
        if v in data["verticals"] and data["verticals"][v]["count"] >= 3
    )
    prompt = build_vertical_prompt(data)

    for attempt in range(2):
        logger.info("Generating vertical summaries (EN), attempt %d...", attempt + 1)
        result = chat(
            model=MODEL_GENERATE,
            prompt=prompt,
            system=VERTICAL_SYSTEM_PROMPT,
            temperature=0.6,
        )
        result = result.strip()
        # Quick check: count how many vertical headers appear in parsed result
        parsed_check = parse_vertical_summaries(result)
        found = len(parsed_check)
        logger.info("Vertical summaries EN: %d words, %d/%d verticals",
                     len(result.split()), found, expected_verticals)
        if found >= expected_verticals // 2:
            return result
        logger.warning("Too few verticals (%d/%d), retrying...", found, expected_verticals)

    return result


def _generate_single_vertical_en(vertical: str, data: dict) -> str | None:
    """Generate a summary for a single missing vertical."""
    vd = data["verticals"].get(vertical)
    if not vd or vd["count"] < 3:
        return None
    label, _ = VERTICAL_LABELS.get(vertical, (vertical, ""))
    top_mt = vd["mega_trend_counts"].most_common(3)
    mt_parts = []
    for k, c in top_mt:
        mt_info = data["mega_trend_map"].get(k, {})
        mt_name = mt_info.get("name_en", k.replace("_", " ").title())
        mt_parts.append(f"{mt_name} ({c})")
    mt_str = ", ".join(mt_parts) if mt_parts else "none"
    signal_str = ", ".join(f"{st}: {c}" for st, c in vd["signal_types"].most_common(3))
    trends_str = _format_top_trends(vd["top_trends"][:3], max_summary=80)

    prompt = f"""Write a 2-3 sentence summary for the {label} vertical this week.

<data>
{vertical} — {label} ({vd["count"]} signals)
Mega-trends: {mt_str}
Signal types: {signal_str}
Top signals:
{trends_str}
</data>

Sentence 1: What defined this vertical's signals? Name the dominant signal type and direction.
Sentence 2: Which mega-trend dominated? Connect it to a specific signal by naming the company, product, or development.
Sentence 3 (only if warranted): An emerging pattern or cross-vertical connection.
Use full mega-trend names. No bracketed IDs. No bullet points."""

    logger.info("Generating single vertical summary for %s...", vertical)
    result = chat(
        model=MODEL_GENERATE,
        prompt=prompt,
        system=VERTICAL_SYSTEM_PROMPT,
        temperature=0.6,
    )
    result = result.strip()
    if len(result.split()) < 10:
        return None
    logger.info("Single vertical %s: %d words", vertical, len(result.split()))
    return result



def parse_vertical_summaries(raw: str) -> dict[str, str]:
    """Parse the vertical summaries output into {VERTICAL: summary} dict.

    Handles various LLM formatting: plain labels, **bold**, ##-headers,
    colons, trailing dashes, etc.
    """
    result = {}
    current_vertical = None
    current_lines = []

    for line in raw.split("\n"):
        stripped = line.strip()
        # Remove common markdown/formatting around vertical labels
        cleaned = stripped
        cleaned = re.sub(r'^#+\s*', '', cleaned)        # ## TECH → TECH
        cleaned = re.sub(r'\*+', '', cleaned)            # **TECH** → TECH
        cleaned = cleaned.strip()
        cleaned = re.sub(r'[\s:—\-]+$', '', cleaned)    # TECH: or TECH — → TECH
        cleaned = cleaned.strip()

        if cleaned in VERTICAL_LABELS:
            if current_vertical and current_lines:
                result[current_vertical] = " ".join(current_lines).strip()
            current_vertical = cleaned
            current_lines = []
        elif current_vertical and stripped:
            current_lines.append(stripped)

    # Last vertical
    if current_vertical and current_lines:
        result[current_vertical] = " ".join(current_lines).strip()

    return result


# ---------------------------------------------------------------------------
# 4. Mega-trend radar data
# ---------------------------------------------------------------------------

def build_mega_trend_radar(data: dict) -> list[dict]:
    """Build the signal-themes radar entries for the newsletter. Momentum is
    MEASURED (pipeline.mega_momentum); themes too thin for a directional call
    carry momentum=None and render without an arrow."""
    from pipeline.mega_momentum import measure
    try:
        measured = measure()
    except Exception:  # noqa: BLE001 — newsletter must not die on a DB hiccup
        measured = {}
    radar = []
    for key, count in data["mega_trend_counts"].most_common(7):
        mt_info = data["mega_trend_map"].get(key, {})
        radar.append({
            "key": key,
            "name_en": mt_info.get("name_en", key.replace("_", " ").title()),
            "name_de": mt_info.get("name_de", ""),
            "icon": mt_info.get("icon", ""),
            "momentum": (measured.get(key) or {}).get("momentum"),
            "signal_count": count,
        })
    return radar


# ---------------------------------------------------------------------------
# 5. Newsletter edition storage
# ---------------------------------------------------------------------------

NEWSLETTER_EDITIONS_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS newsletter_editions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    week INTEGER NOT NULL,
    editorial TEXT,
    vertical_summaries TEXT,
    mega_trend_radar TEXT,
    trend_refs TEXT,
    total_signals INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(year, week)
);
"""

NEWSLETTER_EDITIONS_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS newsletter_editions (
    id SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    week INTEGER NOT NULL,
    editorial TEXT,
    vertical_summaries TEXT,
    mega_trend_radar TEXT,
    trend_refs TEXT,
    total_signals INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(year, week)
);
"""


def init_newsletter_table():
    """Ensure newsletter_editions table exists."""
    with get_connection() as conn:
        conn.execute(NEWSLETTER_EDITIONS_SCHEMA_PG if db_mod.USE_POSTGRES
                     else NEWSLETTER_EDITIONS_SCHEMA_SQLITE)


def save_newsletter_edition(edition: dict):
    """Save a newsletter edition to the database (upsert on year+week)."""
    init_newsletter_table()
    upsert = (
        "INSERT INTO newsletter_editions "
        "(year, week, editorial, vertical_summaries, "
        "mega_trend_radar, trend_refs, total_signals) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (year, week) DO UPDATE SET "
        "editorial = EXCLUDED.editorial, "
        "vertical_summaries = EXCLUDED.vertical_summaries, "
        "mega_trend_radar = EXCLUDED.mega_trend_radar, "
        "trend_refs = EXCLUDED.trend_refs, "
        "total_signals = EXCLUDED.total_signals"
    ) if db_mod.USE_POSTGRES else (
        "INSERT OR REPLACE INTO newsletter_editions "
        "(year, week, editorial, vertical_summaries, "
        "mega_trend_radar, trend_refs, total_signals) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    with get_connection() as conn:
        conn.execute(
            upsert,
            (
                edition["year"],
                edition["week"],
                edition["editorial"],
                json.dumps(edition["vertical_summaries"], ensure_ascii=False),
                json.dumps(edition["mega_trend_radar"], ensure_ascii=False),
                json.dumps(edition["trend_refs"], ensure_ascii=False),
                edition["total_signals"],
            ),
        )
    logger.info("Saved newsletter edition %d-W%02d", edition["year"], edition["week"])


def decode_edition_row(row) -> dict:
    """Turn a newsletter_editions row into the shape generate_html() expects.

    The three JSON columns come back as TEXT and must be decoded, or every
    consumer trips over `'str' object has no attribute 'items'`. This lived
    inline in get_latest_newsletter(), so the sender's --year/--week path —
    which builds its dict separately — never decoded them and could not render
    a single edition. It only stayed hidden because every real send so far used
    --latest (2026-08-12).
    """
    d = dict(row) if hasattr(row, "keys") else {}
    for field in ("vertical_summaries", "mega_trend_radar", "trend_refs"):
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def get_latest_newsletter() -> dict | None:
    """Get the most recent newsletter edition."""
    init_newsletter_table()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM newsletter_editions ORDER BY year DESC, week DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return decode_edition_row(row)


def get_newsletter_editions(limit: int = 12) -> list[dict]:
    """Get recent newsletter editions for archive listing."""
    init_newsletter_table()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, year, week, total_signals, created_at "
            "FROM newsletter_editions ORDER BY year DESC, week DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) if hasattr(r, "keys") else {} for r in rows]


# ---------------------------------------------------------------------------
# 6. HTML generation (for preview / email)
# ---------------------------------------------------------------------------

def _md_links_to_html(text: str) -> str:
    """Convert markdown [text](url) links to HTML <a> tags."""
    return re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        rf'<a href="{BASE_URL}\2" style="color: {ACCENT}; text-decoration: none;">\1</a>',
        text,
    )


def generate_html(edition: dict) -> str:
    """Render an edition as email HTML in the site's "Editorial Intelligence" look.

    Mirrors frontend/src/app/globals.css and TrendCard.tsx: ink ground, chartreuse
    accent, serif headlines, monospace micro-labels with wide tracking, square
    corners, and the 3px vertical-coloured left edge that identifies a card.

    Email constraints shape the translation: tables instead of grid, inline
    styles only (several clients drop <style>), and no web fonts — IBM Plex is
    unavailable in a mail client, so the stacks fall back to Georgia for the
    serif voice and a monospace stack for labels. Square corners and hairline
    borders survive everywhere, and they carry most of the identity.

    The literal `{{UNSUBSCRIBE_URL}}` placeholder (doubled braces below, since
    this is an f-string) is substituted per recipient by the sender.
    """
    editorial = _md_links_to_html(edition.get("editorial", ""))
    vert_summaries = {
        k: _md_links_to_html(v) for k, v in edition.get("vertical_summaries", {}).items()
    }
    radar = edition.get("mega_trend_radar", [])
    trend_refs = edition.get("trend_refs", {})
    year = edition.get("year", 0)
    week = edition.get("week", 0)
    total = edition.get("total_signals", 0)

    serif = "Georgia, 'Times New Roman', Times, serif"
    mono = "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    sans = "'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

    def eyebrow(text: str, color: str = MUTED) -> str:
        return (f'<div style="font-family: {mono}; font-size: 10px; '
                f'letter-spacing: 0.16em; text-transform: uppercase; color: {color};">'
                f'{text}</div>')

    # Hidden preheader: the inbox preview line. Without it clients show the
    # wordmark and the eyebrow, which is the same for every issue.
    first_sentence = re.sub(r"<[^>]+>", "", edition.get("editorial", "")).strip()
    first_sentence = re.split(r"(?<=\.)\s", first_sentence)[0][:160] if first_sentence else ""

    editorial_html = ""
    for para in editorial.split("\n\n"):
        para = para.strip()
        if para:
            editorial_html += (
                f'<p style="font-family: {sans}; color: {TEXT}; font-size: 15px; '
                f'line-height: 1.7; margin: 0 0 14px;">{para}</p>\n')

    # --- Vertical cards -----------------------------------------------------
    vertical_sections = ""
    for v in VERTICAL_ORDER:
        summary = vert_summaries.get(v, "")
        if not summary:
            continue
        label = VERTICAL_LABELS.get(v, (v, ""))[0]
        color = VERTICAL_COLORS.get(v, ACCENT)
        v_trends = trend_refs.get(v, [])
        count_str = f"{len(v_trends)} signals" if v_trends else ""

        trend_items = ""
        for t in v_trends[:3]:
            t_title = t.get("title", "")
            slug = t.get("slug", "")
            source = t.get("source_name", "")
            trend_items += f"""
              <tr><td style="padding: 10px 0 0; border-top: 1px dashed {EDGE};">
                <a href="{BASE_URL}/trends/{slug}" style="font-family: {serif}; color: {PAPER}; font-size: 15px; line-height: 1.35; text-decoration: underline; text-underline-offset: 2px;">{t_title}</a>
                <div style="font-family: {mono}; font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: {MUTED}; padding-top: 5px;">{source}</div>
              </td></tr>"""

        vertical_sections += f"""
        <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="margin-bottom: 14px; border: 1px solid {EDGE}; border-left: 3px solid {color}; background: {SURFACE};">
          <tr><td style="padding: 18px 20px 20px;">
            <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
              <tr>
                <td style="font-family: {mono}; font-size: 9px; letter-spacing: 0.15em; text-transform: uppercase; color: {color};">
                  <span style="display: inline-block; width: 10px; height: 3px; background: {color}; vertical-align: middle; margin-right: 7px;">&nbsp;</span>{v}
                  <span style="color: {MUTED};">&nbsp;&middot;&nbsp;{label}</span>
                </td>
                <td align="right" style="font-family: {mono}; font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase; color: {MUTED};">{count_str}</td>
              </tr>
            </table>
            <p style="font-family: {sans}; color: {TEXT}; font-size: 14px; line-height: 1.6; margin: 12px 0 16px;">{summary}</p>
            <table width="100%" cellpadding="0" cellspacing="0" role="presentation">{trend_items}</table>
          </td></tr>
        </table>"""

    # --- Signal themes radar ------------------------------------------------
    arrows = {"rising": "&uarr;", "emerging": "&uarr;&uarr;",
              "declining": "&darr;", "stable": "&rarr;"}
    radar_items = ""
    for mt in radar:
        name = mt.get("name_en", "")
        count = mt.get("signal_count", 0)
        momentum = mt.get("momentum")  # measured; None = too thin for a claim
        mom = (f'<span style="color: {MUTED};">{arrows[momentum]} {momentum}</span>'
               if momentum in arrows else "")
        radar_items += f"""
          <tr>
            <td style="padding: 9px 0; border-top: 1px dashed {EDGE}; font-family: {sans}; font-size: 14px; color: {PAPER};">{name}</td>
            <td align="right" style="padding: 9px 0; border-top: 1px dashed {EDGE}; font-family: {mono}; font-size: 11px; letter-spacing: 0.08em; color: {ACCENT}; white-space: nowrap;">{count}&nbsp;&nbsp;{mom}</td>
          </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="supported-color-schemes" content="dark">
<title>Catandary Trends &mdash; Week {week}/{year}</title>
</head>
<body style="margin: 0; padding: 0; background: {INK}; -webkit-text-size-adjust: 100%;">
  <div style="display: none; max-height: 0; overflow: hidden; opacity: 0; color: {INK};">{first_sentence}</div>
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background: {INK};">
    <tr><td align="center" style="padding: 28px 12px 40px;">
      <table width="600" cellpadding="0" cellspacing="0" role="presentation" style="width: 600px; max-width: 100%; border: 1px solid {EDGE}; background: {INK};">

        <!-- Masthead -->
        <tr><td style="padding: 30px 24px 22px; border-bottom: 1px solid {EDGE};">
          <div style="font-family: {serif}; font-size: 25px; letter-spacing: -0.01em; color: {PAPER};">Catandary<span style="color: {ACCENT};">.</span></div>
          <div style="font-family: {mono}; font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase; color: {MUTED}; padding-top: 9px;">
            Week {week}&thinsp;/&thinsp;{year} &nbsp;&middot;&nbsp; {total:,} signals &nbsp;&middot;&nbsp; 8 verticals
          </div>
        </td></tr>

        <!-- Editorial -->
        <tr><td style="padding: 26px 24px 6px;">
          {eyebrow("Weekly overview")}
          <h1 style="font-family: {serif}; font-size: 27px; line-height: 1.2; letter-spacing: -0.015em; color: {PAPER}; font-weight: normal; margin: 10px 0 16px;">What moved this week</h1>
          {editorial_html}
        </td></tr>

        <!-- Verticals -->
        <tr><td style="padding: 20px 24px 6px;">
          {eyebrow("By vertical")}
          <div style="height: 14px; line-height: 14px;">&nbsp;</div>
          {vertical_sections}
        </td></tr>

        <!-- Radar -->
        <tr><td style="padding: 14px 24px 8px;">
          {eyebrow("Signal themes radar")}
          <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="margin-top: 12px;">{radar_items}</table>
        </td></tr>

        <!-- CTA -->
        <tr><td style="padding: 28px 24px 30px;">
          <table cellpadding="0" cellspacing="0" role="presentation">
            <tr><td style="background: {ACCENT};">
              <a href="{BASE_URL}/trends" style="display: inline-block; padding: 13px 30px; font-family: {mono}; font-size: 11px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: {INK}; text-decoration: none;">View all trends</a>
            </td></tr>
          </table>
          <div style="font-family: {mono}; font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: {MUTED}; padding-top: 16px;">
            Deeper analysis &rarr; <a href="{BASE_URL}" style="color: {ACCENT}; text-decoration: none;">Catandary Foresight</a>
          </div>
        </td></tr>

        <!-- Footer -->
        <tr><td style="padding: 18px 24px 22px; border-top: 1px solid {EDGE};">
          <div style="font-family: {mono}; font-size: 10px; line-height: 1.8; letter-spacing: 0.1em; text-transform: uppercase; color: {MUTED};">
            &copy; {datetime.now().year} Catandary &nbsp;&middot;&nbsp; Built locally in Germany<br>
            You receive this because you subscribed to Catandary Trends.<br>
            <a href="{{{{UNSUBSCRIBE_URL}}}}" style="color: {MUTED}; text-decoration: underline;">Unsubscribe</a>
          </div>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

# ---------------------------------------------------------------------------
# 7. Main orchestration
# ---------------------------------------------------------------------------

def generate_newsletter(days: int = 7, skip_llm: bool = False,
                        year: int | None = None, week: int | None = None) -> dict:
    """Generate a complete newsletter edition.

    If year/week are provided, generate for that specific ISO week retroactively.
    Returns the edition dict with all fields populated.
    """
    if year and week:
        # Calculate Monday-Sunday of the given ISO week
        from datetime import date
        monday = date.fromisocalendar(year, week, 1)
        sunday = date.fromisocalendar(year, week, 7)
        week_start = f"{monday.isoformat()}T00:00:00"
        week_end = f"{sunday.isoformat()}T23:59:59"
        logger.info("Collecting trend data for %d-W%02d (%s to %s)...", year, week, monday, sunday)
        data = get_weekly_newsletter_data(week_start=week_start, week_end=week_end)
        # Override period label
        data["period"] = f"{year}-W{week:02d}"
        data["period_label"] = f"Week {week}/{year}"
        iso_year, iso_week = year, week
    else:
        logger.info("Collecting trend data (last %d days)...", days)
        data = get_weekly_newsletter_data(days)
        now = datetime.now(timezone.utc)
        iso_year, iso_week, _ = now.isocalendar()

    logger.info("Found %d signals across %d verticals",
                data["total_count"], len(data["verticals"]))

    if data["total_count"] == 0:
        logger.info("No signals found — skipping newsletter generation")
        return {}

    # Build trend_refs for the HTML template
    trend_refs = {}
    for v, vd in data["verticals"].items():
        trend_refs[v] = [
            {
                "title": t["title_en"],
                "slug": t["slug"],
                "source_name": t.get("source_name", ""),
            }
            for t in vd["top_trends"][:3]
        ]

    if skip_llm:
        logger.info("Skipping LLM calls (--skip-llm)")
        return {
            "year": iso_year,
            "week": iso_week,
            "editorial": f"[LLM skipped] {data['total_count']} signals this week.",
            "vertical_summaries": {},
            "mega_trend_radar": build_mega_trend_radar(data),
            "trend_refs": trend_refs,
            "total_signals": data["total_count"],
        }

    # Generate editorial
    editorial = generate_editorial_en(data)

    # Generate vertical summaries
    verticals_raw = generate_vertical_summaries_en(data)
    verticals = parse_vertical_summaries(verticals_raw)

    # Fill missing verticals that should have been included (>= 3 signals)
    missing = [
        v for v in VERTICAL_ORDER
        if v in data["verticals"] and data["verticals"][v]["count"] >= 3
        and v not in verticals
    ]
    if missing:
        logger.warning("Missing verticals %s, generating individually...", missing)
        for v in missing:
            summary = _generate_single_vertical_en(v, data)
            if summary:
                verticals[v] = summary

    # Linkify editorials and vertical summaries (markdown for frontend)
    editorial = linkify_editorial_md(editorial, data)
    verticals_linked = {
        v: linkify_editorial_md(text, data)
        for v, text in verticals.items()
    }

    edition = {
        "year": iso_year,
        "week": iso_week,
        "editorial": editorial,
        "vertical_summaries": verticals_linked,
        "mega_trend_radar": build_mega_trend_radar(data),
        "trend_refs": trend_refs,
        "total_signals": data["total_count"],
    }

    return edition


def main():
    parser = argparse.ArgumentParser(description="Generate weekly newsletter")
    parser.add_argument("--days", type=int, default=7, help="Days to look back")
    parser.add_argument("--year", type=int, help="ISO year for retroactive generation")
    parser.add_argument("--week", type=int, help="ISO week number for retroactive generation")
    parser.add_argument("--preview", action="store_true", help="Save HTML preview only, don't store in DB")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM calls, data-only output")
    args = parser.parse_args()

    edition = generate_newsletter(
        days=args.days, skip_llm=args.skip_llm,
        year=args.year, week=args.week,
    )
    if not edition:
        return

    # Save to DB
    if not args.preview:
        save_newsletter_edition(edition)

    # Generate HTML preview
    preview_dir = DATA_DIR / "newsletters"
    preview_dir.mkdir(exist_ok=True)

    week_label = f"{edition['year']}-W{edition['week']:02d}"

    html = generate_html(edition)
    path = preview_dir / f"newsletter_{week_label}.html"
    path.write_text(html, encoding="utf-8")
    logger.info("HTML preview: %s", path)
    (preview_dir / "latest.html").write_text(html, encoding="utf-8")

    # Save edition JSON
    json_path = preview_dir / f"newsletter_{week_label}.json"
    json_path.write_text(
        json.dumps(edition, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("JSON: %s", json_path)

    logger.info("Newsletter %s complete: %d signals, %d verticals",
                week_label, edition["total_signals"], len(edition.get("vertical_summaries", {})))


if __name__ == "__main__":
    main()
