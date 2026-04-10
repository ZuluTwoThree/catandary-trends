# Catandary Trends — Backlog

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

- [x] ~~**Mega-Trend-Reviewer Live-Run für heute published Trends.**~~ Erledigt 2026-04-09 über `scripts/review_recent_live.py`: 2678 Trends (gestern + heute) reviewed, 104 Mega-Trend-Updates, 61 min, 0 Fehler.

- [ ] **Hybrid-Suche (FTS5 + Embedding-Similarity) über Trends.** Ziel: User tippt z.B. "Getränke" und filtert innerhalb eines Verticals semantisch + lexikalisch. Infrastruktur: Alle 3908 Trends haben bereits qwen3-embedding-Vektoren (1024 Dim) als BLOB in `trends.embedding`.
  - **Plan:**
    1. SQLite FTS5 Virtual Table `trends_fts` über `title_de, summary_de, tags` + Trigger für Sync bei Insert/Update.
    2. Next.js API-Route `/api/search?q=...&vertical=FOOD&limit=20` (Prototyp: `frontend/src/app/api/search/route.ts`). Ruft Ollama `POST http://127.0.0.1:11434/api/embed` mit `qwen3-embedding` für Query-Embedding.
    3. In-Memory-Similarity: Trend-Embeddings einmalig beim Serverstart in `Float32Array` laden (~16 MB für 3908×1024), cosine gegen alle, Top-K (<50 ms). Invalidierung bei Poll-Cycle.
    4. Reciprocal Rank Fusion: FTS5-Resultate + Embedding-Resultate mergen (RRF mit k=60).
    5. Frontend: Suchfeld oben im Trends-Grid, debounced 300 ms, rendert `TrendCard` sortiert nach Score, Schwelle ~0.35 empirisch.
  - **Upgrade-Pfad:** bei >50k Trends oder komplexen Metadaten-Filtern → `sqlite-vec` Extension; später pgvector bei Postgres-Migration.
  - **Aufwand:** ~4-6h für Variante a + FTS5 inkl. UI. Prototyp der API-Route existiert unter `frontend/src/app/api/search/route.ts` (ohne FTS5, ohne Frontend-Anbindung).

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

- [ ] **Auto-Publish + Review in Pipeline integrieren.** Aktuell müssen `auto_publisher` und manuelles Review nach jedem LLM-Processor-Lauf separat angestoßen werden. Das ist fehleranfällig und blockiert den Workflow bei Nachtläufen. Lösung gesucht:
  - **Option A (einfach):** Am Ende von `llm_processor.py` automatisch `auto_publisher` aufrufen (als Python-Import, nicht Subprocess). Skipped Drafts in eine Datei/Log schreiben für späteres manuelles Review.
  - **Option B (Orchestrator):** Leichtgewichtiges Pipeline-Script `pipeline/run_full_cycle.py`, das Feed-Poll → LLM-Processor → Auto-Publish → Mega-Trend-Review sequentiell ausführt und einen Summary-Report schreibt. Passt gut zu Cron-Automatisierung.
  - **Option C (Cron-Kette):** Separate Cron-Jobs mit Zeitversatz (z.B. Poll 00:00, LLM 00:30, Auto-Publish 08:00, Review-Report per Mail).
  - Bevorzugt: **Option B** — ein einziger Cron-Eintrag, ein Report, keine Timing-Abhängigkeiten.
