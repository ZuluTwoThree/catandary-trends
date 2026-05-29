# Catandary Trends — Arbeitsplan: TRL 7–8 & Infrastruktur-Migration

Branch: `arch/trl-upgrade`
Erstellt: 2026-05-22
Basis: Briefing "Reife-Sprung auf TRL 7–8" + Ergänzung "Infrastruktur-Migration"
Repo: `github.com/ZuluTwoThree/catandary-trends @ main 1c11cbc`

## Statusübersicht (Stand 2026-05-29)

| # | Deliverable | Status |
|---|---|---|
| D1 | Code-Review A–H | offen |
| D2 | Infrastruktur-Migration Ollama → llama.cpp + 80B | **teilweise erledigt** — Stage 6 (Content-Gen) läuft seit 2026-05-25 auf llama.cpp mit **Qwen3.6-35B-A3B** (nicht 80B); GPU-Handover, Pre-Flight, Wortzahl-Guard implementiert (Commits `e0161e0` + `5250ba8` + `91e0729`); vier saubere Nachtläufe. Restscope: weitere Stages auf llama.cpp + 80B-A/B-Test (D3) |
| D3 | A/B-Studie Qwen3-Next-80B vs qwen3:14b (Stage 6) | offen — Dry-Run-Tool `scripts/dryrun_stage5_llamacpp.py` ist die Basis, 80B-Run noch nicht durchgeführt |
| D4 | Quellen-Diversifizierungsplan inkl. Newsletter-Ingest | **brief erstellt** (`pipeline_expansion_prompt.md`, `2f9db07`) + aktiver Goal Contract (`goals/2026-05-29-pipeline-expansion-mvp.md`); MVP-Deadline 2026-06-26 |
| D5 | Synthese-Layer (Cluster-Detection, Weak-Signal) | offen |
| D6 | Quality-Metrics-Framework | offen |
| D7 | TRL-Roadmap (6→7→8) | offen — neu zu fassen nach D2/D4-Fortschritt |

Detaillierter Wochenplan unten ist der ursprüngliche Stand vom 2026-05-22 und wird beim nächsten Review aktualisiert.

---

## 0. Zusammenfassung

Dieser Plan führt Catandary Trends von TRL 6 (operativer Prototyp, manuell überwacht) auf TRL 7 (validierte Operation mit messbarer Output-Qualität). Er umfasst sieben Deliverables in sechs Wochen, organisiert um zwei parallele Stränge: Infrastruktur-Migration (Ollama → llama.cpp + Qwen3-Next-80B) und systematische Qualitätsverbesserung (Klassifikation, Scoring, Synthese, Metriken).

Erfolgskriterium TRL 7 (aus dem Briefing):

> Die Pipeline klassifiziert jeden neuen Trend mit mega_trend-Korrektheit ≥ 90 % (Trendforscher-Audit), wirft mega_trend = null nicht stillschweigend in den Publish, erkennt Konvergenzen über ≥ 3 Vertical-Grenzen automatisch, und produziert Stage-6-Texte die in einem Blind-Test gegen Trendwatching-Artikel nicht trivial unterscheidbar sind. Quellen umfassen RSS plus ≥ 12 Newsletter. Trend-Scores spreizen über mindestens 0.3 Punkte (P95 minus P5).

---

## 1. Deliverable-Übersicht

| #  | Deliverable                                          | Lead               | Aufwand     | Abhängigkeiten |
|----|------------------------------------------------------|---------------------|-------------|----------------|
| D1 | Code-Review A–H                                      | Architekt           | 14 Tage     | —              |
| D2 | Infrastruktur-Migration Ollama → llama.cpp + 80B      | Architekt           | 8 Tage      | —              |
| D3 | A/B-Studie Qwen3-Next-80B vs qwen3:14b (Stage 6)     | Architekt + TF      | 3 Tage      | D2             |
| D4 | Quellen-Diversifizierungsplan inkl. Newsletter-Ingest | Trendforscher       | 4 Tage      | —              |
| D5 | Synthese-Layer (Cluster-Detection, Weak-Signal)       | TF Methodik, Arch   | 6 Tage      | D1-F1          |
| D6 | Quality-Metrics-Framework                             | Gemeinsam           | 7 Tage      | D2, D3         |
| D7 | TRL-Roadmap (6→7→8)                                  | Gemeinsam           | 2 Tage      | D1–D6          |

