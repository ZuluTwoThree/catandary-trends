"""Konservatives Firmen-Matching für Phase-2-Signal-Ingester (#87).

Signal-Quellen (HN, FDA, ClinicalTrials, USAspending) tragen keine harten IDs
und oft keine Geografie. Regel daher wie beim Presse-Merge (Plan §4):
gematcht wird nur ein EINDEUTIGER Namensschlüssel — name_norm, das im
Firmenstamm genau einmal vorkommt, mindestens MIN_KEY_LEN Zeichen. Alles
andere wird verworfen; ein fehlendes Signal ist billiger als ein falsches.
"""
from __future__ import annotations

import logging

from pipeline.company_norm import norm_company_name
from pipeline.db import get_connection

logger = logging.getLogger(__name__)

MIN_KEY_LEN = 5


def load_unique_name_index() -> dict[str, int]:
    """name_norm -> company_id, nur eindeutige Schlüssel, ohne excluded."""
    with get_connection() as conn:
        rows = conn.execute(
            "select name_norm, min(id) as id, count(*) as n "
            "from startup_companies where excluded is null "
            "and length(name_norm) >= ? group by name_norm", (MIN_KEY_LEN,)).fetchall()
    idx = {x["name_norm"]: x["id"] for x in rows if x["n"] == 1}
    logger.info("Matching-Index: %d eindeutige Namensschlüssel (%d mehrdeutige verworfen)",
                len(idx), sum(1 for x in rows if x["n"] > 1))
    return idx


def match(idx: dict[str, int], raw_name: str | None) -> int | None:
    nn = norm_company_name(raw_name)
    if len(nn) < MIN_KEY_LEN:
        return None
    return idx.get(nn)


def insert_events(events: list[tuple]) -> int:
    """Batch-Insert; Duplikate fängt der UNIQUE-Key der Tabelle.
    Tupel: (company_id, event_type, event_date, amount, currency, round_label,
            investors_json, meta_json, source, source_url, raw_entry_id)"""
    if not events:
        return 0
    with get_connection() as conn:
        for i in range(0, len(events), 2000):
            conn.executemany(
                "INSERT OR IGNORE INTO startup_events (company_id, event_type, "
                "event_date, amount, currency, round_label, investors, meta, "
                "source, source_url, raw_entry_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                events[i:i + 2000])
    return len(events)


def refresh_aggregates() -> None:
    """event_count/first/last nach neuen Events nachziehen (total_funding
    bleibt Sache des Build-Skripts — neue Signal-Events sind kein Funding)."""
    with get_connection() as conn:
        conn.execute("""
            update startup_companies c set
              event_count = s.n, first_event_at = s.mn, last_event_at = s.mx
            from (select company_id, count(*) n, min(event_date) mn,
                         max(event_date) mx from startup_events group by 1) s
            where s.company_id = c.id
        """)
    logger.info("Firmen-Aggregate aktualisiert.")
