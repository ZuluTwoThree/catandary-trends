#!/usr/bin/env bash
# Move cold tables (and their indexes) into a Postgres tablespace on the HDD (Owner 2026-10-03).
#
# Frees the NVMe without dropping anything: the three *_old tables (36 GB) are read only by
# the nightly pg_dump. ALTER … SET TABLESPACE copies the files and holds an exclusive lock
# for the copy (~5 min at HDD speed for 36 GB) — never during the backup (01:30) or the
# cycle (02:45 on weekdays). The tablespace itself needs a superuser once (step 1, sudo).
#
#   scripts/move_cold_tables_to_hdd.sh            # dry run: prints what it would do
#   scripts/move_cold_tables_to_hdd.sh --apply
#
# Consequences (docs/restore_runbook.md): a restore needs the tablespace to exist first, or
# `pg_restore --no-tablespaces`; if /mnt/data-hdd is not mounted (fstab: nofail), Postgres
# starts but these tables fail to read — and so does the backup.
set -euo pipefail
DB=${DB:-catandary}
DIR=${TABLESPACE_DIR:-/mnt/data-hdd/pg_tablespace}
SPC=${TABLESPACE:-hdd}
TABLES=${TABLES:-"patent_cpc_full_old patent_spnp_full_old patent_spnp_full_z3_old"}
APPLY=0; [ "${1:-}" = "--apply" ] && APPLY=1

run() { if [ $APPLY = 1 ]; then echo "+ $*"; "$@"; else echo "would: $*"; fi; }

if pgrep -f "[s]cheduled_cycle.sh|[f]ull_cycle_cron.sh|[b]ackup_db.py" >/dev/null; then
  echo "a cycle or the backup is running — try later"; exit 75
fi

if ! psql -d "$DB" -tAc "SELECT 1 FROM pg_tablespace WHERE spcname='$SPC'" | grep -q 1; then
  run sudo install -d -o postgres -g postgres -m 700 "$DIR"
  run sudo -u postgres psql -d "$DB" -c "CREATE TABLESPACE $SPC OWNER $(whoami) LOCATION '$DIR'"
fi

for t in $TABLES; do
  before=$(psql -d "$DB" -tAc "SELECT pg_size_pretty(pg_total_relation_size('$t'))")
  echo "== $t ($before)"
  run psql -d "$DB" -c "ALTER TABLE $t SET TABLESPACE $SPC"
  for i in $(psql -d "$DB" -tAc "SELECT indexrelid::regclass FROM pg_index WHERE indrelid = '$t'::regclass"); do
    run psql -d "$DB" -c "ALTER INDEX $i SET TABLESPACE $SPC"
  done
done
[ $APPLY = 1 ] && psql -d "$DB" -c "SELECT c.relname, coalesce(ts.spcname,'pg_default') AS tablespace,
  pg_size_pretty(pg_total_relation_size(c.oid)) FROM pg_class c LEFT JOIN pg_tablespace ts ON ts.oid = c.reltablespace
  WHERE c.relname IN ($(printf "'%s'," $TABLES | sed 's/,$//'))"
echo "done"
