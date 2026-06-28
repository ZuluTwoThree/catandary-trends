# Catandary Trends — Backlog

## Status-Update 2026-05-29

- **Stage 6 (Content-Gen) auf llama.cpp 35B** seit 2026-05-25 produktiv (`5250ba8` + `91e0729`, vier saubere Nachtläufe in Folge). Architektur, Pre-Flight, Wortzahl-Guard, GPU-Handover und Rollback-Pfade dokumentiert in `CLAUDE.md`. Offene Folgearbeit: Stage 6 ⇄ andere Stages konsolidieren, ggf. Stage 4 (Classify) ebenfalls auf 35B testen.
- **Quellen-Expansion über RSS hinaus** als priorisiertes Vorhaben: Brief in `pipeline_expansion_prompt.md` (Commit `2f9db07`), aktiver Goal Contract `goals/2026-05-29-pipeline-expansion-mvp.md` (Deadline 2026-06-26, 30 published Trends aus 3 neuen `source_type`-Werten).
- **Newsletter**: KW15–KW21/2026 retroaktiv per Qwen3.6-35B-A3B generiert, persistiert in DB-Tabelle `newsletter_editions`, Frontend liest live. Offen bleibt nur die Automatisierung (Mo-09:00-Cron + Versand-Anbindung).
- **Pipeline-Lauf**: `scripts/scheduled_cycle.sh` ist die Referenz-Orchestrierung, läuft per transientem systemd-Timer (`systemd-run --user --on-calendar=…`). Tägliches DB-Backup via `scripts/backup_db.py` (Cron 00:05).

## Status-Update 2026-06-12 — Quellen-Port von product/trend-radar

- **Quellennetz vereinigt:** 192 Feeds (189 aktiv) — Upstream-Bestand + 62 verifizierte Zugänge
  aus `product/trend-radar` (Forschung/Regulierung: EFSA/WHO/EU-Parlament/idw/The Conversation,
  DACH: heise/Golem/Handelsblatt/WiWo/Tagesschau/TextilWirtschaft, Guardian/NYT-Sektionen,
  Fierce/Dive-Familie). Gepruned: The Spoon (4 % Relevanz-Pass), Confectionery Production,
  The Japan News. Deaktiviert (`active: false`, von Mac-IP 403/Timeout — vom Prod-System ggf.
  reaktivieren): MobiHealthNews, Healthcare IT News, BMJ.
- **Brave-Radar reimplementiert:** `pipeline/radar_discovery.py` (Rewrite), 32 kuratierte Queries
  in `sources.yaml` (`radar:`), Tests gemockt. Braucht `BRAVE_SEARCH_API_KEY`.
- **Poller robuster:** Browser-UA + Accept-Header, 403/406-Fallback auf Reader-UA
  (Just Food/New Scientist erlauben nur Reader-UAs), 5xx-Retry mit Backoff (idw), Timeout 30 s.
  `poll_dryrun.py` respektiert jetzt `active: false`.
- **Messwerkzeug:** `scripts/source_quality_report.py` (Wochenfrequenz aus Feed-Timestamps,
  Stale-Erkennung, Kandidaten-Modus). Verifiziert: Dry-Run pollt alle 189 aktiven Feeds fehlerfrei.

## Status-Update 2026-06-20 — FOOD-Backfill + Alternativ-Datenstrategie

- **FOOD-Backfill durchgeführt (zwei Methoden, alles datiert):**
  - **Brave-Mode** (`scripts/backfill_sources.py --mode brave --months-back 36`): 1.494 publizierte Trends, 2023–2026, gleichmäßig ~50/Monat. Neu im Script: 6-Monats-Date-Window-Slicing (`--months-back`) + `page_age`→`published_date`. Commit `c829737`.
  - **Deep-Mode** (Firecrawl `/map` @100, `--skip-noisy`): 702 publizierte Trends, **2002–2026** (tiefer historischer Schwanz). Lehren: Firecrawl-Scrapes laufen im Free-Tier massiv ins Rate-Limit (echte Kosten nur ~38 Credits, aber ~790 leere Einträge → gelöscht); `/map`-URLs tragen nur ~16 % ein Datum. **Datums-Recovery** baute die Lücke: `scripts/recover_dates.py` (Live-Seite JSON-LD/`article:published_time`, pro-Domain sequenziell, ~74 % Treffer) + `scripts/recover_dates_crossref.py` (DOI→Crossref für bot-geblockte Wiley-Journale, 99 %). Damit 405→1.418 datiert; 1.092 Müll (leer/Nicht-Artikel) gelöscht.
  - **Throughput-Engpass identifiziert:** Stage-1-Dedup von `difflib`→`rapidfuzz` migriert (167× schneller, gemessen). Vollpipeline bei 50k Signalen ≈ 70 h GPU → Strategie nötig (siehe unten).

- **Cross-Vertical-Quellen-Survey (`scripts/probe_source_apis.py`):** 193 Quellen geprobt → **44 mit WordPress-REST-API** (`/wp-json/wp/v2/posts`, gratis, datiert, Volltext — Summe **~3 Mio. Posts** verfügbar; vegconomist 15k, Green Queen 9k, Variety 609k, TechCrunch 261k …), **57 akademisch** (OpenAlex), 89 sonstige. **Firecrawl Deep ist damit für die meisten Quellen obsolet.** Neue Ingester: `scripts/ingest_wordpress.py` (WP-API, datums-/kategorie-gefiltert, gratis), geplant analog für OpenAlex/Sitemaps.
  - **Erkenntnis:** Datenbeschaffung ist gelöst und faktisch unbegrenzt; Engpass = **Selektivität + Durchsatz**. RSS bleibt fürs Laufende (etablierte Quellen erfassen 100 %, bewiesen Green Queen 84/84) — WP/OpenAlex sind **Backfill + Onboarding-Catch-up**, kein Dauerstrom.

- **Offene Entscheidung (Erinnerung 2026-06-20 17:00, `trig_01N4fr3iLUphyiXuvkbRKVmt`):** Option 3 phasiert — Throughput-Offensive zuerst (`--signal-mode` = kein Content-Gen, Artikel lazy; Batch-Klassifizierung via Anthropic Haiku/Sonnet; Embeddings lokal), dann gezielter Gap-Ingest pro Vertical. Kosten ~$1/1k (Haiku) bzw. ~$3/1k (Sonnet) Signale, ganzer Backfill grob ~$50–450. **Signalqualität bleibt:** signal-mode beschneidet nur die Artikel-Generierung, nicht Relevanz/Klassifizierung/Mega-Trend/Datum; Embeddings unverändert (`qwen3-embedding`, Input = `title+excerpt[:500]`, läuft ohnehin vor Content-Gen).

## ⭐ STRATEGISCHE PRIORITÄT (HOCH) — Cluster-/Trajektorien-Foresight als Verkaufsfeature

- [ ] **Foresight-Engine: Reasoning *in* den Signal-Daten, nicht in generierten Artikeln (Strategie-Entscheidung 2026-06-22).** Die **Cluster-/Trajektorien-Analyse auf den Signal-Embeddings ist das Mehrwert-Instrument und zukünftige Verkaufsfeature von Catandary Foresight** — nicht die publizierten Artikel (die sind der kostenlose Lead-Magnet). Das Modell: **Noise aus den Signalen canceln → das Reasoning fürs Trendverständnis passiert in den Daten** (Embedding-Cluster + Zeit-Trajektorien + Cross-Source-Korroboration), nicht durch LLM-Textgenerierung. Belegt am FOOD-Test (`docs/a2_food_evaluation.md`, `scripts/cluster_trajectory_demo.py`): 6.863 Signale → 12 kohärente Trend-Cluster + Tag-Momentum (food safety ↗, precision fermentation ↘) + 5–11-Quellen-Korroboration, **bei $0 Content-Gen**.

  **Ausbau zum Produkt (vom Demo-Skript zur Foresight-Engine):**
  - **Noise-Cancellation (Vorstufe):** Quellen-Qualitäts-Gewichtung (Pass-Rate pro Quelle, `scripts/source_signal_yield.py`), Relevanz-/Dedup-Filter, Signal-Typ-Gewichtung — nur hochwertige Signale ins Clustering. Rauschige Quellen (Variety/HR-Klasse) deckeln/ausschließen.
  - **Clustering at scale:** ANN-Dedup + skalierbares Clustering (`discover_mega_trends.py` v1.1, hnswlib/faiss) über alle Verticals × Mehrjahres-Historie statt O(n)-bruteforce.
  - **Trajektorien/Momentum:** Monats-/Quartals-Buckets, Slope/S-Kurven-Fit, **Lead-Time-Positionierung** (research → patent → funding → product → market) — voll tragfähig erst mit **3–5-Jahres-Backfill** (siehe FOOD-Test war nur 2024 = Intra-Jahr).
  - **Reasoning in den Daten:** Cross-Source-Korroboration, Signal-Typ-Triangulation, PESTEL-Treiber-Analyse, Novelty-/Emergenz-Detektion (neuer Cluster = aufkommender Trend), Cross-Vertical-Trends (Signale mit mehreren `verticals`).
  - **⭐ Zeitfenster-/Trend-Evolution-Analyse (Idee 2026-06-22):** Cluster/Trajektorien **pro Zeitfenster** statt nur statisch, um zu beobachten *wie* sich Trends entwickeln. Zwei Modi: (a) **feste Cluster → Volumen/Fenster** (Momentum, einfach); (b) **Pro-Fenster-Clustering + Cross-Window-Matching** per Centroid-Ähnlichkeit → Cluster-**Lineage**: Emergenz (Cluster in spätem Fenster dicht, in frühem fehlend), Spaltung/Fusion (Alt-Protein → Fermentation/Cultivated/Plant-Based), Decline, **semantische Drift** (Centroid wandert im Embedding-Raum). Produkt-Features: „Landschaft 2021 vs 2024", „verfolge Trend X 2020–2026", „was ist neu in den letzten 6 Monaten", Lead-Time *datengetrieben messen* (research/patent früh → funding/product spät). **Sauber lösen:** Volumen-**Normalisierung** (Share-of-Voice statt Roh-Counts — Quellen kamen über Zeit hinzu) + Fenstergröße (Quartal/Jahr). Technisch nur `--since/--until` in `cluster_trajectory_demo.py` + Matching-Funktion zwischen zwei Läufen. **Voraussetzung: der kontinuierliche Mehrjahres-Backfill** (läuft 2026-06-22).
  - **Verhältnis zu `discover_mega_trends.py` (sie sind sich näher als es scheint und ergänzen sich):** Beide nutzen im Kern **dasselbe** Embedding-Clustering (PCA/KMeans). Unterschied ist *Zuweisung vs. Entdeckung*: Die Pipeline mappt Signale **top-down** auf die eingefrorene `mega_trends.yaml` (~21, grob — ganz FOOD → *ein* Mega-Trend); die Cluster-/Trajektorien-Engine **entdeckt bottom-up** die granularen/emergenten Themen aus den Daten (FOOD → Fermentation/Cultivated/Plant-Based/…). `discover_mega_trends.py` war der frühe Versuch derselben Idee, aber tangled (Clustering- und Momentum-Strategie unverbunden) und nicht lauffähig. **Zielbild:** Die Cluster-Engine **löst die Discovery-Rolle ab** (cleaner) **und speist** die kanonische Taxonomie — Cluster (+ Zeitfenster-Emergenz) *schlagen* neue/gesplittete/fusionierte Mega-Trends *vor* → Mensch kuratiert → eine **lebende** Taxonomie statt einer fixen Liste. Beide Schichten behalten: Cluster = Entdeckungs-Motor, kuratierte Liste = stabile menschenlesbare Labels (Produkt-Konsistenz). Siehe Item „Upgrade `discover_mega_trends.py`".
  - **Produktisierung:** speist **Catandary Foresight** (Paid-Tier) — Cluster-Dashboards, „Wohin geht dieser Trend"-Ansicht, Mega-Trend-Trajektorien, Momentum-Rankings. Frontend-Foresight-Cockpit (`/trends/foresight`) als Ausgangspunkt.
  - **Voraussetzung Datenbasis:** der gescopte Voll-Backfill (A3, lokal-parallel klassifiziert) liefert die Signal-Dichte; Content-Gen bleibt der *optionale, separate* Schritt nur für den öffentlichen Free-Layer.
  - **Abgrenzung:** Free-Layer = Artikel (Lead-Magnet, GPU-Content-Gen für Teilmenge). **Premium-Layer = die Foresight-Engine auf den Signalen** (das hier). Beide aus derselben Signal-Basis.