Reihenfolge: D1 + D2 parallel → D3 (Gate) → D4 parallel mit D5 → D6 → D7.

---

## 2. Wochenplan

### Woche 1–2: Infrastruktur + Code-Review (parallel)

**D2 — Infrastruktur-Migration (Architekt, 8 Tage, höchste Priorität)**

Die Migration folgt den sechs Schritten aus §3.1 der Ergänzung. Alle Dateien relativ zu `catandary-trends/`.

Tag 1–2: Abstraktionsschicht

- `pipeline/llamacpp_client.py` schreiben — Drop-in für `pipeline/ollama_client.py` mit identischen Signaturen:
  - `chat(model, prompt, system, temperature) → str`
  - `chat_structured(model, prompt, schema, system, temperature, fallback_model) → T | None`
  - `generate_embedding(model, text) → list[float] | None`
  - `check_model_available(model) → bool`
- HTTP gegen `POST /v1/chat/completions` (Port 8081) für Generation, `POST /embedding` (Port 8082) für Embeddings
- Structured-Output-Pfad evaluieren: JSON-Schema via `response_format` vs. GBNF-Grammar. Entscheidung anhand von 50-Item-Testlauf (Failure-Rate < 1 % als Kriterium)
- `INFERENCE_BACKEND` env-Variable in `pipeline/config.py` einführen (`'ollama' | 'llamacpp'`), Default `'ollama'` bis Cut-over
- Neue env-Variablen: `LLAMACPP_GEN_URL` (default `http://127.0.0.1:8081`), `LLAMACPP_EMBED_URL` (default `http://127.0.0.1:8082`)
- `.env.example` aktualisieren (H4)

Tag 3: systemd-Units + Wrapper

- `~/.config/systemd/user/catandary-llama-gen.service` — `llama-server -m ~/llama.cpp/models/Qwen3-Next-80B-A3B-Instruct-UD-Q3_K_XL.gguf --port 8081 -ngl 99 -fa on -c 16384 --jinja`
- `~/.config/systemd/user/catandary-llama-embed.service` — `llama-server -m ~/llama.cpp/models/nomic-embed-text-v1.5.Q4_K_M.gguf --port 8082 --embedding`
- GPU-Health-Check in `pipeline/run_full_cycle.py:check_gpu()` umbauen (H3):
  - Ollama-spezifisches `/api/ps` ersetzen durch `/health`-Endpoint pro Server + `nvidia-smi --query-gpu=memory.used` VRAM-Verifikation
  - Schwelle: beide Server `up` UND VRAM ≥ 33.5 GB belegt
- `scripts/scheduled_cycle.sh` anpassen: catandary-llama-Services starten/stoppen um den fcc-Stack herum

Tag 4–5: Schatten-Lauf + Threshold-Kalibrierung

- 200-Item-Schatten-Lauf: gleiche raw_entries durch beide Backends (Ollama-Pfad + llama.cpp-Pfad), Output in separate Test-Tabelle `trends_test_llamacpp`
- Manuelle Diff-Sichtung:
  - Relevance-Filter: Übereinstimmung der Entscheidungen
  - Vertical-Classification: Übereinstimmung der Verticals
  - Content-Quality: Stichprobe 20 Bodies vergleichen
  - Structured-Output Failure-Rate messen (Ziel: < 1 %)
- Akzeptanzkriterien: ≤ 5 % Divergenz in `primary_vertical`, Content-Qualität visuell ≥ Ollama, Cycle-Zeit ≤ aktueller Stand

Tag 5–6: Re-Embedding

- `scripts/reembed_all_trends.py` schreiben:
  - 23.808 published Trends × ~50 ms = ~20 min
  - `trends.embedding` BLOB komplett neu schreiben (4096-dim → 768-dim, alte BLOBs unbrauchbar)
  - Backup-Snapshot (`scripts/backup_db.py`) direkt davor
  - Optionale Spalte `embedding_legacy` für Rollback-Pfad (Architekt entscheidet ob Spalte oder externer Snapshot)
- `DUPLICATE_SIMILARITY_THRESHOLD` (aktuell 0.92 in `pipeline/config.py`) neu kalibrieren:
  - Trendforscher kuratiert 100 positive Duplikat-Paare + 100 negative aus bestehendem Korpus
  - Architekt berechnet ROC-Kurve, wählt Schwelle bei Precision ≥ 0.95
