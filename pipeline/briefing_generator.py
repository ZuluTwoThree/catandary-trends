"""Weekly personalized trend briefing generator for Trend-Radar customers.

For every active customer: select the week's top published trends for
their verticals, run their watchlist keywords against FTS5, render a
branded HTML email, archive it in radar_briefings and (optionally) send
it via Resend. Without RESEND_API_KEY the HTML lands in the outbox
directory — useful for review, demos and local development.

Also handles the daily watchlist alerts (Team tier and up): a compact
email that fires only when a watchlist keyword has new hits that were
not alerted before. No hits, no email.

Usage:
    python -m pipeline.briefing_generator                  # all active customers, archive + outbox
    python -m pipeline.briefing_generator --send           # also send via Resend
    python -m pipeline.briefing_generator --customer 3     # single customer
    python -m pipeline.briefing_generator --since-days 14  # wider window
    python -m pipeline.briefing_generator --anchor-latest  # anchor week on newest trend (demo/stale DB)
    python -m pipeline.briefing_generator --alerts [--send]  # daily watchlist alerts (cron: Tue-Fri 07:00)
"""

import argparse
import html
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import request as urlrequest

from pipeline import radar_db
from pipeline.config import (
    BRIEFING_FROM,
    BRIEFING_OUTBOX,
    LOG_LEVEL,
    PORTAL_BASE_URL,
    RESEND_API_KEY,
)

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TOP_TRENDS_LIMIT = 10
WATCHLIST_LIMIT_PER_KEYWORD = 3

VERTICAL_LABELS = {
    "FOOD": "Food & Beverage", "TECH": "Technology & AI", "HEALTH": "Health & Wellness",
    "ECO": "Sustainability", "DESIGN": "Design & Architecture", "FASHION": "Fashion & Beauty",
    "BIZ": "Business & Retail", "LIFESTYLE": "Lifestyle",
}

PESTEL_COLORS = {
    "P": "#ef4444", "E": "#3b82f6", "S": "#22c55e",
    "T": "#a855f7", "En": "#14b8a6", "L": "#f97316",
}

DEFAULT_BRAND_COLOR = "#0ea5e9"


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _trend_title(trend: dict, language: str) -> str:
    if language == "de":
        return trend.get("title_de") or trend.get("title_en") or ""
    return trend.get("title_en") or trend.get("title_de") or ""


def _trend_summary(trend: dict, language: str) -> str:
    if language == "de":
        return trend.get("summary_de") or trend.get("summary_en") or ""
    return trend.get("summary_en") or trend.get("summary_de") or ""


def _pestel_badges(pestel: list[str]) -> str:
    spans = []
    for dim in pestel or []:
        color = PESTEL_COLORS.get(dim, "#64748b")
        spans.append(
            f'<span style="display:inline-block;padding:1px 7px;margin-right:4px;'
            f'border-radius:9px;font-size:11px;color:#fff;background:{color};">{_esc(dim)}</span>'
        )
    return "".join(spans)


def _trend_card_html(trend: dict, language: str, brand_color: str) -> str:
    title = _esc(_trend_title(trend, language))
    summary = _esc(_trend_summary(trend, language))
    vertical = VERTICAL_LABELS.get(trend.get("primary_vertical"), trend.get("primary_vertical") or "")
    article_url = f"{PORTAL_BASE_URL}/trends/{trend['slug']}"
    source = _esc(trend.get("source_name") or "Quelle")
    source_url = _esc(trend.get("source_url") or "#")
    score = trend.get("trend_score")
    score_str = f"{round(score * 100)}" if isinstance(score, (int, float)) and score <= 1 else (str(round(score)) if score else "—")
    return f"""
    <tr><td style="padding:14px 0;border-bottom:1px solid #e2e8f0;">
      <div style="font-size:12px;color:#64748b;margin-bottom:4px;">
        <span style="color:{brand_color};font-weight:600;">{_esc(vertical)}</span>
        &nbsp;·&nbsp;Relevanz {score_str}/100&nbsp;·&nbsp;{_pestel_badges(trend.get('pestel'))}
      </div>
      <a href="{article_url}" style="font-size:16px;font-weight:700;color:#0f172a;text-decoration:none;">{title}</a>
      <p style="font-size:14px;color:#334155;line-height:1.5;margin:6px 0;">{summary}</p>
      <div style="font-size:12px;color:#64748b;">
        Originalquelle: <a href="{source_url}" style="color:{brand_color};">{source}</a>
      </div>
    </td></tr>"""


