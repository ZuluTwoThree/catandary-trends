#!/usr/bin/env python3
"""SPNP centrality on the FULL graph, straight from the Parquet staging (#35).

Reuses the exact vectorized SPNP math from spnp_centrality (_layer_logsum: layered
log-sum-exp of ancestor/descendant path counts over the strictly-backward DAG,
degree adjustment, within-grant-year percentile). Loads nodes+edges from the
staging shards (112M nodes / 260M edges), so it needs NOTHING in Postgres and
covers the technology-neutral graph (fixes the A61B absolute-rate bias).

Output: table `patent_spnp_staging` (pub_number TEXT PK, year SMALLINT, spnp_pctl
REAL) — a NEW table, so the live `patent_spnp` (raw_id-keyed) is untouched until we
deliberately swap. Memory-hardened: node ids are int32 (max ~112M << 2.1B).

    python scripts/spnp_from_staging.py --staging /mnt/data-hdd/patent_staging
    python scripts/spnp_from_staging.py --limit 5   # subset for a correctness test
"""
from __future__ import annotations

import argparse
import glob
import io
import os
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db import get_connection
from scripts.spnp_centrality import _layer_logsum

UNKNOWN_YEAR = np.int32(-32768)


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def load_graph_staging(staging: str, limit: int = 0, class_chars: int = 3):
    """→ (nodes_pub, src_c, dst_c int32, year int32, cls int32 per node). Edges are
    filtered to strictly-backward-in-time (DAG) with both endpoints dated. `cls` is
    the node's main technology class (first CPC code, first `class_chars` chars,
    encoded to an int id; -1 = unknown) for class-aware normalization (#35)."""
    efiles = sorted(glob.glob(f"{staging}/edges-*.parquet"))
    nfiles = sorted(glob.glob(f"{staging}/nodes-*.parquet"))
    if limit:
        efiles, nfiles = efiles[:limit], nfiles[:limit]

    log(f"loading {len(efiles)} edge shards …")
    # large_string (int64 offsets): the concatenated endpoint array is >2GB of
    # bytes, which overflows arrow's int32-offset `string` type.
    src_chunks, dst_chunks = [], []
    for f in efiles:
        t = pq.read_table(f, columns=["src", "dst"])
        src_chunks.append(t.column("src").combine_chunks().cast(pa.large_string()))
        dst_chunks.append(t.column("dst").combine_chunks().cast(pa.large_string()))
    n_edges = sum(len(c) for c in src_chunks)
    log(f"  {n_edges:,} raw edges — factorizing pub_number → int32 node id …")
    both = pa.concat_arrays(src_chunks + dst_chunks); del src_chunks, dst_chunks
    enc = pc.dictionary_encode(both); del both
    codes = enc.indices.to_numpy(zero_copy_only=False).astype(np.int32)
    nodes_pub = enc.dictionary            # unique pub_numbers = graph nodes
    del enc
    n = len(nodes_pub)
    src_c = codes[:n_edges].copy(); dst_c = codes[n_edges:].copy(); del codes
    log(f"  {n:,} distinct graph nodes")

    # node → year, resolved per shard via index_in against the node set. NOT an
    # arrow join: pub_numbers recur across delivery shards (same publication in
    # several files), and a join on duplicated keys blows up (std::length_error).
    # index_in maps each shard row to its graph-node id (null if not a node);
    # memory-bounded per shard, last write wins (same patent → same year).
    log(f"loading node years + main class from {len(nfiles)} node shards …")
    year = np.full(n, UNKNOWN_YEAR, dtype=np.int32)
    node_cls = np.full(n, -1, dtype=np.int32)
    cls_map: dict[str, int] = {}
    for f in nfiles:
        t = pq.read_table(f, columns=["pub_number", "year", "cpc"])
        pubs = t.column("pub_number").combine_chunks().cast(pa.large_string())
        ids = pc.index_in(pubs, value_set=nodes_pub).to_numpy(zero_copy_only=False).astype("float64")
        yrs = t.column("year").to_numpy(zero_copy_only=False).astype("float64")
        mask = ~np.isnan(ids) & ~np.isnan(yrs)
        idn = ids[mask].astype(np.int64)
        year[idn] = yrs[mask].astype(np.int32)
        # main class = first CPC code truncated to class_chars (null-safe: rows with
        # an empty CPC list get None), encoded to a global id.
        lst = t.column("cpc").combine_chunks()
        codes = pc.list_flatten(lst)
        parent = pc.list_parent_indices(lst).to_numpy(zero_copy_only=False)
        cls_rows = np.full(len(lst), "", dtype=object)        # "" = unknown/empty sentinel
        if len(parent):
            change = np.empty(len(parent), dtype=bool)
            change[0] = True; change[1:] = np.diff(parent) != 0
            fp = np.flatnonzero(change)                       # first code index per present row
            first_cls = pc.utf8_slice_codeunits(pc.take(codes, pa.array(fp)),
                                                0, class_chars).to_pylist()
            cls_rows[parent[fp]] = [c if c else "" for c in first_cls]
        su, sinv = np.unique(cls_rows, return_inverse=True)
        gid = np.array([-1 if s == "" else cls_map.setdefault(s, len(cls_map))
                        for s in su], dtype=np.int32)
        node_cls[idn] = gid[sinv][mask]

    # strictly-backward DAG: citing (src) newer than cited (dst), both dated
    sy, dy = year[src_c], year[dst_c]
    keep = (sy > dy) & (sy > 0) & (dy > 0)
    log(f"  strictly-backward dated edges: {keep.sum():,} ({100*keep.mean():.1f}%)")
    src_k, dst_k = src_c[keep], dst_c[keep]; del src_c, dst_c, sy, dy, keep
    # re-compact to CONNECTED nodes only (endpoints of a kept backward edge) —
    # matches spnp_centrality semantics; isolated/undated nodes carry no measurable
    # centrality and must not pollute the year-cohort percentiles.
    uniq, inv = np.unique(np.concatenate([src_k, dst_k]), return_inverse=True)
    m = len(src_k)
    src_new = inv[:m].astype(np.int32); dst_new = inv[m:].astype(np.int32); del inv
    nodes_conn = nodes_pub.take(pa.array(uniq))
    year_conn = year[uniq]
    cls_conn = node_cls[uniq]
    log(f"  connected graph: {len(uniq):,} nodes, {m:,} edges, "
        f"{len(cls_map):,} distinct classes")
    return nodes_conn, src_new, dst_new, year_conn, cls_conn