## Quellen-Architektur — neue Signalquellen (priorisiert 2026-06-20)

- [ ] **⭐ Quellen-Universum / Acquisition-Roadmap nach Lead-Time-Tier (Strategie 2026-06-22).** Wir schöpfen aus einem **winzigen Bruchteil** des legal/API-zugänglichen Materials: aktuell ~2 Kanäle (WP-REST + OpenAlex), konzentriert in den **späten** Tiers (Fachmedien + bisschen Research). Der Foresight-Vorsprung entsteht aber durch die **frühen** Tiers (längste Lead-Time, höchster Vorhersagewert) und harte **Mittel-Tier**-Signale — beides weitgehend ungenutzt. Jeder Kanal ist nur ein modularer Ingester (wie `ingest_wordpress.py`), der `raw_entries` mit eigenem `source_type` schreibt → entkoppelte Acquisition + Signal-Mode verarbeiten alles uniform. **Nur offizielle APIs / legale Primärquellen** (kein Aggregator-Scrape) — EDGAR/openFDA/OpenAlex/PatentsView/arXiv erfüllen das alle.

  **Nach Lead-Time-Tier (priorisiert: frühe Tiers zuerst — das ist das fehlende Wertvolle):**
  - **Frühestens — R&D-Förderung & Preprints (gratis):** **NIH RePORTER**, **NSF Award Search**, **CORDIS** (EU-Horizon-Projekte, Open Data) = wofür Geld bewilligt wird, *vor* der Forschung. **arXiv/bioRxiv/medRxiv/ChemRxiv** = früheste Forschungssignale, Monate vor Publikation (gezielt nach Category/Concept filtern → löst das arXiv-Firehose-Problem von früher).
  - **Patente (gratis, eigenes Item unten):** USPTO PatentsView, EPO OPS, Lens.org.
  - **Früh — Forschung publiziert:** OpenAlex (haben) + **Crossref** (150M Works, Metadaten/Abstracts), **Semantic Scholar API** (200M+ Paper, TLDRs), **PubMed/Europe PMC** (Biomed). Plus OpenAlex-Concept-Expansion (eigenes Item unten).
  - **Mittel — Regulierung & Funding/M&A (gratis, harte Signale):** **SEC EDGAR Full-Text-API** (8-K/S-1-Filings = Funding/M&A/Pivots, *vor* der Presse), **Federal Register**, **openFDA** (Approvals/Recalls), **EUR-Lex** (`trend_signal_type='regulation'` ist schon im Datenmodell). Crunchbase/Dealroom = paid.
  - **Marktnah — Produkte/Adoption:** WP-Fachmedien (haben Slice) + **Product Hunt** (Launches), **GitHub** (Trending/Releases = Tech-Adoption), **Hacker News** (Algolia-API).
  - **Validierung — Nachfrage:** Google Trends (pytrends), Reddit-API.
  - **CMS-Verallgemeinerung (billigster Zuwachs derselben Tier):** WordPress ist nur *ein* CMS — dieselbe API-Logik bei **Ghost** (Content API), **Substack** (JSON-Archiv), **Arc XP** (viele Fachverlage, z. B. FoodNavigator), **Drupal JSON:API**. → `probe_source_apis` um eine „CMS-Probe" erweitern, erschließt Hunderte weitere Sites.

  **Strategischer Kern:** Mehr Fachmedien = mehr vom Gleichen. Die **frühen Tiers (Preprints + Grants + Patente)** + **Mittel-Tier (Filings + Regulierung)** machen die Zeitfenster-/Lead-Time-Analyse *prädiktiv* statt beschreibend — und sind genau das, was die Lead-Time-Positionierung (research→patent→funding→product→market) der Foresight-Engine erst füttert.

