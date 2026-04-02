#!/usr/bin/env python3
"""Backfill Catandary Relevance Score (CRS) for all existing trends.

Updates the trend_score column with the computed CRS value (0–100, stored as 0.0–1.0).

Usage:
    python scripts/backfill_crs.py --dry-run   # Preview score distribution
    python scripts/backfill_crs.py              # Apply scores
"""

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from pipeline.crs import compute_crs

DB_PATH = Path(__file__).parent.parent / "data" / "catandary.db"


def run_backfill(dry_run: bool = False):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Get all trends with their source info
    rows = conn.execute("""
        SELECT t.id, t.confidence, t.verticals, t.pestel, t.trend_signal_type,
               s.source_type
        FROM trends t
        LEFT JOIN raw_entries re ON t.raw_entry_id = re.id
        LEFT JOIN sources s ON re.source_id = s.id
    """).fetchall()

    print(f"Computing CRS for {len(rows)} trends...")

    scores = []
    updates = []

    for row in rows:
        verticals = json.loads(row["verticals"]) if row["verticals"] else []
        pestel = json.loads(row["pestel"]) if row["pestel"] else []

        crs = compute_crs(
            confidence=row["confidence"] or 0.8,
            num_verticals=len(verticals),
            num_pestel=len(pestel),
            signal_type=row["trend_signal_type"] or "product_launch",
            source_type=row["source_type"],
        )

        scores.append(crs)
        # Store as 0.0–1.0 in trend_score (consistent with existing schema)
        updates.append((crs / 100.0, row["id"]))

    # Print distribution
    print(f"\nCRS Distribution (n={len(scores)}):")
    print(f"  Min: {min(scores)}  Max: {max(scores)}  Avg: {sum(scores)/len(scores):.1f}")

    buckets = Counter()
    for s in scores:
        bucket = (s // 10) * 10
        buckets[bucket] += 1

    print(f"\n{'Range':<12} {'Count':>6} {'Bar'}")
    print("-" * 50)
    for bucket in sorted(buckets):
        bar = "#" * (buckets[bucket] // 5)
        print(f"  {bucket:3d}–{bucket+9:3d}    {buckets[bucket]:>5}  {bar}")

    # Top 10 score breakdown
    print(f"\nTop 10 highest CRS:")
    top = sorted(zip(scores, [r["id"] for r in rows]), reverse=True)[:10]
    for crs_val, tid in top:
        row = conn.execute(
            "SELECT title_en, trend_signal_type, verticals, pestel FROM trends WHERE id = ?",
            (tid,)
        ).fetchone()
        verts = len(json.loads(row["verticals"])) if row["verticals"] else 0
        pestel_n = len(json.loads(row["pestel"])) if row["pestel"] else 0
        print(f"  CRS {crs_val:3d} | {row['trend_signal_type']:<18s} | V={verts} P={pestel_n} | {row['title_en'][:60]}")

    if dry_run:
        print("\n[DRY RUN] No changes applied.")
        conn.close()
        return

    print("\nApplying CRS scores...")
    conn.executemany("UPDATE trends SET trend_score = ? WHERE id = ?", updates)
    conn.commit()
    conn.close()
    print(f"Updated {len(updates)} trends.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run_backfill(dry_run=dry_run)
