#!/usr/bin/env bash
# Scheduled Catandary pipeline run for off-hours use on ki-workstation.
#
# Sequence:
#   0. Capture a watermark (max raw_entries.id) BEFORE polling. Both runs below
#      are scoped to id > WATERMARK (--min-id), so the cycle only processes the
#      freshly-polled entries and never drains an unrelated backfill backlog that
#      shares the unprocessed pool (the multi-year signal backfill is classified
#      separately by signal_batch).
#   1. Run full cycle (poll + LLM) with the given batch size (default 600).
#   2. If fresh entries remain (id > WATERMARK), run a second cycle (--skip-poll)
#      sized to drain that fresh backlog in one go.
#   3. Always start llama-server.service at the end so the fcc-stack is
#      available again after the off-hours window.
#
# The script stops llama-server.service BEFORE running so Ollama
# (qwen3:14b 9.3 GB + qwen3:8b 5.2 GB) gets the full GPU. The fcc
# llama-server (~22 GB) and Ollama models cannot share VRAM on the
# RTX 3090. llama-server is restarted at the end regardless of outcome.
#
# Usage:
#   scripts/scheduled_cycle.sh [BATCH]    # default BATCH=600
#
# Logs go to ~/logs/catandary-scheduled-<YYYYMMDD-HHMM>.log

set -u

REPO="/home/dirk/projects/catandary-trends"

# >>> Signaltyp-Head (#110, Owner 25.09.2026) >>>
# Fünfter Distill-Head: Presse-Signale bekommen product_launch / regulation /
# partnership / consumer_behavior / market_shift aus dem Embedding statt pauschal
# market_shift (Regression seit 14.07.). Greift nur, wenn models/distill/
# signal_type.joblib im Worktree liegt (sonst wie bisher); Konfidenz-Boden 0,6
# (docs/signal_type_head_2026-09-25.md). Abschalten: Zeile entfernen oder =0.
export DISTILL_SIGNAL_TYPE=1
# <<< Signaltyp-Head <<<
BATCH="${1:-600}"
LOG="/home/dirk/logs/catandary-scheduled-$(date +%Y%m%d-%H%M).log"
mkdir -p "$(dirname "$LOG")"

