# Frontend-Plan: Foresight-Visualisierungen auf dem Signal-Space

**Stand:** 2026-07-02 · **Issue:** [#3](https://github.com/ZuluTwoThree/catandary-trends/issues/3) · **Ziel:** vermarktungsfähige Foresight-Engine — die Visualisierungen müssen den echten Datenbestand tragen, nicht nur den Artikel-Layer.

## 1. Audit-Befund: Frontend vs. Datenbank

| Ebene | Datenbank (Ist) | Frontend (Ist) |
|---|---|---|
| Raw Entries | **768.060** | — (korrekt unsichtbar) |
| Embedded Trends | **455.600** (404.567 `signal` + 47.030 `published` + 3.872 `draft`) | nur `status='published'` (47k) — **~10 % des Korpus** |
| Patent-Graph | 74.534 Patente, 495.057 Zitationskanten, `patent_cpc` | nicht angebunden |
| Funding-Pool | 35.227 Awards (NSF/NIH/OpenAIRE/UKRI) mit Geo/Betrag | nicht angebunden |
| Cluster/Trajektorien | nur als CLI (`cluster_trajectory_demo.py`, `propose_mega_trends.py`); `trend_clusters`-Tabelle ungenutzt | keine Cluster-Ansicht mit echten Clustern |
| Zeitachse | Signale 2002–2026 (Mehrjahres-Backfill) | Card-Grid zeigt de facto die letzten Wochen |

**Konkrete technische Blocker:**

1. **Hardcodiertes `status='published'`** in `frontend/src/lib/db.ts` und `frontend/src/app/api/search/route.ts` — der Signal-Space ist für alle Ansichten inkl. Foresight-Cockpit unsichtbar.
2. **Embedding-Suche skaliert nicht:** `api/search` lädt alle published-Embeddings in einen Modul-Cache (47k × 16 KB ≈ **770 MB** RAM) und macht Brute-Force-Cosine in JS. Auf 455k Signale wären das ~7,5 GB — unmöglich. → ANN-Index nötig.
3. **Keine persistierten Foresight-Artefakte:** Cluster, Trajektorien, Momentum und Lead-Time-Verteilungen werden nirgends in die DB geschrieben; das Frontend hätte nichts zum Rendern. Die Mega-Trend-Karten zeigen kuratierte YAML-Metadaten (`momentum`, `cluster_strength`), nicht datengetriebene Werte.
4. **Live-Aggregation über 455k Zeilen** (Timeline, SoV, Tier-Breakdown) ist in einem Next.js-Request-Handler nicht sinnvoll — die Analytik muss vorberechnet werden.

**Kernprinzip des Plans:** *Der Batch-Layer rechnet, das Frontend liest.* Alle teuren Analysen (Clustering, Trajektorien, SoV, Lead-Time) laufen als Pipeline-Jobs und persistieren kompakte Artefakte; das Frontend rendert ausschließlich vorberechnete Tabellen/JSON. Das hält den Hetzner-VPS klein und macht die Ansichten schnell.

## 2. Phase 0 — Fundament: Signal-Space-Daten fürs Frontend (Voraussetzung für alles)

**0.1 Foresight-Artefakt-Tabellen (Batch-Job schreibt, Frontend liest):**

```sql
-- Ein Lauf der Cluster-Engine (pro Scope: global / vertical / tier)
CREATE TABLE foresight_runs (
    id INTEGER PRIMARY KEY,
    scope TEXT NOT NULL,             -- 'global' | 'vertical:FOOD' | 'tier:science' …
    k INTEGER, signals INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
-- Cluster eines Laufs (ersetzt/füllt die bislang ungenutzte trend_clusters)
CREATE TABLE foresight_clusters (
    id INTEGER PRIMARY KEY,
    run_id INTEGER REFERENCES foresight_runs(id),
    label TEXT,                      -- LLM- oder tag-abgeleitet
    size INTEGER, cohesion REAL,
    mega_trend TEXT, verticals TEXT, top_tags TEXT,       -- JSON
    momentum TEXT, sov_delta_pp REAL,                     -- rising/stable/declining
    n_sources INTEGER,                                    -- Korroboration
    rep_trend_ids TEXT,                                   -- JSON, 3-5 Repräsentanten
    monthly_series TEXT                                   -- JSON [{m:'2024-01',n:12,share:0.03},…]
);
```

Befüllt von einem neuen `pipeline/foresight_snapshot.py` (Kern aus `cluster_trajectory_demo.py`/`propose_mega_trends.py` extrahiert), Cron wöchentlich bzw. nach großen Ingests. Läuft auf der Workstation, nicht auf dem VPS.

**0.2 ANN-Suche statt In-Memory-Brute-Force:** Der 770-MB-Cache in `api/search` wird ersetzt durch einen der beiden Pfade (Entscheidung in Issue #8 mitgeführt):
- **Zielbild:** Postgres + pgvector (HNSW auf Matryoshka-truncated ≤2000 dims, Volldim-Re-Ranking der Top-K), oder
- **Brücke auf SQLite:** hnswlib-Index als Sidecar-Datei, vom Snapshot-Job gebaut, im Next.js-Prozess memory-mapped geladen (Index über *alle* 455k Signale ≈ 455k × 2000 × 4 B ≈ 3,6 GB → mit Truncation auf 512–1024 dims für die Suche: 0,9–1,8 GB; alternativ Suche als kleiner Python-Sidecar-Service auf :8091).

**0.3 API-Schnitt:** `GET /api/foresight/clusters?scope=…`, `GET /api/foresight/cluster/[id]`, `GET /api/foresight/timeline?scope=…` — alles reine Reads auf den Artefakt-Tabellen. Signale bleiben ohne öffentliche Detailseite (kein Artikel-Body vorhanden); Drill-down zeigt Titel + Quelle + Datum + Link zur Originalquelle.

## 3. Phase 1 — Cluster-Explorer (der erste sichtbare Foresight-Mehrwert)

Route: `/trends/foresight/clusters` (löst die statischen Mega-Trend-Karten von `/trends/clusters` ab bzw. speist sie).

- **Cluster-Übersicht pro Scope** (global + je Vertical): Karte je Cluster mit Größe, Kohäsion, Momentum-Pfeil (SoV-Δ), Quellen-Korroboration (n Quellen), Top-Tags, 1 Repräsentant-Titel. Sortierung nach SoV-Δ (steigende zuerst) — exakt die Ansicht, die `cluster_trajectory_demo.py --sov` heute im Terminal zeigt.
- **Monats-Sparkline** je Cluster aus `monthly_series` (SoV-normalisiert, nicht Roh-Counts — Quellen kamen über die Zeit hinzu).
- **Drill-down:** Cluster → Signal-Liste (Titel, Quelle, Datum, Vertical, Signal-Typ), Filter nach Zeitraum/Quelle.
- **Mega-Trend-Karten datengetrieben:** `momentum`/`cluster_strength`/„Seit <first_seen> · <n> Signale/30d" aus den Artefakten statt aus YAML-Handpflege (die YAML bleibt für Namen/Beschreibung — kuratierte Labels, gemessene Zahlen).
- **Free/Paid-Schnitt:** Übersicht + Top-3-Cluster frei; vollständige Liste, Drill-down und Momentum-Ranking hinter dem Foresight-CTA/Email-Gate (Lead-Capture-Strategie aus CLAUDE.md).

## 4. Phase 2 — Lead-Time- & Evolutions-Ansichten (das Differenzierungs-Feature)

Braucht die gescopten Discoverer-Läufe (Issue #2) als Artefakte (`scope='tier:…'`).

- **Lead-Time-Strom je Thema:** Für ein Cluster/Mega-Trend die Signal-Volumina getrennt nach Tier (Science/OpenAlex → Patent → Funding → Markt) als gestapelte Zeitreihe — „dieses Thema war 2022 in der Forschung dicht, erreicht 2025 den Markt". Das ist die Kern-Verkaufsgrafik der Foresight-Engine; kein Wettbewerber im Free-Bereich zeigt das.
- **Zeitfenster-Vergleich:** „Landschaft 2021 vs. 2024" — zwei Snapshot-Läufe nebeneinander, Cluster-Matching per Centroid-Ähnlichkeit; Emergenz- (neu im späten Fenster), Split-/Merge- und Decline-Badges aus dem Proposer-Output (NEW/SPLIT/MERGE/COVERED).
- **„Was ist neu in den letzten 6 Monaten":** NEW-Kandidaten des jüngsten Proposer-Laufs als Teaser-Widget auf der Foresight-Startseite.
- **Patent-/Funding-Einblendung:** im Cluster-Drill-down eigene Reiter „Patente" (aus `pub_number`-Signalen, mit Cycle-Time-Kennzahl der CPC-Domain aus `tir_graph`) und „Förderung" (Awards mit Land/Betrag → einfache Hotspot-Liste nach Jurisdiktion).

## 5. Phase 3 — Foresight-Workbench (Paid-Teaser, aus dem Search-Workbench-Konzept)

Ausbau des bestehenden Cockpits (`/trends/foresight`), jetzt auf dem Signal-Space:

- **Suche über alle Signale** (ANN aus Phase 0), Treffer-Timeline, Tier-Breakdown, Mega-Trend-Verortung — Analytik-Overlays nur bei n ≥ 30 Treffern („Zu wenige Signale für Trend-Analyse" darunter).
- **Saved Queries als Radar** (Watchlist, Email-Digest bei Velocity-Spikes; Mindest-Baseline ≥3 in der Vorperiode gegen Singleton-Alarme).
- **Co-Occurrence mit TF-IDF-Gewichtung** (83 % der Tags sind Singletons; Signal-Typ-Tags getrennt führen).
- **Export** (Markdown/CSV) pro Ergebnismenge — Analysten-Feature, klarer Paid-Anker.

## 6. Reihenfolge & Abhängigkeiten

| Schritt | Hängt an | Aufwand (grob) |
|---|---|---|
| 0.1 Artefakt-Tabellen + `foresight_snapshot.py` | Cluster-Kern existiert (CLI) | 2–3 Tage |
| 0.2 ANN-Suche | Entscheidung pgvector vs. hnswlib (Issue #8) | 2–4 Tage |
| 1 Cluster-Explorer | 0.1 | 3–5 Tage |
| 2 Lead-Time/Evolution | 0.1 + gescopte Discoverer (Issue #2) + Tier-Mapping | 1–2 Wochen |
| 3 Workbench | 0.2 | 1–2 Wochen, inkrementell |

**Sofort sinnvoll (Quick Wins, unabhängig):**
- ~~Mega-Trend-Karten „Seit/Signale"-Badge~~ — bereits umgesetzt (`getMegaTrends` liefert `first_seen`/`signals_30d`, `MegaTrendsPage.tsx` rendert beides); offen bleibt nur `momentum`/`cluster_strength` von YAML-Handpflege auf Messwerte umzustellen (Phase 1).
- Foresight-Cockpit-Zähler ehrlich machen: „47.030 kuratierte Artikel aus 455.600 analysierten Signalen" — die Korpusgröße ist selbst ein Trust-/Verkaufssignal und heute komplett unsichtbar.
- `trend_clusters`-Tabelle entweder durch `foresight_clusters` ersetzen oder entfernen (tote Struktur).

## 7. Nicht-Ziele

- Keine öffentlichen Detailseiten für rohe Signale (kein Content → SEO-Thin-Pages; Signale verlinken auf die Originalquelle).
- Keine Live-Clustering-Berechnung im Request-Pfad — alles über Snapshots.
- DE-Lokalisierung der neuen Ansichten erst nach Produkt-Validierung (EN-only, konsistent mit dem Content-Layer seit ~2026-06).