def render_briefing_html(customer: dict, top_trends: list[dict], watchlist_hits: dict,
                         week_label: str, anchor_date: datetime) -> tuple[str, str]:
    """Render the briefing email. Returns (subject, html)."""
    language = customer.get("language") or "de"
    brand_name = customer.get("brand_name") or "Catandary Trend-Radar"
    brand_color = customer.get("brand_color") or DEFAULT_BRAND_COLOR
    logo_html = ""
    if customer.get("brand_logo_url"):
        logo_html = (f'<img src="{_esc(customer["brand_logo_url"])}" alt="{_esc(brand_name)}" '
                     f'style="max-height:40px;margin-bottom:8px;" />')

    n_watchlist = sum(len(v) for v in watchlist_hits.values())
    week_num = week_label.split("-W")[-1]
    subject = (f"{brand_name} — KW {week_num}: {len(top_trends)} Trend-Signale"
               + (f", {n_watchlist} Watchlist-Treffer" if n_watchlist else ""))

    verticals_str = ", ".join(VERTICAL_LABELS.get(v, v) for v in customer["verticals"])
    date_str = anchor_date.strftime("%d.%m.%Y")

    watchlist_section = ""
    if watchlist_hits:
        rows = []
        for keyword, trends in watchlist_hits.items():
            items = "".join(_trend_card_html(t, language, brand_color) for t in trends)
            rows.append(f"""
            <tr><td style="padding-top:18px;">
              <div style="font-size:13px;font-weight:700;color:{brand_color};
                          text-transform:uppercase;letter-spacing:0.05em;">⌖ {_esc(keyword)}</div>
            </td></tr>{items}""")
        watchlist_section = f"""
        <tr><td style="padding-top:28px;">
          <h2 style="font-size:18px;color:#0f172a;margin:0;">Ihre Watchlist</h2>
          <p style="font-size:13px;color:#64748b;margin:4px 0 0;">Treffer zu Ihren beobachteten Themen</p>
        </td></tr>{''.join(rows)}"""

    top_section = "".join(_trend_card_html(t, language, brand_color) for t in top_trends)
    portal_url = f"{PORTAL_BASE_URL}/radar/{customer['token']}"

    body = f"""<!DOCTYPE html>
<html lang="{language}"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;">
  <tr><td style="background:{brand_color};padding:24px 32px;">
    {logo_html}
    <div style="font-size:20px;font-weight:800;color:#ffffff;">{_esc(brand_name)}</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.85);">Wöchentliches Trend-Briefing · KW {week_num} · {date_str}</div>
  </td></tr>
  <tr><td style="padding:24px 32px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="font-size:14px;color:#334155;line-height:1.6;">
        Guten Morgen{', ' + _esc(customer['contact_name']) if customer.get('contact_name') else ''} —
        hier sind die <strong>{len(top_trends)} relevantesten Signale</strong> dieser Woche
        aus Ihren Branchen ({_esc(verticals_str)})
        {f"sowie <strong>{n_watchlist} Treffer</strong> aus Ihrer Watchlist" if n_watchlist else ""}.
      </td></tr>
      {watchlist_section}
      <tr><td style="padding-top:28px;">
        <h2 style="font-size:18px;color:#0f172a;margin:0;">Top-Signale der Woche</h2>
        <p style="font-size:13px;color:#64748b;margin:4px 0 0;">Kuratiert aus über 1.500 gesichteten Signalen dieser Woche, sortiert nach Relevanz</p>
      </td></tr>
      {top_section}
      <tr><td style="padding-top:24px;" align="center">
        <a href="{portal_url}" style="display:inline-block;background:{brand_color};color:#ffffff;
           font-size:14px;font-weight:700;padding:12px 28px;border-radius:8px;text-decoration:none;">
          Alle Signale im Radar-Portal ansehen →</a>
      </td></tr>
    </table>
  </td></tr>
  <tr><td style="padding:18px 32px;background:#f8fafc;border-top:1px solid #e2e8f0;">
    <div style="font-size:11px;color:#94a3b8;line-height:1.6;">
      {_esc(brand_name)} · bereitgestellt durch Catandary Trend-Radar ·
      Alle Signale verlinken auf die Originalquelle.<br>
      Konfiguration ändern oder abbestellen: Antwort auf diese E-Mail genügt.
    </div>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
    return subject, body


def select_briefing_content(customer: dict, since: str) -> tuple[list[dict], dict]:
    """Select watchlist hits first, then top trends excluding those IDs."""
    watchlist_hits = {}
    if customer["keywords"]:
        watchlist_hits = radar_db.search_watchlist(
            customer["keywords"], since=since,
            limit_per_keyword=WATCHLIST_LIMIT_PER_KEYWORD,
        )
    seen_ids = [t["id"] for trends in watchlist_hits.values() for t in trends]
    top_trends = radar_db.get_top_trends(
        customer["verticals"], since=since,
        limit=TOP_TRENDS_LIMIT, exclude_ids=seen_ids,
    )
    return top_trends, watchlist_hits


def send_via_resend(to: list[str], subject: str, html_body: str) -> bool:
    """Send through the Resend API. Returns True on success."""
    payload = json.dumps({
        "from": BRIEFING_FROM,
        "to": to,
        "subject": subject,
        "html": html_body,
    }).encode("utf-8")
    req = urlrequest.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=30) as resp:
            ok = 200 <= resp.status < 300
            if not ok:
                logger.error("resend returned status %s", resp.status)
            return ok
    except Exception as exc:
        logger.error("resend send failed: %s", exc)
        return False


def generate_for_customer(customer: dict, since: str, week_label: str,
                          anchor_date: datetime, send: bool) -> dict:
    """Generate, archive and optionally send one customer's briefing."""
    top_trends, watchlist_hits = select_briefing_content(customer, since)
    if not top_trends and not watchlist_hits:
        logger.warning("customer %s: no content in window since %s — skipped",
                       customer["id"], since)
        return {"customer_id": customer["id"], "status": "empty"}

    subject, body = render_briefing_html(customer, top_trends, watchlist_hits,
                                         week_label, anchor_date)
    trend_ids = [t["id"] for t in top_trends]
    hit_summary = {kw: [t["id"] for t in trends] for kw, trends in watchlist_hits.items()}
    briefing_id = radar_db.insert_briefing(
        customer["id"], week_label, subject, body, trend_ids, hit_summary,
    )

    outbox = Path(BRIEFING_OUTBOX)
    outbox.mkdir(parents=True, exist_ok=True)
    outfile = outbox / f"{week_label}-customer{customer['id']}.html"
    outfile.write_text(body, encoding="utf-8")

    sent = False
    if send:
        if not RESEND_API_KEY:
            logger.warning("RESEND_API_KEY not set — briefing archived + outbox only")
        else:
            recipients = [customer["email"], *customer["extra_recipients"]]
            sent = send_via_resend(recipients, subject, body)
            if sent:
                radar_db.mark_briefing_sent(briefing_id)

    logger.info("customer %s: briefing %s — %d top trends, %d watchlist hits%s",
                customer["id"], week_label, len(top_trends),
                sum(len(v) for v in watchlist_hits.values()),
                ", sent" if sent else "")
    return {
        "customer_id": customer["id"], "status": "sent" if sent else "generated",
        "briefing_id": briefing_id, "top_trends": len(top_trends),
        "watchlist_hits": sum(len(v) for v in watchlist_hits.values()),
        "outfile": str(outfile),
    }


