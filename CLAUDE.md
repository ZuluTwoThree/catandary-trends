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
- **llama.cpp-Pfad für Stage 6 (Content-Gen), aktuell:** **Gemma-4-26B-A4B-it-qat-UD-Q4_K_XL** (`start-gemma4-26b.sh`) — Umstellung von Qwen3-30B via #11 (2026-07-14) nach einem kontrollierten A/B: das 30B erfand in 32,9 % der Bodies erfundene Spezifika (fake Gesetze/Städte), das Gemma-26B nur 8,6 %. *(Die frühere Zusatzbehauptung, Gemma treffe das 150–250-Wörter-Ziel, ist durch den Dauerbetrieb widerlegt: der Median fiel am Umstiegstag von 131 auf 105 und liegt seither bei ~109. Owner hat ~100 am 2026-08-19 als Länge akzeptiert.)* Qwen3-30B-A3B-Q4_K_M (~18 GB) und Qwen3.6-35B-A3B (~24 GB) bleiben installiert und sind per `STAGE5_MODEL`/`STAGE5_START` **revertierbar**. Mid-Pipeline-GPU-Handover (siehe `pipeline/gpu_handover.py`). Default-Backend (ohne `scheduled_cycle.sh`) bleibt Ollama.
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

Neue Quellen werden manuell kuratiert und in `sources.yaml` eingetragen. Kein automatisches Scraping oder Aggregator-Quellen. Trendhunter und Brave Search Radar wurden entfernt (2026-04-12) — **257 aktive Quellen** (Stand 2026-08-07; RSS-Primärquellen + OpenAlex/Patente/Funding-Pseudoquellen) decken alle 8 Vertikale ab. 2026-08-07 kamen 15 verifizierte Feeds für die Taxonomie-Erweiterung dazu (Quantum/Semis/Space/Digital Health/Future of Work/Education — u. a. The Quantum Insider, NVIDIA/Intel/IBM Newsroom, SpaceNews, NASA/ESA, Rock Health, HR Dive, EdSurge). Ausbau auf nicht-RSS-Quellentypen siehe `pipeline_expansion_prompt.md` und Goal Contract unter `goals/`.

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
[Schritt 2] STRUKTURIERTE EXTRAKTION (Qwen3 8B; NuExtract-Fallback deaktiviert)
    Template: {brand_name, product_name, source_type, key_claims,
               key_figures, dates, quotes, geography}  (Listen gedeckelt)
    → Rein extraktiv, nur Text der im Original steht; Temperatur: 0
    → EXTRACTION_STRICT=1 (Default seit 2026-08-21): alle Felder Pflicht,
      quotes/geography werden auf Wörtlichkeit gefiltert (~5,3 s/Artikel)
    → key_figures kommen NICHT vom Modell: deterministisch per Regex aus der
      Quelle, jeder Eintrag mit wörtlichem Satzkontext (figures_with_context)
    → Alle Felder gehen in den Content-Prompt von Schritt 5 (seit 2026-08-21;
      vorher nur brand/product/claims — Artikel dadurch ~170 statt ~110 Wörter)
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
    → Eigener Trend-Artikel (~100 Wörter; Owner-Festlegung 2026-08-19.
      Der Prompt fragt weiterhin 150-250 — hoch fragen ist das, was ~100
      erzeugt. Guard-Untergrenze STAGE5_TARGET_BODY_WORDS=100.)
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
    │
    ▼
[Schritt 10] DRAFT-RICHTER (Qwen3.8-27B lokal; seit 2026-08-22, DRAFT_JUDGE=0 schaltet ab)
    → Beurteilt die frischen Drafts UNTER der Schwelle redaktionell
      (Kriterien der Haiku-Volldurchsicht: 71,6 % davon sind publizierbar,
      Confidence trennt kaum — docs/confidence_threshold_entscheidung_2026-08-21.md)
    → publish nur bei signal=true UND Kategorie ok; sonst ZURÜCKHALTEN, nie verwerfen
    → Jede Freigabe durch dieselben Gates wie Auto-Publish: Grounding,
      Truncation, pgvector-Dedup gegen Published (pipeline/draft_judge.py)
    → auto_published=true; Zahlen → data/draft_judge_last.json → Morgen-Mail
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

