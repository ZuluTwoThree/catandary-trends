# Postgres Restore Runbook

Verified 2026-07-13 (Epic W0.6). The daily backup (`scripts/backup_db.py` →
`/mnt/data-hdd/backups/catandary/catandary-pg-<date>.dumpdir`) is structurally
sound: a full restore recovers **20.5M raw_entries, 112M patent_links** and
every non-vector table exactly.

> **Format change 2026-08-24:** the backup is now a **directory-format dump**
> (`pg_dump -Fd -j 4 --compress=zstd:3`, ~113 GB, ~18 min) instead of the old
> single-file `-Fc` dump. Background: the `-Fc` dump had been dying on its
> 1-hour timeout every night since 2026-07-13 while the log still said
> "backup OK" — 42 nights without a restorable backup. Failures are fatal now,
> each dump is verified with `pg_restore --list` against the live table count,
> and `scripts/cycle_watchdog.py` checks the artifact on weekday mornings.
> `pg_restore` handles the directory exactly like the old file — just point it
> at the `.dumpdir` path. (`-Fc` dumps from before the change restore the same
> way.)

## The one gotcha: pgvector must exist in the target first

The production schema has `vector`-typed columns (`trends.embedding VECTOR(4096)`,
CPC/OpenAlex embedding columns). `pg_restore` **cannot** create the `vector`
extension (it is not a trusted extension → needs superuser). A bare
`createdb + pg_restore` therefore fails ~57 statements, **silently dropping the
`trends` table and everything referencing it** while the restore "succeeds"
with exit 1. The dump is fine — the target DB just wasn't prepared.

## Correct restore procedure

```bash
# 1. create the empty target (dirk has CREATEDB)
createdb catandary_restore

# 2. create the vector extension AS SUPERUSER — this is the load-bearing step
sudo -u postgres psql -d catandary_restore -c 'CREATE EXTENSION vector'

# 3. restore (parallel, ignore ownership/ACLs that reference roles you may lack)
pg_restore -d catandary_restore -j4 --no-owner --no-privileges \
    /mnt/data-hdd/backups/catandary/catandary-pg-<date>.dumpdir

# 4. verify a vector-typed table came back
psql -d catandary_restore -c 'SELECT count(*) FROM trends'
```

## Disaster-recovery note

For a real DR onto a fresh host, the same rule applies: install pgvector
(`apt install postgresql-16-pgvector` or build), then `CREATE EXTENSION vector`
in the target **before** `pg_restore`. Keep this runbook with the backups.

## What the W0.6 test confirmed

- Backup file integrity: raw_entries 20,567,258 / patent_links 112,037,453 /
  sources 250 all restored bit-for-bit (raw_entries is ~1k short of live only
  because the dump is from the prior night — expected).
- The vector-extension prerequisite (above) is the only manual step; once done,
  the vector tables restore normally.
