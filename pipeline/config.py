"""Configuration loader for Catandary Trends pipeline."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "catandary.db"))
DATABASE_URL = os.getenv("DATABASE_URL", "")  # PostgreSQL connection string for production

# Ollama
# OLLAMA_HOST env var is often set to 0.0.0.0 for the server bind address.
# For the client, we always connect to 127.0.0.1.
OLLAMA_HOST = os.getenv("OLLAMA_CLIENT_HOST", "http://127.0.0.1:11434")

# Models — override via environment variables for testing
MODEL_FILTER = os.getenv("MODEL_FILTER", "qwen3:8b")
MODEL_EXTRACT = os.getenv("MODEL_EXTRACT", "nuextract")
MODEL_CLASSIFY = os.getenv("MODEL_CLASSIFY", "qwen3:8b")
MODEL_GENERATE = os.getenv("MODEL_GENERATE", "qwen3:14b")
MODEL_EMBEDDING = os.getenv("MODEL_EMBEDDING", "qwen3-embedding")

# Content-generation backend (pipeline Stage 6 / "Stage 5" in the foresight doc).
# "ollama" (default) uses MODEL_GENERATE on Ollama. "llamacpp" routes content
# generation to a llama-server (GGUF in STAGE5_MODEL) with a mid-pipeline GPU
# handover — see pipeline.gpu_handover. Other stages stay on Ollama.
STAGE5_BACKEND = os.getenv("STAGE5_BACKEND", "ollama")
STAGE5_MODEL = os.getenv("STAGE5_MODEL", "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf")
# Garbage floor for the content guard — only catches a near-empty stub body (a
# real generation failure), NOT a length target. A short but complete, cliché-free
# body is preferred over retrying for length: clear short text beats AI slop. The
# guard retries on clichés or mid-sentence truncation, not on brevity.
STAGE5_MIN_BODY_WORDS = int(os.getenv("STAGE5_MIN_BODY_WORDS", "25"))
# Option B (#11): re-roll bodies below this word count (prompt targets 150-250w
# but the 30B naturally lands ~100w; this pushes closer to spec at the cost of
# more re-rolls). Still bounded by max_validate_retries, then accepted.
# Obergrenze, wie viele Eintraege EINER Quelle ein einzelner Cycle-Lauf in die
# Content-Generierung nimmt. Owner-Praezisierung 2026-08-20: Funding-News duerfen
# ueber den regulaeren Cycle zu Artikeln werden — verhindert werden soll nur,
# dass ein Massen-Ingest en masse in die Content-Generierung laeuft (235k
# SBIR/CORDIS-Zeilen brachen den 04:00-Lauf ab). Normale RSS-Quellen liegen bei
# Median 6 / p95 70 Eintraegen pro Tag (gemessen 14 Tage) — 200 trifft also nie
# den Normalbetrieb, aber jeden Dump. Der Rest bleibt liegen und gehoert dem
# Distill-Pfad (signal_batch).
CYCLE_MAX_PER_SOURCE = int(os.getenv("CYCLE_MAX_PER_SOURCE", "200"))

# Strenge Extraktion (Owner-Entscheidung 2026-08-21: AN als Default):
# alle Schema-Felder werden als Pflicht angefordert + Zitate/Orte auf
# Woertlichkeit gefiltert. Wirkung an 40 Artikeln: brand_name 0/40 -> 40/40,
# key_claims ~0 -> 274, Spekulationsquote 32,5 % -> 22,5 %. Preis: die
# Extraktion dauert 5,3 statt 1,1 Sekunden pro Artikel (bei 24 parallelen
# Slots ca. 9 -> 45 Minuten pro Nachtlauf) — Owner hat das abgewogen und
# akzeptiert. EXTRACTION_STRICT=0 ist der Rueckweg ohne Codeaenderung.
EXTRACTION_STRICT = os.getenv("EXTRACTION_STRICT", "1") == "1"

# Untergrenze, unterhalb derer der Content-Guard neu wuerfelt.
# Owner-Entscheidung 2026-08-19: ~100 Woerter sind als Artikellaenge in
# Ordnung. Vorher stand hier 130 — bei einem Produktions-Median von 109
# loesten damit 80,6 % aller Artikel eine Neuwuerfelung aus, die nach
# aufgebrauchtem Retry-Budget ohnehin akzeptiert wurde (gemessen an 4.848
# veroeffentlichten Artikeln, 14 Tage). Jeder dieser Neuwuerfe ist eine
# volle Generierung auf dem 26B. Mit 100 faellt die Quote auf 29,1 %.
STAGE5_TARGET_BODY_WORDS = int(os.getenv("STAGE5_TARGET_BODY_WORDS", "100"))
# Ab welcher Quelltextlaenge die Wort-Untergrenze ueberhaupt eingefordert wird.
# Darunter ist sie ein Dünne-Quelle-Melder, kein Laengenziel: der Neuwurf
# verlangt vom Modell Woerter, die in der Quelle nicht stehen, bekommt dreimal
# dieselbe kurze Antwort und akzeptiert sie dann ohnehin. Gemessen ueber 5.355
# Artikel (22.-24.09.2026), Anteil der Bodies, die nach aufgebrauchtem Budget
# UNTER der Grenze blieben: 0-250 Zeichen 29,1 % · 250-500 22,3 % · 500-750
# 27,7 % · 750-1000 8,4 % — und ab 1000 Zeichen 0,2 % (8 von 4.352). 242 der
# 250 Dauer-Fehlschlaege liegen also unter dieser Schwelle. In der Nacht auf
# den 24.09. verbrannten 86 solcher Faelle je zwei volle Generierungen auf dem
# 26B. Die Stub-Grenze STAGE5_MIN_BODY_WORDS bleibt davon unberuehrt — ein
# echter Generierungsfehler wird weiterhin bei jeder Quellenlaenge neu gewuerfelt.
# 0 schaltet die Ausnahme ab (Untergrenze gilt dann wieder immer).
STAGE5_BREVITY_MIN_SOURCE_CHARS = int(os.getenv("STAGE5_BREVITY_MIN_SOURCE_CHARS", "1000"))
# Symmetric max-word guard (#11), mirror of the MIN floor: re-roll a runaway body
# above this ceiling (the prompt targets 150-250w). Set well above target so it
# only catches genuine overruns, and it is bounded by max_validate_retries (a
# still-too-long body is accepted after the budget, never looped). 0 disables it.
STAGE5_MAX_BODY_WORDS = int(os.getenv("STAGE5_MAX_BODY_WORDS", "320"))
# Wie viel Quelltext (raw_content bzw. Teaser) der Content-Prompt sieht — nur
# der ANFANG. Bis 2026-09-05 die Konstante CONTENT_CHARS=4000 in llm_processor;
# jetzt per Env steuerbar, Default unverändert 4000. Bewusst NICHT angehoben:
# die 22 Garbage-Bodies vom 05.09. entstanden ausschließlich bei Prompts, die
# genau an dieser 4000er-Kappe lagen (114 andere lange Prompts desselben Laufs
# waren in Ordnung; alle Teaser-Prompts auch). Mehr Quelltext ist die falsche
# Richtung, bis scripts/repro_stage6_garbage.py die Ursache eingegrenzt hat.
# Nur Anfang statt Anfang+Schluss: unsere Volltext-Quellen enden mit
# Boilerplate (idw: Pressekontakt mit Namen/Telefon, ScienceDaily: "Story
# Source"/Journal Reference, The Conversation: Disclosure) — der Schluss
# liefert keinen Artikelinhalt, aber Fremdnamen; die Zahlen/Daten/Zitate der
# hinteren Hälfte kommen ohnehin über die Extraktion (liest 12.000 Zeichen).
STAGE6_SOURCE_MAX_CHARS = int(os.getenv("STAGE6_SOURCE_MAX_CHARS", "4000"))

# Mindest-Textbasis fuer die Content-Generierung (#97, 2026-09-09). Ein Eintrag,
# von dem nur der Titel uebrig ist, darf nie zu einem Artikel werden: das
# Grounding-Gate prueft Zahlen/Namen GEGEN die Quelle — steht dort nichts, gibt
# es nichts zu pruefen und jede Erfindung des Modells rutscht durch. Genau so
# entstanden am 08.09. 187 published Artikel aus den am 04.09. deaktivierten
# TDM-Vorbehalts-Quellen, deren excerpt der Purge geleert hatte: fluessige,
# frei erfundene Studieninhalte mit 0 Grounding-Flags.
# Gemessen an der Kohorte vom 08.09. (2.714 Trends): 0 Zeichen 216, <60 229,
# <80 247 (9,1 %), <100 296, <200 770 (28 %). 80 trifft das Loch (kein Text /
# Bruchstueck), laesst normale RSS-Teaser (Median 508 Zeichen) unberuehrt.
MIN_SOURCE_TEXT_CHARS = int(os.getenv("MIN_SOURCE_TEXT_CHARS", "80"))

# Eigener Embedding-Endpunkt auf der CPU (:8091, #97, 2026-09-09): dasselbe
# Qwen3-Embedding-8B wie Stage 5, aber ohne VRAM — fuer Vektorsuchen, waehrend
# :8090 ein Chatmodell haelt (ein Embedding-Request dorthin wuerde vom Chatmodell
# beantwortet). Urspruenglicher Nutzer war der Korpus-Rechercheur der
# Scouting-Dossiers (Feature entfernt 2026-09-19); der Server bleibt als
# systemd-Unit catandary-embed-cpu.service bestehen. Leer = kein CPU-Endpunkt.
RESEARCH_EMBED_HOST = os.getenv("RESEARCH_EMBED_HOST", "")

# qwen3:8b stages backend (pipeline Stages 2 Relevance, 3 Extraction,
# 4 Classification, 8 Reclassify).
# "ollama" (default) uses MODEL_FILTER/MODEL_CLASSIFY on Ollama. "llamacpp" routes
# all four stages to a llama-server serving STAGE_8B_MODEL, sharing the same
# port 8090 with Stage 6's 35B server via symlink-swap (see pipeline.gpu_handover).
STAGE_8B_BACKEND = os.getenv("STAGE_8B_BACKEND", "ollama")
STAGE_8B_MODEL = os.getenv("STAGE_8B_MODEL", "Qwen3-8B-UD-Q4_K_XL.gguf")

# Stages 2/3/4 classification concurrency. Dispatches the pure step_* LLM calls
# via a thread pool against the llama-server's parallel slots. Default 24 matches
# the 208K/24-slot 8B server the handover brings up (see MODEL_START_SCRIPTS).
# Set 0/1 for sequential (e.g. Ollama single-stream). Validated sweet spot: 24.
CLASSIFY_WORKERS = int(os.getenv("CLASSIFY_WORKERS", "24"))

# Stage 5 (Embeddings + Dedup) backend.
# "ollama" (default) uses MODEL_EMBEDDING on Ollama. "llamacpp" routes embedding
# generation to a llama-server in --embedding mode serving EMBED_MODEL on
# port 8090, sharing the symlink with the other llama.cpp stages.
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "ollama")
EMBED_MODEL = os.getenv("EMBED_MODEL", "Qwen3-Embedding-8B-Q4_K_M.gguf")

# Pipeline
RELEVANCE_THRESHOLD = 0.6
DUPLICATE_SIMILARITY_THRESHOLD = 0.92
AUTO_PUBLISH_CONFIDENCE = 0.85
# Max drafts the auto-publisher scans per run. Must exceed the number of drafts
# a cycle can leave behind, otherwise publishable high-confidence drafts pile up
# as a permanent backlog (each run only ever reaches the first N). Set generously
# so a run drains the whole draft pool — sub-threshold drafts are skipped cheaply,
# so the real cost is bounded by the high-confidence subset actually published.
AUTO_PUBLISH_LIMIT = int(os.getenv("AUTO_PUBLISH_LIMIT", "20000"))
MAX_RETRIES = 3

# RSS-cycle classification backend (#41). "hybrid" (default) does embed-first +
# distill heads for vertical/mega/PESTEL (GPU-free, seconds) and a HYBRID
# relevance gate: distill decides the confident tails, the 8B LLM only judges the
# uncertain band [DISTILL_REL_LOW, DISTILL_REL_HIGH). Extraction (brand names) and
# content-gen stay on the LLM. "llm" reverts to the full 8B path (Stages 2-4).
# Falls back to "llm" automatically if the distill heads can't be loaded.
RSS_CLASSIFY_MODE = os.getenv("RSS_CLASSIFY_MODE", "hybrid")  # hybrid | llm
DISTILL_REL_HIGH = float(os.getenv("DISTILL_REL_HIGH", "0.7"))   # >= → relevant (distill)
DISTILL_REL_LOW = float(os.getenv("DISTILL_REL_LOW", "0.3"))     # < → not relevant (distill)

# Grounding gate (#11): when on, auto_publisher holds any high-confidence draft
# whose body contains a number/date/percentage absent from its source (a
# fabricated specific) for manual review instead of publishing it. Trades some
# publish volume (~1/4 of drafts on the current corpus) for factual integrity —
# set AUTO_PUBLISH_GROUNDING_GATE=0 to prioritise volume.
AUTO_PUBLISH_GROUNDING_GATE = os.getenv("AUTO_PUBLISH_GROUNDING_GATE", "1") == "1"

# Brave Search (radar discovery layer, pipeline/radar_discovery.py)
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")

# Firecrawl (backfill script, scripts/backfill_sources.py)
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")

# Anthropic API — classification backend for the one-time historical backfill.
# CLASSIFY_BACKEND="anthropic" routes Stages 2/3/4/8 (relevance/extraction/
# classification/reclassify) to Claude (off-GPU); embeddings + content-gen stay
# local. The ongoing RSS pipeline stays fully local (CLAUDE.md). Takes precedence
# over STAGE_8B_BACKEND when set to "anthropic".
CLASSIFY_BACKEND = os.getenv("CLASSIFY_BACKEND", "ollama")  # ollama | llamacpp | anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL_CLASSIFY = os.getenv("ANTHROPIC_MODEL_CLASSIFY", "claude-haiku-4-5")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def load_sources() -> dict:
    """Load sources configuration from sources.yaml."""
    sources_path = PROJECT_ROOT / "sources.yaml"
    with open(sources_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


_REL_MIN_CACHE: dict[str, float] | None = None


def source_relevance_min() -> dict[str, float]:
    """{source_name: relevance_min} from sources.yaml — the per-source cap.

    A capped source must clear a HIGHER relevance bar to enter the corpus: its
    marginal content is dropped, its borderline content still goes to the 8B for
    a proper look, its strong signals pass unchanged. Used to damp low-foresight
    'now'-tier sources (market confirmation) without losing their good signals.
    Cached — sources.yaml is static at runtime.
    """
    global _REL_MIN_CACHE
    if _REL_MIN_CACHE is None:
        cfg = load_sources()
        out: dict[str, float] = {}

        def put(s: dict) -> None:
            v = s.get("relevance_min")
            if v is not None:
                # duplicates (a source listed under two verticals): keep the strictest
                out[s["name"]] = max(float(v), out.get(s["name"], 0.0))

        for _v, g in (cfg.get("verticals") or {}).items():
            for k in ("sources", "science"):
                for s in g.get(k) or []:
                    put(s)
        for _g, e in (cfg.get("cross_industry") or {}).items():
            for s in e or []:
                put(s)
        _REL_MIN_CACHE = out
    return _REL_MIN_CACHE


def load_mega_trends() -> list[dict]:
    """Load canonical mega-trends taxonomy from mega_trends.yaml."""
    path = PROJECT_ROOT / "mega_trends.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("mega_trends", [])


def get_mega_trend_keys() -> list[str]:
    """Get list of canonical mega-trend keys for LLM prompt."""
    return [mt["key"] for mt in load_mega_trends()]


def get_mega_trend_prompt_block() -> str:
    """Build the mega-trend section for the classification prompt.

    No momentum annotation: that was the hand-typed yaml claim (removed
    2026-08-08 — 19 of 26 contradicted the measurement), and assigning a
    signal to a theme doesn't depend on the theme's current momentum anyway.
    """
    trends = load_mega_trends()
    return "\n".join(f'- {mt["key"]}: {mt["description"]}' for mt in trends)
