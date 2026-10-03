#!/usr/bin/env python3
"""Dry run for completing the signal space's past (Owner 2026-10-03). Writes nothing to the DB.

Question: how many patents and research works before 2023 would have to be embedded so
the signal cloud, the nests and the citation graph have a past — without bloating the DB?

The plan it measures (docs/history_backfill_plan_2026-10-03.md):

  * frame per month and tier = what CAN be embedded: patents with an abstract (>= 80
    characters, one per DOCDB family, dated by the family's earliest publication) from
    raw_entries, research works with an abstract from research_corpus;
  * random layer: per month the QUOTA members with the smallest hash — the representative
    sample; each point later carries weight = frame / sampled, so the past is not counted
    a hundred times too thin. Members that already have a vector cost nothing;
  * cited layer: every patent family cited by a patent already in the signal space (the
    bridge to the TIR graph), outside the random layer — deliberately not representative,
    flagged, never weighted;
  * cost: rows to embed, GPU hours with the 3090 and the 5080 in parallel (rates measured
    28.09., docs/space_eval_2026-09-28.md, ~600 characters = title + excerpt[:500]), and
    storage as float16 1024-prefix in a side table without an ANN index.

    .venv/bin/python scripts/history_plan.py                     # 2,000 per month
    .venv/bin/python scripts/history_plan.py --quota 1000 --json data/history_plan.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.db import get_connection  # noqa: E402

CACHE = Path.home() / ".cache" / "catandary" / "domain_service"
RATE_3090 = 18.5          # texts/s, ~600 characters, measured 28.09.
RATE_5080 = 32.0
BYTES_PER_ROW = 2048 + 120  # float16 x 1024 + ids, month, tier, weight, tuple header
HASH = "(({k})::bigint * 2654435761) %% 4294967296"


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def month_num(y: int, m: int) -> int:
    return y * 12 + m - 1


def space_coverage() -> dict[str, dict[int, int]]:
    """Signals with a vector per tier and month, from the domain service's copy."""
    from pipeline.domain_service import TIER_NAMES, ST_PUBLISHED
    meta = np.load(CACHE / "meta.npz")
    keep = meta["status"] <= ST_PUBLISHED
    out: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for t, m in zip(meta["tier"][keep], meta["month"][keep]):
        out[TIER_NAMES[t]][int(m)] += 1
    return out


def patents(c, start: str, until: str, quota: int) -> dict[int, dict]:
    log("patents: vectors already stored, cited set …")
    c.execute("""CREATE TEMP TABLE vecraw AS SELECT DISTINCT raw_entry_id AS id FROM trends
                 WHERE embedding_1024 IS NOT NULL AND raw_entry_id IS NOT NULL""")
    c.execute("CREATE INDEX ON vecraw(id)")
    c.execute("""CREATE TEMP TABLE cited AS SELECT DISTINCT l.dst_pub AS p FROM patent_links l
                 JOIN (SELECT DISTINCT r.pub_number p FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id
                       WHERE r.pub_number IS NOT NULL AND t.status IN ('signal','published')
                       AND t.embedding_1024 IS NOT NULL) e ON e.p = l.src_pub
                 WHERE l.link_type = 'cites'""")
    c.execute("CREATE INDEX ON cited(p)")
    c.execute("ANALYZE vecraw"); c.execute("ANALYZE cited")
    log("patents: families with an abstract …")
    c.execute(f"""CREATE TEMP TABLE fam AS
        SELECT coalesce(pf.family_id, -r.id) AS fid, min(r.published_date) AS d,
               bool_or(v.id IS NOT NULL OR r.embedding_blob IS NOT NULL) AS vec,
               bool_or(ci.p IS NOT NULL) AS cited
        FROM raw_entries r
        LEFT JOIN patent_family pf ON pf.pub_number = r.pub_number
        LEFT JOIN vecraw v ON v.id = r.id
        LEFT JOIN cited ci ON ci.p = r.pub_number
        WHERE r.pub_number IS NOT NULL AND octet_length(r.excerpt) >= 80
          AND r.published_date >= ? AND r.published_date < ?
        GROUP BY 1""", (start, until))
    log("patents: random layer per month …")
    rows = c.execute(f"""
        WITH f AS (SELECT fid, vec, cited, extract(year FROM d)::int * 12 + extract(month FROM d)::int - 1 AS m,
                          row_number() OVER (PARTITION BY date_trunc('month', d)
                                             ORDER BY {HASH.format(k='abs(fid)')}, fid) AS rk
                   FROM fam)
        SELECT m, count(*) AS frame,
               count(*) FILTER (WHERE vec) AS have_vec,
               count(*) FILTER (WHERE rk <= ?) AS sampled,
               count(*) FILTER (WHERE rk <= ? AND NOT vec) AS embed_random,
               count(*) FILTER (WHERE cited) AS cited,
               count(*) FILTER (WHERE cited AND rk > ? AND NOT vec) AS embed_cited
        FROM f GROUP BY m""", (quota, quota, quota)).fetchall()
    return {int(r["m"]): dict(r) for r in rows}