def _grouped_percentile(resid, year, cls, min_group: int = 50) -> np.ndarray:
    """Rank-percentile of resid within (year × class) cohorts — corrects both the
    time- AND class-specific SPNP biases the paper flags (Triulzi 2020 §5.3). Groups
    smaller than min_group fall back to a year-only percentile (rare classes stay
    stable). Undated nodes (year<=0) are left at 0 (skipped at write)."""
    n = len(resid)
    pctl = np.zeros(n, dtype=np.float32)
    key = year.astype(np.int64) * 100000 + (cls.astype(np.int64) + 1)
    order = np.lexsort((resid, key))          # primary key, secondary resid (ascending)
    sk = key[order]
    bnd = np.flatnonzero(np.diff(sk)) + 1
    starts = np.concatenate(([0], bnd)); ends = np.concatenate((bnd, [n]))
    small = np.zeros(n, dtype=bool)
    ps = np.empty(n, dtype=np.float32)
    for s, e in zip(starts, ends):
        m = e - s
        if m >= min_group:
            ps[s:e] = (np.arange(m) + 0.5) / m
        else:
            small[order[s:e]] = True
    pctl[order] = ps
    # year-only fallback for small (year×class) groups
    idxs = np.flatnonzero(small & (year > 0))
    if len(idxs):
        o2 = np.lexsort((resid[idxs], year[idxs]))
        syk = year[idxs][o2]
        b2 = np.flatnonzero(np.diff(syk)) + 1
        st2 = np.concatenate(([0], b2)); en2 = np.concatenate((b2, [len(idxs)]))
        pf = np.empty(len(idxs), dtype=np.float32)
        for s, e in zip(st2, en2):
            pf[s:e] = (np.arange(e - s) + 0.5) / (e - s)
        pctl[idxs[o2]] = pf
    return pctl


