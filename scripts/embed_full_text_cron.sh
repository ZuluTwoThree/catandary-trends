#!/usr/bin/env bash
# Taeglicher Volltext-Vektor-Lauf (#102) — mit Kollisionswaechter.
#
# Warum ein Shell-Wrapper um den Python-Wrapper: der Lauf ist der
# NIEDRIGRANGIGSTE GPU-Job im Haus. Montags um 09:00 startet gleichzeitig
# weekly_newsletter_publish.sh, und der Full Cycle kann an langen Naechten noch
# laufen. Beide sind zeitkritisch, dieser hier nicht — er soll warten, nicht
# draengeln (Befund 2026-09-11: er hatte als einziger GPU-Job keinen Waechter).
#
# Braucht die fremde GPU im Tailnet (bequiet, Fenster 01:00-17:00) nicht
# gewartet zu werden: dann fasst der Lauf die lokale Karte gar nicht an. Der
# Python-Wrapper entscheidet das selbst; hier wird nur derselbe Test vorgezogen,
# um das Warten zu sparen.
#
# --limit 30000 deckt auch den Samstag ab: die Wochen-Ingester bringen dort rund
# 30.000 Kandidaten auf einmal (Preprints, Patente, OpenAlex). 30.000 sind rund
# 40 min auf bequiet und 76 min lokal — mit Waechter davor ist das vertretbar,
# ohne waere es der Job, der dem Newsletter die Karte wegnimmt.

set -u
REPO="/home/dirk/projects/catandary-trends"
PY="$REPO/.venv/bin/python"
cd "$REPO" || exit 1

LIMIT="${EMBED_LIMIT:-30000}"

REMOTE_OK=$("$PY" -c "from pipeline import remote_gpu; print('1' if remote_gpu.available() else '0')" 2>/dev/null)

if [ "$REMOTE_OK" != "1" ]; then
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/gpu_guard.sh"
  if ! gpu_guard_wait embed_full_text; then
    echo "$(date -Iseconds) SKIP: fremder GPU-Job nach ${GPU_GUARD_MAX_MIN} min noch aktiv — naechster Lauf holt nach"
    exit 75
  fi
else
  echo "$(date -Iseconds) fremde GPU im Fenster — lokale Karte bleibt unberuehrt, kein Warten noetig"
fi

exec "$PY" -u scripts/embed_full_text_gpu.py --limit "$LIMIT" --apply
