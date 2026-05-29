# Catandary Trends — Datenpipeline-Erweiterung: Von RSS zu Multi-Source Intelligence

## Rolle

Du designst die **Quellen-Erweiterung** des Catandary-Trends-Ingestion-Layers. Deine Optimierungsziele in dieser Priorität:

1. **Signal-Lead-Time senken** — frühere Erkennung als die etablierte Fachpresse.
2. **Selektionsbias reduzieren** — geografisch, sprachlich, formattechnisch.
3. **Wartungskosten und rechtliches Risiko begrenzen** — `2026-04-12`-Realität: Reddit-, X- und Crunchbase-APIs sind seit 2023 mehrheitlich kostenpflichtig oder strikt eingeschränkt; HTML-Scraping toleriert keine ToS-Verletzungen oder Login-Umgehungen.

Du bist kein Listenpfleger. **Du priorisierst und begründest.** Eine 30-Punkte-Liste ohne Begründung ist eine schlechtere Antwort als 8 sauber bewertete Quellen mit Trade-off-Analyse.

## Faktischer Ist-Zustand (Stand 2026-05-29)

**Hardware & LLM-Stack:**
- GPU: variiert (NVIDIA RTX 3090 24GB oder RTX 5080 16GB — VRAM-Headroom je nach Konfiguration). Embeddings: `qwen3-embedding`, 4096-dim.
- 9-stufige LLM-Pipeline: 1) Title-Dedup → 2) Relevance (Qwen3 8B) → 3) Extraction (Qwen3 8B) → 4) NER+Classification (Qwen3 8B) → 5) Embedding-Dedup → 6) Content-Gen → 7) Insert → 8) Reclassify → 9) Auto-Publish (≥0.85 confidence).
- **Stage 6 läuft seit 2026-05-25 auf llama.cpp `Qwen3.6-35B-A3B` via Mid-Pipeline GPU-Swap** (Ollama-Modelle entladen → llama-server hoch → zurück). Default-Fallback Ollama Qwen3 14B. Routing via `STAGE5_BACKEND=llamacpp`.

**Datenbasis:**
- **137 aktive Quellen** von 140 (Typen: 87 trade_media, 48 research, 2 press_wire). Trendhunter und Aggregatoren wurden 2026-04-12 entfernt.
- **26.374 published Trends** in SQLite, Embedding-Dedup-Schwelle 0.92 cosine.
- 8 Vertikale (FOOD, TECH, HEALTH, ECO, DESIGN, FASHION, BIZ, LIFESTYLE), **21 kanonische Mega-Trends** (`mega_trends.yaml`), PESTEL-Cross-Klassifizierung.
- **`lead_time_tier`** ist im Code validiert: nur `future` | `market` | `now` zulässig (`pipeline/feed_poller.py:100`).

**Aktueller `source_type` in der Tabelle `sources`:** nur `trade_media`, `research`, `press_wire`. Reichere Typen wie `social`, `patent`, `regulation`, `brand_newsroom`, `marketplace` existieren **nicht** — sie sind Teil dieses Designs, nicht des Ist-Zustands.

**Was fehlt nachweislich** (verifiziert in DB): keine Reddit-, keine Hacker-News-, keine Patent-, keine Job-Market-, keine Funding-, keine chinesischen, keine offiziellen Brand-Newsroom-Integrationen. Heise und Golem fehlen (t3n vorhanden). arXiv ist aktiv (nicht deaktiviert).

## Was die bestehende Pipeline strukturell nicht abdeckt

1. **Lead-Time-Defizit gegenüber Communities.** RSS von Fachmedien hinkt 1–6 Wochen hinter dem Diskurs in Subreddits, HN-Threads und Patent-Filings hinterher.
2. **Quantitative Signale fehlen.** Keine Funding-Volumina, Patent-Counts, Job-Postings, Suchvolumen — alles, was sich nicht als Text-Artikel veröffentlicht.
3. **Geosprachlicher Bias.** Chinesische (36Kr, LatePost, TechNode), japanische (Nikkei Asia), koreanische, deutschsprachige (Heise, Golem) Frühindikatoren fehlen.
4. **Keine Erstpartei-Brand-Signale.** Tesla AI Day, Apple Newsroom, Unilever Innovation, Nestlé R&D — Marken publizieren oft vor der Fachpresse.
5. **Regulatorische und legale Frühindikatoren fehlen** (EFSA, FDA, EUR-Lex, EPO Open Patent Services).

## Constraints (hart)

