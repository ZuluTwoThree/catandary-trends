#!/usr/bin/env python3
"""Build patent_cpc_grant: (pub_number, cpc, inventive) for the US-utility-grant
patents that carry an SPNP percentile (patent_spnp_staging), from the Parquet
staging nodes. This is the domain-mapping table the finalized (calibrated) K(t)
trajectory joins against patent_spnp_staging on pub_number.

    python scripts/build_patent_cpc_grant.py
"""
from __future__ import annotations
import glob, io, sys, time
from pathlib import Path
import numpy as np
import pyarrow as pa, pyarrow.compute as pc, pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db import get_connection

STAGING = "/mnt/data-hdd/patent_staging"


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def main() -> int:
    t0 = time.time()
    log("loading grant pub_numbers from patent_spnp_staging …")
    with get_connection() as c:
        cur = c._conn.cursor()
        cur.execute("SELECT pub_number FROM patent_spnp_staging")
        grant_pub = pa.array([r[0] for r in cur.fetchall()], type=pa.large_string())
    log(f"  {len(grant_pub):,} grant pubs")

    with get_connection() as conn:
        cc = conn._conn.cursor()
        cc.execute("DROP TABLE IF EXISTS patent_cpc_grant")
        cc.execute("CREATE TABLE patent_cpc_grant (pub_number TEXT, cpc TEXT, inventive BOOLEAN)")
        conn._conn.commit()

    out = io.StringIO(); written = 0
    shards = sorted(glob.glob(f"{STAGING}/nodes-*.parquet"))
    for i, sh in enumerate(shards):
        t = pq.read_table(sh, columns=["pub_number", "cpc", "inv"])
        pub = t.column("pub_number").combine_chunks().cast(pa.large_string())
        keep = pc.is_in(pub, value_set=grant_pub).to_numpy(zero_copy_only=False)
        if not keep.any():
            continue
        pub_l = pub.to_pylist()
        cpc_l = t.column("cpc").to_pylist()
        inv_l = t.column("inv").to_pylist()
        idx = np.flatnonzero(keep)
        for j in idx:
            p = pub_l[j]
            for code, inv in zip(cpc_l[j] or [], inv_l[j] or []):
                if code:
                    out.write(f"{p}\t{code}\t{'t' if inv else 'f'}\n")
        if out.tell() > 40_000_000:
            out.seek(0)
            with get_connection() as conn:
                conn._conn.cursor().copy_expert(
                    "COPY patent_cpc_grant FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t')", out)
                conn._conn.commit()
            written += out.tell(); out = io.StringIO()
        if (i + 1) % 40 == 0:
            log(f"  {i+1}/{len(shards)} shards")
    out.seek(0)
    with get_connection() as conn:
        conn._conn.cursor().copy_expert(
            "COPY patent_cpc_grant FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t')", out)
        conn._conn.commit()

    log("indexing patent_cpc_grant (cpc prefix + pub_number) …")
    with get_connection() as conn:
        cc = conn._conn.cursor()
        cc.execute("CREATE INDEX idx_cpcg_cpc ON patent_cpc_grant (cpc text_pattern_ops)")
        cc.execute("CREATE INDEX idx_cpcg_pub ON patent_cpc_grant (pub_number)")
        cc.execute("SELECT count(*), count(DISTINCT pub_number) FROM patent_cpc_grant")
        n, npub = cc.fetchone()
        conn._conn.commit()
    log(f"DONE in {(time.time()-t0)/60:.1f} min — {n:,} cpc rows over {npub:,} grants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
