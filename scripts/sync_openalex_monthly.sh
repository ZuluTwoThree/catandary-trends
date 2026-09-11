#!/usr/bin/env bash
# Monatlicher OpenAlex-Sync (#80) — das Amend-Gegenstück für den Research-
# Korpus. Cron: 0 2 5 * * (5. des Monats, 02:00; entzerrt 2026-08-29; GPU-frei, kollidiert mit
# keinem GPU-Fenster — BDDS Di 05:00 ist reine CPU/Netz-Arbeit).
#
# OpenAlex veröffentlicht ~monatlich ein Release; geänderte/neue Werke landen
# in neuen updated_date-Partitionen. Alle drei Pipelines sind resumable über
# State-Tabellen (openalex_snap_state / _journal_state / _extract_state) und
# verarbeiten daher genau die neuen Partitionen:
#   1. ingest_openalex_snapshot  — neue Werke → research_corpus (+ Archiv-Kopie)
#   2. enrich_openalex_journals  — Journal-Namen der neuen Partitionen (S3)
#   3. extract_openalex_archive  — Autoren/Institutionen/Zitationskurven
#      (liest das lokale Archiv; finalize baut die Aggregate neu, sobald
#      alle Parts verarbeitet sind)
#   4. Statistik-Tabellen: research_corpus_topics + research_corpus_meta
#      (das Explorer-Frontend liest NUR diese — nie COUNTs über die 45M-Tabelle)
#
# WICHTIG: Updates bestehender Werke (Zitationszahlen!) kommen als neue Zeilen
# derselben work_id in neuen Partitionen — ON CONFLICT DO NOTHING behält die
# ALTE Zeile. Fürs Erste akzeptiert (Titel/Abstract ändern sich praktisch nie);
# die Zitations-Frische kommt aus research_citation_recent, dessen Extrakt
# dieselbe Grenze hat. Ein UPDATE-Pfad ist als Ausbau in #80 notiert.

set -u

REPO="/home/dirk/projects/catandary-trends"
LOG="/home/dirk/logs/catandary-openalex-sync-$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG")"

{
  echo "================================================================"
  echo "sync_openalex_monthly.sh start $(date -Iseconds)"
  echo "================================================================"
  cd "$REPO" || { echo "ABORT: cannot cd to $REPO"; exit 1; }
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/ops_events.sh"
  ops_event_start sync_openalex_monthly
  # shellcheck disable=SC1091
  source .venv/bin/activate

  RC=0
  echo; echo "----- 1/5 Snapshot-Ingest (neue Partitionen) -----"
  python -u scripts/ingest_openalex_snapshot.py --workers 4 || RC=$?

  echo; echo "----- 2/5 Journal-Enrichment (neue Partitionen) -----"
  python -u scripts/enrich_openalex_journals.py --workers 4 || RC=$?

  echo; echo "----- 3/5 Archiv-Extrakt (Autoren/Institutionen/Zitationen) -----"
  python -u scripts/extract_openalex_archive.py --workers 4 || RC=$?

  echo; echo "----- 4/5 Funder/OA-Enrichment (neue Partitionen) -----"
  python -u scripts/enrich_openalex_funders_oa.py --workers 4 || RC=$?

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

  ops_event_end "$RC"
  echo; echo "sync_openalex_monthly.sh end $(date -Iseconds) (rc=$RC)"
  exit "$RC"
} >> "$LOG" 2>&1