### Cron-Jobs (realer Stand seit 2026-08-09)

```
# Env-Zeilen sind Pflicht: cron hat keine systemd-User-Session — ohne
# XDG_RUNTIME_DIR schlagen die GPU-Handover (`systemctl --user`) still fehl.
XDG_RUNTIME_DIR=/run/user/1000
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

# Full Cycle Mo–Fr 04:00 (Feed-Polling + LLM-Pipeline + Auto-Publish in einem
# Lauf via scheduled_cycle.sh; Wrapper räumt vorher ALLES VRAM frei, auch
# manuell gestartete llama-server). Log: ~/logs/catandary-full-cycle-*.log
0 4 * * 1-5  scripts/full_cycle_cron.sh

# Waechter (seit 2026-08-17): meldet per Mail, wenn der Nachtlauf keine
# end-Zeile mit Exit-Code geschrieben hat. Der Wrapper schreibt sie als letzte
# Handlung — stirbt er vorher (Stromausfall 17.08.), fehlt sie einfach und
# niemand merkt es. Schweigen = alles in Ordnung. Wochenenden sind ausgenommen.
# Seit 2026-08-24 prüft er zusätzlich das heutige Backup-ARTEFAKT (existiert
# catandary-pg-<Datum>.dumpdir, toc.dat da, ≥1 GB?) — Log-Zeilen zählen nicht.
45 7 * * 1-5 cd <repo> && .venv/bin/python -m scripts.cycle_watchdog

# DB-Backup (täglich 02:45). Seit 2026-08-24: pg_dump -Fd -j4 + zstd:3 →
# catandary-pg-<Datum>.dumpdir (~113 GB, ~18 min), verifiziert per
# pg_restore --list gegen die Live-Tabellenzahl, Fehler FATAL. Der alte
# -Fc/-Z6-Dump lief ab 13.07. jede Nacht in den 1-h-Timeout, wurde als
# "non-fatal" verschluckt und meldete trotzdem "backup OK" — 42 Nächte ohne
# restaurierbares Postgres-Backup. Restore: docs/restore_runbook.md.
# keep-days 4 = Owner-Entscheidung 2026-08-24 (~480 GB Steady-State).
45 2 * * *   .venv/bin/python scripts/backup_db.py --dest /mnt/data-hdd/backups/catandary --skip-sqlite --keep-days 4

# Source-Discovery-Loop (Sonntag 06:00)
0 6 * * 0    .venv/bin/python scripts/discovery_loop.py

# Monatlicher Quellen-Check mit Issue-Post (1. des Monats, 08:00)
0 8 1 * *    .venv/bin/python scripts/monthly_source_check.py --post-issue

# Wöchentlicher Patent-Sweep (Dienstag 05:00; --kind both = Cr-Del + Amend,
# Amend trägt CPC-Codes + Zitationskanten nach — hält den SPNP/TIR-Graph aktuell)
0 5 * * 2    scripts/weekly_patents.sh

# Patentbasierte Rechnungen nach dem Sweep (Dienstag 08:00, seit 2026-08-09):
# build_cpc_tier_series + build_cpc_insights + assign_cpc (alles CPU/SQL).
# Radare + TIR-/SPNP-Forschungsläufe bewusst NICHT im Cron (Owner: on-demand).
0 8 * * 2    scripts/weekly_patent_analytics.sh

# OpenAlex-Monats-Sync (5. des Monats 07:00, seit 2026-08-15, #80): neue
# Snapshot-Partitionen → research_corpus (45M-Suchschicht) + Journal-/
# Autoren-Nebentabellen + Statistik-Refresh (Amend-Analog, CPU/Netz)
0 7 5 * *    scripts/sync_openalex_monthly.sh

# Nicht-RSS-Ingester wöchentlich (Samstag 05:00, seit 2026-08-09): Preprints
# (arXiv/bioRxiv/medRxiv, 14-Tage-Fenster) + Funding (NSF/NIH/OpenAIRE/UKRI,
# 45 Tage) + SEC Form D (Vorquartal, nur im 1. Quartalsmonat) + sofortige
# Distill-Verarbeitung der Neuzugänge via signal_batch_embedded (GPU-Handover).
# Seit 2026-08-23 (#87) zusätzlich die Startup-Explorer-Signale: Presse-Regex,
# HN-Launches (30-Tage-Fenster), ClinicalTrials-Sweep, FDA-510(k)-Bulk.
0 5 * * 6    scripts/weekly_ingesters.sh

# Startup-Explorer-Quellen monatlich (6. 12:00, seit 2026-08-23, #87): CORDIS +
# SBIR (--refresh) + GLEIF + Companies House + GLEIF/CH-Enrichment + Distill
# der Neuzugänge + HDD-Download-Cleanup. Firmenstamm-Rebuild, Wikidata und
# Brücken bewusst NICHT im Cron (Rebuild würde Enrichment verwerfen) — on-demand.
0 12 6 * *   scripts/monthly_startup_sources.sh
```