{
  echo "================================================================"
  echo "scheduled_cycle.sh start  $(date -Iseconds)"
  echo "  repo  : $REPO"
  echo "  batch : $BATCH"
  echo "  log   : $LOG"
  echo "================================================================"

  cd "$REPO" || { echo "ABORT: cannot cd to $REPO"; exit 1; }
  # shellcheck disable=SC1091
  source .venv/bin/activate

  # >>> Stage-6 content generation on llama.cpp 35B — `git revert` this commit to disable >>>
  # Activates the llama.cpp backend ONLY if start-active.sh actually loads the
  # expected GGUF (so the mid-pipeline GPU handover reloads exactly that model and
  # fits VRAM). Otherwise fall back to Ollama 14B — no crash, no symlink mutation.
  # Content gen ALWAYS attempts the 35B, regardless of which model (or none) is
  # loaded at pipeline start: content_gen_on_llamacpp swaps start-active.sh to the
  # 35B start script for the duration of Stage 6 and restores it afterwards. We
  # therefore gate only on the 35B START SCRIPT existing and referencing the
  # expected GGUF — not on start-active.sh's current target. Fall back to Ollama
  # only if that start script is missing/misconfigured (avoids a hard crash).
  # Model choice (#11, 2026-07-14): switched 30B → Gemma-4-26B-A4B after a
  # controlled A/B (same entries/prompt/temp, only the model swaps; n=70 across
  # two runs, Fisher p=0.013):
  #   qwen3-30b   32.9% of bodies invent a specific · 0.65 invented tokens · 145 words
  #   gemma4-26b   8.6% ·············································· 0.10 ······ 175 words
  # Four other levers were refuted first (prompt prohibition, re-roll, full text,
  # temperature) — fabrication is MODEL-specific. Qwen invented e.g. a fake city
  # law ("Ordinance 2023-47") to satisfy the concreteness mandate; Gemma reports
  # the source's real specifics and lands inside the 150-250 word target the 30B
  # undershoots. Revert = point these two back at the 30B (both registered in
  # gpu_handover.MODEL_START_SCRIPTS).
  export STAGE5_MODEL="gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"
  STAGE5_START="/home/dirk/llama.cpp/start-gemma4-26b-ctx16k.sh"
  if [ -f "$STAGE5_START" ] && grep -q "$STAGE5_MODEL" "$STAGE5_START" 2>/dev/null; then
    export STAGE5_BACKEND=llamacpp
    echo "----- Stage-6 backend: llamacpp ($STAGE5_MODEL), handover swaps symlink to 30B -----"
  else
    export STAGE5_BACKEND=ollama
    echo "----- Stage-6 backend: ollama (fallback — $STAGE5_START missing or wrong GGUF) -----"
  fi
  # <<< Stage-6 activation <<<

  # >>> Stages 2/3/4/8 on llama.cpp 8B — `git revert` this commit to disable >>>
  # Activates the llama.cpp 8B backend for the four qwen3:8b stages ONLY if the
  # 8B start script exists and references the expected GGUF. The pipeline's
  # in-run eight_b_on_llamacpp handover swaps the symlink to the 208K/24-slot
  # start script (start-qwen3-8b-208k.sh) before Stages 2-4 and Stage 8 and
  # restores it afterwards — phase 2-4 then runs parallel (CLASSIFY_WORKERS=24).
  # Fail-safe: missing script or wrong GGUF reference → fall back to Ollama.
  export STAGE_8B_MODEL="Qwen3-8B-UD-Q4_K_XL.gguf"
  # 2048 statt Default 1024: die richer extraction (#11) sprengt bei langen
  # Volltexten sonst das Token-Limit → JSON-Truncation, 3 verlorene Retries
  # (14× im Cron-Lauf 2026-07-29).
  export LLAMACPP_MAX_TOKENS=2048
  ACTIVE_8B="/home/dirk/llama.cpp/start-qwen3-8b-208k.sh"
  if [ -f "$ACTIVE_8B" ] && grep -q "$STAGE_8B_MODEL" "$ACTIVE_8B" 2>/dev/null; then
    export STAGE_8B_BACKEND=llamacpp
    echo "----- Stages 2/3/4/8 backend: llamacpp ($STAGE_8B_MODEL) -----"
  else
    export STAGE_8B_BACKEND=ollama
    echo "----- Stages 2/3/4/8 backend: ollama (fallback — $ACTIVE_8B missing or wrong GGUF) -----"
  fi
  # <<< Stage 8B activation <<<

  # >>> Stage 5 Embedding on llama.cpp — `git revert` this commit to disable >>>
  # Activates the llama.cpp embedding backend ONLY if the embedding start
  # script exists and references the expected GGUF. The in-pipeline
  # embed_on_llamacpp handover swaps the symlink to start-qwen3-emb.sh
  # for Stage 5 and restores it afterwards.
  # Fail-safe: missing script or wrong GGUF reference → fall back to Ollama.
  export EMBED_MODEL="Qwen3-Embedding-8B-Q4_K_M.gguf"
  ACTIVE_EMB="/home/dirk/llama.cpp/start-qwen3-emb.sh"
  if [ -f "$ACTIVE_EMB" ] && grep -q "$EMBED_MODEL" "$ACTIVE_EMB" 2>/dev/null; then
    export EMBED_BACKEND=llamacpp
    echo "----- Stage 5 backend: llamacpp ($EMBED_MODEL) -----"
  else
    export EMBED_BACKEND=ollama
    echo "----- Stage 5 backend: ollama (fallback — $ACTIVE_EMB missing or wrong GGUF) -----"
  fi
  # <<< Stage 5 Embed activation <<<

  # Kollisionswächter (#98, seit 2026-09-05): läuft ein fremder GPU-Job
  # (Samstags-Ingester, Dossier-Worker, Pulse, Deep Dive, zweiter Cycle …),
  # würde das Stoppen der Unit hier seinen Server unter ihm wegziehen. Warten
  # (max GPU_GUARD_MAX_MIN=90 min), sonst Abbruch OHNE etwas anzufassen.
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/gpu_guard.sh"
  if ! gpu_guard_wait scheduled_cycle; then
    echo "ABORT: fremder GPU-Job nach ${GPU_GUARD_MAX_MIN} min immer noch aktiv — Cycle nicht gestartet, nichts angefasst"
    echo "scheduled_cycle.sh end  $(date -Iseconds)  (rc1=75 rc2=0 rc3=0 blocked)"
    exit 75
  fi

  echo
  echo "----- stopping llama-server.service to free GPU -----"
  systemctl --user stop llama-server.service
  # Give the GPU a moment to release VRAM before Ollama loads qwen3:14b
  for i in 1 2 3 4 5 6 7 8; do
    sleep 2
    USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    echo "  [${i}] VRAM used: ${USED} MiB"
    if [ "${USED:-9999}" -lt 1500 ]; then break; fi
  done

  # Watermark: max raw_entries.id BEFORE the poll. Both runs are scoped to
  # id > WATERMARK so the cycle only processes freshly-polled entries and never
  # picks up an unrelated backfill backlog that shares the unprocessed pool
  # (the multi-year signal backfill is classified separately by signal_batch).
  echo
  # Patents are now excluded at the source (get_unprocessed_entries filters
  # pub_number IS NULL), so the cycle can safely process the whole non-patent
  # unprocessed pool with min_id=0 — the old watermark-vs-backfill dance is no
  # longer needed (and was broken: the RSS ids overlap the backfill's, so no
  # min_id could separate them). WATERMARK stays 0.
  WATERMARK=0
  # SANITY GUARD: count the non-patent unprocessed backlog. A normal off-hours
  # gap is dozens–hundreds; anything above 50k means something unexpected merged
  # into the RSS pool — refuse rather than content-gen tens of thousands.
  PENDING=$(python - <<'PY'
from pipeline.config import CYCLE_MAX_PER_SOURCE
from pipeline.db import get_connection
# Counts the INTAKE a run would actually feed to content generation — the
# per-source cap applied, exactly like get_unprocessed_entries. Owner rule
# 2026-08-20: a mass ingest must not abort the whole night (235k SBIR/CORDIS
# rows did); it now contributes at most CYCLE_MAX_PER_SOURCE entries per run
# and the rest waits for signal_batch, so this count stays honest AND small.
with get_connection() as c:
    r = c.execute(
        "WITH ranked AS (SELECT ROW_NUMBER() OVER ("
        "  PARTITION BY re.source_id ORDER BY re.fetched_at, re.id) AS rn "
        "  FROM raw_entries re JOIN sources s ON re.source_id = s.id "
        "  WHERE re.processed=FALSE AND re.filtered_out=FALSE "
        "  AND re.pub_number IS NULL "
        "  AND COALESCE(s.llm_pipeline, TRUE) = TRUE) "
        "SELECT COUNT(*) AS n FROM ranked WHERE rn <= ?",
        (CYCLE_MAX_PER_SOURCE,)).fetchone()
    print(r["n"] if isinstance(r, dict) else r[0])
PY
)
  PENDING="${PENDING:-0}"
  echo "----- non-patent unprocessed backlog: $PENDING -----"
  if [ "${PENDING}" -gt 50000 ]; then
    echo "ABORT: $PENDING pending non-patent entries exceeds the 50k sanity cap — refusing."
    ln -sf start-qwen3-8b-208k.sh /home/dirk/llama.cpp/start-active.sh
    systemctl --user reset-failed llama-server.service 2>/dev/null || true  # start limit (gpu_handover.unit_start)
    systemctl --user start llama-server.service
    exit 1
  fi

  echo
  echo "----- run 1: full cycle (poll + LLM), batch $BATCH, min_id $WATERMARK -----"
  python -m pipeline.run_full_cycle --batch "$BATCH" --min-id "$WATERMARK"
  RC1=$?
  echo "----- run 1 exit code: $RC1 -----"

  # Remaining backlog = freshly-polled entries (id > WATERMARK) not yet done in
  # run 1 — NOT the backfill. Drained by run 2, still scoped to the watermark.
  # Entries run 1 left garbled (Stage 6, cycle_log.jsonl garbled_ids) do not
  # count: retrying them costs the same failed generations plus two ~20-min
  # reclassify passes (2026-09-09: one entry, four passes, 1.5 h). The batch
  # is still sized to the whole pool so they cannot crowd out real entries.
  read -r UNPROCESSED UNPROCESSED_TOTAL <<<"$(WATERMARK="$WATERMARK" python - <<'PY'
import os
from pipeline.run_full_cycle import remaining_backlog
retryable, total = remaining_backlog(int(os.environ["WATERMARK"]))
print(retryable, total)
PY
)"
  UNPROCESSED="${UNPROCESSED:-0}"; UNPROCESSED_TOTAL="${UNPROCESSED_TOTAL:-0}"
  echo
  echo "----- backlog after run 1 (id > $WATERMARK): $UNPROCESSED_TOTAL unprocessed, $UNPROCESSED retryable -----"

  RC2=0
  if [ "$UNPROCESSED" -gt 0 ]; then
    echo
    echo "----- run 2: drain fresh backlog (--skip-poll), batch $UNPROCESSED_TOTAL, min_id $WATERMARK -----"
    python -m pipeline.run_full_cycle --skip-poll --batch "$UNPROCESSED_TOTAL" --min-id "$WATERMARK"
    RC2=$?
    echo "----- run 2 exit code: $RC2 -----"
  elif [ "$UNPROCESSED_TOTAL" -gt 0 ]; then
    echo "backlog consists only of entries Stage 6 left garbled in run 1 → skipping run 2"
  else
    echo "no fresh backlog → skipping run 2"
  fi

  # >>> Stage 10: Draft-Richter auf dem lokalen 27B (Owner 2026-08-22) >>>
  # Beurteilt die frischen Drafts UNTER der Auto-Publish-Schwelle nach den
  # Kriterien der Haiku-Volldurchsicht (71,6 % davon sind publizierbar) und gibt
  # frei oder haelt zurueck — verworfen wird nie. Jede Freigabe laeuft durch
  # dieselben deterministischen Gates wie der Auto-Publisher (Grounding,
  # Truncation, Dedup gegen Published). Zahlen landen in
  # data/draft_judge_last.json und damit in der Morgen-Mail.
  # Abschalten: DRAFT_JUDGE=0. Dauer: ~340 Artikel x ~2-3 s auf --parallel 1.
  if [ "${DRAFT_JUDGE:-1}" = "1" ] && ! gpu_guard_wait scheduled_cycle-judge 30; then
    # Ein fremder GPU-Job (z. B. ein vom Owner gestarteter Dossier-Worker) hat
    # sich während der Stages eingeklinkt — sein Server bleibt stehen (#98).
    echo
    echo "----- draft judge SKIPPED: fremder GPU-Job aktiv (Stage-10-Stop würde ihn treffen) -----"
  elif [ "${DRAFT_JUDGE:-1}" = "1" ]; then
    echo
    echo "----- stage 10: draft judge on Qwen3.8-27B -----"
    systemctl --user stop llama-server.service 2>/dev/null
    sleep 3
    # VRAM-Vorab-Check (2026-08-26): das 27B belegt ~23.4 von 24.6 GB — schon
    # ~1.1 GB Fremdbelegung kippen den Start in den OOM (Unsloth-Vorfall
    # 26.08: 20.8 GB resident -> 240s-Timeout-Kaskade statt klarer Diagnose).
    JUDGE_VRAM_OK=0
    for i in $(seq 1 8); do
      VRAM_USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
      if [ -n "$VRAM_USED" ] && [ "$VRAM_USED" -lt 1100 ]; then JUDGE_VRAM_OK=1; break; fi
      echo "  [$i/8] VRAM belegt: ${VRAM_USED:-?} MiB (27B braucht <1100 frei-Rest) — warte"
      sleep 5
    done
    if [ "$JUDGE_VRAM_OK" != "1" ]; then
      echo "----- draft judge SKIPPED: VRAM von Fremdprozess belegt (${VRAM_USED:-?} MiB) -----"
    else
      ln -sf start-qwen3.8-27b-ctx16k.sh /home/dirk/llama.cpp/start-active.sh
      systemctl --user reset-failed llama-server.service 2>/dev/null || true  # start limit (gpu_handover.unit_start)
      systemctl --user start llama-server.service
      # Besitzvermerk (#98 c): data/llama-server.scheduled_cycle-judge.pid —
      # der Stop nach dem Richter trifft nur noch DIESEN Server (MainPID-Abgleich).
      llama_unit_record_owner scheduled_cycle-judge
      JUDGE_UP=0
      for i in $(seq 1 40); do
        sleep 3
        curl -sf -m 3 http://127.0.0.1:8090/v1/models >/dev/null 2>&1 && { JUDGE_UP=1; break; }
      done
      if [ "$JUDGE_UP" = "1" ]; then
        # Identitäts-Check (2026-08-26): llama-server ignoriert den model-Namen
        # im Request und antwortet mit dem geladenen Modell — ein fehlgeschlagener
        # Symlink-Swap ließe den Richter stillschweigend auf dem 8B urteilen.
        SERVED=$(curl -s -m 3 http://127.0.0.1:8090/v1/models 2>/dev/null)
        if echo "$SERVED" | grep -q "Qwen3.8-27B"; then
          python -m pipeline.draft_judge --since-hours 30
          RCJ=$?
          echo "----- draft judge exit code: $RCJ -----"
        else
          echo "----- draft judge SKIPPED: falsches Modell geladen ($SERVED) -----"
        fi
      else
        echo "----- draft judge SKIPPED: 27B server came not up -----"
      fi
      llama_unit_stop_owned scheduled_cycle-judge 2>/dev/null
      sleep 3
    fi
  fi
  # <<< Stage 10 <<<

  # >>> Stage 11: Review-Agent (Owner 2026-09-22) >>>
  # Prueft die Drafts, die ein Gate zurueckhaelt, auf AEQUIVALENZ statt auf
  # Wortgleichheit: ist die beanstandete Zahl dieselbe Angabe in anderer Form
  # ("1 000" / "1,000", "Seventy percent" / "70%", eine japanische Schreibung)
  # und nennt die Quelle die Person wirklich? Jede Bestaetigung braucht ein
  # WOERTLICHES Quellzitat, das gegen den Quelltext geprueft wird — das Modell
  # kann nur bestaetigen, was dasteht. Ergaenzte Vornamen werden korrigiert und
  # das Ergebnis durch dieselben Gates geschickt wie das Auto-Publish.
  # Rollen-Halluzinationen ("the Foreign Secretary" -> ein Name aus dem
  # Modellwissen), fehlende Personen und abweichende Schreibweisen bleiben beim
  # Menschen und stehen als Vorschlag auf /trends/review.
  # Messung 22.09.: von 183 Holds 100 aequivalent, danach 15 weitere repariert.
  # Abschalten: REVIEW_AGENT=0. Nur pruefen, nichts schreiben: REVIEW_AGENT_APPLY=0.
  # Dauer: ~1,5 s je Draft plus einmal Modell laden.
  if [ "${REVIEW_AGENT:-1}" != "1" ]; then
    echo
    echo "----- stage 11: review agent DISABLED (REVIEW_AGENT=0) -----"
  elif ! gpu_guard_wait scheduled_cycle-agent 30; then
    echo
    echo "----- review agent SKIPPED: fremder GPU-Job aktiv -----"
  else
    echo
    echo "----- stage 11: review agent (Aequivalenz-Pruefung der gehaltenen Drafts) -----"
    AGENT_ARGS="--handover -q"
    [ "${REVIEW_AGENT_APPLY:-1}" = "1" ] && AGENT_ARGS="$AGENT_ARGS --apply"
    # shellcheck disable=SC2086
    GPU_JOB_NAME=scheduled_cycle-agent "$REPO/.venv/bin/python" "$REPO/scripts/review_agent.py" $AGENT_ARGS
    RCA=$?
    echo "----- review agent exit code: $RCA -----"
  fi
  # <<< Stage 11 <<<

  echo
  # Force the symlink back to the canonical 208K classifier before the final start.
  # A hard-killed mid-cycle handover (OOM/SIGKILL) can leave start-active.sh on a
  # transient script (emb/30B/35B); without this reset the final `systemctl start`
  # would bring up the wrong model and the next consumer (signal_batch/cycle) would
  # run against it. See pipeline.gpu_handover CANONICAL_RESTING_SCRIPT.
  # Ausnahme (#98): hält inzwischen ein fremder GPU-Job die Unit, gehört ihm
  # der Ruhezustand — er stellt ihn beim eigenen Exit selbst her. Nicht anfassen.
  if BUSY=$(gpu_guard_busy); then
    echo "----- resting state NOT restored: fremder GPU-Job aktiv (stellt ihn selbst her) -----"
    echo "$BUSY" | sed 's/^/    /'
    RC3=0
  else
    echo "----- resetting start-active.sh → start-qwen3-8b-208k.sh -----"
    ln -sf start-qwen3-8b-208k.sh /home/dirk/llama.cpp/start-active.sh
    echo "----- restarting llama-server.service -----"
    systemctl --user reset-failed llama-server.service 2>/dev/null || true  # start limit (gpu_handover.unit_start)
    systemctl --user start llama-server.service
    RC3=$?
    echo "----- llama-server start exit code: $RC3 -----"
  fi

  echo
  echo "scheduled_cycle.sh end  $(date -Iseconds)  (rc1=$RC1 rc2=$RC2 rc3=$RC3 agent=${RCA:--})"
} >> "$LOG" 2>&1
