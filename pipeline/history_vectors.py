"""The signal space's past as a weighted sample, outside `trends` (Owner 2026-10-03).

Plan and measurements: docs/history_backfill_plan_2026-10-03.md (dry run:
scripts/history_plan.py). Two tables, additive, never touched by feed, search or judge:

  history_items    what is to be embedded: one row per sampled document
                   tier 'patent' (one per DOCDB family, ref = pub_number, raw_entry_id)
                   or 'science' (ref = OpenAlex work id in research_corpus),
                   month (year*12 + month-1), layer 'random' | 'cited', cited flag,
                   weight = frame / sampled of its tier-month (random layer only),
                   claimed_by / claimed_at / embedded_at for the workers
  history_vectors  item_id -> the 1024 prefix, L2-normalised, float16 little-endian
                   (2,048 bytes; pgvector 0.6 has no halfvec), device that embedded it

Kept apart so the 1.3 M wide rows are written once (INSERT), never updated; the claim
bookkeeping lives on the narrow item rows. Text recipe = the signal path's:
title + "\\n" + abstract[:500] (scripts/signal_batch.py), so the vectors share the space
of trends.embedding_1024.
"""
from __future__ import annotations

import logging

import numpy as np

from pipeline.db import USE_POSTGRES, get_connection

logger = logging.getLogger("history_vectors")

DIM = 1024
TEXT_CHARS = 500
MIN_ABSTRACT = 80
HASH = "(({k})::bigint * 2654435761) %% 4294967296"
# Readers that mix history with trends (archive scan, signal cloud) give a history
# point the id BASE + item id: trends ids stay far below 2^31, the packed cloud keeps
# ids as uint32, so the top bit says "look in history_items".
HISTORY_ID_BASE = 1 << 31
# Synthetic source per tier, chosen so pipeline.tiers.tier_of places it right.
SOURCES = {"patent": ("EPO DOCDB (history sample)", "api"),
           "science": ("OpenAlex corpus (history sample)", "research")}
HISTORY_UNTIL = "2026-07"     # the sample covers the months before this one (extended 03.10.)


def migrate_history_tables() -> None:
    if not USE_POSTGRES:
        with get_connection() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS history_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tier TEXT NOT NULL, ref TEXT NOT NULL,
                raw_entry_id INTEGER, month INTEGER NOT NULL, layer TEXT NOT NULL,
                cited INTEGER DEFAULT 0, weight REAL, claimed_by TEXT, claimed_at TIMESTAMP,
                embedded_at TIMESTAMP, dup_of_trend INTEGER, UNIQUE(tier, ref))""")
            c.execute("""CREATE TABLE IF NOT EXISTS history_vectors (
                item_id INTEGER PRIMARY KEY, vec BLOB NOT NULL, device TEXT)""")
        return
    with get_connection() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS history_items (
            id SERIAL PRIMARY KEY, tier TEXT NOT NULL, ref TEXT NOT NULL,
            raw_entry_id BIGINT, month INTEGER NOT NULL, layer TEXT NOT NULL,
            cited BOOLEAN DEFAULT FALSE, weight REAL, claimed_by TEXT, claimed_at TIMESTAMPTZ,
            embedded_at TIMESTAMPTZ, UNIQUE(tier, ref))""")
        c.execute("""CREATE TABLE IF NOT EXISTS history_vectors (
            item_id INTEGER PRIMARY KEY REFERENCES history_items(id), vec BYTEA NOT NULL,
            device TEXT)""")
        c.execute("ALTER TABLE history_items ADD COLUMN IF NOT EXISTS dup_of_trend BIGINT")
        c.execute("CREATE INDEX IF NOT EXISTS idx_history_items_open ON history_items(id) "
                  "WHERE embedded_at IS NULL")
        c.execute("CREATE INDEX IF NOT EXISTS idx_history_items_tier_month ON history_items(tier, month)")


def pack(vec) -> bytes:
    """4096 (or 1024) floats -> L2-normalised 1024 prefix as float16 bytes."""
    v = np.asarray(vec, np.float32)[:DIM]
    v = v / max(float(np.linalg.norm(v)), 1e-9)
    return v.astype("<f2").tobytes()


def unpack(blob: bytes) -> np.ndarray:
    return np.frombuffer(bytes(blob), "<f2").astype(np.float32)


def text_of(title: str | None, body: str | None) -> str:
    return f"{title or ''}\n{(body or '')[:TEXT_CHARS]}"