**Mengenbremse statt Quellen-Verbot (Owner-Präzisierung 2026-08-20):** Funding-News
dürfen über den regulären Cycle zu Artikeln werden. Verhindert wird nur, dass ein
Massen-Ingest en masse in die Content-Generierung läuft (235k SBIR/CORDIS-Zeilen
brachen den 04:00-Lauf an der 50k-Grenze ab): `get_unprocessed_entries` nimmt pro
Quelle und Lauf höchstens `CYCLE_MAX_PER_SOURCE` (Default 200; RSS-Normalbetrieb
liegt bei p95 ≈ 70/Tag) — der Rest bleibt liegen und gehört dem Distill-Pfad
(`signal_batch`). Die 50k-Sanity-Zählung in `scheduled_cycle.sh` zählt denselben
gebremsten Intake. Zusätzlich existiert `sources.llm_pipeline` als manueller
Notschalter (FALSE = Quelle liefert nie Artikelmaterial). **Gesetzt für „SEC
Form D" (id 260, Owner 2026-08-24):** die Reg-D-Stubs fluteten den Draft-Richter
(248 von 546 Gehaltenen am 24.08.) und sind als Drei-Datenpunkte-Meldungen kein
Artikelmaterial — sie bleiben Signale über den Distill-Pfad. Redaktionelle
Funding-News aus Fachmedien dürfen weiterhin Artikel werden (Präzisierung
2026-08-20 bleibt gültig).

Auto-Publish ist in die LLM-Pipeline integriert (Stage 8+9: Reclassify → Auto-Publish);
Standalone-Lauf nur als Fallback: `python pipeline/auto_publisher.py`
(nutzt `AUTO_PUBLISH_CONFIDENCE=0.85` aus config.py). Ein Newsletter-Cron ist
derzeit **nicht** eingerichtet (`pipeline/newsletter_generator.py` läuft manuell).

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

### Tech-Stack (Ist-Stand 2026-07-23)