def render_alert_html(customer: dict, watchlist_hits: dict, day_str: str) -> tuple[str, str]:
    """Render the compact daily alert email. Returns (subject, html)."""
    language = customer.get("language") or "de"
    brand_name = customer.get("brand_name") or "Catandary Trend-Radar"
    brand_color = customer.get("brand_color") or DEFAULT_BRAND_COLOR
    n_hits = sum(len(v) for v in watchlist_hits.values())
    keywords = ", ".join(watchlist_hits.keys())
    subject = f"{brand_name} Alert: {n_hits} neue{'r' if n_hits == 1 else ''} Watchlist-Treffer ({keywords})"

    sections = []
    for keyword, trends in watchlist_hits.items():
        items = "".join(_trend_card_html(t, language, brand_color) for t in trends)
        sections.append(f"""
        <tr><td style="padding-top:14px;">
          <div style="font-size:13px;font-weight:700;color:{brand_color};
                      text-transform:uppercase;letter-spacing:0.05em;">⌖ {_esc(keyword)}</div>
        </td></tr>{items}""")

    portal_url = f"{PORTAL_BASE_URL}/radar/{customer['token']}"
    body = f"""<!DOCTYPE html>
<html lang="{language}"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;">
  <tr><td style="background:{brand_color};padding:18px 32px;">
    <div style="font-size:17px;font-weight:800;color:#ffffff;">{_esc(brand_name)} · Watchlist-Alert</div>
    <div style="font-size:12px;color:rgba(255,255,255,0.85);">{day_str} · {n_hits} neue Treffer zu Ihren Themen</div>
  </td></tr>
  <tr><td style="padding:18px 32px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      {''.join(sections)}
      <tr><td style="padding-top:20px;" align="center">
        <a href="{portal_url}" style="display:inline-block;background:{brand_color};color:#ffffff;
           font-size:13px;font-weight:700;padding:10px 24px;border-radius:8px;text-decoration:none;">
          Im Radar-Portal ansehen →</a>
      </td></tr>
    </table>
  </td></tr>
  <tr><td style="padding:14px 32px;background:#f8fafc;border-top:1px solid #e2e8f0;">
    <div style="font-size:11px;color:#94a3b8;">Sie erhalten Alerts nur bei neuen Watchlist-Treffern.
    Die Wochen-Synthese folgt im Montags-Briefing.</div>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
    return subject, body


def generate_alert_for_customer(customer: dict, since: str, day_label: str,
                                day_str: str, send: bool) -> dict:
    """Daily alert: new watchlist hits only, deduped against recent alerts."""
    if not radar_db.TIER_LIMITS[customer["tier"]]["alerts"]:
        return {"customer_id": customer["id"], "status": "tier_without_alerts"}
    if not customer["keywords"]:
        return {"customer_id": customer["id"], "status": "no_keywords"}

    hits = radar_db.search_watchlist(customer["keywords"], since=since,
                                     limit_per_keyword=WATCHLIST_LIMIT_PER_KEYWORD)
    already = radar_db.get_alerted_trend_ids(customer["id"])
    hits = {kw: [t for t in trends if t["id"] not in already]
            for kw, trends in hits.items()}
    hits = {kw: trends for kw, trends in hits.items() if trends}
    if not hits:
        return {"customer_id": customer["id"], "status": "no_new_hits"}

    subject, body = render_alert_html(customer, hits, day_str)
    trend_ids = [t["id"] for trends in hits.values() for t in trends]
    hit_summary = {kw: [t["id"] for t in trends] for kw, trends in hits.items()}
    alert_id = radar_db.insert_alert(customer["id"], day_label, subject, body,
                                     trend_ids, hit_summary)

    outbox = Path(BRIEFING_OUTBOX)
    outbox.mkdir(parents=True, exist_ok=True)
    outfile = outbox / f"alert-{day_label}-customer{customer['id']}.html"
    outfile.write_text(body, encoding="utf-8")

    sent = False
    if send and RESEND_API_KEY:
        recipients = [customer["email"], *customer["extra_recipients"]]
        sent = send_via_resend(recipients, subject, body)
        if sent:
            radar_db.mark_alert_sent(alert_id)

    logger.info("customer %s: alert %s — %d new hits%s", customer["id"], day_label,
                len(trend_ids), ", sent" if sent else "")
    return {"customer_id": customer["id"], "status": "sent" if sent else "generated",
            "hits": len(trend_ids), "outfile": str(outfile)}


def main():
    parser = argparse.ArgumentParser(description="Trend-Radar Briefing-Generator")
    parser.add_argument("--customer", type=int, default=None, help="nur diese Kunden-ID")
    parser.add_argument("--send", action="store_true", help="per Resend versenden")
    parser.add_argument("--since-days", type=int, default=7, help="Signalfenster in Tagen")
    parser.add_argument("--anchor-latest", action="store_true",
                        help="Woche am neuesten Trend statt heute ausrichten (Demo/alter Snapshot)")
    parser.add_argument("--alerts", action="store_true",
                        help="Tages-Alerts statt Wochen-Briefing (Fenster: --since-days, Default 1)")
    args = parser.parse_args()
    if args.alerts and args.since_days == 7:
        args.since_days = 1

    radar_db.init_radar_schema()

    anchor = datetime.now(timezone.utc)
    if args.anchor_latest:
        from pipeline.db import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT MAX(COALESCE(published_at, created_at)) AS latest "
                "FROM trends WHERE status = 'published'"
            ).fetchone()
        if row and row["latest"]:
            latest = row["latest"].replace(" ", "T").split(".")[0]
            anchor = datetime.fromisoformat(latest).replace(tzinfo=timezone.utc)
            logger.info("anchoring on latest published trend: %s", anchor.date())

    since = (anchor - timedelta(days=args.since_days)).strftime("%Y-%m-%d")
    iso = anchor.isocalendar()
    week_label = f"{iso.year}-W{iso.week:02d}"

    if args.customer:
        customer = radar_db.get_customer(args.customer)
        if not customer:
            sys.exit(f"Kunde {args.customer} nicht gefunden.")
        customers = [customer]
    else:
        customers = radar_db.list_customers(status="active")

    if not customers:
        logger.info("no active customers")
        return

    if args.alerts:
        day_label = anchor.strftime("%Y-%m-%d")
        day_str = anchor.strftime("%d.%m.%Y")
        results = [generate_alert_for_customer(c, since, day_label, day_str, args.send)
                   for c in customers]
        generated = [r for r in results if r["status"] in ("generated", "sent")]
        print(f"\nAlerts {day_label}: {len(generated)}/{len(results)} erzeugt "
              f"(Fenster: {args.since_days} Tag(e))")
        for r in generated:
            print(f"  Kunde {r['customer_id']}: {r['hits']} neue Treffer → {r['outfile']}"
                  + ("  [versandt]" if r["status"] == "sent" else ""))
        return

    results = [generate_for_customer(c, since, week_label, anchor, args.send)
               for c in customers]
    generated = [r for r in results if r["status"] != "empty"]
    print(f"\nBriefings {week_label}: {len(generated)}/{len(results)} erzeugt "
          f"(Fenster: {args.since_days} Tage bis {anchor.date()})")
    for r in generated:
        print(f"  Kunde {r['customer_id']}: {r['top_trends']} Top-Trends, "
              f"{r['watchlist_hits']} Watchlist-Treffer → {r['outfile']}"
              + ("  [versandt]" if r["status"] == "sent" else ""))


if __name__ == "__main__":
    main()