def _spnp(n, year, src_c, dst_c, fmask=None):
    """observed log-SPNP = log n⁻ + log n⁺ (ancestor + descendant path counts).

    n⁻ (what a patent cites, backward) uses ALL edges — a patent's references are
    complete at grant. n⁺ (who cites a patent, forward) grows over time and biases
    older patents; passing `fmask` (forward edges with citation-age ≤ cap) measures
    every patent's forward centrality at a FIXED age — the 'graph as of grant+age'
    reconstruction that makes cohorts comparable and removes the immaturity bias."""
    lm = _layer_logsum(n, year, src_c, dst_c, np.zeros(n), ascending=True)
    if fmask is None:
        lp = _layer_logsum(n, year, dst_c, src_c, np.zeros(n), ascending=False)
    else:
        lp = _layer_logsum(n, year, dst_c[fmask], src_c[fmask], np.zeros(n), ascending=False)
    return lm + lp


def _randomized_zscore(n, year, cls, src_c, dst_c, log_spnp_obs, R, seed=0, fmask=None):
    """Normalize SPNP by the paper's citation-network randomization null (Triulzi
    2020): compare each patent's observed log-SPNP to its distribution over R random
    networks that preserve — per patent — in/out-degree, citation-age profile, and
    same-class citation share. Return z-score per node.

    The constrained edge-swap is implemented exactly as a grouped permutation of the
    dst endpoints within buckets (year_src, year_dst, class_src, same_class_flag):
    permuting dst inside such a bucket preserves every conserved quantity, is
    swap-invariant, keeps the strictly-backward DAG (year_dst fixed), and is fully
    vectorized (no rejection sampling)."""
    m = len(src_c)
    ys = year[src_c].astype(np.int64); yd = year[dst_c].astype(np.int64)
    cs = cls[src_c].astype(np.int64); cd = cls[dst_c].astype(np.int64)
    ncls = int(cls.max()) + 2
    same = (cs == cd).astype(np.int64)
    bucket = ((ys * 3000 + yd) * ncls + (cs + 1)) * 2 + same
    del ys, yd, cs, cd, same
    base_order = np.argsort(bucket, kind="stable")
    rng = np.random.default_rng(seed)
    s1 = np.zeros(n); s2 = np.zeros(n)
    for r in range(R):
        shuf = np.lexsort((rng.random(m), bucket))    # bucket-major, random within bucket
        dst_r = np.empty_like(dst_c)
        dst_r[base_order] = dst_c[shuf]
        # fmask is position-based; the bucket permutation preserves year_dst per
        # position, so the citation-age (hence the cap) is invariant under the swap.
        ls = _spnp(n, year, src_c, dst_r, fmask)
        s1 += ls; s2 += ls * ls
        if (r + 1) % 10 == 0:
            log(f"  randomization {r+1}/{R}")
    mean = s1 / R
    var = np.maximum(s2 / R - mean * mean, 1e-9)
    return (log_spnp_obs - mean) / np.sqrt(var)


def _save_cache(path, nodes_pub, src_c, dst_c, year, cls):
    np.savez(path + ".npz", src=src_c, dst=dst_c, year=year, cls=cls)
    pq.write_table(pa.table({"pub": nodes_pub}), path + ".pub.parquet")


def _load_cache(path):
    d = np.load(path + ".npz")
    nodes_pub = pq.read_table(path + ".pub.parquet").column("pub").combine_chunks()
    return nodes_pub, d["src"], d["dst"], d["year"], d["cls"]