- [~] **Patente als Signalquelle anbinden.** Hoher Foresight-Wert: Patente haben die **längste Lead-Time** (Anmeldung Jahre vor Markteintritt → „Future/Science-Tier"). Das Datenmodell ist vorbereitet — `trend_signal_type` enthält bereits `"patent"`. **Ingester gebaut: `scripts/ingest_patents.py` (EPO OPS, Parsing per `--selftest` validiert). Offen: kostenlose OPS-Credentials, dann Voll-Ingest + Signal-Klassifizierung.**
  - **API-Landschafts-Befund (2026-06-24, geprüft):** **USPTO PatentsView ist tot** (→ data.uspto.gov SPA, key-gated; die ODP-„Patent File Wrapper"-API liefert nur US-*Application*-Prosecution-Metadaten, **kein Abstract/CPC** → schlechter Fit). **PPUBS** (ppubs.uspto.gov) ist WAF-geblockt. **BigQuery patents-public-data** bräuchte gcloud (nicht installiert). **bulkdata.uspto.gov** = ECONNREFUSED. **→ EPO OPS** ist die richtige Quelle (weltweit, Titel + **Abstract** + **CPC** + Datum, kostenloser throttled Tier, OAuth). Lens.org (JSON, Bearer-Token) als Alternative — gleiche normalisierte Record-Form, nur `_ops_*`→`_lens_*` tauschen.
  - **Gebaut:** `scripts/ingest_patents.py` — OAuth (`EPO_OPS_KEY`/`EPO_OPS_SECRET` in `.env`), CQL-Suche `cpc=/low "<class>" and pd within "..."` + Range-Pagination + 429/503-Backoff, defensives Parsing der OPS-XML-als-JSON (Titel/Abstract/CPC/Applicant/Datum), **kuratiertes CPC→Vertical-Mapping** (A23 Food, A61 Health, C12 Biotech, G06/H Tech, Y02 Eco, A41/D Fashion …), `record_to_excerpt` (Abstract+Applicant+CPC), `insert_raw_entry` (URL-Dedup), `--dry-run`, `--selftest` (validiert ohne Creds).
  - **Nächster Schritt (braucht 1 manuellen Schritt):** kostenlose OPS-App registrieren (developers.epo.org → Consumer Key+Secret) → in `.env` → `python scripts/ingest_patents.py --vertical FOOD --after 2020-01-01 --before 2026-07-01` pro Vertical → dann `signal_batch`/Pipeline klassifiziert sie in den Signal-Space (`trend_signal_type='patent'`). Analog zum OpenAlex-Key-Flow.
  - **Caveats:** dichte Patent-Sprache → Relevanz/Klassifizierung gut prompten; Volumen riesig → strikt klassen-/datumsgefiltert ziehen (max-pages cappt). OPS-Free-Tier ist throttled (4 GB/Woche) → über Tage verteilen.

- [ ] **⭐ Patent-Daten-Features-Checkliste (aus `patent.dev` / Wolfgang Stark gelernt, 2026-06-24).** Was wir noch *nicht* haben, nach Wert sortiert. Erledigt = ✅, offen = ☐.
  - ✅ **Citation-Graph** (`patent_links`: cites/parent/child + category) — `67c9e4d`. Backfill verkettet nach Klassifizierung.
  - ✅ **Kind-Code-Parsing** (App/Grant via `kind_code`, `is_application`) — `c9483df`. App (A*) = frühestes Lead-Time-Signal.
  - ✅ **Throttle „black"** (4. OPS-Stufe, harte Sperre) — `c9483df`.
  - ✅ **`scripts/tir_metrics.py`** — Technology Improvement Rate: Cycle Time + Immediate Importance (r≈0,76) pro **Embedding-Cluster**, SPNP-Centrality offen. Siehe Memory `tir-patent-metrics-methodology`. `5bd0b33`.
  - ✅ **`scripts/tir_graph.py` (2026-06-25)** — **GPU-freie** TIR auf dem Graph-Layer: Domains *top-down per CPC-Subklasse* statt Embedding-Cluster → Citation-Metriken über **alle** ingesteten Patente (embedded oder nicht), read-only, keine GPU/keine Writes. `--rank cycle|imm|recency`. Belegt empirisch die Lazy-These (s. u.).
  - ☐ **Legal-Status-Ingest (INPADOC Legal Events)** — grant/in-force/**lapsed/abandoned**. *Neues* Signal neben Citations: Aufgabe einer Technologie = Negativsignal, Reife-Marker. Quelle: **BDDS-Produkt 5/11** (haben Zugang!) oder OPS `GetLegal`. Eigener Ingester → `patent_legal_events`-Tabelle.
  - ☐ **INPADOC-Family-Dedup** — autoritative Familien-Gruppierung (besser als Google `parent`/`child`). Für korrekte Trend-*Counts* (1× pro Erfindung, nicht pro Land). OPS `GetFamily` / BDDS-INPADOC.
  - ☐ **Earliest-Publication-Dedup im Analyse-Layer** — A+B desselben `pub_number`-Stamms auf die A-Publikation kollabieren (Lead-Time-Datum); cross-country via INPADOC-Family. `kind_code` ist schon da.
  - ✅ **BDDS-DOCDB-XML-Ingester** (`--source epo-bdds`) — Produkt 3 (Front) validiert (`4279724`), `--product 14` (Welt-Back-File) parametrisiert. DOCDB-XML → `raw_entries` + `patent_links` (Citations+Family). Weltweiter Bulk ohne OPS-Rate-Limits. **⭐ Entscheidung 2026-06-25: legitime *Produktionsquelle*, ersetzt die HF-Google-Patents-Stichprobe** (HF = nur MVP/Bootstrap: 340k Privat-Upload, undurchsichtiges Sampling CN 46 %, EN-Titel-Filter, 2025 abgeschnitten). Für unverzerrte Foresight → BDDS-DOCDB (EPO offiziell, ~150M, kein Sampling-Bias).
  - ✅ **Strukturiertes CPC (`patent_cpc`-Tabelle, vorbereitet 2026-06-25)** — eine Zeile je (Patent, CPC-Symbol) mit denormalisierter `subclass` + `inventive`-Flag (DOCDB `classification-value` I/A) → CPC-Scoping/Domain-Rollup als indizierter GROUP BY statt Excerpt-Text-Parsing. Code + Insert-Wiring in `ingest_bdds` fertig & getestet (kein DB-Write); **Migration + `backfill_patent_cpc_from_excerpt()` zünden nach dem laufenden HEALTH-Lauf** (Lock-Vermeidung). Future-Ingests schreiben die volle CPC-Menge strukturiert.
  - ☐ **OPS-Citations-Constituent** — OPS `…/published-data/.../citations` für Citation-Anreicherung OPS-gezogener Patente (HF hat sie schon).
  - ☐ **OPS-Full-Text** (`GetClaims`/`GetDescription`) + EP-Full-Text (BDDS-Produkt 32) — Volltext für tiefere Analyse, wo verfügbar.
  - ☐ **CQL-Verfeinerungen** im OPS-Provider: `pd>=2020` (Vergleichsoperatoren), `ic=` (IPC alternativ zu CPC), Proximity (`prox/distance`).
  - ☐ **DPMA Connect Plus** (DE-Patentamt, `patent.dev/dpma-connect-plus`) — falls DE-Markt-Fokus relevant wird.

- [~] **⭐ DOCDB-Tiefen-Pull- & Lazy-Embedding-Architektur (entschieden 2026-06-25).** Trennung in zwei Layer, weil empirisch belegt (s. „Beweis" unten), dass die starken TIR-Metriken den breiten Korpus brauchen, Embeddings aber *nicht* eager für alle:
  - **EAGER / GPU-frei / breit — der Graph-Layer:** DOCDB → `raw_entries` (Titel/Abstract, *alle Sprachen* — keine Übersetzung nötig) + `patent_links` (Citations/Family) + `patent_cpc` (strukturiert) + `vertical` (**CPC-deterministisch, kein LLM**). Darauf laufen Cycle Time, Forward-Hubs, Family-Dedup, CPC-Domain-Rollup (`tir_graph.py`) **sofort, ohne GPU**.
  - **LAZY / GPU / on-demand — der Embedding-Layer:** Embeddings nur für Knoten, die eine Query/ein Cluster wirklich berührt. `ensure_embeddings(ids, cap, timeout)` (☐ zu bauen): Cache-Check (`trends.embedding`) → fehlende embedden → zurückschreiben. Absicherung: **(1)** Knoten-Cap pro Query (>N → Sample/async), **(2)** Wall-Clock-Timeout, **(3)** *Prefilter zuerst* (CPC+Zitate+Datum als SQL schrumpft das Set, bevor embedded wird → nie unbegrenzt), **(4)** GPU-idle-Gate (teilt :8090 mit der Pipeline), **(5)** Persistenz (Kosten 1×/Knoten).
  - **Pull-Strategie (auf „lieber mehr Daten" abgestimmt):** **1-Hop-rückwärts** (die zitierten Patente nachziehen) liefert nur Cycle Time + Cross-Domain-Klassen, **nicht** die Vorwärts-Metriken (Immediate Importance, SPNP) — die entstehen erst, wenn *beide* Zitations-Endpunkte im Korpus sind. → richtiger Zug ist der **CPC-gescopte Back-File (Produkt 14)** für die Kern-Verticals: ganze Klassen drin ⇒ Zitate in beide Richtungen dicht. **Offen: Back-File-Scope-Entscheidung** (welche Verticals, wie viel; sprengt SQLite → triggert die Postgres+pgvector-Migration).
  - **Beweis (2026-06-25, `tir_graph.py` über 74.534 Patente / 411.884 Zitate, GPU-frei):** ø **11,4 Zitate/Patent**, aber zitierte Patente nur **0,1 % im Korpus** → Vorwärtsrichtung leer ⇒ Immediate Importance ~0 (Hubs mit 1 Forward-Zitat). **Cycle Time funktioniert** (Coverage bis 15k): Ranking aufsteigend liefert genau die schnelllebigen Frontier-Domains — **G06N (AI, 5 J), B60W (ADAS, 5 J), G05D (autonom, 5 J), G06T/G06V (CV, 6 J), Y02E/Y02T (Clean Energy, 6 J), H04W (Wireless, 6 J)**. Der billige Graph-Layer allein gibt also schon verwertbares Foresight-Signal; der Back-File schaltet die r≈0,76- und SPNP-Metriken frei.

- [ ] **⭐ OpenAlex Graph-Layer — eigenständiges „Science"-Signal (entschieden 2026-06-27).** Zwei eigenständige, parallele Frühsignale in der Foresight-Suite: **Patente = „Technology"**, **OpenAlex = „Science"** (research→preprint, die *früheste* Lead-Time-Stufe). Wir ingesten OpenAlex schon als **Text-Layer** (~58 Research-Quellen → Titel/Abstract → Signal), aber **nicht** den Graph-Layer. Genau der macht es zum vollwertigen Foresight-Substrat — analog zur Patent-Architektur:
  - **Graph-Layer (eager, GPU-frei):** Work → `raw_entries` (Titel + rekonstruierter Abstract aus `abstract_inverted_index`) + `openalex_citations` (`referenced_works` → Edges, wie `patent_links`) + `openalex_topics` (Topic-Hierarchie Domain→Field→Subfield, wie `patent_cpc`) + `type` (preprint = früheste Stufe, wie kind_code) + `cited_by_count`/`counts_by_year` (native Forward-Velocity). Vertical via **Topic→Vertical-Mapping** (deterministisch, wie `vertical_for_cpc`).
  - **⭐ Entscheidender Vorteil vs. Patente:** der Zitationsgraph ist **dicht & selbst-enthalten** (`referenced_works` = OpenAlex-IDs, OpenAlex deckt ~die ganze Wissenschaft ab) → genau die Vorwärts-Metriken, die an Patenten scheiterten (0,1 % im Korpus), **funktionieren hier sofort**. `cited_by_count`/`counts_by_year` geben Forward-Velocity nativ (keine Invertierung, kein Voll-Korpus nötig).
  - **Quantitative Indikatoren — übernehmbar, aber auf „Science" abzustimmen:** Cycle Time / Immediate Importance / Acceleration aus `tir_graph` wiederverwenden, ABER **feld-normieren** (Zitationsraten variieren ~10× zwischen Feldern → `cited_by_percentile_year` bzw. Normalisierung *innerhalb* Topic-Subfield), **Zitationsfenster** feldabhängig (~2 J statt 3), **Zitations-Lag** beachten (frische Works zitatarm → Topic-**Volumen/-Wachstum** ist das aktuelle Frühsignal, Zitate bestätigen ältere), **Co-Citation/Bibliographic-Coupling-Cluster** = Research Fronts (Science-spezifische Methode), `is_retracted` = Negativsignal (analog patent „lapsed").
  - **Cross-Tier-Fusion:** Science (OpenAlex) *vor* Technology (Patente) *vor* Funding/Produkt → die research→patent→funding→product-Kette wird **messbar**, sobald beide über vergleichbare Zeitfenster im Signal-Space liegen (stabile-Kohorte-Prinzip).
  - **Akquise-Plan: `docs/openalex_acquisition.md`** (analog zum BDDS-Backfill, aber via REST-API statt Bulk-Snapshot).

- [ ] **⭐⭐ Tiefen-Backfill: Embedding-Distillation-Klassifikation + Lazy-Content (Architektur 2026-06-28).** Das *Processing*-Modell für die Massen-Pulls (Patent-Back-File + OpenAlex pre-2020, Millionen Items) — Klammer über DOCDB-Back-File + OpenAlex-Graph-Layer + Lazy-Embedding + Postgres. **Voll-Plan: `docs/deep_backfill_architecture.md`.**
  - **Problem:** Das 8B ist output-generierungs-gebunden (gemessen ~198 req/min Classification, der echte Engpass — der Merge-/Parallel-Hebel brachte nur ~1,2×). Bei Millionen Items sind 3 LLM-Calls/Item unbezahlbar.
  - **Lösung — LLM raus aus dem Ingest-Pfad:** *eager* = Graph-Layer (CPC/Topics/Citations, GPU-frei) + **Embeddings** (einziger GPU-Schritt, gebatcht) + **billige Klassifikator-Heads**; *lazy* = Extraction + Content-Gen on-query; *LLM* nur lazy + periodische Discovery.
  - **Distillation:** den LLM-Klassifikator in einen **Embedding-Klassifikator** destillieren, trainiert auf den **vorhandenen LLM-Labels** (~227k Signale + filtered_out; für Patente die 74k LLM-klassifizierten). Heads auf dem 4096-dim Vektor: Relevanz (binär, kalibriert), Mega-Trend (21-Klassen), PESTEL (Multi-Label). **Vertical bei Patent/OpenAlex deterministisch (CPC/Topic) — gratis**; Relevanz bei Patent/OpenAlex = das CPC/Topic-**Scoping** selbst.
  - **Was NICHT geht:** Extraktion aus Embeddings (verlustbehaftet, konkreter Text nicht rekonstruierbar) → bleibt **lazy** (spaCy-NER/LLM auf Text, nur für angefragte Signale). Content-Gen lazy per Query über `ensure_embeddings` + den schon gefixten de-cliché-Pfad.
  - **⭐ Discovery-Loop (Pflicht):** Klassifikator ist auf die bekannte Taxonomie *bounded* → kann **keine neuen Mega-Trends entdecken**. Gegenmittel: periodischer **LLM-Pass auf Cluster-Zentren** → neue Mega-Trend-Kandidaten → `mega_trends.yaml` erweitern → Klassifikator nachtrainieren. So bleibt Novelty (Kernwert der Engine) erhalten, ohne pro Item ein LLM.
  - **Wirkung:** Ingest der Welt-Korpora ohne LLM-Generierung → Stunden statt Wochen; LLM nur noch lazy-on-query. Validierung: Agreement Klassifikator vs LLM auf Holdout (Vertical ≥~90 %, Mega-Trend top-1/3, Relevanz P/R) + A/B-Foresight (Cluster/Trajektorien embedding-first vs LLM-3-stage). Prototyp ist sofort möglich (gelabelte Embeddings liegen vor), CPU-only.

- [ ] **Weitere keyless Leading Indicators (für den Lead-Time-Layer, ohne Credential-Hürde):** arXiv (`export.arxiv.org/api/query`), bioRxiv/medRxiv, **NIH RePORTER** (`api.reporter.nih.gov`), **CORDIS** (EU-Horizon-Grants, Open Data) — alle keyless, früheste Tiers (Grants/Preprints *vor* der Forschung). Gleiches Muster wie `ingest_patents.py`: normalisierter Record → `insert_raw_entry` → Signal-Pipeline. Ergänzt die Patente um die noch früheren Lead-Indikatoren.

- [ ] **OpenAlex über die 57 kuratierten Journale hinaus erweitern (Concept-/Topic-basiert).** Die 57 sind nur unsere bestehende Quellenliste — OpenAlex indexiert **~250 Mio. Werke über ~250k Quellen** und erlaubt Abfrage **nach Concept/Topic** (nicht nur Journal), je mit Datum + Abstract. Gratis.
  - **Hebel:** statt journalweise → `filter=concepts.id:<concept>` (oder `topics`) + `from_publication_date` ziehen, quer über alle Journale (z. B. „food science", „machine learning", „renewable energy").
  - **Qualitäts-/Volumen-Tradeoff:** Concept-Expansion bringt Millionen Werke **plus Rauschen** (Predatory Journals, irrelevante Subfelder). Mit OpenAlex-Qualitätssignalen gaten: `cited_by_count`, Source-Impact/`is_in_doaj`, `is_oa`, Mindest-Concept-Score. Pro Vertical 1–3 Concepts kuratieren, datums-/qualitätsgefiltert ziehen, dann durch denselben Relevanzfilter.
  - Beide Items in der 17:00-Entscheidung (Option 3) als zusätzliche `source_type`-Kandidaten mitdenken.

- [ ] **OpenAlex-Ingest fixen: Namens-Auflösung + Router-Fehlrouting (Befund Welle-0-Backfill 2026-06-21).** Beim All-Vertical-Backfill lieferten **nur 18 von 57 ACADEMIC-Quellen** Works (8.363 statt projizierter 14.302). Zwei Ursachen:
  - **(Bug, echter Verlust) `resolve_source_id` scheitert per Anzeigename an Top-Journalen:** PNAS, Nature (main), Science Magazine, Quanta, Nature Energy/Materials/Human Behaviour/Reviews Materials, Psychological Science, Trends in Biotechnology → **0 Works**, obwohl sie tausende 2024-Arbeiten haben. Die `?search=<name>`-Auflösung matcht die falsche/keine OpenAlex-Source. **Fix:** per **ISSN** auflösen (in `sources.yaml` hinterlegen) statt Namenssuche, bzw. Kandidaten nach `works_count`/Typ disambiguieren. Hoher Hebel — das sind genau die hochwertigen Quellen (Top-Pass-Rate in der Qualitätsanalyse).
  - **(Router-Fehlklassifizierung, korrekt leer) Nicht-Journale als ACADEMIC geroutet:** The Conversation, WHO News, FAO, EU Parliament/idw/Fraunhofer Presse, EFSA News, NYT/MIT/Phys.org/ScienceDaily/Medical Xpress/Tech Xplore, HBR, Project Syndicate → OpenAlex hat sie nicht → 0. **Fix:** in `probe_source_apis.classify` Presse-/News-Outlets nicht nach ACADEMIC routen (→ WP/Sitemap). Kein Datenverlust, aber sauberere Kategorisierung.
  - Geglückt (Referenz): The Lancet 1.807, NEJM 1.067, Frontiers Sustainable Food 924, Nature Medicine 747, EFSA Journal 495, Nature Biotech 484, Trends in Food Sci 445, Nature Climate 325.
  - **GELÖST 2026-06-21:** Hauptursache war nicht Namens-Auflösung sondern **OpenAlex' Freemium-Budget** ($0,10/Tag ohne Key → 429 = Budget erschöpft, nicht Reputation). Mit kostenlosem `OPENALEX_API_KEY` ($1/Tag), `per_page=100`-Fix und works_count-Disambiguierung lieferte der Re-Ingest **+10.298** Works (Nature 4.420, PNAS 3.962 …) für ~$0,08. Verbleibende echte Nuller per `openalex_id`-Override in `sources.yaml` gefixt: Science Magazine News→S3880285 (+2.047), Matter (Cell Press)→S4210178557 (+377). **Rest korrekt leer** (kein 2024-OpenAlex-Index): Harvard Business Review, Science News, The Conversation — optional aus ACADEMIC-Routing nehmen (kein Datenverlust). Offen bleibt nur die Router-Klassifizierung (News→WP/Sitemap statt ACADEMIC) als Aufräumarbeit.

- [ ] **The Conversation per Sitemap ingesten (Befund 2026-06-21).** Bei der Prüfung der OpenAlex-Nuller: The Conversation ist **nicht** über WP (`/wp-json` 404, eigene Plattform) oder OpenAlex (kaum indexiert) erreichbar, **aber voll über Sitemap** — `https://theconversation.com/sitemap.xml` ist ein Index mit **225 Sub-Sitemaps**, darunter regionale **`{region}/sitemap_archive_2024.xml`** (au/africa/br/uk/us …) mit datierten Artikel-URLs. Inhaltlich wertvoll (Experten-Kommentar quer über alle Themen, **CC-lizenziert** = republikationsfreundlich). Umsetzung über `scripts/ingest_sitemap.py`:
  - **Caveats:** langsamer Kanal (og:title/og:description-Fetch pro Artikel, ~1 s/Stück + Rate-Limit) → bei mehreren Regionen × tausenden Artikeln zeitintensiv; `max_fetch`-Default (300) anheben. `ingest_sitemap.find_source_entry` findet die Quelle evtl. nicht (gleiches Problem wie `ingest_wordpress` bei Science News) → ggf. `--base-url`/`ingest_via: OTHER` setzen. `discover()` ist auf 60 besuchte Sitemaps gedeckelt — für die 225er-Indexstruktur prüfen, ob das reicht (gezielt nur die `sitemap_archive_2024.xml` pro gewünschter Region ziehen statt Vollcrawl).
  - **Hinweis HBR (kein Backlog nötig):** Harvard Business Review ist ein echter Dead-End — kein WP (404), OpenAlex 2024=0, kein Sitemap/robots-Sitemap, kein RSS an Standard-Pfaden. Für den Backfill nicht erreichbar; nicht erneut versuchen.

## Pipeline-Optimierung

- [ ] **Strategie für parallelisiertes Content-Gen entwickeln (2026-06-23).** Klassifizierung (Stages 2–4) und Embeddings sind jetzt parallelisierbar (concurrent llama.cpp `--parallel`), aber **Content-Gen (Stage 6) bleibt der harte Engpass**: die 35B (Qwen3.6-35B-A3B) frisst ~22 GB → nur 2–3 parallele Slots passen auf der 3090, kaum Skalierung. Zu entwickeln: wie Content-Gen *trotzdem* parallelisiert/beschleunigt werden kann. Optionen zum Durchdenken: (a) **kleineres/quantisierteres Content-Modell** mit mehr Slots (Qualität testen vs. 35B); (b) **MoE-Routing** — ein 30B-A3B für classify *und* gen, dafür VRAM-bound; (c) **selektives Content-Gen** — nur Top-`trend_score`-Teilmenge bekommt Artikel (passt zur Signal-Mode-Logik: viele Signale, wenige Artikel), Rest bleibt reines Signal; (d) **vLLM/SGLang** mit PagedAttention für höhere Content-Gen-Concurrency; (e) **2-Karten-Setup** (35B auf der 24-GB-Karte, parallel klassifizieren auf der 16-GB-Karte). Kontext: Content-Gen war ~37 % der RSS-Batch-Zeit; Klassifizierung+Embeddings (~62 %) sind jetzt parallelisiert (`CLASSIFY_WORKERS`).

- [ ] **Parallelisierte lokale Klassifizierung (Stages 2–4) bauen — Build-Plan: [`docs/local_parallel_classification_plan.md`](docs/local_parallel_classification_plan.md) (2026-06-22).** Der Anthropic-Batch-Pfad scheiterte an Latenz (Extraktions-Batch 0/6.998 nach ~12 h), nicht an Korrektheit. Engpass war der unparallelisierte Serving-Stack (Ollama 1 Slot = 49 req/min), nicht die GPU. Lösung: vLLM/SGLang mit **Continuous Batching + Prefix-Cache + Grammar-JSON** + kleinem Dense (Qwen3-8B) → projiziert ~500–1.000 req/min, $0, vorhersehbar. Phasen P1–P5 (Setup → 1 Stage → 3-Stage-Runner `classify_local.py` → Benchmark → A3-Entscheidung) im Plan. Reuse: Prompts/Schemas, numpy-Dedup + Insert aus `signal_batch.py`. Siehe Memory `batch-api-latency-vs-local`.

- [ ] **Content-Prompt-Optimierung zur Artikelqualität (#3, inkl. zusätzlicher Output-Felder) — Stand 2026-06-21.** Ziel: Qualität der erzeugten Artikel heben, getestet per A/B gegen eine Stichprobe **bereits erzeugter** Artikel. Off-GPU planbar bis auf die Test-Generierung (lokal qwen, braucht freies VRAM-Fenster).

  **Diagnose (gemessen):** Der Artikel entsteht in **einem** LLM-Call (Stage 6) aus `Title + Excerpt[:1000] + Extraktion (brand/product/key_claims) + Klassifizierung (verticals/PESTEL/signal_type/mega_trend)`, gesteuert durch `CONTENT_EN_SYSTEM` (`llm_processor.py:186`, nur ~10 Zeilen) und Schema `GeneratedContent` (`models.py:93`). Das Embedding fließt **nicht** ein (nur Dedup/Foresight). Zwei strukturelle Schwächen prägen die Qualität: (1) **Input-Hunger** — `raw_content` ist bei allen 62.062 raw_entries leer, genutzt wird nur der RSS-Teaser `excerpt` (Ø **445 Zeichen** ≈ 70 Wörter) → das Modell bläst 70 Wörter auf 150–250 auf, was Floskeln/Erfindung begünstigt (das ist Item #1, eigener Eintrag offen). (2) **Kein Body-Qualitätsgate** — Auto-Publish entscheidet nur über Klassifizierungs-`confidence >= 0.85` (`auto_publisher.py:39`), der einzige Body-Check ist die Wortzahl im llamacpp-Pfad (Item #2).

  **Scope dieses Items (#3):**
  - **`CONTENT_EN_SYSTEM` überarbeiten:** Signal-Type-spezifisches Framing (ein `regulation`-Artikel ≠ `funding`/`research`/`product_launch` → Prompt-Block nach `classification.trend_signal_type` verzweigen), **Anti-Floskel-Blocklist** („game-changer", „revolutionize", „in today's fast-paced world"), **erzwungene Konkretheit** („cite ≥1 specific figure/name/date from the source; do not generalize"), optional ein **Few-Shot-Exemplar** eines exzellenten Artikels.
  - **Zusätzliche Output-Felder in `GeneratedContent`:** z. B. `key_implication` und `what_to_watch` → zwingen das Modell zur analytischen Aussage, statt den `body` mit Fülltext zu strecken. **Persistenz separat:** für den Test in einen JSON-Report schreiben (keine DB-Migration); erst bei Adoption neue Spalten in `trends` + Migration. Frontend-Anbindung später.
  - **Max-Wort-Guard** spiegelbildlich zum bestehenden Min-Wort-Guard (`STAGE5_MIN_BODY_WORDS`) ergänzen, damit reichere Prompts die Länge nicht über 250 Wörter driften lassen.

  **Testmethodik (A/B gegen Bestand):** neues `scripts/ab_test_prompt.py` — stratifizierte Stichprobe (~30–50) **bestehender publizierter** Trends ziehen, deren `raw_entry` (Title+Excerpt+`extraction_json`+`classification_json`) durch die **neue** Prompt-/Schema-Variante **lokal auf qwen** (gleiches Produktionsmodell, faithful) regenerieren, **nicht** in die `trends`-Tabelle schreiben (non-destruktiv, Report-only). Bewertung per **Haiku-Judge** (off-GPU, ~Cent) auf fixer Rubrik: Quellentreue / analytische Tiefe / Originalität ggü. Excerpt / Floskel-Freiheit (0–5), alt vs. neu paarweise. Output: Score-Verteilung + Sample zum Eyeballing. Deckt sich mit dem Eval-Harness-Gedanken (#6).

  **Laufzeit-/Längen-Effekt (analysiert):** Nur Stage 6 betroffen. Prompt-only ≈ **+0,3 s/Artikel (+7 %)** (Prefill von ~+450 Input-Tokens); **mit** neuen Output-Feldern ≈ **+0,8 s/Artikel (+19 %)** durch zusätzliche Output-Tokens → bei 600er-Batch (~30 min Stage 6) **+~2 bis +6 min**, gegen den ~3-h-Gesamtzyklus vernachlässigbar (+1–2 %). Keine zusätzlichen Calls/Retries (Regenerate-Loop gehört zu #2). **Artikellänge:** Ziel-Band 150–250 W unverändert, Wirkung ist Dichte statt Länge; neue Felder verlängern den Gesamt-Output, **nicht** den `body`; Max-Guard hält die Länge stabil. Eval-Harness selbst: **0** Pipeline-Laufzeit (entkoppeltes Offline-Skript), eigene Laufzeit ~5–8 min lokal / ~1–2 min via Haiku.

  **Verwandte Hebel (aus derselben Analyse, eigene Items/Folge):** **#1 Volltext beschaffen** (Article-Fetch → `raw_content`, der eigentliche Ceiling-Raiser; ToS-sorgfältig, per Quelle opt-in) — siehe „Historisches Backfill via Website-Scraping" oben für die Fetch-Vorlage. **#2 Qualitäts-Gate** (LLM-Critic Stage 6.5 + `confidence`-UND-`quality_score`-Publish). **#4 reichere Extraktion** (`key_figures`/`quotes`/`dates`/`geography` in `ExtractionResult`). **#5 bessere Klassifizierung im RSS-Pfad** (Haiku schlug qwen3:8b in Phase 5 → besseres Vertical/Mega → besserer Outlook). **#6 Eval-Harness** als Meta-Stellschraube (Messbarkeit aller Änderungen).

- [ ] **Upgrade `scripts/discover_mega_trends.py` v1.0 → v1.1.** Review-Stand 2026-06-13 (Ist-Version = Commit `3be3e8b`): inhaltlich solide (PCA→KMeans mit Silhouette-k-Wahl, temporale Tag-Beschleunigung, Momentum-Update), Datengrundlage top (34.142 published Trends, alle embedded, einheitlich 4096-dim, 98% mit `published_date`). **Aktuell aber nicht lauffähig** + ein paar Sauberkeitslücken. (numpy + scikit-learn sind inzwischen installiert, 2026-06-22.) **Querverweis:** Dieses Script und die Cluster-/Trajektorien-Foresight-Engine (Item oben) nutzen *dasselbe* Embedding-Clustering und ergänzen sich — die Cluster-Engine ist die saubere, bottom-up Discovery-Realisierung und sollte diese Discovery-Rolle ablösen + die kanonische Taxonomie speisen (lebende statt fixe Liste). v1.1 ggf. als Teil davon neu denken. v1.1-Scope:
  - **[Blocker] Deps deklarieren/installieren:** `numpy` + `scikit-learn` fehlen in `requirements.txt` **und** im `.venv` → Script crasht sofort beim Import (`ModuleNotFoundError: numpy`). In `requirements.txt` aufnehmen, im `.venv` installieren (scikit-learn zieht scipy, ~100 MB).
  - **Docstring↔Code-Mismatch:** Docstring (Z. 5) sagt „UMAP + HDBSCAN", Code nutzt **PCA + KMeans**. Docstring an die reale Implementierung anpassen (oder, falls UMAP/HDBSCAN gewünscht, als separate optionale Strategie nachrüsten).
  - **`run_momentum_update(--write)` kommentarschonend/abgesichert machen:** schreibt `mega_trends.yaml` per `yaml.dump` neu und stellt nur einen hartcodierten Header wieder her → sonstige Kommentare/Struktur gehen verloren. Außerdem nennt der Header `cluster_strength` als „data-driven", obwohl es **nie berechnet** wird (Clustering-Strategy 1 und Momentum-Strategy 3 sind unverbunden). Optionen: ruamel.yaml für Kommentar-Erhalt, oder nur die geänderten Felder in-place patchen; `cluster_strength` entweder real aus dem Clustering ableiten oder aus dem Header entfernen.
  - **Robustheit:** Leere-DB-Guard in `load_trends()` (Z. 84 `len(trends[0]["embedding"])` → `IndexError` bei 0 Zeilen). `random_state` an `silhouette_score(sample_size=…)` durchreichen, damit die `best_k`-Wahl reproduzierbar ist (aktuell schwankt sie trotz `KMeans(random_state=42)`).
  - **Methodik (optional, siehe auch Structural-Score-Item unten):** early/late-Split am globalen Median + `min_tag_count=3` sind anfällig für Batch-Timing-Verzerrung/Rauschen; ggf. Signal-Share statt -Count und höhere Mindestschwellen. Performance-Hinweis: KMeans-Sweep k=10…35 × `n_init=10` auf 34k×50 ≈ 260 Fits (mehrere Min, ~1,5 GB RAM-Peak) — für ein Discovery-Tool ok, aber kein Schnelllauf.

- [ ] **Rauschige neue Feeds beobachten — Qualitätscheck am 2026-06-20.** Im ersten großen Lauf der `product/trend-radar`-Quellen (Lauf `20260612-1840`, 2.391 Einträge verarbeitet) lagen mehrere **neue** Feeds deutlich unter der erwarteten Pass-Rate (research ~80% / trade ~57%). Kandidaten mit ≥20 verarbeiteten Einträgen und niedrigster Pass-Rate (= Anteil, der den Relevanz-Filter passiert):
  - GlobeNewswire (press_wire) **20%** · Guardian Food **20%** · Guardian Culture **27%** · Architectural Record **30%** · TextilWirtschaft **33%** · EU Parliament Press **35%** · NYT Science **46%** · OMR **47%** · EFSA News **47%**
  - Auffällig: Research lag im Lauf gesamt bei **64,6%** (unter den erwarteten ~80%), weil die neuen Regulierungs-/Research-Feeds (EU Parliament, EFSA, NYT Science, The Conversation/MIT News je 58%) den Schnitt drücken; Trade lag mit **71,7%** über Erwartung.
  - **Aktion am/ab 2026-06-20** (≥1 Woche Daten): Pass-Rate dieser Feeds erneut messen (`scripts/source_quality_report.py` bzw. `raw_entries`-Join wie im Post-Run-Report 2026-06-13). Wenn ein Feed dauerhaft <35% Pass-Rate bei relevantem Volumen liefert → Relevanz-Schwelle pro Quelle erwägen, Feed auf eine spezifischere Sektions-URL umstellen, oder bei strukturellem Off-Topic (z. B. Guardian-Sektionen, GlobeNewswire-PR-Flut) `active: false` setzen. Guardian Food/Culture und GlobeNewswire sind die heißesten Kandidaten.

- [ ] **Historisches Backfill via Website-Scraping (Firecrawl / WebSearch).** Neue RSS-Feeds liefern nur die letzten 10–20 Artikel. Die 62 Feeds aus dem `product/trend-radar`-Merge (Commit `9cacaa3`, 2026-06-12) haben daher eine Historielücke bis zu ihrem Einbindungsdatum — besonders relevant für Regulation/Research-Quellen (EFSA, EU-Parlament, idw), DACH-Presse und Guardian-Sektionen. Ziel: pro Quell-Website die letzten 90–180 Tage Archiv-Seiten crawlen und als `raw_entries` in die Pipeline einspeisen.

  **Implementierungsoptionen:**
  - **Firecrawl** (`firecrawl-py`): crawlt Archiv-Seitenbaum, rendert JS, gibt saubere Markdown-Excerpts zurück. Direkt als `source_type='backfill'` in `raw_entries` einspeisen. Kein API-Key-freier Pfad (SaaS oder Self-Hosted).
  - **WebSearch (Brave Search API)**: `site:foodnavigator.com after:2026-01-01` pro Feed — liefert Titel + URL + Snippet, kein Volltext. Geringer Aufwand, aber Snippet-Qualität für Stage-2-Extraktion oft zu dünn.
  - **Hybrid:** Brave Search liefert URLs, Firecrawl holt den Content → teurer, aber beste Qualität.

  **Konkrete Architektur:**
  - `scripts/backfill_sources.py --source-name "EFSA News" --days-back 90` — nimmt den Feed-Namen aus `sources.yaml`, leitet die Homepage-URL ab, crawlt Archiv-Seiten, dedupliciert via `raw_entries.url UNIQUE`, schreibt neue Einträge mit `processed=0`.
  - Normaler LLM-Processor verarbeitet den Backfill dann im nächsten Batch (kein eigener Pfad nötig).
  - Scope initial: nur die 9 beobachteten Noisy-Feeds + die wichtigsten Regulation-Quellen, **nicht alle 189 Feeds** (zu viel Volume, zu hohes Rate-Limit-Risiko).

  **Risiken/Offene Fragen:**
  - ToS-Grauzone: Das Projekt nutzt ausschließlich Primärquellen via RSS. Direktes Crawlen der Website der gleichen Quelle ist eine Graubereichserweiterung davon — keine Aggregatoren, keine fremden Inhalte, aber ggf. außerhalb der impliziten RSS-Nutzungsvereinbarung. Vor dem Produktiv-Einsatz für jede geplante Quelle `robots.txt` prüfen und ggf. Crawl-Delay 5–10s einhalten.
  - Volume-Schock: 180 Tage × 10 Artikel/Tag × 9 Feeds = ~16.000 neue Raw-Entries → ~8 Stunden LLM-Pipeline. Empfehlung: erst Noisy-Feeds-Qualitäts-Check (2026-06-20) abwarten, dann nur Feeds einbeziehen die ≥35% Pass-Rate halten.
  - Dedup: Title-Dedup (`is_title_duplicate`) wird bei großem Backfill teuer (→ rapidfuzz-Migration abschließen vorher).

  **Voraussetzungen:** rapidfuzz-Migration (Stage-1 Dedup) abgeschlossen, Qualitätscheck 2026-06-20 ausgewertet.

- [ ] **Stage-1 Title-Dedup beschleunigen (`difflib` → `rapidfuzz`).** `is_title_duplicate()` in `pipeline/llm_processor.py` vergleicht jeden Batch-Eintrag per pure-Python `difflib.SequenceMatcher` gegen alle Titel der letzten 30 Tage. Bei einem 600er-Batch gegen ~12.500 bestehende Titel sind das bis zu ~7,5 Mio. `.ratio()`-Aufrufe single-threaded → **~10 Min pro Batch**, ohne Zwischen-Logging (beobachtet im Lauf 2026-06-12-1840, sah anfangs wie ein Hänger aus, war aber CPU-gebundener Dedup). Beim Backlog-Drain (mehrere 600er-Batches) summiert sich das auf Stunden reiner Dedup-Zeit. Fix: `rapidfuzz.fuzz.ratio` (C-Backend, ~50–100× schneller) bei gleicher Schwelle 0.90; der Längen-Prefilter (`min/max < 0.6`) kann bleiben oder durch `rapidfuzz.process.cdist` mit `score_cutoff` ersetzt werden. Schwellen-Äquivalenz vor dem Umstieg auf einem Sample verifizieren (SequenceMatcher.ratio vs. rapidfuzz.ratio liefern leicht andere Werte). Optional zusätzlich: das per-Batch `normalize_title()` der bestehenden Titel cachen statt pro Batch neu zu berechnen.

- [ ] **Datengetriebener "Structural vs. Hype"-Score für Mega-Trend-Karten.** Idee: aus der monatlichen Signalverteilung pro Mega-Trend ein Maß ableiten (Coverage + Entropie + Post-Peak-Decay). Dry-Run-Implementierung: `scripts/dryrun_structural_score.py` — kann re-run werden, sobald die Datenbasis besser ist.
  - **Aktuell nicht einsetzbar**, weil (1) neu hinzugefügte Mega-Trends durch kurze Historie falsch-positiv als STRUCTURAL klassifiziert werden, (2) die Monatsverteilung stark durch Pipeline-Batch-Zeitpunkte verzerrt ist (Signal-Share statt Signal-Count nötig), (3) Monatsauflösung bei <20 Signalen/Monat zu dünn ist. Wiedervorlage in ~6 Monaten, wenn alle Mega-Trends >=12 Monate Historie haben und Pipeline-Normalisierung implementiert ist.
  - **Erweiterung: Signal-Typologie gewichten.** Nicht jedes Signal ist gleich viel wert — die Lead-Zeit hängt stark vom Quellen-Typ ab:
    - **Science-Quellen** (Nature, Lancet, MIT Tech Review, IEEE Spectrum, Carbon Brief, STAT): Vorlauf ~5-10 Jahre → *Future Trends*
    - **Trade-Quellen** (TechCrunch, Vogue Business, Business of Fashion, FoodNavigator): Vorlauf ~1-2 Jahre → *Market Trends*
    - **Lifestyle/Culture** (Hypebeast, Highsnobiety, Creator Economy Blogs): Echtzeit → *Now Trends*
    - **Override-Listen in `scripts/assign_lead_time_tier.py` nachjustieren**, sobald der erste echte Score-Lauf ausgewertet ist. Aktuell sind die Tier-Zuordnungen Bauchgefühl; konkret überprüfen: `Semiconductor Engineering` (future vs. market?), `GamesIndustry.biz` (now vs. market?), `Platformer`/`Nieman Lab`/`Rest of World` (future vs. market?), `McKinsey Insights` (future vs. market?). Wenn ein Tier offensichtlich falsch liegt weil der Score-Verlauf nicht zur Realität passt, hier anpassen und `sources.yaml` per Script neu taggen.
    - Umsetzungsidee: `sources.yaml` um ein Feld `lead_time_tier` (`future | market | now`) ergänzen. Im Score dann Signale pro Tier getrennt aggregieren. Ein Mega-Trend, der zuerst in Science-Quellen auftaucht und Monate später in Trade und dann Now, ist strukturell echt. Ein Mega-Trend, der nur in Now-Quellen feuert, ist ein Hype/Opportunity-Fenster. Das macht den Score gleichzeitig erklärbar ("Signal-Pfad: Science → Trade → Now") und unabhängig von der Batch-Verzerrung der Pipeline.

- [ ] **Datengetriebene "Seit/Signale"-Badge auf Mega-Trend-Karten.** Statt erfundenem Horizont eine ehrliche Fakten-Zeile: `Seit <first_seen_month> · <n> Signale in 30 Tagen`. Werte kommen aus `raw_entries.published_date` gejoint über `trends.mega_trend`. Umsetzung: SQL in `getMegaTrends()` um `MIN(r.published_date) as first_seen` und `SUM(CASE WHEN r.published_date >= date('now','-30 days') THEN 1 ELSE 0 END) as signals_30d` erweitern, dann in `MegaTrendsPage.tsx` rendern.

- [ ] **Mega-Trend Full-Review via Anthropic API.** Ab ~15.000 Trends lohnt sich ein einmaliger Full-Review aller Trends über die Anthropic API statt lokal. Lokal (Qwen3 14B, Batches à 25): ~384 Batches × 90s = **9,5 Stunden**. Via API (Sonnet/Haiku, Batches à 400 dank 200K Kontext): ~24 Batches × 10-15s = **5 Minuten**. Kosten: ~$8.60 (Sonnet) / ~$2.40 (Haiku). Haiku reicht für Klassifizierung. Umsetzung: `--api` Flag in `mega_trend_reviewer.py`, Anthropic SDK statt `ollama_client.chat_structured`, Batch-Size auf 400. Trigger: wenn `SELECT COUNT(*) FROM trends WHERE status='published'` >= 15.000.

- [x] ~~**Mega-Trend-Reviewer Live-Run für heute published Trends.**~~ Erledigt 2026-04-09 über `scripts/review_recent_live.py`: 2678 Trends (gestern + heute) reviewed, 104 Mega-Trend-Updates, 61 min, 0 Fehler.

- [x] ~~**Hybrid-Suche (FTS5 + Embedding-Similarity) über Trends.**~~ Erledigt 2026-04-11. Foresight Cockpit live unter `/trends/foresight`. FTS5 + qwen3-embedding (4096-dim) via RRF (k=60). API: `GET /api/search?q=...&vertical=FOOD&limit=20`. In-Memory-Embedding-Cache (~75 MB für 4782 Trends). Analytics-Sidebar (Timeline, PESTEL, Lead-Time-Tiers, Mega-Trends, Co-Occurrence) ab >=30 Treffern. FTS5-only-Fallback automatisch wenn Ollama nicht erreichbar. Strict Threshold 0.60 für Embedding-only-Queries. RRF normalisiert auf Prozent (theoretisches Max 2/61).

- [ ] **Foresight-Search-Workbench — Ausbau der Hybrid-Suche zu einem Analysten-Werkzeug.** Aufbauend auf der Hybrid-Suche (FTS5 + Embedding, siehe oben). Die Suche soll vom reinen Nachschlagewerk zum Früherkennungs- und Hypothesenwerkzeug werden.
  - **Stufe 1 (MVP, auf der Hybrid-Suche aufbauend):**
    - Signal-Timeline pro Query: Histogramm der Trefferfrequenz über Zeit (Wochen/Monate), zeigt ob Begriff ansteigt/plateauiert/abflacht.
    - `lead_time_tier`-Breakdown: Treffer nach Science (future) / Trade (market) / Now getrennt zählen. Ein Begriff primär in Science = Frühindikator, primär in Now = Hype-Peak. Als Signal-Pfad-Strom visualisieren (Science → Trade → Now).
    - Mega-Trend-Verortung: Verteilung der Treffer über die 23 Mega-Trends.
  - **Stufe 2 (Power-User):**
    - Saved Queries als "Radar": Watchlist aus 10-30 Begriffen, Email/Newsletter-Digest bei neuen Treffern oder Velocity-Spikes.
    - Velocity-Score: Treffer letzte 30d vs. Baseline 90d; Delta-Alerts bei signifikantem Anstieg.
    - Co-Occurrence / Konzept-Graph: Welche Tags/Entitäten häufen sich mit einem Query? Funktioniert als Query-Erweiterer und Weak-Signal-Detector.
  - **Stufe 3 (Deep-Mode):**
    - Cross-Vertical-Parallelsuche: Derselbe Query in allen Vertikalen nebeneinander, "Jumping Trends" identifizieren.
    - Hypothesen-Dossiers: mehrere Queries bündeln zu einer These, gemeinsame Zeitreihe + Top-Quellen + Mega-Trends.
    - Negative Queries / Kontrast-Queries (`A vs. B` Ratio über Zeit).
    - PESTEL-Schnittebene: Treffer auf PESTEL-Dimensionen gemappt.
    - Export: Markdown / CSV / BibTeX pro Ergebnismenge für Reports/Keynotes.
  - **Mockup**: `frontend/mockups/foresight-search.html` (statischer Demo-Prototyp mit Fake-Daten, nicht verdrahtet).
  - **Watchouts (Daten-Audit 2026-04-09, n=3905 published Trends):**
    - **Analytik-Overlays nur bei n ≥ 30 Treffern anzeigen.** Query-Tiefe ist stark bimodal: breite Begriffe (AI=2030, climate=201, protein=128) tragen Timeline/Velocity/Tier-Breakdown problemlos, Nischen (cheese=4, fermentation=25, beverage=29) nicht. Unter der Schwelle: explizite Meldung "Zu wenige Signale für Trend-Analyse", nur Embedding-Treffer zeigen. Schützt vor falscher Präzision.
    - **Co-Occurrence braucht TF-IDF, nicht Raw-Count.** 16.115 unique Tags, davon **83% Singletons** (13.388). Top-10 sind ausschließlich Signal-Typ-Tags (`product_launch`, `market_shift`, ...), keine thematischen. Raw-Count-Cloud würde immer dieselben Signal-Typen oben zeigen. Fix: (1) Signal-Typ-Tags separat vom thematischen Vokabular führen oder (2) Tag-Counts gegen Gesamt-Korpus-Baseline gewichten (TF-IDF).
    - **Weak-Signal-Detection braucht Mindest-Baseline.** Wegen der 83% Singletons würden Tag-Velocity-Delta-Alerts ("+320% in 30 Tagen") bei jedem neuen Tag losgehen. Mindest-Baseline-Count (z.B. ≥3 in der Vorperiode) als Voraussetzung vor Prozent-Delta-Rechnung.
    - **PESTEL-Profil ist valide.** 100% der Published-Trends haben PESTEL-Tags (T=2538, S=1769, En=1260, E=1118, L=499, P=286). Aside-Block kann gebaut werden wie im Mockup.
    - **Published-Date-Coverage 94.2%** (3679/3905), Span 2023-01 → 2026-06 (~3,5 Jahre). Timeline-fähig.
    - **816 Trends haben NULL mega_trend.** Mega-Trend-Verortung ist für diese Trends leer. Vor dem produktiven Feature-Bau Reviewer-Ebene-B-Lauf über die NULLs abschließen.
    - **Mega-Trend-Power-Law.** 22 Mega-Trends, Median 107, Top bei 669 (AI), Bottom bei 4 (`modular_and_adaptive_systems`). Pro-Mega-Trend-Analysen nur für die Top-10-15 ehrlich.

- [x] ~~**Kombinierter EN+DE-Call testen.**~~ Getestet 2026-04-09 via `scripts/dryrun_bilingual_call.py` (50 Samples, `BilingualContent`-Schema mit allen 6 Feldern + `source_attribution` in einem strukturierten Aufruf). **Ergebnis: Zeitersparnis real, Qualitätsverlust nicht akzeptabel — nicht in Produktion übernehmen.**
  - **Performance:** 2-Call mean 33.0s, 1-Call mean 21.6s, Speedup **1.53×**. Erfolgsquote 50/50 in beiden Pfaden. **0 CJK-Leaks** im 1-Call-Pfad (2-Call hatte 1 automatischen Retry). Keine Schema-Validierungsausfälle.
  - **Qualitätsverlust:** (1) 1-Call produziert durchgängig einen **einzelnen Fließtext-Absatz** statt der im System-Prompt geforderten 3-Absatz-Struktur (Hook → Kontext/Analyse → Ausblick). (2) Outputs sind **30–40% kürzer** als 2-Call und unterschreiten die 150-250-Wort-Vorgabe. (3) DE-Teil gelegentlich Kasus-/Kleinschreibungsfehler ("patientenkapital", "langfristigem Werterschaffung"). (4) Positiv: 1-Call ist inhaltlich oft konkreter (zitiert mehr Originaldetails), weil das Modell den Excerpt nur einmal verarbeitet.
  - **Einordnung:** Die Einsparung von 11.4s/Entry (~38 Min auf 200 Entries) ist attraktiv, rechtfertigt den Strukturverlust aber nicht — die 3-Absatz-Struktur ist Kern des Produkt-Tons. Vor einer Wiedervorlage müsste der 1-Call-Prompt die Struktur- und Längen-Vorgaben deutlich härter einfordern (z.B. explizites "three paragraphs, minimum 150 words per language") und ein zweiter Vergleichslauf zeigen, dass sich Qualität auf 2-Call-Niveau bringen lässt ohne den Speedup zu verlieren. Artefakte: `data/bilingual_dryrun.json` + `.md`.

- [x] ~~**Auto-Publish + Review in Pipeline integrieren.**~~ Erledigt 2026-04-12. Umgesetzt als **Option A**: `reclassify_drafts()` (Stage 9) + `auto_publish()` (Stage 10) werden am Ende von `llm_processor.py` automatisch aufgerufen. Schwelle: `AUTO_PUBLISH_CONFIDENCE=0.85` (config.py). Neues Modul: `pipeline/reclassify.py`. Orchestrator-Script (Option B) bleibt als Backlog für Cron-Automatisierung.

- [x] ~~**Brave Search Radar Pipeline.**~~ Entfernt 2026-04-12. `pipeline/radar_discovery.py` (obsoleter Trendhunter-Workflow) gelöscht. Brave Search Radar wird nicht weiterverfolgt — 112 RSS-Primärquellen decken alle Vertikale ausreichend ab.

- [x] ~~**Foresight Cockpit auf MacBook Air (8GB RAM) testen.**~~ Erledigt 2026-04-12. Ergebnis: FTS5-only einwandfrei (787 ms), qwen3-embedding unbenutzbar auf 8 GB (4 min/Query, Memory Pressure rot, 8.9 GB Swap). Hybrid-Suche fachlich korrekt aber nicht interaktiv nutzbar. Empfehlung: FTS5-only auf schwachen Clients, optional `DISABLE_EMBEDDING_SEARCH` Env-Var. Details in `MACBOOK_SETUP.md`.

## Google Trends Integration via pytrends

- [ ] **pytrends als ergänzende Datenquelle für Trend-Validierung, Momentum-Scoring und Micro-Trend-Discovery.**

  Google Trends liefert über die inoffizielle Python-Library `pytrends` kostenlos Suchinteresse-Daten, die unsere RSS-Fachpresse-Signale um eine Consumer-Demand-Perspektive ergänzen. Kein API-Key nötig, aber Rate-Limits (~10-20 Requests/Minute).

  ### Drei Nutzungsebenen

  **Ebene 1 — Mega-Trend-Momentum-Validierung (wöchentlicher Cron)**

  Zweck: Prüfen ob unsere Mega-Trend-Gewichtung (AI=2772, Health=1410, ...) dem tatsächlichen öffentlichen Suchinteresse entspricht. Aufdecken von Über-/Unterrepräsentation.

  - `interest_over_time()` für alle 20 Mega-Trend-Keywords abfragen (je 5 pro Request, 4 Requests)
  - Zeitraum: `today 12-m` (wöchentliche Datenpunkte)
  - Google-Trends-Index (0-100) gegen unsere Signal-Counts normalisiert plotten
  - Ergebnis: `data/google_trends_momentum.json` — pro Mega-Trend: `{key, gt_index_current, gt_index_3m_ago, gt_delta_pct, catandary_signal_count, ratio}`
  - Divergenzen flaggen: wenn `gt_delta_pct > +50%` aber unsere Signale stagnieren → blinder Fleck; wenn `gt_delta_pct < -30%` aber wir viele neue Signale haben → Fachpresse-Bubble
  - `interest_by_region()` parallel abfragen → validiert unser `regions`-Feld (sind "Global"-markierte Trends wirklich global, oder nur US/EU?)

  Implementierung:
  ```
  pipeline/google_trends.py
    - fetch_mega_trend_momentum() → 4 Requests, 20 Keywords, 12-Monats-Zeitreihe
    - fetch_mega_trend_regions() → 4 Requests, Top-5-Länder pro Keyword
    - save_momentum_snapshot() → data/google_trends_momentum.json (append, timestamped)
    - compare_with_catandary() → Divergenz-Report nach stdout/log
  ```

  Google-Trends-Keywords pro Mega-Trend (Mapping nötig, da unsere Keys nicht direkt suchbar sind):
  ```yaml
  artificial_intelligence_and_automation: "artificial intelligence"
  personalized_health_and_longevity: "longevity health"
  financial_innovation_and_inclusion: "fintech"
  future_of_food_and_agriculture: "future of food"
  clean_energy_transition: "clean energy"
  new_luxury_and_premiumization: "quiet luxury"
  inclusive_and_human_centric_design: "inclusive design"
  mental_health_and_neuro_wellness: "mental health tech"
  digital_trust_and_data_sovereignty: "data privacy"
  regenerative_design_and_net_positive: "regenerative design"
  climate_resilience_and_adaptation: "climate adaptation"
  geopolitical_disruption_and_supply_chain_resilience: "supply chain resilience"
  experience_economy_and_immersive_design: "immersive experience"
  bio_revolution_and_new_materials: "biomaterials"
  electric_and_autonomous_mobility: "electric vehicle"
  circular_economy_and_zero_waste: "circular economy"
  connected_living_and_smart_spaces: "smart home"
  cultural_heritage_and_identity: "cultural heritage"
  wearable_technology_and_augmented_living: "wearable technology"
  creator_economy_and_platform_shift: "creator economy"
  ```
  Dieses Mapping muss einmal manuell kuratiert und in `config.py` oder `mega_trends.yaml` hinterlegt werden. Pro Mega-Trend ggf. 2-3 alternative Suchbegriffe testen und den mit dem höchsten/stabilsten Index wählen.

  **Ebene 2 — Micro-Trend-Discovery via Rising Queries (wöchentlicher Cron)**

  Zweck: Neue aufsteigende Suchbegriffe finden, die wir in unseren RSS-Quellen noch nicht covern. Frühwarnsystem für Trends die in der Consumer-Suche explodieren bevor sie in der Fachpresse landen.

  - `related_queries()` für die 20 Mega-Trend-Keywords, Filter: `rising` (>= Breakout oder >100% Wachstum)
  - Zusätzlich: `related_queries()` ohne Keywords aber mit Kategorie-Filter für unsere 8 Verticals:
    ```
    FOOD:      cat=71  (Food & Drink)
    TECH:      cat=5   (Computers & Electronics)
    HEALTH:    cat=45  (Health)
    ECO:       cat=174 (Science) + cat=12 (Business & Industrial)
    DESIGN:    cat=3   (Arts & Entertainment)
    FASHION:   cat=44  (Beauty & Fitness)
    BIZ:       cat=12  (Business & Industrial) + cat=7 (Finance)
    LIFESTYLE: cat=3   (Arts & Entertainment) + cat=65 (Hobbies & Leisure)
    ```
  - `related_topics()` parallel → breitere thematische Felder statt einzelner Suchbegriffe
  - `suggestions(keyword)` für jeden Rising Query → Autocomplete-Expansion, findet Long-Tail-Varianten

  Ergebnis-Pipeline:
  1. Rising Queries sammeln → `data/google_trends_rising.json`
  2. Gegen bestehende `trends.tags` und `trends.title_en` matchen (FTS5 MATCH oder simple LIKE)
  3. **Unmatched Rising Queries** = potenzielle blinde Flecken → Report: "Google-Nutzer suchen zunehmend nach X, aber wir haben dazu 0 Signale"
  4. Optional: Unmatched Queries als Seed-Keywords für neue RSS-Quellen-Recherche verwenden

  Implementierung:
  ```
  pipeline/google_trends.py (Erweiterung)
    - fetch_rising_queries_by_mega_trend() → 20 Keywords × related_queries(rising)
    - fetch_rising_queries_by_category() → 8 Verticals × cat-IDs
    - fetch_related_topics() → 20 Keywords × related_topics(rising)
    - match_against_corpus() → FTS5-Match gegen trends.title_en + trends.tags
    - generate_gap_report() → data/google_trends_gaps.md
  ```

  **Ebene 3 — Trending-Searches als Consumer-Signal-Layer (täglicher Cron)**

  Zweck: Tägliche Google-Trending-Searches als zusätzlichen Signal-Stream neben RSS-Fachpresse. Zeigt was *Konsumenten* bewegt vs. was *Fachmedien* berichten.

  - `trending_searches(pn='united_states')` + `pn='germany'` → je ~20 tägliche Trending-Begriffe
  - `realtime_trending_searches(pn='US')` → Trending Now mit **zugehörigen News-Links** (quasi Discovery-Quelle)
  - Gegen unsere Vertical-Taxonomie klassifizieren (einfacher LLM-Call oder Keyword-Matching)
  - Speichern in neue Tabelle `google_trending` (nicht in `trends` — anderer Signaltyp)

  Implementierung:
  ```
  pipeline/google_trends.py (Erweiterung)
    - fetch_daily_trending(countries=['united_states', 'germany']) → trending_searches()
    - fetch_realtime_trending(countries=['US', 'DE']) → realtime_trending_searches()
    - classify_trending(items) → Vertical-Zuordnung via Keyword-Match oder LLM
    - store_trending() → INSERT in google_trending Tabelle
  ```

  DB-Schema:
  ```sql
  CREATE TABLE google_trending (
      id INTEGER PRIMARY KEY,
      query TEXT NOT NULL,
      country TEXT NOT NULL,           -- 'US', 'DE'
      source TEXT NOT NULL,            -- 'daily' | 'realtime'
      related_news_url TEXT,           -- nur bei realtime
      related_news_title TEXT,
      vertical TEXT,                   -- klassifiziert gegen Catandary-Taxonomie
      mega_trend TEXT,                 -- optional: Mega-Trend-Match
      matched_trend_id INTEGER,        -- FK auf trends.id wenn Match gefunden
      fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX idx_google_trending_date ON google_trending(fetched_at);
  CREATE INDEX idx_google_trending_vertical ON google_trending(vertical);
  ```

  Frontend-Darstellung (perspektivisch):
  - "Consumer Buzz"-Widget auf `/trends`: Top-5 Trending Queries der letzten 24h die zu einem unserer Verticals matchen
  - Auf Mega-Trend-Detailseiten: "Was Konsumenten gerade suchen" als Kontrast zu den Fachpresse-Signalen

  ### Rate-Limiting & Scheduling

  Google drosselt bei >10-20 Requests/Minute. Strategie:
  - **3 Sekunden Pause** zwischen Requests (`time.sleep(3)`)
  - **Exponential Backoff** bei 429-Errors (2s → 4s → 8s → 16s, max 3 Retries)
  - **Request-Budget pro Cron-Lauf:**
    - Ebene 1 (Momentum): ~12 Requests (4× interest_over_time + 4× interest_by_region + Reserve) → ~1 Minute
    - Ebene 2 (Rising): ~30 Requests (20× related_queries + 8× category-queries + Reserve) → ~2 Minuten
    - Ebene 3 (Trending): ~4 Requests (2× daily + 2× realtime) → ~15 Sekunden
  - **Gesamt: ~46 Requests, ~4 Minuten pro Lauf** — weit unter dem Drosselungs-Limit wenn über 3-5 Minuten verteilt

  Cron-Vorschlag:
  ```
  # Google Trends Momentum + Rising Queries (Samstag 6:00, wöchentlich)
  0 6 * * 6    python -m pipeline.google_trends --momentum --rising
  # Google Trends Daily Trending (täglich 8:00)
  0 8 * * *    python -m pipeline.google_trends --trending
  ```

  ### Priorisierung & Abhängigkeiten

  | Ebene | Aufwand | Wert | Abhängigkeiten |
  |---|---|---|---|
  | 1 Momentum | ~2h | Hoch — validiert Mega-Trend-Gewichtung, sofort actionable | Mega-Trend-Keyword-Mapping kuratieren |
  | 2 Rising | ~3h | Hoch — Blind-Spot-Detection, neue Quellen-Seeds | FTS5 muss laufen (bereits vorhanden) |
  | 3 Trending | ~3h | Mittel — Consumer-Perspektive, eher Nice-to-have | Neue DB-Tabelle, Frontend-Widget optional |

  Empfehlung: Ebene 1 zuerst als Standalone-Script (`scripts/dryrun_google_trends.py`), Ergebnis evaluieren. Wenn die Momentum-Daten nützlich sind, Ebene 2 dranbauen. Ebene 3 ist unabhängig und kann jederzeit separat gebaut werden.

  ### Risiken & Watchouts

  - **pytrends ist inoffiziell** — Google kann Endpoints jederzeit ändern. Library-Updates verfolgen, Fallback: `serpapi.com` Google Trends API ($50/Monat, 5.000 Searches) als Alternative.
  - **Relative Werte** — Google Trends liefert nur Index 0-100 relativ zum Zeitraum, kein absolutes Suchvolumen. Vergleiche nur innerhalb eines Requests valide. Mega-Trend-Keywords daher immer im selben 5er-Batch abfragen.
  - **Keyword-Qualität entscheidend** — "circular economy" trifft den Mega-Trend gut, "inclusive design" vielleicht nicht. Das Keyword-Mapping muss iterativ optimiert werden.
  - **Geo-Bias** — Google Trends ist stark US/EU-lastig. Für APAC/LatAm-Trends weniger aussagekräftig.
  - **Kein Ersatz für Fachpresse** — Google Trends zeigt Consumer-Interesse, nicht Branchen-Innovation. Ein Trend kann in der Fachpresse explodieren ohne dass Konsumenten danach suchen (z.B. "carbon capture"). Beide Perspektiven ergänzen sich, ersetzen sich nicht.

## Pipeline-Orchestrierung (Cron)

- [x] ~~**`pipeline/run_full_cycle.py` — Orchestrator-Script für den Hauptzyklus.**~~ Implementiert 2026-04-12. Flags: `--batch N`, `--skip-poll`, `--skip-llm`, `--dry-run`. Logs to `data/cycle_log.jsonl`. Crontab:
    ```
    30 */4 * * *   python -m pipeline.run_full_cycle --batch 200
    0 3 1 * *      python -m pipeline.mega_trend_reviewer
    # 0 9 * * 1    python -m pipeline.newsletter_generator  (wenn Versand fertig)
    ```
  - **Bestehendes `deploy/crontab.txt` danach aktualisieren** (aktuell veraltet: Trendhunter-Referenz, auto_publisher als eigener Cron — beides inzwischen in die LLM-Pipeline integriert)

## Hardware-Notizen

- **Pipeline-Verhalten auf RTX 3090 (24 GB GDDR6X)** — Stand 2026-05-09. Aktuelle Baseline: RTX 5080, 16 GB GDDR7, 960 GB/s.

  | Aspekt | RTX 5080 (jetzt) | RTX 3090 |
  |---|---|---|
  | VRAM | 16 GB GDDR7 | **24 GB** GDDR6X |
  | Bandbreite | 960 GB/s | 936 GB/s |
  | Architektur | Blackwell | Ampere (mature) |

  **Auswirkungen beim Umzug:**

  1. **Qwen3:14B passt komfortabel** — belegt nur ~68 % der 24 GB statt 84 % der 16 GB. Headroom für VRAM-Hijacks (Browser-WebGPU, ComfyUI, DWM) → Crash am 2026-05-09 (41 % Offload, 9.6 h Laufzeit, 263 Reclassify-Errors) wäre nicht passiert.
  2. **Größere Modelle möglich** — Qwen3:32B (~20 GB) oder Mistral Small 3.2 24B (CLAUDE.md-Alternative für Stage 5) laufen ohne CPU-Offload. Höhere Sprachqualität bei Content-Gen.
  3. **Mehrere Modelle parallel** — qwen3:14b + qwen3-embedding gleichzeitig im VRAM. Spart Modell-Reload zwischen Stage 5 und 6 (~1–2 Min/Batch). `OLLAMA_NUM_PARALLEL=2` wird sinnvoll nutzbar.
  4. **Geschwindigkeit pro Token** — 5–10 % langsamer (älterer Tensor-Core, ähnliche Bandbreite). Stage 6 von 70–82 Min auf 75–90 Min. Praktisch unmerklich, durch fehlendes Offload-Risiko + Parallelisierung **netto gleich schnell oder schneller**.
  5. **GPU-Check (`MIN_GPU_FRACTION=0.80`)** — unverändert sinnvoll, fängt VRAM-Hijacks weiterhin auf der 3090.

  **Beim Umzug zu beachten:**
  - Ollama + Modelle portabel (`ollama pull` neu ziehen)
  - 3090 läuft heißer/lauter unter Dauerlast (älteres Cooling) — bei Eigen-Hardware Belüftung sicherstellen
  - `OLLAMA_KEEP_ALIVE` höher setzen (z. B. 30m), weil Modell-Reloads keine Konkurrenz ums VRAM mehr haben

  **Net-Effekt:** Pipeline robuster (kein Offload-Risiko), gleich schnell oder schneller durch parallele Stages, Tür zu größeren Modellen offen.

## Tagesziele 2026-04-11

- [x] ~~**Cron-Jobs einrichten.**~~ Plan erstellt, siehe "Pipeline-Orchestrierung" oben. Umsetzung als eigenes Feature.
- [x] ~~**Newsletter implementieren.**~~ Erledigt — `pipeline/newsletter_generator.py` produziert EN-Editions in DB-Tabelle `newsletter_editions`, KW15–KW21/2026 retroaktiv generiert (Stand 2026-05-25). Optionales llama.cpp-Backend via `NEWSLETTER_LLM_BACKEND=llamacpp` (Qwen3.6-35B-A3B). **Offen:** automatischer Cron-Job (Mo 09:00), Anbindung an Resend/Buttondown für tatsächlichen Versand.
- [x] ~~**Plattform auf MacBook Air testen.**~~ Erledigt 2026-04-12, siehe `MACBOOK_SETUP.md`.
