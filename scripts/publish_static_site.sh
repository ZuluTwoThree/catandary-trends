#!/usr/bin/env bash
# Täglicher Publish des statischen Exports auf den Webspace (Schritt 8 des
# Designs docs/audits/2026-09-02_static_export_design.md; Betrieb in
# docs/launch/HOSTING_HETZNER.md, „Statischer Export — Publish").
# Cron: 15 3 * * *  — täglich, rund 45 min VOR dem 04:00-Cycle (Owner 05.09.):
# veröffentlicht wird der Stand nach einem vollen Review-Tag, nie frische
# unbeurteilte Artikel. Am Wochenende läuft kein Cycle, das 30-Tage-Fenster
# rollt aber weiter — abgelaufene Artikel müssen trotzdem raus.
#
# Ablauf: Kollisionswächter (Full Cycle) → build_public_static.sh →
# publish_static_site.py --apply. Bewusst NICHT in full_cycle_cron.sh
# eingehängt, damit ein Export-Fehler den Cycle-Exit-Code nicht verfälscht.
# Der Wächter (scripts/cycle_watchdog.py, 07:45) liest data/publish_last.json.
#
# Ohne ~/.config/catandary/webspace.env (SFTP-Zugang aus konsoleH, chmod 600)
# tut das Skript nichts — kein Build, keine Mail: es gibt noch kein Ziel.

set -u

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

# node/npm liegen unter nvm und stehen in cron NICHT im PATH — der erste
# Cron-Lauf (2026-09-06 03:15) brach nach 0 s mit "node: Befehl nicht gefunden"
# ab (rc=127). nvm laedt eine Login-Shell, cron nicht: deshalb den aktiven
# nvm-Pfad direkt aufnehmen (Version aus ~/.nvm/alias/default, sonst die
# hoechste installierte).
if ! command -v node >/dev/null 2>&1; then
  for d in "$HOME/.nvm/versions/node"/*/bin; do [ -x "$d/node" ] && NODE_BIN="$d"; done
  [ -n "${NODE_BIN:-}" ] && export PATH="$NODE_BIN:$PATH"
fi
command -v node >/dev/null 2>&1 || { echo "ABBRUCH: node nicht gefunden (PATH=$PATH)"; exit 2; }

REPO="${PUBLISH_REPO:-/home/dirk/projects/catandary-trends}"
PY="$REPO/.venv/bin/python"
CONFIG="${PUBLISH_CONFIG:-$HOME/.config/catandary/webspace.env}"
LOG="${PUBLISH_LOG:-/home/dirk/logs/catandary-publish-$(date +%Y%m%d).log}"
LOCK="/home/dirk/logs/.catandary-publish.lock"
mkdir -p "$(dirname "$LOG")"

{
  echo "================================================================"
  echo "publish_static_site.sh start $(date -Iseconds)"
  echo "================================================================"
  cd "$REPO" || { echo "ABORT: cannot cd $REPO"; echo "publish_static_site.sh end $(date -Iseconds) (rc=1)"; exit 1; }
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/ops_events.sh"
  ops_event_start publish_static_site

  if [ ! -f "$CONFIG" ]; then
    echo "skip: no webspace config at $CONFIG — nothing to publish to (create it: HOSTING_HETZNER.md)"
    ops_event_end 0 "skipped: keine Webspace-Config"
    echo "publish_static_site.sh end $(date -Iseconds) (rc=0 skipped)"
    exit 0
  fi

  # Ein Publish zur Zeit (Cron + Handstart dürfen sich nicht überholen).
  exec 9>"$LOCK"
  if ! flock -n 9; then
    echo "ABORT: another publish is running (lock $LOCK)"
    ops_event_end 1 "locked: anderer Publish laeuft"
    echo "publish_static_site.sh end $(date -Iseconds) (rc=1)"
    exit 1
  fi

  # Kollisionswächter: läuft der 04:00-Full-Cycle noch (lange Nächte kommen
  # vor), wäre der Export unvollständig — die Auto-Publish-Stufe hat die
  # Artikel des Tages noch nicht freigegeben. Warten statt halb exportieren
  # (max 90 min, wie weekly_newsletter_publish.sh).
  for i in $(seq 1 90); do
    pgrep -f "scheduled_cycle.sh|full_cycle_cron.sh" >/dev/null || break
    [ "$i" -eq 1 ] && echo "Full Cycle läuft noch — warte (max 90 min) ..."
    sleep 60
  done
  if pgrep -f "scheduled_cycle.sh|full_cycle_cron.sh" >/dev/null; then
    echo "ABORT: Full Cycle nach 90 min immer noch aktiv — Publish heute ausgelassen"
    ops_event_end 1 "blocked: Full Cycle"
    echo "publish_static_site.sh end $(date -Iseconds) (rc=1 blocked)"
    exit 1
  fi

  # Build-Parameter dürfen in der Webspace-Config stehen (PUBLIC_NOINDEX=0 ist
  # der Launch-Schalter am 01.10., PUBLIC_WINDOW_DAYS das Fenster). Nur diese
  # zwei Schlüssel werden übernommen — die Datei wird nicht gesourct
  # (Passwörter mit Sonderzeichen).
  for key in PUBLIC_NOINDEX PUBLIC_WINDOW_DAYS PUBLIC_SITE_URL; do
    val=$(grep -E "^${key}=" "$CONFIG" | tail -1 | cut -d= -f2- | sed -e "s/^['\"]//" -e "s/['\"]\$//" -e 's/[[:space:]]*#.*$//')
    if [ -n "$val" ]; then export "$key=$val"; echo "build env: $key=$val"; fi
  done

  echo "----- build: scripts/build_public_static.sh -----"
  bash "$REPO/scripts/build_public_static.sh"
  RC=$?
  if [ "$RC" -ne 0 ]; then
    echo "ABORT: build failed (rc=$RC) — nothing uploaded, yesterday's site stays online"
    # Fehlschlag ins Summary schreiben, sonst steht dort der ERFOLG von gestern
    # und der Waechter meldet nichts (2026-09-06: Build brach an fehlendem node
    # ab, publish_last.json blieb auf "ok", niemand erfuhr davon).
    printf '{"status":"build-failed","uploaded":0,"deleted":0,"unchanged":0,"errors":1,"rc":%s,"finished_at":"%s","note":"build_public_static.sh failed — see the log"}\n' \
      "$RC" "$(date -Iseconds)" > "$REPO/data/publish_last.json"
    ops_event_end "$RC" "build failed"
    echo "publish_static_site.sh end $(date -Iseconds) (rc=$RC build)"
    exit "$RC"
  fi

  echo "----- publish: scripts/publish_static_site.py --apply -----"
  "$PY" "$REPO/scripts/publish_static_site.py" --apply --config "$CONFIG" \
    --out "$REPO/frontend/.export/out" --log-file -
  RC=$?
  ops_event_end "$RC"
  echo "publish_static_site.sh end $(date -Iseconds) (rc=$RC)"
  exit "$RC"
} >> "$LOG" 2>&1
