# Catandary Trends – Lokale Cross-Industry Trend Intelligence Pipeline

## Architekturübersicht

Catandary Trends ist eine branchenübergreifende Trend-Intelligence-Plattform, die auf lokalen LLMs (Ollama) läuft und als öffentlicher Free-Content-Bereich auf der Catandary-Website dient. Sie deckt alle relevanten Industrie-Vertikale ab und fungiert als Lead-Generator für die kostenpflichtigen Catandary-Services, insbesondere Catandary Foresight.

**Kernprinzipien:**
- Branchenübergreifend mit eigenständiger Catandary-Taxonomie (Vertikale + PESTEL + Mega/Macro/Micro)
- Nur legale Primärquellen (RSS-Feeds von Fachmedien, Presseverteilern, Marken-Newsrooms)
- Keine Aggregator-Seiten scrapen (Trendhunter etc.)
- Alle LLM-Verarbeitung lokal auf der **RTX 3090 (24 GB)** (produktive Linux-Workstation; VRAM per `nvidia-smi` verifizieren). Stage 6 (Content-Gen) auf llama.cpp **Gemma-4-26B-A4B** (aktuell seit #11 / 2026-07-14; Qwen3-30B-A3B und 35B bleiben installiert + revertierbar).
- Cloud-APIs nur als Fallback für komplexe Synthese-Aufgaben
- Modularer Aufbau: Neue Vertikale können ohne Architekturänderung hinzugefügt werden

---

## Catandary Trend-Taxonomie

### Industrie-Vertikale (eigenständige Catandary-Struktur)

| Vertikale | Kürzel | Abdeckung | Beispiel-Signale |
|---|---|---|---|
| **Food & Beverage** | FOOD | Lebensmittel, Getränke, Gastronomie, AgriTech | Plant-Based, Fermentation, Functional Foods |
| **Technology & AI** | TECH | Software, Hardware, AI, Robotik, IoT | GenAI-Tools, Wearables, Edge Computing |
| **Health & Wellness** | HEALTH | Medizin, klinische Wellness, Mental Health, Pharma, Supplements, körperphysiologische Fitness | Digital Health, Longevity, Microbiome |
| **Sustainability & Eco** | ECO | Energie, Kreislaufwirtschaft, Klima, Mobilität | Carbon Capture, Circular Packaging, EV |
| **Design & Architecture** | DESIGN | Produktdesign, Architektur, Interiors, UX | Biophilic Design, Modular Housing |
| **Fashion & Beauty** | FASHION | Mode, Kosmetik, Textil, Schmuck | Slow Fashion, Biotech Materials, Clean Beauty |
| **Business & Retail** | BIZ | Strategie, Startups, Handel, E-Commerce, Fintech | D2C, Recommerce, Embedded Finance |
| **Lifestyle** | LIFESTYLE | Kultur, Entertainment, Social Media, Gaming, Kunst, Bildung, Inklusion, Luxury, Travel, Sport (Athleten/Events/Communities/Studios) | Creator Economy, Spatial Computing, Experiential Luxury, EdTech, Hyrox |

### PESTEL-Klassifizierung (quer zu den Vertikalen)

Jeder Trend wird zusätzlich einer oder mehreren PESTEL-Dimensionen zugeordnet:

| Dimension | Kürzel | Farbe (UI) | Beispiele |
|---|---|---|---|
| **Political** | P | Rot | Regulierung, Trade Policy, Subventionen |
| **Economic** | E | Blau | Preisdruck, Funding, Marktkonsolidierung |
| **Social** | S | Grün | Verbraucherverhalten, Demografie, Werte |
| **Technological** | T | Violett | Neue Technologien, Patente, F&E |
| **Environmental** | En | Türkis | Nachhaltigkeit, Klima, Ressourcen |
| **Legal** | L | Orange | Gesetze, Compliance, IP-Schutz |

### Mega/Macro/Micro-Ebenen (Catandary Foresight Taxonomie)

| Ebene | Zeithorizont | Beispiel |
|---|---|---|
| **Mega-Trend** | 10-25 Jahre | "Personalisierte Ernährung" |
| **Macro-Trend** | 3-10 Jahre | "Functional Foods mit Darm-Hirn-Achse-Fokus" |
| **Micro-Trend** | 6 Monate - 3 Jahre | "Postbiotische Snack-Bars mit Mood-Claims" |

Die Mega/Macro-Einordnung wird auf der Free-Seite nur angeteasert – die vollständige Prognose ist Catandary-Foresight-Content.

---

## Hardware-Basis

- **GPU:** NVIDIA RTX 3090 (24 GB GDDR6X) — die produktive lokale Karte (per `nvidia-smi` bestätigt). Vor jeder VRAM-/Koexistenz-Entscheidung trotzdem `nvidia-smi` prüfen (llama-server hält ~22 GB im Ruhezustand). *(Frühere Doku nannte alternativ eine 16-GB-Karte; produktiv ist es die 3090.)*
- **Modelle laufen sequentiell** (nicht parallel) – VRAM wird zwischen Schritten freigegeben
- **Peak-VRAM Ollama-Pfad:** ~10.7 GB (Qwen3 14B Q4_K_M) — passt auf der 24-GB-Karte mit Headroom
- **llama.cpp-Pfad für Stage 6 (Content-Gen), aktuell:** **Gemma-4-26B-A4B-it-qat-UD-Q4_K_XL** (`start-gemma4-26b.sh`) — Umstellung von Qwen3-30B via #11 (2026-07-14) nach einem kontrollierten A/B: das 30B erfand in 32,9 % der Bodies erfundene Spezifika (fake Gesetze/Städte), das Gemma-26B nur 8,6 % und trifft zudem das 150–250-Wörter-Ziel, das das 30B unterschritt. Qwen3-30B-A3B-Q4_K_M (~18 GB) und Qwen3.6-35B-A3B (~24 GB) bleiben installiert und sind per `STAGE5_MODEL`/`STAGE5_START` **revertierbar**. Mid-Pipeline-GPU-Handover (siehe `pipeline/gpu_handover.py`). Default-Backend (ohne `scheduled_cycle.sh`) bleibt Ollama.
- **Ollama-Konfiguration:** `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_KEEP_ALIVE=5m`

---

## Datenbeschaffung: Legale Quellenstrategie

### Schicht 1: Direkte Primärquellen via RSS (nach Vertikale)

Quellen werden pro Vertikale organisiert. Neue Vertikale starten mit 3-5 Kernquellen und wachsen organisch. Feed-URLs sind zu verifizieren.

**FOOD & BEVERAGE:**
| Quelle | Typ | Fokus |
|---|---|---|
| FoodNavigator | Fachpresse | Ingredients, Regulation, Innovation |
| Food Dive | Fachpresse | Business, Supply Chain, M&A |
| The Spoon | FoodTech | Technology, AgriTech, Delivery |
| FoodBev Media | Fachpresse | Product Launches, Packaging |
| New Food Magazine | Fachpresse | Processing, Safety, Science |

**TECHNOLOGY & AI:**
| Quelle | Typ | Fokus |
|---|---|---|
| TechCrunch | Tech-Presse | Startups, Funding, Product Launches |
| The Verge | Tech-Presse | Consumer Tech, Culture, Policy |
| Ars Technica | Tech-Presse | Deep Tech, Science, Policy |
| MIT Technology Review | Forschung | Emerging Tech, AI, Biotech |
| VentureBeat (AI) | Tech-Presse | AI/ML, Enterprise, Startups |

**HEALTH & WELLNESS:**
| Quelle | Typ | Fokus |
|---|---|---|
| STAT News | Fachpresse | Pharma, Biotech, Health Policy |
| Mobihealthnews | Fachpresse | Digital Health, Wearables |
| Nutraingredients | Fachpresse | Supplements, Functional, Nutrition |
| Fierce Healthcare | Fachpresse | Health Systems, Insurance, AI |

**SUSTAINABILITY & ECO:**
| Quelle | Typ | Fokus |
|---|---|---|
| GreenBiz | Fachpresse | Corporate Sustainability, Circular |
| CleanTechnica | Fachpresse | Renewable Energy, EV, Storage |
| Packaging Dive | Fachpresse | Sustainable Packaging, Materials |
| Carbon Brief | Forschung | Climate Science, Policy |

**DESIGN & ARCHITECTURE:**
| Quelle | Typ | Fokus |
|---|---|---|
| Dezeen | Fachpresse | Architecture, Product Design |
| ArchDaily | Fachpresse | Architecture, Urban Planning |
| Core77 | Fachpresse | Industrial Design, UX |
| Designboom | Fachpresse | Art, Design, Technology |

**FASHION & BEAUTY:**
| Quelle | Typ | Fokus |
|---|---|---|
| Business of Fashion | Fachpresse | Fashion Business, Strategy |
| Cosmetics Design | Fachpresse | Beauty, Ingredients, Innovation |
| Vogue Business | Fachpresse | Luxury, Retail, Consumer |
| Sourcing Journal | Fachpresse | Supply Chain, Textiles |

**BUSINESS & RETAIL:**
| Quelle | Typ | Fokus |
|---|---|---|
| Retail Dive | Fachpresse | Retail, E-Commerce, DTC |
| Fast Company | Business-Presse | Innovation, Leadership |
| Finextra | Fachpresse | Fintech, Banking, Payments |
| CB Insights (Blog) | Research | Startups, Markets, VC |

**LIFESTYLE (Kultur, Entertainment, Social Impact, Luxury):**
| Quelle | Typ | Fokus |
|---|---|---|
| Nieman Lab | Fachpresse | Media, Journalism, Platforms |
| The Creator Economy | Fachpresse | Creators, Social Media |
| Game Industry.biz | Fachpresse | Gaming, Interactive Media |

**Cross-Industry Presseverteiler:**
| Quelle | Typ | Nutzung |
|---|---|---|
| PR Newswire | Pressemitteilungen | Alle Kategorien, Filter nach Branche |
| BusinessWire | Pressemitteilungen | Alle Kategorien, Filter nach Branche |
| GlobeNewswire | Pressemitteilungen | Alle Kategorien, Filter nach Branche |

**Ergänzende Datenquellen:**
| Quelle | Zugang | Typ |
|---|---|---|
| Exploding Topics API | API, $249/Monat | Cross-Industry Trend-Daten |
| Google Trends | pytrends (kostenlos) | Validierung aller Vertikalen |
| Reddit (diverse Subreddits) | Offizielle API | Community-Signale |
| Hacker News | RSS/API | Tech-Signale |

### Quellenwachstum

Neue Quellen werden manuell kuratiert und in `sources.yaml` eingetragen. Kein automatisches Scraping oder Aggregator-Quellen. Trendhunter und Brave Search Radar wurden entfernt (2026-04-12) — **137 aktive RSS-Primärquellen** (Stand 2026-05-29) decken alle 8 Vertikale ab. Ausbau auf nicht-RSS-Quellentypen siehe `pipeline_expansion_prompt.md` und Goal Contract unter `goals/`.

---

## LLM-Pipeline: Modellarchitektur

### Modell-Zuordnung pro Pipeline-Schritt

| Schritt | Modell | VRAM | Speed (Referenz) | Backend |
|---|---|---|---|---|
| 1. Relevanz-Filter | Qwen3 8B Q4_K_M | ~6.5 GB | ~129 t/s | Ollama (`ollama pull qwen3:8b`) |
| 2. Strukturierte Extraktion | NuExtract 3.8B | ~4 GB | ~200+ t/s | Ollama (`ollama pull nuextract`) — derzeit Fallback auf qwen3:8b |
| 3. NER (Markennamen) | Qwen3 8B Q4_K_M | ~6.5 GB | ~129 t/s | Ollama |
| 4. Klassifizierung | Qwen3 8B Q4_K_M | ~6.5 GB | ~129 t/s | Ollama |
| 5. Content-Generierung (EN) | Qwen3 14B Q4_K_M (Ollama-Fallback) **oder** Gemma-4-26B-A4B (llama.cpp, aktuell; 30B/35B revertierbar) | ~10.7 GB / ~16 GB | ~80 t/s / ~110 t/s | Ollama (Default) **oder** llama.cpp (`STAGE5_BACKEND=llamacpp`, nur 24-GB-Karte, mit GPU-Handover) |
| 6. Embeddings | Qwen3-Embedding 8B | ~5–6 GB | Batch | Ollama (`ollama pull qwen3-embedding`) |

> **⚠️ Backend-Realität (Stand 2026-07-01):** Die „Backend"-Spalte zeigt den **Config-Default** (`ollama` — Modell-Refs oben). **Produktiv läuft der ganze Cycle aber auf llama.cpp:** `scheduled_cycle.sh` setzt `STAGE_8B_BACKEND`/`EMBED_BACKEND`/`STAGE5_BACKEND=llamacpp`, sodass **alle** LLM-Stages (Relevanz/Extraktion/Klassifizierung/Reclassify auf dem 208K-8B, Embeddings, Content-Gen auf dem Gemma-4-26B) über den **llama-server (:8090)** laufen — Beleg: ein realer Cycle machte 3.922 `/v1/chat/completions` + 60 `/v1/embeddings` auf :8090 und **0** Inferenz-Calls auf Ollama. Ollama bleibt der **Default/Fallback** (greift nur, wenn `STAGE*_BACKEND=ollama`), plus optional `CLASSIFY_BACKEND=anthropic` für Stages 2/3/4/8 off-GPU.
>
> **Kein Ollama-Zwang mehr im Full Cycle:** `run_full_cycle` erkennt seit 2026-07-01 die aktiven GPU-Backends. Läuft alles auf llama.cpp, wird der frühere Ollama-Preflight (`check_ollama` + `check_gpu` lädt qwen3:14b als CPU-Offload-Canary) **übersprungen** und stattdessen `check_gpu_nvidia_smi()` genutzt (nur `nvidia-smi`, kein Modell-Load). → **Ein llama.cpp-Cycle braucht Ollama nicht** (nicht mal laufend). Nur wenn ein GPU-Stage auf `ollama` steht, wird Ollama geprüft/benötigt.
>
> **Hybrid-Klassifikation ist Default im RSS-Cycle (seit 2026-07-11, #41, `7d03d14`):** `RSS_CLASSIFY_MODE=hybrid` — embed-first, dann **Distill-Embedding-Heads** für Vertical/Mega/PESTEL (GPU-frei, Sekunden statt Minuten). Relevanz als **Hybrid-Gate**: Distill entscheidet die sicheren Ränder (≥0.7 behalten, <0.3 verwerfen), nur das unsichere Band geht ans 8B (~21 % real). Extraktion (Markennamen) + Content-Gen bleiben LLM. Embeddings werden persistiert (auch für Gefilterte — Trend-Drift-Hedge), Stage 5 macht nur noch Dedup. Fallback: `RSS_CLASSIFY_MODE=llm` = alter Voll-8B-Pfad; lädt der Head nicht, fällt der Cycle automatisch zurück. Referenzwerte Prod-Cycle 2026-07-12: 0 Fehler, Stage-8-Korrekturquote ~3,5 % (Drift-Wächter: Retrain bei dauerhaft >30 % oder 8B-Band >35 %).

**Alternative Modelle zum Testen:**
- Relevanz-Filter: Gemma 3 4B (`ollama pull gemma3:4b`, ~3.5 GB) – noch schneller
- Extraktion: Qwen3 8B mit Structured Output als Alternative zu NuExtract
- Content-Gen: Qwen3.5 9B (`ollama pull qwen3.5:9b`, ~6.6 GB) – neuer, kompakter
- Content-Gen: Mistral Small 3.2 24B – beste Sprachqualität, braucht aber CPU-Offloading
- Embeddings: jina-embeddings-v2-base-de (~323 MB) – speziell Deutsch+Englisch, minimaler VRAM

### Pipeline-Ablauf pro RSS-Eintrag

```
RSS-Eintrag (Titel + Teaser + URL + Datum)
    │
    ▼
[Schritt 1] RELEVANZ-FILTER (Qwen3 8B)
    "Ist das ein relevantes Trend-Signal?"
    → ja/nein/grenzwertig + confidence score
    → Vertikale zuordnen: FOOD/TECH/HEALTH/ECO/DESIGN/FASHION/BIZ/LIFESTYLE
    → Wenn nein: archivieren als "gefiltert", Ende
    │
    ▼
[Schritt 2] STRUKTURIERTE EXTRAKTION (NuExtract)
    Template: {brand_name, product_name, source_type, key_claims}
    → Rein extraktiv, nur Text der im Original steht
    → Temperatur: 0
    │
    ▼
[Schritt 3] NER + KLASSIFIZIERUNG (Qwen3 8B)
    Structured Output mit Pydantic-Schema:
    {
        verticals: ["FOOD", "HEALTH", ...],  // Kann cross-vertical sein
        pestel: ["T", "S", "En"],  // PESTEL-Dimensionen
        tags: ["protein", "ai-powered", "circular", ...],
        trend_signal_type: "product_launch" | "research" | "market_shift" |
                           "consumer_behavior" | "regulation" | "funding" |
                           "partnership" | "patent",
        regions: ["US", "EU", "APAC", "Global", ...],
        mega_trend: "Personalized Nutrition" | "Generative AI" | "Circular Economy" | ...
    }
    → Temperatur: 0
    │
    ▼
[Schritt 4] DUPLIKAT-CHECK (Qwen3-Embedding)
    → Embedding generieren
    → Cosine-Similarity gegen letzte 30 Tage prüfen
    → Wenn >0.92 Similarity: als Duplikat markieren, Ende
    │
    ▼
[Schritt 5] CONTENT-GENERIERUNG EN (llama.cpp Gemma-4-26B / Ollama 14B)
    → Eigener Trend-Artikel (150-250 Wörter)
    → Analytischer, professioneller Ton
    → Quellennennung + Backlink Pflicht
    → MUSS sich substanziell vom Original unterscheiden
    → HARD RULE Sprache: title + body IMMER Englisch, auch bei
      nicht-englischer (z. B. deutscher) Quelle → übersetzen, nie echoen
    → Temperatur: 0.6-0.8
    │
    ▼
[Schritt 6] ÜBERSETZUNG DE — ENTFÄLLT (seit ~2026-06)
    → DE-Content wurde geskippt: `title_de`/`summary_de`/`body_de` bleiben NULL.
      Pipeline erzeugt nur EN-Content (`title_en`/`body_en`). Die DE-Spalten im
      Datenmodell bleiben für evtl. spätere Reaktivierung erhalten, werden aber
      nicht mehr befüllt.
    │
    ▼
[Schritt 7] INSERT (trends Tabelle, Status: "draft")
    │
    ▼
[Schritt 8] RECLASSIFY (Qwen3 8B)
    → Vertikale per LLM-Semantic-Check korrigieren
    → Fängt Fehlklassifizierungen aus Schritt 3 ab
    │
    ▼
[Schritt 9] AUTO-PUBLISH
    → Status: "draft" → "published" wenn confidence >= 0.85
    → Niedrigere Confidence bleibt als Draft für manuelles Review
```

### Structured Output: Produktionsreife Absicherung

```python
from pydantic import BaseModel
from ollama import chat
from typing import Literal
import time

class TrendSignal(BaseModel):
    is_relevant: bool
    confidence: float
    primary_vertical: Literal["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]
    brand_name: str | None
    categories: list[str]
    tags: list[str]
    trend_signal_type: Literal[
        "product_launch", "research", "market_shift",
        "consumer_behavior", "regulation", "funding"
    ]

def extract_with_retry(model: str, prompt: str, schema, max_retries: int = 3):
    """Structured extraction mit Retry-Loop und Fallback."""
    for attempt in range(max_retries):
        try:
            response = chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                format=schema.model_json_schema(),
                options={"temperature": 0}
            )
            result = schema.model_validate_json(response["message"]["content"])
            return result
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            # Fallback auf anderes Modell
            try:
                response = chat(
                    model="qwen3:8b" if model != "qwen3:8b" else "nuextract",
                    messages=[{"role": "user", "content": prompt}],
                    format=schema.model_json_schema(),
                    options={"temperature": 0}
                )
                return schema.model_validate_json(response["message"]["content"])
            except:
                return None  # Log als Fehler, manuell reviewen
```

---

## Datenmodell

```sql
-- Quellen-Registry
CREATE TABLE sources (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    feed_url TEXT NOT NULL,
    source_type TEXT CHECK (source_type IN ('trade_media', 'press_wire', 'brand', 'api', 'radar')),
    vertical TEXT CHECK (vertical IN ('FOOD','TECH','HEALTH','ECO','DESIGN','FASHION','BIZ','LIFESTYLE','CROSS')),
    sub_categories JSONB DEFAULT '[]',
    active BOOLEAN DEFAULT true,
    auto_discovered BOOLEAN DEFAULT false,
    discovery_count INTEGER DEFAULT 0,
    last_fetched TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rohdaten aus Feeds
CREATE TABLE raw_entries (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id),
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    excerpt TEXT,
    raw_content TEXT,
    published_date TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT false,
    filtered_out BOOLEAN DEFAULT false,
    filter_reason TEXT
);

-- Kuratierte Trend-Artikel
CREATE TABLE trends (
    id SERIAL PRIMARY KEY,
    raw_entry_id INTEGER REFERENCES raw_entries(id),
    title_en TEXT NOT NULL,
    title_de TEXT,                     -- *_de-Spalten bleiben NULL (DE-Content seit ~2026-06 geskippt, Spalten für spätere Reaktivierung erhalten)
    slug TEXT UNIQUE NOT NULL,
    summary_en TEXT,
    summary_de TEXT,
    body_en TEXT,
    body_de TEXT,
    -- Catandary-Taxonomie
    verticals JSONB DEFAULT '[]',     -- ["FOOD", "HEALTH"] (cross-vertical möglich)
    primary_vertical TEXT,             -- Haupt-Vertikale für Routing
    pestel JSONB DEFAULT '[]',        -- ["T", "S", "En"]
    tags JSONB DEFAULT '[]',
    trend_signal_type TEXT,
    -- Mega/Macro/Micro (Foresight-Teaser)
    mega_trend TEXT,
    macro_trend TEXT,                  -- Nur auf Foresight voll sichtbar
    trend_level TEXT CHECK (trend_level IN ('mega', 'macro', 'micro')),
    -- Entitäten
    brands JSONB DEFAULT '[]',
    companies JSONB DEFAULT '[]',
    people JSONB DEFAULT '[]',
    regions JSONB DEFAULT '[]',
    -- Scoring
    trend_score REAL,
    confidence REAL,
    -- Quelle
    source_url TEXT NOT NULL,
    source_name TEXT,
    -- Embeddings (qwen3-embedding = 4096-dim; pgvector ANN-Index cappt bei 2000 → für indizierte Suche truncaten)
    embedding VECTOR(4096),
    -- Status
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'published', 'rejected', 'signal')),
    auto_published BOOLEAN DEFAULT false,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Engagement-Tracking (für späteres Foresight-Feedback)
CREATE TABLE trend_metrics (
    id SERIAL PRIMARY KEY,
    trend_id INTEGER REFERENCES trends(id),
    page_views INTEGER DEFAULT 0,
    unique_visitors INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    newsletter_clicks INTEGER DEFAULT 0,
    avg_time_on_page REAL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cross-Vertical Trend-Cluster (für Foresight)
CREATE TABLE trend_clusters (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    verticals JSONB DEFAULT '[]',
    pestel JSONB DEFAULT '[]',
    mega_trend TEXT,
    trend_ids JSONB DEFAULT '[]',     -- Array von trend.id
    cluster_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Automatisierung & Scheduling

### Cron-Jobs

```
# RSS-Feeds pollen (alle 4 Stunden)
0 */4 * * *  python pipeline/feed_poller.py

# LLM-Pipeline für neue Einträge (alle 4 Stunden, nach Polling)
30 */4 * * * python pipeline/llm_processor.py

# Auto-Publish ist in die LLM-Pipeline integriert (Stage 9+10: Reclassify → Auto-Publish)
# Standalone-Lauf nur als Fallback nötig:
# python pipeline/auto_publisher.py  (nutzt AUTO_PUBLISH_CONFIDENCE=0.85 aus config.py)

# Wöchentlicher Newsletter (Montag 9:00)
0 9 * * 1    python pipeline/newsletter_generator.py

# Source-Discovery Report (Freitag 17:00)
0 17 * * 5   python pipeline/source_report.py
```

### Feed-Poller Architektur

```python
# sources.yaml – Konfigurationsdatei für Quellen (pro Vertikale)
verticals:
  FOOD:
    sources:
      - name: FoodNavigator
        feed_url: https://www.foodnavigator.com/rss/...
        type: trade_media
      - name: Food Dive
        feed_url: https://www.fooddive.com/feeds/...
        type: trade_media

  TECH:
    sources:
      - name: TechCrunch
        feed_url: https://techcrunch.com/feed/
        type: trade_media
      - name: Ars Technica
        feed_url: https://feeds.arstechnica.com/arstechnica/index
        type: trade_media

  # ... weitere Vertikale nach gleichem Schema

cross_industry:
  press_wires:
    - name: PR Newswire
      feed_url: https://www.prnewswire.com/rss/...
      type: press_wire
    - name: BusinessWire
      feed_url: https://www.businesswire.com/rss/...
      type: press_wire
```

---

## Frontend: Catandary Trends Website

### Tech-Stack

- **Framework:** Next.js 14 (App Router) + TypeScript
- **Styling:** Tailwind CSS
- **DB-Anbindung:** Drizzle ORM + PostgreSQL (mit pgvector)
- **Hosting:** Hetzner VPS (bestehend)
- **Reverse Proxy:** Caddy (automatisches HTTPS via Let's Encrypt)
- **Domain:** catandary.de (Trends unter catandary.de/trends)
- **Newsletter:** Resend (oder Buttondown)
- **Process Manager:** PM2 oder systemd für Next.js + Pipeline-Prozesse

### Deployment auf Hetzner

```
# Caddy-Konfiguration (Caddyfile)
catandary.de {
    # Next.js App
    reverse_proxy localhost:3000

    # Statische Assets cachen
    @static path /trends/_next/static/*
    header @static Cache-Control "public, max-age=31536000, immutable"
}

# Oder als Subdomain falls bestehende Seite nicht stören:
# trends.catandary.de { reverse_proxy localhost:3000 }
```

```bash
# Deployment-Workflow auf Hetzner
git pull origin main
npm run build
pm2 restart catandary-trends

# PostgreSQL + pgvector auf Hetzner
sudo apt install postgresql postgresql-contrib
# pgvector Extension installieren
CREATE EXTENSION vector;
```

### Routing

```
catandary.de/trends                        → Hauptseite (alle Vertikale, Card-Grid)
catandary.de/trends/vertical/[v]           → Vertikale-Übersicht (z.B. /vertical/food)
catandary.de/trends/[slug]                 → Einzelner Trend-Artikel
catandary.de/trends/pestel/[dimension]     → PESTEL-Dimension (z.B. /pestel/technological)
catandary.de/trends/mega/[megatrend]       → Mega-Trend-Cluster (Teaser für Foresight)
catandary.de/trends/search                 → Volltextsuche + Filter
catandary.de/trends/newsletter             → Newsletter-Signup
```

### Design-Richtung

- Dark-Mode Card-Grid UI
- **Vertikale-Tabs** oder Filter-Bar oben (FOOD / TECH / HEALTH / ECO / DESIGN / FASHION / BIZ / LIFESTYLE)
- **PESTEL-farbcodierte Badges** auf jeder Karte
- **Vertikale-Icons** für schnelle visuelle Orientierung
- Trend-Score-Visualisierung pro Karte
- Cross-Vertical-Trends hervorgehoben ("Trends die mehrere Branchen betreffen")
- Prominente Quellennennung (Trust-Signal)
- "Powered by Catandary Foresight" CTA
- Newsletter-Signup (primärer Lead-Magnet)

### Lead-Capture-Strategie

- **Free Layer (Trends):** Kuratierte Artikel, Kategorisierung, Trend-Score
- **Teaser Layer:** Mega/Macro/Micro-Einordnung andeuten, aber nicht voll zeigen
- **Premium CTA:** "Vollständige Trend-Prognose → Catandary Foresight"
- **Gated Content:** Tiefere Analysen hinter Email-Gate
- **Newsletter:** Wöchentliche Top-Trends + Foresight-Teaser

---

## Sprint-Plan (alle Sprints abgeschlossen)

### Sprint 1 ✓ — Pipeline-MVP (FOOD + TECH)
- [x] Ollama-Setup, Feed-Poller, LLM-Pipeline, Pydantic-Schemas, Review-CLI

### Sprint 2 ✓ — Content-Generierung + DB
- [x] Content-Generierung DE+EN, Duplikat-Erkennung, PostgreSQL-Support, Radar-Pipeline

### Sprint 3 ✓ — Frontend-MVP
- [x] Next.js mit Dark-Mode Card-Grid, Vertical-Filter, PESTEL-Badges, DE/EN-Switcher

### Sprint 4 ✓ — Launch + HEALTH/ECO
- [x] HEALTH + ECO Vertikale, Newsletter, SEO, Deployment-Config

### Sprint 5 ✓ — DESIGN/FASHION/BIZ + Polish
- [x] Weitere Vertikale, Cross-Vertical Clustering, Mega-Trend-Seiten, Auto-Publish

### Sprint 6 ✓ — Vollausbau + Overhaul
- [x] Alle Vertikale live (8 Vertikale nach Konsolidierung)
- [x] CULTURE+SOCIAL+LUXURY → LIFESTYLE zusammengelegt
- [x] Trendhunter komplett ersetzt durch 43 Primärquellen + Brave Search Radar
- [x] Semantische Reklassifizierung aller 1226 Trends
- [x] CRS-Scoring, kanonische Mega-Trends-Taxonomie
- [x] Engagement-Tracking, Newsletter, Cluster-Dashboard

---

## Technische Randbedingungen

- **Domain:** catandary.de – alle URLs müssen dazu passen (catandary.de/trends/...)
- **Hosting:** Hetzner VPS mit Caddy als Reverse Proxy
- **Kein Scraping von Aggregator-Seiten** – nur Primärquellen über RSS/API
- **Quellennennung ist Pflicht** – jeder Artikel verlinkt zur Originalquelle
- **Content muss eigenständig sein** – LLM-Texte substanziell anders als Original
- **API-Kosten minimieren** – lokale Modelle (Ollama) für alles außer komplexe Synthese
- **Konfigurierbar** – neue Quellen ohne Code-Änderung via sources.yaml
- **Testbar** – Unit-Tests für Deduplizierung, Schema-Validierung, LLM-Output-Qualität
- **Modular** – Feed-Poller, LLM-Processor, Frontend sind unabhängige Komponenten

---

## Anweisungen für Claude Code (Autonomer Arbeitsmodus)

### ⚖️ Konstitutionelle Bedingung: Doku spiegelt immer die Realität

**Verbindlich bei jeder Arbeit in diesem Repo:** Die Repo-Dokumentation (`CLAUDE.md`, `README.md`, `docs/`) muss stets die **tatsächlichen aktuellen Bedingungen** des Repos widerspiegeln.

- **Ändert eine Arbeit reale Bedingungen** (Modelle, Backends, Defaults, Konfiguration, DB-Schema, Branch-Zustand, Pipeline-Verhalten, Cron/Deploy), wird die betroffene Doku **im selben Zug** mitgezogen — niemals stale Doku hinterlassen.
- **Gegen die Realität verifizieren, nicht die alte Doku fortschreiben:** aktive Start-Skripte/GGUFs/Env in `scheduled_cycle.sh`, `config.py`-Defaults, Schema in `pipeline/db.py` etc. tatsächlich prüfen statt annehmen.
- **Doku-Stand auf `dev` UND `epic/alpha` konsistent halten** (z. B. via isoliertem `git worktree`, ohne einen laufenden Cycle im Haupt-Tree zu stören).
- Ursprung dieser Regel (2026-07-18): Content-Gen lief real längst auf Gemma-4-26B, während CLAUDE.md/README noch 30B/35B nannten — solche Drift ist ab jetzt konstitutionell auszuschließen.

### Arbeitsweise

Claude Code soll **möglichst autonom** arbeiten. Das bedeutet:

- **Triff eigene Entscheidungen** bei Implementierungsdetails (Library-Wahl, Dateistruktur, Naming Conventions, Error-Handling-Patterns). Frage nicht nach Präferenzen – wähle die beste Option und baue weiter.
- **Implementiere vollständig.** Keine Platzhalter, keine TODOs, keine "hier musst du noch..."-Kommentare. Jede Datei soll lauffähig sein.
- **Teste während du baust.** Schreibe Unit-Tests für kritische Logik (Deduplizierung, Schema-Validierung, Feed-Parsing). Führe sie aus bevor du weitergehst.
- **Verifiziere RSS-Feeds.** Bevor du einen Feed in die sources.yaml einträgst, prüfe ob die URL tatsächlich erreichbar ist und valides RSS/Atom liefert.
- **Erstelle eine funktionierende .env.example** mit allen benötigten Umgebungsvariablen.
- **Schreibe ein README.md** mit Setup-Anweisungen (Ollama-Modelle, DB-Setup, Abhängigkeiten, Start-Befehle).
- **Git-Commits** nach jedem abgeschlossenen Feature-Block mit aussagekräftiger Commit-Message.
- **Git-Branches** für jeden Sprint, Merge via Pull Request in `main`.
- **Push regelmäßig** auf GitHub – nach jedem Feature-Block, mindestens am Ende jeder Arbeitssession.

### Git & GitHub Workflow

**Repository:** GitHub, Organisation/User: `ZuluTwoThree`, Repo-Name: `catandary-trends`

**Initialisierung (einmalig):**
```bash
git init
git remote add origin git@github.com:ZuluTwoThree/catandary-trends.git
```

**Branch-Strategie (seit 2026-07-08 — dev/main statt Sprint-Branches):**
- `main` – stabiler, deployter Prototyp (**"save"**). Prod-Server 3001 läuft von hier. Nur bewusst per Merge aus `dev` aktualisieren.
- `dev` – Integrations-Branch für laufende Arbeit. Hierhin committen; nach Stabilisierung → `main` mergen + 3001 neu bauen.
- Feature-Branches optional bei komplexen Features (von `dev` abzweigen, in `dev` zurück).
- `epic/alpha` – Branch der Alpha-Epic-Arbeit (Foresight-Engine/Monetarisierung/UX/Newsletter). **Stand 2026-07-18 vollständig in `dev` gemergt** (direkter Vorfahr, 0 eigene Commits, ~32 dahinter) — Merge epic/alpha→dev ist ein No-op; Branch kann nachgezogen oder gelöscht werden. Offener Alpha-Rest = Owner-Gates (Stripe/Resend/UX/Labels), kein Code-Blocker (siehe `docs/issue_status.md`).
- `product/trend-radar` – archivierte, divergente Produkt-Variante (Sales-Kit/Pricing/Kunden-Portal, Stand 2026-06-11). **Nicht in main/dev mergen** (reaktiviert das entfernte Brave-Search-Radar, 213 Commits hinter main) — nur als Referenz/Teil-Extraktion.
- Die alten `sprint/*`-Branches wurden 2026-07-08 gelöscht (waren vollständig in `main`).

**Commit-Konventionen:**
```
feat: add RSS feed poller with sources.yaml config
fix: handle malformed RSS entries gracefully
refactor: extract Ollama retry logic into shared client
test: add unit tests for deduplication
docs: update README with setup instructions
chore: add .gitignore, .env.example
```

**Workflow (dev → main):**
```bash
# Laufende Arbeit auf dev
git checkout dev
git pull

# Während der Arbeit: regelmäßig committen und pushen
git add -A
git commit -m "feat: implement feed poller for FOOD + TECH verticals"
git push origin dev

# Stabilen Stand nach main übernehmen (bewusster Schritt)
git checkout main
git merge dev
git push origin main
# danach 3001 neu bauen + Neustart über systemd (seit 2026-07-13, #38):
# cd frontend && npm run build && systemctl --user restart catandary-frontend
# (Unit: deploy/systemd/catandary-frontend.service — ohne DATABASE_URL, Socket-Default; Autostart via Linger)
```

**Claude Code soll autonom:**
- Auf `dev` committen und pushen; `main` nur per bewusstem Merge aktualisieren (main bleibt der deploybare "save")
- Nach jedem abgeschlossenen Feature committen und pushen
- Keine manuellen Merge-Konflikte hinterlassen

**Tags/Releases:**
- `v0.1.0` – Sprint 1 (Pipeline MVP)
- `v0.2.0` – Sprint 2 (Content Gen + DB)
- `v0.3.0` – Sprint 3 (Frontend MVP)
- `v0.4.0` – Sprint 4 (Launch)
- `v1.0.0` – Alle Vertikale live

### Entscheidungsprinzipien

Bei Unsicherheit, folge diesen Prinzipien:
1. **Einfachheit über Komplexität** – die einfachere Lösung ist fast immer besser
2. **Lauffähig über perfekt** – ein funktionierendes MVP schlägt eine halbe Idealarchitektur
3. **SQLite zuerst** – starte mit SQLite, PostgreSQL-Migration kommt in Sprint 2
4. **Weniger Quellen, dafür verifiziert** – lieber 3 funktionierende RSS-Feeds als 15 kaputte URLs
5. **Structured Output mit Retry** – immer Pydantic-Validierung + 3 Retries implementieren
6. **Logging überall** – jeder Pipeline-Schritt loggt Input, Output, Dauer, Fehler

### Projektstruktur (Empfohlen)

```
catandary-trends/
├── CLAUDE.md                    # Diese Datei
├── README.md                    # Setup & Usage (von Claude Code generiert)
├── .gitignore                   # Python, Node, .env, DB-Dateien
├── .env.example                 # Umgebungsvariablen (ohne Secrets)
├── sources.yaml                 # Quellen-Konfiguration
├── pipeline/
│   ├── __init__.py
│   ├── feed_poller.py           # RSS-Feed-Aggregation
│   ├── llm_processor.py         # LLM-Pipeline (Filter → Extract → Classify → Generate)
│   ├── auto_publisher.py        # Auto-Publish high-confidence Drafts
│   ├── newsletter_generator.py  # Wöchentlicher Newsletter
│   ├── source_report.py         # Neue-Quellen-Report
│   ├── models.py                # Pydantic-Schemas für LLM-Outputs
│   ├── db.py                    # Datenbank-Layer (SQLite → PostgreSQL)
│   ├── ollama_client.py         # Ollama-Wrapper mit Retry-Logic
│   └── config.py                # sources.yaml Loader + Settings
├── frontend/                    # Next.js App (ab Sprint 3)
│   ├── app/
│   │   ├── trends/
│   │   │   ├── page.tsx         # Hauptseite
│   │   │   ├── [slug]/page.tsx  # Einzelartikel
│   │   │   ├── vertical/[v]/page.tsx
│   │   │   └── ...
│   │   └── layout.tsx
│   ├── components/
│   ├── lib/
│   ├── tailwind.config.ts
│   └── package.json
├── tests/
│   ├── test_feed_poller.py
│   ├── test_llm_processor.py
│   ├── test_models.py
│   └── test_deduplication.py
├── scripts/
│   ├── setup_db.py              # DB-Initialisierung
│   ├── verify_feeds.py          # RSS-Feed-Validierung
│   └── review_cli.py            # Manueller Review-Client
└── requirements.txt
```

### Weiterentwicklung

**Das Backlog lebt seit 2026-07-02 in den [GitHub Issues](https://github.com/ZuluTwoThree/catandary-trends/issues)** (Labels: `foresight`, `acquisition`, `pipeline`, `frontend`, `content-quality`, `ops`, `prio-high`). Vor jeder neuen Feature-Planung **immer zuerst `gh issue list` prüfen** — die Issues enthalten den Kontext zu Ideen, die schon durchdacht oder angetestet wurden (Dry-Runs, Methodik-Notizen, Wiedervorlage-Kriterien). Neue Ideen, die nicht sofort umgesetzt werden, als Issue anlegen statt im Code oder Chat verloren gehen zu lassen. `BACKLOG.md` im Repo-Root ist nur noch die Issue-Übersicht + Meilenstein-Historie (Volltexte der alten Items: Git-Historie, Stand `1fd18e5`).

Alle 6 Sprints sind abgeschlossen. Neue Features und Verbesserungen werden direkt auf `main` oder in Feature-Branches entwickelt. Aktuelle Prioritäten:

1. **Pipeline-Automatisierung** — Cron-Jobs einrichten (Orchestrator-Script `run_full_cycle.py`, siehe BACKLOG.md)
2. **Newsletter** — `pipeline/newsletter_generator.py` fertigstellen, Anbindung an Resend/Buttondown
3. **Deployment auf Hetzner** — Caddy + PM2, README aktualisieren

**Hinweis zur Vertical-Balance:** LIFESTYLE, DESIGN und FASHION sind die *Now*-Trendsignale im Foresight-Modell (kurze Lead-Zeit). Ihr kombinierter Anteil (~18 %) ist gesund — keine aktive Quellenausweitung nötig.

---

## Quellenbalance & Pipeline-Optimierung (Stand: 2026-05-29)

### Ist-Zustand

137 aktive Quellen (87 Trade Media, 48 Research, 2 Press Wire). 38.689 Raw Entries, 26.374 published Trends, 21 kanonische Mega-Trends.

| Vertical | Trends | Anteil | Bewertung |
|----------|--------|--------|-----------|
| TECH | 9.623 | 36% | TECH-Dominanz hat zugenommen (vorher 32%) — Quellenvielfalt rechtfertigt das weiterhin |
| BIZ | 4.699 | 18% | Stabil hoch |
| HEALTH | 3.812 | 14% | Weiter gewachsen, Endpoints/Healthcare IT News tragen |
| ECO | 2.388 | 9% | Stabil |
| FOOD | 1.691 | 6% | Anteil **gesunken** (vorher 12%), aber 8 neue FOOD-Quellen seit 2026-05-24 noch in Catch-up — Effekt schlägt erst über Wochen voll durch |
| LIFESTYLE | 1.594 | 6% | Stabil |
| DESIGN | 1.343 | 5% | Stabil |
| FASHION | 1.224 | 5% | Stabil |
| **TOTAL** | **26.374** | **100%** | |

### Balance-Prinzip für die Datenpipeline

1. **TECH-Dominanz beobachten** — bei 36% durch Quellenvielfalt (VC/Startup + Deep Tech + Halbleiter + Quantum) erklärt, aber Trend zur weiteren Konzentration im Auge behalten
2. **Regelmäßiger Balance-Check** (monatlich): bei >3× Abweichung vom Median Quellen und Schwellenwerte anpassen
3. **FOOD-Catch-up** beobachten — die 8 Quellen aus dem 2026-05-24-Commit (`a561b74`) füttern erst seit dem 2026-05-25-Lauf. Anteil sollte sich über 4–6 Wochen Richtung historischer ~10–12% normalisieren.

### Geplante Quellen-Ergänzungen

Keine offenen Ergänzungen. Lebensmittelzeitung wurde in `sources.yaml` eingebunden.

---

## Stage-6 auf llama.cpp (Content-Gen; Gemma-4-26B aktuell seit #11 / 2026-07-14; 30B/35B revertierbar)

Auf der 24-GB-Karte kann Stage 6 (Content-Generierung) auf ein deutlich größeres Modell umgeleitet werden:

- **Modell (aktuell):** **Gemma-4-26B-A4B-it-qat-UD-Q4_K_XL** (~16 GB), Start-Skript `start-gemma4-26b.sh`. Umstellung von Qwen3-30B via **#11 (2026-07-14)** nach kontrolliertem A/B (n=70, Fisher p=0.013): 30B erfand in **32,9 %** der Bodies fake Spezifika (z. B. „Ordinance 2023-47"), Gemma-26B nur **8,6 %** und trifft das 150–250-Wörter-Ziel (das 30B unterschritt). Qwen3-30B-A3B (`start-qwen3-30b.sh`) und Qwen3.6-35B (`start-qwen3.6-35b.sh`) bleiben installiert und sind per `STAGE5_MODEL`/`STAGE5_START` **revertierbar**. Geladen via `llama-server` (systemd user unit `llama-server.service`, Port 8090).
- **Routing:** `STAGE5_BACKEND=llamacpp` in `scheduled_cycle.sh` aktiviert den Pfad — gegated nur darauf, dass das in `STAGE5_MODEL` gesetzte **Start-Skript** (aktuell `start-gemma4-26b.sh`) existiert und das erwartete GGUF referenziert, **nicht** darauf, worauf `start-active.sh` beim Start zeigt. Content-Gen versucht damit **immer** das gesetzte Modell, egal welches Modell (oder keines) bei Pipeline-Start geladen war.
- **GPU-Handover:** `pipeline/gpu_handover.py` (`content_gen_on_llamacpp`) **hängt vor Stage 6 den Symlink `start-active.sh` selbst auf das Content-Gen-Start-Skript um** (speichert das vorherige Ziel), entlädt die Ollama-Modelle, startet llama-server, und stoppt es nach Stage 6 wieder + **stellt den Symlink zurück** (wie die 8B-/Embedding-Handover). Der Pre-Flight prüft danach konsistent das nun gesetzte Modell — OOM-Schutz bleibt. Stages 7–9 nutzen Ollama wieder (Qwen3 8B für Reclassify on-demand). MODEL_START_SCRIPTS mappt die Content-Gen-GGUFs (Gemma-26B + 30B + 35B) auf ihre Start-Skripte.
- **Content-Guard:** Wortzahl-Validator retryt bis zu 3× bei vorzeitig terminierten Body-Strings (Grammar-Artefakt bei temp 0.7). In den ersten vier Nachtläufen war die "alle 3 Versuche failed"-Rate <0,25 %.
- **Rückbau:** `STAGE5_BACKEND=ollama` (Env-Override) erzwingt den Ollama-14B-Pfad. Alternativ das Content-Gen-Start-Skript entfernen/umbenennen → `scheduled_cycle.sh` fällt automatisch auf Ollama zurück. **Zurück auf 30B/35B:** in `scheduled_cycle.sh` `STAGE5_MODEL`/`STAGE5_START` auf `start-qwen3-30b.sh` bzw. `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` + `start-qwen3.6-35b.sh` zeigen lassen. (Das bloße Umhängen von `start-active.sh` deaktiviert den Pfad **nicht** — der Handover hängt selbst um.)
- **Zugehörige Goals:** offene Erweiterung der Quellen-Architektur, siehe `goals/` und `pipeline_expansion_prompt.md`.

## Technische Hinweise

- Ollama läuft als Windows-Exe auf `127.0.0.1:11434`. Env: `OLLAMA_CLIENT_HOST=http://127.0.0.1:11434`
- Python: `C:\Users\Dirk\AppData\Local\Programs\Python\Python313\python.exe` (oder Git Bash: `/c/Users/Dirk/AppData/Local/Programs/Python/Python313/python.exe`); auf der Linux-Workstation `.venv/bin/python` im Repo
- LLM-Processor Default-Batch ist 10, für große Batches: `python -m pipeline.llm_processor 200`
- Pipeline-Output in Datei umleiten (nicht pipen!): `python -m pipeline.llm_processor 200 > data/llm_processor.log 2>&1`
- Frontend Dev-Server auf Port 3001 (Port 3000 belegt durch Open WebUI)
- Qwen3 braucht `think=False` in Ollama-Calls (oder `enable_thinking=false` in llama.cpp) um Chain-of-Thought-Bloat zu vermeiden