- **Kein API-Tier > 100 €/Monat** ohne explizite Rechtfertigung. Reddit ($0.24/1k calls seit 2023), Crunchbase (Basic 99 $/Monat), X Basic (200 $/Monat) gelten als **bezahlt** und müssen Impact begründen.
- **Keine ToS-Verletzungen, keine Login-Umgehungen, keine Paywall-Bypässe.** Robots.txt respektieren. Bei HTML-Scraping nur dann, wenn der Seitenbetreiber kein API/RSS anbietet und das öffentliche HTML ein robots-konformer Pfad ist.
- **Eingabe-Schema ist nicht verhandelbar.** Jede neue Quelle muss in ein Entry-Objekt konvertieren: `{title, url, excerpt, source_name, vertical, published_date, source_type, lead_time_tier}`. Das ist der Mindest-Kontrakt mit `llm_processor.py`. Felder dürfen ergänzt werden, der Kern bleibt.
- **`lead_time_tier` ist Pflicht** für jede neue Quelle und muss in `{future, market, now}` liegen. Die Wahl ist zu begründen.
- **Dedup-Layer wird über die bestehende Embedding-Stage gelöst.** Neue Quellen erzeugen keinen eigenen Dedup-Mechanismus — sie müssen Excerpts liefern, die für 4096-dim qwen3-embedding ausreichen (≥120 Zeichen wirklicher Inhalt; kein „Click here to read more").

## Antipatterns (das willst du **nicht** liefern)

- Eine Quellenliste ohne `lead_time_tier`-Zuordnung.
- „Reddit API ist kostenlos" / „X via Topic-Streams" / „Crunchbase free tier 100 calls/Monat" — alle drei sind **falsch in 2026**.
- EUIPO als Patent-Quelle nennen (EUIPO = Trademarks/Designs; Patente = **EPO Open Patent Services / Espacenet OPS API**).
- Quellen vorschlagen, die bereits existieren (siehe `sources.yaml` — vor jeder Empfehlung prüfen).
- 4 Quellen pro Vertikale × 8 Vertikale = 32 Vorschläge ohne Priorisierung. **Liefere lieber 8–12 wirklich begründete Vorschläge** mit klarem Pfad.
- Architekturvorschläge ohne konkretes Modulverhalten („wir brauchen einen Fetcher-Dispatcher" reicht nicht — beschreibe Interfaces und State).
- HTML-Scraping ohne Fragility-Plan (CSS-Selector-Drift ist die häufigste Ausfallursache).

## Deliverables (in dieser Reihenfolge)

### 1) Quellen-Roadmap — 8–12 priorisierte Kandidaten (Hauptlieferung)

Pro Kandidat eine YAML-Karte in diesem Format:

```yaml
- name: <Quelle>
  url: <Root oder Feed-URL>
  vertical: <FOOD|TECH|HEALTH|ECO|DESIGN|FASHION|BIZ|LIFESTYLE|CROSS>
  source_type: <rss_feed|html_scrape|api|social|patent|regulation|brand_newsroom|marketplace|research_preprint>
  lead_time_tier: <future|market|now>           # Begründung in `rationale`
  access_method: <RSS|REST|GraphQL|HTML|OAI-PMH>
  legality: <public_no_login|public_with_throttling|terms_require_attribution>
  cost: <free|low|paid>                          # paid = > 100 €/Monat
  implementation_effort: 1-5                     # 1=Tag, 2=2-3 Tage, 3=Woche, 4=2 Wochen, 5=Monat
  expected_impact: 1-5                           # 1=Nischensignal, 5=Strukturwandel-Frühwarnung
  priority_score: impact × (6 - effort)          # höher = besser
  rationale: |
    Warum diese Quelle? Welcher Bias-Lücke begegnet sie? Welche Klasse von
    Signalen liefert sie, die wir heute nicht haben? Warum dieser lead_time_tier?
  failure_modes: |
    Wo bricht es? (Rate-Limits, Selektor-Drift, Sprache, Volumen-Spam)
  guardrails: |
    Was muss in der Filter-Stage 2 anders sein, damit die Quelle nicht in Spam endet?
```

**Sortierreihenfolge:** `priority_score` absteigend. Wenn zwei Quellen vergleichbar sind, gewinnt die mit niedrigerem `implementation_effort`.

**Pflicht-Coverage:** Mindestens je ein Vorschlag aus den Achsen *Community/Social*, *Brand Newsroom*, *Non-English*, *Patent oder Regulierung*. Eine Achse leer lassen ist erlaubt, wenn begründet.

### 2) Architektur-Delta — wie sich nicht-RSS in `feed_poller.py` einfügt

Ein knapper Vorschlag (max. 1 Bildschirmseite Code/Pseudocode), der folgende Fragen beantwortet:

- **Polymorpher Fetcher oder neues Modul?** Begründung — keine Lösung ohne Trade-off-Diskussion.
- **`source_type` als Dispatch-Schlüssel:** Wie wird ein neuer Typ angemeldet, ohne `feed_poller.py` für jeden Typ aufzubohren?
- **Excerpt-Mindeststandard:** Wie stellst du bei API-/Social-Quellen sicher, dass das Embedding-Dedup nicht durch leere/zu kurze Texte ausgehebelt wird?
- **Backoff und Quellengesundheit:** Aktuell logged der Poller nur HTTP-Status. Was ändert sich bei Quellen mit echten Rate-Limits?
- **Cross-Source-Dedup:** Wenn dieselbe Story aus 3 Quellen kommt — wo wird das gefangen (Title-Dedup Stage 1? Embedding-Dedup Stage 5? Beides?).

### 3) MVP-Plan — was in 2 Wochen umsetzbar ist

Konkret: welche **3 Quellen** aus deiner Roadmap startet du zuerst, in welcher Reihenfolge, und warum. Erfolgskriterium pro Quelle (was muss nach 14 Tagen messbar besser sein? z.B. „mindestens 5 published Trends aus dieser Quelle mit confidence ≥ 0.85"; „mindestens 1 trend, der nicht aus einer bestehenden Quelle bereits abgeleitet wurde").

### 4) Stage-2-Filter-Anpassung — der einzige Prompt-Eingriff der Pipeline

Stage 2 (Relevance Filter) ist die einzige Stelle, an der quellen-typ-spezifisches Verhalten in die LLM-Pipeline einfließen muss. Frage: **Welche source_types brauchen einen anderen Filter-Prompt?**

- Ein Reddit-Kommentar-Thread hat andere Relevanz-Schwellen als ein Nature-Paper.
- Ein Patent-Abstract ist immer „relevant" im engen Sinne, aber liefert vielleicht keinen verwertbaren Trend.
- Ein Brand-Newsroom-Eintrag ist immer ein Selbst-Marketing-Text — braucht es einen Skeptizismus-Override?

Liefere ein konkretes Prompt-Patch-Konzept (kein vollständiger Prompt) für die `source_type`-Klassen, die du in Deliverable 1 vorgeschlagen hast.

## Success Criteria

Deine Antwort ist gut, wenn:

- Jeder Quellen-Vorschlag mindestens eine konkrete URL, eine begründete `lead_time_tier`-Zuordnung und einen `failure_modes`-Block hat.
- Die `priority_score`-Reihenfolge keine Überraschungen enthält (eine 5/5-Impact-Quelle mit Effort 1 muss Platz 1 sein).
- Mindestens eine deiner Empfehlungen **widerspricht** dem naheliegenden Pfad — z.B. begründet, warum Reddit-API trotz Kosten lohnt, oder warum 36Kr trotz Übersetzungsaufwand kein Quick-Win ist.
- Architektur-Delta ist im bestehenden Codestil umsetzbar (keine neue Sprache, kein neuer Framework-Layer).
- MVP-Plan nennt konkrete erste 3 Quellen, nicht „dann sehen wir weiter".

## Kontextdateien

- `sources.yaml` — bestehende Konfiguration, **vor jedem Vorschlag prüfen** (vermeide Duplikate)
- `pipeline/feed_poller.py` — bestehender RSS-Poller, validiert `lead_time_tier`
- `pipeline/llm_processor.py` — 9-stufige Pipeline, Stage-2-Filter ist dein Eingriffspunkt
- `pipeline/config.py` — Modelle, Schwellen
- `pipeline/llamacpp_client.py` und `pipeline/gpu_handover.py` — falls Stage 6 später quellen-typ-abhängig generieren soll (out of scope hier, aber relevant für Architektur-Diskussion)
- `mega_trends.yaml` — 21 kanonische Mega-Trends, an die deine Quellen gemappt werden sollten
- `CLAUDE.md` — Vollarchitektur, Taxonomie, Hetzner-Deployment
- `BACKLOG.md` — bereits aufgeschobene Ideen (Google Trends, Structural Score) — nicht doppelt vorschlagen
