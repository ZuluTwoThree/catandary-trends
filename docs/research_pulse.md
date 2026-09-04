# Research Pulse (#73 Teil 1) — Datenlage, Methode, Betrieb

Stand 2026-09-04. Code: `pipeline/research_pulse.py` (Kern), `scripts/research_pulse.py`
(CLI), `scripts/migrate_research_pulse.py` (Tabelle), Frontend
`/trends/foresight/research/pulse` (+ `/[theme]`), Wrapper `scripts/weekly_research_pulse.sh`.

## 1. Datenlage (geprüft 2026-09-04)

- **Wo liegen die frischen Forschungssignale?** In `research_signals` (Research-Explorer-Index,
  Voll-Rebuild durch `scripts/build_research_index.py` am Ende von `weekly_ingesters.sh`,
  Samstag 06:00). 545.399 Zeilen; `published` = Publikationsdatum des Papers (nicht Ingest-Datum),
  Maximum 2026-08-29 = letzter Samstagslauf. Letzte 14 Tage: **17.317** Zeilen (35 Tage: 58.915).
  Quellen der 14 Tage: `OpenAlex fresh: <Konzept>` (zitationsfreier Wochen-Sweep, ~65 %),
  `arXiv Preprints` 2.263, `medrxiv Preprints` 492, `biorxiv Preprints` 349, dazu Journal-/Presse-
  Feeds (Trends in Food Science & Technology, Trends in Biotechnology, …).
- **Theme-Zuordnung:** `research_signals.mega_trend` (aus `trends.mega_trend`, Distill-Head im
  Samstagslauf). 22 der 28 Themes tragen in 14 Tagen Signale; 6 sind praktisch leer
  (Platformization of Culture, Experience Economy, Cultural Heritage, Virtual Worlds, Orbital
  Economy, Evolution of Work). ~7 % der frischen Zeilen haben kein Theme (`mega_trend` NULL,
  Abstain) — sie fließen in keinen Pulse. `concept` = OpenAlex-Konzept bzw. arXiv-Kategorie
  aus dem Routing-Präfix des Excerpts.
- **Embeddings:** ja, vollständig. Der Join `research_signals → trends` liefert für **20.084 von
  20.084** Zeilen der letzten 14 Tage sowohl `embedding` (4096) als auch `embedding_1024`
  (1024, HNSW-indiziert). Der Pulse nutzt `embedding_1024` (klein genug für den Transfer, gleiche
  Distill-Basis wie die Klassifikation). Daher **KMeans auf Embeddings**, keine Konzept-Gruppen;
  das Konzept bleibt sekundäres Cluster-Label.
