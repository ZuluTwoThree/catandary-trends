"""Reclassify draft trends using LLM-based semantic vertical assignment.

Reuses the same Qwen3 8B model as the pipeline classification stage.
Called after trend insertion to fix vertical misclassifications before auto-publish.
"""

import json
import logging
import re
import sqlite3
import time

import httpx

from pipeline.config import DATABASE_PATH, OLLAMA_HOST, MODEL_CLASSIFY

logger = logging.getLogger(__name__)

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

Title: "Royal Enfield's Electric Motorcycle Signals a Shift"
→ {{"primary": "TECH", "secondaries": ["ECO"]}}

Title: "Durable Outdoor Bluetooth Speakers"
→ {{"primary": "TECH", "secondaries": []}}

## Task
Title: {title}
Summary: {summary}

Return ONLY a JSON object with "primary" and "secondaries", nothing else. /no_think"""


def _classify_one(title: str, summary: str) -> dict | None:
    """Classify a single trend via Ollama."""
    prompt = CLASSIFY_PROMPT.format(title=title, summary=summary[:500])
    try:
        resp = httpx.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL_CLASSIFY,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=30,
        )
        text = resp.json().get("response", "").strip()
        match = re.search(r'\{[^}]+\}', text)
        if match:
            data = json.loads(match.group())
            primary = data.get("primary", "").upper()
            secondaries = [s.upper() for s in data.get("secondaries", [])]
            if primary in VERTICALS:
                all_verts = [primary] + [s for s in secondaries if s in VERTICALS and s != primary]
                return {"primary": primary, "verticals": all_verts}
    except Exception as e:
        logger.warning("Reclassify error: %s", e)
    return None


def reclassify_drafts() -> dict:
    """Reclassify all draft trends. Returns stats dict."""
    conn = sqlite3.connect(DATABASE_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT id, title_en, summary_en, primary_vertical FROM trends WHERE status = 'draft' ORDER BY id")
    rows = c.fetchall()
    total = len(rows)

    if total == 0:
        logger.info("Reclassify: no drafts to process")
        conn.close()
        return {"total": 0, "changed": 0, "errors": 0}

    logger.info("Reclassify: processing %d drafts", total)
    changed = 0
    errors = 0
    t0 = time.time()

    for i, row in enumerate(rows):
        tid = row["id"]
        title = row["title_en"]
        summary = row["summary_en"] or ""
        old_primary = row["primary_vertical"]

        result = _classify_one(title, summary)
        if result is None:
            errors += 1
            continue

        new_primary = result["primary"]
        new_verticals = result["verticals"]

        if new_primary != old_primary:
            changed += 1
            logger.info("Reclassify #%d: %s -> %s  %s", tid, old_primary, new_primary, title[:55])

        c.execute(
            "UPDATE trends SET primary_vertical = ?, verticals = ? WHERE id = ?",
            (new_primary, json.dumps(new_verticals), tid),
        )

        if (i + 1) % 50 == 0:
            conn.commit()

    conn.commit()
    elapsed = time.time() - t0
    logger.info("Reclassify done in %.1fs: %d/%d changed, %d errors", elapsed, changed, total, errors)
    conn.close()
    return {"total": total, "changed": changed, "errors": errors}
