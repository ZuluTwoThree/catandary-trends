#!/usr/bin/env python3
"""INPADOC-Legal-Events via EPO OPS für die kuratierten Technologien (#7, Paket C).

Gezieltes Enrichment im OPS-Fair-Use — NICHT der Bulk-Weg (der bleibt PATSTAT/
TIP): je kuratierter CPC-Subclass die jüngsten N Patente unseres Bestands,
Legal-Events des angefragten Familienmitglieds nach patent_legal_events.
Rechtsstands-Ereignisse (Lapse/Withdrawal/Grant) sind das Desinvestitions-
bzw. Reife-Signal auf der Patentseite.

Resumable: ops_legal_state merkt sich jede abgefragte pub_number (auch bei 0
Events oder 404), --cap begrenzt die OPS-Calls je Lauf. pub_number-Format:
Bindestriche → Punkte (CN-116596637-A → CN.116596637.A), sonst 404 (P0-Probe
2026-08-09 in #7).

    python scripts/enrich_ops_legal.py --cpc-limit 5 --cap 20   # Smoke
    python scripts/enrich_ops_legal.py                          # 100/Achse, max 1500 Calls
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402

# Kuratierte Achsen = build_cpc_insights.CURATED + die 2026-08-Themes
CPCS = ["A01H", "A23C", "A23J", "A23L", "A61B", "A61K", "A63F", "B09B", "B25J",
        "B33Y", "C12N", "C25B", "D01F", "E04B", "F03D", "G06N", "G06Q", "G09B",
        "G16H", "G16Y", "H01M", "H02S", "H04W", "B64G", "H10K", "H01L"]

OPS = "https://ops.epo.org/3.2"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def event_date(ev: dict) -> str | None:
    """Datum eines INPADOC-Events: bevorzugt das Feld mit @desc 'Gazette DATE'
    (ops:L007EP u. ä. — Amts-spezifische Keys), sonst das erste ISO-Datum mit
    'date' in der Beschreibung. @dateMigr (oft 00010101) wird ignoriert."""
    fallback = None
    for v in ev.values():
        if not isinstance(v, dict):
            continue
        val = v.get("$")
        desc = (v.get("@desc") or "").lower()
        if isinstance(val, str) and ISO_DATE.match(val.strip()) and "date" in desc:
            if "gazette" in desc:
                return val.strip()
            fallback = fallback or val.strip()
    return fallback


def token() -> str:
    key = os.environ["EPO_OPS_CONSUMER_KEY"]
    sec = os.environ["EPO_OPS_CONSUMER_SECRET_KEY"]
    basic = base64.b64encode(f"{key}:{sec}".encode()).decode()
    r = httpx.post(f"{OPS}/auth/accesstoken",
                   headers={"Authorization": f"Basic {basic}",
                            "Content-Type": "application/x-www-form-urlencoded"},
                   data={"grant_type": "client_credentials"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def ensure_tables() -> None:
    import psycopg2
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS patent_legal_events (
        pub_number TEXT, seq SMALLINT, member_doc TEXT,
        event_code TEXT, event_desc TEXT, event_date DATE,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (pub_number, seq))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS ops_legal_state (
        pub_number TEXT PRIMARY KEY, http_status INT, events INT,
        ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()
    conn.close()


def candidates(cpc_limit: int) -> list[str]:
    """Jüngste N Patente je kuratierter Subclass, noch nicht abgefragt."""
    out: list[str] = []
    with db_mod.get_connection() as c:
        for cpc in CPCS:
            rows = c.execute(
                "SELECT r.pub_number FROM raw_entries r "
                "JOIN patent_cpc pc ON pc.pub_number = r.pub_number "
                "WHERE pc.subclass = ? AND r.published_date >= '2023-01-01' "
                "AND NOT EXISTS (SELECT 1 FROM ops_legal_state s "
                "                WHERE s.pub_number = r.pub_number) "
                "GROUP BY r.pub_number, r.published_date "
                "ORDER BY r.published_date DESC LIMIT ?", (cpc, cpc_limit)).fetchall()
            out.extend(r["pub_number"] for r in rows)
    return list(dict.fromkeys(out))


def extract_events(j: dict, want_cc: str, want_nr: str):
    """Events des angefragten Familienmitglieds (Fallback: erstes Mitglied)."""
    members = (j.get("ops:world-patent-data", {})
                .get("ops:patent-family", {})
                .get("ops:family-member", []))
    if isinstance(members, dict):
        members = [members]
    chosen, member_doc = None, ""
    for m in members:
        pref = m.get("publication-reference", {}).get("document-id", [])
        if isinstance(pref, dict):
            pref = [pref]
        for did in pref:
            cc = (did.get("country", {}) or {}).get("$", "")
            nr = (did.get("doc-number", {}) or {}).get("$", "")
            if cc == want_cc and nr == want_nr:
                chosen, member_doc = m, f"{cc}{nr}"
                break
        if chosen:
            break
    if chosen is None and members:
        chosen = members[0]
        pref = chosen.get("publication-reference", {}).get("document-id", [])
        if isinstance(pref, dict):
            pref = [pref]
        if pref:
            member_doc = ((pref[0].get("country", {}) or {}).get("$", "") +
                          (pref[0].get("doc-number", {}) or {}).get("$", ""))
    if chosen is None:
        return "", []
    legals = chosen.get("ops:legal", [])
    if isinstance(legals, dict):
        legals = [legals]
    events = []
    for seq, ev in enumerate(legals, 1):
        code = ev.get("@code", "")
        desc = (ev.get("@desc") or "").strip()[:200]
        events.append((seq, member_doc, code, desc, event_date(ev)))
    return member_doc, events


def main() -> int:
    ap = argparse.ArgumentParser(description="OPS INPADOC legal events for curated technologies")
    ap.add_argument("--cpc-limit", type=int, default=100, help="Patente je CPC-Achse")
    ap.add_argument("--cap", type=int, default=1500, help="max OPS-Calls je Lauf (Fair-Use)")
    ap.add_argument("--sleep", type=float, default=0.7)
    args = ap.parse_args()

    ensure_tables()
    pubs = candidates(args.cpc_limit)[: args.cap]
    print(f"{len(pubs)} Kandidaten (je Achse ≤{args.cpc_limit}, Cap {args.cap})")
    if not pubs:
        return 0

    import psycopg2
    from psycopg2.extras import execute_values
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor()
    tok = token()
    H = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}
    st = {"ok": 0, "e404": 0, "err": 0, "events": 0}
    t0 = time.time()
    with httpx.Client(headers=H, timeout=30) as client:
        for i, pub in enumerate(pubs):
            parts = pub.split("-")
            docdb = ".".join(parts)
            try:
                r = client.get(f"{OPS}/rest-services/legal/publication/docdb/{docdb}")
                if r.status_code == 200:
                    _, events = extract_events(r.json(), parts[0], parts[1])
                    if events:
                        execute_values(cur,
                            "INSERT INTO patent_legal_events "
                            "(pub_number, seq, member_doc, event_code, event_desc, event_date) "
                            "VALUES %s ON CONFLICT DO NOTHING",
                            [(pub, *e) for e in events])
                    cur.execute("INSERT INTO ops_legal_state (pub_number, http_status, events) "
                                "VALUES (%s, 200, %s) ON CONFLICT DO NOTHING", (pub, len(events)))
                    st["ok"] += 1
                    st["events"] += len(events)
                else:
                    cur.execute("INSERT INTO ops_legal_state (pub_number, http_status, events) "
                                "VALUES (%s, %s, 0) ON CONFLICT DO NOTHING", (pub, r.status_code))
                    st["e404"] += 1
                if r.status_code in (403, 429):  # Fair-Use-Grenze → sofort aufhören
                    print(f"OPS drosselt ({r.status_code}) — Lauf endet nach {i+1} Calls")
                    break
            except Exception as exc:  # noqa: BLE001
                st["err"] += 1
                print(f"  err {pub}: {type(exc).__name__}")
            if i % 50 == 49:
                conn.commit()
                tok = token()  # Token läuft nach ~20 min ab
                client.headers["Authorization"] = f"Bearer {tok}"
                print(f"  … {i+1}/{len(pubs)} ({st['ok']} ok, {st['events']} Events, "
                      f"{time.time()-t0:.0f}s)")
            time.sleep(args.sleep)
    conn.commit()
    conn.close()
    print(f"\nFERTIG: {st['ok']} ok · {st['e404']} ohne/4xx · {st['err']} Fehler · "
          f"{st['events']} Events · {(time.time()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
