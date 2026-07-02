# Catandary Trends

Cross-industry trend intelligence platform powered by local LLMs (Ollama /
llama.cpp). Aggregates RSS signals from primary trade/research sources across
eight industry verticals, classifies them via a multi-stage LLM pipeline, and
publishes curated trend articles (EN) through a Next.js frontend. Each LLM
stage has a pluggable backend (Ollama, llama.cpp, or — for the one-off historical
backfill — the Anthropic API); the day-to-day RSS pipeline stays fully local.

See [`CLAUDE.md`](CLAUDE.md) for the full architecture and taxonomy, and
[`BACKLOG.md`](BACKLOG.md) for open ideas.

## Verticals

FOOD · TECH · HEALTH · ECO · DESIGN · FASHION · BIZ · LIFESTYLE

Cross-cutting classification: PESTEL dimensions (P/E/S/T/En/L) plus
Mega/Macro/Micro trend levels (Foresight taxonomy).

## Setup

### Prerequisites

- Python 3.12+
- Node.js 20+ (for frontend)
- [Ollama](https://ollama.com/) running on `127.0.0.1:11434`
- NVIDIA GPU with ≥12 GB VRAM (verified on RTX 5080 16 GB and RTX 3090 24 GB)
- Optional: [`llama.cpp`](https://github.com/ggerganov/llama.cpp) `llama-server` (port 8090) as an alternate backend for the classification stages (8B), embeddings, and content generation (35B, requires the 24 GB card). See `CLAUDE.md` → "Stage-6 auf llama.cpp 35B".
- Optional: an Anthropic API key for the historical-backfill classification path (`CLASSIFY_BACKEND=anthropic`, Haiku). Not used by the regular RSS pipeline.

### Install Ollama models

```bash
ollama pull qwen3:8b          # filter / extract / classify
ollama pull qwen3:14b         # content generation (DE + EN)
ollama pull qwen3-embedding   # dedup + semantic search (4096-dim)
```

### Install dependencies

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### Initialize database

```bash
python scripts/setup_db.py
```

SQLite is used by default (`data/catandary.db`). PostgreSQL + pgvector is
the planned production target.

### Environment

Copy `.env.example` to `.env`. Key settings:

- `OLLAMA_CLIENT_HOST` — default `http://127.0.0.1:11434`.
  From WSL2 use the Windows host IP instead of `localhost`.
- `DATABASE_PATH` — default `./data/catandary.db`
- `LOG_LEVEL` — default `INFO`

Per-stage backend switches (all default to `ollama`; `scheduled_cycle.sh` sets
them automatically when the matching llama.cpp start scripts are present):

- `STAGE_8B_BACKEND` — relevance/extract/classify/reclassify: `ollama` | `llamacpp`
- `EMBED_BACKEND` — Stage 5 embeddings: `ollama` | `llamacpp`
- `STAGE5_BACKEND` — Stage 6 content gen: `ollama` (qwen3:14b) | `llamacpp` (35B)
- `CLASSIFY_BACKEND` — `ollama` | `llamacpp` | `anthropic` (backfill only)
- `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL_CLASSIFY` (default `claude-haiku-4-5`) — for `CLASSIFY_BACKEND=anthropic`

## Pipeline

```
RSS feeds ──► feed_poller ──► raw_entries
                                  │
                                  ▼
                       llm_processor (run_pipeline_batch)
                        1. title dedup          (no LLM, rapidfuzz)
                        2. relevance filter     ┐
                        3. structured extract   │ 8B  (Ollama qwen3:8b /
                        4. NER + classify       ┘      llama.cpp 8B / Anthropic)
                        5. dedup via embedding  (qwen3-embedding, 4096-dim)
                        6. content EN           (Ollama qwen3:14b / llama.cpp 35B)
                        7. insert trends        (draft | signal)
                        8. reclassify verticals (8B)
                        9. auto-publish         (conf ≥ 0.85)
                                  │
                                  ▼
                          trends (published) ──► Next.js frontend
                                  │
                          mega_trend_reviewer (periodic)
```

Notes:
- **DE generation is currently suspended** — articles are EN-only (`title_de`/
  `body_de` are left `NULL`; existing German bodies are historical). The frontend
  DE/EN switcher still works for older content.
- **`--signal-mode`** skips Stage 6 and inserts content-less `status='signal'`
  rows (classification + embedding only) for fast foresight density; the article
  is generated later, decoupled, by `scripts/generate_content.py`.
- Each LLM stage's backend is selected via the env switches above; the regular
  RSS run is fully local. `CLASSIFY_BACKEND=anthropic` is the backfill-only path.

### Poll feeds

```bash
python -m pipeline.feed_poller                 # all verticals
python -m pipeline.feed_poller FOOD TECH       # subset
python scripts/poll_dryrun.py                  # count new signals, no write
```

### Run the full cycle (poll + LLM)

`scripts/scheduled_cycle.sh` is the reference orchestration: it picks the
llama.cpp backends when their start scripts are present, stops `llama-server`
to free the GPU, runs `pipeline.run_full_cycle` (poll + LLM), drains any
backlog, and restarts `llama-server` at the end.

```bash
scripts/scheduled_cycle.sh 600                 # poll + process, batch 600
python -m pipeline.run_full_cycle --batch 600  # same, without the GPU/service wrapper
python -m pipeline.run_full_cycle --skip-poll --batch 600   # process existing backlog only
```

### Run the LLM pipeline directly

```bash
python -m pipeline.llm_processor 200           # process up to 200 entries (default 200)
python -m pipeline.llm_processor 200 --signal-mode   # classify+embed only, no article (status='signal')
```

### Decoupled content generation (signal-mode follow-up)

Generates EN articles locally for `status='signal'` trends and promotes them to
`published`/`draft`. Has a VRAM pre-flight guard (stop `llama-server` first).

```bash
python scripts/generate_content.py --vertical FOOD --limit 200
python scripts/generate_content.py --all --chunk 200
```

### Auto-publish high-confidence drafts

Auto-publish and reclassify are integrated into the LLM pipeline (stages 8+9).
Standalone run as fallback:

```bash
python -m pipeline.auto_publisher              # threshold: AUTO_PUBLISH_CONFIDENCE=0.85
```

### Assign / refresh mega-trends

```bash
python -m pipeline.mega_trend_reviewer         # Qwen3 14B, batched
python scripts/review_recent_live.py           # yesterday + today only
```

### Manual review CLI

```bash
python scripts/review_cli.py list draft
python scripts/review_cli.py show <id>
python scripts/review_cli.py publish <id>
python scripts/review_cli.py review            # interactive
python scripts/review_cli.py stats
```

### Verify feed URLs

```bash
python scripts/verify_feeds.py
```

## Historical backfill (non-RSS acquisition)

RSS feeds only carry the latest ~10–50 items. For dated historical depth the
acquisition scripts pull from free, dated channels and write `raw_entries`
(processed=0) for the signal-mode pipeline to pick up. `probe_source_apis.py`
classifies each source (WordPress REST API / OpenAlex / sitemap) and the
`ingest_backfill.py` router dispatches accordingly.

```bash
python scripts/probe_source_apis.py                         # which channel per source
python scripts/ingest_backfill.py --after 2024-01-01 --before 2025-01-01 --dry-run
python scripts/ingest_wordpress.py --source-name "Green Queen" --after 2024-01-01 --before 2025-01-01
python scripts/ingest_openalex.py  --source-name "Nature Food" --after 2024-01-01 --before 2025-01-01
```

Then classify the ingested entries off-GPU with Haiku and generate articles
locally later:

```bash
CLASSIFY_BACKEND=anthropic python -m pipeline.llm_processor 5000 --signal-mode
python scripts/generate_content.py --all --chunk 200
```

## Frontend

Next.js 14 App Router, Tailwind, better-sqlite3. Runs on port **3001**
(port 3000 is reserved for Open WebUI on the dev machine).

```bash
cd frontend
npm run dev                  # http://localhost:3001
npm run build && npm start   # production
```

Routes:
- `/trends` — main grid with vertical filter
- `/trends/[slug]` — single trend article
- `/trends/vertical/[v]` — vertical view
- `/trends/mega` — mega-trends with momentum tracking
- `/trends/pestel/[dimension]` — PESTEL cut
- `/trends/foresight` — Foresight Cockpit (hybrid FTS5 + embedding search with analytics)
- `/trends/foresight/clusters` — Cluster Explorer: data-driven trend clusters over the full signal space (momentum, source corroboration, evidence links). Reads persisted snapshots from `pipeline/foresight_snapshot.py` (`foresight_runs`/`foresight_clusters`)
- `/api/search?q=...&vertical=FOOD&limit=20` — hybrid search API (RRF fusion)
- `/api/foresight/clusters?scope=global` (or `?vertical=FOOD`) — latest cluster snapshot per scope

Note: `frontend/next.config.ts` sets `output: "standalone"`. The local production
server is run as `npx next start -p 3001` (behind the `deploy/Caddyfile` reverse
proxy). To regenerate the cluster snapshots the page reads, run
`python -m pipeline.foresight_snapshot --all-verticals` (GPU-free; ~5 min over the
signal space) — schedule it after large ingests.

## Tests

```bash
python -m pytest tests/ -v
```

## Backups

`scripts/backup_db.py` takes an online-consistent snapshot of
`data/catandary.db` via SQLite's `Connection.backup()` (safe during pipeline
writes), gzips it, copies `.env` alongside, and prunes snapshots older than
`--keep-days` (default 14) in each destination.

```bash
# Manual run, one or more --dest folders
python scripts/backup_db.py --dest /mnt/data-hdd/backups/catandary
```

Daily cron (00:05), as installed on the reference machine:

```cron
5 0 * * * /home/dirk/projects/catandary-trends/.venv/bin/python \
    /home/dirk/projects/catandary-trends/scripts/backup_db.py \
    --dest /mnt/data-hdd/backups/catandary \
    >> /home/dirk/logs/catandary-backup.log 2>&1
```

Snapshot scales with the DB (currently ~1.5 GB on disk, ~41k trends with
4096-dim embeddings); gzip roughly halves it. Online `Connection.backup()`
keeps it consistent during pipeline writes.

### Restore

```bash
gunzip -c /mnt/data-hdd/backups/catandary/catandary-YYYY-MM-DD.db.gz \
    > data/catandary.db
cp /mnt/data-hdd/backups/catandary/env-YYYY-MM-DD .env
```

Quick integrity check: row count should match the timeline up to that date.

```bash
python -c "import sqlite3; print(sqlite3.connect('data/catandary.db').execute('select count(*) from trends').fetchone()[0])"
```

## Sources

Configured in [`sources.yaml`](sources.yaml), grouped by vertical.
Only legal primary sources (trade media, research, press wires, brand
newsrooms). No aggregator scraping.

## Project structure

```
catandary-trends/
├── CLAUDE.md               # Architecture & taxonomy spec
├── BACKLOG.md              # Open ideas, deferred experiments
├── sources.yaml            # Feed configuration
├── mega_trends.yaml        # Canonical mega-trend taxonomy
├── pipeline/
│   ├── feed_poller.py
│   ├── run_full_cycle.py   # poll + LLM orchestration
│   ├── llm_processor.py    # stages 1–9 (+ --signal-mode)
│   ├── mega_trend_reviewer.py
│   ├── auto_publisher.py
│   ├── reclassify.py       # vertical reclassification for drafts
│   ├── radar_discovery.py  # Brave-search source discovery
│   ├── newsletter_generator.py
│   ├── crs.py              # composite trend/relevance scoring
│   ├── models.py           # Pydantic schemas
│   ├── config.py           # settings + backend switches + sources loader
│   ├── db.py               # SQLite layer (Postgres-ready schema)
│   ├── ollama_client.py    # backend: Ollama
│   ├── llamacpp_client.py  # backend: llama.cpp (8B / 35B / embeddings)
│   ├── anthropic_client.py # backend: Anthropic (backfill classification)
│   └── gpu_handover.py     # Ollama⇄llama-server VRAM/symlink handover
├── frontend/               # Next.js app
│   ├── src/app/
│   ├── src/components/
│   └── mockups/            # static design demos
├── scripts/                # setup, ingest/backfill, content-gen, review, dryruns
│   └── scheduled_cycle.sh  # reference full-cycle runner
└── tests/
```

## Status

Sprints 1–6 complete. **190 active sources, 41k+ published trends** across 8
verticals (Stand 2026-06-21). Every LLM stage now has a pluggable backend:
the classification stages (8B) and embeddings can run on Ollama or llama.cpp,
and Stage 6 content generation always attempts the llama.cpp 35B (with
mid-pipeline GPU handover, falling back to Ollama qwen3:14b). A decoupled
throughput path (`--signal-mode` + Anthropic-Haiku backfill classification +
local `generate_content.py`) drives the historical cross-vertical backfill via
free WordPress-REST / OpenAlex / sitemap acquisition. DE article generation is
currently suspended (EN-only). Active focus: cross-vertical backfill rollout,
newsletter cadence, Hetzner deployment. See `CLAUDE.md` for full architecture
and `BACKLOG.md` for the running idea list.

For MacBook Air (8 GB) deployment, see [`MACBOOK_SETUP.md`](MACBOOK_SETUP.md).