def select_patents(c, start: str, until: str, quota: int) -> int:
    """Insert the patent sample: per month the `quota` families with the smallest hash
    (random layer, weighted) plus every family cited by a patent in the signal space
    (cited layer). One row per family = its earliest publication with an abstract."""
    c.execute("""CREATE TEMP TABLE h_cited AS SELECT DISTINCT l.dst_pub AS p FROM patent_links l
        JOIN (SELECT DISTINCT r.pub_number p FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id
              WHERE r.pub_number IS NOT NULL AND t.status IN ('signal','published')
              AND t.embedding_1024 IS NOT NULL) e ON e.p = l.src_pub
        WHERE l.link_type = 'cites'""")
    c.execute("CREATE INDEX ON h_cited(p)")
    c.execute("ANALYZE h_cited")
    c.execute("""CREATE TEMP TABLE h_fam AS
        SELECT coalesce(pf.family_id, -r.id) AS fid,
               (array_agg(r.id ORDER BY r.published_date, r.id))[1] AS rid,
               (array_agg(r.pub_number ORDER BY r.published_date, r.id))[1] AS pub,
               min(r.published_date) AS d, bool_or(ci.p IS NOT NULL) AS cited
        FROM raw_entries r
        LEFT JOIN patent_family pf ON pf.pub_number = r.pub_number
        LEFT JOIN h_cited ci ON ci.p = r.pub_number
        WHERE r.pub_number IS NOT NULL AND octet_length(r.excerpt) >= ?
          AND r.published_date >= ? AND r.published_date < ?
        GROUP BY 1""", (MIN_ABSTRACT, start, until))
    n = c.execute(f"""
        INSERT INTO history_items (tier, ref, raw_entry_id, month, layer, cited, weight)
        SELECT 'patent', pub, rid, m, CASE WHEN rk <= ? THEN 'random' ELSE 'cited' END, cited,
               CASE WHEN rk <= ? THEN frame::real / LEAST(frame, ?) END
        FROM (SELECT pub, rid, cited,
                     extract(year FROM d)::int * 12 + extract(month FROM d)::int - 1 AS m,
                     row_number() OVER (PARTITION BY date_trunc('month', d)
                                        ORDER BY {HASH.format(k='abs(fid)')}, fid) AS rk,
                     count(*) OVER (PARTITION BY date_trunc('month', d)) AS frame
              FROM h_fam) f
        WHERE rk <= ? OR cited
        ON CONFLICT (tier, ref) DO NOTHING""", (quota, quota, quota, quota)).rowcount
    c.execute("DROP TABLE h_fam")
    c.execute("DROP TABLE h_cited")
    return n


def select_science(c, start: str, until: str, quota: int) -> int:
    """Insert the research sample: per month the `quota` works with an abstract and the
    smallest hash, retracted works excluded."""
    return c.execute(f"""
        INSERT INTO history_items (tier, ref, month, layer, weight)
        SELECT 'science', id, m, 'random', frame::real / LEAST(frame, ?)
        FROM (SELECT rc.id,
                     extract(year FROM rc.published)::int * 12 + extract(month FROM rc.published)::int - 1 AS m,
                     row_number() OVER (PARTITION BY date_trunc('month', rc.published)
                                        ORDER BY {HASH.format(k="hashtext(rc.id)::bigint & 2147483647")}, rc.id) AS rk,
                     count(*) OVER (PARTITION BY date_trunc('month', rc.published)) AS frame
              FROM research_corpus rc
              WHERE rc.published >= ? AND rc.published < ? AND octet_length(rc.abstract) >= ?
                AND NOT coalesce(rc.is_retracted, FALSE)) f
        WHERE rk <= ?
        ON CONFLICT (tier, ref) DO NOTHING""", (quota, start, until, MIN_ABSTRACT, quota)).rowcount


def claim(c, worker: str, n: int, stale_minutes: int = 20) -> list[dict]:
    rows = c.execute(f"""UPDATE history_items SET claimed_by = ?, claimed_at = now()
        WHERE id IN (SELECT id FROM history_items
                     WHERE embedded_at IS NULL
                       AND (claimed_at IS NULL OR claimed_at < now() - interval '{int(stale_minutes)} minutes')
                     ORDER BY id LIMIT ? FOR UPDATE SKIP LOCKED)
        RETURNING id, tier, ref, raw_entry_id""", (worker, n)).fetchall()
    return [dict(r) for r in rows]


def texts_for(c, items: list[dict]) -> dict[int, str]:
    """item id -> text to embed (signal-path recipe)."""
    out: dict[int, str] = {}
    pats = {it["raw_entry_id"]: it["id"] for it in items if it["tier"] == "patent"}
    if pats:
        for r in c.execute("SELECT id, title, excerpt FROM raw_entries WHERE id = ANY(?)",
                           (list(pats),)).fetchall():
            out[pats[int(r["id"])]] = text_of(r["title"], r["excerpt"])
    sci = {it["ref"]: it["id"] for it in items if it["tier"] == "science"}
    if sci:
        for r in c.execute("SELECT id, title, abstract FROM research_corpus WHERE id = ANY(?)",
                           (list(sci),)).fetchall():
            out[sci[r["id"]]] = text_of(r["title"], r["abstract"])
    return out


