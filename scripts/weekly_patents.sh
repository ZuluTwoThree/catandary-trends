#!/usr/bin/env bash
# Weekly BDDS patent ingest (#50). Cron: 0 5 * * 2  (Tuesday 05:00)
#
# Runs --kind both, and that is not a detail: Cr-Del and Amend carry different
# things. A patent enters via Cr-Del at publication, largely without CPC codes
# and with almost no citations. The examiner's classification and the search
# report's citations arrive WEEKS LATER, via Amend. Measured on real deliveries:
#
#   Amend   547,130 docs -> 22,877 citation edges
#   Amend   729,921 docs -> 56,151 edges
#   Cr-Del  121,702 docs ->    549 edges
#   Cr-Del  137,478 docs ->  7,300 edges
#
# Cr-Del alone would therefore grow the patent count while leaving the citation
# graph blind for every new patent — and SPNP/TIR are built on exactly that
# graph. --kind both is what keeps the graph alive.
#
# Idempotent: catchup_bdds.py keeps per-delivery state and raw_entries dedups on
# url, so a missed week heals itself on the next run and a re-run inserts
# nothing. GPU-free (download + XML parse + insert) — safe next to any pipeline.

set -u

REPO="/home/dirk/projects/catandary-trends"
LOG="/home/dirk/logs/bdds-weekly-$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG")"

# Rolling window: bound the publication-date filter to the last ~120 days. The
# per-delivery state (not this date) decides what gets fetched; this only keeps
# the parse from considering ancient records in a fresh delivery.
AFTER=$(date -d '120 days ago' +%F)
BEFORE=$(date -d '+1 year' +%F)

{
  echo "================================================================"
  echo "weekly_patents.sh start $(date -Iseconds)  window ${AFTER} .. ${BEFORE}"
  echo "================================================================"
  cd "$REPO" || { echo "ABORT: cannot cd to $REPO"; exit 1; }
  # shellcheck disable=SC1091
  source .venv/bin/activate

  python -u scripts/catchup_bdds.py --after "$AFTER" --before "$BEFORE" --kind both
  RC=$?
  echo "----- catchup exit code: $RC -----"

  # Density guard (#50). Currency must NEVER be judged by MAX(published_date):
  # a single fresh delivery made a 7-month crater look current, twice in one day
  # (patents #49, OpenAlex #51). Check the density of a COMPLETED month instead.
  echo
  echo "----- Dichte-Wächter -----"
  python - <<'PY'
from pipeline.db import get_connection
from datetime import date, timedelta

# THREE months back, not two. The 2026-07-16 catch-up measured where DOCDB's
# classification/citation lag actually settles:
#
#   2026-04 (m-3)  177,837  123%   filled
#   2026-05 (m-2)   82,973   57%   still filling
#   2026-06 (m-1)   79,695   55%   still filling
#
# A month needs ~3 months before its CPC codes and citations have arrived, so
# checking m-2 would raise a false alarm on a perfectly healthy corpus. m-3 is
# the earliest window where a real stall is distinguishable from normal lag.
d = date.today().replace(day=1)
for _ in range(3):
    d = (d - timedelta(days=1)).replace(day=1)
month = d.strftime("%Y-%m")
with get_connection() as c:
    r = c.execute("SELECT COUNT(*) AS n FROM raw_entries WHERE pub_number IS NOT NULL "
                  "AND CAST(published_date AS TEXT) LIKE ?", (month + "%",)).fetchone()
    n = r["n"] if isinstance(r, dict) else r[0]
NORM = 145_000
pct = n / NORM * 100
print(f"{month}: {n:,} Patente ({pct:.0f}% des Normalwerts {NORM:,})")
if pct < 50:
    print(f"WARNUNG: {month} liegt unter 50% — Ingest prüfen (#49/#50)")
PY
  echo
  echo "weekly_patents.sh end $(date -Iseconds) (rc=$RC)"
} >> "$LOG" 2>&1
