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
  5. OPENALEX DENSITY  — raw_entries intake from the OpenAlex* topic-shard
     sources, last full month vs. the month before; alert on zero or a >50%
     drop. Also reports research_corpus size + how long ago the monthly
     snapshot-sync (openalex_snap_state, cron on the 5th) last ran, alerting
     if that sync itself looks overdue (issue #81).
  6. PATSTAT/TIP EDITIONS — the EPO ships two PATSTAT editions/year (Spring
     ~April, Autumn ~October); a TIP refresh is an owner-only action (runbook:
     issue #76). No DB access — a pure reminder keyed on the current month.
  7. BRAND-PR BALANCE  — share of raw_entries (last 30d) coming from
     source_type='brand' (company newsrooms); alert if company PR dominates
     the feed (issue #81).
  8. TDM/ROBOTS COMPLIANCE — re-probes every active source with
     scripts/probe_source_compliance.py (feed, robots.txt for our UA, bot
     status, TDM reservation, licence hints; 1 req/s/host, ~5-10 min) and
     writes the protocol fields tdm_checked/tdm_status/license back into
     sources.yaml (line-based, order + comments preserved). Alerts on every
     transition into/out of reserved|blocked; `fulltext: true` is switched
     off automatically when the article-level verdict is reserved/blocked
     (issue #97). --no-tdm skips it.

Report: data/source_check_<YYYY-MM>.md. Alerts additionally appended to
data/ALERTS.md and (with --post-issue) posted as a comment on issue #13 so the
issue becomes the living quality log.

    python scripts/monthly_source_check.py                # report only
    python scripts/monthly_source_check.py --post-issue   # + comment on #13
    python scripts/monthly_source_check.py --skip-network # sections 1+2 only
    python scripts/monthly_source_check.py --no-tdm       # without the ~10-min TDM re-probe
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

import yaml

from pipeline.db import get_connection
from probe_source_compliance import (SOURCES_YAML, fulltext_reason, iter_active_sources, probe_sources,
                                     summarize, write_protocol_fields)
from source_signal_yield import collect as collect_yield
from source_quality_report import iter_configured_feeds, measure_feed

DATA = REPO / "data"
NOISE_PASS = 0.35       # issue #13 threshold: durably below this = act
MIN_VOLUME = 20         # processed entries needed before pass-rate is judged
BALANCE_FACTOR = 3.0    # CLAUDE.md: >3x deviation from median share = alert
WP_FACTOR = 3.0         # WP posts / our intake above this = silent feed defect
WP_MIN_POSTS = 10       # ignore hosts that barely publish
VERTICALS = ["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]
UA = {"User-Agent": "CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology; source-check)"}

OA_DROP_FACTOR = 0.5    # issue #81: last full month < 50% of prior month = alert
OA_MIN_PRIOR = 50       # ignore tiny/early-history prior-month counts (noise floor)
OA_SYNC_STALE_DAYS = 40 # monthly snapshot-sync (cron 5th) overdue past this many days
BRAND_SHARE_ALERT = 0.15  # issue #81: brand-source (company PR) share of raw_entries above this = alert
# issue #81: EPO PATSTAT editions ship ~April (Spring) and ~October (Autumn);
# the reminder window covers the release month plus the month after (rollout lag).
PATSTAT_REMINDER_MONTHS = {4: "Spring", 5: "Spring", 10: "Autumn", 11: "Autumn"}


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


# ------------------------------------------------------- 5. OpenAlex density

def _month_bounds(now: datetime) -> tuple[str, str, str]:
    """(prior_month_start, last_full_month_start, this_month_start) as ISO dates.

    E.g. run in August -> (2026-06-01, 2026-07-01, 2026-08-01): "last full
    month" is always the most recently *completed* calendar month, never the
    in-progress current one.
    """
    this_month_start = now.replace(day=1)
    last_full_start = (this_month_start - timedelta(days=1)).replace(day=1)
    prior_start = (last_full_start - timedelta(days=1)).replace(day=1)
    return (prior_start.strftime("%Y-%m-%d"), last_full_start.strftime("%Y-%m-%d"),
            this_month_start.strftime("%Y-%m-%d"))


def _evaluate_openalex_intake(prior_count: int, last_count: int,
                              prior_label: str, last_label: str) -> tuple[list[str], list[str]]:
    """Pure evaluator (no DB) so the drop/zero logic is unit-testable directly."""
    lines = [f"raw_entries intake (OpenAlex* sources): {prior_label}={prior_count}  {last_label}={last_count}"]
    alerts = []
    if last_count == 0:
        lines.append("  << ZERO intake in the last full month")
        alerts.append(f"openalex-density: 0 raw_entries in {last_label} "
                      f"(prior {prior_label}: {prior_count}) — check the OpenAlex topic-shard ingest")
    elif prior_count >= OA_MIN_PRIOR and last_count < OA_DROP_FACTOR * prior_count:
        ratio = last_count / prior_count
        lines.append(f"  << DROP to {ratio:.0%} of prior month (< {OA_DROP_FACTOR:.0%} threshold)")
        alerts.append(f"openalex-density: {last_label} intake ({last_count}) is only {ratio:.0%} of "
                      f"{prior_label} ({prior_count}) — check OpenAlex ingest cadence")
    return lines, alerts


def _evaluate_corpus_sync(days_since_last_sync: float | None,
                          corpus_total: int | None) -> tuple[list[str], list[str]]:
    """Pure evaluator (no DB) for the research_corpus snapshot-sync staleness check."""
    lines = []
    alerts = []
    if corpus_total is not None:
        lines.append(f"research_corpus total: {corpus_total:,}")
    if days_since_last_sync is None:
        lines.append("research_corpus: no snapshot-sync recorded (openalex_snap_state empty/missing)")
        alerts.append("openalex-density: research_corpus has no recorded snapshot-sync "
                      "(openalex_snap_state empty or missing)")
    else:
        lines.append(f"research_corpus: last snapshot-sync {days_since_last_sync:.0f}d ago")
        if days_since_last_sync > OA_SYNC_STALE_DAYS:
            lines.append(f"  << monthly sync overdue (> {OA_SYNC_STALE_DAYS:.0f}d; cron runs the 5th of each month)")
            alerts.append(f"openalex-density: research_corpus snapshot-sync is "
                          f"{days_since_last_sync:.0f}d overdue (> {OA_SYNC_STALE_DAYS:.0f}d)")
    return lines, alerts


def check_openalex_density(now: datetime) -> tuple[list[str], list[str]]:
    """OpenAlex inflow watch (#81): two channels, both fed by real DB tables.

    (a) raw_entries from sources named 'OpenAlex*' (the per-topic shards that
    feed the regular signal pipeline, see CONCEPT_SHARDS in
    scripts/ingest_openalex.py) — last full calendar month vs. the one before.
    (b) research_corpus (the 45M-row snapshot backfill, #80) via
    openalex_snap_state.done_at — is the monthly sync (cron, 5th) still
    running. That table/research_corpus_meta are Postgres-only additions (not
    in pipeline/db.py's schema), so on a DB without them this degrades to an
    informational "not available" line instead of crashing the whole report.
    """
    prior_start, last_start, this_start = _month_bounds(now)
    prior_label, last_label = prior_start[:7], last_start[:7]
    with get_connection() as c:
        prior_count = c.execute(
            "SELECT COUNT(*) AS n FROM raw_entries r JOIN sources s ON s.id = r.source_id "
            "WHERE s.name LIKE ? AND r.fetched_at >= ? AND r.fetched_at < ?",
            ("OpenAlex%", prior_start, last_start)).fetchone()["n"]
        last_count = c.execute(
            "SELECT COUNT(*) AS n FROM raw_entries r JOIN sources s ON s.id = r.source_id "
            "WHERE s.name LIKE ? AND r.fetched_at >= ? AND r.fetched_at < ?",
            ("OpenAlex%", last_start, this_start)).fetchone()["n"]

        days_since, corpus_total = None, None
        try:
            sync_row = c.execute("SELECT MAX(done_at) AS last_sync FROM openalex_snap_state").fetchone()
            last_sync = sync_row["last_sync"] if sync_row else None
            if last_sync is not None:
                last_sync_dt = datetime.fromisoformat(str(last_sync)) if not isinstance(last_sync, datetime) else last_sync
                if last_sync_dt.tzinfo is None:
                    last_sync_dt = last_sync_dt.replace(tzinfo=timezone.utc)
                days_since = (now - last_sync_dt).total_seconds() / 86400
            meta_row = c.execute("SELECT total FROM research_corpus_meta LIMIT 1").fetchone()
            corpus_total = meta_row["total"] if meta_row else None
        except Exception:
            pass  # openalex_snap_state/research_corpus_meta are Postgres-only extras (#80), not core schema

    lines_a, alerts_a = _evaluate_openalex_intake(prior_count, last_count, prior_label, last_label)
    if days_since is None and corpus_total is None:
        lines_b, alerts_b = ["research_corpus: table not available on this DB (Postgres-only, #80)"], []
    else:
        lines_b, alerts_b = _evaluate_corpus_sync(days_since, corpus_total)
    return lines_a + lines_b, alerts_a + alerts_b


# ---------------------------------------------------- 6. PATSTAT/TIP reminder

def check_patstat_reminder(now: datetime) -> tuple[list[str], list[str]]:
    """Pure function of the current date — no DB, no network (#81).

    The EPO publishes two PATSTAT editions/year (Spring ~April, Autumn
    ~October); the TIP refresh itself is an owner-only action (runbook:
    issue #76), so this is a reminder line, not an automated action.
    """
    edition = PATSTAT_REMINDER_MONTHS.get(now.month)
    if edition is None:
        return [f"No PATSTAT edition window this month ({now.strftime('%B')}); "
                f"next windows: April/May (Spring) and October/November (Autumn)."], []
    line = f"PATSTAT {edition} {now.year} dürfte verfügbar sein — TIP-Refresh fällig (Runbook: Issue #76)"
    return [line], [line]


# ------------------------------------------------------- 7. Brand-PR balance

def _evaluate_brand_balance(brand_count: int, total_count: int) -> tuple[list[str], list[str]]:
    """Pure evaluator (no DB) — issue #81: company-PR (source_type='brand')
    must not dominate the feed. Always reports the measured share; only
    alerts above BRAND_SHARE_ALERT."""
    share = brand_count / total_count if total_count else 0.0
    lines = [f"brand-source raw_entries last 30d: {brand_count}/{total_count} ({share:.1%})"]
    alerts = []
    if total_count and share > BRAND_SHARE_ALERT:
        lines.append(f"  << OVER (> {BRAND_SHARE_ALERT:.0%})")
        alerts.append(f"brand-balance: company-PR (source_type=brand) is {share:.0%} of raw_entries "
                      f"last 30d (> {BRAND_SHARE_ALERT:.0%} threshold)")
    return lines, alerts


def check_brand_balance(since: str) -> tuple[list[str], list[str]]:
    with get_connection() as c:
        brand_n = c.execute(
            "SELECT COUNT(*) AS n FROM raw_entries r JOIN sources s ON s.id = r.source_id "
            "WHERE s.source_type = 'brand' AND r.fetched_at >= ?", (since,)).fetchone()["n"]
        total_n = c.execute(
            "SELECT COUNT(*) AS n FROM raw_entries WHERE fetched_at >= ?", (since,)).fetchone()["n"]
    return _evaluate_brand_balance(brand_n, total_n)


# ----------------------------------------------------- 8. TDM/robots (#97)

TDM_ALERT_STATUSES = ("reserved", "blocked")


def _fulltext_must_go(r: dict) -> bool:
    """Same predicate as probe_source_compliance.write_protocol_fields."""
    return bool(r.get("fulltext")) and r.get("tdm_status") in TDM_ALERT_STATUSES and r.get("fulltext_ok") is False


def _evaluate_tdm_changes(results: list[dict]) -> tuple[list[str], list[str]]:
    """Pure: report lines + alerts from probe results that carry prev_status
    (the tdm_status stored in sources.yaml before this run)."""
    counts = summarize(results)
    lines = [f"{len(results)} active sources probed — "
             + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))]
    alerts: list[str] = []
    for r in results:
        prev, cur, name = r.get("prev_status"), r.get("tdm_status"), r.get("name") or r.get("feed_url")
        reason = r.get("reason") or ""
        if cur in TDM_ALERT_STATUSES and prev != cur:
            was = f"was {prev}" if prev else "first check"
            alerts.append(f"tdm: {name} now {cur} ({reason}; {was})")
        elif prev in TDM_ALERT_STATUSES and cur == "ok":
            alerts.append(f"tdm: {name} back to ok (was {prev}) — fulltext may be re-enabled by hand")
        if _fulltext_must_go(r):
            alerts.append(f"tdm: {name} fulltext switched off ({fulltext_reason(r)})")
        if cur != "ok":
            lines.append(f"  {cur:<10} {name}: {reason}")
    return lines, alerts


def check_tdm_status(today: str | None = None, yaml_path: Path | str = SOURCES_YAML,
                     write: bool = True, probe=None) -> tuple[list[str], list[str]]:
    """Section 8: re-probe every active source, stamp the protocol fields into
    sources.yaml, alert on reserved/blocked transitions. `probe` is injectable
    for tests (default: the real network probe, 1 req/s/host)."""
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cfg = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
    entries = iter_active_sources(cfg)
    results = (probe or probe_sources)(entries)
    lines, alerts = _evaluate_tdm_changes(results)
    if write:
        s = write_protocol_fields(yaml_path, results, today)
        lines.append(f"sources.yaml: {s['updated']} entries stamped tdm_checked={today}"
                     + (f", fulltext off: {', '.join(s['fulltext_off'])}" if s["fulltext_off"] else "")
                     + (f", not found: {len(s['missing'])}" if s["missing"] else ""))
    return lines, alerts


# ------------------------------------------------------------------ report

def main() -> int:
    ap = argparse.ArgumentParser(description="Monthly source-quality check (#13)")
    ap.add_argument("--since", help="override the 30d window start (ISO date)")
    ap.add_argument("--skip-network", action="store_true",
                    help="only DB-based checks (1, 2, 5, 6, 7), skip feed/WP probes")
    ap.add_argument("--post-issue", action="store_true",
                    help="post the report as a comment on issue #13 via gh")
    ap.add_argument("--no-tdm", action="store_true",
                    help="skip section 8 (TDM/robots re-probe of all active sources, ~10 min)")
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
    for title, fn in [("5. OpenAlex density watch", lambda: check_openalex_density(now)),
                      ("6. PATSTAT/TIP editions reminder", lambda: check_patstat_reminder(now)),
                      ("7. Brand-PR balance (30d)", lambda: check_brand_balance(since))]:
        lines, alerts = fn()
        sections.append((title, lines, alerts))
    if not args.skip_network and not args.no_tdm:
        lines, alerts = check_tdm_status(now.strftime("%Y-%m-%d"))
        sections.append(("8. TDM/robots compliance (all active sources, #97)", lines, alerts))

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
    try:
        from pipeline.ops_events import record  # Laufprotokoll fuer /trends/ops (#104)
    except ImportError:  # Paket nicht im Pfad (Cron ohne cd, 12.09.: Backup fiel aus) — Protokoll ist optional, der Job nicht
        from contextlib import nullcontext as record
    with record("monthly_source_check"):
        raise SystemExit(main())
