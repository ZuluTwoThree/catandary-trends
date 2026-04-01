"""Weekly newsletter generator for Catandary Trends.

Generates an HTML newsletter with top trends from the past week,
grouped by vertical. Run weekly via cron: 0 9 * * 1
"""

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.db import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_URL = "https://catandary.de"

VERTICAL_LABELS = {
    "FOOD": ("Food & Beverage", "🍽"),
    "TECH": ("Technology & AI", "💻"),
    "HEALTH": ("Health & Wellness", "🏥"),
    "ECO": ("Sustainability", "🌱"),
    "DESIGN": ("Design & Architecture", "🎨"),
    "FASHION": ("Fashion & Beauty", "👗"),
    "BIZ": ("Business & Retail", "📊"),
    "CULTURE": ("Culture & Media", "🎭"),
    "SOCIAL": ("Social Impact", "🤝"),
    "LUXURY": ("Luxury & Premium", "✨"),
}


def get_weekly_trends(days: int = 7, limit_per_vertical: int = 3) -> dict[str, list[dict]]:
    """Get top trends from the past N days, grouped by vertical."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title_en, title_de, slug, summary_en, summary_de, "
            "primary_vertical, trend_score, source_name "
            "FROM trends WHERE status = 'published' AND created_at > ? "
            "ORDER BY trend_score DESC, created_at DESC",
            (cutoff,),
        ).fetchall()

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        r = dict(row) if hasattr(row, "keys") else {
            "id": row[0], "title_en": row[1], "title_de": row[2],
            "slug": row[3], "summary_en": row[4], "summary_de": row[5],
            "primary_vertical": row[6], "trend_score": row[7],
            "source_name": row[8],
        }
        v = r["primary_vertical"]
        if v not in grouped:
            grouped[v] = []
        if len(grouped[v]) < limit_per_vertical:
            grouped[v].append(r)

    return grouped


def get_subscribers() -> list[str]:
    """Get active newsletter subscriber emails."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT email FROM newsletter_subscribers "
            "WHERE unsubscribed_at IS NULL"
        ).fetchall()
    return [row["email"] if hasattr(row, "keys") else row[0] for row in rows]


def generate_html(grouped: dict[str, list[dict]], lang: str = "de") -> str:
    """Generate newsletter HTML."""
    today = datetime.now().strftime("%d.%m.%Y")

    sections = []
    for vertical, trends in grouped.items():
        label, icon = VERTICAL_LABELS.get(vertical, (vertical, "📌"))
        items = []
        for t in trends:
            title = (t["title_de"] or t["title_en"]) if lang == "de" else t["title_en"]
            summary = (t["summary_de"] or t["summary_en"]) if lang == "de" else t["summary_en"]
            score = t["trend_score"] or 0
            url = f"{BASE_URL}/trends/{t['slug']}"
            items.append(f"""
            <tr>
              <td style="padding: 12px 0; border-bottom: 1px solid #2a2a2a;">
                <a href="{url}" style="color: #60a5fa; text-decoration: none; font-weight: 600; font-size: 15px;">
                  {title}
                </a>
                <div style="color: #9ca3af; font-size: 13px; margin-top: 4px; line-height: 1.5;">
                  {summary or ''}
                </div>
                <div style="color: #6b7280; font-size: 12px; margin-top: 4px;">
                  Score: {score:.1f} · {t['source_name'] or ''}
                </div>
              </td>
            </tr>""")

        sections.append(f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 24px;">
          <tr>
            <td style="padding: 8px 12px; background: #1e1e2e; border-radius: 8px 8px 0 0;">
              <span style="font-size: 16px; font-weight: 700; color: #e2e8f0;">
                {icon} {label}
              </span>
            </td>
          </tr>
          {''.join(items)}
        </table>""")

    title_text = "Wöchentliche Trend-Signale" if lang == "de" else "Weekly Trend Signals"
    subtitle = "Die wichtigsten Trends der Woche aus allen Branchen" if lang == "de" else "Top trends of the week across all industries"
    cta_text = "Alle Trends ansehen" if lang == "de" else "View all trends"
    foresight_text = "Tiefere Analysen? → Catandary Foresight" if lang == "de" else "Deeper analysis? → Catandary Foresight"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin: 0; padding: 0; background: #0f0f17; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background: #0f0f17;">
    <tr><td align="center" style="padding: 20px;">
      <table width="600" cellpadding="0" cellspacing="0" style="background: #161622; border-radius: 12px; overflow: hidden;">

        <!-- Header -->
        <tr><td style="padding: 32px 24px; text-align: center; border-bottom: 1px solid #2a2a2a;">
          <div style="font-size: 24px; font-weight: 700; color: #e2e8f0;">
            Catandary <span style="color: #60a5fa;">Trends</span>
          </div>
          <div style="font-size: 14px; color: #9ca3af; margin-top: 8px;">{today}</div>
        </td></tr>

        <!-- Title -->
        <tr><td style="padding: 24px;">
          <h1 style="margin: 0; font-size: 22px; color: #e2e8f0;">{title_text}</h1>
          <p style="color: #9ca3af; font-size: 14px; margin: 8px 0 0;">{subtitle}</p>
        </td></tr>

        <!-- Trends -->
        <tr><td style="padding: 0 24px 24px;">
          {''.join(sections)}
        </td></tr>

        <!-- CTA -->
        <tr><td style="padding: 0 24px 24px; text-align: center;">
          <a href="{BASE_URL}/trends" style="display: inline-block; background: #3b82f6; color: white; padding: 12px 32px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px;">
            {cta_text}
          </a>
          <div style="margin-top: 16px;">
            <a href="{BASE_URL}" style="color: #60a5fa; font-size: 13px; text-decoration: none;">
              {foresight_text}
            </a>
          </div>
        </td></tr>

        <!-- Footer -->
        <tr><td style="padding: 16px 24px; border-top: 1px solid #2a2a2a; text-align: center;">
          <p style="color: #6b7280; font-size: 12px; margin: 0;">
            © {datetime.now().year} Catandary. Powered by Catandary Foresight.
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate weekly newsletter")
    parser.add_argument("--days", type=int, default=7, help="Days to look back")
    parser.add_argument("--lang", default="de", choices=["de", "en"])
    parser.add_argument("--preview", action="store_true", help="Save HTML preview only")
    args = parser.parse_args()

    grouped = get_weekly_trends(days=args.days)
    total = sum(len(v) for v in grouped.values())
    logger.info("Found %d trends across %d verticals", total, len(grouped))

    if total == 0:
        logger.info("No trends to send")
        return

    html = generate_html(grouped, lang=args.lang)

    if args.preview:
        out = Path("data/newsletter_preview.html")
        out.write_text(html, encoding="utf-8")
        logger.info("Preview saved to %s", out)
        return

    subscribers = get_subscribers()
    logger.info("Found %d subscribers", len(subscribers))

    if not subscribers:
        logger.info("No subscribers, saving preview only")
        out = Path("data/newsletter_preview.html")
        out.write_text(html, encoding="utf-8")
        logger.info("Preview saved to %s", out)
        return

    # Email sending via Resend or SMTP would go here
    logger.info("Newsletter generated for %d subscribers (email sending not yet configured)", len(subscribers))
    out = Path("data/newsletter_preview.html")
    out.write_text(html, encoding="utf-8")
    logger.info("Preview saved to %s", out)


if __name__ == "__main__":
    main()
