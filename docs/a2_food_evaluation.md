# A2 FOOD-Test — Auswertung (2026-06-22)

Erster echter Klassifizierungs-Lauf des Signal-Mode-Backfills über die Anthropic
Message-Batches-API (`scripts/signal_batch.py`), Scope = Vertical FOOD.

## Ergebnis

- **8.557 Einträge → 6.863 Signale (80 % Pass-Rate)** — FOOD clean ist hochwertig.
  (5.341 mit `primary_vertical=FOOD`; der Rest FOOD-Quellen, inhaltlich korrekt in
  HEALTH/BIZ/DESIGN/… klassifiziert — Cross-Vertical funktioniert.)
- **Qualität: sehr gut.** Stichproben treffsicher (vegan/alt-protein→FOOD,
  WHO-Medizin→HEALTH, Interior-Design→DESIGN). Cluster-Demo liefert kohärente,
  interpretierbare Trend-Cluster mit 2024-Monats-Trajektorien und Cross-Source-
  Korroboration (5–11 Quellen/Cluster): Alt-Proteine/Fermentation, Plant-Based
  Meat, AgriFoodTech-Funding, Food Security, funktionale Inhaltsstoffe.

## Yield pro Quelle (Auszug)

| Quelle | raw | Signale | Pass |
|---|---|---|---|
| AgFunderNews | 570 | 538 | 94 % |
| Frontiers Sustainable Food | 924 | 863 | 93 % |
| vegconomist | 1.989 | 1.820 | 92 % |
| Green Queen | 1.012 | 925 | 91 % |
| Trends in Food Science | 445 | 397 | 89 % |
| Nature Food | 186 | 148 | 80 % |
| EFSA Journal | 495 | 392 | 79 % |
| Science News | 733 | 425 | 58 % |
| Plant Based News | 1.293 | 617 | 48 % |

## Kosten (gemessen aus Batch-Token)

| Stage | n | in/Req | out/Req | Kosten |
|---|---|---|---|---|
| Relevanz | 8.502 | ~730 | ~84 | $4,89 |
| Extraktion | 6.998 | ~661 | ~132 | $4,62 |
| Klassifizierung | 6.998 | **~3.104** | ~90 | **$12,44** |
| **Gesamt (Batch −50 %)** | | | | **~$21,95** |

**Befund:** **Prompt-Caching griff im Batch nicht** (`cache_read=0` überall). Der
große Klassifizierungs-System-Prompt (Mega-Trend-Taxonomie, ~3.100 Tok) wurde für
alle 6.998 Requests voll berechnet → Stage 4 dominiert die Kosten. Statt der
projizierten ~$12 wurden es ~$22.

## Wall-Time (der entscheidende Befund)

**~14h46m gesamt (53.179 s).** Aufschlüsselung:
- Relevanz-Batch: 116 min (73 req/min) — okay
- **Extraktions-Batch: ~13 h, davon ~12 h mit 0 Fortschritt** (Anthropic-Queue-Stall)
- Klassifizierung + Embeddings: Rest

Die Batch-API ist best-effort; die Laufzeit ist **völlig unvorhersehbar** (gleiche
Größenordnung 7k: einmal 2 h, einmal 13 h).

## Batch vs. Lokal — Gesamtvergleich

| Pfad | Wall-Time | Kosten | Vorhersehbar | Caching |
|---|---|---|---|---|
| **Anthropic Batch (gemessen)** | **~14h46m** | **~$22** | ❌ | ❌ (griff nicht) |
| Lokal qwen3:8b single-slot (geschätzt) | ~7,7 h | **$0** | ✅ | n/a |
| **Lokal vLLM/SGLang batched (projiziert)** | **~15–40 min** | **$0** | ✅ | ✅ (Prefix-Cache) |

(Single-slot: 22.553 Calls über Stages 2–4 ÷ 49 req/min ≈ 7,7 h.)

## Verdikt

Die Klassifizierung **funktioniert qualitativ einwandfrei** (80 % Yield, treffsichere
Labels, brauchbare Foresight-Cluster) — aber der **Anthropic-Batch-Pfad ist für
diesen Workflow disqualifiziert**: langsamer *und* teurer *und* unvorhersehbar als
selbst der unparallelisierte lokale Single-Slot. Caching, der einzige Kosten-Hebel,
griff nicht.

## Entscheidung für A3 (74k Voll-Lauf)

**Nicht über die Anthropic-Batch-API.** Stattdessen den **parallelisierten lokalen
Pfad** bauen (`docs/local_parallel_classification_plan.md`): vLLM/SGLang +
Continuous Batching + Prefix-Cache + Grammar-JSON + Qwen3-8B dense. Erwartung:
74k in **wenigen Stunden statt Tagen, $0, vorhersehbar** — schlägt den Batch auf
allen Achsen. Der einzige Restvorteil des Batch („GPU frei") ist in der
sequenziellen Pipeline ohnehin illusorisch (Embeddings brauchen die GPU als
nächstes; siehe Memory `batch-api-latency-vs-local`).

**Nebenbefund (Foresight-Taxonomie):** Alle FOOD-Cluster mappen auf den einen
Mega-Trend `future_of_food_and_agriculture` — die kanonische Mega-Trend-Taxonomie
ist für FOOD zu grob; die *Embedding-Cluster + Tags* tragen die eigentliche
Granularität. Kandidat für eine feinere FOOD-Mega-Trend-Unterteilung.
