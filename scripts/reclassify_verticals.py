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

OLLAMA_HOST = "http://172.29.96.1:11434"
MODEL = "qwen3:8b"
DB_PATH = "data/catandary.db"

VERTICALS = ["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]

CLASSIFY_PROMPT = """Classify this trend into the Catandary vertical taxonomy.

## Verticals
- FOOD: Food & beverage, ingredients, restaurants, agriculture, nutrition science
- TECH: Technology, AI, software, hardware, robotics, IoT, biotech, quantum, materials science, R&D breakthroughs
- HEALTH: Clinical medicine, pharma drugs in trials/market, mental health, supplements, body physiology, healthcare delivery
- ECO: Sustainability, energy, climate, circular economy, packaging, environmental policy
- DESIGN: Architecture, product design, interiors, UX, urban planning
- FASHION: Apparel, beauty, cosmetics, textiles, jewelry (the products themselves)
- BIZ: Business strategy, retail, e-commerce, fintech, banking, payments, M&A, funding
- LIFESTYLE: Culture, media, entertainment, gaming, social impact, education, luxury experiences, travel, sport (athletes, events, communities, gym/studio culture, fitness as lifestyle)

## Disambiguation rules (CRITICAL)
1. **Biotech, gene editing, synthetic biology, lab research → TECH** (not HEALTH). HEALTH is for clinical/patient-facing topics.
2. **AI/tech applied to a specific industry → that industry.** E.g. "AI for drug discovery" = HEALTH, "AI chip architecture" = TECH.
3. **Fintech, payments, banking, crypto finance → BIZ** (not TECH), unless it's about the underlying tech stack.
4. **Sustainable materials for a specific industry → that industry.** E.g. bio-textiles = FASHION, compostable food packaging = FOOD.
5. **Sustainability as the core topic → ECO** (carbon credits, circular economy policy, renewables).
6. **M&A, funding rounds, IPOs, earnings → BIZ**, unless the deal only makes sense within one vertical.
7. **Scientific research papers (biology, chemistry, physics) → TECH**, unless clearly clinical/patient-focused.
8. **Sport & fitness routing:**
   - Athletes, sport events, sport communities, gyms/studios as lifestyle, fitness culture → LIFESTYLE
   - Clinical/physiological wellness, supplements, body health, medical aspects of fitness → HEALTH
   - Sport apparel, footwear, athleisure → FASHION
   - Sport business, M&A, brand strategy → BIZ
   - Sport architecture, stadiums, facility design → DESIGN
   - Sport nutrition products → FOOD
   - Sport wearables / biometrics tech itself → TECH
9. **Most trends belong to ONE vertical.** Only add secondaries when the trend genuinely cannot be understood without two industries.

## Examples
Title: "CRISPR Advances Enable Faster Gene Editing in Crops"
→ {{"primary": "TECH", "secondaries": ["FOOD"]}}

Title: "New Alzheimer's Drug Shows Promise in Phase 3 Trial"
→ {{"primary": "HEALTH", "secondaries": []}}

Title: "Stripe Launches Embedded Banking for SMBs"
→ {{"primary": "BIZ", "secondaries": []}}

Title: "LVMH Acquires Luxury Watchmaker in €2B Deal"
→ {{"primary": "BIZ", "secondaries": ["FASHION"]}}

Title: "Bacterial Flagellar Adaptation Reveals Evolutionary Mechanism"
→ {{"primary": "TECH", "secondaries": []}}

Title: "Biodegradable Packaging for Fresh Produce Hits Shelves"
→ {{"primary": "FOOD", "secondaries": ["ECO"]}}

Title: "Quantum Computing Breakthrough in Drug Discovery"
→ {{"primary": "TECH", "secondaries": ["HEALTH"]}}

## Task
Title: {title}
Summary: {summary}

Return ONLY a JSON object with "primary" and "secondaries", nothing else. /no_think"""


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
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    # Force WAL checkpoint to clear any stale locks
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Only reclassify drafts by default, pass --all to reclassify everything
    if "--all" in sys.argv:
        c.execute("SELECT id, title_en, summary_en, primary_vertical, verticals FROM trends ORDER BY id")
    else:
        c.execute("SELECT id, title_en, summary_en, primary_vertical, verticals FROM trends WHERE status = 'draft' ORDER BY id")
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
