# Trend & Mega-Trend Discovery — Two-Layer Architecture

**Status:** 2026-07-03 · v1 build on the existing ~523k embedded signals (no backfill
required for v1). Supersedes the flat-silhouette global-KMeans approach and the
overlapping-scope roll-up (both shown methodologically unsound — see review below).

## Why (the methodological findings that shaped this)

- **Silhouette on raw 4096-D embeddings is broken** (distance concentration / curse of
  dimensionality → ~0.02 at every k). It is NOT evidence of "no structure"; it means the
  metric is unusable on raw embeddings. → We reduce dimensions before clustering.
- **Overlapping scopes make a "recurrence across scopes" mega-trend detector circular**
  (76 % of signals carry ≥2 verticals, so the same signal appears in up to 6 scopes). →
  Mega-trends are discovered globally and *characterized* by metrics, not by scope recurrence.
- **Cluster volume = current salience, not structural significance.** A long-lead-time
  mega-trend has few current signals (small/absent cluster); a hype cycle produces a huge
  one. → We add a maturity (lead-time) axis and tier-weighting so early signals count.

## The two layers

### Layer 1 — Scope clustering (bottom-up, customer-facing)
Fine-grained, human-interpretable trends **within a homogeneous slice**:
- **Per vertical** (`primary_vertical`): FOOD, TECH, … → the industry's Macro/Micro trends.
- **Per cross-vertical pair** (`verticals` ⊇ {A,B}): HEALTH&TECH, ECO&FOOD, … → intersection
  trends. Only pairs with enough signal/source/time depth (~30 scopes; see the scope analysis).
- **Per canonical mega-trend** (`--mega <key>`, or `NULL` for the unlabelled rest):
  the slice that answers *"is this one theme or five?"* — SPLIT evidence for curation.
  Added 2026-08-07 because global density clustering leaves ~88 % of the corpus as
  background and therefore cannot see the shape of an over-broad label from outside.
Reduced-dim + HDBSCAN per scope → clean, labelled clusters (Sonnet 5). This is the
"lens" for customers: it says *where* trends live and what the sub-themes are.

### Layer 2 — Mega-trend themes (top-altitude, still bottom-up discovery)
Discovered **globally**, then *characterized* on two axes — never mapped onto a frozen list:
- **Axis A — reach/breadth** (the "where"): how broadly a theme spans industries.
- **Axis B — maturity/lead-time** (the "when/how-deep"): where it sits and how far it
  spans the research → patent → funding → market chain.
A theme qualifies as a **mega-trend** when it is broad (Axis A) AND spans the maturity
chain (Axis B) AND durable over time. These are metrics *on* discovered themes, not the
scope structure — which removes the circularity.

