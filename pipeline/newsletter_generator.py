"""Weekly newsletter generator for Catandary Trends.

Generates an editorial newsletter with LLM-synthesized summaries:
- Overall editorial (EN → DE) — 3 paragraphs
- Per-vertical summaries (EN → DE) — 2-3 sentences each
- Mega-trend radar — top mega-trends by weekly signal count

Output: JSON + HTML preview. Published to frontend via newsletter_editions table.
Run weekly via cron: 0 9 * * 1
"""

import argparse
import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.config import DATA_DIR, LOG_LEVEL, MODEL_GENERATE, load_mega_trends
from pipeline.db import get_connection

import os as _os
if _os.getenv("NEWSLETTER_LLM_BACKEND") == "llamacpp":
    from pipeline.llamacpp_client import chat
else:
    from pipeline.ollama_client import chat

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_URL = "https://catandary.de"

VERTICAL_LABELS = {
    "FOOD": ("Food & Beverage", "\U0001f37d"),
    "TECH": ("Technology & AI", "\U0001f4bb"),
    "HEALTH": ("Health & Wellness", "\U0001f3e5"),
    "ECO": ("Sustainability", "\U0001f331"),
    "DESIGN": ("Design & Architecture", "\U0001f3a8"),
    "FASHION": ("Fashion & Beauty", "\U0001f457"),
    "BIZ": ("Business & Retail", "\U0001f4ca"),
    "LIFESTYLE": ("Lifestyle & Culture", "\U0001f3ad"),
}

VERTICAL_ORDER = ["TECH", "BIZ", "FOOD", "HEALTH", "ECO", "LIFESTYLE", "FASHION", "DESIGN"]

# ---------------------------------------------------------------------------
# System prompts (approved by user)
# ---------------------------------------------------------------------------

EDITORIAL_SYSTEM_PROMPT = (
    "You are the editorial voice of Catandary Trends, a cross-industry trend "
    "intelligence newsletter. Your tone is analytical, confident, concise — like "
    "a senior analyst briefing a board. Never use assistant language (\"Let's "
    "explore\", \"Here's what happened\"). Never end with rhetorical questions. "
    "State observations as facts. Technical terms stay in English."
)

VERTICAL_SYSTEM_PROMPT = (
    "You are a vertical analyst for Catandary Trends. You write per-vertical "
    "summaries for a weekly newsletter read by foresight professionals. Be "
    "concise and declarative. Every word must earn its place. Name specific "
    "companies and products — never stay abstract. No superlatives, no "
    "exclamation marks."
)


BANNED_PHRASES = (
    '"landscape", "paradigm shift", "game-changing", "reshaping the future", '
    '"it remains to be seen", "stakeholders", "navigate", '
    '"at the intersection of", "leveraging", "ecosystem", "doubling down", '
    '"amid growing concerns", "poised to", "underscores the importance of", '
    '"robust", "innovative", "in an era of"'
)


# ---------------------------------------------------------------------------
# 1. Data aggregation
# ---------------------------------------------------------------------------