- `frontend/src/app/api/search/route.ts`: `EMBED_DIM` von 4096 auf 768 ändern (Zeile 24). In-Memory-Embedding-Cache (`vecCache`) wird bei nächstem Prozess-Restart neu geladen
- `scripts/setup_fts5.py` verifizieren (FTS5-Tabelle ist embedding-unabhängig, sollte nicht betroffen sein)

Tag 7: Cut-over (Samstag empfohlen)

- Backup-Snapshot verifizieren
- `INFERENCE_BACKEND=llamacpp` in `.env` setzen
- systemd-Services starten, `python -m pipeline.run_full_cycle --dry-run`
- Manueller Smoke-Run mit `--batch 50`
- Wenn sauber: produktiver Nacht-Cycle
- Ollama bleibt installiert — Rollback via `INFERENCE_BACKEND=ollama` + Embedding-Restore

Tag 8: Stabilisierung + Cleanup

- Erste drei nightly Cycles monitoren
- `migration_to_llamacpp.md` aktualisieren: Pfade, Service-Namen, VRAM-Tabelle auf RTX 3090 / Ubuntu anpassen (H2)
- `pipeline/ollama_client.py` als deprecated markieren, nicht löschen (H1)
- Erfolgskriterium Migration: drei aufeinanderfolgende Cycles ohne Fehler, GPU-Check 100 %, structured-output Failure-Rate < 1 %

---

**D1 — Code-Review A–H (Architekt, 14 Tage, parallel zu D2)**

Pro Punkt ein Abschnitt in `docs/architecture-review-2026-05/01-code-review.md`: aktueller Zustand mit Datei/Zeile, Fix-Vorschlag, Aufwandsschätzung, Risiken.

A1 — Stage 8 Reclassify erweitern (2 Tage)

- `pipeline/reclassify.py` erweitern: neben `primary_vertical`/`verticals[]` auch `mega_trend` re-assignen
- Gleicher Prompt-Ansatz wie `pipeline/mega_trend_reviewer.py`, aber im Reclassify-Kontext (einzelne Items statt Batches)
- Few-Shot-Beispiele für die häufigsten Fehlerklassen (Sport→HEALTH statt LIFESTYLE, Halbleiter→clean_energy statt TECH, etc.)
- `scripts/audit_classification.py` als Vor/Nach-Diff-Tool
- Hinweis: teilweise durch Modell-Upgrade (D2) entschärft — 80B klassifiziert initial besser, Reclassify-Stage wird zum Auffangnetz statt zum Hauptkorrektor

A2 — mega_trend null-Guard (0.5 Tage)

- `pipeline/auto_publisher.py`: `mega_trend IS NOT NULL` als Hard-Constraint für Auto-Publish
- Items mit `mega_trend = null` bleiben als `draft` für manuellen Review via `scripts/review_cli.py`
- Einzeiler-Fix, minimales Risiko

A3 — "53 skipped" Hard-Limit lokalisieren (0.5 Tage)

- Vermutlich `LIMIT` oder Threshold-Bucket in `pipeline/auto_publisher.py` oder `pipeline/llm_processor.py`
- Bug lokalisieren, beheben oder als bewusstes Throttling dokumentieren
- Falls Throttling: konfigurierbar über `.env` (`AUTO_PUBLISH_BATCH_LIMIT`)

B1 — Score-Kalibrierung (2 Tage)

- `pipeline/crs.py` Verteilungsanalyse: Histogram über alle 23.808 published Trends, Percentile-Cuts
- Problem: feste Mappings (`cross_map`, `pestel_map`) erzeugen Bandbegrenzung bei typischem Profil (1 Vertical, 2 PESTEL, trade_media, confidence ~0.85 → immer 0.79–0.85)
- Score-Komponenten neu kalibrieren — Zielverteilung: P75 ≥ 0.90, Median ~0.75, P95-P5-Spread ≥ 0.30
- Optionen: logarithmische Skalierung statt Stufen-Maps, oder Normalisierung gegen Korpus-Verteilung
- `scripts/backfill_crs.py` nach Neukalibrierung erneut ausführen

C1 — mega_trend_reviewer Integration (1 Tag)

