#!/usr/bin/env bash
# Wöchentliche Newsletter-EDITION für die Website (Owner 2026-08-29).
# Cron: 0 9 * * 1 (Montag 09:00).
#
# Generiert die Edition der VORWOCHE und speichert sie in newsletter_editions —
# /trends/newsletter zeigt sie sofort (öffentliche Route, auch unter
# PUBLIC_MODE). Der E-Mail-VERSAND ist bewusst NICHT hier: der bleibt in
# scripts/newsletter_tonight.sh und wartet auf die Launch-Kette (#16,
# NEWSLETTER_GOLIVE.md). Publikation auf der Website hat keine der drei
# Versand-Blocker.
#
# Vorwoche deterministisch statt "aktuelle Woche beim Lauf": am Montag ist die
# laufende ISO-Woche fast leer — %G/%V von vor 7 Tagen liefert immer die
# abgeschlossene Woche (Historie: die KW32-Edition entstand am Mittwoch der
# Folgewoche; dieser Cron macht daraus einen festen Rhythmus). Cron seit
# 2026-09-11 DIENSTAG 09:00 (vorher Montag, Owner-Entscheid) — die Rechnung
# aendert sich dadurch nicht, 'vor 7 Tagen' trifft an beiden Tagen dieselbe
# abgeschlossene ISO-Woche.
#
# Optionaler Schritt „Deep Dive of the Week" (#96, Phase 1): NUR wenn
# NEWSLETTER_DEEP_DIVE=dry-run gesetzt ist (Default off — der Montagslauf
# ändert sich nicht, bis der Owner es in der crontab setzt). Läuft NACH der
# Edition: Rechercheur auf Qwen3.8-27B über den Dossier-Auftragspfad, Gemma-
# Kondensat, danach Ruhezustand (start-active.sh → 8B-208k, llama-server
# aktiv). Schreibt newsletter_editions.deep_dive mit dry_run=true — öffentlich
# nie gerendert. Fehler dort sind nie ein Blocker für die Edition (eigener
# Exit-Code in der end-Zeile: dd=…). Scharfschaltung (--apply) erst nach
# Owner-Blick auf 2–3 Wochen Dry-Run — docs/newsletter_deep_dive.md.

set -u

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

REPO="/home/dirk/projects/catandary-trends"
PY="$REPO/.venv/bin/python"
LOG="/home/dirk/logs/catandary-newsletter-publish-$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG")"
export NEWSLETTER_LLM_BACKEND=llamacpp

YEAR=$(date -d '7 days ago' +%G)
WEEK=$(date -d '7 days ago' +%-V)

