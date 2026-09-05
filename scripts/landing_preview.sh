#!/usr/bin/env bash
# Vorschau der oeffentlichen Landing (docs/launch/preview.html) vor dem Upload.
#
# Warum eigen: die App-Landing wurde am 2026-09-05 durch eine Weiterleitung auf
# /trends ersetzt (sie war eine driftende Zweitkopie). Gepflegt wird nur noch
# docs/launch/preview.html — ohne diesen Server gaebe es keinen Ort, an dem sich
# Countdown, Animationen und das Newsletter-Formular pruefen liessen, bevor die
# Datei live geht.
#
#   scripts/landing_preview.sh          # startet auf 127.0.0.1:3997
#   scripts/landing_preview.sh --stop
#
# Erreichbar im Tailnet: https://kiworkstation.tail678c6e.ts.net:3997/preview.html
# (tailscale serve --bg --https=3997 http://127.0.0.1:3997 — einmalig gesetzt).
# Das Formular postet an https://catandary.de/newsletter/subscribe.php, also den
# ECHTEN Endpunkt: zum Testen eine Wegwerf-Adresse nehmen, nicht blind absenden.
set -u
PORT="${LANDING_PREVIEW_PORT:-3997}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../docs/launch" && pwd)"
PIDF="/tmp/catandary-landing-preview.pid"

if [ "${1:-}" = "--stop" ]; then
  [ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null && rm -f "$PIDF" && echo "gestoppt" || echo "lief nicht"
  exit 0
fi
if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
  echo "laeuft bereits (PID $(cat "$PIDF")) auf 127.0.0.1:$PORT"; exit 0
fi
nohup python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$DIR" \
  > /home/dirk/logs/catandary-landing-preview.log 2>&1 &
echo $! > "$PIDF"
sleep 1
printf 'Landing-Vorschau: http://127.0.0.1:%s/preview.html  (Tailnet: https://kiworkstation.tail678c6e.ts.net:%s/preview.html)\n' "$PORT" "$PORT"
