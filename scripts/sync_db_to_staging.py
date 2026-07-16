#!/usr/bin/env python3
"""Sync the DB-only patent data into the Parquet staging graph (goal: close the
citation-network gap so TIR is computed over the current, gap-closed graph).

Background: the SPNP substrates (patent_spnp_full / _z3) are built from the frozen
back-file staging shards (2026-07-11). The weekly BDDS front-file ingest (#49/#50)
wrote its ~1.6M new citation edges into Postgres (patent_links) but NOT into the
staging Parquet — the downloads were discarded (no --keep-files). So the substrate
the frontend reads never saw the gap-filling data.

This bridges that: it finds every patent in Postgres that the staging graph does
NOT know about (DB pub_number ∉ staging node set), and writes two NEW staging
shards from the DB rows —

    nodes-dbsync_<date>.parquet : the new patents (pub_number, year, cpc[], …)
    edges-dbsync_<date>.parquet : patent_links 'cites' edges whose SRC is a new
                                  patent.

Restricting edges to a new SRC is what guarantees NO double-counting: an edge with
a src the staging graph already knows could already be in a staging edge shard, and
the SPNP build does not de-duplicate edges. A src the staging graph has never seen
cannot have a pre-existing edge. (The one category this deliberately skips: a late
citation attached via Amend to a patent that WAS already a staging node — src is
old. Those sit in the truncated recent years anyway; documented, acceptable.)

The shards drop into the staging dir and are picked up by spnp_from_staging.py's
glob automatically. Rebuild WITHOUT the frozen cache so the new shards are read.

GPU-free (Postgres read + Parquet write). Idempotent: re-running overwrites the
same dated shards.

    python scripts/sync_db_to_staging.py --dry-run     # measure the delta
    python scripts/sync_db_to_staging.py               # write the shards
"""
from __future__ import annotations

import argparse
import glob
import time
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db import get_connection
from scripts.parse_patents_to_staging import NODE_SCHEMA, EDGE_SCHEMA

STAGING = "/mnt/data-hdd/patent_staging"