- `pipeline/mega_trend_reviewer.py` ist nicht Teil von `pipeline/run_full_cycle.py`
- Als wöchentlichen Job integrieren (Sonntag nach Nightly-Cycle) oder Frequenz auf pro Cycle erhöhen für published-Trends der letzten 24h
- `deploy/crontab.txt` aktualisieren

C2 — verticals[] im Frontend nutzen (1.5 Tage)

- `frontend/src/lib/db.ts`: Filterung von `primary_vertical = ?` auf `EXISTS (SELECT 1 FROM json_each(t.verticals) WHERE json_each.value = ?)` umstellen
- Neuer "Cross-Industry"-Tab für Trends mit `json_array_length(t.verticals) >= 2`
- Performance-Impakt verifizieren (json_each + Index auf published)

D1 — Anti-Pattern-Prompt für Stage 6 (1 Tag)

- `pipeline/llm_processor.py`: `CONTENT_EN_SYSTEM` erweitern um explizite Verbotsliste: "Avoid generic openings such as 'The Rise of', 'Signals', 'A Shift Toward', 'Redefining'. Lead with the substantive claim or actor."
- Few-Shot-Beispiele aus echten Trendwatching-Artikeln (3–5 gute Beispiele, 3–5 schlechte)
- Hinweis: nach Modell-Upgrade (D2) erneut evaluieren — 80B produziert vermutlich diverseren Output, aber Anti-Pattern-Guidance bleibt sinnvoll

E1 — Geographisches Tagging (2 Tage)

- `pipeline/models.py:ClassificationResult`: `regions` Field von Freitext auf ISO-3166-1-alpha-2 Codes umstellen (Validator)
- Geographisches Tagging als explizite Sub-Anweisung im Classification-Prompt (`pipeline/llm_processor.py:_CLASSIFICATION_SYSTEM_TEMPLATE`)
- Frontend: Region-Filter in FilterBar (`frontend/src/components/filters/`)

F1 — HNSW-Index für Embedding-Dedup (3 Tage)

- `pipeline/llm_processor.py:step_dedup_check` / Stage 5 Batch-Code: linearen Cosinus-Vergleich ersetzen durch HNSW-Index
- Optionen: `hnswlib` (Pure Python/C++, leichtgewichtig), `faiss` (mächtiger, mehr Abhängigkeiten), oder SQLite-vec (wenn es die DB nicht verlässt)
- Empfehlung: `hnswlib` — persistenter Index in `data/dedup_index.bin`, wird bei Pipeline-Start geladen, nach Stage 5 aktualisiert
- Throughput-Tests bei 10k / 25k / 50k Korpus-Größe dokumentieren
- Hinweis: nach Re-Embedding (D2) muss der Index komplett neu aufgebaut werden (Dimension wechselt)

G1 — Quellen-Bias → siehe D4

H1–H4 — Migrations-Touchpoints → werden durch D2 abgedeckt

---

### Woche 3: A/B-Studie + Quellen-Diversifizierung (parallel)

**D3 — A/B-Studie Qwen3-Next-80B vs qwen3:14b (3 Tage)**

Voraussetzung: D2 Cut-over abgeschlossen.

Tag 1: Benchmark-Setup

- 30 raw_entries als festes Sample (Stichprobe über alle 8 Verticals, Mix aus signal_types)
- Gleiche Entries durch beide Pipelines:
  - Pfad A: Ollama + qwen3:14b (bestehende `content_en_json`-Cache nutzen wenn vorhanden)
  - Pfad B: llama.cpp + Qwen3-Next-80B (frisch generiert)
- Output in `data/ab_study_stage6.json`
- Latenz/Throughput-Vergleich: Wall-Clock pro Item, Gesamt-Batch-Zeit

Tag 2: Blind-Rating durch Trendforscher

- 30 Paare randomisiert, Zuordnung verdeckt
- Rating auf drei Kriterien (je 1–5 Skala):
  1. Aussagespezifität: konkrete Akteure/Zahlen/Konsequenzen statt Floskeln
  2. Cross-Vertical-Referenzen: werden Verbindungen explizit gemacht
  3. Mega-Trend-Konsistenz: passt der Text zur zugewiesenen Mega-Trend-Klassifikation
- Zusätzlich: binäres Rating "könnte das ein Trendwatching-Artikel sein?"

Tag 3: Auswertung + Entscheidung