The stable **canonical `mega_trends.yaml`** is the only top-down element: a curated,
customer-consistent label set. Discovery proposes NEW/SPLIT/MERGE into it; a human
curates. → living taxonomy (issue #2).

## Method (v1 — sklearn only, deterministic)

0. **Draw the sample** (`load_scope_meta` → `plan_sample` → `load_scope(ids=…)`).
   The mega layer clusters a sample, so *which* signals it draws decides what it can
   find. Two properties of the corpus (1.13M signals, 2026-08) make a naive draw
   misleading, so the draw is an explicit, reported step:
   - **The corpus is not a neutral mix.** Two feeds hold ~25 % of it (NIH RePORTER
     13.1 %, TechCrunch 11.5 %; 243 sources total). Uncapped, density clustering
     returns their house style as "themes". → `--source-cap` (default 0.05) caps any
     single source's share of the sample; the freed quota is redistributed
     **proportionally**, not equally (equalising sources would make a 300-signal blog
     as loud as a 130k wire — a much stronger claim than "no feed may dominate").
   - **The tiers are 3:1 lopsided** (market 638k · science 253k · funding 175k ·
     patent 60k). A proportional draw buries the early tiers — which is precisely
     what Axis B exists to measure. → `--strata tier` (default) balances the four
     lead-time tiers; `--strata proportional` keeps the corpus mix for comparison.
   - The old path used SQL `LIMIT n` **without `ORDER BY`** = the physically first
     n rows (≈ ingest order), i.e. an unreported, time-biased slice. `--limit` still
     exists for smoke tests and is documented as such; analysis uses `plan_sample`.
   - The realised composition (per-tier draw, which sources hit the cap, shortfalls)
     is printed and written into the candidate YAML's `_meta.sample` — a run's
     sampling is auditable after the fact.
1. **Load** embedded signals for the scope (reuse `pipeline.foresight.load_signals`
   + a cross-vertical `verticals ⊇ {A,B}` filter). Drop bogus future dates.
   `--dim1024` loads the Matryoshka 1024-prefix instead of the full vector (4× less
   text to parse). Fidelity measured on 1500 random signals (2026-08-07): Pearson
   0.944 / Spearman 0.933 against the 4096-D cosine geometry, mean |Δcos| 0.022,
   top-10-neighbour overlap 0.77 — fine for large samples, but the default stays
   4096-D because a 50k draw is affordable at full width.
2. **Reduce** 4096-D → `PCA` (randomized, fast, deterministic): ~50-D for the scope
   layer, **30-D for the mega layer** (calibrated 2026-08-07 — see
   `docs/mega_discovery_calibration.md`). *(UMAP is a later refinement; it needs
   `umap-learn` and is non-deterministic but better preserves local density for HDBSCAN.)*
3. **Cluster** with `sklearn.cluster.HDBSCAN` on the reduced space — variable density,
   **labels background as noise (−1)** instead of forcing every point into a cluster; no
   `k` to choose. Selection method **`leaf`** (calibrated default): `eom` merges the
   density hierarchy upward and at 1.13M signals returned one 7.6–11.3k super-blob in
   every setting tried. `leaf` costs a higher noise fraction (~88 %) — which is the
   same fact stated honestly: only the dense cores are themes.
4. **Characterize** each cluster:
   - `size`, `n_sources` (corroboration), top tags, representatives (nearest to medoid).
   - **`vertical_entropy`** = normalized Shannon entropy over the members' `verticals`
     (Axis A reach; 0 = single-industry, 1 = spread evenly across all 8).
   - **`tier_onsets`** per lead-time tier (science/patent/funding/market), reusing the
     `lead_time_discoverer` tier map → **`maturity_span`** = how many tiers the theme
     covers and the earliest→market lead (Axis B).
   - **`durability`** = fraction of the recent window with non-trivial monthly share
     (persistence, not a one-off spike) + SoV momentum.
   - **`mega_score`** = f(vertical_entropy, maturity_span, durability) — a principled,
     non-circular cross-cutting score. High = broad + deep + durable = mega-trend-like.
5. **Verdict** vs canonical `mega_trends.yaml` (reuse the proposer logic): NEW / SPLIT /
   MERGE / COVERED, gated on cohesion + `mega_score`.
6. **Label** NEW candidates with **Claude Sonnet 5** (better naming; `--label-backend`).
7. **Validate** — **stability**: re-run clustering under a different seed/subsample and
   report Adjusted Rand Index (ARI) of the two labelings (are clusters real or noise?).
   *(External-framework benchmark — map to WEF/Gartner/STEEP lists — and temporal
   robustness are v2.)*
8. **Read-only**: writes a candidate YAML + report; never touches `mega_trends.yaml`.

## Tier → source map (Axis B), reused from `lead_time_discoverer`
`patent` = `raw_entries.pub_number` set · `science` = `source_type='research'` +
preprints · `funding` = `api` + NSF/NIH/OpenAIRE/UKRI · `market` = trade_media/press_wire.

## Build phases

- **Phase 1 (this build, existing 523k data):** `pipeline/discovery.py` + `scripts/
  discover_trends.py` (both layers, PCA+HDBSCAN, characterization, Sonnet labels, ARI
  stability). Ships the scope layer + a mega discovery whose maturity axis is complete for
  **patent→market** (science tier shallow pre-2020 — known limit).
- **Phase 2 (enablers):** #10 distillation to production + #8 Postgres/pgvector + lazy
  embeddings → makes a large research backfill affordable.
- **Phase 3 (data depth):** #4-execute (OpenAlex concept-expansion pre-2020) + #9 (OpenAlex
  graph-layer) → fills the science tier → the maturity axis shows its *earliest*, highest-
  lead-time stage → the full research→…→market chain becomes measurable.

## Explicit non-goals / known limits of v1
- Science-tier lead-time is shallow before ~2020 → mega maturity axis leans on patents for now.
- PCA (not UMAP) → adequate, not optimal, density structure. UMAP is a v2 swap.
- External-framework validation + temporal-slice clustering are v2.
- Read-only throughout; taxonomy changes remain a human curation step.
