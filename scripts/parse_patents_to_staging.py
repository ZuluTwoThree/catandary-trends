#!/usr/bin/env python3
"""Parse the full DOCDB back-file archive → compact Parquet staging (issues #35/#27).

Decouples the expensive one-time PARSE from the irreversible INSERT: we scan every
patent in the local BDDS archive once (graph-backfill mode — non-EN AND
out-of-vertical kept), and stream normalized records to Parquet shards on the HDD.
NOTHING goes into Postgres here. Afterwards the real numbers (doc/edge counts,
per-year density) drive the insert-scope decision, and SPNP centrality can be
built on the FULL graph straight from these shards (numpy) without bloating the DB.

Per outer archive file two shards are written to --out:
  nodes-<stem>.parquet : pub_number, year, vertical, kind, title, cpc[], inv[]
  edges-<stem>.parquet : src, dst, rel            (citation + family links)

Resumable: an outer whose nodes shard already exists is skipped.

    python scripts/parse_patents_to_staging.py \
        --archive /mnt/data-hdd/bdds_backfile --out /mnt/data-hdd/patent_staging --workers 12
"""
from __future__ import annotations

import argparse
import glob
import os
import time
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.ingest_patents import parse_docdb_document, _EXCH

NODE_SCHEMA = pa.schema([
    ("pub_number", pa.string()),
    ("year", pa.int16()),
    ("vertical", pa.string()),
    ("kind", pa.string()),
    ("title", pa.string()),
    ("cpc", pa.list_(pa.string())),
    ("inv", pa.list_(pa.bool_())),
])
EDGE_SCHEMA = pa.schema([
    ("src", pa.string()),
    ("dst", pa.string()),
    ("rel", pa.string()),
])


def _year(pub_date: str | None) -> int | None:
    if pub_date and len(pub_date) >= 4 and pub_date[:4].isdigit():
        y = int(pub_date[:4])
        if 1700 <= y <= 2100:
            return y
    return None


FLUSH_ROWS = 400_000  # flush node buffer to a Parquet row-group past this (bounds RAM)


def parse_outer(zpath: str, out_dir: str, max_inner: int = 0) -> dict:
    """Parse one outer archive zip → two Parquet shards (streamed row-groups, so
    RAM stays bounded regardless of outer size). Returns stats."""
    stem = Path(zpath).stem
    node_path = os.path.join(out_dir, f"nodes-{stem}.parquet")
    edge_path = os.path.join(out_dir, f"edges-{stem}.parquet")
    if os.path.exists(node_path) and os.path.exists(edge_path):
        return {"stem": stem, "skipped": True, "nodes": 0, "edges": 0, "docs": 0, "secs": 0}

    nbuf = {k: [] for k in ("pub_number", "year", "vertical", "kind", "title", "cpc", "inv")}
    ebuf = {k: [] for k in ("src", "dst", "rel")}
    n_nodes = n_edges = docs = 0
    t0 = time.time()
    nw = pq.ParquetWriter(node_path + ".part", NODE_SCHEMA, compression="zstd")
    ew = pq.ParquetWriter(edge_path + ".part", EDGE_SCHEMA, compression="zstd")

    def flush(force=False):
        nonlocal n_nodes, n_edges
        if nbuf["pub_number"] and (force or len(nbuf["pub_number"]) >= FLUSH_ROWS):
            nw.write_table(pa.table(nbuf, schema=NODE_SCHEMA))
            n_nodes += len(nbuf["pub_number"])
            for v in nbuf.values():
                v.clear()
        if ebuf["src"] and (force or len(ebuf["src"]) >= FLUSH_ROWS):
            ew.write_table(pa.table(ebuf, schema=EDGE_SCHEMA))
            n_edges += len(ebuf["src"])
            for v in ebuf.values():
                v.clear()

    try:
        with zipfile.ZipFile(zpath) as z:
            inner = [n for n in z.namelist() if n.endswith(".zip") and "/DOC/" in n]
            for name in (inner[:max_inner] if max_inner else inner):
                try:
                    with z.open(name) as innerf, zipfile.ZipFile(innerf) as iz:
                        xml = iz.read(iz.namelist()[0])
                    root = ET.fromstring(xml)
                except (zipfile.BadZipFile, ET.ParseError, KeyError, IndexError):
                    continue
                for docu in root.findall(f"{_EXCH}exchange-document"):
                    docs += 1
                    rec = parse_docdb_document(docu, require_en=False, require_vertical=False)
                    if rec is None:
                        continue
                    nbuf["pub_number"].append(rec["pub_number"])
                    nbuf["year"].append(_year(rec["pub_date"]))
                    nbuf["vertical"].append(rec["vertical"])
                    nbuf["kind"].append(rec["kind_code"] or "")
                    nbuf["title"].append(rec["title"] or "")
                    cs = rec.get("cpc_struct") or [(c, True) for c in rec["cpc"]]
                    nbuf["cpc"].append([c for c, _ in cs])
                    nbuf["inv"].append([bool(i) for _, i in cs])
                    for s, d, rel, _ in rec["links"]:
                        ebuf["src"].append(s); ebuf["dst"].append(d); ebuf["rel"].append(rel)
                flush()
        flush(force=True)
    finally:
        nw.close(); ew.close()
    os.replace(node_path + ".part", node_path)
    os.replace(edge_path + ".part", edge_path)
    return {"stem": stem, "skipped": False, "nodes": n_nodes,
            "edges": n_edges, "docs": docs, "secs": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse DOCDB archive → Parquet staging (#35/#27)")
    ap.add_argument("--archive", default="/mnt/data-hdd/bdds_backfile")
    ap.add_argument("--out", default="/mnt/data-hdd/patent_staging")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0, help="cap outer files (0=all; for a test)")
    ap.add_argument("--max-inner", type=int, default=0, help="cap inner files per outer (0=all; for a fast test)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    outers = sorted(glob.glob(os.path.join(args.archive, "*.zip")))
    if args.limit:
        outers = outers[:args.limit]
    print(f"[staging] {len(outers)} outer files, {args.workers} workers → {args.out}", flush=True)

    tot = {"nodes": 0, "edges": 0, "docs": 0, "done": 0, "skipped": 0}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(parse_outer, z, args.out, args.max_inner): z for z in outers}
        for fut in as_completed(futs):
            r = fut.result()
            tot["done"] += 1
            if r["skipped"]:
                tot["skipped"] += 1
                detail = "skip"
            else:
                tot["nodes"] += r["nodes"]; tot["edges"] += r["edges"]; tot["docs"] += r["docs"]
                detail = f"nodes={r['nodes']:>8,} edges={r['edges']:>9,} {r['secs']}s"
            el = time.time() - t0
            print(f"  [{tot['done']:3d}/{len(outers)}] {r['stem']:34s} {detail}"
                  f"  | Σ nodes={tot['nodes']:,} edges={tot['edges']:,} | {el/60:.1f}min", flush=True)

    el = time.time() - t0
    print(f"\n[staging] DONE in {el/60:.1f} min — {tot['docs']:,} docs scanned, "
          f"{tot['nodes']:,} nodes, {tot['edges']:,} edges "
          f"({tot['skipped']} outers skipped/resumed).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