- Statistische Auswertung: Mittelwerte, Standardabweichung, Wilcoxon-Test auf die drei Kriterien
- Wenn 80B signifikant besser: Migration bestätigt, weiter mit Plan
- Wenn 80B nicht besser: dokumentieren warum trotzdem migriert wird (Latenz, Kontrolle, VRAM-Effizienz) — oder Stop und Rückfall auf Qwen3.6-35B-A3B als Kompromiss
- Output: `docs/architecture-review-2026-05/03-ab-study.md`

---

**D4 — Quellen-Diversifizierungsplan (Trendforscher Lead, 4 Tage)**

Tag 1–2: Newsletter-Liste + Quality-Gates

- Priorisierte Liste von 15–25 Newslettern, gruppiert nach Vertical und Quellentyp:
  - Trendforschung: Trendwatching, Sparks & Honey, WGSN (wo frei zugänglich)
  - Branchen-News: Food Dive, Retail Dive, Modern Retail, BoF (Newsletter-Varianten)
  - Consumer-Behavior: McKinsey, BCG, Deloitte Insights
- Quality-Gates: jeder Newsletter wird vor Aufnahme manuell gegen ein 5-Item-Sample bewertet (Signal-Density, Originalität, Lead-Time). Schwache Quellen rauswerfen bevor sie in die DB kommen
- Output: `docs/architecture-review-2026-05/04-source-diversification.md`

Tag 3–4: IMAP-Ingest-Architektur

- `pipeline/newsletter_poller.py` analog zu `pipeline/feed_poller.py`:
  - Lesender IMAP-Zugriff, idempotent (UID-Tracking in DB)
  - Mehrteil-MIME-Parsing, HTML→Text via BeautifulSoup, Inline-Link-Extraktion
  - Authentifizierung über App-Password in `.env` (`IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD`), nicht im Code
  - Output: `raw_entries` mit `source_type = 'newsletter'`
- Bestehende LLM-Pipeline läuft unverändert weiter — Newsletter-Entries sind aus Sicht der Pipeline normale raw_entries
- Dedup zwischen RSS und Newsletter: Stage 5 Embedding-Dedup deckt exakte Duplikate ab, aber für partielle Overlaps (Newsletter zitiert RSS-Artikel) Audit-Script schreiben
- Roll-out-Plan: Tranche 1 (5 Newsletter, erste Woche), Evaluation, Tranche 2 (weitere 10)

---

### Woche 4: Synthese-Layer

**D5 — Synthese-Layer-Konzept (6 Tage)**

Voraussetzung: D1-F1 (HNSW-Index) abgeschlossen.

Tag 1–2: Cluster-Detection

- Neuer Pipeline-Schritt `pipeline/cluster_detector.py`, läuft nach Stage 9, wöchentlich oder pro Cycle
- Methodik:
  1. HNSW-Nearest-Neighbor über alle published Trends der letzten 30 Tage (nutzt den in F1 aufgebauten Index)
  2. Verbindungs-Graph aufbauen (Kanten = Similarity > Threshold)
  3. Community-Detection via Leiden oder Louvain (Python: `leidenalg` oder `networkx`)
  4. Cluster mit ≥ 3 Items + Cross-Vertical-Score (≥ 2 verschiedene primary_verticals) → als "emerging convergence" markieren
- Output in bestehende `trend_clusters`-Tabelle (Schema existiert bereits in `pipeline/db.py`)
- Datenmodell-Erweiterung: `trend_clusters.verticals`, `trend_clusters.trend_ids` sind bereits JSON-Felder

Tag 3: Weak-Signal-Heuristik

- SQL-Heuristik, kein LLM nötig:
  - Item ist Weak Signal wenn:
    - `signal_count` für sein Mega-Trend < Median des Mega-Trends, UND
    - `trend_signal_type` IN ('regulation', 'research'), UND
    - mindestens ein konkreter Akteur benannt (Brand, Company, oder Region nicht leer)
  - Implementierung als View oder materialisierte Tabelle `weak_signals` (ID, trend_id, reason, detected_at)
- Schwellenwerte mit Trendforscher abstimmen

Tag 4–5: Frontend-Routen

