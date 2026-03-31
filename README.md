# Catandary Trends

Cross-industry trend intelligence pipeline powered by local LLMs (Ollama).

## Setup

### Prerequisites

- Python 3.12+
- [Ollama](https://ollama.com/) installed and running
- NVIDIA GPU (RTX 5080 recommended, 16GB VRAM)

### Install Ollama Models

```bash
ollama pull qwen3:8b
ollama pull qwen3:14b
ollama pull qwen3-embedding
```

### Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Initialize Database

```bash
python scripts/setup_db.py
```

### Environment Variables (optional)

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

Key settings:
- `OLLAMA_CLIENT_HOST` — Ollama API endpoint (default: `http://127.0.0.1:11434`)
- `DATABASE_PATH` — SQLite database path (default: `./data/catandary.db`)
- `LOG_LEVEL` — Logging level (default: `INFO`)

## Usage

### 1. Poll RSS Feeds

Fetch new entries from all configured sources:

```bash
# All verticals
python -m pipeline.feed_poller

# Specific verticals
python -m pipeline.feed_poller FOOD TECH
```

### 2. Run LLM Pipeline

Process unprocessed entries through the full pipeline (relevance filter → extraction → classification → dedup → content generation):

```bash
# Process up to 10 entries (default)
python -m pipeline.llm_processor

# Process specific number
python -m pipeline.llm_processor 50
```

### 3. Radar Discovery

Extract brand names from Trendhunter radar feeds:

```bash
python -m pipeline.radar_discovery FOOD TECH
```

### 4. Review & Publish

```bash
# List all trends
python scripts/review_cli.py list

# List drafts only
python scripts/review_cli.py list draft

# Show trend detail
python scripts/review_cli.py show 1

# Publish a trend
python scripts/review_cli.py publish 1

# Interactive review
python scripts/review_cli.py review

# Statistics
python scripts/review_cli.py stats
```

### 5. Verify RSS Feeds

```bash
python scripts/verify_feeds.py
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Architecture

```
RSS Feeds → Feed Poller → raw_entries DB
                              ↓
                    LLM Pipeline (Ollama)
                    1. Relevance Filter (Qwen3 8B)
                    2. Structured Extraction (Qwen3 8B)
                    3. NER + Classification (Qwen3 8B)
                    4. Duplicate Check (Qwen3-Embedding)
                    5. Content Generation EN+DE (Qwen3 14B)
                              ↓
                        trends DB → Review CLI → Published
```

## Sources (Sprint 1)

**FOOD:** FoodNavigator, Food Dive, The Spoon, BeverageDaily, New Food Magazine, Trendhunter Food Radar
**TECH:** TechCrunch, The Verge, Ars Technica, VentureBeat, MIT Technology Review, Trendhunter Tech Radar
**Cross-Industry:** PR Newswire, GlobeNewswire

## Project Structure

```
catandary-trends/
├── pipeline/
│   ├── config.py            # Configuration & sources.yaml loader
│   ├── db.py                # SQLite database layer
│   ├── feed_poller.py       # RSS feed aggregation
│   ├── llm_processor.py     # Full LLM pipeline
│   ├── models.py            # Pydantic schemas
│   ├── ollama_client.py     # Ollama wrapper with retry logic
│   └── radar_discovery.py   # Trendhunter radar pipeline
├── scripts/
│   ├── review_cli.py        # CLI for trend review/publish
│   ├── setup_db.py          # Database initialization
│   └── verify_feeds.py      # RSS feed URL verification
├── tests/                   # Unit tests (43 tests)
├── sources.yaml             # Feed source configuration
├── requirements.txt
└── CLAUDE.md               # Full project specification
```
