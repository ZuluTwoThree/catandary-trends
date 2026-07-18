#!/usr/bin/env python3
"""WS1 (korrigiert): cited-Zentralität aus dem STAGING-Graphen (dieselben Kanten,
aus denen das SPNP-Substrat gebaut ist), NICHT aus patent_links.

Der erste Versuch (build_cited_spnp.py) las patent_links (DB, 113M) — dort haben
historische US-Grants (1980-2010) nur ~0,1% Rückwärts-Zitate, während der
Staging-Graph (146M, voller DOCDB-Back-File-Parse) sie enthält. Das verzerrte den
cited-Prädiktor (n_cited ≪ n_own). Hier: cited_pctl[v] = Mittel der spnp_pctl der
von v zitierten Knoten, über die Staging-Kanten (Cache), mit derselben Abdeckung
wie own.

    python scripts/build_cited_spnp_staging.py --cache /mnt/data-hdd/patent_staging/extended_graph_cache \
        --spnp patent_spnp_full_z3 --out patent_citedspnp_full_z3
"""
from __future__ import annotations
import argparse, io, sys, time
from pathlib import Path
import numpy as np
import pyarrow as pa, pyarrow.compute as pc, pyarrow.parquet as pq
sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db import get_connection


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="/mnt/data-hdd/patent_staging/extended_graph_cache")
    ap.add_argument("--spnp", default="patent_spnp_full_z3")
    ap.add_argument("--out", default="patent_citedspnp_full_z3")
    args = ap.parse_args()
    t0 = time.time()

    log(f"lade Staging-Graph-Cache {args.cache} …")
    d = np.load(args.cache + ".npz")
    src, dst = d["src"], d["dst"]            # int32 node ids der verbundenen Kanten
    nodes_pub = pq.read_table(args.cache + ".pub.parquet").column("pub").combine_chunks()
    n = len(nodes_pub)
    log(f"  {n:,} Knoten, {len(src):,} Kanten")

    log(f"lade spnp_pctl aus {args.spnp} und richte auf Knoten-Reihenfolge aus …")
    with get_connection() as conn:
        c = conn._conn.cursor()
        c.execute(f"SELECT pub_number, spnp_pctl FROM {args.spnp}")
        rows = c.fetchall()
    tbl_pub = pa.array([r[0] for r in rows], type=nodes_pub.type)
    tbl_val = np.array([r[1] for r in rows], dtype=np.float64)
    # Position jedes Tabellen-Pubs in der Knotenliste → pctl-Array in Knoten-Reihenfolge
    idx = pc.index_in(tbl_pub, value_set=nodes_pub).to_numpy(zero_copy_only=False).astype("float64")
    pctl = np.full(n, np.nan, dtype=np.float64)
    m = ~np.isnan(idx)
    pctl[idx[m].astype(np.int64)] = tbl_val[m]
    log(f"  {int(m.sum()):,} pctl-Werte zugeordnet ({100*np.isfinite(pctl).mean():.1f}% der Knoten)")

    log("cited_pctl[v] = Mittel der spnp_pctl der von v ZITIERTEN Knoten …")
    # Kante src->dst bedeutet: src zitiert dst (dst ist älter). cited = Mittel pctl[dst] je src.
    valid = np.isfinite(pctl[dst])
    s = src[valid]; w = pctl[dst][valid]
    sums = np.bincount(s, weights=w, minlength=n)
    cnts = np.bincount(s, minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        cited = sums / cnts
    have = cnts > 0
    log(f"  {int(have.sum()):,} Knoten mit ≥1 zitiertem, abgedecktem Patent")

    log(f"schreibe {args.out} (COPY) …")
    pubs = nodes_pub.to_pylist()
    with get_connection() as conn:
        c = conn._conn.cursor()
        c.execute(f"DROP TABLE IF EXISTS {args.out}")
        c.execute(f"CREATE TABLE {args.out} (pub_number TEXT PRIMARY KEY, cited_pctl REAL, n_cited INT)")
        buf = io.StringIO(); w_ = 0
        for i in np.flatnonzero(have):
            buf.write(f"{pubs[i]},{cited[i]:.6f},{int(cnts[i])}\n")
            if buf.tell() > 50_000_000:
                buf.seek(0); c.copy_expert(f"COPY {args.out} FROM STDIN WITH (FORMAT csv)", buf)
                w_ += buf.tell(); buf = io.StringIO()
        buf.seek(0); c.copy_expert(f"COPY {args.out} FROM STDIN WITH (FORMAT csv)", buf)
        conn._conn.commit()
    log(f"DONE in {(time.time()-t0)/60:.1f} min — {int(have.sum()):,} Knoten mit cited-Zentralität "
        f"(Ø {np.nanmean(cited[have]):.3f}, Ø {cnts[have].mean():.1f} zitiert).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
