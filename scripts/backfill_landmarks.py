#!/usr/bin/env python3
"""Landmark-Backfill (#80): Standardwerke vor 2010 gezielt nachladen.

Der Korpus-Schnitt (Jahr >= 2010) hat die klassischen Standardwerke der
Felder ausgeschlossen — genau die Werke, in die Forschung diffundiert
(Laser-/LED-Argument des Owners). Dieser Lauf holt sie über die OpenAlex-
API gezielt nach: **Jahr < 2010, Englisch, Abstract vorhanden, Artikel/
Review, fwci >= 25** (das Landmark-Kriterium, Top 1 % feldnormierter
Impact) — gemessen 248.043 Werke, via Cursor-Paging ~1.250 Calls, weit
unter dem Fair-Use-Limit (100k/Tag).

Füllt research_corpus UND die Nebentabellen (authors_flat, work_journal,
citation_recent) in einem Durchgang — die API liefert authorships,
primary_location und counts_by_year mit. Idempotent (ON CONFLICT), bei
Abbruch einfach neu starten.

    python scripts/backfill_landmarks.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402
from scripts.ingest_openalex_snapshot import reconstruct  # noqa: E402

API = "https://api.openalex.org/works"
FILTER = ("publication_year:<2010,language:en,has_abstract:true,"
          "type:article|review,fwci:>25")
SELECT = ("id,doi,title,publication_date,publication_year,type,"
          "abstract_inverted_index,cited_by_count,counts_by_year,fwci,"
          "is_retracted,primary_topic,authorships,primary_location")
AUTHOR_CAP = 30
INSERT_TMPL = ("(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
               "setweight(to_tsvector('english', left(%s, 2000)), 'A') || "
               "setweight(to_tsvector('english', left(%s, 16000)), 'B'))")


def main() -> int:
    import httpx
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    t0 = time.time()
    cursor = "*"
    total = inserted = 0
    rc_buf: list[tuple] = []
    af_buf: list[tuple] = []
    wj_buf: list[tuple] = []
    cr_buf: list[tuple] = []

    def flush():
        nonlocal inserted
        if rc_buf:
            psycopg2.extras.execute_values(
                cur, "INSERT INTO research_corpus (id, doi, title, abstract, "
                     "published, year, type, topic, cited_by_count, fwci, "
                     "is_retracted, tsv) VALUES %s ON CONFLICT (id) DO NOTHING",
                rc_buf, template=INSERT_TMPL, page_size=500)
            inserted += max(cur.rowcount, 0)
            rc_buf.clear()
        for buf, sql in [
            (af_buf, "INSERT INTO research_authors_flat VALUES %s "
                     "ON CONFLICT (work_id) DO NOTHING"),
            (wj_buf, "INSERT INTO research_work_journal VALUES %s "
                     "ON CONFLICT (work_id) DO NOTHING"),
            (cr_buf, "INSERT INTO research_citation_recent VALUES %s "
                     "ON CONFLICT (work_id) DO NOTHING"),
        ]:
            if buf:
                psycopg2.extras.execute_values(cur, sql, buf, page_size=500)
                buf.clear()

    with httpx.Client(timeout=120) as client:
        while cursor:
            # Sanfte Drossel (~2 Calls/s): Nach dem grossen Snapshot-Tag hat
            # OpenAlex uns in einen laengeren 429-Cooldown gesetzt — der
            # zweite Lauf kam gar nicht erst rein. Lieber langsam und durch.
            time.sleep(0.5)
            for attempt, wait in enumerate((10, 30, 60, 120, 240)):
                r = client.get(API, params={
                    "filter": FILTER, "select": SELECT, "per-page": 200,
                    "cursor": cursor, "mailto": "trends@catandary.de"})
                if r.status_code == 200:
                    break
                retry_after = int(r.headers.get("retry-after") or 0)
                if r.status_code == 429 and retry_after > 300:
                    # Tageslimit (Retry-After in Stunden) — Retries sind
                    # sinnlos UND unhoeflich. Sauber raus, aussen neu planen.
                    print(f"TAGESLIMIT: Retry-After {retry_after}s "
                          f"(~{retry_after/3600:.1f}h) — Abbruch, idempotent "
                          "neu starten nach Ablauf", flush=True)
                    return 2
                print(f"  HTTP {r.status_code}, warte {wait}s "
                      f"(Versuch {attempt+1}/5)", flush=True)
                time.sleep(wait)
            else:
                print(f"ABBRUCH: API {r.status_code} — Lauf ist idempotent, "
                      "neu starten", flush=True)
                return 1
            j = r.json()
            cursor = j["meta"].get("next_cursor")
            for w in j["results"]:
                wid = (w.get("id") or "").rsplit("/", 1)[-1]
                title = (w.get("title") or "").strip()[:2000]
                abstract = reconstruct(w.get("abstract_inverted_index"))[:16000]
                if not wid or not title or len(abstract) < 50:
                    continue
                total += 1
                topic = w.get("primary_topic")
                topic = topic.get("display_name") if isinstance(topic, dict) else None
                rc_buf.append((wid, w.get("doi"), title, abstract,
                               w.get("publication_date"), w.get("publication_year"),
                               w.get("type"), topic, w.get("cited_by_count"),
                               w.get("fwci"), w.get("is_retracted"),
                               title, abstract))
                auths = w.get("authorships") or []
                names, insts = [], []
                for a in auths[:AUTHOR_CAP]:
                    nm = ((a.get("author") or {}).get("display_name") or "").strip()
                    if nm:
                        names.append(nm)
                    for inst in a.get("institutions") or []:
                        dn = (inst.get("display_name") or "").strip()
                        if dn and dn not in insts:
                            insts.append(dn)
                if names or insts:
                    af_buf.append((wid, "; ".join(names) or None,
                                   "; ".join(insts[:AUTHOR_CAP]) or None))
                loc = w.get("primary_location") or {}
                jn = ((loc.get("source") or {}).get("display_name") or "").strip()
                if jn:
                    wj_buf.append((wid, jn[:300]))
                cby = w.get("counts_by_year") or []
                ctotal = sum(x.get("cited_by_count") or 0 for x in cby)
                if ctotal > 0:
                    recent = sum(x.get("cited_by_count") or 0 for x in cby
                                 if (x.get("year") or 0) >= 2025)
                    cr_buf.append((wid, recent, ctotal))
            if len(rc_buf) >= 1000:
                flush()
            if total and total % 20_000 < 200:
                print(f"  {total:,} verarbeitet, {inserted:,} neu, "
                      f"{time.time()-t0:.0f}s", flush=True)
    flush()
    # Statistik-/Aggregat-Tabellen bleiben dem Monats-Sync überlassen — bis
    # dahin fehlen die Backfill-Werke in Topic-Zahlen, nicht in der Suche.
    print(f"FERTIG: {total:,} verarbeitet, {inserted:,} neu eingefügt in "
          f"{(time.time()-t0)/60:.0f} min", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
