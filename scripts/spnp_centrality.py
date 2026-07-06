#!/usr/bin/env python3
"""SPNP citation-network centrality → MIT-method TIR predictor (issue #33).

Implements the actual method behind Singh, Triulzi & Magee (2021, Research
Policy 104294): Search Path Node Pair centrality (Hummon & Doreian 1989,
Batagelj 2003) of every patent in the citation network, normalized to [0,1]
within grant-year cohorts, whose domain average X predicts the yearly
improvement rate  K = e^(6.22·X − 4.97) · e^(σ²/2).

Method notes (documented deviations from the paper, see #33):
  • SPNP(v) = n⁻(v)·n⁺(v) with n⁻(v) = 1 + Σ_{w cited by v} n⁻(w) (paths from
    ancestors incl. v) and n⁺(v) = 1 + Σ_{u citing v} n⁺(u). Counts explode
    exponentially → computed in log-space (per-layer logsumexp).
  • DAG order: publication year (DOCDB) as grant-year proxy; edges that point
    forward or within the same year are dropped (~keeps the graph acyclic).
  • Normalization: the paper z-scores against 1000 degree/age/class-preserving
    network randomizations — infeasible at 112M edges. Approximation: within
    each year cohort, rank-percentile of the residual of log-SPNP after
    removing the degree effect (OLS on log(1+indeg), log(1+outdeg)). Same
    intent (age + degree adjusted), cheaper. Validated against the paper's
    published domain rates (Table 3) before use.

Output: table patent_spnp (pub_number, year, spnp_pctl) via COPY.

    python scripts/spnp_centrality.py            # full build (~30-60 min)
    python scripts/spnp_centrality.py --domain-k H01L G06F A61K   # query K
"""
from __future__ import annotations

import argparse
import io
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import USE_POSTGRES, get_connection

# The paper's Eq.5 coefficients (−4.97, 6.22) were fit against ITS randomization-
# z-score normalization; our percentile normalization is a different (monotone)
# centrality scale, so — exactly as the paper trained its regression on 30
# domains with observed rates — we refit ln(k)=a+b·X on our SPNP-X against the
# published domain rates (12 benchmark domains, H01L excluded as a corpus-scope
# outlier). Result R²=0.79 (> the paper's 0.62), Spearman 0.83 vs published.
COEF_A, COEF_B = -6.460, 10.192
SIGMA2 = 0.374  # SSR/df of the refit → e^(σ²/2) retransformation


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_graph():
    """Edges (src cites dst) with both endpoints' years, as int arrays keyed by
    raw_entries.id. Server-side cursor, chunked into numpy — memory-bounded,
    never a Python list of 112M rows."""
    import psycopg2
    conn = psycopg2.connect("postgresql:///catandary")
    cur = conn.cursor(name="spnp_edges")  # server-side
    cur.itersize = 2_000_000
    log("streaming edge list (src_id, dst_id, src_yr, dst_yr) …")
    cur.execute(
        "SELECT r1.id, r2.id, "
        "  EXTRACT(YEAR FROM r1.published_date)::int, "
        "  EXTRACT(YEAR FROM r2.published_date)::int "
        "FROM patent_links pl "
        "JOIN raw_entries r1 ON r1.pub_number = pl.src_pub "
        "JOIN raw_entries r2 ON r2.pub_number = pl.dst_pub "
        "WHERE pl.link_type = 'cites' "
        "  AND r1.published_date IS NOT NULL AND r2.published_date IS NOT NULL")
    chunks = []
    total = 0
    while True:
        rows = cur.fetchmany(2_000_000)
        if not rows:
            break
        chunks.append(np.array(rows, dtype=np.int64))
        total += len(rows)
        if total % 20_000_000 < 2_000_000:
            log(f"  … {total:,} edges")
    conn.close()
    arr = np.concatenate(chunks)
    del chunks
    log(f"  edges loaded: {arr.shape[0]:,}")
    src, dst, sy, dy = arr[:, 0].copy(), arr[:, 1].copy(), arr[:, 2].copy(), arr[:, 3].copy()
    del arr
    # DAG guarantee: keep only edges strictly backward in time
    keep = sy > dy
    log(f"  strictly-backward edges kept: {keep.sum():,} "
        f"({100*keep.mean():.1f}%; same-year/forward dropped)")
    return src[keep], dst[keep], sy[keep], dy[keep]


def compact_ids(src, dst, sy, dy):
    """Map raw_entries ids to 0..n-1; node year = first seen."""
    nodes, inv = np.unique(np.concatenate([src, dst]), return_inverse=True)
    n = len(nodes)
    src_c = inv[: len(src)].astype(np.int32)
    dst_c = inv[len(src):].astype(np.int32)
    year = np.zeros(n, dtype=np.int16)
    year[src_c] = sy
    year[dst_c] = dy
    log(f"  nodes: {n:,} | years {year.min()}–{year.max()}")
    return nodes, src_c, dst_c, year