- `/trends/clusters/[id]` — existiert teilweise (`frontend/src/app/trends/clusters/page.tsx`), aber zeigt aktuell Mega-Trend-Aggregation, nicht echte Cluster. Umbauen auf `trend_clusters`-Tabelle
- `/trends/weak-signals` — neue Route, Listing mit Drill-down
- API-Endpoints: `GET /api/clusters`, `GET /api/weak-signals`

Tag 6: Integration in Pipeline

- `pipeline/run_full_cycle.py`: Cluster-Detection als optionalen Step nach Stage 9 aufrufen (Flag `--with-clusters`)
- Alternativ: separater Cron-Job (wöchentlich Sonntag)

---

### Woche 5: Quality-Metrics

**D6 — Quality-Metrics-Framework (7 Tage)**

Tag 1: Klassifikations-Stabilität

- 100 zufällige published Items zweimal durch Stage 4 (Classification) laufen lassen
- Agreement-Rate messen: wie oft kommt dasselbe `mega_trend` raus?
- Zielwert: ≥ 85 % Übereinstimmung (nach Modell-Upgrade)

Tag 2: Inter-Annotator-Agreement (Proxy)

- 100 zufällige Items durch zwei Modelle klassifizieren lassen:
  - Qwen3-Next-80B (produktiv) vs. Qwen3.6-35B-A3B oder qwen3:8b (als Kontrollmodell)
  - Cohen's Kappa auf `mega_trend`-Feld berechnen
- Zielwert: Kappa ≥ 0.65 (substantial agreement)

Tag 3–4: Externe Validierung (Trendforscher)

- 50 Items des letzten Monats händisch durch Trendforscher gegen Pipeline-Klassifikation raten
- Pro Item: ist `mega_trend` korrekt? Ist `primary_vertical` korrekt? Ist die Content-Qualität akzeptabel?
- Cohen's Kappa als KPI für mega_trend-Korrektheit
- Zielwert: Kappa ≥ 0.75 (≈ ≥ 90 % Agreement bei ausbalancierter Verteilung)

Tag 5: Lead-Time-Validierung

- Für Items mit `lead_time_tier = 'leading'` (future-Quellen): kommen tatsächlich Folge-Signale in market/now-Quellen innerhalb von 3 Monaten?
- SQL-basierte Analyse: Items aus future-Quellen, Embedding-Similarity > 0.7 zu späteren Items aus market/now-Quellen
- Explorative Analyse, kein festes Zielwert — dokumentieren was die Daten zeigen

Tag 6–7: Dashboard oder Report

- Option A: React-Dashboard (neue Route `/trends/admin/metrics`) — höherer Aufwand, schönere Darstellung
- Option B: Wöchentlicher Markdown-Report via Script (`scripts/quality_report.py`) — pragmatischer, weniger Wartung
- Empfehlung: Option B starten, Dashboard später als separates Feature
- KPIs auf einen Blick: Klassifikations-Stabilität, Inter-Annotator Kappa, externe Validierung, Score-Spread (P95-P5), Cycle-Zeiten, Fehlerrate
- Schwellenwerte definieren (Trendforscher + Architekt gemeinsam):
  - mega_trend-Korrektheit ≥ 90 %
  - Score-Spread (P95-P5) ≥ 0.30
  - Structured-Output Failure-Rate < 1 %
  - nightly Cycle-Erfolgsrate ≥ 95 %

---

### Woche 6: TRL-Roadmap + Abschluss

**D7 — TRL-Roadmap (2 Tage)**

Synthese aller vorherigen Deliverables in ein 2-Seiten-Dokument: `docs/architecture-review-2026-05/07-trl-roadmap.md`

Inhalt:

- TRL 6 → 7: Kriterien, erledigte Arbeiten, messbare Ergebnisse (Verweise auf D1–D6)
- TRL 7 → 8: verbleibende Kriterien (externe Validierung durch Industriekunden/Foresight-Studio), offene Arbeiten, geschätzter Aufwand
- Risiken und Abhängigkeiten für TRL 8

---

## 3. Risiko-Register

