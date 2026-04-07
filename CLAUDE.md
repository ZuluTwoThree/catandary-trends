# Catandary Trends – Lokale Cross-Industry Trend Intelligence Pipeline

## Architekturübersicht

Catandary Trends ist eine branchenübergreifende Trend-Intelligence-Plattform, die auf lokalen LLMs (Ollama) läuft und als öffentlicher Free-Content-Bereich auf der Catandary-Website dient. Sie deckt alle relevanten Industrie-Vertikale ab und fungiert als Lead-Generator für die kostenpflichtigen Catandary-Services, insbesondere Catandary Foresight.

**Kernprinzipien:**
- Branchenübergreifend mit eigenständiger Catandary-Taxonomie (Vertikale + PESTEL + Mega/Macro/Micro)
- Nur legale Primärquellen (RSS-Feeds von Fachmedien, Presseverteilern, Marken-Newsrooms)
- Keine Aggregator-Seiten scrapen (Trendhunter etc.)
- Alle LLM-Verarbeitung lokal auf RTX 5080 (16GB VRAM)
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

- **GPU:** NVIDIA RTX 5080, 16GB GDDR7, 960 GB/s Bandbreite
- **Modelle laufen sequentiell** (nicht parallel) – VRAM wird zwischen Schritten freigegeben
- **Peak-VRAM:** ~10.7 GB (Qwen3 14B Q4_K_M), lässt Headroom für 16K Token Kontext
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

### Schicht 2: Brave Search als Cross-Industry Radar

Trendhunter wurde vollständig ersetzt (Stand: 2026-04-03). Stattdessen nutzt die Pipeline Brave Search API als Entdeckungsschicht:

- Pro Vertikale werden kuratierte Suchqueries ausgeführt
- Ergebnisse werden per LLM auf Trend-Relevanz gefiltert
- Originalquellen werden direkt identifiziert und in das Quellen-Netzwerk aufgenommen
- **Kein Scraping von Aggregator-Seiten**

### Schicht 3: Organisches Quellenwachstum

Das System lernt über Zeit:
- Neue Quellen-Domains, die über Brave Search Radar entdeckt werden, automatisch registrieren
- Nach 3+ Treffern von derselben Domain → RSS-Feed suchen und direkt anbinden
- Wöchentlicher Report: "Neue Quellen entdeckt, noch nicht als RSS eingebunden"

---

## LLM-Pipeline: Modellarchitektur

### Modell-Zuordnung pro Pipeline-Schritt

| Schritt | Modell | VRAM | Speed (RTX 5080) | Ollama-Befehl |
|---|---|---|---|---|
| 1. Relevanz-Filter | Qwen3 8B Q4_K_M | ~6.5 GB | ~129 t/s | `ollama pull qwen3:8b` |
| 2. Strukturierte Extraktion | NuExtract 3.8B | ~4 GB | ~200+ t/s | `ollama pull nuextract` |
| 3. NER (Markennamen) | Qwen3 8B Q4_K_M | ~6.5 GB | ~129 t/s | `ollama pull qwen3:8b` |
| 4. Klassifizierung | Qwen3 8B Q4_K_M | ~6.5 GB | ~129 t/s | `ollama pull qwen3:8b` |
| 5. Content-Generierung (DE+EN) | Qwen3 14B Q4_K_M | ~10.7 GB | ~80 t/s | `ollama pull qwen3:14b` |
| 6. Embeddings | Qwen3-Embedding 8B | ~5-6 GB | Batch | `ollama pull qwen3-embedding` |

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
[Schritt 5] CONTENT-GENERIERUNG (Qwen3 14B)
    → Eigener Trend-Artikel (150-250 Wörter), DE und EN separat
    → Analytischer, professioneller Ton
    → Quellennennung + Backlink Pflicht
    → MUSS sich substanziell vom Original unterscheiden
    → Temperatur: 0.6-0.8
    │
    ▼
[Schritt 6] REVIEW-QUEUE
    → Status: "draft" → manueller Quick-Check → "published"
    → Oder: Auto-Publish wenn confidence > 0.9 und kein Flag
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
    title_de TEXT,
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
    -- Embeddings
    embedding VECTOR(1024),
    -- Status
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'published', 'rejected')),
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

