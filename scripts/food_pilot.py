#!/usr/bin/env python3
"""Food pilot (#114): patents and research of the FOOD domain into the signal space.

The signal space holds almost no patents for 2019-2025 and a thin slice of food
science (issue #114). The pilot takes ONE domain completely instead of a random
sample: the window is the last three years, the selection is by domain, and
everything selected goes the same way every other research/patent signal goes —
`scripts/signal_batch_embedded.py` (distill heads, embedding dedup, status
'signal') — with the text cleaned before embedding (`--clean-text`,
docs/space_eval_2026-09-28.md).

    .venv/bin/python scripts/food_pilot.py select                # counts + id lists, writes nothing to the DB
    .venv/bin/python scripts/food_pilot.py takeover --limit 500  # dry run: what would be inserted
    .venv/bin/python scripts/food_pilot.py takeover --apply      # research_corpus -> raw_entries
    .venv/bin/python scripts/signal_batch_embedded.py --ids-file data/food_pilot/embed.ids --clean-text
    .venv/bin/python scripts/food_pilot.py status                # outcome per group

Selection (counted 28.09., issue #114 comments):
  patents   raw_entries of `EPO DOCDB (FOOD)` (CPC A23, A21, A22, A01H, C12C/G/J, C13),
            published in the window, abstract > 200 chars, not a utility model (U),
            ONE publication per DOCDB family (`patent_family`): the earliest that
            carries an abstract (EP/KR members are header stubs); a family that
            already has a signal is skipped. `--with-cross-cpc` adds food-CPC patents
            routed to other verticals (off by default).
  research  research_corpus (OpenAlex) in the window, abstract > 200 chars, type
            article/preprint/review, not a repository deposit, no year-only date
            (published = 1 January: 1.49M such rows would inflate every January),
            not yet a research signal (DOI):
              · subfield Food Science (incl. Culinary Culture and Tourism)
              · subfield Nutrition and Dietetics
              · alternative proteins anywhere else, by phrase in title + abstract
            Taken over into raw_entries under three signal-only pseudo-sources
            (`llm_pipeline = FALSE`, so the nightly cycle never writes articles from
            them), excerpt `[Science · <group>] <cleaned abstract>` — the tag is what
            build_research_index.py reads as the concept; --clean-text keeps it out of
            the vector.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import db  # noqa: E402
from pipeline.research_kinds import is_repository_url  # noqa: E402
from pipeline.text_clean import clean_text  # noqa: E402

OUT = ROOT / "data" / "food_pilot"
WINDOW_START = "2023-10-01"
FOOD_SUBFIELDS = ("Food Science", "Nutrition and Dietetics")
WORK_TYPES = ("article", "preprint", "review")
ALT_PROTEIN_PHRASES = (
    "alternative protein", "alternative proteins", "cultivated meat", "cultured meat",
    "cell-based meat", "cell-cultured meat", "meat analogue", "meat analog", "meat substitute",
    "plant-based meat", "mycoprotein", "single cell protein", "single-cell protein",
    "precision fermentation", "insect protein", "edible insects", "microalgae protein",
    "microalgal protein", "fungal biomass", "recombinant milk", "textured vegetable protein",
    "plant-based dairy", "dairy alternative",
)
FOOD_CPC_SUBCLASS_SQL = ("(pc.subclass LIKE 'A23%%' OR pc.subclass IN "
                         "('A21B','A21C','A21D','A22B','A22C','C12C','C12G','C12J','C13B','C13K'))")
SOURCES = {  # group -> pseudo-source name
    "Food Science": "OpenAlex corpus: Food Science",
    "Nutrition and Dietetics": "OpenAlex corpus: Nutrition and Dietetics",
    "Alternative proteins": "OpenAlex corpus: Alternative proteins",
}
SOURCE_FEED = "https://api.openalex.org/works?filter=primary_topic.subfield&pilot=food-114"


def rows(sql: str, params=()) -> list[dict]:
    with db.get_connection() as c:
        c.execute("SET statement_timeout = '1800s'")
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------------ select

def select_patents(start: str, cross_cpc: bool) -> list[int]:
    src = ("s.name LIKE 'EPO DOCDB%%'" if cross_cpc else "s.name = 'EPO DOCDB (FOOD)'")
    cross = (f"""AND (s.name = 'EPO DOCDB (FOOD)' OR EXISTS (
                    SELECT 1 FROM patent_cpc pc WHERE pc.pub_number = r.pub_number AND {FOOD_CPC_SUBCLASS_SQL}))"""
             if cross_cpc else "")
    got = rows(f"""
        WITH cand AS (
          SELECT r.id, r.processed, r.published_date, pf.family_id
          FROM raw_entries r JOIN sources s ON s.id = r.source_id
          LEFT JOIN patent_family pf ON pf.pub_number = r.pub_number
          WHERE {src} {cross} AND r.published_date >= ? AND length(coalesce(r.excerpt, '')) > 200
            AND coalesce(r.kind_code, split_part(r.pub_number, '-', 3)) <> 'U'),
        signalled AS (
          SELECT DISTINCT pf.family_id FROM patent_family pf
          JOIN raw_entries r ON r.pub_number = pf.pub_number
          JOIN trends t ON t.raw_entry_id = r.id AND t.status = 'signal'
          WHERE pf.family_id IN (SELECT family_id FROM cand WHERE family_id IS NOT NULL)),
        one AS (
          SELECT DISTINCT ON (coalesce(family_id, -id)) id, processed, family_id
          FROM cand ORDER BY coalesce(family_id, -id), published_date, id)
        SELECT id FROM one
        WHERE NOT processed AND (family_id IS NULL OR family_id NOT IN (SELECT family_id FROM signalled))
        ORDER BY id""", (start,))
    return [int(r["id"]) for r in got]


def select_research(start: str) -> list[dict]:
    tsq = " || ".join("phraseto_tsquery('english', %s)" for _ in ALT_PROTEIN_PHRASES)
    base = """rc.published >= %s AND length(coalesce(rc.abstract, '')) > 200
              AND NOT (extract(month from rc.published) = 1 AND extract(day from rc.published) = 1)
              AND rc.type IN ('article','preprint','review')
              AND NOT coalesce(rc.is_retracted, false)"""
    # the ? -> %s wrapper is not used here: literal %s placeholders, psycopg2-style
    sql = f"""
        WITH ft AS (SELECT DISTINCT ON (topic) topic, subfield FROM openalex_topics ORDER BY topic),
        sub AS (
          SELECT rc.id, ft.subfield AS grp FROM research_corpus rc JOIN ft ON ft.topic = rc.topic
          WHERE ft.subfield IN ('Food Science', 'Nutrition and Dietetics') AND {base}),
        alt AS (
          SELECT rc.id, 'Alternative proteins' AS grp FROM research_corpus rc
          LEFT JOIN ft ON ft.topic = rc.topic
          WHERE rc.tsv @@ ({tsq}) AND {base}
            AND (ft.subfield IS NULL OR ft.subfield NOT IN ('Food Science', 'Nutrition and Dietetics')))
        SELECT x.id, x.grp, rc.doi FROM (SELECT * FROM sub UNION ALL SELECT * FROM alt) x
        JOIN research_corpus rc ON rc.id = x.id"""
    # "already a research signal" is checked here, not in SQL: research_signals has
    # no index on lower(url), and the anti-join ran into the 30-min timeout (29.09.)
    params = (start, *ALT_PROTEIN_PHRASES, start)   # sub: base; alt: phrases, then base
    import psycopg2  # direct: the phrase list needs real %s placeholders
    conn = psycopg2.connect(db.DATABASE_URL)
    try:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '1800s'")
        cur.execute(sql, params)
        out = [{"rc_id": r[0], "group": r[1], "doi": r[2]} for r in cur.fetchall()]
    finally:
        conn.close()
    known = {r["u"] for r in rows("SELECT lower(url) AS u FROM research_signals")}
    fresh = [r for r in out if not (r["doi"] and r["doi"].lower() in known)]
    kept = [r for r in fresh if not is_repository_url(r["doi"])]
    log(f"research: {len(out):,} candidates, {len(out) - len(fresh):,} already research signals, "
        f"{len(fresh) - len(kept):,} repository deposits dropped")
    return kept


def cmd_select(args) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    pats = select_patents(args.start, args.with_cross_cpc)
    log(f"patents: {len(pats):,} (one per family, unprocessed, no U{', + cross-vertical food CPC' if args.with_cross_cpc else ''})")
    res = select_research(args.start)
    by = {}
    for r in res:
        by[r["group"]] = by.get(r["group"], 0) + 1
    (OUT / "patents.ids").write_text("\n".join(map(str, pats)) + "\n")
    with (OUT / "research.jsonl").open("w") as f:
        for r in res:
            f.write(json.dumps(r) + "\n")
    summary = {"window_start": args.start, "cross_cpc": args.with_cross_cpc,
               "patents": len(pats), "research": len(res), "research_by_group": by,
               "selected_at": time.strftime("%Y-%m-%d %H:%M"), "seconds": round(time.time() - t0)}
    (OUT / "selection.json").write_text(json.dumps(summary, indent=2))
    log(f"research by group: {by}")
    log(f"selection written to {OUT} ({summary['seconds']} s)")
    return 0


# ---------------------------------------------------------------- takeover

def _sources() -> dict[str, int]:
    out = {}
    for grp, name in SOURCES.items():
        sid = db.upsert_source(name=name, feed_url=f"{SOURCE_FEED}&group={grp.replace(' ', '+')}",
                               source_type="research", vertical="FOOD", llm_pipeline=False)
        with db.get_connection() as c:     # an existing row keeps its flags: enforce signal mode
            c.execute("UPDATE sources SET llm_pipeline = FALSE, active = TRUE WHERE id = ?", (sid,))
        out[grp] = sid
    return out


def cmd_takeover(args) -> int:
    sel = [json.loads(line) for line in (OUT / "research.jsonl").read_text().splitlines() if line.strip()]
    if args.limit:
        sel = sel[: args.limit]
    ids = [r["rc_id"] for r in sel]
    grp = {r["rc_id"]: r["group"] for r in sel}
    log(f"takeover: {len(sel):,} selected works{'' if args.apply else ' (dry run)'}")
    src = _sources() if args.apply else {g: -1 for g in SOURCES}
    inserted = dup_known = 0
    raw_ids: list[int] = []
    meta: list[tuple] = []
    for start in range(0, len(ids), 5000):
        chunk = ids[start:start + 5000]
        works = rows("""SELECT id, doi, title, abstract, published, type, cited_by_count, is_retracted
                        FROM research_corpus WHERE id = ANY(?)""", (chunk,))
        for w in works:
            url = w["doi"] or f"https://openalex.org/{w['id']}"
            title = clean_text(w["title"])[:500]
            if not title:
                continue
            g = grp[w["id"]]
            excerpt = f"[Science · {g}] {clean_text(w['abstract'])}"[:2000]
            if not args.apply:
                inserted += 1
                continue
            eid = db.insert_raw_entry(src[g], url, title, excerpt, str(w["published"]),
                                      openalex_id=w["id"])
            if eid is None:                       # URL already known (e.g. a fresh sweep)
                known = rows("SELECT id, processed FROM raw_entries WHERE url = ?", (url,))
                if known and not known[0]["processed"]:
                    raw_ids.append(int(known[0]["id"]))
                dup_known += 1
            else:
                raw_ids.append(int(eid))
                inserted += 1
            meta.append((w["id"], w["cited_by_count"], "[]", w["type"], 1 if w["is_retracted"] else 0))
        if args.apply and meta:
            db.insert_openalex_meta(meta)
            meta.clear()
        log(f"  {min(start + 5000, len(ids)):,}/{len(ids):,}: {inserted:,} inserted, {dup_known:,} already known")
    if args.apply:
        pats = [int(x) for x in (OUT / "patents.ids").read_text().split()]
        if args.limit:
            pats = pats[: args.limit]
        (OUT / "research_raw.ids").write_text("\n".join(map(str, raw_ids)) + "\n")
        (OUT / "embed.ids").write_text("\n".join(map(str, pats + raw_ids)) + "\n")
        log(f"embed list: {len(pats):,} patents + {len(raw_ids):,} research -> {OUT / 'embed.ids'}")
        log("next: .venv/bin/python scripts/signal_batch_embedded.py "
            f"--ids-file {OUT / 'embed.ids'} --clean-text")
    return 0


# ------------------------------------------------------------------ status

def cmd_status(args) -> int:
    f = OUT / "embed.ids"
    if not f.exists():
        print("no embed.ids yet — run select + takeover --apply")
        return 1
    ids = [int(x) for x in f.read_text().split()]
    res = rows("""
        SELECT CASE WHEN s.name LIKE 'EPO DOCDB%%' THEN 'patents' ELSE s.name END AS grp,
               count(*) AS n,
               count(*) FILTER (WHERE t.status = 'signal') AS signals,
               count(*) FILTER (WHERE r.filter_reason LIKE 'not_relevant%%') AS not_relevant,
               count(*) FILTER (WHERE r.filter_reason LIKE '%%duplicate%%') AS duplicates,
               count(*) FILTER (WHERE r.filtered_out AND r.filter_reason NOT LIKE 'not_relevant%%'
                                AND r.filter_reason NOT LIKE '%%duplicate%%') AS other_filtered,
               count(*) FILTER (WHERE NOT r.processed) AS unprocessed
        FROM raw_entries r JOIN sources s ON s.id = r.source_id
        LEFT JOIN trends t ON t.raw_entry_id = r.id
        WHERE r.id = ANY(?) GROUP BY 1 ORDER BY 2 DESC""", (ids,))
    for r in res:
        print(json.dumps(r))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Food pilot (#114): select, take over, check")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select", help="count and list the selection (reads only)")
    s.add_argument("--start", default=WINDOW_START)
    s.add_argument("--with-cross-cpc", action="store_true",
                   help="add food-CPC patents routed to other verticals")
    t = sub.add_parser("takeover", help="research_corpus -> raw_entries (dry run unless --apply)")
    t.add_argument("--apply", action="store_true")
    t.add_argument("--limit", type=int, default=0, help="first N research works and N patents (test runs)")
    sub.add_parser("status", help="outcome per group for embed.ids")
    args = ap.parse_args()
    return {"select": cmd_select, "takeover": cmd_takeover, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
