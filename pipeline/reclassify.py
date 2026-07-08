"""Reclassify draft trends using LLM-based semantic vertical assignment.

Reuses the same Qwen3 8B model as the pipeline classification stage.
Called after trend insertion to fix vertical misclassifications before auto-publish.
"""

import json
import logging
import sqlite3
import time
from typing import Literal

from pydantic import BaseModel, Field

from pipeline.config import (
    ANTHROPIC_MODEL_CLASSIFY,
    CLASSIFY_BACKEND,
    DATABASE_PATH,
    MODEL_CLASSIFY,
    STAGE_8B_BACKEND,
    STAGE_8B_MODEL,
)
from pipeline import anthropic_client, llamacpp_client
from pipeline.ollama_client import chat_structured

logger = logging.getLogger(__name__)

Vertical = Literal["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]
VERTICALS = ["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]


class ReclassifyResult(BaseModel):
    primary: Vertical
    secondaries: list[Vertical] = Field(default_factory=list)


CLASSIFY_SYSTEM = """You assign trends to the Catandary vertical taxonomy.

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
→ {"primary": "TECH", "secondaries": ["FOOD"]}

Title: "New Alzheimer's Drug Shows Promise in Phase 3 Trial"
→ {"primary": "HEALTH", "secondaries": []}

Title: "Stripe Launches Embedded Banking for SMBs"
→ {"primary": "BIZ", "secondaries": []}

Title: "Royal Enfield's Electric Motorcycle Signals a Shift"
→ {"primary": "TECH", "secondaries": ["ECO"]}

Title: "Durable Outdoor Bluetooth Speakers"
→ {"primary": "TECH", "secondaries": []}"""


def _classify_one(title: str, summary: str) -> dict | None:
    """Classify a single trend with retries + structured output.

    Routes to llama.cpp 8B when STAGE_8B_BACKEND=llamacpp (run_pipeline_batch
    is responsible for bringing the 8B server up around this call), otherwise
    Ollama qwen3:8b.
    """
    prompt = f"Title: {title}\nSummary: {summary[:500]}"
    if CLASSIFY_BACKEND == "anthropic":
        result = anthropic_client.chat_structured(
            model=ANTHROPIC_MODEL_CLASSIFY,
            prompt=prompt,
            schema=ReclassifyResult,
            system=CLASSIFY_SYSTEM,
            temperature=0.0,
        )
    elif STAGE_8B_BACKEND == "llamacpp":
        result = llamacpp_client.chat_structured(
            model=STAGE_8B_MODEL,
            prompt=prompt,
            schema=ReclassifyResult,
            system=CLASSIFY_SYSTEM,
            temperature=0.0,
        )
    else:
        result = chat_structured(
            model=MODEL_CLASSIFY,
            prompt=prompt,
            schema=ReclassifyResult,
            system=CLASSIFY_SYSTEM,
            temperature=0.0,
            fallback_model="qwen3:8b",
        )
    if result is None:
        return None
    primary = result.primary
    secondaries = [s for s in result.secondaries if s != primary]
    return {"primary": primary, "verticals": [primary] + secondaries}


def _open_conn():
    """Backend-appropriate raw connection (long-lived with periodic commits —
    the get_connection context manager doesn't fit this loop's shape).
    Returns (conn, cursor, paramstyle-placeholder)."""
    from pipeline.db import USE_POSTGRES, DATABASE_URL
    if USE_POSTGRES:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return conn, c, "%s"
    conn = sqlite3.connect(DATABASE_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor(), "?"


def gate_mega_trends() -> dict:
    """Null out mega-trends the embedding strongly disagrees with (issue #39).

    The LLM classifier sometimes forces a mega-trend that doesn't fit (a
    superhero-movie box-office trend labelled 'future_of_food_and_agriculture').
    After embedding, we re-check each draft's mega-trend against the distill
    head's top-3 for that embedding; if the stored label isn't even a top-3
    candidate, it's a genuine misassignment → set NULL. Same rule as the #39
    backfill (scripts/fix_mega_abstain.py). Cheap, CPU-only, no GPU.
    """
    import numpy as np
    try:
        from pipeline.distill import DistillClassifier
        clf = DistillClassifier.load()
    except Exception as e:  # noqa: BLE001 — head missing → skip gate, don't crash cycle
        logger.warning("Mega-gate skipped (distill head unavailable: %s)", e)
        return {"checked": 0, "nulled": 0}

    conn, c, ph = _open_conn()
    c.execute("SELECT id, mega_trend, embedding FROM trends "
              "WHERE status = 'draft' AND mega_trend IS NOT NULL AND embedding IS NOT NULL")
    rows = c.fetchall()
    checked = 0
    nulled = 0
    for row in rows:
        emb = row["embedding"]
        if not emb:
            continue
        v = np.array([float(x) for x in emb.strip("[]").split(",")]).reshape(1, -1)
        pred = clf.classify_batch(v)[0]
        checked += 1
        if row["mega_trend"] not in (pred.get("mega_top3") or []):
            c.execute(f"UPDATE trends SET mega_trend = NULL WHERE id = {ph}", (row["id"],))
            nulled += 1
    conn.commit()
    conn.close()
    logger.info("Mega-gate: %d/%d drafts had an implausible mega-trend nulled", nulled, checked)
    return {"checked": checked, "nulled": nulled}


def reclassify_drafts() -> dict:
    """Reclassify all draft trends. Returns stats dict."""
    conn, c, ph = _open_conn()

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
            f"UPDATE trends SET primary_vertical = {ph}, verticals = {ph} WHERE id = {ph}",
            (new_primary, json.dumps(new_verticals), tid),
        )

        if (i + 1) % 50 == 0:
            conn.commit()

    conn.commit()
    elapsed = time.time() - t0
    logger.info("Reclassify done in %.1fs: %d/%d changed, %d errors", elapsed, changed, total, errors)
    conn.close()
    return {"total": total, "changed": changed, "errors": errors}
