#!/usr/bin/env bash
# OpenAlex-Sync (#80) — das Amend-Gegenstück für den Research-Korpus.
#
# Seit 2026-10-05 (Owner, docs/openalex_sync_2026-10-05.md): v2 — EIN Lesedurchgang je
# Teilstück erkennt Änderungen statt sie zu verwerfen (neue Werke, echt geänderte Texte,
# Zurückziehungen in research_corpus; Zitationen/FWCI/OA/Typ in der schmalen Tabelle
# research_work_state), schreibt Journal, Förderer und Open Access gleich mit und arbeitet
# in einem ZEITFENSTER: täglich ab 09:00, nach dem Ende der Morgen-Crons, bis SYNC_UNTIL
# (Default 00:30); was dann offen ist, setzt der nächste Tag fort. Ohne neue Teilstücke ist
# der Lauf nach dem S3-Listing fertig (Schritte 2–5 entfallen).
#
#   1. ingest_openalex_snapshot  — Teilstücke lesen + vergleichen + schreiben (Exit 3 = pausiert)
#   2. enrich_openalex_journals  — nur noch Aggregat (v2 markiert seine Teilstücke als erledigt)
#   3. extract_openalex_archive  — Autoren/Institutionen/Zitationskurven aus den v2-Archivdateien
#   4. enrich_openalex_funders_oa — nur noch Aggregat (wie 2)
#   5. Statistik-Tabellen        — research_corpus_topics/_meta … (nur nach abgeschlossenem Lauf)
#
# Last: SYNC_WORKERS (Default 2), nice 10 + ionice idle, Sperrdatei gegen Doppelstart, Warten
# (bis SYNC_WAIT_MAX_MIN) solange Nachtlauf, Patent-Jobs, Startup-Register, Ingester, Publish
# oder Backup laufen. Einmalig: SYNC_REDO_SINCE=2026-10-05 liest die am 05.10. noch mit v1
# gelesenen Teilstücke mit v2 nach (Zitationen, Texte, Journal/Förderer/OA).
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$HOME/logs/catandary-openalex-sync-$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG")"
SYNC_UNTIL="${SYNC_UNTIL:-00:30}"
SYNC_WORKERS="${SYNC_WORKERS:-2}"
SYNC_REDO_SINCE="${SYNC_REDO_SINCE:-}"
SYNC_WAIT_MAX_MIN="${SYNC_WAIT_MAX_MIN:-240}"
BUSY_PATTERNS='full_cycle_cron[.]sh|scheduled_cycle[.]sh|weekly_patents[.]sh|weekly_patent_analytics[.]sh|monthly_startup_sources[.]sh|weekly_ingesters[.]sh|publish_static_site[.]sh|backup_db[.]py|weekly_newsletter_publish[.]sh'
MARKER="$REPO/data/openalex_sync_finalize_pending"

