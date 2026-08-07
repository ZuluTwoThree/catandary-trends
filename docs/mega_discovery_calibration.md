# Mega-layer clustering: calibration against the 1.13M corpus

**Run:** 2026-08-07 · `scripts/tune_mega_clustering.py` · read-only ·
raw table in `data/discovery/tuning.json`

## Why

The mega layer's parameters (PCA dims, HDBSCAN selection method, min_cluster_size)
were set when the corpus was ~0.5M signals. At 1.13M the shipped defaults
(15-D, `eom`, `min_cluster_size = n/300`) returned **2–4 themes at 54–71 % noise**,
one of them a 20.8k-signal "Cancer Treatment · Biomedical Engineering" whose top
tags included *energy efficiency, material science, automation* — a super-blob, not
a theme. Rather than guess new values, one drawn sample (50k, tier-balanced,
5 % source cap, seed 42) was clustered under 18 parameter settings.

## What the sweep measured

Per setting: number of themes, noise fraction, median and **max** theme size, and
the architecture's own validation criterion — **stability ARI** (re-cluster an 80 %
resample, compare labelings).

Two measurement bugs were fixed first, both of which had made earlier ARI numbers
meaningless:

- `stability_ari()` re-clustered with **its own** `min_cluster_size` default
  (`max(30, n/400)`) and with HDBSCAN's `min_samples` default and always `eom` —
  i.e. it validated a *different configuration* than the one it was checking. It
  now shares `effective_mcs()` with `cluster_density()` and takes the same
  `method`/`min_samples`. (This is what produced the "ARI 0.19 — weak" verdict on
  a run whose real stability was ~0.8.)
- The sweep initially fitted one wide PCA and sliced it. Randomized SVD
  approximates a different subspace depending on how many components it is asked
  for, and production calls `reduce_dims(X, d)` — sliced-PCA results did not
  transfer (12 vs 18 themes on identical input). The sweep now fits per dim.

## Result

| dims | method | min_size | themes | noise | median n | **max n** | **ARI** |
|---:|---|---:|---:|---:|---:|---:|---:|
| 15 | eom | 60 | 12 | 75 % | 189 | 7 663 | 0.69 |
| 15 | eom | 150 | 7 | 76 % | 418 | 7 663 | 0.75 |
| 15 | eom | 400 | 4 | 76 % | 1 548 | 8 703 | 0.75 |
| 15 | leaf | 60 | 20 | 90 % | 130 | 953 | 0.64 |
| 15 | leaf | 150 | 9 | 85 % | 522 | 2 143 | 0.76 |
| 15 | leaf | 400 | 6 | 87 % | 913 | 2 143 | 0.69 |
| 30 | eom | 60 | 8 | 72 % | 626 | 8 856 | 0.69 |
| 30 | eom | 150 | 5 | 72 % | 1 036 | 9 210 | 0.70 |
| 30 | eom | 400 | 4 | 73 % | 1 695 | 9 210 | 0.71 |
| 30 | leaf | 60 | 23 | 92 % | 130 | 480 | 0.63 |
| **30** | **leaf** | **150** | **8** | **88 %** | **521** | **2 355** | **0.84** |
| 30 | leaf | 400 | 5 | 85 % | 1 036 | 2 355 | 0.79 |
| 50 | eom | 60 | 8 | 71 % | 169 | 11 324 | 0.72 |
| 50 | eom | 150 | 5 | 71 % | 237 | 11 324 | 0.35 |
| 50 | eom | 400 | 2 | 71 % | 7 184 | 11 324 | 0.57 |
| 50 | leaf | 60 | 22 | 92 % | 150 | 514 | 0.60 |
| 50 | leaf | 150 | 13 | 89 % | 228 | 2 684 | 0.76 |
| 50 | leaf | 400 | 4 | 88 % | 1 332 | 3 045 | 0.67 |

PCA explained variance: 15-D = 20.3 % · 30-D = 27.7 % · 50-D = 34.7 %.

## Decisions

1. **`leaf` replaces `eom` as the mega-layer default.** `eom` merges the density
   hierarchy upward, and at this heterogeneity that produces one 7.6–11.3k blob in
   *every* configuration (15–23 % of the sample declared a single "theme"). `leaf`
   caps the largest theme at 0.5–3k across the board. The cost is a higher noise
   fraction, which is the honest version of the same fact: `eom`'s lower noise came
   from the blob swallowing points, not from explaining them.
2. **30 PCA dims** (`MEGA_REDUCE_DIM` 15 → 30). Best stability (0.84) and the only
   dim where both methods stay coherent. More is not better — 50-D `eom` collapses
   to ARI 0.35; explained variance keeps rising while cluster structure degrades,
   the usual distance-concentration behaviour.
3. **`min_cluster_size` keeps the `max(100, n/300)` formula** (= 166 at n = 50k),
   which sits in the measured optimum (0.84 at 150, 0.79 at 400, 0.63 at 60). It
   scales with the sample, which a pinned constant would not.

## The limit this exposes

At the calibrated optimum, **~88 % of the sample is background** — roughly 6 000 of
50 000 signals sit in a stable density mode at mega altitude. Global density
clustering is therefore a *narrow* instrument for taxonomy work: it reliably finds
the few dense cores, not the shape of the whole corpus. The complementary move is
to cluster **inside** a canonical mega-trend (`--layer scope --mega <key>`, added
the same day), where the slice is homogeneous, KMeans places every signal, and the
question — "is this one theme or five?" — is the one curation actually needs.
