# Tiefen-Backfill-Architektur — Embedding-Distillation + Lazy-Content

Für den Massen-Pull (Millionen Patente aus dem DOCDB-Back-File + OpenAlex-Works,
inkl. pre-2020) **ohne** pro Item 3 LLM-Calls. Gemessener Engpass: das 8B ist
output-generierungs-gebunden (~198 req/min Classification) → bei Millionen
unbezahlbar. **Lösung: LLM raus aus dem Ingest-Pfad.** Eager = Graph-Layer +
Embeddings + billige Klassifikator-Heads; LLM nur **lazy-on-query** + periodische
Discovery.

## Architektur — eager vs. lazy

| Stage | RSS-Quellen | **Patente / OpenAlex (Tiefen-Pull)** |
|---|---|---|
| Scope / Relevanz | Embedding-Klassifikator | **CPC- / Topic-Scoping beim Acquire** (GPU-frei) — *ist* der Relevanzfilter |
| Vertical | Embedding-Klassifikator | **CPC→Vertical / Topic→Vertical deterministisch** (GPU-frei) |
| Mega-Trend / PESTEL / Cross-Vertical | Embedding-Klassifikator | **Embedding-Klassifikator** |
| Embedding | eager, gebatcht | eager, gebatcht — **der einzige GPU-Schritt** |
| Extraction | lazy (NER/LLM on-demand) | lazy |
| Content-Gen | lazy per Query | lazy per Query |

→ Millionen Items kommen rein mit Vertical gratis (CPC/Topic), Relevanz gratis
(Scoping), Mega-Trend per billigem Klassifikator, **null LLM-Generierung beim
Ingest**. Das LLM feuert nur lazy bei Query-Request + periodisch zur Discovery.

## Klassifikation per Distillation (der Kern)

**Idee:** den LLM-Klassifikator in einen Embedding-Klassifikator destillieren —
trainiert auf den **bereits vorhandenen LLM-Labels**.

- **Trainingsdaten:** ~227k Signale (Embedding + Vertical/Mega-Trend/PESTEL) +
  hunderttausende `filtered_out` (= „nicht relevant"). Für Patente konkret die
  **74k via signal_batch LLM-klassifizierten Patente** (Embedding + Mega-Trend) als
  Quellentyp-spezifischer Trainingssatz. Für OpenAlex: kleiner LLM-gelabelter Seed
  → Klassifikator → auf die Millionen anwenden.
- **Heads** (auf dem 4096-dim Embedding):
  - *Relevanz:* binär, kalibriert (LogReg/MLP) — nur für RSS nötig; Patente/OpenAlex via Scoping.
  - *Vertical:* deterministisch (CPC/Topic) für Patente/OpenAlex; Klassifikator für RSS.
  - *Mega-Trend (21 Klassen):* Multiclass-Klassifikator oder kNN/Centroid-Nähe.
  - *PESTEL (Multi-Label):* Klassifikator.
- **Inferenz:** Vektor → Heads, µs/Item, voll batchbar. Ersetzt ~3 LLM-Calls.
- **Was NICHT geht:** Extraktion (brand/product/claims) — Embedding ist verlustbehaftet,
  konkreter Text nicht rekonstruierbar → bleibt lazy (NER/LLM auf Text).

## Lazy-Layer (Extraction + Content)

- **Extraction:** spaCy-NER auf dem Quelltext (brand/product) on-demand, oder LLM
  lazy — nur für angefragte/publizierte Signale.
- **Content-Gen:** lazy per Query über `ensure_embeddings(ids, cap, timeout)` +
  den **schon gefixten de-cliché Content-Gen-Pfad** (`step_generate_content_en`,
  committed). Artikel entsteht beim ersten Request, mit Floskel-Guard.
- **Guards** (aus dem Lazy-Embedding-Item): Knoten-Cap pro Query, Wall-Clock-Timeout,
  Prefilter-zuerst (CPC/Topic/Citations/Datum als SQL), GPU-idle-Gate, Persistenz.

## Discovery-Loop (gegen die bounded Taxonomie)

Der Klassifikator kann nur bekannte Kategorien zuweisen → **keine neuen
Mega-Trends entdecken** (Kernwert der Engine!). Gegenmittel: periodisch (z. B.
monatlich) ein **LLM-Pass auf die Cluster-Zentren** der embedded Signale →
neue Mega-Trend-Kandidaten → Taxonomie (`mega_trends.yaml`) erweitern →
Klassifikator nachtrainieren. So bleibt Novelty erhalten, ohne pro Item ein LLM.

## Skala / Infra

- **Embedding = der einzige eager GPU-Schritt** → batchen (llama.cpp `/v1/embeddings`
  nimmt Listen); seine Rate bestimmt den Gesamtdurchsatz (statt der LLM-Generierung).
- **Postgres + pgvector** (Millionen Vektoren) — von diesem Pull getriggert; Storage
  `halfvec(4096)` + truncated-2000 HNSW (s. `docs/postgres_migration.md`).
- Klassifikator-Artefakte versioniert (sklearn/joblib), pro Quellentyp.

## Phasen

```
1. Distillation-Prototyp   Klassifikator auf 74k Patente + 227k Signale trainieren,
                           Agreement vs LLM auf Holdout messen (Relevanz/Vertical/Mega-Trend)
2. Kalibrierung            Relevanz-Threshold (Recall vs Noise); Mega-Trend low-confidence
                           → LLM-Fallback oder status='draft' für Review
3. Ingest-Pfad             signal_batch-Variante "embedding-first": embed → Klassifikator-Heads
                           → status='signal' (kein LLM-Classify)
4. Lazy-Layer              ensure_embeddings + lazy Content-Gen-Hook + NER-Extraction
5. Discovery-Loop          periodischer LLM-Pass auf Cluster-Zentren → Taxonomie + Retrain
6. Skalieren               DOCDB Back-File + OpenAlex pre-2020 durchziehen (Postgres)
```

## Validierung

- **Agreement Klassifikator vs LLM** (Holdout): Vertical ≥ ~90 %? Mega-Trend top-1/top-3?
  Relevanz Precision/Recall am gewählten Threshold.
- **A/B-Foresight:** ein Sample embedding-first vs. LLM-3-stage → Cluster/Trajektorien
  vergleichen (führt der billige Pfad zu denselben Trends?).

## Risiken & Gegenmittel

- **Bounded Taxonomie** → Discovery-Loop (s. o.).
- **Mega-Trend 21-Klassen-Genauigkeit** geringer als Vertical → low-confidence-Fallback (LLM/draft).
- **Extraction-Verlust** → NER/LLM lazy auf Text.
- **Embedding-Durchsatz** bei Millionen → Batch-Größe + ggf. kleineres/schnelleres Embedding-Modell für den Bulk (Qualität gegenprüfen).
- **Klassifikator-Drift** über Zeit → periodisches Retrain im Discovery-Loop.

## Verhältnis zu bestehenden Plänen

Klammer über: **DOCDB-Back-File** (`BACKLOG`, Patent-Graph-Layer) + **OpenAlex-Graph-Layer**
(`docs/openalex_acquisition.md`) + **Lazy-Embedding** + **Postgres-Migration**
(`docs/postgres_migration.md`). Liefert das *Processing*-Modell für die dort
beschriebenen Massen-Pulls.
