#!/usr/bin/env python3
"""OpenAlex-Download — vom Verarbeiten getrennt (Owner 2026-10-05).

Ziel: der Datenbank-Job (scripts/ingest_openalex_snapshot.py, Fenster 09:00–17:00) wartet nie
auf das Internet. Dieser Job lädt die Teilstücke vorher — nachts, außerhalb des Fensters —
am Stück herunter (kein Mehrfachlesen wie beim Streamen: gemessen 1,4 GB statt 0,85 GB je
Teilstück), filtert sie mit DEMSELBEN Filter wie der Ingest auf die behaltenen Zeilen und die
benötigten Spalten (gemessen 15 % der Originalgröße) und legt sie ab:

    /mnt/data-hdd/openalex_staging/<updated_date=…>/<part_NNNN>.parquet

Rohdatei nur vorübergehend auf der NVMe (~/.cache/catandary/openalex_dl), danach gelöscht.
Keine Datenbank-Last außer der Statustabelle openalex_download_state, kein Modell, keine GPU.
Mehrere Teilstücke parallel (`--streams`), nice/ionice, Zeitfenster (`--window`/`--until`),
SIGTERM = sanfter Halt (laufende Downloads werden fertig). Resumable: was in
openalex_download_state steht und als Datei liegt, wird nicht erneut geladen.

    python scripts/download_openalex.py --streams 4 --until 00:40
    python scripts/download_openalex.py --redo-since 2026-10-05 --window 17:00-23:59
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
from scripts import ingest_openalex_snapshot as ing  # noqa: E402

STAGING = Path(os.getenv("OPENALEX_STAGING", "/mnt/data-hdd/openalex_staging"))
TMP = Path(os.getenv("OPENALEX_DL_TMP", str(Path.home() / ".cache" / "catandary" / "openalex_dl")))
NVME_MIN_FREE = 100e9
HDD_MIN_FREE = 150e9

DDL = """CREATE TABLE IF NOT EXISTS openalex_download_state (
    part          TEXT PRIMARY KEY,
    raw_bytes     BIGINT,
    staged_bytes  BIGINT,
    rows_total    INTEGER,
    kept          INTEGER,
    dl_seconds    REAL,
    filter_seconds REAL,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""


def staged_path(part: str) -> Path:
    return STAGING / Path(part).parent.name / Path(part).name


def _init_worker() -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        os.nice(10)
        subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def download_part(part: str) -> tuple[str, dict, str]:
    """Am Stück laden → filtern/projizieren → atomar in die Ablage. Rohdatei danach weg."""
    import pyarrow.parquet as pq
    import s3fs
    TMP.mkdir(parents=True, exist_ok=True)
    raw = TMP / (Path(part).parent.name + "__" + Path(part).name)
    out = staged_path(part)
    st: dict = {}
    try:
        t0 = time.time()
        s3fs.S3FileSystem(anon=True).get(part if part.startswith("openalex/") else "openalex/" + part, str(raw))
        st["dl_seconds"] = time.time() - t0
        st["raw_bytes"] = raw.stat().st_size
        t1 = time.time()
        f = pq.ParquetFile(raw)
        cols = [c for c in ing.COLS if c in f.schema_arrow.names]
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp_out = out.with_suffix(".tmp")
        writer = None
        rows = kept = 0
        for i in range(f.metadata.num_row_groups):
            rg = f.read_row_group(i, columns=cols)
            rows += rg.num_rows
            k = rg.filter(ing.keep_mask(rg))
            if writer is None:
                schema = k.schema.with_metadata({b"source_part": part.encode()})
                writer = pq.ParquetWriter(tmp_out, schema, compression="zstd")
            if k.num_rows:
                kept += k.num_rows
                writer.write_table(k.replace_schema_metadata(writer.schema.metadata))
        if writer is not None:
            writer.close()
        # Zeilenzahl des Originals für die Statistik des Ingests (rows_total) mitgeben
        meta = {"rows_total": rows, "kept": kept, "source_part": part}
        Path(str(out) + ".json").write_text(json.dumps(meta), encoding="utf-8")
        tmp_out.replace(out)
        st.update(filter_seconds=time.time() - t1, staged_bytes=out.stat().st_size, rows_total=rows, kept=kept)
        return part, st, ""
    except Exception as e:  # noqa: BLE001
        return part, st, f"{type(e).__name__}: {str(e)[:300]}"
    finally:
        try:
            raw.unlink()
        except OSError:
            pass


_STOP = {"flag": False, "why": ""}


def _on_term(signum, _frame) -> None:
    _STOP["flag"], _STOP["why"] = True, f"signal {signum}"
    print(f"Halt angefordert ({_STOP['why']}) — laufende Downloads werden fertig.", flush=True)


def space_ok() -> bool:
    TMP.mkdir(parents=True, exist_ok=True)
    STAGING.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(TMP).free > NVME_MIN_FREE and shutil.disk_usage(STAGING).free > HDD_MIN_FREE


def main(argv: list[str] | None = None) -> int:
    import psycopg2
    import s3fs
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--streams", type=int, default=3, help="parallele Downloads")
    ap.add_argument("--until", help="HH:MM — danach keine neuen Downloads (über Mitternacht)")
    ap.add_argument("--window", help="HH:MM-HH:MM am selben Tag; außerhalb startet nichts")
    ap.add_argument("--redo-since", help="wie beim Ingest: v1-Teilstücke ab diesem Datum ebenfalls laden")
    ap.add_argument("--max-files", type=int, default=0)
    ap.add_argument("--parts-file", help="Teilstücke aus dieser Datei statt S3-Listing (eine je Zeile)")
    args = ap.parse_args(argv)
    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)
    if args.window:
        inside, stop_at = ox.window_end(args.window)
        if not inside:
            print(f"außerhalb des Zeitfensters {args.window} — nichts gestartet", flush=True)
            return 3
    else:
        stop_at = ox.deadline(args.until)

    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(DDL)
    cur.execute("SELECT part, version, done_at FROM openalex_snap_state")
    done = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    cur.execute("SELECT part FROM openalex_download_state")
    have = {r[0] for r in cur.fetchall()}
    parts = (Path(args.parts_file).read_text().split() if args.parts_file
             else ing.list_parts(s3fs.S3FileSystem(anon=True)))
    todo = [p for p in ing.select_todo(parts, done, args.redo_since)
            if not (p in have and staged_path(p).exists())]
    todo.sort(reverse=True)                # neueste Partitionen zuerst (sie sind die großen und aktuellen)
    if args.max_files:
        todo = todo[:args.max_files]
    print(f"{len(parts)} Teilstücke auf S3, {len(todo)} zu laden · {args.streams} parallel"
          + (f" · bis {stop_at:%d.%m. %H:%M}" if stop_at else ""), flush=True)
    t0 = time.time()
    tot = {"parts": 0, "raw": 0, "staged": 0, "errors": 0}
    queue, inflight = list(todo), {}
    with ProcessPoolExecutor(max_workers=args.streams, initializer=_init_worker) as ex:
        while queue or inflight:
            while queue and len(inflight) < args.streams and not _STOP["flag"]:
                if stop_at and datetime.now() >= stop_at:
                    _STOP["flag"], _STOP["why"] = True, f"Zeitfenster bis {stop_at:%H:%M}"
                    print(f"Zeitfenster zu ({stop_at:%H:%M}) — keine neuen Downloads.", flush=True)
                    break
                if not space_ok():
                    _STOP["flag"], _STOP["why"] = True, "Platz-Wächter"
                    print("ABBRUCH: Platz-Wächter (NVMe < 100 GB oder HDD < 150 GB frei).", flush=True)
                    break
                part = queue.pop(0)
                inflight[ex.submit(download_part, part)] = part
            if not inflight:
                break
            finished, _ = wait(list(inflight), return_when=FIRST_COMPLETED)
            for fut in finished:
                part = inflight.pop(fut)
                _, st, err = fut.result()
                if err:
                    tot["errors"] += 1
                    print(f"FEHLER {part}: {err}", flush=True)
                    continue
                cur.execute("""INSERT INTO openalex_download_state (part, raw_bytes, staged_bytes, rows_total, kept,
                                   dl_seconds, filter_seconds) VALUES (%s,%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (part) DO UPDATE SET raw_bytes = EXCLUDED.raw_bytes,
                                 staged_bytes = EXCLUDED.staged_bytes, rows_total = EXCLUDED.rows_total,
                                 kept = EXCLUDED.kept, dl_seconds = EXCLUDED.dl_seconds,
                                 filter_seconds = EXCLUDED.filter_seconds, downloaded_at = CURRENT_TIMESTAMP""",
                            (part, st["raw_bytes"], st["staged_bytes"], st["rows_total"], st["kept"],
                             st["dl_seconds"], st["filter_seconds"]))
                tot["parts"] += 1
                tot["raw"] += st["raw_bytes"]
                tot["staged"] += st["staged_bytes"]
                el = time.time() - t0
                print(f"{datetime.now():%H:%M:%S} [{tot['parts']}] {Path(part).parent.name}/{Path(part).name}: "
                      f"{st['raw_bytes']/1e6:.0f} MB in {st['dl_seconds']:.0f} s "
                      f"({st['raw_bytes']/1e6/max(st['dl_seconds'], 0.1):.1f} MB/s), Filter {st['filter_seconds']:.0f} s · "
                      f"gesamt {tot['raw']/1e9:.1f} GB = {tot['raw']/1e6/el:.1f} MB/s "
                      f"({tot['raw']*8/1e6/el:.0f} Mbit/s), abgelegt {tot['staged']/1e9:.2f} GB", flush=True)
    el = time.time() - t0
    remaining = len(queue)
    print(f"{'PAUSIERT' if remaining else 'FERTIG'}: {tot['parts']} Teilstücke, {tot['raw']/1e9:.1f} GB geladen "
          f"in {el/60:.1f} min = {tot['raw']/1e6/max(el,1):.1f} MB/s ({tot['raw']*8/1e6/max(el,1):.0f} Mbit/s), "
          f"abgelegt {tot['staged']/1e9:.2f} GB, {remaining} offen, {tot['errors']} Fehler", flush=True)
    conn.close()
    if tot["errors"]:
        return 1
    return 3 if remaining else 0


if __name__ == "__main__":
    raise SystemExit(main())