- **Framework:** Next.js 16 (App Router, Turbopack-Dev) + TypeScript + React 19
- **Styling:** Tailwind CSS v4 (`@theme`-Tokens in `frontend/src/app/globals.css` — Designsystem „Editorial Intelligence": IBM Plex Serif/Mono/Sans, Ink `#0a0c0a`, Akzent Chartreuse `#d4ff3a`, scharfe Kanten)
- **DB-Anbindung:** eigener `pg`-Layer (`frontend/src/lib/pg.ts` + `db.ts`) auf PostgreSQL/pgvector, Socket-Default (kein Drizzle); teure Aggregat-Queries laufen über einen In-Process-TTL-Cache in `db.ts`
- **Auth/Paywall:** Magic-Link-Auth (`lib/auth.ts`) + Tier-Entitlements (`lib/entitlement.ts`, `lib/tiers.ts`, `TierGate`), Stripe-Checkout/Webhook; alles hinter `AUTH_ENABLED`/`PAYWALL_ENABLED` (Gates aus = alles offen)
- **Hosting:** Hetzner VPS (bestehend), lokal Port 3001 via systemd user unit `catandary-frontend`
- **Reverse Proxy:** Caddy (automatisches HTTPS via Let's Encrypt)
- **Domain:** catandary.de (Landing `/`, Trends unter `/trends`)
- **Newsletter:** Resend (Domain send.catandary.de)
- **Tests:** Vitest (`frontend/src/lib/*.test.ts`)

### Deployment auf Hetzner

```
# Caddy-Konfiguration (Caddyfile) — App läuft lokal auf :3001
catandary.de {
    # Next.js App
    reverse_proxy localhost:3001

    # Statische Assets cachen
    @static path /trends/_next/static/*
    header @static Cache-Control "public, max-age=31536000, immutable"
}

# Oder als Subdomain falls bestehende Seite nicht stören:
# trends.catandary.de { reverse_proxy localhost:3001 }
```

```bash
# Deployment-Workflow (lokal wie Hetzner) — systemd statt PM2 (seit #38)
git pull origin main
cd frontend && npm run build
systemctl --user restart catandary-frontend
# Unit: deploy/systemd/catandary-frontend.service (Socket-Default, Autostart via Linger)

# PostgreSQL + pgvector
sudo apt install postgresql postgresql-contrib
# pgvector Extension installieren
CREATE EXTENSION vector;
```

### Routing (Ist-Stand 2026-07-23)

```
/                                → Landing („The Instrument", Wertversprechen + Pricing-Teaser)
/trends                          → Hauptfeed (Card-Grid, Filter-Bar inkl. Suche ?q= — es gibt KEINE separate /trends/search-Route)
/trends/[slug]                   → Einzelner Trend-Artikel
/trends/vertical/[v]             → Redirect auf /trends?v=<VERTICAL>
/trends/mega, /trends/mega/[m]   → „Mega Signal Themes"-Übersicht (28 kuratierte Themes; „Megatrend" ist verdientes, gemessenes Badge — 12 Keys, Regel in scripts/measure_mega_axes.py) + Detail
/trends/foresight                → Foresight-Cockpit (Hub) + Unterseiten:
  /radar /clusters /technology /lead-time /evolution /dossier
  /research /patents               (Research-/Patent-Explorer)
  /ventures, /ventures/company/[id] → Startup Explorer (#87, seit 2026-08-23):
                                     Firmen-Korpus mit Evidenz-Timeline + Brücken
                                   (Tier-gegated: radar+clusters=Starter, technology+lead-time+
                                    evolution+dossier=Pro, On-Demand-Analyzer=Super Pro+;
                                    Free-Teaser bleibt sichtbar — „gate at the value drill-down")
/trends/methodology              → Methodik-/Trust-Seite
/trends/pricing                  → Pläne (Stripe-Checkout wenn konfiguriert)
/trends/newsletter (+/unsubscribe) → Newsletter-Signup/-Abmeldung
/account, /account/signin        → Konto + Magic-Link-Login (nur bei AUTH_ENABLED=1)
/imprint, /privacy               → Rechtstexte (Impressum-Adressblock = Owner-Gate vor Public-Launch)
```

Hinweis: Ein DE/EN-Switcher existiert nicht mehr — die Produktsprache ist durchgehend Englisch (DE-Content-Spalten bleiben NULL, s.o.).

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
- **Doku-Stand auf `dev` und `main` konsistent halten** (`dev` sofort mitziehen; `main` erhält den Stand beim bewussten Release-Merge). *(Der frühere Parallel-Zweig `epic/alpha` wurde am 2026-07-19 gelöscht — es gibt keinen zweiten Doku-Branch mehr zu pflegen.)*
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
- `product/trend-radar` – **Branch am 2026-07-19 gelöscht, als Tag `archive/product-trend-radar-2026-06-11` (57eecaf) archiviert.** War die divergente Produkt-Variante (Sales-Kit/Pricing/Kunden-Portal, Stand 2026-06-11, 338 hinter main). **Nicht in main/dev mergen** (reaktiviert das entfernte Brave-Search-Radar + Aggregator-Sourcing, gegen das Legal-Primärquellen-Prinzip). Bergbar aus dem Tag (extrahieren, nicht mergen): das Sales-/Business-Material unter `docs/sales/`, `docs/BUSINESS_PLAN.md`, `docs/SETUP_VERKAUF.md` — nutzt aber die **alte** 4-Tier-Preisstruktur (basic/team/pro/agency), abgelöst durch Starter/Pro/Super Pro+ + Hypercare.
- **Gelöschte Branches** (alle vollständig in `main` bzw. als Tag gesichert): `sprint/*` (2026-07-08), sowie `hardening/release-candidate` + `epic/alpha` (2026-07-19, nach dem Release-Merge `dev`→`main` PR #62). `epic/alpha` war die Alpha-Epic-Arbeit (Foresight/Monetarisierung/UX/Newsletter); ihre 2 Restcommits waren inhaltsgleiche Doku-Syncs, deren Endzustand in `main` steht. Offener Alpha-Rest = Owner-Gates (Stripe/Resend/UX/Labels), kein Code-Blocker (siehe `docs/issue_status.md`).
- `feature/foresight-radar` – **die gesamte Radar-/Foresight-Instrument-Arbeit, geparkt am 2026-08-07** (38 Commits, Basis `main` @ `146d522`). Enthält: Horizont-Radar (H1/H2/H3, kalibriert über 52 Felder), Cluster- und Mega-Trend-Radare, Signalwolke, Blechschmidt-Portfolio, und „Der Messtisch" (`pipeline/instrument.py`, `scripts/instrument.py`, `/trends/foresight/instrument`) inkl. Suchfeld-Einstieg, Korpus-Projektion und Automatisierung der Relevanzbewertung. Doku dazu: `docs/radar_*.md`, `docs/instrument_learning_curve.md`.
  - **Warum getrennt:** `dev` sollte für andere Entwicklung frei werden, ohne dass ein `dev`→`main`-Merge das unfertige Radar mitveröffentlicht (Owner 2026-08-07).
  - **Zustand bei Parkzeit:** lauffähig, 271 pytest / 142 vitest / tsc grün; läuft im Worktree `/home/dirk/projects/ct-dev` auf Port 3004.
  - **Wiederaufnahme:** auf dieser Branch weiterarbeiten, vorher `git rebase main` (die Nicht-Radar-Arbeit steckt bereits in `main`, es gab beim Parken keine Divergenz außerhalb der Radar-Dateien).
- **Aktiv sind `main`, `dev` und `feature/foresight-radar`.** Archiv-Referenzen liegen als `archive/*`-Tags (nicht als Branches).

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

## Quellenbalance & Pipeline-Optimierung

### Ist-Zustand (Stand 2026-08-07)

257 aktive Quellen. 21,6 Mio. Raw Entries, 1.134.488 Trends (67.035 published), **28 kanonische Mega-Trends** (22 + 6 neue Keys aus der Taxonomie-Erweiterung 2026-08-07: Quantum Information Science, Next-Gen Semiconductors, Orbital Economy, Evolution of Work Models, Education & Lifelong Learning, Digital Healthcare Integration — siehe `docs/mega_taxonomy_decision_2026-08-07.md`).

*(Die folgende Tabelle ist der historische Snapshot 2026-05-29 — nur published Trends der Frühphase; der heutige Korpus ist backfill-dominiert.)*

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

- **Modell (aktuell):** **Gemma-4-26B-A4B-it-qat-UD-Q4_K_XL** (~16 GB), Start-Skript `start-gemma4-26b.sh`. Umstellung von Qwen3-30B via **#11 (2026-07-14)** nach kontrolliertem A/B (n=70, Fisher p=0.013): 30B erfand in **32,9 %** der Bodies fake Spezifika (z. B. „Ordinance 2023-47"), Gemma-26B nur **8,6 %**. *(Die Wortziel-Behauptung ist widerlegt — Median am Umstiegstag 14.07. von 131 auf 105 gefallen, seither ~109. ~100 Wörter sind seit 2026-08-19 die akzeptierte Länge; siehe `docs/confidence_threshold_eval_2026-08-18.md`.)* Qwen3-30B-A3B (`start-qwen3-30b.sh`) und Qwen3.6-35B (`start-qwen3.6-35b.sh`) bleiben installiert und sind per `STAGE5_MODEL`/`STAGE5_START` **revertierbar**. Geladen via `llama-server` (systemd user unit `llama-server.service`, Port 8090).
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