-- Source-Discovery-Log (Brave Search Radar)
CREATE TABLE source_discoveries (
    id SERIAL PRIMARY KEY,
    radar_source TEXT DEFAULT 'brave_search',
    radar_vertical TEXT,               -- welche Vertikale
    original_title TEXT,
    extracted_brand TEXT,
    discovered_url TEXT,
    discovered_domain TEXT,
    has_rss_feed BOOLEAN,
    feed_url TEXT,
    added_to_sources BOOLEAN DEFAULT false,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

# Brave Search Radar (1x täglich, morgens)
0 8 * * *    python pipeline/radar_discovery.py

# LLM-Pipeline für neue Einträge (alle 4 Stunden, nach Polling)
30 */4 * * * python pipeline/llm_processor.py

# Auto-Publish (stündlich, nur high-confidence Drafts)
0 * * * *    python pipeline/auto_publisher.py --min-confidence 0.9

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

### Radar-Discovery Pipeline (Brave Search)

```python
"""
Brave Search API → Trend-Signale finden → Originalquelle identifizieren
"""

def discover_sources_from_radar(verticals):
    for vertical, queries in verticals.items():
        for query in queries:
            # 1. Brave Search mit kuratierten Queries
            search_results = brave_search(query)

            # 2. Ergebnisse per LLM auf Trend-Relevanz filtern
            relevant = filter_trend_signals(search_results)

            # 3. Domain registrieren
            for result in relevant:
                log_discovery(result.brand, result.url, result.domain)

            # 4. Wenn Domain 3+ mal gesehen → RSS-Feed suchen
            if get_discovery_count(result.domain) >= 3:
                rss_feed = find_rss_feed(result.domain)
                if rss_feed:
                    add_to_sources(result.domain, rss_feed)
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

**Branch-Strategie:**
- `main` – stabiler, deployable Stand
- `sprint/1-pipeline-mvp` – Sprint-Branch, wird nach Abschluss in main gemergt
- `sprint/2-content-gen` – usw.
- Feature-Branches optional bei komplexen Features: `feature/radar-discovery`

**Commit-Konventionen:**
```
feat: add RSS feed poller with sources.yaml config
fix: handle malformed RSS entries gracefully
refactor: extract Ollama retry logic into shared client
test: add unit tests for deduplication
docs: update README with setup instructions
chore: add .gitignore, .env.example
```

**Workflow pro Sprint:**
```bash
# Sprint starten
git checkout main
git pull
git checkout -b sprint/1-pipeline-mvp

# Während der Arbeit: regelmäßig committen und pushen
git add -A
git commit -m "feat: implement feed poller for FOOD + TECH verticals"
git push -u origin sprint/1-pipeline-mvp

# Sprint abschließen
git checkout main
git merge sprint/1-pipeline-mvp
git push origin main
git tag -a v0.1.0 -m "Sprint 1: Pipeline MVP"
git push origin --tags
```

**Claude Code soll autonom:**
- Das Repo initialisieren falls noch nicht geschehen
- `.gitignore` erstellen (Python, Node, .env, __pycache__, .next, node_modules, *.db)
- Nach jedem abgeschlossenen Feature committen und pushen
- Sprint-Branch am Ende mergen und taggen
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
│   ├── radar_discovery.py       # Brave Search Radar → Source Discovery
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

Alle 6 Sprints sind abgeschlossen. Neue Features und Verbesserungen werden direkt auf `main` oder in Feature-Branches entwickelt. Aktuelle Prioritäten:

1. **Quellen-Ergänzung** — 7 verifizierte Feeds stehen bereit (siehe Quellenbalance)
2. **LIFESTYLE stärken** — neue Quellen für das schwächste Vertical finden
3. **Frontend-Polish** — README aktualisieren, Deployment auf Hetzner finalisieren
4. **Pipeline-Automatisierung** — Cron-Jobs auf Produktionssystem einrichten

---

## Quellenbalance & Pipeline-Optimierung (Stand: 2026-04-04)

### Ist-Zustand nach semantischem Overhaul

Nach der Reklassifizierung aller 1226 Trends und der Konsolidierung von CULTURE+SOCIAL+LUXURY → LIFESTYLE:

| Vertical | Trends | Anteil | Bewertung |
|----------|--------|--------|-----------|
| TECH | 401 | 33% | **Größtes Vertical** — breites Quellenspektrum (VC/Startup + Deep Tech) |
| FOOD | 254 | 21% | Deutlich reduziert nach semantischem Overhaul (vorher 32%) |
| BIZ | 124 | 10% | Verbessert, strategische Quellen fehlen noch |
| ECO | 116 | 9% | Ausbalanciert |
| HEALTH | 107 | 9% | Pharma/Biotech-Perspektive fehlt |
| DESIGN | 85 | 7% | Ausbalanciert |
| FASHION | 84 | 7% | OK |
| LIFESTYLE | 55 | 4% | **Schwächstes Vertical** — strukturell bedingt (RSS-Angebot dünn für Luxury/Culture-Nischen) |
| **TOTAL** | **1226** | **100%** | |

### Verifizierte Quellen-Ergänzungen (RSS-Feeds geprüft 2026-04-02, noch nicht eingebunden)

| Quelle | Feed-URL | Vertical | Typ | Begründung |
|--------|----------|----------|-----|------------|
| **McKinsey Insights** | `https://www.mckinsey.com/insights/rss` | BIZ | trade_media | Strategische Cross-Industry-Perspektive |
| **Endpoints News** | `https://endpts.com/feed/` | HEALTH | trade_media | Biotech, Pharma, Drug Development |
| **Healthcare IT News** | `https://www.healthcareitnews.com/feed` | HEALTH | trade_media | Digital Health, KI im Gesundheitswesen |
| **Wired** | `https://www.wired.com/feed/rss` | TECH | trade_media | Breitere Tech/Society-Perspektive |
| **IEEE Spectrum** | `https://spectrum.ieee.org/feeds/feed.rss` | TECH | trade_media | Deep Tech, Engineering, Forschung |
| **Glossy** | `https://www.glossy.co/feed/` | FASHION | trade_media | Fashion/Beauty-Industrie |
| **Platformer** | `https://platformer.news/rss/` | LIFESTYLE | trade_media | Tech-Policy, Platform-Regulierung, Social Media |

### Balance-Prinzip für die Datenpipeline

1. **Neue Quellen priorisiert für unterrepräsentierte Vertikale** (LIFESTYLE, FASHION, HEALTH, BIZ)
2. **TECH-Dominanz beobachten** — mit 33% aktuell größtes Vertical, aber durch Quellenvielfalt gerechtfertigt
3. **Regelmäßiger Balance-Check** (monatlich): bei >3x Abweichung vom Median Quellen und Schwellenwerte anpassen
4. **LIFESTYLE stärken**: Brand-Newsrooms (LVMH, Kering, Richemont), Gaming- und Creator-Economy-Quellen evaluieren

### FOOD-Vertical Aufspaltung — Entschärft

Nach dem semantischen Overhaul ist FOOD von 32% auf 21% geschrumpft. Eine Aufspaltung in Sub-Vertikale (FOODTECH, GASTRO, FOODRETAIL) ist damit **nicht mehr dringend**. Die Option bleibt als Sub-Tagging-Ansatz bestehen, falls FOOD wieder überproportional wächst.

### Geplante Quellen-Ergänzungen

| Quelle | Vertical | Status | Begründung |
|--------|----------|--------|------------|
| **Lebensmittelzeitung** | FOOD | RSS-Feed prüfen | Deutsche FOOD-Fachpresse, stärkt DE-Perspektive im FOOD-Vertical |

---

## Session-Log

### Session 2026-04-04 (Abend)

**Kontext:** LLM-Processor war vorzeitig abgebrochen, 194 Entries unverarbeitet.

**Durchgeführt:**
1. Ollama (Windows-Exe) war nicht erreichbar — neu gestartet, erreichbar über `172.29.96.1:11434` (WSL2 → Windows)
2. Python-Abhängigkeiten auf Windows Python 3.13 installiert (`/mnt/c/Users/Dirk/AppData/Local/Programs/Python/Python313/python.exe`)
3. LLM-Processor in mehreren Batches durchlaufen lassen (Batch-Limit default=10, per Argument auf 200 erhöht)
4. **Ergebnis:** 171 Entries verarbeitet (10 + 161), **109 neue Trends** erstellt, 62 gefiltert, 0 Fehler
5. DB-Stand danach: **3.644 Raw Entries**, **2.495 Trends** (davon 1.226 published, 1.269 drafts)

**Bekannte Probleme identifiziert:**
- `primary_vertical` wird im Relevanz-Filter oft falsch gesetzt (z.B. FASHION für Quantum-Computing) — Klassifizierungsschritt korrigiert `verticals`, aber `primary_vertical` bleibt falsch
- Mega-Trend-Zuordnung teilweise sinnlos (z.B. Neandertal-Genomik → `regenerative_design_and_net_positive`)

**Nächste Schritte (Post-Processing-Pipeline):**
1. `scripts/reclassify_verticals.py` — Verticals fixen (Qwen3 8B, ~65s/500 Trends)
2. `scripts/discover_mega_trends.py` — Mega-Trend-Kandidaten analysieren (kein LLM, Clustering)
3. `pipeline/mega_trend_reviewer.py` — Mega-Trends per LLM zuweisen (Qwen3 14B, ~15-25 Min)
4. `scripts/backfill_crs.py` — CRS-Scores berechnen (Formel, ~2s)

**Technische Hinweise:**
- Ollama läuft als Windows-Exe, WSL2 erreicht es über `OLLAMA_CLIENT_HOST=http://172.29.96.1:11434`
- Windows Python nutzen: `"/mnt/c/Users/Dirk/AppData/Local/Programs/Python/Python313/python.exe"`
- LLM-Processor Default-Batch ist 10, für große Batches Argument übergeben: `python -m pipeline.llm_processor 200`