def build(staging: str, limit: int = 0, class_chars: int = 3, randomize: int = 0,
          age_cap: int = 0, cache: str = "", us_utility: bool = False,
          out_table: str = "patent_spnp_staging", year_only_pctl: bool = False,
          seed: int = 0) -> None:
    t0 = time.time()
    if cache and os.path.exists(cache + ".npz"):
        log(f"loading cached connected graph from {cache} …")
        nodes_pub, src_c, dst_c, year, cls = _load_cache(cache)
    else:
        nodes_pub, src_c, dst_c, year, cls = load_graph_staging(staging, limit, class_chars)
        if cache:
            log(f"caching connected graph to {cache} …")
            _save_cache(cache, nodes_pub, src_c, dst_c, year, cls)
    n = len(nodes_pub)

    if us_utility:
        # Path A: restrict to the US utility-patent-GRANT subgraph — the corpus the
        # MIT method was designed and rate-calibrated on (Singh 2021 §3/App C: US
        # granted utility patents). Grant kind codes A (pre-2001), B1, B2 (post-2001);
        # excludes application publications A1/A2/A9 (separate documents that only
        # fragment the citation paths — ~3.7M of our US nodes) and non-utility. Keep
        # only edges with BOTH endpoints in-scope, then re-compact.
        log("filtering to US-utility-GRANT subgraph …")
        node_mask = pc.match_substring_regex(
            nodes_pub, "^US-[0-9]+-(A|B1|B2)$").to_numpy(zero_copy_only=False)
        ekeep = node_mask[src_c] & node_mask[dst_c]
        src_k, dst_k = src_c[ekeep], dst_c[ekeep]; del src_c, dst_c, ekeep
        uniq, inv = np.unique(np.concatenate([src_k, dst_k]), return_inverse=True)
        m = len(src_k)
        src_c = inv[:m].astype(np.int32); dst_c = inv[m:].astype(np.int32); del inv
        nodes_pub = nodes_pub.take(pa.array(uniq))
        year = year[uniq]; cls = cls[uniq]
        n = len(nodes_pub)
        log(f"  US-utility connected subgraph: {n:,} nodes, {m:,} edges "
            f"({100*node_mask.mean():.0f}% of full-graph nodes were US-utility)")

    # forward-citation age cap: measure every patent's n⁺ at a fixed age (the
    # 'graph as of grant+cap' reconstruction). Position-based mask, reused per
    # randomization (bucket permutation preserves citation-age).
    fmask = None
    if age_cap > 0:
        fmask = (year[src_c].astype(np.int64) - year[dst_c].astype(np.int64)) <= age_cap
        log(f"forward age cap = {age_cap}y: {100*fmask.mean():.1f}% of edges kept for n⁺")

    log("computing observed log-SPNP …")
    log_spnp = _spnp(n, year, src_c, dst_c, fmask)

    if randomize > 0:
        log(f"randomization null: {randomize}× degree+age+class-preserving swaps → z-score …")
        z = _randomized_zscore(n, year, cls, src_c, dst_c, log_spnp, randomize,
                               seed=seed, fmask=fmask)
        del src_c, dst_c, log_spnp
        log("year-cohort percentiles of z-score …")
        pctl = _grouped_percentile(z, year, np.zeros(n, dtype=np.int32))
    else:
        log("degree adjustment + (year × class) percentiles …")
        outdeg = np.bincount(src_c, minlength=n).astype(np.float64)
        indeg = np.bincount(dst_c, minlength=n).astype(np.float64)
        del src_c, dst_c
        Xd = np.column_stack([np.ones(n), np.log1p(indeg), np.log1p(outdeg)])
        beta, *_ = np.linalg.lstsq(Xd, log_spnp, rcond=None)
        resid = log_spnp - Xd @ beta
        del Xd, log_spnp, indeg, outdeg
        log(f"  degree fit: intercept={beta[0]:.2f} b_in={beta[1]:.2f} b_out={beta[2]:.2f}")
        # year-only percentile (cls=0) for a cross-domain-comparable scale: the
        # trajectory's domain X IS a CPC set, so a (year×class) percentile would rank
        # each patent within its own class → every domain collapses to ~0.5 and the
        # cross-domain signal (the thing K measures) is destroyed. year-only ranks
        # against the technology-neutral population — and on the balanced full-archive
        # corpus that is exactly what pulls the A61B over-centrality back to true (#35).
        pctl_cls = np.zeros(n, dtype=np.int32) if year_only_pctl else cls
        pctl = _grouped_percentile(resid, year, pctl_cls)

    log(f"writing {out_table} (COPY) …")
    copy_sql = f"COPY {out_table} FROM STDIN WITH (FORMAT csv)"
    pubs = nodes_pub.to_pylist()
    with get_connection() as conn:
        c = conn._conn.cursor()
        c.execute(f"DROP TABLE IF EXISTS {out_table}")
        c.execute(f"CREATE TABLE {out_table} (pub_number TEXT PRIMARY KEY, "
                  "year SMALLINT, spnp_pctl REAL)")
        out = io.StringIO()
        written = 0
        for i in range(n):
            if year[i] <= 0:
                continue  # undated → not in any cohort, skip
            out.write(f"{pubs[i]},{year[i]},{pctl[i]:.6f}\n")
            if out.tell() > 50_000_000:
                out.seek(0); c.copy_expert(copy_sql, out)
                written += out.tell(); out = io.StringIO()
        out.seek(0); c.copy_expert(copy_sql, out)
        c.execute(f"CREATE INDEX idx_{out_table}_year ON {out_table} (year)")
        conn._conn.commit()
    log(f"DONE in {(time.time()-t0)/60:.1f} min — {n:,} graph nodes, SPNP percentile written.")


