#!/usr/bin/env python3
"""Measure the architecture's three mega-trend axes for every CANONICAL key.

The two-layer architecture (docs/mega_discovery_architecture.md) defines a
mega-trend as broad (reach) AND deep (maturity chain) AND durable — but those
axes were only ever computed for discovery clusters, never for the canonical
keys themselves. This measures them on each key's FULL signal population
(no embeddings needed — the axes are metadata: verticals, dates, tiers), so the
"is this actually a mega-trend or a topic domain?" question gets numbers.

Metrics per key:
  reach          normalized vertical entropy (discovery.vertical_entropy);
                 0 = single industry, 1 = evenly across all 8
  maturity_span  how many lead-time tiers (science/patent/funding/market) are
                 populated, with per-tier onsets (discovery._onset) and
                 lead_months (earliest early tier -> market)
  presence       fraction of months since the key's onset with >=3 signals —
                 persistence independent of size (the cluster-level durability
                 formula compares against sample totals and would zero out
                 every small key at corpus scale)
  mega_score     0.40*reach + 0.35*span/4 + 0.25*presence — the characterize()
                 weights; reference threshold 0.45 = discover_trends'
                 --min-mega-score for calling a cluster NEW
Context columns: dominant vertical + its share, corpus share, market-tier share.

Read-only. Writes docs/mega_axes_<date>.md and prints the table.

    python scripts/measure_mega_axes.py
    python scripts/measure_mega_axes.py --status published
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db as db_mod
from pipeline.config import load_mega_trends
from pipeline.discovery import _onset, _months_between, tier_of, vertical_entropy, TIER_ORDER, EARLY_TIERS

BATCH = 20_000


def month_key(d) -> str | None:
    if not d:
        return None
    s = d.isoformat() if isinstance(d, (datetime, date)) else str(d)
    return s[:7] if len(s) >= 7 else None


def load_rows(status: str):
    """Stream metadata for every labeled trend: key, verticals, month, tier."""
    import psycopg2, json
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor(name="axes_scan")
    cur.itersize = BATCH
    sts = tuple(s.strip() for s in status.split(","))
    cur.execute(
        "SELECT t.mega_trend, t.verticals::text, r.published_date, r.pub_number, "
        "       s.source_type, t.source_name "
        "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
        "JOIN sources s ON r.source_id = s.id "
        "WHERE t.mega_trend IS NOT NULL AND t.status IN %s "
        "  AND (r.published_date IS NULL OR r.published_date <= NOW())", (sts,))
    by_key: dict[str, list[dict]] = {}
    n = 0
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            break
        for mega, verts, pub, pubno, stype, sname in rows:
            n += 1
            try:
                v = json.loads(verts) if verts else []
            except Exception:
                v = []
            by_key.setdefault(mega, []).append({
                "_verts": v,
                "published_date": pub.isoformat() if pub else None,
                "_tier": tier_of(stype, sname, pubno),
            })
    cur.close()
    conn.close()
    return by_key, n


def measure_key(members: list[dict]) -> dict:
    reach = vertical_entropy(members)
    # tier onsets + span + lead (same logic as discovery.maturity)
    onsets, totals = {}, {}
    for tier in TIER_ORDER:
        grp = [m for m in members if m["_tier"] == tier]
        o, t = _onset(grp)
        onsets[tier], totals[tier] = o, t
    span = sum(1 for t in TIER_ORDER if onsets[t])
    market = onsets["market"]
    early = sorted((onsets[t], t) for t in EARLY_TIERS if onsets[t])
    lead_months = lead_tier = None
    if early and market:
        first, lead_tier = early[0]
        lead_months = _months_between(first, market)
    # presence: months since onset with >=3 signals
    months = sorted(m for x in members if (m := month_key(x["published_date"])))
    cnt = Counter(months)
    onset_all, _ = _onset(members)
    presence = 0.0
    if onset_all and months:
        span_months = [m for m in _month_range(onset_all, months[-1])]
        active = sum(1 for m in span_months if cnt.get(m, 0) >= 3)
        presence = active / len(span_months) if span_months else 0.0
    dom = Counter(v for m in members for v in (m["_verts"] or [None]) if v)
    dom_v, dom_n = (dom.most_common(1)[0] if dom else ("—", 0))
    dom_share = dom_n / sum(dom.values()) if dom else 0.0
    market_share = totals["market"] / max(len(members), 1)
    score = 0.40 * reach + 0.35 * (span / 4.0) + 0.25 * presence
    return {"n": len(members), "reach": reach, "span": span, "onsets": onsets,
            "lead_tier": lead_tier, "lead_months": lead_months,
            "presence": presence, "mega_score": score,
            "dom_v": dom_v, "dom_share": dom_share, "market_share": market_share}


def _month_range(a: str, b: str):
    y, m = int(a[:4]), int(a[5:7])
    while f"{y:04d}-{m:02d}" <= b:
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12:
            y, m = y + 1, 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure the three mega axes per canonical key")
    ap.add_argument("--status", default="signal,published")
    ap.add_argument("--threshold", type=float, default=0.45,
                    help="reference line (= discover_trends --min-mega-score)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    t0 = time.time()
    names = {m["key"]: m.get("name_en", m["key"]) for m in load_mega_trends()}
    by_key, total = load_rows(args.status)
    print(f"{total:,} labeled signals over {len(by_key)} keys loaded in {time.time()-t0:.0f}s\n")

    results = {k: measure_key(v) for k, v in by_key.items()}
    order = sorted(results.items(), key=lambda kv: -kv[1]["mega_score"])

    hdr = (f"{'Key':<44} {'n':>8} {'reach':>6} {'tiers':>5} {'lead':>9} "
           f"{'pres':>5} {'SCORE':>6}  {'dominant':>12}")
    lines = [hdr, "-" * len(hdr)]
    for k, r in order:
        lead = (f"{r['lead_months']:+d}mo" if r["lead_months"] is not None else "—")
        mark = " ◀" if r["mega_score"] >= args.threshold else ""
        lines.append(
            f"{k:<44} {r['n']:>8,} {r['reach']:>6.2f} {r['span']:>5} {lead:>9} "
            f"{r['presence']:>5.2f} {r['mega_score']:>6.2f}  "
            f"{r['dom_v']:>7} {r['dom_share']:>4.0%}{mark}")
    qualified = [k for k, r in order if r["mega_score"] >= args.threshold]
    lines.append("")
    lines.append(f"◀ = mega_score >= {args.threshold} (Referenz: discover_trends "
                 f"--min-mega-score): {len(qualified)} von {len(order)} Keys")
    print("\n".join(lines))

    out = Path(args.out or f"docs/mega_axes_{date.today().isoformat()}.md")
    doc = ["# Drei-Achsen-Messung der kanonischen Mega-Trend-Keys",
           "",
           f"**Lauf:** {date.today().isoformat()} · `scripts/measure_mega_axes.py` "
           f"· Status {args.status} · {total:,} Signale · read-only",
           "",
           "Misst die Architektur-Definition eines Mega-Trends (broad AND deep AND",
           "durable, `docs/mega_discovery_architecture.md`) erstmals auf den kanonischen",
           "Keys selbst statt nur auf Discovery-Clustern. `reach` = normierte",
           "Vertical-Entropie · `tiers` = belegte Lead-Time-Tiers · `lead` = frühester",
           "Early-Tier-Onset → Markt-Onset · `pres` = Anteil Monate seit Onset mit ≥3",
           "Signalen · SCORE = 0,40·reach + 0,35·tiers/4 + 0,25·pres.",
           "", "```", *lines, "```", ""]
    out.write_text("\n".join(doc), encoding="utf-8")
    print(f"\n→ {out}  ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
