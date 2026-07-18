# Catandary Trends

Cross-industry **trend & foresight intelligence platform**, running end-to-end
on local LLMs. It acquires innovation signals across the entire maturity chain
— **science → patents → funding → market** — classifies them with a local
multi-stage pipeline (plus a distilled, embedding-based fast path for mass
ingest), and derives foresight artifacts on top: data-driven trend clusters,
technology improvement rates from the patent citation graph, and cross-tier
lead-time analysis on a common CPC technology axis. Curated trend articles are
published through a Next.js frontend at `catandary.de/trends`.

See [`CLAUDE.md`](CLAUDE.md) for the architecture & taxonomy contract. The
living backlog is in the
[GitHub issues](https://github.com/ZuluTwoThree/catandary-trends/issues);
`BACKLOG.md` is only the issue overview + milestone history.

---

## Contents

- [Architecture](#architecture)
- [Requirements & setup](#requirements--setup)
- [Configuration](#configuration)
- [Daily pipeline](#daily-pipeline)
- [Distilled fast path (mass ingest)](#distilled-fast-path-mass-ingest)
- [Acquisition layer](#acquisition-layer)
- [Foresight engine](#foresight-engine)
- [Frontend](#frontend)
- [Operations](#operations)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Engineering conventions](#engineering-conventions)
- [Status](#status)

---

## Architecture

```
        ACQUISITION (lead-time tiers)                PROCESSING                     PRODUCT
┌──────────────────────────────────────────┐  ┌────────────────────────┐  ┌───────────────────────┐
│ science   OpenAlex graph sweep, preprints│  │ Stage pipeline         │  │ Next.js frontend      │
│ patent    EPO BDDS back-file + OPS       │─▶│  relevance → extract → │─▶│  /trends (published)  │
│ funding   NSF/NIH/OpenAIRE/UKRI +        │  │  classify → dedup →    │  │  FTS + pgvector ANN   │
│           SEC Form D (startup rounds)    │  │  content → publish     │  │                       │
│ market    RSS poller + WordPress         │  │ backends: llama.cpp /  │  │ Foresight engine      │
│           archives, press wires          │  │  Ollama / distill /    │  │  clusters, TIR,       │
└──────────────────────────────────────────┘  │  Anthropic (fallback)  │  │  lead-time, CPC axes  │
                                              └────────────────────────┘  └───────────────────────┘
              all state in PostgreSQL + pgvector · SQLite = frozen fallback & test backend
```

**Taxonomy.** Eight verticals (`FOOD TECH HEALTH ECO DESIGN FASHION BIZ
LIFESTYLE`), cross-cutting PESTEL dimensions (P/E/S/T/En/L), and
Mega/Macro/Micro trend levels. Every signal additionally carries a
**lead-time tier** — the maturity stage it was observed at. Research precedes
patents, patents precede funding, funding precedes market coverage; measuring
that offset per technology is the core foresight capability, and every tier
has historical depth (to 1990 for science and patents) so the offsets are
real, not acquisition artifacts.

**Principles.** Legal primary sources only (no aggregator scraping), source
attribution is mandatory, generated content must differ substantially from the
original, all LLM inference is local (cloud APIs are opt-in fallbacks), and
new sources are added via `sources.yaml` — no code changes.

---

## Requirements & setup

| Component | Notes |
|---|---|
| Python 3.12+ | virtualenv at `.venv/` |
| PostgreSQL 16+ with `pgvector` | production database `catandary`, peer auth via local socket |
| Node.js 20+ | frontend only |
| NVIDIA GPU, 24 GB VRAM | verified on RTX 3090; models run **sequentially**, never in parallel |
| [llama.cpp](https://github.com/ggerganov/llama.cpp) `llama-server` | port `8090`, systemd user unit `llama-server.service` — production backend for **all** LLM stages |
| [Ollama](https://ollama.com/) on `127.0.0.1:11434` | default/fallback backend |
| Anthropic API key *(optional)* | off-GPU classification fallback and one-off repair jobs |

```bash
# Ollama models (fallback path)
ollama pull qwen3:8b          # relevance / extraction / classification
ollama pull qwen3:14b         # content generation (EN)
ollama pull qwen3-embedding   # embeddings (4096-dim, multilingual)

# Python + frontend
pip install -r requirements.txt
(cd frontend && npm install)

# Database — creates/migrates all tables incl. the graph & foresight layers
python scripts/setup_db.py
```

For the low-resource laptop path (8 GB, no GPU) see
[`MACBOOK_SETUP.md`](MACBOOK_SETUP.md).

## Configuration

Copy `.env.example` → `.env`. The switches that matter:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql:///catandary` for the pipeline. **Leave unset for the frontend in production** — it connects through the local socket (`lib/pg.ts`); a TCP URL breaks peer auth. |
| `DATABASE_PATH` | SQLite path — only used by the frozen fallback and the test suite |
| `STAGE_8B_BACKEND` | relevance/extract/classify/reclassify: `ollama` \| `llamacpp` |
| `EMBED_BACKEND` | embeddings: `ollama` \| `llamacpp` |
| `STAGE5_BACKEND` | content generation: `ollama` (qwen3:14b) \| `llamacpp` (**Gemma-4-26B-A4B** — current since #11/2026-07-14; Qwen3-30B-A3B and 35B remain installed and revertible via `STAGE5_MODEL`/`STAGE5_START`) |
| `CLASSIFY_BACKEND` | `ollama` \| `llamacpp` \| `anthropic` (moves stages 2/3/4/8 off-GPU, API cost) |
| `OPENALEX_API_KEY`, `EPO_OPS_*`, `EPO_LOGIN`/`EPO_PASSWORD` | acquisition APIs (science / patents) |

`scripts/scheduled_cycle.sh` sets the `llamacpp` backends automatically when
the matching start scripts are present — in production the **entire** cycle
runs on `llama-server` (:8090) and Ollama is not required at runtime.

**GPU coexistence** is managed by `pipeline/gpu_handover.py`: it stops/starts
`llama-server`, swaps the `start-active.sh` symlink to the model a stage
needs, verifies VRAM headroom, and restores the previous state afterwards.
The resting llama-server holds ~22 GB — **check `nvidia-smi` before any manual
model load**.

---

## Daily pipeline

```
RSS feeds ──► feed_poller ──► raw_entries
                                  │
                                  ▼
                       llm_processor (run_pipeline_batch)
                        1. title dedup          (no LLM, rapidfuzz)
                        2. relevance filter     ┐
                        3. structured extract   │ 8B  (llama.cpp / Ollama /
                        4. NER + classify       ┘      Anthropic)
                        5. dedup via embedding  (qwen3-embedding, cosine > 0.92)
                        6. content EN           (llama.cpp Gemma-26B / Ollama 14B)
                        7. insert trends        (draft | signal)
                        8. reclassify verticals (8B)
                        9. auto-publish         (confidence ≥ 0.85)
                                  │
                                  ▼
                          trends (published) ──► Next.js frontend
```

```bash
scripts/scheduled_cycle.sh 600                 # reference off-hours run: poll + stages,
                                               # watermark-scoped, GPU/service wrapper
python -m pipeline.feed_poller                 # RSS poll only (all verticals)
python -m pipeline.feed_poller FOOD TECH       # subset
python -m pipeline.run_full_cycle --batch 600  # poll + stages, no service wrapper
python -m pipeline.run_full_cycle --skip-poll --batch 600   # drain existing backlog
python -m pipeline.llm_processor 200           # stages only, batch of 200
python -m pipeline.llm_processor 200 --signal-mode  # classify+embed only → status='signal'
```

Notes:

- **Articles are EN-only** — DE generation is suspended; `*_de` columns stay
  `NULL` (schema kept for a possible reactivation). Non-English sources are
  translated, never echoed.
- **`--signal-mode`** skips content generation and inserts content-less
  `status='signal'` rows (classification + embedding only) for fast foresight
  density. Articles can be generated later, decoupled:

```bash
python scripts/generate_content.py --vertical FOOD --limit 200
python scripts/generate_content.py --all --chunk 200
python -m pipeline.auto_publisher              # standalone publish fallback (≥ 0.85)
python -m pipeline.mega_trend_reviewer         # assign/refresh mega-trends (batched)
```

### Review CLI

```bash
python scripts/review_cli.py list draft
python scripts/review_cli.py show <id>
python scripts/review_cli.py publish <id>
python scripts/review_cli.py review            # interactive
python scripts/review_cli.py stats
python scripts/verify_feeds.py                 # validate feed URLs in sources.yaml
```

## Distilled fast path (mass ingest)

Linear heads on the 4096-dim embeddings replace the three 8B calls
(relevance, classification, mega-trend) for classification-only workloads —
roughly an order of magnitude faster; the batched embedding pass is the only
GPU work. This is what makes broad acquisition affordable
(*acquire broad, classify cheap*).

```bash
# classify a backfill scope into status='signal' rows (embed → heads →
# relevance gate 0.5 → dedup → insert); the wrapper handles the GPU handover
python scripts/run_distill_batch.py --source-type research --limit 0

# dry-run / cost projection and backend selection live in signal_batch itself
python scripts/signal_batch.py --limit 5000                    # dry-run
python scripts/signal_batch.py --backend distill --execute ...

# retrain the heads (vertical 85% · mega 78%/96% top-1/top-3 ·
# PESTEL 84% F1 · relevance P85/R88)
python scripts/train_distill_heads.py
```

`scripts/discovery_loop.py` (cron, Sun 06:00) re-discovers clusters, curates
the mega-trend taxonomy, and **auto-retrains the heads** when
`mega_trends.yaml` changes.

---

## Acquisition layer

RSS carries only the newest ~10–50 items per feed. The ingesters below give
every lead-time tier **historical depth** — all GPU-free, batched inserts,
idempotent on URL:

| Tier | Script | Source & depth |
|---|---|---|
| science | `scripts/ingest_openalex.py` | OpenAlex works. `--graph <topic\|subfield\|search>` pulls the graph layer (citations, topics, native forward velocity); `--science-sweep ALL --after 1990-01-01` sweeps all 82 vertical-relevant subfields, citation-gated |
| science | `scripts/ingest_preprints.py` | arXiv / bioRxiv / medRxiv |
| patent | `scripts/ingest_patents.py` | EPO **BDDS DOCDB back-file** (`--source epo-bdds`): 162 files ≈ 205 GB, archived on HDD for re-parses → 18.7M in-scope patents, 112M citation edges, 131M CPC rows, back to 1990. `--source epo-ops` for targeted OPS pulls |
| funding | `scripts/ingest_funding.py` | NSF (to 1959) / NIH RePORTER / OpenAIRE / UKRI — `--since 2005` |
| funding | `scripts/ingest_secform_d.py` | **SEC Form D** structured quarterly data sets (2008+): startup private offerings (Reg D), operating companies only — pooled funds/real estate dropped |
| market | `scripts/ingest_wordpress.py` | Full WordPress archives of our trade sources: `--probe` lists the ~41 WP-capable sources with archive sizes, `--all` deep-sweeps them (respects per-source `wp_categories` scoping; skips `ingest_cap`'d low-yield giants). Single-source mode for scoped pulls |
| market | `pipeline/feed_poller.py` | RSS/Atom, configured in `sources.yaml` |
| any | `scripts/ingest_backfill.py` | router: probes each source (`probe_source_apis.py`) and dispatches to WP / OpenAlex / sitemap |

Backfilled entries are then classified via the distilled fast path (above) or,
off-GPU, with `CLASSIFY_BACKEND=anthropic python -m pipeline.llm_processor
--signal-mode`.

---

## Foresight engine

The product core: reasoning **in the data**, not in generated text.

| Capability | Entry point | Method |
|---|---|---|
| Trend discovery (two layers) | `scripts/discover_trends.py` → `pipeline/discovery.py` | PCA 4096→50, then **scope layer** (KMeans partition per vertical / cross-vertical pair — customer-facing sub-themes) and **mega layer** (HDBSCAN density, characterized on reach-entropy × maturity × durability) |
| Cluster snapshots & momentum | `pipeline/foresight_snapshot.py` | SoV time series per cluster, persisted to `foresight_runs`/`foresight_clusters` for the frontend. `--dim1024` clusters the **full ~1.1M-signal space** (Matryoshka 1024-d column); `--all-verticals` after large ingests. Validated: `scripts/foresight_validation.py` → 23/24 known-trend recovery, 6/6 momentum plausibility |
| Cross-tier fusion (lead time) | `scripts/build_cpc_tier_series.py` | materializes all four tiers on the shared CPC axis — `cpc_tier_series` (per cpc/tier/year), `cpc_tier_totals` (SoV denominators), `cpc_leadtime_summary`. Lead-time uses SoV S-curve takeoff over each pair's **common support window** + emergence/signal gates, so only technologies the corpus can prove get a `reliable` lead (no fabricated long leads); reads from the #28 `signal_cpc` projection |
| Field-normalized science velocity | `scripts/openalex_velocity.py` | `velocity_3y` (native `counts_by_year`) + subfield percentile (`velocity_pctl`); retracted works excluded as a negative signal |
| Technology Improvement Rate | `scripts/tir_metrics.py --cpc A23C` | patent-cluster metrics from the citation graph: **Cycle Time** (median backward-citation age), **Immediate Importance** (fwd cites ≤ 3 y, r≈0.76), hub patents. Citation queries are **scoped in SQL** — the 112M-edge graph must never be loaded into RAM |
| Science-front metrics | `scripts/science_metrics.py` | citation velocity, field-normalized impact percentiles, front hubs, retraction rate — per OpenAlex topic |
| **CPC technology backbone** | `scripts/parse_cpc.py` → `scripts/embed_cpc.py` | all 653 CPC subclass definitions parsed and embedded (multilingual) + HNSW index → any signal from any tier projects onto CPC via ANN |
| **Fine CPC index** (#42) | `scripts/parse_cpc_scheme.py` → `scripts/embed_cpc_fine.py` | the full CPC scheme (261k fine codes with title + hierarchy path) in `cpc_fine`; the ~102k with ≥50 patents embedded + HNSW → free text resolves to the specific fine codes that describe a technology (A23C20/025 = plant-based cheese), not a coarse subclass |
| **TIR trajectory** K(t) (#36) | `scripts/tir_trajectory.py --like "H01M10/052%"` | year-by-year improvement rate for a technology = a UNION of fine CPC codes; direction (accelerating/steady/maturing/decelerating) from the recent complete window. Honest gates: per-window MIN_N, ~7y citation-maturity truncation (greyed), absolute K withheld outside the calibrated range. Validated 6/6 (`scripts/tir_trajectory_validate.py`) |
| **On-demand technology** (#42+#36) | `scripts/tech_trajectory.py "protein recovery by electrodialysis"` | free text → nearest fine CPC domain → K(t) trajectory + S-curve direction, end-to-end. Powers `/api/foresight/trajectory` + the Technology Explorer input |
| Cross-tier lead time | `scripts/cpc_leadtime.py --cpc H02S` | patents via native CPC (full corpus), science/funding/market via embedding projection → per-tier takeoff years and lead-time estimates on one axis |
| Empirical technology axes | `scripts/build_cpc_cooccurrence.py --top H01M` | CPC pair co-occurrence per year over the back-file (44M pairs): combinations sharpen coarse classes (H01M+B60L = EV batteries, +B09B/Y02W = battery recycling) and rising pairs flag cross-domain convergence |
| Mega-trend proposer | `scripts/propose_mega_trends.py` | data-driven candidate mega-trends vs. the canonical `mega_trends.yaml` |

---

## Frontend

Next.js 14 (App Router) + Tailwind + `pg` (Postgres Pool via local socket).
Dark-mode card grid, PESTEL badges, vertical tabs, hybrid search (Postgres FTS
+ pgvector HNSW ANN on the 1024-dim Matryoshka prefix, RRF fusion).

```bash
cd frontend
npm run dev                  # http://localhost:3001 (3000 is taken by Open WebUI)
npm run build && systemctl --user restart catandary-frontend
                             # production (port 3001) runs as a systemd user unit
                             # (deploy/systemd/catandary-frontend.service), behind deploy/Caddyfile
```

Routes:

- `/trends` — main grid with vertical filter
- `/trends/[slug]` — single trend article
- `/trends/vertical/[v]`, `/trends/pestel/[dimension]`, `/trends/mega`
- `/trends/foresight` — Foresight Cockpit (hybrid search + analytics), with a
  lead-time proof strip above the fold
- `/trends/foresight/technology` — Technology Explorer, with an **on-demand TIR
  trajectory** input (#36/#42): describe a technology in words → its year-by-year
  improvement rate K(t) on a time axis + S-curve direction, honest gates built in
- `/trends/foresight/lead-time` — **Lead-time view**: the four innovation tiers
  (research → patents → funding → market) as per-peak-indexed SoV curves over
  time; the research↔market gap is the lead, shown as a headline number only
  where the corpus can prove it (`reliable`)
- `/trends/foresight/clusters` — Cluster Explorer over the full signal space
  (momentum, source corroboration, evidence links; reads persisted snapshots)
- `/api/search?q=...&vertical=FOOD&limit=20` — hybrid search API (RRF)
- `/api/foresight/clusters?scope=global` (or `?vertical=FOOD`)

Production runs **without** `DATABASE_URL` — the pool connects through the
local socket with peer auth. `next.config.ts` sets `output: "standalone"`.

---

## Operations

| Job | Schedule | Command |
|---|---|---|
| DB backup | daily 02:45 (cron) | `scripts/backup_db.py --dest /mnt/data-hdd/backups/catandary --skip-sqlite --keep-days 7` |
| Discovery loop | Sun 06:00 (cron) | `scripts/discovery_loop.py` — re-cluster, curate, retrain distill heads |
| Pipeline cycle | manual / off-hours | `scripts/scheduled_cycle.sh` |

**Backups** are compressed `pg_dump -Fc` snapshots with 7-day retention (a
dump is ~25–60 GB at current corpus size). The pre-migration SQLite state is
kept **once**, permanently, under `backups/catandary/frozen/` — it is no
longer re-dumped daily. `.env` is copied alongside each snapshot.

```bash
# Restore (custom format)
pg_restore -d catandary /mnt/data-hdd/backups/catandary/catandary-pg-YYYY-MM-DD.dump
cp /mnt/data-hdd/backups/catandary/env-YYYY-MM-DD .env
```

**Disk layout:** Postgres lives on the NVMe (`/`), bulk artifacts on the HDD
(`/mnt/data-hdd`): BDDS zip archive (205 GB, kept for re-parses), backups.
Embeddings are **lazy** — only the subsets a concrete foresight question needs
are embedded; embedding all ~19M patents (~280 GB of vectors) is deliberately
avoided.

---

## Testing

```bash
python -m pytest tests/        # 67 tests; conftest.py forces SQLite — no Postgres needed
python -m pyflakes pipeline/ scripts/
```

Covers feed parsing, dedup, schema validation, the DB layer, discovery
metrics, foresight snapshots, and the auto-publish gate.

---

## Project structure

```
catandary-trends/
├── CLAUDE.md                  # architecture & taxonomy contract
├── sources.yaml               # curated source registry (per vertical)
├── mega_trends.yaml           # canonical mega-trend taxonomy
├── pipeline/                  # long-running components
│   ├── feed_poller.py         #   RSS acquisition
│   ├── llm_processor.py       #   stage pipeline 1–9 (+ --signal-mode)
│   ├── run_full_cycle.py      #   orchestrator (poll + stages + publish)
│   ├── db.py                  #   Postgres/SQLite layer, migrations, batch inserts
│   ├── discovery.py           #   two-layer trend discovery core
│   ├── foresight.py           #   cluster kernel (scope load, KMeans, SoV)
│   ├── foresight_snapshot.py  #   persisted cluster snapshots for the frontend
│   ├── distill.py             #   embedding-head classifier (GPU-free)
│   ├── gpu_handover.py        #   llama-server ⇄ Ollama VRAM/symlink orchestration
│   ├── llamacpp_client.py / ollama_client.py / anthropic_client.py
│   ├── auto_publisher.py / reclassify.py / mega_trend_reviewer.py / crs.py
│   └── models.py              #   Pydantic schemas for all LLM outputs
├── scripts/                   # operational tools
│   ├── scheduled_cycle.sh     #   reference off-hours runner
│   ├── setup_db.py            #   DB init/migrations
│   ├── ingest_*.py            #   acquisition layer (see table above)
│   ├── signal_batch.py        #   mass classification (anthropic|local|distill)
│   ├── run_distill_batch.py   #   distill ingest incl. GPU handover
│   ├── train_distill_heads.py #   head training
│   ├── discover_trends.py / discovery_loop.py
│   ├── tir_metrics.py / science_metrics.py / cpc_leadtime.py
│   ├── parse_cpc.py / embed_cpc.py / build_cpc_cooccurrence.py
│   ├── backup_db.py / review_cli.py / verify_feeds.py
│   └── generate_content.py    #   decoupled article generation
├── frontend/                  # Next.js app (catandary.de/trends)
├── deploy/                    # Caddyfile, deploy script
├── tests/                     # pytest suite (SQLite-backed via conftest)
└── data/                      # logs, frozen SQLite fallback
```

---

## Engineering conventions

- **Batch inserts for anything at backfill scale** — per-row inserts cap at
  ~100/s; use the `db.insert_raw_entries_batch*` helpers (`execute_values`,
  `ON CONFLICT DO NOTHING`).
- **Never load the full citation graph into RAM** — scope graph queries in SQL
  (`= ANY(...)` against the indexed link columns).
- **PG wrapper rows are dicts** — tuple-unpacking a row silently binds the
  column *names*; always access `r["col"]`.
- **Literal `%` in SQL must be `%%`** when parameters are bound (psycopg2).
- **Strip NUL (`0x00`)** from external text before insert — Postgres rejects it.
- Pydantic validation + retry (3 attempts, exponential backoff) around every
  LLM call; structured outputs only; `temperature=0` for extraction/classify.
- Qwen3 needs `think=False` (Ollama) / `enable_thinking=false` (llama.cpp) to
  avoid chain-of-thought bloat.
- Commits follow `feat:/fix:/refactor:/test:/docs:/chore:`; work lands on
  `main` or short-lived feature branches.

---

## Status

*(2026-07-05)* All six build sprints are complete; the platform runs on
PostgreSQL + pgvector. **243 active sources**, **50k published trend
articles**, **>510k classified signals** with embeddings, and a **~20M-entry
raw corpus** across all four lead-time tiers: 18.7M patents (112M citation
edges, 131M CPC rows, to 1990), 334k science works (11.6M OpenAlex citation
edges, to 1990), 293k funding records (incl. 117k SEC Form D startup rounds),
~700k market posts (WordPress archive depth to 2010). The CPC backbone (653
embedded subclass definitions + 44M co-occurrence pairs) puts all tiers on a
common technology axis. Active focus: cross-tier lead-time productization,
embedding-based pipeline stages, Hetzner deployment — see the
[issues](https://github.com/ZuluTwoThree/catandary-trends/issues).
