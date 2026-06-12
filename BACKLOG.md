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

## Pipeline-Optimierung

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
