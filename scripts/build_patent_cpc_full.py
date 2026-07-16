#!/usr/bin/env python3
"""Build patent_cpc_full: (pub_number, cpc, inventive) for every patent that carries
an SPNP percentile in patent_spnp_full (the #35 technology-balanced full-archive
graph), from the Parquet staging nodes. This is the domain-mapping table the
full-archive K(t) trajectory joins against patent_spnp_full on pub_number — the
dense, all-country, all-domain counterpart to build_patent_cpc_grant.py.

    python scripts/build_patent_cpc_full.py
"""
from __future__ import annotations
import argparse, glob, io, sys, time
from pathlib import Path
import numpy as np
import pyarrow as pa, pyarrow.compute as pc, pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db import get_connection

STAGING = "/mnt/data-hdd/patent_staging"
OUT = "patent_cpc_full"
SRC_TABLE = "patent_spnp_full"


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="build patent_cpc_full from staging nodes")
    ap.add_argument("--out", default=OUT, help="destination cpc table")
    ap.add_argument("--src", default=SRC_TABLE, help="SPNP table whose pub set to keep")
    args = ap.parse_args()
    global OUT, SRC_TABLE
    OUT, SRC_TABLE = args.out, args.src
    idx_suffix = OUT.replace("patent_cpc_", "")  # unique index names per table
    t0 = time.time()
    log(f"loading pub_numbers from {SRC_TABLE} …")
    with get_connection() as c:
        cur = c._conn.cursor()
        cur.execute(f"SELECT pub_number FROM {SRC_TABLE}")
        keep_pub = pa.array([r[0] for r in cur.fetchall()], type=pa.large_string())
    log(f"  {len(keep_pub):,} SPNP pubs")

    with get_connection() as conn:
        cc = conn._conn.cursor()
        cc.execute(f"DROP TABLE IF EXISTS {OUT}")
        cc.execute(f"CREATE TABLE {OUT} (pub_number TEXT, cpc TEXT, inventive BOOLEAN)")
        conn._conn.commit()

    out = io.StringIO()
    shards = sorted(glob.glob(f"{STAGING}/nodes-*.parquet"))
    for i, sh in enumerate(shards):
        t = pq.read_table(sh, columns=["pub_number", "cpc", "inv"])
        pub = t.column("pub_number").combine_chunks().cast(pa.large_string())
        keep = pc.is_in(pub, value_set=keep_pub).to_numpy(zero_copy_only=False)
        if not keep.any():
            continue
        pub_l = pub.to_pylist()
        cpc_l = t.column("cpc").to_pylist()
        inv_l = t.column("inv").to_pylist()
        for j in np.flatnonzero(keep):
            p = pub_l[j]
            for code, inv in zip(cpc_l[j] or [], inv_l[j] or []):
                if code:
                    out.write(f"{p}\t{code}\t{'t' if inv else 'f'}\n")
        if out.tell() > 40_000_000:
            out.seek(0)
            with get_connection() as conn:
                conn._conn.cursor().copy_expert(
                    f"COPY {OUT} FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t')", out)
                conn._conn.commit()
            out = io.StringIO()
        if (i + 1) % 40 == 0:
            log(f"  {i+1}/{len(shards)} shards")
    out.seek(0)
    with get_connection() as conn:
        conn._conn.cursor().copy_expert(
            f"COPY {OUT} FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t')", out)
        conn._conn.commit()

    log(f"indexing {OUT} (cpc prefix + pub_number) …")
    with get_connection() as conn:
        cc = conn._conn.cursor()
        cc.execute(f"CREATE INDEX idx_cpcf_{idx_suffix}_cpc ON {OUT} (cpc text_pattern_ops)")
        cc.execute(f"CREATE INDEX idx_cpcf_{idx_suffix}_pub ON {OUT} (pub_number)")
        cc.execute(f"SELECT count(*), count(DISTINCT pub_number) FROM {OUT}")
        n, npub = cc.fetchone()
        conn._conn.commit()
    log(f"DONE in {(time.time()-t0)/60:.1f} min — {n:,} cpc rows over {npub:,} patents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
