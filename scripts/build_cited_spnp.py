#!/usr/bin/env python3
"""WS1: Precompute the CITED-centrality predictor per patent (the canonical MIT
predictor, proven better than own-centrality — mit_calibrate.py: R² 0.62 vs 0.55).

For every citing patent, the mean SPNP percentile of the patents it CITES. Stored
once so the trajectory's per-year aggregate stays as fast as the own-centrality path
(a plain join), instead of the ~18s live patent_links join.

    python scripts/build_cited_spnp.py --spnp patent_spnp_full_z3 --out patent_citedspnp_full_z3
"""
from __future__ import annotations
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db import get_connection


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spnp", default="patent_spnp_full_z3")
    ap.add_argument("--out", default="patent_citedspnp_full_z3")
    args = ap.parse_args()
    t0 = time.time()
    with get_connection() as conn:
        c = conn._conn.cursor()
        c.execute("SET statement_timeout='0'")
        c.execute("SET work_mem='2GB'")
        log(f"building {args.out} from {args.spnp} × patent_links (cites) …")
        c.execute(f"DROP TABLE IF EXISTS {args.out}")
        # cited_pctl = mean SPNP percentile of the patents each src cites.
        c.execute(
            f"CREATE TABLE {args.out} AS "
            f"SELECT l.src_pub AS pub_number, AVG(sp.spnp_pctl)::real AS cited_pctl, "
            f"       COUNT(*)::int AS n_cited "
            f"FROM patent_links l JOIN {args.spnp} sp ON sp.pub_number = l.dst_pub "
            f"WHERE l.link_type = 'cites' "
            f"GROUP BY l.src_pub")
        conn._conn.commit()
        c.execute(f"CREATE INDEX idx_{args.out}_pub ON {args.out}(pub_number)")
        c.execute(f"SELECT COUNT(*), AVG(cited_pctl), AVG(n_cited) FROM {args.out}")
        n, avg, avgn = c.fetchone()
        conn._conn.commit()
    log(f"DONE in {(time.time()-t0)/60:.1f} min — {n:,} patents with cited-centrality "
        f"(mean {float(avg):.3f}, avg {float(avgn):.1f} cited each).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