def get_weekly_newsletter_data(days: int = 7, week_start: str | None = None,
                               week_end: str | None = None) -> dict:
    """Fetch published trends for a date range and aggregate for editorial.

    If week_start/week_end are provided, use those instead of days-based cutoff.
    """
    if week_start and week_end:
        cutoff = week_start
        upper = week_end
    else:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        upper = None

    with get_connection() as conn:
        if upper:
            rows = conn.execute(
                "SELECT id, title_en, title_de, slug, summary_en, summary_de, "
                "primary_vertical, mega_trend, tags, pestel, trend_signal_type, "
                "trend_score, confidence, source_name, created_at "
                "FROM trends WHERE status = 'published' AND created_at > ? AND created_at < ? "
                "ORDER BY trend_score DESC, created_at DESC",
                (cutoff, upper),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title_en, title_de, slug, summary_en, summary_de, "
                "primary_vertical, mega_trend, tags, pestel, trend_signal_type, "
                "trend_score, confidence, source_name, created_at "
                "FROM trends WHERE status = 'published' AND created_at > ? "
                "ORDER BY trend_score DESC, created_at DESC",
                (cutoff,),
            ).fetchall()

    # Convert rows to dicts
    trends = []
    for row in rows:
        d = dict(row) if hasattr(row, "keys") else {
            "id": row[0], "title_en": row[1], "title_de": row[2],
            "slug": row[3], "summary_en": row[4], "summary_de": row[5],
            "primary_vertical": row[6], "mega_trend": row[7],
            "tags": row[8], "pestel": row[9], "trend_signal_type": row[10],
            "trend_score": row[11], "confidence": row[12],
            "source_name": row[13], "created_at": row[14],
        }
        # Parse JSON fields
        for field in ("tags", "pestel"):
            val = d.get(field)
            if isinstance(val, str):
                try:
                    d[field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    d[field] = []
        trends.append(d)

    # Aggregate
    mega_trend_map = {mt["key"]: mt for mt in load_mega_trends()}
    overall_mega_counts: Counter = Counter()
    overall_signal_types: Counter = Counter()
    verticals: dict[str, dict] = {}

    for t in trends:
        v = t["primary_vertical"]
        if v not in verticals:
            verticals[v] = {
                "count": 0,
                "top_trends": [],
                "mega_trend_counts": Counter(),
                "signal_types": Counter(),
            }
        vd = verticals[v]
        vd["count"] += 1
        if len(vd["top_trends"]) < 5:
            vd["top_trends"].append(t)

        mt = t.get("mega_trend")
        if mt:
            vd["mega_trend_counts"][mt] += 1
            overall_mega_counts[mt] += 1

        st = t.get("trend_signal_type")
        if st:
            vd["signal_types"][st] += 1
            overall_signal_types[st] += 1

    # Calendar week
    now = datetime.now(timezone.utc)
    iso_year, iso_week, _ = now.isocalendar()

    return {
        "total_count": len(trends),
        "period": f"{iso_year}-W{iso_week:02d}",
        "period_label": f"Week {iso_week}/{iso_year}",
        "verticals": verticals,
        "mega_trend_counts": overall_mega_counts,
        "mega_trend_map": mega_trend_map,
        "signal_types": overall_signal_types,
        "top_trends": trends[:10],
    }


# ---------------------------------------------------------------------------
# 2. Format data for LLM prompts
# ---------------------------------------------------------------------------

def _format_vertical_counts(data: dict) -> str:
    """Format vertical counts as 'TECH (41), BIZ (24), ...'"""
    parts = []
    for v in VERTICAL_ORDER:
        if v in data["verticals"]:
            parts.append(f'{v} ({data["verticals"][v]["count"]})')
    return ", ".join(parts)


def _format_top_trends(trends: list[dict], max_summary: int = 120) -> str:
    """Format trends with titles and summaries for LLM context."""
    lines = []
    for t in trends:
        title = t["title_en"] or ""
        summary = (t["summary_en"] or "")[:max_summary]
        source = t.get("source_name") or ""
        lines.append(f'- "{title}" ({source}) — {summary}')
    return "\n".join(lines)


def _format_mega_trend_momentum(data: dict) -> str:
    """Format top mega-trends with human-readable names, counts and momentum."""
    top_mts = data["mega_trend_counts"].most_common(7)
    parts = []
    for key, count in top_mts:
        mt_info = data["mega_trend_map"].get(key, {})
        name = mt_info.get("name_en", key.replace("_", " ").title())
        momentum = mt_info.get("momentum", "stable")
        parts.append(f"{name} ({count} signals, {momentum})")
    return ", ".join(parts)


def _format_signal_types(data: dict) -> str:
    """Format signal type distribution."""
    return ", ".join(f"{st}: {c}" for st, c in data["signal_types"].most_common(5))


def build_editorial_prompt(data: dict) -> str:
    """Build the user prompt for overall editorial generation."""
    return f"""Write the editorial summary for this week's Catandary Trends newsletter.

<data>
Period: {data["period_label"]}
Total new signals: {data["total_count"]}
Verticals: {_format_vertical_counts(data)}

Top signals:
{_format_top_trends(data["top_trends"])}

Mega-trend momentum: {_format_mega_trend_momentum(data)}
Signal types: {_format_signal_types(data)}
</data>

Structure your response as exactly 3 paragraphs:
1. DOMINANT THEME: What single pattern defined this week? Name the 1-2 mega-trends with strongest momentum. Do not open with "This week" — lead with the insight.
2. KEY SIGNALS: 2-3 specific signals that carry the most strategic weight. Name companies, products, or specific developments from the signal titles above. Weave them naturally into your sentences.
3. CROSS-CURRENTS: One unexpected cross-vertical connection or weak signal that deserves attention. Name the shared driver and the mechanism. End with one forward-looking implication — a concrete statement, not a question.

Constraints:
- Select 4-5 most significant signals. Do NOT cover every vertical.
- Use ONLY facts from the data above. Do not invent statistics or numbers.
- Use the full mega-trend names as provided (e.g., "Artificial Intelligence & Automation", not keys with underscores).
- Reference specific signals by weaving their topic or company name into prose — do NOT use bracketed IDs like [TECH-01]. Write grammatically correct flowing text.
- Each paragraph: 2-3 sentences. Total: 150-200 words.
- No bullet points, no headers, no lists. Flowing editorial prose only.

Banned phrases: {BANNED_PHRASES}"""


def build_vertical_prompt(data: dict) -> str:
    """Build the user prompt for per-vertical summaries."""
    sections = []
    for v in VERTICAL_ORDER:
        vd = data["verticals"].get(v)
        if not vd or vd["count"] < 3:
            continue
        label, _ = VERTICAL_LABELS.get(v, (v, ""))
        top_mt = vd["mega_trend_counts"].most_common(3)
        # Use human-readable mega-trend names
        mt_parts = []
        for k, c in top_mt:
            mt_info = data["mega_trend_map"].get(k, {})
            mt_name = mt_info.get("name_en", k.replace("_", " ").title())
            mt_parts.append(f"{mt_name} ({c})")
        mt_str = ", ".join(mt_parts) if mt_parts else "none"
        signal_str = ", ".join(f"{st}: {c}" for st, c in vd["signal_types"].most_common(3))
        trends_str = _format_top_trends(vd["top_trends"][:3], max_summary=80)

        sections.append(f"""{v} — {label} ({vd["count"]} signals)
Mega-trends: {mt_str}
Signal types: {signal_str}
Top signals:
{trends_str}""")

    return f"""Write per-vertical summaries for this week's newsletter.

<data>
{chr(10).join(sections)}
</data>

For each vertical, write exactly 2-3 sentences as one paragraph:
- Sentence 1: What defined this vertical's signals? Name the dominant signal type and direction.
- Sentence 2: Which mega-trend dominated? Connect it to a specific signal by naming the company, product, or development.
- Sentence 3 (only if warranted): An emerging pattern or cross-vertical connection. Omit if nothing genuinely noteworthy — do not pad.

Format:
TECH
[2-3 sentences]

FOOD
[2-3 sentences]

Order by signal count descending. Skip verticals with fewer than 3 signals.
For verticals with 3-5 signals, keep to 2 sentences.
Use full mega-trend names as provided (e.g., "Artificial Intelligence & Automation", not keys with underscores).
Reference specific signals by topic or company name in natural prose — do NOT use bracketed IDs like [TECH-01].
Do not add introduction or transitions between verticals."""



# ---------------------------------------------------------------------------
# 2b. Post-processing: linkify mega-trends and trend references
# ---------------------------------------------------------------------------

def linkify_editorial(text: str, data: dict) -> str:
    """Insert HTML links for mega-trend names and trend titles in editorial text.

    Mega-trends link to /trends/mega, trend titles link to /trends/[slug].
    Each match is linked only on first occurrence to avoid cluttered text.
    """
    linked = set()

    mt_links = {}
    for key, mt_info in data["mega_trend_map"].items():
        name = mt_info.get("name_en", "")
        if name and len(name) > 5:
            mt_links[name] = f"{BASE_URL}/trends/mega"

    trend_links = {}
    for v, vd in data["verticals"].items():
        for t in vd["top_trends"]:
            title = t.get("title_en", "")
            slug = t.get("slug", "")
            if title and slug and len(title) > 10:
                trend_links[title] = f"{BASE_URL}/trends/{slug}"

    for name in sorted(mt_links.keys(), key=len, reverse=True):
        if name in linked:
            continue
        url = mt_links[name]
        if name in text:
            link = f'<a href="{url}" style="color: #60a5fa; text-decoration: none;">{name}</a>'
            text = text.replace(name, link, 1)
            linked.add(name)

    for title in sorted(trend_links.keys(), key=len, reverse=True):
        if title in linked:
            continue
        url = trend_links[title]
        if title in text:
            link = f'<a href="{url}" style="color: #60a5fa; text-decoration: none;">{title}</a>'
            text = text.replace(title, link, 1)
            linked.add(title)

    return text


def linkify_editorial_md(text: str, data: dict) -> str:
    """Insert markdown links for mega-trends and trends (for frontend rendering).

    Returns text with [Name](/trends/mega) and [Title](/trends/slug) markdown links.
    """
    linked = set()

    mt_links = {}
    for key, mt_info in data["mega_trend_map"].items():
        name = mt_info.get("name_en", "")
        if name and len(name) > 5:
            mt_links[name] = "/trends/mega"

    trend_links = {}
    for v, vd in data["verticals"].items():
        for t in vd["top_trends"]:
            title = t.get("title_en", "")
            slug = t.get("slug", "")
            if title and slug and len(title) > 10:
                trend_links[title] = f"/trends/{slug}"

    for name in sorted(mt_links.keys(), key=len, reverse=True):
        if name in linked:
            continue
        if name in text:
            text = text.replace(name, f"[{name}]({mt_links[name]})", 1)
            linked.add(name)

    for title in sorted(trend_links.keys(), key=len, reverse=True):
        if title in linked:
            continue
        if title in text:
            text = text.replace(title, f"[{title}]({trend_links[title]})", 1)
            linked.add(title)

    return text


# ---------------------------------------------------------------------------
# 3. LLM editorial generation
# ---------------------------------------------------------------------------

def generate_editorial_en(data: dict) -> str:
    """Generate the overall editorial in English."""
    prompt = build_editorial_prompt(data)
    logger.info("Generating overall editorial (EN)...")
    result = chat(
        model=MODEL_GENERATE,
        prompt=prompt,
        system=EDITORIAL_SYSTEM_PROMPT,
        temperature=0.65,
    )
    logger.info("Editorial EN: %d words", len(result.split()))
    return result.strip()


def generate_vertical_summaries_en(data: dict) -> str:
    """Generate per-vertical summaries in English.

    Retries once if the model produces fewer than half the expected verticals.
    """
    expected_verticals = sum(
        1 for v in VERTICAL_ORDER
        if v in data["verticals"] and data["verticals"][v]["count"] >= 3
    )
    prompt = build_vertical_prompt(data)

    for attempt in range(2):
        logger.info("Generating vertical summaries (EN), attempt %d...", attempt + 1)
        result = chat(
            model=MODEL_GENERATE,
            prompt=prompt,
            system=VERTICAL_SYSTEM_PROMPT,
            temperature=0.6,
        )
        result = result.strip()
        # Quick check: count how many vertical headers appear in parsed result
        parsed_check = parse_vertical_summaries(result)
        found = len(parsed_check)
        logger.info("Vertical summaries EN: %d words, %d/%d verticals",
                     len(result.split()), found, expected_verticals)
        if found >= expected_verticals // 2:
            return result
        logger.warning("Too few verticals (%d/%d), retrying...", found, expected_verticals)

    return result


def _generate_single_vertical_en(vertical: str, data: dict) -> str | None:
    """Generate a summary for a single missing vertical."""
    vd = data["verticals"].get(vertical)
    if not vd or vd["count"] < 3:
        return None
    label, _ = VERTICAL_LABELS.get(vertical, (vertical, ""))
    top_mt = vd["mega_trend_counts"].most_common(3)
    mt_parts = []
    for k, c in top_mt:
        mt_info = data["mega_trend_map"].get(k, {})
        mt_name = mt_info.get("name_en", k.replace("_", " ").title())
        mt_parts.append(f"{mt_name} ({c})")
    mt_str = ", ".join(mt_parts) if mt_parts else "none"
    signal_str = ", ".join(f"{st}: {c}" for st, c in vd["signal_types"].most_common(3))
    trends_str = _format_top_trends(vd["top_trends"][:3], max_summary=80)

    prompt = f"""Write a 2-3 sentence summary for the {label} vertical this week.

<data>
{vertical} — {label} ({vd["count"]} signals)
Mega-trends: {mt_str}
Signal types: {signal_str}
Top signals:
{trends_str}
</data>

Sentence 1: What defined this vertical's signals? Name the dominant signal type and direction.
Sentence 2: Which mega-trend dominated? Connect it to a specific signal by naming the company, product, or development.
Sentence 3 (only if warranted): An emerging pattern or cross-vertical connection.
Use full mega-trend names. No bracketed IDs. No bullet points."""

    logger.info("Generating single vertical summary for %s...", vertical)
    result = chat(
        model=MODEL_GENERATE,
        prompt=prompt,
        system=VERTICAL_SYSTEM_PROMPT,
        temperature=0.6,
    )
    result = result.strip()
    if len(result.split()) < 10:
        return None
    logger.info("Single vertical %s: %d words", vertical, len(result.split()))
    return result



def parse_vertical_summaries(raw: str) -> dict[str, str]:
    """Parse the vertical summaries output into {VERTICAL: summary} dict.

    Handles various LLM formatting: plain labels, **bold**, ##-headers,
    colons, trailing dashes, etc.
    """
    result = {}
    current_vertical = None
    current_lines = []

    for line in raw.split("\n"):
        stripped = line.strip()
        # Remove common markdown/formatting around vertical labels
        cleaned = stripped
        cleaned = re.sub(r'^#+\s*', '', cleaned)        # ## TECH → TECH
        cleaned = re.sub(r'\*+', '', cleaned)            # **TECH** → TECH
        cleaned = cleaned.strip()
        cleaned = re.sub(r'[\s:—\-]+$', '', cleaned)    # TECH: or TECH — → TECH
        cleaned = cleaned.strip()

        if cleaned in VERTICAL_LABELS:
            if current_vertical and current_lines:
                result[current_vertical] = " ".join(current_lines).strip()
            current_vertical = cleaned
            current_lines = []
        elif current_vertical and stripped:
            current_lines.append(stripped)

    # Last vertical
    if current_vertical and current_lines:
        result[current_vertical] = " ".join(current_lines).strip()

    return result


# ---------------------------------------------------------------------------
# 4. Mega-trend radar data
# ---------------------------------------------------------------------------

def build_mega_trend_radar(data: dict) -> list[dict]:
    """Build mega-trend radar entries for the newsletter."""
    radar = []
    for key, count in data["mega_trend_counts"].most_common(7):
        mt_info = data["mega_trend_map"].get(key, {})
        radar.append({
            "key": key,
            "name_en": mt_info.get("name_en", key.replace("_", " ").title()),
            "name_de": mt_info.get("name_de", ""),
            "icon": mt_info.get("icon", ""),
            "momentum": mt_info.get("momentum", "stable"),
            "signal_count": count,
        })
    return radar


# ---------------------------------------------------------------------------
# 5. Newsletter edition storage
# ---------------------------------------------------------------------------

NEWSLETTER_EDITIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS newsletter_editions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    week INTEGER NOT NULL,
    editorial TEXT,
    vertical_summaries TEXT,
    mega_trend_radar TEXT,
    trend_refs TEXT,
    total_signals INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(year, week)
);
"""


def init_newsletter_table():
    """Ensure newsletter_editions table exists."""
    with get_connection() as conn:
        conn.execute(NEWSLETTER_EDITIONS_SCHEMA)


def save_newsletter_edition(edition: dict):
    """Save a newsletter edition to the database."""
    init_newsletter_table()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO newsletter_editions "
            "(year, week, editorial, vertical_summaries, "
            "mega_trend_radar, trend_refs, total_signals) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                edition["year"],
                edition["week"],
                edition["editorial"],
                json.dumps(edition["vertical_summaries"], ensure_ascii=False),
                json.dumps(edition["mega_trend_radar"], ensure_ascii=False),
                json.dumps(edition["trend_refs"], ensure_ascii=False),
                edition["total_signals"],
            ),
        )
    logger.info("Saved newsletter edition %d-W%02d", edition["year"], edition["week"])


def get_latest_newsletter() -> dict | None:
    """Get the most recent newsletter edition."""
    init_newsletter_table()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM newsletter_editions ORDER BY year DESC, week DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    for field in ("vertical_summaries", "mega_trend_radar", "trend_refs"):
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def get_newsletter_editions(limit: int = 12) -> list[dict]:
    """Get recent newsletter editions for archive listing."""
    init_newsletter_table()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, year, week, total_signals, created_at "
            "FROM newsletter_editions ORDER BY year DESC, week DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) if hasattr(r, "keys") else {} for r in rows]


# ---------------------------------------------------------------------------
# 6. HTML generation (for preview / email)
# ---------------------------------------------------------------------------

def _md_links_to_html(text: str) -> str:
    """Convert markdown [text](url) links to HTML <a> tags."""
    return re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        rf'<a href="{BASE_URL}\2" style="color: #60a5fa; text-decoration: none;">\1</a>',
        text,
    )


def generate_html(edition: dict) -> str:
    """Generate newsletter HTML from an edition dict."""
    editorial = _md_links_to_html(edition.get("editorial", ""))
    vert_summaries = {
        k: _md_links_to_html(v) for k, v in edition.get("vertical_summaries", {}).items()
    }
    radar = edition.get("mega_trend_radar", [])
    trend_refs = edition.get("trend_refs", {})
    year = edition.get("year", 0)
    week = edition.get("week", 0)
    total = edition.get("total_signals", 0)

    period_label = f"Week {week}/{year}"
    title_text = f"Catandary Trends — {period_label}"
    editorial_title = "Weekly Overview"
    radar_title = "Mega-Trend Radar"
    cta_text = "View all trends"
    foresight_text = "Deeper analysis? \u2192 Catandary Foresight"
    signals_label = "signals"

    # Editorial paragraphs
    editorial_html = ""
    for para in editorial.split("\n\n"):
        para = para.strip()
        if para:
            editorial_html += f'<p style="color: #d1d5db; font-size: 15px; line-height: 1.7; margin: 0 0 16px;">{para}</p>\n'

    # Vertical sections
    vertical_sections = ""
    for v in VERTICAL_ORDER:
        summary = vert_summaries.get(v, "")
        if not summary:
            continue
        label, icon = VERTICAL_LABELS.get(v, (v, ""))
        v_trends = trend_refs.get(v, [])
        count = len(v_trends) if v_trends else ""
        count_str = f" ({count} {signals_label})" if count else ""

        trend_items = ""
        for t in v_trends[:3]:
            t_title = t.get("title", "")
            slug = t.get("slug", "")
            source = t.get("source_name", "")
            trend_items += f"""
            <tr><td style="padding: 8px 0; border-bottom: 1px solid #2a2a2a;">
              <a href="{BASE_URL}/trends/{slug}" style="color: #60a5fa; text-decoration: none; font-weight: 600; font-size: 14px;">{t_title}</a>
              <span style="color: #6b7280; font-size: 12px; margin-left: 8px;">{source}</span>
            </td></tr>"""

        vertical_sections += f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 24px;">
          <tr><td style="padding: 10px 14px; background: #1e1e2e; border-radius: 8px 8px 0 0;">
            <span style="font-size: 15px; font-weight: 700; color: #e2e8f0;">{icon} {label}{count_str}</span>
          </td></tr>
          <tr><td style="padding: 12px 14px;">
            <p style="color: #d1d5db; font-size: 14px; line-height: 1.6; margin: 0 0 12px;">{summary}</p>
            <table width="100%" cellpadding="0" cellspacing="0">{trend_items}</table>
          </td></tr>
        </table>"""

    # Mega-trend radar
    radar_items = ""
    for mt in radar:
        name = mt.get("name_en", "")
        icon = mt.get("icon", "")
        count = mt.get("signal_count", 0)
        momentum = mt.get("momentum", "stable")
        arrow = {"rising": "\u2191", "emerging": "\u2191\u2191", "declining": "\u2193", "stable": "\u2192"}.get(momentum, "\u2192")
        radar_items += f"""
        <tr><td style="padding: 6px 0; color: #d1d5db; font-size: 14px;">
          {icon} {name}: <strong>{count}</strong> {signals_label} <span style="color: #9ca3af;">({arrow} {momentum})</span>
        </td></tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
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
          <div style="font-size: 14px; color: #9ca3af; margin-top: 8px;">{period_label} &middot; {total} {signals_label}</div>
        </td></tr>

        <!-- Editorial -->
        <tr><td style="padding: 24px;">
          <h2 style="margin: 0 0 16px; font-size: 18px; color: #e2e8f0; font-weight: 700;">{editorial_title}</h2>
          {editorial_html}
        </td></tr>

        <!-- Verticals -->
        <tr><td style="padding: 0 24px 24px;">
          {vertical_sections}
        </td></tr>

        <!-- Mega-Trend Radar -->
        <tr><td style="padding: 0 24px 24px;">
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 16px;">
            <tr><td style="padding: 10px 14px; background: #1e1e2e; border-radius: 8px 8px 0 0;">
              <span style="font-size: 15px; font-weight: 700; color: #e2e8f0;">{radar_title}</span>
            </td></tr>
            <tr><td style="padding: 12px 14px;">
              <table width="100%" cellpadding="0" cellspacing="0">{radar_items}</table>
            </td></tr>
          </table>
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
            &copy; {datetime.now().year} Catandary. Powered by Catandary Foresight.
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 7. Main orchestration
# ---------------------------------------------------------------------------

def generate_newsletter(days: int = 7, skip_llm: bool = False,
                        year: int | None = None, week: int | None = None) -> dict:
    """Generate a complete newsletter edition.

    If year/week are provided, generate for that specific ISO week retroactively.
    Returns the edition dict with all fields populated.
    """
    if year and week:
        # Calculate Monday-Sunday of the given ISO week
        from datetime import date
        monday = date.fromisocalendar(year, week, 1)
        sunday = date.fromisocalendar(year, week, 7)
        week_start = f"{monday.isoformat()}T00:00:00"
        week_end = f"{sunday.isoformat()}T23:59:59"
        logger.info("Collecting trend data for %d-W%02d (%s to %s)...", year, week, monday, sunday)
        data = get_weekly_newsletter_data(week_start=week_start, week_end=week_end)
        # Override period label
        data["period"] = f"{year}-W{week:02d}"
        data["period_label"] = f"Week {week}/{year}"
        iso_year, iso_week = year, week
    else:
        logger.info("Collecting trend data (last %d days)...", days)
        data = get_weekly_newsletter_data(days)
        now = datetime.now(timezone.utc)
        iso_year, iso_week, _ = now.isocalendar()

    logger.info("Found %d signals across %d verticals",
                data["total_count"], len(data["verticals"]))

    if data["total_count"] == 0:
        logger.info("No signals found — skipping newsletter generation")
        return {}

    # Build trend_refs for the HTML template
    trend_refs = {}
    for v, vd in data["verticals"].items():
        trend_refs[v] = [
            {
                "title": t["title_en"],
                "slug": t["slug"],
                "source_name": t.get("source_name", ""),
            }
            for t in vd["top_trends"][:3]
        ]

    if skip_llm:
        logger.info("Skipping LLM calls (--skip-llm)")
        return {
            "year": iso_year,
            "week": iso_week,
            "editorial": f"[LLM skipped] {data['total_count']} signals this week.",
            "vertical_summaries": {},
            "mega_trend_radar": build_mega_trend_radar(data),
            "trend_refs": trend_refs,
            "total_signals": data["total_count"],
        }

    # Generate editorial
    editorial = generate_editorial_en(data)

    # Generate vertical summaries
    verticals_raw = generate_vertical_summaries_en(data)
    verticals = parse_vertical_summaries(verticals_raw)

    # Fill missing verticals that should have been included (>= 3 signals)
    missing = [
        v for v in VERTICAL_ORDER
        if v in data["verticals"] and data["verticals"][v]["count"] >= 3
        and v not in verticals
    ]
    if missing:
        logger.warning("Missing verticals %s, generating individually...", missing)
        for v in missing:
            summary = _generate_single_vertical_en(v, data)
            if summary:
                verticals[v] = summary

    # Linkify editorials and vertical summaries (markdown for frontend)
    editorial = linkify_editorial_md(editorial, data)
    verticals_linked = {
        v: linkify_editorial_md(text, data)
        for v, text in verticals.items()
    }

    edition = {
        "year": iso_year,
        "week": iso_week,
        "editorial": editorial,
        "vertical_summaries": verticals_linked,
        "mega_trend_radar": build_mega_trend_radar(data),
        "trend_refs": trend_refs,
        "total_signals": data["total_count"],
    }

    return edition


def main():
    parser = argparse.ArgumentParser(description="Generate weekly newsletter")
    parser.add_argument("--days", type=int, default=7, help="Days to look back")
    parser.add_argument("--year", type=int, help="ISO year for retroactive generation")
    parser.add_argument("--week", type=int, help="ISO week number for retroactive generation")
    parser.add_argument("--preview", action="store_true", help="Save HTML preview only, don't store in DB")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM calls, data-only output")
    args = parser.parse_args()

    edition = generate_newsletter(
        days=args.days, skip_llm=args.skip_llm,
        year=args.year, week=args.week,
    )
    if not edition:
        return

    # Save to DB
    if not args.preview:
        save_newsletter_edition(edition)

    # Generate HTML preview
    preview_dir = DATA_DIR / "newsletters"
    preview_dir.mkdir(exist_ok=True)

    week_label = f"{edition['year']}-W{edition['week']:02d}"

    html = generate_html(edition)
    path = preview_dir / f"newsletter_{week_label}.html"
    path.write_text(html, encoding="utf-8")
    logger.info("HTML preview: %s", path)
    (preview_dir / "latest.html").write_text(html, encoding="utf-8")

    # Save edition JSON
    json_path = preview_dir / f"newsletter_{week_label}.json"
    json_path.write_text(
        json.dumps(edition, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("JSON: %s", json_path)

    logger.info("Newsletter %s complete: %d signals, %d verticals",
                week_label, edition["total_signals"], len(edition.get("vertical_summaries", {})))


if __name__ == "__main__":
    main()
