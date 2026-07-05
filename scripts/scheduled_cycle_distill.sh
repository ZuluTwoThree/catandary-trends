#!/usr/bin/env bash
# EXPERIMENTAL distill-backed pipeline cycle (test alternative to scheduled_cycle.sh).
#
# Replaces the per-entry 8B LLM stages (relevance / extraction / classification)
# with the embedding-head fast path validated by the mass backfill:
#
#   0. WATERMARK = max(raw_entries.id) before polling — the cycle only touches
#      freshly polled entries, never a backfill backlog.
#   1. Poll RSS feeds (no GPU).
#   2. run_distill_batch --min-id WATERMARK: one batched embedding pass (GPU via
#      handover) + linear heads (CPU) → relevance gate → dedup →
#      status='signal' rows. ~10× faster than the 8B path.
#   3. generate_content --since <cutoff>: EN articles for the fresh signals
#      (llama.cpp 30B via its own handover + VRAM pre-flight), promotes to
#      published/draft.
#
# Differences vs. the classic cycle (accepted for the test):
#   - no entity extraction (brands/companies stay empty on distill signals)
#   - tags empty; trend_signal_type derived from the source deterministically
#   - classification quality = head accuracy (vertical 85%, mega 78% top-1,
#     PESTEL 84% F1) instead of 8B-LLM quality
#
# Usage: scripts/scheduled_cycle_distill.sh [content_limit]   (default 150)

set -uo pipefail

REPO="/home/dirk/projects/catandary-trends"
PY="$REPO/.venv/bin/python"
CONTENT_LIMIT="${1:-150}"
LOG="/home/dirk/logs/catandary-distill-cycle-$(date +%Y%m%d-%H%M).log"
SINCE="$(date -d '2 days ago' +%Y-%m-%d)"

cd "$REPO"
exec >>"$LOG" 2>&1
echo "===== distill cycle start $(date '+%F %T') (content_limit=$CONTENT_LIMIT) ====="

WATERMARK=$($PY -c "
from pipeline.db import get_connection
with get_connection() as c:
    r = c.execute('SELECT COALESCE(MAX(id),0) AS m FROM raw_entries').fetchone()
    print(r['m'] if isinstance(r, dict) else r[0])")
echo "----- watermark: raw_entries.id > $WATERMARK -----"

echo "----- 1/3 poll feeds -----"
$PY -m pipeline.feed_poller

echo "----- 2/3 distill classification (embed + heads, min-id $WATERMARK) -----"
$PY scripts/run_distill_batch.py --min-id "$WATERMARK" --limit 0

echo "----- 3/3 content generation for fresh signals (since $SINCE) -----"
$PY scripts/generate_content.py --since "$SINCE" --limit "$CONTENT_LIMIT"

echo "===== distill cycle done $(date '+%F %T') ====="