{
  echo "================================================================"
  echo "weekly_newsletter_publish.sh start $(date -Iseconds) — Edition ${YEAR}-W${WEEK}"
  echo "================================================================"
  cd "$REPO" || { echo "ABORT: cannot cd $REPO"; exit 1; }
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/ops_events.sh"
  ops_event_start weekly_newsletter_publish "edition=${YEAR}-W${WEEK}"

  # Kollisionswächter: 04:00 startet der Full Cycle — läuft er um 09:00
  # noch (lange Nächte kommen vor), würde der Modell-Swap unten seinen
  # llama-server unter ihm wegziehen. Warten statt kaputt machen (max 90 min).
  # Seit #98 der gemeinsame Helfer (wartet auch auf Ingester/Worker/Pulse).
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/gpu_guard.sh"
  if ! gpu_guard_wait weekly_newsletter_publish; then
    echo "ABORT: fremder GPU-Job nach ${GPU_GUARD_MAX_MIN} min immer noch aktiv — Edition ${YEAR}-W${WEEK} beim nächsten Lauf nachholen"
    ops_event_end 75 "blocked: fremder GPU-Job"
    echo "weekly_newsletter_publish.sh end $(date -Iseconds) (gen=blocked)"
    exit 1
  fi

  # Idempotenz: existiert die Edition schon, nichts tun (Cron-Doppelläufe,
  # manuelle Vorab-Generierung).
  EXISTS=$("$PY" - <<PYEOF
from pipeline.db import get_connection
with get_connection() as c:
    r = c.execute("SELECT count(*) AS n FROM newsletter_editions WHERE year = ? AND week = ?", (${YEAR}, ${WEEK})).fetchone()
    print(r["n"] if isinstance(r, dict) else r[0])
PYEOF
)
  if [ "${EXISTS:-0}" -gt 0 ]; then
    echo "Edition W${WEEK} existiert bereits — nichts zu tun."
    ops_event_end 0 "exists"
    echo "weekly_newsletter_publish.sh end $(date -Iseconds) (gen=exists)"
    exit 0
  fi

  # Content-Engine sicherstellen: Gemma-4-26B auf :8090 (gleicher Swap-Block
  # wie newsletter_tonight.sh / scheduled_cycle.sh — Owner-Entscheidung
  # 2026-08-02 nach A/B auf den W31-Daten).
  MODEL_ID() { curl -sf -m 3 http://127.0.0.1:8090/v1/models \
      | "$PY" -c "import json,sys;print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null; }
  WANT="gemma-4-26B"
  CUR="$(MODEL_ID)"
  if [ -n "$CUR" ] && [[ "$CUR" == *"$WANT"* ]]; then
    echo "----- :8090 already serving the content engine: $CUR -----"
  else
    echo "----- :8090 serving '${CUR:-nothing}' — swapping to $WANT -----"
    systemctl --user stop llama-server.service 2>/dev/null
    sleep 3
    ln -sfn start-gemma4-26b.sh /home/dirk/llama.cpp/start-active.sh \
      || echo "  WARN: symlink swap failed — starting whatever is active"
    systemctl --user start llama-server.service
    for i in $(seq 1 30); do
      sleep 3
      CUR="$(MODEL_ID)"
      [ -n "$CUR" ] && { echo "  :8090 up: $CUR (after $((i*3))s)"; break; }
    done
  fi
  if [ -z "$CUR" ]; then
    echo "ABORT: no model serving on :8090 — refusing to generate"
    ops_event_end 1 "skipped: kein Modell auf :8090"
    echo "weekly_newsletter_publish.sh end $(date -Iseconds) (gen=skipped)"
    exit 1
  fi

  echo "----- generating edition ${YEAR}-W${WEEK} (saves to DB, website only) -----"
  "$PY" -m pipeline.newsletter_generator --year "$YEAR" --week "$WEEK"
  RC=$?

  # ----- optionaler Deep-Dive-Schritt (#96) — Default off ------------------
  DD_RC="off"
  case "${NEWSLETTER_DEEP_DIVE:-off}" in
    dry-run)
      if [ "$RC" -ne 0 ]; then
        echo "----- deep dive skipped: edition generation failed (gen=$RC) -----"
        DD_RC="skipped"
      else
        echo "----- deep dive (dry-run) for ${YEAR}-W${WEEK}: 27B research → Gemma condensate → resting state -----"
        "$PY" -m scripts.newsletter_deep_dive --year "$YEAR" --week "$WEEK" --dry-run
        DD_RC=$?
        echo "----- deep dive exit code: $DD_RC (never blocks the edition) -----"
        echo "----- resting state: start-active.sh → $(readlink /home/dirk/llama.cpp/start-active.sh 2>/dev/null), llama-server $(systemctl --user is-active llama-server.service 2>/dev/null) -----"
      fi
      ;;
    off|"") ;;
    *) echo "WARN: NEWSLETTER_DEEP_DIVE='${NEWSLETTER_DEEP_DIVE}' unknown (dry-run|off) — step skipped"; DD_RC="skipped" ;;
  esac

  ops_event_end "$RC" "dd=$DD_RC"
  echo "weekly_newsletter_publish.sh end $(date -Iseconds) (gen=$RC dd=$DD_RC)"
  exit "$RC"
} >> "$LOG" 2>&1
