#!/usr/bin/env python3
"""OpenAlex-Snapshot-Ingest v2 — ein Lesedurchgang, Änderungen erkennen (#80; Owner 2026-10-05).

Liest die Works-Parquet-Partitionen (s3://openalex/data/parquet/works/, frei, anonym) mit
Spaltenauswahl, filtert wie bisher (Artikel/Preprint/Review · kein Paratext · Englisch ·
Jahr >= 2010 · Abstract vorhanden · ältere Werke mit mindestens einem Zitat) und vergleicht
jeden Batch mit dem bekannten Stand (`pipeline/openalex_sync.py`):

  neu im Korpus        → research_corpus (+ Volltext-Vektor), Journal, Förderer, Open Access,
                         Zitationen, Zustand, Archivzeile
  Text echt geändert   → Zeile in research_corpus neu (bereinigter/vervollständigter Abstract,
                         Titel ohne Markup); Kürzung zum Anfangsstück wird NICHT übernommen
  zurückgezogen        → nur das Flag
  Zitationen/FWCI/OA/Typ geändert → schmale Tabelle research_work_state (+ research_citation_recent,
                         research_work_oa) — die 147-GB-Tabelle und ihr GIN bleiben unberührt
  unverändert          → nichts

Vorher (bis 05.10.2026): `ON CONFLICT DO NOTHING` + Volltext-Vektor für JEDE Zeile, auch
die ~94 % Duplikate; Journal und Förderer/OA in zwei weiteren S3-Durchgängen (Schritte 2
und 4 des Wrappers), die nun nur noch ihre Aggregate bauen — diese Läufe markiert v2 als
erledigt (openalex_journal_state / openalex_funder_state).

Last: `--workers` (Default 2), Arbeitsprozesse mit nice 10 + ionice idle, `--until HH:MM`
(keine neuen Teilstücke nach dem Zeitpunkt), SIGTERM = sanfter Halt (laufende Teilstücke
schreiben zu Ende, keine neuen). Jeder Batch ist eine Transaktion; ein Teilstück gilt erst
als erledigt, wenn alle Batches und die Archivdatei geschrieben sind (resumable, idempotent).

Exit: 0 fertig · 3 pausiert (Zeitfenster/SIGTERM, Rest bleibt offen) · 2 Platz-Wächter · 1 Fehler.
Statusdatei: data/openalex_sync_last.json; Marker data/openalex_sync_finalize_pending, sobald
etwas verarbeitet wurde (der Wrapper baut dann die Aggregate).

    python scripts/ingest_openalex_snapshot.py --dry-run --max-files 2        # nur zählen
    python scripts/ingest_openalex_snapshot.py --workers 2 --window 09:00-17:00   # Fensterlauf
    python scripts/ingest_openalex_snapshot.py --redo-since 2026-10-05        # v1-Teilstücke dieses
                                                                              # Datums mit v2 nachholen
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402
from pipeline import openalex_sync as ox  # noqa: E402
from pipeline.openalex_sync import reconstruct  # noqa: E402,F401  (Altnutzer importieren es von hier)

REPO = Path(__file__).resolve().parents[1]
ARCHIVE = Path("/mnt/data-hdd/openalex_snapshot")
# Vom nächtlichen Download (scripts/download_openalex.py) abgelegte, vorgefilterte Teilstücke.
STAGING = Path(os.getenv("OPENALEX_STAGING", "/mnt/data-hdd/openalex_staging"))
S3_PREFIX = "openalex/data/parquet/works/"
STATUS = REPO / "data" / "openalex_sync_last.json"
FINALIZE_MARKER = REPO / "data" / "openalex_sync_finalize_pending"
COLS = ["id", "doi", "title", "publication_date", "publication_year", "language",
        "type", "is_paratext", "is_retracted", "abstract_inverted_index",
        "cited_by_count", "counts_by_year", "fwci", "authorships",
        "primary_topic", "topics", "primary_location", "funders", "open_access",
        "citation_normalized_percentile", "updated_date"]
SLIM = [c for c in COLS if c not in ("authorships", "topics", "language", "is_paratext")]
KEEP_TYPES = list(ox.KEEP_TYPES)
MIN_YEAR = ox.MIN_YEAR
CITE_FLOOR_BEFORE = ox.CITE_FLOOR_BEFORE
HDD_MIN_FREE = 150e9
NVME_MIN_FREE = 100e9
BATCH = 2000
VERSION = 2

DDL = """
CREATE TABLE IF NOT EXISTS research_corpus (
    id             TEXT PRIMARY KEY,        -- OpenAlex W-Id (Kurzform)
    doi            TEXT,
    title          TEXT NOT NULL,
    abstract       TEXT NOT NULL,
    published      DATE,
    year           INTEGER,
    type           TEXT,
    topic          TEXT,
    cited_by_count INTEGER,
    fwci           REAL,
    is_retracted   BOOLEAN,
    tsv            tsvector NOT NULL
);
CREATE TABLE IF NOT EXISTS openalex_snap_state (
    part       TEXT PRIMARY KEY,
    rows_total INTEGER,
    kept       INTEGER,
    done_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE openalex_snap_state ADD COLUMN IF NOT EXISTS version SMALLINT;
ALTER TABLE openalex_snap_state ADD COLUMN IF NOT EXISTS counts JSONB;
CREATE TABLE IF NOT EXISTS research_work_state (
    id             TEXT PRIMARY KEY,   -- = research_corpus.id
    oa_fp          BIGINT,             -- Fingerabdruck des OpenAlex-Texts beim letzten Lesen
    cited_by_count INTEGER,            -- jeweils der jüngste OpenAlex-Stand
    fwci           REAL,
    cnp            REAL,               -- citation_normalized_percentile.value
    type           TEXT,
    is_retracted   BOOLEAN,
    is_oa          BOOLEAN,
    shortened      BOOLEAN DEFAULT FALSE,  -- OpenAlex hat nur ein Anfangsstück unseres Abstracts
    oa_updated     DATE,               -- OpenAlex updated_date
    seen_at        DATE DEFAULT CURRENT_DATE
);
CREATE TABLE IF NOT EXISTS research_work_journal (work_id TEXT PRIMARY KEY, journal TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_work_funder (work_id TEXT NOT NULL, funder TEXT NOT NULL, PRIMARY KEY (work_id, funder));
CREATE TABLE IF NOT EXISTS research_work_oa (work_id TEXT PRIMARY KEY, oa_url TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_citation_recent (work_id TEXT PRIMARY KEY, cites_recent INTEGER NOT NULL, cites_total INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS openalex_journal_state (part TEXT PRIMARY KEY, done_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS openalex_funder_state (part TEXT PRIMARY KEY, done_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""

TSV = ("setweight(to_tsvector('english', left({t}, 2000)), 'A') || "
       "setweight(to_tsvector('english', left({a}, 16000)), 'B')")
INSERT_TMPL = ("(%s,%s,%s,%s,%s::date,%s::int,%s,%s,%s::int,%s::real,%s::boolean,"
               + TSV.format(t="%s", a="%s") + ")")


def keep_mask(rg):
    """Der Ingest-Filter als Arrow-Maske (geteilt mit scripts/download_openalex.py)."""
    import pyarrow as pa
    import pyarrow.compute as pc
    m = pc.is_in(rg["type"], value_set=pa.array(KEEP_TYPES))
    m = pc.and_(m, pc.equal(rg["is_paratext"], False))
    m = pc.and_(m, pc.equal(rg["language"], "en"))
    m = pc.and_(m, pc.greater_equal(rg["publication_year"], MIN_YEAR))
    m = pc.and_(m, pc.is_valid(rg["abstract_inverted_index"]))
    return pc.and_(m, pc.or_(pc.greater(rg["publication_year"], CITE_FLOOR_BEFORE),
                             pc.greater_equal(rg["cited_by_count"], 1)))


def disk_ok() -> bool:
    return (shutil.disk_usage(ARCHIVE).free > HDD_MIN_FREE
            and shutil.disk_usage("/").free > NVME_MIN_FREE)


# ---------------------------------------------------------------------------
# Datenbank je Batch
# ---------------------------------------------------------------------------
def load_known(cur, works: list[ox.Work]) -> tuple[dict, dict]:
    ids = [w.id for w in works]
    cur.execute("""SELECT id, oa_fp, cited_by_count, fwci, cnp, type, is_retracted, is_oa, shortened
                   FROM research_work_state WHERE id = ANY(%s)""", (ids,))
    cols = ("oa_fp", "cited_by_count", "fwci", "cnp", "type", "is_retracted", "is_oa", "shortened")
    state = {r[0]: dict(zip(cols, r[1:])) for r in cur.fetchall()}
    need = [w.id for w in works if w.id not in state or state[w.id]["oa_fp"] != w.fp]
    db_text: dict[str, dict] = {}
    if need:
        cur.execute("SELECT id, title, abstract, is_retracted FROM research_corpus WHERE id = ANY(%s)", (need,))
        db_text = {r[0]: {"title": r[1], "abstract": r[2], "is_retracted": r[3]} for r in cur.fetchall()}
    return state, db_text   # Gleitkomma-Vergleich mit Toleranz: openalex_sync.same_float


def apply_plan(cur, p: ox.Plan) -> None:
    from psycopg2.extras import execute_values as ev
    if p.insert:
        ev(cur, "INSERT INTO research_corpus (id, doi, title, abstract, published, year, type, topic, "
                "cited_by_count, fwci, is_retracted, tsv) VALUES %s ON CONFLICT (id) DO NOTHING",
           [(w.id, w.doi, w.title, w.abstract, w.published, w.year, w.type, w.topic, w.cited_by_count,
             w.fwci, w.is_retracted, w.title, w.abstract) for w in p.insert],
           template=INSERT_TMPL, page_size=BATCH)
    if p.update_text:
        ev(cur, f"""UPDATE research_corpus rc SET title = v.title, abstract = v.abstract,
                       tsv = {TSV.format(t='v.title', a='v.abstract')},
                       doi = v.doi, published = v.published, year = v.year, type = v.type, topic = v.topic,
                       cited_by_count = v.cites, fwci = v.fwci, is_retracted = v.retr
                    FROM (VALUES %s) v(id, title, abstract, doi, published, year, type, topic, cites, fwci, retr)
                    WHERE rc.id = v.id""",
           [(w.id, d.title, d.abstract, w.doi, w.published, w.year, w.type, w.topic, w.cited_by_count,
             w.fwci, w.is_retracted) for w, d in p.update_text],
           template="(%s,%s,%s,%s,%s::date,%s::int,%s,%s,%s::int,%s::real,%s::boolean)", page_size=BATCH)
    if p.retraction:
        ev(cur, "UPDATE research_corpus rc SET is_retracted = v.r FROM (VALUES %s) v(id, r) "
                "WHERE rc.id = v.id AND rc.is_retracted IS DISTINCT FROM v.r",
           p.retraction, template="(%s,%s::boolean)")
    if p.state:
        ev(cur, """INSERT INTO research_work_state (id, oa_fp, cited_by_count, fwci, cnp, type, is_retracted,
                                                    is_oa, shortened, oa_updated, seen_at) VALUES %s
                   ON CONFLICT (id) DO UPDATE SET oa_fp = EXCLUDED.oa_fp, cited_by_count = EXCLUDED.cited_by_count,
                     fwci = EXCLUDED.fwci, cnp = EXCLUDED.cnp, type = EXCLUDED.type,
                     is_retracted = EXCLUDED.is_retracted, is_oa = EXCLUDED.is_oa, shortened = EXCLUDED.shortened,
                     oa_updated = EXCLUDED.oa_updated, seen_at = EXCLUDED.seen_at
                   WHERE (research_work_state.oa_fp, research_work_state.cited_by_count, research_work_state.fwci,
                          research_work_state.cnp, research_work_state.type, research_work_state.is_retracted,
                          research_work_state.is_oa, research_work_state.shortened)
                     IS DISTINCT FROM (EXCLUDED.oa_fp, EXCLUDED.cited_by_count, EXCLUDED.fwci, EXCLUDED.cnp,
                          EXCLUDED.type, EXCLUDED.is_retracted, EXCLUDED.is_oa, EXCLUDED.shortened)""",
           p.state, template="(%s,%s::bigint,%s::int,%s::real,%s::real,%s,%s::boolean,%s::boolean,%s::boolean,"
                             "%s::date,CURRENT_DATE)", page_size=BATCH)
    side = p.side + [w for w, _ in p.update_text]
    jr = [(w.id, w.journal) for w in side if w.journal]
    if jr:
        ev(cur, "INSERT INTO research_work_journal (work_id, journal) VALUES %s ON CONFLICT (work_id) DO NOTHING", jr)
    fr = [(w.id, f) for w in side for f in w.funders]
    if fr:
        ev(cur, "INSERT INTO research_work_funder (work_id, funder) VALUES %s ON CONFLICT DO NOTHING", fr)
    if p.oa:
        # Nur schreiben, wenn sich der Link unterscheidet (Owner 05.10.): ON CONFLICT DO UPDATE legt
        # sonst für jedes der ~24 Mio. OA-Werke beim ersten Kontakt eine neue Zeilenversion an.
        ev(cur, """INSERT INTO research_work_oa (work_id, oa_url) VALUES %s
                   ON CONFLICT (work_id) DO UPDATE SET oa_url = EXCLUDED.oa_url
                   WHERE research_work_oa.oa_url IS DISTINCT FROM EXCLUDED.oa_url""",
           [(w.id, w.oa_url) for w in p.oa])
    if p.cites:
        ev(cur, """INSERT INTO research_citation_recent (work_id, cites_recent, cites_total) VALUES %s
                   ON CONFLICT (work_id) DO UPDATE SET cites_recent = EXCLUDED.cites_recent,
                     cites_total = EXCLUDED.cites_total
                   WHERE (research_citation_recent.cites_recent, research_citation_recent.cites_total)
                     IS DISTINCT FROM (EXCLUDED.cites_recent, EXCLUDED.cites_total)""",
           [(w.id, w.recent, w.total) for w in p.cites])


# ---------------------------------------------------------------------------
# Ein Teilstück (läuft im Arbeitsprozess)
# ---------------------------------------------------------------------------
def _init_worker() -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)   # der Hauptprozess entscheidet über den Halt
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        os.nice(10)
        subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def staged_path(part: str) -> Path:
    return STAGING / Path(part).parent.name / Path(part).name


def archive_path(part: str, stamp: str | None = None) -> Path:
    """Archivdatei eines Laufs. Jeder v2-Lauf schreibt eine EIGENE Datei
    (`part_0034.v2-202610061015.parquet`) und überschreibt nie — sonst gingen neue Werke eines
    früheren Laufs verloren, bevor der Archiv-Extrakt (Schritt 3, `part_*.parquet`) sie gelesen hat
    (Fund 05.10.: ein zweites Lesen löschte die Datei des ersten). Duplikate über Dateien fängt der
    Extrakt ab (ON CONFLICT (work_id))."""
    p = ARCHIVE / Path(part).parent.name / Path(part).name
    return p if stamp is None else p.with_name(f"{p.stem}.v2-{stamp}.parquet")


def process_part(part: str, dry_run: bool = False, prev_version: int | None = None) -> tuple[str, dict, str]:
    """Liest, vergleicht, schreibt ein Teilstück. Idempotent."""
    import psycopg2
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    import s3fs

    counts = {"rows": 0, "kept": 0, "new": 0, "text": 0, "retract": 0, "state": 0,
              "unchanged": 0, "shortened": 0, "oa": 0, "cites": 0, "source": ""}
    fs = s3fs.S3FileSystem(anon=True)
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SET statement_timeout = '600s'")
    conn.commit()
    local = staged_path(part)
    try:
        if local.exists():   # vom Download abgelegt: kein Netz, schon vorgefiltert
            f = pq.ParquetFile(local)
            side = Path(str(local) + ".json")
            rows_total = json.loads(side.read_text())["rows_total"] if side.exists() else None
        else:
            f = pq.ParquetFile(fs.open("openalex/" + part if not part.startswith("openalex/") else part))
            rows_total = None
        counts["source"] = "local" if local.exists() else "s3"
        names = set(f.schema_arrow.names)
        cols = [c for c in COLS if c in names]
        archive_tables = []
        for i in range(f.metadata.num_row_groups):
            rg = f.read_row_group(i, columns=cols)
            counts["rows"] += rg.num_rows
            kept = rg.filter(keep_mask(rg))
            if kept.num_rows == 0:
                continue
            counts["kept"] += kept.num_rows
            slim = kept.select([c for c in SLIM if c in kept.column_names]).to_pylist()
            works = [w for w in (ox.Work.from_row(r, idx) for idx, r in enumerate(slim)) if w]
            idx_archive: list[int] = []
            for b in range(0, len(works), BATCH):
                batch = works[b:b + BATCH]
                state, db_text = load_known(cur, batch)
                p = ox.plan_batch(batch, state, db_text)
                if not dry_run:
                    apply_plan(cur, p)
                    conn.commit()
                else:
                    conn.rollback()
                idx_archive += p.archive
                counts["new"] += len(p.insert)
                counts["text"] += len(p.update_text)
                counts["retract"] += len(p.retraction)
                counts["state"] += len(p.state)
                counts["unchanged"] += p.unchanged
                counts["shortened"] += p.shortened
                counts["oa"] += len(p.oa)
                counts["cites"] += len(p.cites)
            if idx_archive:
                archive_tables.append(kept.take(pa.array(sorted(set(idx_archive)))))
        if rows_total is not None:
            counts["rows"] = rows_total
        if not dry_run:
            if archive_tables:
                out = archive_path(part, datetime.now().strftime("%Y%m%d%H%M"))
                out.parent.mkdir(parents=True, exist_ok=True)
                tmp = out.with_suffix(".tmp")
                pq.write_table(pa.concat_tables(archive_tables, promote_options="default"), tmp, compression="zstd")
                tmp.replace(out)                      # atomar: nie eine halbe Archivdatei
            v1 = archive_path(part)
            if (prev_version or 1) < VERSION and v1.exists():
                v1.unlink()                           # v1-Vollkopie: Neues und Geändertes steht jetzt in der v2-Datei
            cur.execute("""INSERT INTO openalex_snap_state (part, rows_total, kept, version, counts, done_at)
                           VALUES (%s, %s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP)
                           ON CONFLICT (part) DO UPDATE SET rows_total = EXCLUDED.rows_total, kept = EXCLUDED.kept,
                             version = EXCLUDED.version, counts = EXCLUDED.counts, done_at = EXCLUDED.done_at""",
                        (part, counts["rows"], counts["kept"], VERSION, json.dumps(counts)))
            for t in ("openalex_journal_state", "openalex_funder_state"):
                cur.execute(f"INSERT INTO {t} (part) VALUES (%s) ON CONFLICT DO NOTHING", (part,))
            conn.commit()
            if local.exists():                        # verarbeitet: Ablage freigeben
                local.unlink()
                Path(str(local) + ".json").unlink(missing_ok=True)
        return (part, counts, "")
    except Exception as e:  # noqa: BLE001 — Fehler je Datei melden, Lauf geht weiter
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return (part, counts, f"{type(e).__name__}: {str(e)[:300]}")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Hauptprozess
# ---------------------------------------------------------------------------
_STOP = {"flag": False, "why": ""}


def _on_term(signum, _frame) -> None:
    _STOP["flag"] = True
    _STOP["why"] = f"signal {signum}"
    print(f"Halt angefordert ({_STOP['why']}) — laufende Teilstücke werden fertig geschrieben, keine neuen.",
          flush=True)


def list_parts(fs) -> list[str]:
    parts: list[str] = []
    for d in sorted(fs.ls(S3_PREFIX, detail=False)):
        if "updated_date" in d:
            parts.extend(p for p in sorted(fs.ls(d, detail=False)) if p.endswith(".parquet"))
    return parts


def select_todo(parts: list[str], done: dict[str, tuple], redo_since: str | None) -> list[str]:
    """Nicht erledigt, oder (mit --redo-since) mit v1 an/nach diesem Datum gelesen."""
    todo = []
    for p in parts:
        st = done.get(p)
        if st is None:
            todo.append(p)
        elif redo_since and (st[0] or 1) < VERSION and st[1] and str(st[1])[:10] >= redo_since:
            todo.append(p)
    return todo


def write_status(d: dict) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    tmp.replace(STATUS)


def main(argv: list[str] | None = None) -> int:
    import psycopg2
    import s3fs
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-files", type=int, default=0)
    ap.add_argument("--until", help="HH:MM — danach keine neuen Teilstücke (sanfter Halt, Exit 3); über Mitternacht")
    ap.add_argument("--window", help="HH:MM-HH:MM am selben Tag (z. B. 09:00-17:00) — außerhalb startet nichts, "
                                      "am Ende sanfter Halt (Exit 3); hat Vorrang vor --until")
    ap.add_argument("--redo-since", help="YYYY-MM-DD — mit v1 an/nach diesem Datum gelesene Teilstücke neu lesen")
    ap.add_argument("--parts", nargs="*", help="genau diese Teilstücke (Test)")
    ap.add_argument("--dry-run", action="store_true", help="nur zählen, nichts schreiben")
    ap.add_argument("--local-only", action="store_true",
                    help="nur vom Download abgelegte Teilstücke verarbeiten (kein S3-Lesen); offen bleibt, was noch "
                         "nicht geladen ist — Exit 3, solange auf S3 etwas fehlt")
    args = ap.parse_args(argv)

    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)
    if args.window:
        inside, stop_at = ox.window_end(args.window)
        if not inside:
            print(f"außerhalb des Zeitfensters {args.window} — nichts gestartet", flush=True)
            write_status({"started": datetime.now(), "paused": True, "reason": f"outside window {args.window}"})
            return 3
    else:
        stop_at = ox.deadline(args.until)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    for stmt in DDL.split(";\n"):
        cur.execute(stmt)
    cur.execute("SELECT part, version, done_at FROM openalex_snap_state")
    done = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

    fs = s3fs.S3FileSystem(anon=True)
    parts = args.parts or list_parts(fs)
    todo = args.parts or select_todo(parts, done, args.redo_since)
    not_staged = 0
    if args.local_only:
        staged = [p for p in todo if staged_path(p).exists()]
        not_staged = len(todo) - len(staged)
        todo = staged
        print(f"lokal abgelegt: {len(todo)}, noch nicht geladen: {not_staged}", flush=True)
    if args.max_files:
        todo = todo[:args.max_files]
    started = datetime.now()
    print(f"{len(parts)} Part-Dateien, {len(todo)} zu tun · Arbeitsprozesse {args.workers} · "
          f"bis {stop_at:%d.%m. %H:%M}" if stop_at else
          f"{len(parts)} Part-Dateien, {len(todo)} zu tun · Arbeitsprozesse {args.workers}", flush=True)
    status = {"started": started, "todo_before": len(todo), "processed": 0, "errors": 0, "remaining": len(todo),
              "paused": False, "reason": None, "dry_run": args.dry_run, "until": str(stop_at) if stop_at else None}
    write_status(status)
    if not todo:
        status.update(ended=datetime.now(), remaining=not_staged,
                      paused=bool(not_staged), reason="waiting for download" if not_staged else "nothing to do")
        write_status(status)
        conn.close()
        return 3 if not_staged else 0

    totals: dict[str, int] = {}
    t0 = time.time()
    queue = list(todo)
    inflight = {}
    rc = 0
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init_worker) as ex:
        while queue or inflight:
            while queue and len(inflight) < args.workers and not _STOP["flag"]:
                if stop_at and datetime.now() >= stop_at:
                    _STOP["flag"], _STOP["why"] = True, f"Zeitfenster bis {stop_at:%H:%M}"
                    print(f"Zeitfenster zu ({stop_at:%d.%m. %H:%M}) — keine neuen Teilstücke.", flush=True)
                    break
                if not disk_ok():
                    _STOP["flag"], _STOP["why"] = True, "Platz-Wächter"
                    rc = 2
                    print("ABBRUCH: Platz-Wächter (HDD<150GB oder NVMe<100GB frei) — resumable.", flush=True)
                    break
                part = queue.pop(0)
                inflight[ex.submit(process_part, part, args.dry_run, (done.get(part) or (None,))[0])] = part
            if not inflight:
                break
            finished, _ = wait(list(inflight), return_when=FIRST_COMPLETED)
            for fut in finished:
                part = inflight.pop(fut)
                _, counts, err = fut.result()
                if err:
                    status["errors"] += 1
                    print(f"FEHLER {part}: {err}", flush=True)
                    continue
                status["processed"] += 1
                for k, v in counts.items():
                    if isinstance(v, int):
                        totals[k] = totals.get(k, 0) + v
                n = status["processed"]
                if n % 10 == 0 or n == len(todo) or args.dry_run or args.parts:
                    print(f"[{n}/{len(todo)}] gelesen {totals.get('kept', 0):,} · neu {totals.get('new', 0):,} · "
                          f"Text {totals.get('text', 0):,} · zurückgezogen {totals.get('retract', 0):,} · "
                          f"Zustand {totals.get('state', 0):,} · unverändert {totals.get('unchanged', 0):,} · "
                          f"gekürzt (behalten) {totals.get('shortened', 0):,} · {time.time() - t0:.0f}s", flush=True)
                status.update(remaining=len(queue) + len(inflight), totals=totals)
                write_status(status)
    remaining = len(queue) + not_staged          # lokal-Modus: Ungeladenes zählt als offen
    paused = remaining > 0 and rc == 0
    status.update(ended=datetime.now(), remaining=remaining, paused=paused, reason=_STOP["why"] or None,
                  totals=totals, hours=round((time.time() - t0) / 3600, 2))
    write_status(status)
    if status["processed"] and not args.dry_run:
        FINALIZE_MARKER.write_text(datetime.now().isoformat(), encoding="utf-8")
    conn.close()
    print(("PAUSIERT" if paused else "FERTIG") + f": {status['processed']} Teilstücke, {remaining} offen, "
          f"{status['errors']} Fehler in {(time.time() - t0) / 3600:.1f}h — {json.dumps(totals)}", flush=True)
    if rc:
        return rc
    if paused:
        return 3
    return 1 if status["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