def log(m: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def load_staging_pubs() -> pa.Array:
    """Every pub_number the staging graph knows about (unique)."""
    shards = sorted(glob.glob(f"{STAGING}/nodes-*.parquet"))
    shards = [s for s in shards if "dbsync" not in s]  # never diff against ourselves
    log(f"loading pub_numbers from {len(shards)} staging node shards …")
    chunks = []
    for i, sh in enumerate(shards):
        t = pq.read_table(sh, columns=["pub_number"])
        chunks.append(t.column("pub_number").combine_chunks().cast(pa.large_string()))
        if (i + 1) % 40 == 0:
            log(f"  {i+1}/{len(shards)} shards")
    allpubs = pa.concat_arrays(chunks)
    del chunks
    uniq = pc.unique(allpubs)
    log(f"  {len(allpubs):,} rows → {len(uniq):,} distinct staging pubs")
    return uniq


def new_pubs(staging_set: pa.Array) -> list[str]:
    """DB patents (raw_entries, dated) that the staging graph does not have."""
    log("loading dated DB pubs from raw_entries …")
    with get_connection() as conn:
        cur = conn._conn.cursor()
        cur.execute("SELECT pub_number FROM raw_entries "
                    "WHERE pub_number IS NOT NULL AND published_date IS NOT NULL")
        db = pa.array([r[0] for r in cur.fetchall()], type=pa.large_string())
    log(f"  {len(db):,} dated DB pubs")
    isin = pc.is_in(db, value_set=staging_set)
    new = pc.filter(db, pc.invert(isin))
    new = pc.unique(new)
    log(f"  {len(new):,} DB pubs NOT in the staging graph (the gap to close)")
    return new.to_pylist()


def push_new_pubs(pubs: list[str]) -> None:
    with get_connection() as conn:
        cur = conn._conn.cursor()
        cur.execute("DROP TABLE IF EXISTS _sync_new_pubs")
        cur.execute("CREATE UNLOGGED TABLE _sync_new_pubs (pub TEXT PRIMARY KEY)")
        import io
        buf = io.StringIO()
        for p in pubs:
            buf.write(p + "\n")
        buf.seek(0)
        cur.copy_expert("COPY _sync_new_pubs (pub) FROM STDIN", buf)
        cur.execute("ANALYZE _sync_new_pubs")
        conn._conn.commit()
    log(f"  staged {len(pubs):,} new pubs in _sync_new_pubs")


def write_edges(stamp: str) -> int:
    """patent_links 'cites' edges whose SRC is a new patent → edges shard."""
    log("extracting new edges (src ∈ new pubs) …")
    src_l, dst_l = [], []
    with get_connection() as conn:
        cur = conn._conn.cursor(name="edge_cur")  # server-side, streamed
        cur.itersize = 100_000
        cur.execute("SELECT l.src_pub, l.dst_pub FROM patent_links l "
                    "JOIN _sync_new_pubs n ON n.pub = l.src_pub "
                    "WHERE l.link_type = 'cites'")
        for r in cur:
            src_l.append(r[0]); dst_l.append(r[1])
    n = len(src_l)
    tbl = pa.table({"src": pa.array(src_l, pa.string()),
                    "dst": pa.array(dst_l, pa.string()),
                    "rel": pa.array(["cites"] * n, pa.string())},
                   schema=EDGE_SCHEMA)
    out = f"{STAGING}/edges-dbsync_{stamp}.parquet"
    pq.write_table(tbl, out)
    log(f"  {n:,} new edges → {out}")
    return n


def write_nodes(pubs: list[str], stamp: str) -> int:
    """New patents with year (raw_entries) + cpc (patent_cpc) → nodes shard."""
    log("extracting new nodes (year + cpc) …")
    year_map: dict[str, int] = {}
    with get_connection() as conn:
        cur = conn._conn.cursor(name="year_cur")
        cur.itersize = 100_000
        cur.execute("SELECT n.pub, CAST(EXTRACT(YEAR FROM re.published_date) AS INT) "
                    "FROM _sync_new_pubs n JOIN raw_entries re ON re.pub_number = n.pub "
                    "WHERE re.published_date IS NOT NULL")
        for r in cur:
            y = r[1]
            if y is not None and 1700 <= y <= 2100:
                year_map[r[0]] = y
    cpc_map: dict[str, list] = {}
    inv_map: dict[str, list] = {}
    with get_connection() as conn:
        cur = conn._conn.cursor(name="cpc_cur")
        cur.itersize = 100_000
        cur.execute("SELECT pc.pub_number, pc.cpc, pc.inventive "
                    "FROM patent_cpc pc JOIN _sync_new_pubs n ON n.pub = pc.pub_number")
        for r in cur:
            cpc_map.setdefault(r[0], []).append(r[1])
            inv_map.setdefault(r[0], []).append(bool(r[2]))
    pub_l, yr_l, cpc_l, inv_l = [], [], [], []
    for p in pubs:
        y = year_map.get(p)
        if y is None:
            continue  # undated → no DAG role, skip
        pub_l.append(p); yr_l.append(y)
        cpc_l.append(cpc_map.get(p, [])); inv_l.append(inv_map.get(p, []))
    n = len(pub_l)
    empty = [""] * n
    tbl = pa.table({"pub_number": pa.array(pub_l, pa.string()),
                    "year": pa.array(yr_l, pa.int16()),
                    "vertical": pa.array(empty, pa.string()),
                    "kind": pa.array(empty, pa.string()),
                    "title": pa.array(empty, pa.string()),
                    "cpc": pa.array(cpc_l, pa.list_(pa.string())),
                    "inv": pa.array(inv_l, pa.list_(pa.bool_()))},
                   schema=NODE_SCHEMA)
    out = f"{STAGING}/nodes-dbsync_{stamp}.parquet"
    pq.write_table(tbl, out)
    log(f"  {n:,} new nodes ({len(cpc_map):,} carry CPC) → {out}")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="measure the delta, write nothing")
    ap.add_argument("--stamp", default=date.today().strftime("%Y%m%d"),
                    help="shard date stamp (default today)")
    args = ap.parse_args()
    t0 = time.time()

    staging_set = load_staging_pubs()
    pubs = new_pubs(staging_set)
    del staging_set

    if args.dry_run:
        # cheap edge estimate: how many patent_links src are new
        push_new_pubs(pubs)
        with get_connection() as conn:
            cur = conn._conn.cursor()
            cur.execute("SELECT count(*) FROM patent_links l JOIN _sync_new_pubs n "
                        "ON n.pub = l.src_pub WHERE l.link_type='cites'")
            ne = cur.fetchone()[0]
            cur.execute("DROP TABLE IF EXISTS _sync_new_pubs")
            conn._conn.commit()
        log(f"DRY-RUN: {len(pubs):,} new nodes, ~{ne:,} new edges. Nothing written.")
        return 0

    push_new_pubs(pubs)
    ne = write_edges(args.stamp)
    nn = write_nodes(pubs, args.stamp)
    with get_connection() as conn:
        cur = conn._conn.cursor()
        cur.execute("DROP TABLE IF EXISTS _sync_new_pubs")
        conn._conn.commit()
    log(f"DONE in {(time.time()-t0)/60:.1f} min — {nn:,} node rows, {ne:,} edge rows "
        f"written as dbsync_{args.stamp} shards. Rebuild SPNP WITHOUT the frozen cache.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
