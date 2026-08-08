#!/usr/bin/env bash
# Wöchentlicher Refresh der patentbasierten Rechnungen. Cron: 0 8 * * 2 (Di 08:00,
# nach dem BDDS-Ingest um 05:00 — weekly_patents.sh braucht i. d. R. <1h; ein
# noch laufender Ingest ist unkritisch, dann rechnet die Woche drauf nach).
#
# Kette (alles CPU/SQL, GPU-frei):
#   1. build_cpc_tier_series  — Cross-Tier-Zeitreihen je CPC-Subclass (Voll-Rebuild;
#                               nimmt die neuen Cr-Del-Patente + Amend-CPC/Zitationen auf)
#   2. build_cpc_insights     — Frontend-Payloads der kuratierten Technologien
#   3. assign_cpc             — Signal→CPC-Projektion, inkrementell (ON CONFLICT
#                               DO NOTHING; erfasst neue embedded Signale)
#
# BEWUSST NICHT im Cron:
#   - Radare (Owner-Entscheid 2026-07-30: nur auf Knopfdruck, Radar = Dokument
#     mit sichtbarem Rechenstand)
#   - TIR-/SPNP-Forschungsrechnungen (Staging-Graph; Graph-Queries müssen
#     SQL-gescoped sein — Voll-Graph-OOM; aktive Forschungslinie #35/#36)

set -u

REPO="/home/dirk/projects/catandary-trends"
LOG="/home/dirk/logs/catandary-patent-analytics-$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG")"

{
  echo "================================================================"
  echo "weekly_patent_analytics.sh start $(date -Iseconds)"
  echo "================================================================"
  cd "$REPO" || { echo "ABORT: cannot cd to $REPO"; exit 1; }
  # shellcheck disable=SC1091
  source .venv/bin/activate

  RC=0
  for STEP in "build_cpc_tier_series" "build_cpc_insights" "assign_cpc"; do
    echo; echo "----- $STEP $(date -Iseconds) -----"
    T0=$(date +%s)
    python -u "scripts/${STEP}.py" || RC=$?
    echo "----- $STEP fertig in $(( $(date +%s) - T0 ))s (rc-akkum=$RC) -----"
  done

  echo; echo "weekly_patent_analytics.sh end $(date -Iseconds) (rc=$RC)"
  exit "$RC"
} >> "$LOG" 2>&1
