# SQLite → PostgreSQL + pgvector — Migrations-Runbook

Vorbereitung für den **Patent-Tiefe-Ingest** (Back-File braucht Postgres; Massen-
Vektorsuche wächst aus SQLite heraus). Stand: Code vorbereitet, **kein Cutover** —
SQLite bleibt live, bis die Schritte unten bewusst ausgeführt werden.

## Was bereits vorbereitet ist (Code, GPU-frei, ohne Cutover)

- **`pipeline/db.py` `PG_SCHEMA`** mit dem gewachsenen Schema gesynct: `raw_entries.pub_number/kind_code`, `trends.sort_date`, Tabellen `patent_links` + `patent_cpc`, alle Indizes (sort/pubnum/plinks/pcpc).
- **`_PgConnectionWrapper.executemany`** ergänzt: übersetzt `INSERT OR IGNORE` → `ON CONFLICT DO NOTHING` via `execute_values` → `insert_patent_links`/`insert_patent_cpc` laufen auf PG (Back-File-Ingest-Pfad).
- **`scripts/migrate_to_postgres.py`** — SQLite→PG-Migration. Liest SQLite **read-only** (WAL, stört die Pipeline nicht). Validiert: `--self-check` (Konvertierer inkl. embedding→vector(4096)) und `--dry-run` (Zählung) — beide ohne Postgres.

## Schritt 1 — Postgres + pgvector installieren (braucht `sudo`)

Ubuntu 24.04:
```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib postgresql-16-pgvector
# (Paketname je Major-Version: postgresql-16-pgvector / -17-pgvector)
sudo systemctl enable --now postgresql
```
pgvector ≥ 0.7 (für späteres `halfvec`) ist in den aktuellen Paketen enthalten.

## Schritt 2 — Rolle + Datenbank anlegen

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE catandary WITH LOGIN PASSWORD 'CHANGE_ME';
CREATE DATABASE catandary_trends OWNER catandary;
\c catandary_trends
CREATE EXTENSION IF NOT EXISTS vector;
SQL
```
DATABASE_URL (für die Migration + später die Pipeline):
```
postgresql://catandary:CHANGE_ME@127.0.0.1:5432/catandary_trends
```

## Schritt 3 — Daten migrieren (NUR wenn die SQLite-Writer idle sind)

Wichtig: erst wenn **kein `signal_batch`/`llm_processor` mehr schreibt** (sonst ist
die PG-Kopie unvollständig). Der TECH-Lauf muss durch sein.

```bash
# Probelauf (klein, FK-konsistent, prüft Insert-Pfad + pgvector end-to-end):
DATABASE_URL='postgresql://…' .venv/bin/python scripts/migrate_to_postgres.py --fresh --limit 2000
# Voll (--fresh räumt die Probe-Daten weg und kopiert alles sauber):
DATABASE_URL='postgresql://…' .venv/bin/python scripts/migrate_to_postgres.py --fresh
```
Validiert 2026-06-26: Probe (2000) lief sauber durch — vector_dims=4096, pgvector
`<=>`-Cosine liefert kohärente Nachbarn, jsonb/bool/date-Konvertierung ok.
Hinweis: `sources.source_type`-CHECK wurde um `research`/`science`/`sitemap`
erweitert (Live-Daten enthalten `research` aus den OpenAlex-Quellen).
Erwartete Größenordnung (Stand 2026-06-26): ~1,74 Mio Zeilen (raw_entries ~747k,
trends ~178k+, patent_links ~495k, patent_cpc ~317k). Das Script setzt die
SERIAL-Sequenzen nach dem Copy zurück.

## Schritt 4 — Verifizieren

```bash
DATABASE_URL='postgresql://…' .venv/bin/python - <<'PY'
from pipeline.db import get_connection
with get_connection() as c:
    for t in ("sources","raw_entries","trends","patent_links","patent_cpc"):
        print(t, c.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"])
    # Vektor-Sanity:
    print("embedded trends:", c.execute(
      "SELECT COUNT(*) AS n FROM trends WHERE embedding IS NOT NULL").fetchone()["n"])
PY
```
Counts gegen den SQLite-`--dry-run` abgleichen. Ein read-only Pipeline-Tool
(`tir_graph.py`, `cluster_trajectory_demo.py`) gegen DATABASE_URL gegenchecken.

## Schritt 5 — Frontend-Port (die eigentliche Handarbeit)

`frontend/src/lib/db.ts` nutzt **better-sqlite3 (synchron)** + SQLite-Dialekt. Port
auf `pg` (node-postgres, **async**):
- **Treiber:** `better-sqlite3` → `pg`; Pool statt `new Database()`; alle Query-
  Funktionen `async`, alle Aufrufer (`page.tsx`/API-Routen) `await`-en.
- **Platzhalter:** `?` → `$1,$2,…`.
- **SQL-Dialekt:**
  - `MIN(re.published_date, datetime('now'))` → `LEAST(re.published_date, now())`
  - `datetime('now','-30 days')` / `datetime('now', ?)` → `now() - interval '30 days'`
  - `json_array_length(t.verticals)` → `jsonb_array_length(t.verticals)`
  - `json_each(t.pestel)` → `jsonb_array_elements_text(t.pestel)`
  - `GROUP_CONCAT(DISTINCT x)` → `string_agg(DISTINCT x, ',')`
  - JSONB kommt schon geparst zurück → `JSON.parse(...)` in `parseTrendRow` entfällt für die jsonb-Spalten.
- **Volltextsuche:** SQLite-FTS5 (`trends_fts MATCH`) hat kein PG-Pendant 1:1 →
  auf `tsvector`/`tsquery` (GIN-Index) oder `pg_trgm` umstellen. Größter Einzelposten.
- **Env:** `DATABASE_PATH` raus, `DATABASE_URL` rein.

Empfehlung: `lib/db.ts` hinter ein dünnes Query-Interface kapseln, dann ist es die
einzige zu portierende Datei + die `await`-Ripples.

## Schritt 6 — Cutover

1. Pipeline: `DATABASE_URL` in `.env` setzen → `pipeline/db.py` schaltet automatisch (USE_POSTGRES).
2. Frontend: gebautes pg-`lib/db.ts` deployen, `DATABASE_URL` setzen, `npm run build`.
3. SQLite-DB als Backup behalten (nicht löschen).

## Embedding / ANN-Strategie

- **Jetzt:** `trends.embedding VECTOR(4096)`, **exakte** Cosine-Suche (`<=>`), kein
  ANN-Index. Bei 134k–600k Signalen sub-Sekunde bis ~2 s — völlig ausreichend.
- **Für die Patent-Millionen (Back-File):** pgvector-HNSW cappt bei 2000 Dim. Dann
  Spalte auf `halfvec(4096)` (halber Speicher) + zusätzliche **truncated `embedding_2000 halfvec(2000)`** (Matryoshka-Trunkierung) mit **HNSW-Index** als ANN-Prefilter, Rerank über die vollen 4096. Erst beim Back-File nötig (dann ist die Zeilenzahl noch klein → Alter billig).

## Rollback

`DATABASE_URL` entfernen → Pipeline fällt auf SQLite zurück. Frontend: alte
`lib/db.ts` (better-sqlite3) redeployen. SQLite-DB blieb unangetastet.