{
  echo "================================================================"
  echo "sync_openalex_monthly.sh start $(date -Iseconds) (repo $REPO, bis $SYNC_UNTIL, Arbeitsprozesse $SYNC_WORKERS${SYNC_REDO_SINCE:+, redo-since $SYNC_REDO_SINCE})"
  echo "================================================================"
  cd "$REPO" || { echo "ABORT: cannot cd to $REPO"; exit 1; }
  mkdir -p "$REPO/data"
  # Gemeinsame Sperre für beide Worktrees (dev-Timer und main-Cron dürfen nie parallel laufen)
  mkdir -p "$HOME/.local/state/catandary"
  exec 9>"$HOME/.local/state/catandary/openalex_sync.lock"
  if ! flock -n 9; then
    echo "läuft bereits (Sperrdatei) — Ende"
    echo "sync_openalex_monthly.sh end $(date -Iseconds) (rc=0, locked)"
    exit 0
  fi
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/ops_events.sh"
  ops_event_start sync_openalex_monthly
  # shellcheck disable=SC1091
  source .venv/bin/activate

  waited=0
  while busy=$(pgrep -af "$BUSY_PATTERNS" 2>/dev/null | grep -vE "pgrep|grep " ); [ -n "$busy" ]; do
    if [ "$waited" -ge "$SYNC_WAIT_MAX_MIN" ]; then
      echo "nach $waited min noch belegt — verschoben auf den nächsten Lauf:"; echo "$busy" | cut -c1-140
      ops_event_end 75 "postponed: busy"
      echo "sync_openalex_monthly.sh end $(date -Iseconds) (rc=75, busy)"
      exit 75
    fi
    [ "$waited" -eq 0 ] && { echo "warte, bis diese Jobs fertig sind:"; echo "$busy" | cut -c1-140; }
    sleep 60
    waited=$((waited + 1))
  done
  [ "$waited" -gt 0 ] && echo "frei nach $waited min"

  NICE=(nice -n 10 ionice -c 3)
  RC=0
  echo; echo "----- 1/5 Snapshot-Ingest v2 (lesen, vergleichen, schreiben) -----"
  "${NICE[@]}" python -u scripts/ingest_openalex_snapshot.py --workers "$SYNC_WORKERS" --until "$SYNC_UNTIL" \
      ${SYNC_REDO_SINCE:+--redo-since "$SYNC_REDO_SINCE"}
  RC1=$?
  if [ "$RC1" -eq 3 ]; then
    echo "pausiert (Zeitfenster/Halt) — der Rest folgt im nächsten Fenster; Schritte 2–5 erst danach"
    ops_event_end 0 "paused"
    echo; echo "sync_openalex_monthly.sh end $(date -Iseconds) (rc=0, paused)"
    exit 0
  fi
  [ "$RC1" -ne 0 ] && RC=$RC1
  if [ ! -f "$MARKER" ]; then
    echo "keine neuen Teilstücke — Schritte 2–5 entfallen"
    ops_event_end "$RC" "nothing new"
    echo; echo "sync_openalex_monthly.sh end $(date -Iseconds) (rc=$RC)"
    exit "$RC"
  fi

  echo; echo "----- 2/5 Journal-Aggregat -----"
  "${NICE[@]}" python -u scripts/enrich_openalex_journals.py --workers "$SYNC_WORKERS" || RC=$?

  echo; echo "----- 3/5 Archiv-Extrakt (Autoren/Institutionen/Zitationen) -----"
  "${NICE[@]}" python -u scripts/extract_openalex_archive.py --workers "$SYNC_WORKERS" || RC=$?

  echo; echo "----- 4/5 Förderer/OA-Aggregat -----"
  "${NICE[@]}" python -u scripts/enrich_openalex_funders_oa.py --workers "$SYNC_WORKERS" || RC=$?

  echo; echo "----- 5/5 Statistik-Tabellen -----"
  python - <<'PY' || RC=$?
import psycopg2, os
from dotenv import load_dotenv; load_dotenv('.env')
c = psycopg2.connect(os.environ['DATABASE_URL']); c.autocommit = True; cur = c.cursor()
cur.execute("""DROP TABLE IF EXISTS research_corpus_topics_new;
CREATE TABLE research_corpus_topics_new AS
  SELECT topic, COUNT(*)::int AS n FROM research_corpus
  WHERE topic IS NOT NULL GROUP BY topic""")
cur.execute("ALTER TABLE research_corpus_topics_new ADD PRIMARY KEY (topic)")
cur.execute("DROP TABLE IF EXISTS research_corpus_topics")
cur.execute("ALTER TABLE research_corpus_topics_new RENAME TO research_corpus_topics")
cur.execute("""DROP TABLE IF EXISTS research_topic_years_new;
CREATE TABLE research_topic_years_new AS
  SELECT topic, year, COUNT(*)::int AS n FROM research_corpus
  WHERE topic IS NOT NULL AND year BETWEEN 2010 AND 2026
    AND cited_by_count >= 1  -- gleiche Huerde fuer alle Jahre: der Korpus-
    -- Zitations-Floor (alt braucht >=1 Zitat, jung nicht) wuerde sonst
    -- kuenstliches Wachstum in ALLEN Topics erzeugen (#83, 2026-08-15)
  GROUP BY 1,2""")
cur.execute("ALTER TABLE research_topic_years_new ADD PRIMARY KEY (topic, year)")
cur.execute("DROP TABLE IF EXISTS research_topic_years")
cur.execute("ALTER TABLE research_topic_years_new RENAME TO research_topic_years")
for src, dst, cols in [
    ("research_topic_funders", "research_funders",
     "funder, SUM(n)::int AS n"),
    ("research_topic_institutions", "research_institutions",
     "institution, MAX(country) AS country, SUM(n)::int AS n"),
]:
    # Typeahead-Aggregate (#83) — klein, aus den Topic-Aggregaten abgeleitet
    key = cols.split(",")[0].strip()
    cur.execute(f"DROP TABLE IF EXISTS {dst}_new")
    cur.execute(f"CREATE TABLE {dst}_new AS SELECT {cols} FROM {src} GROUP BY {key}")
    cur.execute(f"ALTER TABLE {dst}_new ADD PRIMARY KEY ({key})")
    cur.execute(f"DROP TABLE IF EXISTS {dst}")
    cur.execute(f"ALTER TABLE {dst}_new RENAME TO {dst}")
cur.execute("SELECT COUNT(*) FROM research_corpus")
n = cur.fetchone()[0]
cur.execute("""INSERT INTO research_corpus_meta (singleton, total) VALUES (TRUE, %s)
  ON CONFLICT (singleton) DO UPDATE SET total = EXCLUDED.total,
  built_at = CURRENT_TIMESTAMP""", (n,))
print(f"Statistik-Tabellen refresht: total={n:,}")
PY

  if [ "$RC" -eq 0 ]; then rm -f "$MARKER"; fi
  ops_event_end "$RC"
  echo; echo "sync_openalex_monthly.sh end $(date -Iseconds) (rc=$RC)"
  exit "$RC"
} >> "$LOG" 2>&1