| # | Risiko                                                     | Wahrscheinlichkeit | Impact | Mitigation                                                                                                       |
|---|------------------------------------------------------------|--------------------|--------|------------------------------------------------------------------------------------------------------------------|
| 1 | Structured-Output Failure-Rate bei llama.cpp > 1 %         | mittel             | hoch   | GBNF-Grammar als Fallback, 200-Item-Schatten-Lauf vor Cut-over                                                   |
| 2 | Embedding-Wechsel (4096→768) verschlechtert Dedup-Qualität | mittel             | mittel | 100+100 kuratierte Paare, ROC-Kalibrierung, Threshold-Anpassung                                                 |
| 3 | Stage-2 Filter wird mit 80B zu aggressiv                   | mittel             | mittel | RELEVANCE_THRESHOLD in config.py anpassbar, Monitoring der Filter-Rate über erste 3 Cycles                       |
| 4 | VRAM-Konkurrenz mit fcc-Stack                              | niedrig            | hoch   | scheduled_cycle.sh stoppt/startet Services bereits, Reihenfolge beibehalten                                      |
| 5 | F1 HNSW-Migration blockiert D5 Cluster-Detection           | mittel             | mittel | Cluster-Detection kann initial auf brute-force laufen (langsam aber funktional), HNSW als Performance-Upgrade    |
| 6 | A/B-Studie zeigt keinen signifikanten Qualitätsgewinn      | niedrig            | mittel | Migration wird trotzdem durchgeführt (Latenz, Kontrolle, VRAM), aber Content-Prompt-Tuning wird höher priorisiert |
| 7 | Rollback nach Cut-over nötig                               | niedrig            | hoch   | INFERENCE_BACKEND env-flip, embedding_legacy-Spalte oder Snapshot, Ollama bleibt installiert                     |

---

## 4. Operatives

- **Branch-Strategie:** Ein Branch pro Deliverable (`arch/01-code-review`, `arch/02-migration`, etc.), Merge in `main` via PR
- **Stand-up:** Mittwoch, 30 min, Status zu allen offenen PRs + nächste Schritte
- **Nightly Pipeline:** Läuft weiter wie bisher. Refactorings nicht in den nightly Cycle integrieren bevor sie auf einem Schatten-Lauf grün sind
- **Backups:** Vor jeder DB-Mutation (Re-Embedding, Reclassify, Cluster-Insertion): `scripts/backup_db.py --dest ...` verifizieren. Backup-Cron läuft täglich 00:05
- **Cut-over-Fenster:** Samstag früh, Backup-Snapshot direkt davor, Wiederherstellungs-Test direkt danach
- **Rollback-Pfad:** `INFERENCE_BACKEND=ollama` als env-flip. Voraussetzung: Embedding-Spalte hat Kopie der 4096-dim BLOBs (als `embedding_legacy` Spalte oder als DB-Snapshot)

---

## 5. Was dieser Plan NICHT umfasst

- Frontend-Redesign (eigene Story, siehe `frontend/DESIGN_REVAMP.md`)
- Modell-Fine-Tuning (bleiben bei pre-trained, bessere Prompts)
- Cloud-Deployment (lokal first)
- Mehrsprachigkeit (DE-Pipeline bleibt deaktiviert)
- Neue Verticals jenseits der bestehenden acht
- Google Trends Integration (siehe `BACKLOG.md`, separates Feature)
- Foresight-Search-Workbench Ausbau (siehe `BACKLOG.md`)

---

## 6. Deliverable-Artefakte

Alle Markdown-Dokumente unter `docs/architecture-review-2026-05/`:

```
docs/architecture-review-2026-05/
├── 01-code-review.md           # D1: Pro Punkt A–H
├── 02-migration-report.md      # D2: Cut-over-Plan, Schatten-Lauf, Rollback
├── 03-ab-study.md              # D3: 30-Item-Vergleich, Ratings, Entscheidung
├── 04-source-diversification.md # D4: Newsletter-Liste, IMAP-Architektur
├── 05-synthesis-layer.md       # D5: Cluster-Detection, Weak-Signal
├── 06-quality-metrics.md       # D6: KPI-Definitionen, Schwellenwerte
└── 07-trl-roadmap.md           # D7: 6→7→8 auf 2 Seiten
```

Code-Änderungen als separate PRs gegen `main`:

```
pipeline/llamacpp_client.py          # D2: neuer Inferenz-Client
pipeline/cluster_detector.py         # D5: Cluster-Detection
scripts/reembed_all_trends.py        # D2: Re-Embedding
scripts/audit_classification.py      # D1-A1: Vor/Nach-Diff
scripts/quality_report.py            # D6: Wöchentlicher KPI-Report
```
