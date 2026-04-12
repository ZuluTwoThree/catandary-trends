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

## Pipeline-Orchestrierung (Cron)

- [ ] **`pipeline/run_full_cycle.py` — Orchestrator-Script für den Hauptzyklus.** Fasst Feed-Poll + LLM-Pipeline in einen sequentiellen Lauf zusammen. Ersetzt die separaten Cron-Einträge für `feed_poller` und `llm_processor`.
  - **Ablauf:** (1) Ollama-Health-Check → (2) Feed Poll alle Verticals → (3) LLM Pipeline Batch N → (4) Summary Report (neue Entries, published, Fehler, Dauer) → Exit Code 0/1
  - **Flags:** `--skip-poll` (nur LLM), `--skip-llm` (nur Poll), `--batch N` (default 200), `--dry-run`
  - **Logging:** Zentrales Log pro Zyklus, optional Append in `data/cycle_log.jsonl` für Monitoring
  - **Vorteile:** Garantiert sequentiell (kein DB-Lock), Ollama-Check vor teurem LLM-Lauf, ein Cron statt zwei
  - **Nicht enthalten:** Mega-Trend-Reviewer (monatlich, eigener Cron), Newsletter (wöchentlich, eigener Cron), Radar (täglich, eigener Cron)
  - **Crontab-Ziel:**
    ```
    30 */4 * * *   python -m pipeline.run_full_cycle --batch 200
    0 3 1 * *      python -m pipeline.mega_trend_reviewer
    # 0 9 * * 1    python -m pipeline.newsletter_generator  (wenn Versand fertig)
    ```
  - **Bestehendes `deploy/crontab.txt` danach aktualisieren** (aktuell veraltet: Trendhunter-Referenz, auto_publisher als eigener Cron — beides inzwischen in die LLM-Pipeline integriert)

## Tagesziele 2026-04-11

- [x] ~~**Cron-Jobs einrichten.**~~ Plan erstellt, siehe "Pipeline-Orchestrierung" oben. Umsetzung als eigenes Feature.
- [ ] **Newsletter implementieren.** Newsletter-Generator (`pipeline/newsletter_generator.py`) fertigstellen und testen. Anbindung an Resend/Buttondown, wöchentlicher Versand (Montag 9:00).
- [x] ~~**Plattform auf MacBook Air testen.**~~ Erledigt 2026-04-12, siehe `MACBOOK_SETUP.md`.
