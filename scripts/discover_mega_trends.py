#!/usr/bin/env python3
"""Mega-Trend Discovery — Data-driven approach to finding mega-trends.

Two complementary strategies:
1. Embedding Clustering (Bottom-Up): UMAP + HDBSCAN on trend embeddings
2. Temporal Signal Detection: Tag frequency over time to spot emerging themes

Usage:
    python -m scripts.discover_mega_trends clustering   # Run embedding clustering
    python -m scripts.discover_mega_trends temporal      # Run temporal signal detection
    python -m scripts.discover_mega_trends both          # Run both (default)
"""

import json
import logging
import struct
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = Path("data/catandary.db")


def load_trends() -> list[dict]:
    """Load all trends with embeddings, tags, and metadata."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT t.id, t.title_en, t.summary_en, t.tags, t.primary_vertical,
               t.mega_trend, t.embedding, t.trend_signal_type,
               r.published_date
        FROM trends t
        LEFT JOIN raw_entries r ON t.raw_entry_id = r.id
        WHERE t.embedding IS NOT NULL AND t.status = 'published'
        ORDER BY t.id
    """).fetchall()
    conn.close()

    trends = []
    for row in rows:
        emb_bytes = row["embedding"]
        n_floats = len(emb_bytes) // 4
        embedding = np.array(struct.unpack(f"{n_floats}f", emb_bytes), dtype=np.float32)

        tags = []
        if row["tags"]:
            try:
                tags = json.loads(row["tags"])
            except json.JSONDecodeError:
                pass

        pub_date = None
        if row["published_date"]:
            try:
                pub_date = datetime.fromisoformat(row["published_date"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        trends.append({
            "id": row["id"],
            "title": row["title_en"],
            "summary": row["summary_en"] or "",
            "tags": tags,
            "vertical": row["primary_vertical"],
            "mega_trend": row["mega_trend"],
            "signal_type": row["trend_signal_type"],
            "embedding": embedding,
            "published_date": pub_date,
        })

    logger.info("Loaded %d trends with embeddings (%d dimensions)", len(trends), len(trends[0]["embedding"]))
    return trends


# =============================================================================
# Strategy 1: Embedding Clustering
# =============================================================================

def run_clustering(trends: list[dict], min_k: int = 10, max_k: int = 35):
    """Cluster trend embeddings and analyze resulting groups."""
    logger.info("=== Strategy 1: Embedding Clustering ===")

    # Build embedding matrix
    X = np.vstack([t["embedding"] for t in trends])
    X = normalize(X)  # L2 normalize for cosine-like behavior with K-Means

    # Dimensionality reduction with PCA first (4096 → 50) for speed and noise reduction
    from sklearn.decomposition import PCA
    logger.info("PCA: 4096 → 50 dimensions")
    pca = PCA(n_components=50, random_state=42)
    X_reduced = pca.fit_transform(X)
    explained = sum(pca.explained_variance_ratio_)
    logger.info("PCA explained variance: %.1f%%", explained * 100)

    # Find optimal k via silhouette score
    logger.info("Testing K-Means with k=%d..%d", min_k, max_k)
    best_k, best_score = 0, -1
    scores = {}
    for k in range(min_k, max_k + 1, 1):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_reduced)
        score = silhouette_score(X_reduced, labels, sample_size=min(1000, len(X_reduced)))
        scores[k] = score
        if score > best_score:
            best_k, best_score = k, score

    logger.info("Silhouette scores:")
    for k, s in sorted(scores.items()):
        marker = " ← BEST" if k == best_k else ""
        logger.info("  k=%2d  silhouette=%.4f%s", k, s, marker)

    # Run final clustering with best k
    logger.info("Final clustering with k=%d (silhouette=%.4f)", best_k, best_score)
    km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    labels = km.fit_predict(X_reduced)

    # Analyze clusters
    clusters = defaultdict(list)
    for i, label in enumerate(labels):
        clusters[label].append(trends[i])

    logger.info("\n" + "=" * 80)
    logger.info("DISCOVERED CLUSTERS (%d clusters, %d trends)", best_k, len(trends))
    logger.info("=" * 80)

    cluster_summaries = []
    for cluster_id in sorted(clusters.keys()):
        members = clusters[cluster_id]
        size = len(members)

        # Top tags
        tag_counter = Counter()
        for m in members:
            tag_counter.update(m["tags"])
        top_tags = tag_counter.most_common(8)

        # Vertical distribution
        vert_counter = Counter(m["vertical"] for m in members)
        top_verts = vert_counter.most_common(3)

        # Existing mega-trend distribution (for comparison)
        mt_counter = Counter(m["mega_trend"] for m in members if m["mega_trend"])
        top_mts = mt_counter.most_common(3)

        # Signal type distribution
        sig_counter = Counter(m["signal_type"] for m in members if m["signal_type"])
        top_sigs = sig_counter.most_common(2)

        # Sample titles
        sample_titles = [m["title"][:80] for m in members[:5]]

        summary = {
            "cluster_id": cluster_id,
            "size": size,
            "top_tags": top_tags,
            "verticals": top_verts,
            "existing_mega_trends": top_mts,
            "signal_types": top_sigs,
            "sample_titles": sample_titles,
        }
        cluster_summaries.append(summary)

        logger.info("\n--- Cluster %d (%d trends) ---", cluster_id, size)
        logger.info("  Verticals: %s", ", ".join(f"{v}({c})" for v, c in top_verts))
        logger.info("  Top tags: %s", ", ".join(f"{t}({c})" for t, c in top_tags))
        if top_mts:
            logger.info("  Existing mega-trends: %s", ", ".join(f"{mt}({c})" for mt, c in top_mts))
        else:
            logger.info("  Existing mega-trends: NONE — potential new mega-trend!")
        logger.info("  Signal types: %s", ", ".join(f"{s}({c})" for s, c in top_sigs))
        logger.info("  Sample titles:")
        for title in sample_titles:
            logger.info("    • %s", title)

    # Compare with existing mega-trends
    logger.info("\n" + "=" * 80)
    logger.info("COMPARISON: Clusters vs. Existing Mega-Trends")
    logger.info("=" * 80)

    existing_mts = set(t["mega_trend"] for t in trends if t["mega_trend"])
    cluster_dominant_mts = set()
    for cs in cluster_summaries:
        if cs["existing_mega_trends"]:
            dominant = cs["existing_mega_trends"][0][0]
            cluster_dominant_mts.add(dominant)

    uncovered_mts = existing_mts - cluster_dominant_mts
    if uncovered_mts:
        logger.info("Existing mega-trends NOT dominant in any cluster (may be too broad/fragmented):")
        for mt in sorted(uncovered_mts):
            count = sum(1 for t in trends if t["mega_trend"] == mt)
            logger.info("  • %s (%d trends)", mt, count)

    # Clusters without clear mega-trend match
    orphan_clusters = [cs for cs in cluster_summaries if not cs["existing_mega_trends"]]
    if orphan_clusters:
        logger.info("\nClusters with NO existing mega-trend — candidates for new mega-trends:")
        for cs in orphan_clusters:
            logger.info("  Cluster %d (%d trends): tags=%s",
                        cs["cluster_id"], cs["size"],
                        ", ".join(t for t, _ in cs["top_tags"][:5]))

    return cluster_summaries


# =============================================================================
# Strategy 2: Temporal Signal Detection
# =============================================================================

def run_temporal(trends: list[dict], min_tag_count: int = 3):
    """Detect tags/themes that are increasing in frequency over time."""
    logger.info("\n=== Strategy 2: Temporal Signal Detection ===")

    # Filter trends with valid dates
    dated = [t for t in trends if t["published_date"] is not None]
    logger.info("Trends with publication dates: %d/%d", len(dated), len(trends))

    if len(dated) < 50:
        logger.warning("Too few dated trends for temporal analysis")
        return []

    # Group by month
    monthly_tags = defaultdict(Counter)
    monthly_counts = Counter()
    for t in dated:
        month_key = t["published_date"].strftime("%Y-%m")
        monthly_counts[month_key] += 1
        monthly_tags[month_key].update(t["tags"])

    months = sorted(monthly_counts.keys())
    logger.info("Time range: %s to %s (%d months)", months[0], months[-1], len(months))
    for m in months:
        logger.info("  %s: %d trends", m, monthly_counts[m])

    # For meaningful trend detection, need at least 2 periods
    if len(months) < 2:
        logger.info("Only 1 month of data — splitting into weekly windows instead")
        # Fall back to weekly
        monthly_tags = defaultdict(Counter)
        monthly_counts = Counter()
        for t in dated:
            week_key = t["published_date"].strftime("%Y-W%W")
            monthly_counts[week_key] += 1
            monthly_tags[week_key].update(t["tags"])
        months = sorted(monthly_counts.keys())
        logger.info("Weekly windows: %s to %s (%d weeks)", months[0], months[-1], len(months))
        for w in months:
            logger.info("  %s: %d trends", w, monthly_counts[w])

    if len(months) < 2:
        logger.warning("Not enough time periods for trend detection")
        return []

    # Split into early/late halves for comparison
    mid = len(months) // 2
    early_months = months[:mid]
    late_months = months[mid:]

    early_tags = Counter()
    early_total = 0
    for m in early_months:
        early_tags.update(monthly_tags[m])
        early_total += monthly_counts[m]

    late_tags = Counter()
    late_total = 0
    for m in late_months:
        late_tags.update(monthly_tags[m])
        late_total += monthly_counts[m]

    logger.info("\nEarly period (%s): %d trends", ", ".join(early_months), early_total)
    logger.info("Late period (%s): %d trends", ", ".join(late_months), late_total)

    # Calculate tag acceleration (normalized frequency change)
    all_tags = set(early_tags.keys()) | set(late_tags.keys())
    accelerating = []
    for tag in all_tags:
        early_freq = early_tags[tag] / max(early_total, 1)
        late_freq = late_tags[tag] / max(late_total, 1)
        total_count = early_tags[tag] + late_tags[tag]

        if total_count < min_tag_count:
            continue

        if early_freq > 0:
            acceleration = (late_freq - early_freq) / early_freq
        elif late_freq > 0:
            acceleration = float("inf")  # New tag, didn't exist before
        else:
            continue

        accelerating.append({
            "tag": tag,
            "early_count": early_tags[tag],
            "late_count": late_tags[tag],
            "early_freq": early_freq,
            "late_freq": late_freq,
            "acceleration": acceleration,
            "total": total_count,
        })

    # Sort by acceleration
    accelerating.sort(key=lambda x: x["acceleration"], reverse=True)

    # Emerging tags (new or strongly increasing)
    logger.info("\n" + "=" * 80)
    logger.info("EMERGING SIGNALS (tags accelerating over time)")
    logger.info("=" * 80)

    emerging_new = [a for a in accelerating if a["acceleration"] == float("inf") and a["total"] >= min_tag_count]
    if emerging_new:
        logger.info("\nNEW tags (only in late period):")
        for a in emerging_new[:20]:
            logger.info("  • %-40s late=%d", a["tag"], a["late_count"])

    emerging_growing = [a for a in accelerating
                        if a["acceleration"] != float("inf")
                        and a["acceleration"] > 0.5
                        and a["total"] >= min_tag_count]
    if emerging_growing:
        logger.info("\nSTRONGLY GROWING tags (>50%% acceleration):")
        for a in emerging_growing[:20]:
            logger.info("  • %-40s early=%d → late=%d (+%.0f%%)",
                        a["tag"], a["early_count"], a["late_count"], a["acceleration"] * 100)

    # Declining tags
    declining = [a for a in accelerating if a["acceleration"] < -0.5 and a["total"] >= min_tag_count]
    declining.sort(key=lambda x: x["acceleration"])
    if declining:
        logger.info("\nDECLINING tags (>50%% drop):")
        for a in declining[:10]:
            logger.info("  • %-40s early=%d → late=%d (%.0f%%)",
                        a["tag"], a["early_count"], a["late_count"], a["acceleration"] * 100)

    # Cluster emerging tags by co-occurrence to find thematic groups
    logger.info("\n" + "=" * 80)
    logger.info("TAG CO-OCCURRENCE CLUSTERS (potential emerging mega-trends)")
    logger.info("=" * 80)

    top_emerging = set(a["tag"] for a in (emerging_new[:15] + emerging_growing[:15]))
    if top_emerging:
        # Build co-occurrence matrix
        cooccurrence = defaultdict(Counter)
        for t in dated:
            trend_emerging = [tag for tag in t["tags"] if tag in top_emerging]
            for i, t1 in enumerate(trend_emerging):
                for t2 in trend_emerging[i + 1:]:
                    cooccurrence[t1][t2] += 1
                    cooccurrence[t2][t1] += 1

        # Simple greedy clustering of co-occurring tags
        used = set()
        tag_clusters = []
        for tag in top_emerging:
            if tag in used:
                continue
            cluster = {tag}
            used.add(tag)
            for co_tag, count in cooccurrence[tag].most_common(5):
                if co_tag not in used and count >= 2:
                    cluster.add(co_tag)
                    used.add(co_tag)
            if len(cluster) >= 2:
                tag_clusters.append(cluster)

        for i, tc in enumerate(tag_clusters):
            logger.info("  Emerging theme %d: {%s}", i + 1, ", ".join(sorted(tc)))

    return accelerating


# =============================================================================
# Strategy 3: Mega-Trend Momentum Update
# =============================================================================

def run_momentum_update(trends: list[dict], write: bool = False):
    """Calculate momentum for each mega-trend and optionally update mega_trends.yaml."""
    import yaml

    logger.info("\n=== Strategy 3: Mega-Trend Momentum Update ===")

    yaml_path = Path("mega_trends.yaml")
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    mega_trends = data.get("mega_trends", [])

    # Split trends at median publication date
    dated = [t for t in trends if t["published_date"] is not None]
    dates = sorted(t["published_date"] for t in dated)
    median_date = dates[len(dates) // 2]

    early = [t for t in dated if t["published_date"] < median_date]
    late = [t for t in dated if t["published_date"] >= median_date]
    logger.info("Median date: %s, Early: %d, Late: %d", median_date.strftime("%Y-%m-%d"), len(early), len(late))

    early_mt = Counter(t["mega_trend"] for t in early if t["mega_trend"])
    late_mt = Counter(t["mega_trend"] for t in late if t["mega_trend"])

    changes = []
    for mt in mega_trends:
        key = mt["key"]
        e = early_mt.get(key, 0)
        l = late_mt.get(key, 0)
        total = e + l

        e_rate = e / len(early) if early else 0
        l_rate = l / len(late) if late else 0

        if e_rate > 0:
            change = (l_rate - e_rate) / e_rate
        elif l_rate > 0:
            change = float("inf")
        else:
            change = 0

        if change == float("inf"):
            new_momentum = "emerging"
        elif change > 0.3:
            new_momentum = "rising"
        elif change < -0.3:
            new_momentum = "declining"
        else:
            new_momentum = "stable"

        old_momentum = mt.get("momentum", "unknown")
        old_signal_count = mt.get("signal_count", 0)

        mt["momentum"] = new_momentum
        mt["signal_count"] = total

        if old_momentum != new_momentum or old_signal_count != total:
            pct = f"+{change*100:.0f}%" if change != float("inf") else "NEW"
            changes.append((key, old_momentum, new_momentum, old_signal_count, total, pct))
            logger.info("  %s: momentum %s → %s, signals %d → %d (%s)",
                        key, old_momentum, new_momentum, old_signal_count, total, pct)

    if not changes:
        logger.info("No momentum changes detected.")
    else:
        logger.info("\n%d mega-trends with updated momentum/signal_count", len(changes))

    if write and changes:
        # Preserve comments by writing with yaml
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write("# Catandary Mega-Trends Taxonomy\n")
            f.write(f"# Updated: {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write("#\n")
            f.write("# momentum: rising | stable | declining | emerging (data-driven)\n")
            f.write("# cluster_strength: strong | moderate | fragmented (from embedding clustering)\n")
            f.write("# signal_count: total trends assigned to this mega-trend\n\n")
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        logger.info("Written updated mega_trends.yaml")
    elif changes:
        logger.info("[DRY RUN] Would update mega_trends.yaml with %d changes", len(changes))

    return changes


# =============================================================================
# Main
# =============================================================================

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    write_momentum = "--write" in sys.argv
    trends = load_trends()

    if mode in ("clustering", "both"):
        run_clustering(trends)

    if mode in ("temporal", "both"):
        run_temporal(trends)

    if mode in ("momentum", "both"):
        run_momentum_update(trends, write=write_momentum)

    logger.info("\n=== Discovery complete ===")


if __name__ == "__main__":
    main()
