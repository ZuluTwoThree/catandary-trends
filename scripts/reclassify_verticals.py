#!/usr/bin/env python3
"""Reclassify all existing trends with the new 8-vertical taxonomy.

Uses pure semantic classification (no source vertical hint).
Updates primary_vertical and verticals JSON array.
"""

import json
import sqlite3
import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OLLAMA_HOST = "http://127.0.0.1:11434"
MODEL = "qwen3:8b"
DB_PATH = "data/catandary.db"

VERTICALS = ["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]

CLASSIFY_PROMPT = """Classify this trend into the Catandary vertical taxonomy.

## Verticals (pick 1 primary + up to 2 secondary if genuinely cross-vertical)
- FOOD: Food & Beverage, ingredients, restaurants, agriculture, nutrition
- TECH: Technology, AI, software, hardware, robotics, IoT, startups
- HEALTH: Medicine, pharma, fitness, mental health, biotech, wellness
- ECO: Sustainability, energy, climate, circular economy, packaging
- DESIGN: Architecture, product design, interiors, UX, urban planning
- FASHION: Fashion, beauty, cosmetics, textiles, jewelry
- BIZ: Business strategy, retail, e-commerce, fintech, finance, M&A
- LIFESTYLE: Culture, media, entertainment, gaming, social impact, education, luxury, travel, sports

Return a JSON object with:
- "primary": the single most fitting vertical code
- "secondaries": array of 0-2 additional verticals (only if genuinely cross-vertical)

Title: {title}
Summary: {summary}

Return ONLY the JSON, nothing else. /no_think"""


def classify_trend(title: str, summary: str) -> dict | None:
    prompt = CLASSIFY_PROMPT.format(title=title, summary=summary[:500])
    try:
        resp = httpx.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=30,
        )
        text = resp.json().get("response", "").strip()
        # Extract JSON
        import re
        match = re.search(r'\{[^}]+\}', text)
        if match:
            data = json.loads(match.group())
            primary = data.get("primary", "").upper()
            secondaries = [s.upper() for s in data.get("secondaries", [])]

            if primary in VERTICALS:
                all_verts = [primary] + [s for s in secondaries if s in VERTICALS and s != primary]
                return {"primary": primary, "verticals": all_verts}
    except Exception as e:
        print(f"  ERROR: {e}")
    return None


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT id, title_en, summary_en, primary_vertical, verticals FROM trends ORDER BY id")
    rows = c.fetchall()
    total = len(rows)

    print(f"Reclassifying {total} trends with 8-vertical taxonomy\n")

    changed = 0
    errors = 0
    t0 = time.time()

    for i, row in enumerate(rows):
        tid = row["id"]
        title = row["title_en"]
        summary = row["summary_en"] or ""
        old_primary = row["primary_vertical"]

        result = classify_trend(title, summary)

        if result is None:
            errors += 1
            print(f"  [{i+1}/{total}] ERROR id={tid}: {title[:50]}")
            continue

        new_primary = result["primary"]
        new_verticals = result["verticals"]

        if new_primary != old_primary:
            changed += 1
            print(f"  [{i+1}/{total}] {old_primary:10} -> {new_primary:10}  {title[:55]}")

        c.execute(
            "UPDATE trends SET primary_vertical = ?, verticals = ? WHERE id = ?",
            (new_primary, json.dumps(new_verticals), tid),
        )

        # Commit every 50
        if (i + 1) % 50 == 0:
            conn.commit()
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            remaining = (total - i - 1) / rate
            print(f"  --- {i+1}/{total} done, {changed} changed, {elapsed:.0f}s elapsed, ~{remaining:.0f}s remaining ---")

    conn.commit()
    elapsed = time.time() - t0

    print(f"\n{'='*60}")
    print(f"Done in {elapsed:.0f}s ({total/elapsed:.1f} trends/sec)")
    print(f"Changed: {changed}/{total} ({changed/total*100:.0f}%)")
    print(f"Errors: {errors}")

    # Show new distribution
    c.execute("SELECT primary_vertical, COUNT(*) FROM trends GROUP BY primary_vertical ORDER BY COUNT(*) DESC")
    print(f"\nNew distribution:")
    for vert, cnt in c.fetchall():
        print(f"  {vert:10} {cnt:>4}")

    conn.close()


if __name__ == "__main__":
    main()