- **OA-Status:** liegt für OpenAlex-Fresh-Werke nicht vor (der Fresh-Ingest speichert keinen
  `is_oa`; `research_work_oa` ist nach OpenAlex-Work-ID geschlüsselt, die frischen URLs sind
  DOIs/arXiv-Links → 0 Treffer). OA-Badge deshalb nur für Preprint-Server (arXiv/bioRxiv/medRxiv
  = per Definition Open Access). Ehrlich gelabelt („open-access preprints").
- **Nebenbefund (nicht in diesem Paket gefixt):** `build_research_index.py` kopiert beim
  Rebuild mit `CREATE TABLE … (LIKE research_signals INCLUDING ALL)` alle bestehenden Indizes und
  legt drei neue an — die Tabelle trägt inzwischen 6 Sätze identischer Indizes
  (`research_signals_new_*_idx1…10`). Kostet Rebuild-Zeit und Platz, keine Fehlfunktion.
  Fix wäre `INCLUDING DEFAULTS` + `ADD PRIMARY KEY` statt `INCLUDING ALL` (nächster Rebuild räumt
  dann auf); als Punkt im Issue vermerkt.

## 2. Methode (deterministische Datenbasis, generierter Text)

Je Theme und ISO-Woche (Montag–Sonntag, Default = letzte abgeschlossene Woche, Regel wie der
Newsletter-Cron: `%G/%V` von vor 7 Tagen):

1. **Volumen:** Papers der Woche (nach `published`) vs. **Median der vier Vorwochen** →
   `ratio` (z. B. 1.09 = +9 %). Median statt Mittel, weil einzelne Wochen Batch-Ausreißer
   haben (W33 = 4.480 Zeilen bei sonst ~15.000: Ingest-Lücke). `ratio` NULL bei Median 0.
2. **Cluster:** L2-normierte `embedding_1024` der Wochen-Papers, **KMeans** mit
   `random_state=73`, `n_init=10`; `k = min(5, n // 8)`, unter 8 Papers ein Block. Eingabe
   sortiert nach `trend_id` → gleiche Daten, gleiche Cluster.
   - **Label:** c-TF-IDF (TfidfVectorizer über Titel×2 + Abstract[:400], Bigrams, sklearn-
     Stoppwörter + generische Wissenschaftssprache, Elsevier-RSS-Boilerplate
     „Publication date/Source/Author(s)" entfernt) → Top-3-Terme, plus die häufigsten
     `concept`-Werte des Clusters.
   - **Top-Papers:** die 4 zentroid-nächsten (Kosinus) je Cluster, mit Titel, Quelle, Datum,
     Link, OA-Badge, Similarity.
   - **Wachstum/emergent:** Vorwochen-Papers desselben Themes werden **in SQL per
     Nächster-Zentroid** (`pgvector <=>`, `CROSS JOIN LATERAL … LIMIT 1`) den Zentroiden
     zugeordnet; `growth = n_week / (prior_n / 4)`; `emerging = n ≥ 5 ∧ growth ≥ 1.5`
     (oder keine Vorwochen-Papers). Bekannter Effekt: ein Journal-Batch (z. B. 284
     „Trends in Food Science & Technology"-Zeilen in einer Woche) erscheint als „emerging
     ×22.7" — das ist die Datenrealität, die Seite weist im Fußtext darauf hin.
3. **Text:** Gemma-4-26B (llama.cpp, `RESEARCH_PULSE_MODEL`), `temperature 0.2`, `seed 73`,
   `max_tokens 420`, System-Prompt „nüchtern, nur die Zahlen aus dem Datenblock, keine
   Prognosen/Empfehlungen, ein Absatz ohne Markdown". Wortwächter 80–190 Wörter: ein zweiter
   Versuch mit `seed 74`, danach wird der letzte Text mit Notiz übernommen. Kein Text unter 5
   Papers (`MIN_PAPERS_FOR_TEXT`). Reproduzierbar per Seed, soweit llama.cpp deterministisch
   ist (Batch-Komposition kann Float-Reduktionen verschieben).
4. **Speichern:** Tabelle `research_pulse` (additiv, `scripts/migrate_research_pulse.py`;
   `ensure_schema` läuft auch vor jedem CLI-Lauf): `theme, year, week, week_start,
   computed_at, stats JSONB, clusters JSONB, text, model, seconds, note`. **Versioniert** —
   jeder Lauf ist eine neue Zeile; die Seiten lesen je (theme, year, week) die jüngste.
   `data/research_pulse_last.json` (finished_at, themes, with_text, errors, status) für den
   Wächter.

## 3. Testlauf 2026-09-04 (Woche 2026-W35, 24.–30.08.)

- `--no-llm`, alle 28 Themes: **14 s** (CPU/SQL; AI 5.084 Papers 4,7 s, Health 3.407 3,1 s,
  Rest < 2 s). 22 Themes mit Clustern, 6 leer.
- Mit Gemma, 5 Themes (AI, Quantum, Food, Clean Energy, Education): **28 s** gesamt,
  davon ~12 s Modell-Load, ~2 s je Text; Texte 126–134 Wörter, alle im Wächterfenster.
  Beispiel (Quantum): „Research volume for the week of 2026-08-24 to 2026-08-30 totaled 82
  papers, representing a 35% decrease compared to the prior four-week median of 127.0. …"
- Ruhezustand danach: `start-active.sh → start-qwen3-8b-208k.sh`, `llama-server` inactive
  (wie vor dem Lauf), 172 MiB VRAM.

## 4. Betrieb

- **Knopf:** `/trends/foresight/research/pulse/<theme>` → „Recompute" (Server Action,
  Owner-Modus + Same-Origin-Check, spawnt `scripts/research_pulse.py --themes <key> --week …`
  detached; Lock `data/research_pulse.lock`, Log `data/research_pulse/<stamp>.log`).
- **Cron-Vorschlag** (auskommentiert in `deploy/crontab.txt`, nicht installiert):
  `0 12 * * 6 scripts/weekly_research_pulse.sh` — Samstag nach dem Ingester (Ende zuletzt
  08:13), Kollisionswächter (Ingester/Dossier-Worker/Cycle, max 90 min), idempotent
  (Woche mit ≥ 20 Texten = no-op). Owner entscheidet Cron vs. Knopf; die Newsletter-Edition ist
  der Präzedenzfall für Cron.
- **Flags:** `--week 2026-W35`, `--themes a,b`, `--no-llm`, `--limit N` (die N
  volumenstärksten), `-v`.
- **Explorer-Facetten** (Signal-Schicht): `?src=arxiv,biorxiv,medrxiv,openalex,journals`,
  `?range=7d|30d|90d|1y`, `?sort=relevance|date` (Relevanz nur mit `q`), `?concept=…`
  (Konzept-Badges), `?layer=signals` (Textsuche auf der Signal-Schicht statt 45M-Korpus).
  Deep-Links: `/trends/mega/<theme>` → Explorer `?theme=` + Pulse (nur Owner-Modus, Foresight
  ist nicht im Export).

## 5. Nicht in diesem Paket

Autoren-Enrichment, Sprach-Kennzeichnung (#73 Teil 2, separat), Wächter-Verdrahtung des
Pulse in `cycle_watchdog.py` (erst mit installiertem Cron sinnvoll), Index-Duplikate in
`build_research_index.py` (s. o.).
