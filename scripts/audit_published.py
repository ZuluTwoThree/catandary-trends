#!/usr/bin/env python3
"""Retro-audit the published corpus for fabricated specifics (#11).

The grounding gate only started holding articles back recently; everything
published before that was written by models we now know invent specifics
(qwen3-30b: 32.9% of bodies, measured A/B). This re-runs the SAME check over
the published corpus to size the damage and mark the affected rows.

The check is pure regex over text the DB already holds — no LLM, no GPU. Cost
is CPU + one pass over the bodies, so auditing everything is cheap; only
REGENERATING flagged articles costs GPU time.

Marking is non-destructive: it writes grounding_flags/grounding_checked_at and
never touches `status`, so nothing disappears from the live site until we
decide it should.

    python scripts/audit_published.py                 # analyse only
    python scripts/audit_published.py --mark          # + write flags to DB
    python scripts/audit_published.py --samples 5     # + show worst offenders
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection
from pipeline.grounding import ungrounded_specifics

# Stage-6 content model history — a body's model follows from created_at.
# (be444d0 switched 35B→30B on 2026-06-26; e423ee0 switched 30B→Gemma on 2026-07-14.)
ERAS = [
    ("2026-06-26", "35B/14B (vor 30B)"),
    ("2026-07-14", "qwen3-30b"),
    ("2099-01-01", "gemma4-26b"),
]


def era_of(created_at) -> str:
    d = str(created_at)[:10]
    for cutoff, name in ERAS:
        if d < cutoff:
            return name
    return ERAS[-1][1]


def ensure_columns() -> None:
    with get_connection() as c:
        c.execute("ALTER TABLE trends ADD COLUMN IF NOT EXISTS grounding_flags JSONB")
        c.execute("ALTER TABLE trends ADD COLUMN IF NOT EXISTS grounding_checked_at TIMESTAMP")


def iter_published(batch: int = 2000):
    """Stream published articles + their source text, keyed on id to avoid
    loading 58k raw_contents (some are full articles) into memory at once."""
    last = 0
    while True:
        with get_connection() as c:
            rows = c.execute(
                "SELECT t.id, t.title_en, t.body_en, t.confidence, t.created_at, "
                "       t.source_name, r.title AS raw_title, r.excerpt, r.raw_content "
                "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
                "WHERE t.status = 'published' AND t.body_en IS NOT NULL AND t.id > ? "
                "ORDER BY t.id LIMIT ?", (last, batch)).fetchall()
        if not rows:
            return
        for r in rows:
            yield dict(r)
        last = dict(rows[-1])["id"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark", action="store_true", help="write flags to the DB")
    ap.add_argument("--samples", type=int, default=0, help="show N worst offenders")
    ap.add_argument("--limit", type=int, default=0, help="stop after N (for a quick probe)")
    args = ap.parse_args()

    if args.mark:
        ensure_columns()

    t0 = time.time()
    n = flagged = 0
    per_era: dict[str, list[int]] = defaultdict(list)
    per_source: dict[str, list[int]] = defaultdict(list)
    tok_hist: Counter = Counter()
    worst: list[tuple] = []
    pending: list[tuple] = []

    for e in iter_published():
        src = f"{e['raw_title'] or ''} {e['raw_content'] or e['excerpt'] or ''}"
        ung = ungrounded_specifics(e["body_en"] or "", src)
        n += 1
        bad = 1 if ung else 0
        flagged += bad
        per_era[era_of(e["created_at"])].append(bad)
        per_source[e["source_name"] or "?"].append(bad)
        tok_hist[min(len(ung), 5)] += 1
        if ung:
            worst.append((len(ung), e, ung))
            worst.sort(key=lambda x: -x[0])
            del worst[max(args.samples, 20):]
        if args.mark:
            pending.append((json.dumps(ung) if ung else json.dumps([]), e["id"]))
            if len(pending) >= 500:
                with get_connection() as c:
                    for p in pending:
                        c.execute("UPDATE trends SET grounding_flags = ?, "
                                  "grounding_checked_at = NOW() WHERE id = ?", p)
                pending.clear()
        if n % 5000 == 0:
            print(f"  … {n:,} geprüft · {flagged/n*100:.1f}% auffällig · {time.time()-t0:.0f}s")
        if args.limit and n >= args.limit:
            break

    if args.mark and pending:
        with get_connection() as c:
            for p in pending:
                c.execute("UPDATE trends SET grounding_flags = ?, "
                          "grounding_checked_at = NOW() WHERE id = ?", p)

    dur = time.time() - t0
    print(f"\n{'='*66}\nGEPRÜFT: {n:,} published Artikel in {dur:.0f}s "
          f"({n/max(dur,1):.0f}/s){'  [MARKIERT]' if args.mark else '  [nur Analyse]'}")
    print(f"AUFFÄLLIG: {flagged:,} ({flagged/max(n,1)*100:.1f}%)\n")

    print(f"{'MODELL-ÄRA':<24}{'N':>9}{'AUFFÄLLIG':>11}{'RATE':>8}")
    print("-" * 52)
    for _, name in ERAS:
        v = per_era.get(name) or []
        if v:
            print(f"{name:<24}{len(v):>9,}{sum(v):>11,}{sum(v)/len(v)*100:>7.1f}%")

    print(f"\n{'ERFUNDENE TOKENS/ARTIKEL':<24}{'N':>9}{'ANTEIL':>9}")
    print("-" * 42)
    for k in sorted(tok_hist):
        lbl = "0 (sauber)" if k == 0 else (f"{k}" if k < 5 else "5+")
        print(f"{lbl:<24}{tok_hist[k]:>9,}{tok_hist[k]/max(n,1)*100:>8.1f}%")

    big = [(s, v) for s, v in per_source.items() if len(v) >= 100]
    big.sort(key=lambda x: -sum(x[1]) / len(x[1]))
    print(f"\nSCHLECHTESTE QUELLEN (>=100 Artikel)\n{'QUELLE':<34}{'N':>7}{'RATE':>8}")
    print("-" * 50)
    for s, v in big[:12]:
        print(f"{s[:33]:<34}{len(v):>7,}{sum(v)/len(v)*100:>7.1f}%")

    if args.samples:
        import textwrap
        print(f"\n{'='*66}\nSCHLIMMSTE FÄLLE")
        for cnt, e, ung in worst[:args.samples]:
            print(f"\n--- #{e['id']} · {e['source_name']} · conf {e['confidence']:.2f} "
                  f"· {str(e['created_at'])[:10]} · {cnt} erfunden: {', '.join(ung)}")
            print(f"QUELL-TITEL: {(e['raw_title'] or '')[:68]}")
            print(textwrap.fill((e["body_en"] or "")[:520], 74,
                                initial_indent="  ", subsequent_indent="  "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
