#!/usr/bin/env python3
"""Monthly source-quality check (issue #13, Epic W0.3).

One run, four checks, one Markdown report:

  1. PASS-RATE WATCH   — last 30 days of raw_entries per source (reuses
     source_signal_yield.collect); alert when pass < NOISE_PASS at volume.
  2. VERTICAL BALANCE  — published shares over the last 30 days; alert when a
     vertical deviates >3x from the median share (CLAUDE.md principle). Appends
     one row per run to data/vertical_balance_history.csv (drift over time).
  3. FEED HEALTH       — live probe of every configured feed (reuses
     source_quality_report.measure_feed); alert on error/stale.
  4. RSS << WP YIELD   — for WordPress-capable sources, compares this month's
     WP post count (X-WP-Total) against our raw_entries intake; a factor >3
     means the RSS feed is silently under-delivering (issue #29 fold-in).

Report: data/source_check_<YYYY-MM>.md. Alerts additionally appended to
data/ALERTS.md and (with --post-issue) posted as a comment on issue #13 so the
issue becomes the living quality log.

    python scripts/monthly_source_check.py                # report only
    python scripts/monthly_source_check.py --post-issue   # + comment on #13
    python scripts/monthly_source_check.py --skip-network # sections 1+2 only
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import httpx

from pipeline.db import get_connection
from source_signal_yield import collect as collect_yield
from source_quality_report import iter_configured_feeds, measure_feed

DATA = REPO / "data"
NOISE_PASS = 0.35       # issue #13 threshold: durably below this = act
MIN_VOLUME = 20         # processed entries needed before pass-rate is judged
BALANCE_FACTOR = 3.0    # CLAUDE.md: >3x deviation from median share = alert
WP_FACTOR = 3.0         # WP posts / our intake above this = silent feed defect
WP_MIN_POSTS = 10       # ignore hosts that barely publish
VERTICALS = ["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]
UA = {"User-Agent": "CatandaryTrends source-check (trends@catandary.de)"}


# ------------------------------------------------------------- 1. pass-rate

def check_pass_rate(since: str) -> tuple[list[str], list[str]]:
    rows = collect_yield(0, since)
    rows = [d for d in rows if d["processed"] >= MIN_VOLUME]
    rows.sort(key=lambda d: d["pass_rate"])
    lines = [f"{len(rows)} sources with >={MIN_VOLUME} processed since {since}", ""]
    lines.append(f"{'Source':<30}{'Vert':<10}{'proc':>6}{'sig':>6}{'pass':>8}  top-filter")
    for d in rows:
        lines.append(f"{d['source'][:29]:<30}{d['vertical']:<10}{d['processed']:>6}"
                     f"{d['signals']:>6}{d['pass_rate']*100:>7.1f}%  {d['top_reason']}")
    alerts = [f"pass-rate: {d['source']} at {d['pass_rate']:.0%} "
              f"({d['signals']}/{d['processed']}, top filter: {d['top_reason']})"
              for d in rows if d["pass_rate"] < NOISE_PASS]
    return lines, alerts


# ------------------------------------------------------- 2. vertical balance

def check_balance(since: str) -> tuple[list[str], list[str]]:
    with get_connection() as c:
        rows = c.execute(
            "SELECT primary_vertical, COUNT(*) AS n FROM trends "
            "WHERE status = 'published' AND published_at >= ? "
            "GROUP BY primary_vertical", (since,)).fetchall()
    counts = {v: 0 for v in VERTICALS}
    for r in rows:
        if r["primary_vertical"] in counts:
            counts[r["primary_vertical"]] += r["n"]
    total = sum(counts.values()) or 1
    shares = {v: n / total for v, n in counts.items()}
    med = sorted(shares.values())[len(shares) // 2] or 1e-9

    lines = [f"Published last 30d: {total}", ""]
    alerts = []
    for v in VERTICALS:
        flag = ""
        if shares[v] > BALANCE_FACTOR * med:
            flag = "  << OVER (>3x median)"
            alerts.append(f"balance: {v} at {shares[v]:.0%} (> {BALANCE_FACTOR:.0f}x median {med:.0%})")
        lines.append(f"{v:<10}{counts[v]:>6}  {shares[v]*100:>5.1f}%{flag}")

    hist = DATA / "vertical_balance_history.csv"
    if not hist.exists():
        hist.write_text("date,total," + ",".join(VERTICALS) + "\n")
    with hist.open("a") as f:
        f.write(datetime.now(timezone.utc).strftime("%Y-%m-%d") + f",{total},"
                + ",".join(f"{shares[v]:.4f}" for v in VERTICALS) + "\n")
    return lines, alerts


# ----------------------------------------------------------- 3. feed health

def check_feeds() -> tuple[list[str], list[str]]:
    feeds = iter_configured_feeds()
    with ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(measure_feed, feeds))
    bad = [r for r in results if not r["ok"]]
    stale = [r for r in results if r["ok"] and r.get("stale")]
    lines = [f"{len(results)} feeds probed: {len(results)-len(bad)-len(stale)} ok, "
             f"{len(stale)} stale, {len(bad)} failing", ""]
    alerts = []
    for r in bad:
        lines.append(f"FAIL  {r['name'][:34]:<35} {r['error']}")
        alerts.append(f"feed: {r['name']} failing ({r['error']})")
    for r in stale:
        lines.append(f"STALE {r['name'][:34]:<35} newest {r['newest_age_days']}d old")
        alerts.append(f"feed: {r['name']} stale (newest {r['newest_age_days']}d)")
    return lines, alerts


# --------------------------------------------------------- 4. RSS << WP yield

def _wp_month_total(root: str, month_start: str) -> int | None:
    """X-WP-Total of posts published since month_start, or None if not WP."""
    try:
        r = httpx.get(f"{root}/wp-json/wp/v2/posts",
                      params={"per_page": 1, "after": f"{month_start}T00:00:00"},
                      headers=UA, timeout=12, follow_redirects=True)
        if r.status_code == 200 and r.headers.get("X-WP-Total"):
            return int(r.headers["X-WP-Total"])
    except Exception:
        pass
    return None


def check_wp_yield(month_start: str) -> tuple[list[str], list[str]]:
    cache_path = DATA / "wp_capability_cache.json"
    cache: dict[str, bool] = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    with get_connection() as c:
        srcs = c.execute(
            "SELECT s.id, s.name, s.feed_url, COUNT(r.id) AS intake FROM sources s "
            "LEFT JOIN raw_entries r ON r.source_id = s.id AND r.fetched_at >= ? "
            "WHERE s.active = TRUE AND s.source_type = 'trade_media' "
            "GROUP BY s.id, s.name, s.feed_url", (month_start,)).fetchall()

    candidates = []
    for s in srcs:
        host = urlparse(s["feed_url"]).netloc
        if host and cache.get(host) is not False:
            candidates.append((s, host))

    def probe(item):
        s, host = item
        return s, host, _wp_month_total(f"https://{host}", month_start)

    lines, alerts, probed = [], [], 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for s, host, wp_total in ex.map(probe, candidates):
            cache[host] = wp_total is not None
            if wp_total is None or wp_total < WP_MIN_POSTS:
                continue
            probed += 1
            intake = s["intake"] or 0
            ratio = wp_total / max(intake, 1)
            mark = "  << SILENT FEED DEFECT" if ratio > WP_FACTOR else ""
            lines.append(f"{s['name'][:29]:<30} wp {wp_total:>5}  intake {intake:>5}  x{ratio:>5.1f}{mark}")
            if ratio > WP_FACTOR:
                alerts.append(f"rss<<wp: {s['name']} published {wp_total} this month, "
                              f"we ingested {intake} (x{ratio:.1f})")
    cache_path.write_text(json.dumps(cache, indent=0, sort_keys=True))
    lines.insert(0, f"{probed} WP-capable sources compared (month since {month_start})")
    return lines, alerts


# ------------------------------------------------------------------ report

def main() -> int:
    ap = argparse.ArgumentParser(description="Monthly source-quality check (#13)")
    ap.add_argument("--since", help="override the 30d window start (ISO date)")
    ap.add_argument("--skip-network", action="store_true",
                    help="only DB-based checks (1+2), skip feed/WP probes")
    ap.add_argument("--post-issue", action="store_true",
                    help="post the report as a comment on issue #13 via gh")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    since = args.since or (now - timedelta(days=30)).strftime("%Y-%m-%d")
    month_start = now.strftime("%Y-%m-01")

    sections: list[tuple[str, list[str], list[str]]] = []
    for title, fn in [("1. Pass-rate watch (30d)", lambda: check_pass_rate(since)),
                      ("2. Vertical balance (30d published)", lambda: check_balance(since))]:
        lines, alerts = fn()
        sections.append((title, lines, alerts))
    if not args.skip_network:
        for title, fn in [("3. Feed health", check_feeds),
                          ("4. RSS vs WP yield", lambda: check_wp_yield(month_start))]:
            lines, alerts = fn()
            sections.append((title, lines, alerts))

    all_alerts = [a for _, _, alerts in sections for a in alerts]
    stamp = now.strftime("%Y-%m")
    md = [f"# Source check {now.strftime('%Y-%m-%d')}", ""]
    md.append(f"**Alerts: {len(all_alerts)}**" if all_alerts else "**No alerts.**")
    for a in all_alerts:
        md.append(f"- ⚠️ {a}")
    for title, lines, _ in sections:
        md += ["", f"## {title}", "", "```", *lines, "```"]
    report = "\n".join(md) + "\n"

    DATA.mkdir(exist_ok=True)
    out = DATA / f"source_check_{stamp}.md"
    out.write_text(report)
    print(report)
    print(f"Report: {out}")

    if all_alerts:
        with (DATA / "ALERTS.md").open("a") as f:
            f.write(f"\n## {now.strftime('%Y-%m-%d')} source check\n")
            f.writelines(f"- {a}\n" for a in all_alerts)

    if args.post_issue:
        subprocess.run(["gh", "issue", "comment", "13", "--body-file", str(out)],
                       cwd=REPO, check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