def science(c, start: str, until: str, quota: int) -> dict[int, dict]:
    log("science: works already in the signal space …")
    c.execute("""CREATE TEMP TABLE scivec AS SELECT DISTINCT r.openalex_id AS w FROM raw_entries r
                 JOIN vecraw v ON v.id = r.id WHERE r.openalex_id IS NOT NULL""")
    c.execute("CREATE INDEX ON scivec(w)"); c.execute("ANALYZE scivec")
    log("science: works with an abstract, random layer per month …")
    rows = c.execute(f"""
        WITH f AS (SELECT (s.w IS NOT NULL) AS vec,
                          extract(year FROM rc.published)::int * 12 + extract(month FROM rc.published)::int - 1 AS m,
                          row_number() OVER (PARTITION BY date_trunc('month', rc.published)
                                             ORDER BY {HASH.format(k="hashtext(rc.id)::bigint & 2147483647")}, rc.id) AS rk
                   FROM research_corpus rc LEFT JOIN scivec s ON s.w = rc.id
                   WHERE rc.published >= ? AND rc.published < ? AND octet_length(rc.abstract) >= 80
                     AND NOT coalesce(rc.is_retracted, FALSE))
        SELECT m, count(*) AS frame, count(*) FILTER (WHERE vec) AS have_vec,
               count(*) FILTER (WHERE rk <= ?) AS sampled,
               count(*) FILTER (WHERE rk <= ? AND NOT vec) AS embed_random,
               0 AS cited, 0 AS embed_cited
        FROM f GROUP BY m""", (start, until, quota, quota)).fetchall()
    return {int(r["m"]): dict(r) for r in rows}


def by_year(per_month: dict[int, dict], space: dict[int, int]) -> list[dict]:
    years: dict[int, dict] = {}
    for m, r in per_month.items():
        y = years.setdefault(m // 12, defaultdict(int))
        for k in ("frame", "have_vec", "sampled", "embed_random", "cited", "embed_cited"):
            y[k] += int(r[k])
        y["in_space_now"] += int(space.get(m, 0))
    return [{"year": y, **dict(v)} for y, v in sorted(years.items())]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quota", type=int, default=2000, help="random layer per month and tier")
    ap.add_argument("--patents-from", default="1990-01-01")
    ap.add_argument("--science-from", default="2010-01-01")
    ap.add_argument("--until", default="2023-01-01", help="exclusive; the signal space is dense from here")
    ap.add_argument("--json", default=str(ROOT / "data" / "history_plan.json"))
    args = ap.parse_args()
    t0 = time.time()
    space = space_coverage()
    with get_connection() as c:
        c.execute("SET statement_timeout = 0")
        c.execute("SET work_mem = '1GB'")
        pat = patents(c, args.patents_from, args.until, args.quota)
        log(f"patents done ({time.time() - t0:.0f} s)")
        sci = science(c, args.science_from, args.until, args.quota)
        log(f"science done ({time.time() - t0:.0f} s)")
    report = {"quota": args.quota, "until": args.until, "tiers": {}}
    total_embed = 0
    for tier, data in (("patent", pat), ("science", sci)):
        years = by_year(data, space.get(tier, {}))
        tot = {k: sum(y[k] for y in years) for k in years[0] if k != "year"} if years else {}
        embed = tot.get("embed_random", 0) + tot.get("embed_cited", 0)
        total_embed += embed
        thin = sum(1 for r in data.values() if r["frame"] < args.quota)
        report["tiers"][tier] = {"years": years, "total": tot, "to_embed": embed,
                                 "months": len(data), "months_below_quota": thin}
        print(f"\n== {tier} (quota {args.quota}/month, {len(data)} months, {thin} below quota)")
        print(f"{'year':>5} {'frame':>11} {'in space':>9} {'sampled':>8} {'embed rnd':>9} {'cited':>8} {'embed cit':>9}")
        for y in years:
            print(f"{y['year']:>5} {y['frame']:>11,} {y['in_space_now']:>9,} {y['sampled']:>8,} "
                  f"{y['embed_random']:>9,} {y['cited']:>8,} {y['embed_cited']:>9,}")
        print(f"{'sum':>5} {tot.get('frame', 0):>11,} {tot.get('in_space_now', 0):>9,} {tot.get('sampled', 0):>8,} "
              f"{tot.get('embed_random', 0):>9,} {tot.get('cited', 0):>8,} {tot.get('embed_cited', 0):>9,}")
    rate = RATE_3090 + RATE_5080
    rows_stored = sum(t["total"].get("sampled", 0) + t["total"].get("embed_cited", 0)
                      for t in report["tiers"].values())
    report["cost"] = {
        "to_embed": total_embed, "rows_stored": rows_stored,
        "gpu_hours_parallel": round(total_embed / rate / 3600, 1),
        "gpu_hours_3090_alone": round(total_embed / RATE_3090 / 3600, 1),
        "share_3090": round(RATE_3090 / rate, 2),
        "storage_gb": round(rows_stored * BYTES_PER_ROW / 1e9, 2),
        "storage_gb_if_in_trends": round(rows_stored * 33_000 / 1e9, 1),
        "ram_gb_domain_service": round(rows_stored * 2048 / 1e9, 2),
        "runtime_s": round(time.time() - t0),
    }
    c_ = report["cost"]
    print(f"\nto embed {total_embed:,} · stored rows {rows_stored:,} · "
          f"{c_['gpu_hours_parallel']} h on 3090+5080 in parallel ({c_['gpu_hours_3090_alone']} h on the 3090 alone; "
          f"3090 takes {c_['share_3090']:.0%}) · {c_['storage_gb']} GB side table "
          f"(vs ~{c_['storage_gb_if_in_trends']} GB in trends) · {c_['ram_gb_domain_service']} GB RAM if the "
          f"domain service loads it · {c_['runtime_s']} s")
    Path(args.json).write_text(json.dumps(report, indent=1, default=int), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
