#!/usr/bin/env python3
"""Corpus re-check for garbled bodies and ungrounded person names (#11, owner
release 2026-09-05).

Runs the two new deterministic checks over every article of one status
(default: published) — no LLM, no GPU, CPU only, streamed in id batches:

  --garbage   pipeline.content_guard.garbage_reasons(body, source): token soup,
              leaked foreign-script characters, repetition, stubs (< 60 words)
  --names     pipeline.grounding.ungrounded_names(body, source): a person named
              with a first name / title the source does not give ("Henkel-Chef
              Knobel" → "Henkel CEO Markus Knobel")

Hits leave the public feed: --apply sets status='review' and stamps
review_reason='recheck_<tag>:<kind>:<detail>' (kind = garbled | name). The
review UI lists them under "Re-check" (/trends/review?scope=recheck), where the
owner publishes, rejects or regenerates each one.

reviewed_at is deliberately NOT set: in frontend/src/lib/review.ts and
docs/owner_manual.md that stamp means "a human decided" (it also drives the
regeneration attempt counter and the dedup exemption). review_reason is the
marker of this sweep; publishing from the queue clears it.

A HUMAN PUBLISH IS FINAL (owner rule, 2026-09-22). Rows a person decided on
(reviewed_at IS NOT NULL) are skipped: when the owner reads the article next to
its source and presses Publish, that settles it — even where a checker still
objects. The objection may simply be wrong: the name gate flagged "Per Second"
out of "Tokens Per Second (TPS)", the owner saw the context and published. A
sweep that hauls such an article back would overrule the one judgement in this
system that outranks every automatic one. --include-reviewed re-opens them for
a deliberate audit (it never publishes anything, it only lists/parks rows).

    python scripts/recheck_published_grounding.py --names --garbage --dry-run
    python scripts/recheck_published_grounding.py --names --garbage --apply
    python scripts/recheck_published_grounding.py --garbage --status draft --apply
    python scripts/recheck_published_grounding.py --garbage --names --status review --apply
        (stamps reasons on rows the owner already moved to 'review' by hand)
    --since 2026-08-01   only rows created on/after that date
    --report PATH        Markdown summary (default docs/compliance/
                         grounding_recheck_<tag>.md, appended per run)

Caveat for the interpretation: the source used here is what the database holds
NOW — title + excerpt/raw_content + extraction. Full texts purged for
compliance (scripts/purge_raw_content.py) are gone, so a name the model read in
the original article can look ungrounded today. That is a hold for review,
never a verdict.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db as db_mod
from pipeline.content_guard import garbage_reasons
from pipeline.db import get_connection
from pipeline.grounding import source_from_parts, ungrounded_names

REPO = Path(__file__).parent.parent


def source_of(r: dict) -> str:
    ext: dict = {}
    if r.get("extraction_json"):
        try:
            ext = json.loads(r["extraction_json"]) or {}
        except (json.JSONDecodeError, TypeError):
            ext = {}
    lst = lambda k: [str(x) for x in ext.get(k) or []] if isinstance(ext.get(k), list) else []
    return source_from_parts(r.get("re_title"), r.get("raw_content") or r.get("excerpt"),
                             lst("key_claims"), lst("key_figures"), lst("dates"),
                             lst("quotes"), lst("geography"))


def row_filter(include_reviewed: bool) -> str:
    """The SQL that keeps a human decision out of this sweep (owner 2026-09-22).

    `reviewed_at` is stamped by every hand decision in the review desk —
    publish, reject, or a one-click fix. Rows carrying it are settled."""
    return "" if include_reviewed else "AND t.reviewed_at IS NULL "


def iter_rows(status: str, since: str | None, batch: int, include_reviewed: bool = False):
    last = 0
    while True:
        with get_connection() as c:
            sql = ("SELECT t.id, t.source_name, t.created_at, t.body_en, "
                   "       re.title AS re_title, re.excerpt, re.raw_content, re.extraction_json "
                   "  FROM trends t LEFT JOIN raw_entries re ON re.id = t.raw_entry_id "
                   " WHERE t.status = ? AND t.id > ? " + row_filter(include_reviewed))
            params: list = [status, last]
            if since:
                sql += "AND t.created_at >= ? "
                params.append(since)
            sql += "ORDER BY t.id LIMIT ?"
            params.append(batch)
            rows = [dict(r) for r in c.execute(sql, params).fetchall()]
        if not rows:
            return
        yield from rows
        last = rows[-1]["id"]


def check_row(r: dict, do_garbage: bool, do_names: bool) -> tuple[list[str], list[str]]:
    body = r.get("body_en") or ""
    src = source_of(r)
    garbage = garbage_reasons(body, src) if do_garbage else []
    names = ungrounded_names(body, src) if do_names else []
    return garbage, names


def reason_string(tag: str, garbage: list[str], names: list[str]) -> str:
    parts = []
    if garbage:
        parts.append("garbled:" + ",".join(garbage[:3]))
    if names:
        parts.append("name:" + ",".join(names[:3]))
    return (f"recheck_{tag}:" + ";".join(parts))[:300]


def apply_hits(hits: list[dict], status: str, tag: str) -> int:
    """status → 'review' (no-op when already 'review'), review_reason stamped."""
    db_mod._migrate_review_reason()
    n = 0
    for i in range(0, len(hits), 500):
        chunk = hits[i:i + 500]
        with get_connection() as c:
            for h in chunk:
                # Zweiter Riegel: auch ein Treffer aus einem aelteren Lauf wird
                # nicht zurueckgeholt, wenn inzwischen ein Mensch entschieden hat.
                c.execute("UPDATE trends SET status = 'review', review_reason = ? "
                          " WHERE id = ? AND status = ? AND reviewed_at IS NULL",
                          (reason_string(tag, h["garbage"], h["names"]), h["id"], status))
                n += 1
    return n


def write_report(path: Path, args, scanned: int, hits: list[dict], seconds: float,
                 applied: int | None) -> None:
    by_kind = Counter()
    by_month: dict[str, Counter] = defaultdict(Counter)
    by_source: dict[str, Counter] = defaultdict(Counter)
    garbage_kinds = Counter()
    short_only = 0
    for h in hits:
        kinds = []
        if h["garbage"]:
            kinds.append("garbled")
            for g in h["garbage"]:
                garbage_kinds[g.split(":")[0]] += 1
            if all(g.startswith("too_short") for g in h["garbage"]):
                short_only += 1
        if h["names"]:
            kinds.append("name")
        month = str(h["created_at"])[:7]
        for k in kinds:
            by_kind[k] += 1
            by_month[month][k] += 1
            by_source[h["source_name"] or "?"][k] += 1
    lines = [
        f"\n## Lauf {date.today().isoformat()} — status={args.status}, "
        + ("inkl. von Hand entschiedener Zeilen, " if args.include_reviewed
           else "ohne von Hand entschiedene Zeilen, ")
        + f"{'APPLY' if args.apply else 'DRY-RUN'}"
        + (f", since {args.since}" if args.since else ""),
        "",
        f"- Checks: {'garbage ' if args.garbage else ''}{'names' if args.names else ''}",
        f"- Gescannt: {scanned:,} Artikel in {seconds:.0f} s",
        f"- Treffer: {len(hits):,} Artikel ({len(hits) / max(scanned, 1):.2%}) — "
        f"garbled {by_kind['garbled']:,}, name {by_kind['name']:,}"
        + (f"; davon nur too_short: {short_only:,}" if args.garbage else ""),
    ]
    if applied is not None:
        lines.append(f"- Angewendet: {applied:,} Zeilen → status='review', review_reason='recheck_{args.tag}:…'")
    if args.garbage and garbage_kinds:
        lines += ["", "### Garbage-Gründe", "", "| Grund | Artikel |", "|---|---|"]
        lines += [f"| {k} | {v:,} |" for k, v in garbage_kinds.most_common()]
    lines += ["", "### Je Monat", "", "| Monat | garbled | name |", "|---|---|---|"]
    lines += [f"| {m} | {c['garbled']:,} | {c['name']:,} |" for m, c in sorted(by_month.items())]
    lines += ["", "### Je Quelle (Top 40)", "", "| Quelle | garbled | name |", "|---|---|---|"]
    top = sorted(by_source.items(), key=lambda kv: -(kv[1]["garbled"] + kv[1]["name"]))[:40]
    lines += [f"| {s} | {c['garbled']:,} | {c['name']:,} |" for s, c in top]
    if args.names:
        names = Counter(n for h in hits for n in h["names"])
        lines += ["", "### Häufigste beanstandete Namen", ""]
        lines += [f"- {n} ({c})" for n, c in names.most_common(25)]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# Grounding-Bestandsprüfung {args.tag} (#11)\n\n"
                        "Erzeugt von `scripts/recheck_published_grounding.py`. "
                        "Kontext und Bewertung: siehe Abschnitt am Ende / Issue #11.\n")
    with path.open("a") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--garbage", action="store_true")
    ap.add_argument("--names", action="store_true")
    ap.add_argument("--include-reviewed", action="store_true",
                    help="auch Zeilen pruefen, die ein Mensch schon entschieden hat "
                         "(Default: nein — ein Publish von Hand ist endgueltig)")
    ap.add_argument("--status", default="published",
                    help="which rows to scan (published | draft | review)")
    ap.add_argument("--since", help="YYYY-MM-DD, only rows created on/after")
    ap.add_argument("--batch", type=int, default=2000)
    ap.add_argument("--tag", default=date.today().isoformat())
    ap.add_argument("--report", type=Path)
    ap.add_argument("--dump", type=Path, help="write all hits as JSON (ids, reasons)")
    ap.add_argument("--samples", type=int, default=0, help="print N hits per kind")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not (args.garbage or args.names):
        ap.error("choose --garbage and/or --names")
    report = args.report or REPO / "docs" / "compliance" / f"grounding_recheck_{args.tag}.md"

    t0 = time.time()
    scanned = 0
    hits: list[dict] = []
    for r in iter_rows(args.status, args.since, args.batch, args.include_reviewed):
        scanned += 1
        garbage, names = check_row(r, args.garbage, args.names)
        if garbage or names:
            hits.append({"id": r["id"], "source_name": r["source_name"],
                         "created_at": str(r["created_at"]), "garbage": garbage, "names": names})
        if scanned % 10000 == 0:
            print(f"  … {scanned:,} scanned, {len(hits):,} hits", file=sys.stderr)
    seconds = time.time() - t0
    print(f"{args.status}: scanned {scanned:,}, hits {len(hits):,} "
          f"(garbled {sum(1 for h in hits if h['garbage']):,}, "
          f"name {sum(1 for h in hits if h['names']):,}) in {seconds:.0f} s")
    if args.samples:
        for kind in ("garbage", "names"):
            for h in [h for h in hits if h[kind]][:args.samples]:
                print(f"  {kind:7} #{h['id']} {h['source_name']}: {h[kind][:3]}")
    if args.dump:
        args.dump.write_text(json.dumps(hits, ensure_ascii=False, indent=0))

    applied = None
    if args.apply and hits:
        applied = apply_hits(hits, args.status, args.tag)
        print(f"applied: {applied:,} rows → status='review'")
    write_report(report, args, scanned, hits, seconds, applied)
    print(f"report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
