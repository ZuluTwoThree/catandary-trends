#!/usr/bin/env python3
"""Per-source signal yield / pass-rate report for a backfill batch.

Answers "which sources produce many signals and which few" — the real-yield
counterpart to the dry-run's raw article counts. For each source it joins the
ingested raw_entries to the trends they became, and reports:

    raw → processed → signals (trends)   with pass-rate = signals / processed

plus the dominant filter reason for the rest. High-volume / low-pass-rate
sources (e.g. entertainment feeds producing few real trend signals) surface at
the bottom as a "noise watchlist" — the basis for per-source relevance caps.

Scope the batch with --min-id (raw_entries.id watermark captured before ingest)
and/or --since (fetched_at). With no scope it evaluates the whole DB.

Usage:
    # Welle-0 backfill batch (watermark captured before ingest)
    python scripts/source_signal_yield.py --min-id 66987
    python scripts/source_signal_yield.py --since 2026-06-21T13:19 --min-volume 20
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db import get_connection


def _reason_bucket(reason: str | None) -> str:
    if not reason:
        return "other"
    r = reason.lower()
    if r.startswith("not_relevant"):
        return "not_relevant"
    if r.startswith("duplicate"):
        return "duplicate"
    if "embedding" in r:
        return "embedding_error"
    if "relevance_filter_error" in r:
        return "relevance_error"
    if "classification" in r:
        return "classification_error"
    return "other"


def collect(min_id: int, since: str | None) -> list[dict]:
    where = ["1=1"]
    params: list = []
    if min_id:
        where.append("r.id > ?")
        params.append(min_id)
    if since:
        where.append("r.fetched_at >= ?")
        params.append(since.replace("T", " "))  # stored fetched_at is space-separated
    wsql = " AND ".join(where)

    rows_sql = f"""
        SELECT COALESCE(s.name, '?')        AS source,
               COALESCE(s.vertical, '?')    AS vertical,
               r.id                          AS rid,
               r.processed                   AS processed,
               r.filtered_out                AS filtered_out,
               r.filter_reason               AS filter_reason,
               (SELECT COUNT(*) FROM trends t WHERE t.raw_entry_id = r.id) AS trended
        FROM raw_entries r
        LEFT JOIN sources s ON r.source_id = s.id
        WHERE {wsql}
    """
    agg: dict[str, dict] = {}
    with get_connection() as c:
        for row in c.execute(rows_sql, params).fetchall():
            d = agg.setdefault(row["source"], {
                "source": row["source"], "vertical": row["vertical"],
                "raw": 0, "processed": 0, "signals": 0, "filtered": 0,
                "reasons": {}})
            d["raw"] += 1
            d["processed"] += row["processed"] or 0
            d["filtered"] += row["filtered_out"] or 0
            if row["trended"]:
                d["signals"] += 1
            elif row["filtered_out"]:
                b = _reason_bucket(row["filter_reason"])
                d["reasons"][b] = d["reasons"].get(b, 0) + 1
    out = list(agg.values())
    for d in out:
        d["pass_rate"] = (d["signals"] / d["processed"]) if d["processed"] else 0.0
        d["top_reason"] = max(d["reasons"], key=d["reasons"].get) if d["reasons"] else "-"
    return out


def render(rows: list[dict], min_volume: int, noise_pass: float) -> str:
    rows_sorted = sorted(rows, key=lambda d: d["raw"], reverse=True)
    tot_raw = sum(d["raw"] for d in rows)
    tot_proc = sum(d["processed"] for d in rows)
    tot_sig = sum(d["signals"] for d in rows)
    overall = (tot_sig / tot_proc) if tot_proc else 0.0

    L = [f"Sources: {len(rows)} | raw {tot_raw} | processed {tot_proc} | "
         f"signals {tot_sig} | overall pass {overall:.1%}", ""]
    L.append(f"{'Source':<28}{'Vert':<10}{'raw':>7}{'proc':>7}{'sig':>7}{'pass':>8}  top-filter")
    L.append("-" * 84)
    for d in rows_sorted:
        L.append(f"{d['source'][:27]:<28}{d['vertical']:<10}{d['raw']:>7}"
                 f"{d['processed']:>7}{d['signals']:>7}{d['pass_rate']*100:>7.1f}%  {d['top_reason']}")

    noisy = [d for d in rows_sorted if d["raw"] >= min_volume and d["pass_rate"] < noise_pass]
    if noisy:
        L += ["", f"NOISE WATCHLIST (raw >= {min_volume}, pass < {noise_pass:.0%}) — cap candidates:"]
        for d in noisy:
            L.append(f"  {d['source'][:34]:<35} raw {d['raw']:>5}  pass {d['pass_rate']*100:>5.1f}%  ({d['top_reason']})")
    top = sorted([d for d in rows if d["processed"] >= min_volume],
                 key=lambda d: d["pass_rate"], reverse=True)[:10]
    if top:
        L += ["", "HIGH-YIELD (best pass-rate, proc >= %d):" % min_volume]
        for d in top:
            L.append(f"  {d['source'][:34]:<35} pass {d['pass_rate']*100:>5.1f}%  sig {d['signals']:>4} / proc {d['processed']}")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-id", type=int, default=0, help="only raw_entries.id > this (batch watermark)")
    ap.add_argument("--since", help="only raw_entries.fetched_at >= this ISO timestamp")
    ap.add_argument("--min-volume", type=int, default=20, help="threshold for watchlist/high-yield")
    ap.add_argument("--noise-pass", type=float, default=0.15, help="pass-rate below this = noise watchlist")
    ap.add_argument("--out", help="also write the report to this path")
    args = ap.parse_args()

    rows = collect(args.min_id, args.since)
    if not rows:
        print("No raw_entries in scope (min-id=%s, since=%s)." % (args.min_id, args.since))
        return 0
    report = render(rows, args.min_volume, args.noise_pass)
    print(report)
    out = args.out
    if not out:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        out = str(Path(__file__).parent.parent / "data" / f"source_signal_yield_{ts}.txt")
    Path(out).parent.mkdir(exist_ok=True)
    Path(out).write_text(report + "\n")
    print(f"\nReport: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
