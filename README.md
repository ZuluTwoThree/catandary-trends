# Catandary Trends

Cross-industry trend intelligence platform powered by local LLMs (Ollama).
Aggregates RSS signals from primary trade/research sources across eight
industry verticals, classifies them via a multi-stage LLM pipeline, and
publishes curated trend articles (DE + EN) through a Next.js frontend.

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
- NVIDIA GPU with ≥12 GB VRAM (RTX 5080 reference)

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

## Pipeline

```
RSS feeds ──► feed_poller ──► raw_entries
                                  │
                                  ▼
                       llm_processor (Ollama)
                        1. title dedup          (no LLM)
                        2. relevance filter     (qwen3:8b)
                        3. structured extract   (qwen3:8b)
                        4. NER + classify       (qwen3:8b)
                        5. dedup via embedding  (qwen3-embedding)
                        6. content EN           (qwen3:14b)
                        7. translate DE         (qwen3:14b)
                        8. insert trends        (draft)
                        9. reclassify verticals (qwen3:8b)
                       10. auto-publish         (conf ≥ 0.85)
                                  │
                                  ▼
                          trends (published) ──► Next.js frontend
                                  │
                          mega_trend_reviewer (periodic)
```

### Poll feeds

```bash
python -m pipeline.feed_poller                 # all verticals
python -m pipeline.feed_poller FOOD TECH       # subset
python scripts/poll_dryrun.py                  # count new signals, no write
```

### Run LLM pipeline

```bash
python -m pipeline.llm_processor 200           # process up to 200 entries
```

Default batch size is 10; pass a larger number as argument for bigger runs.

### Auto-publish high-confidence drafts

Auto-publish and reclassify are integrated into the LLM pipeline (stages 9+10).
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
- `/api/search?q=...&vertical=FOOD&limit=20` — hybrid search API (RRF fusion)

## Tests

```bash
python -m pytest tests/ -v
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
│   ├── llm_processor.py
│   ├── mega_trend_reviewer.py
│   ├── auto_publisher.py
│   ├── reclassify.py       # Vertical reclassification for drafts
│   ├── newsletter_generator.py
│   ├── models.py           # Pydantic schemas
│   ├── db.py               # SQLite layer
│   └── ollama_client.py
├── frontend/               # Next.js app
│   ├── src/app/
│   ├── src/components/
│   └── mockups/            # Static design demos
├── scripts/                # setup, reclassify, review, dryruns
└── tests/
```

## Status

Sprints 1–6 complete. 112 active sources, ~5000 published trends across 8
verticals. Active focus: pipeline cron automation, newsletter, Hetzner
deployment, Brave Search radar. See `CLAUDE.md` → Weiterentwicklung and
`BACKLOG.md` for detailed plans.

For MacBook Air (8 GB) deployment, see [`MACBOOK_SETUP.md`](MACBOOK_SETUP.md).
