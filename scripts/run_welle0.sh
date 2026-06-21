#!/usr/bin/env bash
# Welle 0 — Pilot/E2E-Gate for the cross-vertical signal backfill (Option 3).
#
# Scope: all 8 verticals, window 2024-01-01..2025-01-01, channels WP + OpenAlex
# (sitemap skipped — weak/undated). Acquisition writes dated raw_entries
# (processed=0); then the signal-mode pipeline classifies them via the Anthropic
# Haiku backend (off-GPU) + local Ollama embeddings, inserting status='signal'
# rows (no article). Content-gen stays decoupled (scripts/generate_content.py).
#
# MUST run only AFTER the normal pipeline run has fully drained its backlog,
# otherwise scheduled_cycle's run-2 would process these entries with the normal
# LOCAL pipeline instead of signal-mode + Haiku. The watcher enforces this.
#
# GPU: signal-mode needs local Ollama embeddings (~6 GB). llama-server (~20 GB)
# is stopped first to free VRAM, then restarted at the end (ensure-VRAM rule).

set -u
REPO="/home/dirk/projects/catandary-trends"
AFTER="2024-01-01"
BEFORE="2025-01-01"
LOG="/home/dirk/logs/welle0-$(date +%Y%m%d-%H%M).log"
mkdir -p "$(dirname "$LOG")"

{
  echo "================================================================"
  echo "run_welle0.sh start  $(date -Iseconds)"
  echo "  window : $AFTER .. $BEFORE   channels: WP + OpenAlex (all verticals)"
  echo "  log    : $LOG"
  echo "================================================================"

  cd "$REPO" || { echo "ABORT: cannot cd to $REPO"; exit 1; }
  # shellcheck disable=SC1091
  source .venv/bin/activate

  # Classification backend = Anthropic Haiku (decision from docs/phase5_decision.md).
  # Leave EMBED/STAGE backends at their Ollama defaults so embeddings run locally
  # on the freed GPU and no llama.cpp handover is attempted.
  export CLASSIFY_BACKEND=anthropic
  export ANTHROPIC_MODEL_CLASSIFY="${ANTHROPIC_MODEL_CLASSIFY:-claude-haiku-4-5}"

  echo
  echo "----- backlog BEFORE ingest (must be ~0; else normal run not finished) -----"
  python - <<'PY'
from pipeline.db import get_unprocessed_entries, init_db
init_db()
print("unprocessed:", len(get_unprocessed_entries(limit=999999)))
PY

  # Watermark before ingest so the per-source signal-yield eval at the end scopes
  # exactly to this batch (raw_entries.id > WATERMARK), not historical entries.
  WATERMARK=$(python - <<'PY'
from pipeline.db import get_connection
with get_connection() as c:
    print(c.execute("SELECT COALESCE(MAX(id),0) FROM raw_entries").fetchone()[0])
PY
)
  echo "----- ingest watermark (raw_entries.id): $WATERMARK -----"

  echo
  echo "----- DRY-RUN volume probe (WP) -----"
  python scripts/ingest_backfill.py --after "$AFTER" --before "$BEFORE" --only WP --dry-run
  echo
  echo "----- DRY-RUN volume probe (OpenAlex) -----"
  python scripts/ingest_backfill.py --after "$AFTER" --before "$BEFORE" --only ACADEMIC --dry-run

  echo
  echo "----- REAL ingest: WP REST API (all verticals) -----"
  python scripts/ingest_backfill.py --after "$AFTER" --before "$BEFORE" --only WP
  echo
  echo "----- REAL ingest: OpenAlex (academic sources) -----"
  python scripts/ingest_backfill.py --after "$AFTER" --before "$BEFORE" --only ACADEMIC

  NEW=$(python - <<'PY'
from pipeline.db import get_unprocessed_entries, init_db
init_db()
print(len(get_unprocessed_entries(limit=999999)))
PY
)
  echo
  echo "----- ingested (unprocessed now): $NEW -----"

  if [ "${NEW:-0}" -le 0 ]; then
    echo "no new entries → nothing to classify. Done."
    echo "run_welle0.sh end  $(date -Iseconds)"
    exit 0
  fi

  echo
  echo "----- stopping llama-server.service to free GPU for Ollama embeddings -----"
  systemctl --user stop llama-server.service
  for i in 1 2 3 4 5 6 7 8; do
    sleep 2
    USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    echo "  [${i}] VRAM used: ${USED} MiB"
    if [ "${USED:-9999}" -lt 1500 ]; then break; fi
  done

  echo
  echo "----- signal-mode classification (Haiku, batch=$NEW) -----"
  CLASSIFY_BACKEND=anthropic python -m pipeline.llm_processor "$NEW" --signal-mode
  RC=$?
  echo "----- signal-mode exit code: $RC -----"

  echo
  echo "----- restarting llama-server.service -----"
  systemctl --user start llama-server.service

  echo
  echo "----- result: status='signal' rows -----"
  python - <<'PY'
from pipeline.db import get_connection
with get_connection() as c:
    n = c.execute("SELECT COUNT(*) FROM trends WHERE status='signal'").fetchone()[0]
    print("signal rows total:", n)
    rows = c.execute(
        "SELECT primary_vertical, COUNT(*) FROM trends WHERE status='signal' "
        "GROUP BY primary_vertical ORDER BY 2 DESC").fetchall()
    for v, cnt in rows:
        print(f"  {v or '?':10} {cnt}")
PY

  echo
  echo "----- per-source signal yield (this batch, id > $WATERMARK) -----"
  python scripts/source_signal_yield.py --min-id "${WATERMARK:-0}" \
    --out "${LOG%.log}-yield.txt"

  echo
  echo "run_welle0.sh end  $(date -Iseconds)  (rc=$RC)"
} >> "$LOG" 2>&1