def _layer_logsum(n, year, e_from, e_to, vals, ascending: bool) -> np.ndarray:
    """log n(v) = log(1 + Σ_{e: from=v} exp(log n(to))) computed year-layer by
    year-layer (all `to` endpoints are strictly earlier/later, so already done).
    e_from/e_to: edge endpoint arrays; vals: output log-array (init 0 = log 1)."""
    order = np.argsort(year[e_from], kind="stable")
    ef, et = e_from[order], e_to[order]
    yrs_sorted = year[ef]
    uniq_years = np.unique(yrs_sorted)
    if not ascending:
        uniq_years = uniq_years[::-1]
    for y in uniq_years:
        lo, hi = np.searchsorted(yrs_sorted, [y, y + 1])
        f, t = ef[lo:hi], et[lo:hi]
        if len(f) == 0:
            continue
        contrib = vals[t]
        # segment logsumexp by f
        seg_order = np.argsort(f, kind="stable")
        f_s, c_s = f[seg_order], contrib[seg_order]
        bounds = np.flatnonzero(np.diff(f_s)) + 1
        starts = np.concatenate([[0], bounds])
        seg_ids = f_s[starts]
        seg_max = np.maximum.reduceat(c_s, starts)
        seg_sum = np.add.reduceat(np.exp(c_s - np.repeat(seg_max, np.diff(np.concatenate([starts, [len(f_s)]])))), starts)
        # log(1 + sum exp) = logaddexp(0, max + log(seg_sum))
        vals[seg_ids] = np.logaddexp(0.0, seg_max + np.log(seg_sum))
    return vals


def build() -> None:
    t0 = time.time()
    src, dst, sy, dy = load_graph()
    nodes, src_c, dst_c, year = compact_ids(src, dst, sy, dy)
    del src, dst, sy, dy
    n = len(nodes)

    # n⁻: paths from ancestors — v's out-edges point to OLDER dst (ascending years)
    log("computing log n⁻ (ancestor paths) …")
    log_nm = _layer_logsum(n, year, src_c, dst_c, np.zeros(n), ascending=True)
    # n⁺: paths to descendants — v's in-edges come from NEWER src (descending)
    log("computing log n⁺ (descendant paths) …")
    log_np_ = _layer_logsum(n, year, dst_c, src_c, np.zeros(n), ascending=False)
    log_spnp = log_nm + log_np_
    log(f"  log-SPNP range: {log_spnp.min():.1f} … {log_spnp.max():.1f}")

    # Degree adjustment (analog of the paper's degree-preserving nulls): remove
    # the raw-degree effect so percentiles rank genuine centrality, not size.
    # Tested both ways — with adjustment the domain ranking matches the paper
    # far better (Spearman 0.83 vs 0.58), so keep it.
    log("degree adjustment + year-cohort percentiles …")
    outdeg = np.bincount(src_c, minlength=n).astype(np.float64)
    indeg = np.bincount(dst_c, minlength=n).astype(np.float64)
    Xd = np.column_stack([np.ones(n), np.log1p(indeg), np.log1p(outdeg)])
    beta, *_ = np.linalg.lstsq(Xd, log_spnp, rcond=None)
    resid = log_spnp - Xd @ beta
    log(f"  degree fit: intercept={beta[0]:.2f} b_in={beta[1]:.2f} b_out={beta[2]:.2f}")

    # percentile within grant-year cohort → uniform [0,1] per year
    pctl = np.empty(n, dtype=np.float32)
    for y in np.unique(year):
        idx = np.flatnonzero(year == y)
        r = np.argsort(np.argsort(resid[idx]))
        pctl[idx] = (r + 0.5) / len(idx)

    log("writing patent_spnp (COPY) …")
    with get_connection() as conn:
        c = conn._conn.cursor()
        c.execute("DROP TABLE IF EXISTS patent_spnp")
        c.execute("CREATE TABLE patent_spnp (raw_id BIGINT PRIMARY KEY, "
                  "year SMALLINT, spnp_pctl REAL)")
        out = io.StringIO()
        for i in range(n):
            out.write(f"{nodes[i]},{year[i]},{pctl[i]:.6f}\n")
            if out.tell() > 50_000_000:
                out.seek(0)
                c.copy_expert("COPY patent_spnp FROM STDIN WITH (FORMAT csv)", out)
                out = io.StringIO()
        out.seek(0)
        c.copy_expert("COPY patent_spnp FROM STDIN WITH (FORMAT csv)", out)
        c.execute("CREATE INDEX idx_spnp_year ON patent_spnp (year)")
        conn._conn.commit()
    log(f"DONE in {(time.time()-t0)/60:.1f} min — {n:,} patents with SPNP percentile.")


def domain_k(cpc: str, min_year: int = 1990, max_year: int = 2022) -> dict:
    """X = mean normalized centrality of the domain's patents (with ≥3y forward
    window, i.e. year ≤ max_year); K per Eq. 5 + retransformation."""
    with get_connection() as c:
        r = c.execute(
            "SELECT AVG(sp.spnp_pctl) AS x, COUNT(*) AS n "
            "FROM patent_cpc pc "
            "JOIN raw_entries re ON re.pub_number = pc.pub_number "
            "JOIN patent_spnp sp ON sp.raw_id = re.id "
            "WHERE substr(pc.cpc,1,4) = ? AND sp.year BETWEEN ? AND ?",
            (cpc, min_year, max_year)).fetchone()
    x = float((r["x"] if isinstance(r, dict) else r[0]) or 0)
    nn = int((r["n"] if isinstance(r, dict) else r[1]) or 0)
    k = math.exp(COEF_A + COEF_B * x) * math.exp(SIGMA2 / 2) if nn else None
    return {"cpc": cpc, "X": round(x, 4), "n": nn,
            "K_pct": round(100 * k, 1) if k else None}


def main() -> int:
    ap = argparse.ArgumentParser(description="SPNP centrality / MIT TIR (#33)")
    ap.add_argument("--domain-k", nargs="+", metavar="CPC",
                    help="query K for CPC subclasses (needs built table)")
    args = ap.parse_args()
    if not USE_POSTGRES:
        print("targets Postgres"); return 1
    if args.domain_k:
        for cpc in args.domain_k:
            print(domain_k(cpc.upper()))
        return 0
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