def main() -> int:
    ap = argparse.ArgumentParser(description="SPNP on the full graph from Parquet staging (#35)")
    ap.add_argument("--staging", default="/mnt/data-hdd/patent_staging")
    ap.add_argument("--limit", type=int, default=0, help="cap shards (subset correctness test)")
    ap.add_argument("--class-chars", type=int, default=3,
                    help="CPC prefix length for the class used in the null / cohort "
                         "(1=section, 3=class, 4=subclass)")
    ap.add_argument("--randomize", type=int, default=0,
                    help="R randomizations for the z-score null (0=degree-regression "
                         "fallback; 50-100 = faithful-light method)")
    ap.add_argument("--age-cap", type=int, default=0,
                    help="forward-citation age cap in years (0=all; e.g. 3 = measure "
                         "each patent's centrality at grant+3, cohort complete when "
                         "year+cap <= now)")
    ap.add_argument("--cache", default="",
                    help="path prefix to cache/reuse the loaded connected graph "
                         "(skips the ~25min node-load on re-runs)")
    ap.add_argument("--us-utility", action="store_true",
                    help="Path A: restrict to the US utility-patent subgraph (the "
                         "MIT-method corpus) before computing SPNP")
    ap.add_argument("--out-table", default="patent_spnp_staging",
                    help="destination table (default patent_spnp_staging; use "
                         "patent_spnp_full for the #35 technology-balanced backfill)")
    ap.add_argument("--year-only-pctl", action="store_true",
                    help="rank the degree residual within grant-YEAR only (cross-domain-"
                         "comparable, matches patent_spnp) instead of (year×class)")
    ap.add_argument("--seed", type=int, default=0,
                    help="RNG seed for the randomization null (default 0 = "
                         "historical behavior; vary for replicate/ablation runs)")
    args = ap.parse_args()
    build(args.staging, args.limit, args.class_chars, args.randomize, args.age_cap,
          args.cache, args.us_utility, args.out_table, args.year_only_pctl,
          args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