def store(c, done: list[tuple[int, bytes]], device: str) -> None:
    c.executemany("INSERT OR IGNORE INTO history_vectors (item_id, vec, device) VALUES (?, ?, ?)",
                  [(i, b, device) for i, b in done])
    if done:
        c.execute("UPDATE history_items SET embedded_at = now() WHERE id = ANY(?)",
                  ([d[0] for d in done],))


def status(c) -> list[dict]:
    return [dict(r) for r in c.execute("""SELECT tier, layer, count(*) AS n,
        count(embedded_at) AS done, count(*) FILTER (WHERE embedded_at IS NULL AND claimed_at IS NOT NULL) AS claimed
        FROM history_items GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()]


def is_history_id(i: int) -> bool:
    return int(i) >= HISTORY_ID_BASE


def _month_str(m: int) -> str:
    return f"{m // 12:04d}-{m % 12 + 1:02d}"


def _month_num(s: str) -> int:
    return int(s[:4]) * 12 + int(s[5:7]) - 1


def mark_overlaps() -> int:
    """history_items.dup_of_trend = the trends row that holds the same document, so
    readers that mix both never count a document twice. Idempotent; cheap (narrow rows).
    Postgres only (UPDATE … FROM); the SQLite test schema sets the column directly."""
    if not USE_POSTGRES:
        return 0
    with get_connection() as c:
        n = c.execute("""UPDATE history_items h SET dup_of_trend = t.id
            FROM trends t WHERE h.tier = 'patent' AND h.dup_of_trend IS NULL
              AND t.raw_entry_id = h.raw_entry_id AND t.embedding_1024 IS NOT NULL""").rowcount
        n += c.execute("""UPDATE history_items h SET dup_of_trend = t.id
            FROM raw_entries r JOIN trends t ON t.raw_entry_id = r.id
            WHERE h.tier = 'science' AND h.dup_of_trend IS NULL
              AND r.openalex_id = h.ref AND t.embedding_1024 IS NOT NULL""").rowcount
    return n


def available() -> bool:
    try:
        with get_connection() as c:
            return bool(c.execute("SELECT 1 FROM history_vectors LIMIT 1").fetchone())
    except Exception:                                             # noqa: BLE001
        return False


def iter_history(since: str | None = None, until: str | None = None,
                 layers: tuple[str, ...] = ("random",), chunk_size: int = 20_000):
    """Yield (X, rows) chunks of embedded history items, X L2-normalised float32
    (n, 1024), rows shaped like pipeline.foresight.iter_signals rows (id offset by
    HISTORY_ID_BASE, published_date = first of the month, synthetic source per tier)
    plus layer / cited / weight. Documents that also sit in trends are skipped.
    since/until: 'YYYY-MM[-DD]' bounds on the month, until exclusive."""
    if not available():
        return
    where = ["h.dup_of_trend IS NULL", f"h.layer IN ({','.join('?' * len(layers))})"]
    params: list = list(layers)
    if since:
        where.append("h.month >= ?")
        params.append(_month_num(since))
    if until:
        where.append("h.month < ?")
        params.append(_month_num(until))
    last = 0
    with get_connection() as c:
        while True:
            rows = c.execute(
                "SELECT h.id, h.tier, h.month, h.layer, h.cited, h.weight, v.vec "
                "FROM history_items h JOIN history_vectors v ON v.item_id = h.id "
                f"WHERE {' AND '.join(where)} AND h.id > ? ORDER BY h.id LIMIT ?",
                (*params, last, chunk_size)).fetchall()
            if not rows:
                return
            X = np.vstack([unpack(r["vec"]) for r in rows])
            batch = []
            for r in rows:
                name, stype = SOURCES[r["tier"]]
                batch.append({
                    "id": HISTORY_ID_BASE + int(r["id"]), "title_en": None, "mega_trend": None,
                    "tags": [], "brands": [], "companies": [], "source_name": name,
                    "source_type": stype, "trend_signal_type": None, "primary_vertical": None,
                    "status": "history", "source_url": None,
                    "published_date": _month_str(int(r["month"])) + "-01",
                    "layer": r["layer"], "cited": bool(r["cited"]), "weight": r["weight"],
                })
            last = int(rows[-1]["id"])
            yield X, batch
