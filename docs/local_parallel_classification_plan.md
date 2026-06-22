# Build-Plan: Parallelisierte lokale Klassifizierung (Stages 2–4)

**Stand 2026-06-22.** Ziel: Relevanz (Stage 2), Extraktion (Stage 3) und
Klassifizierung (Stage 4) **lokal, parallelisiert** durchführen — als Ersatz für
den Anthropic-Batch-Pfad (`signal_batch.py`) bei Backfill-Läufen.

## Motivation (gemessen)

Der Anthropic-Batch-Pfad ist an der **Latenz** gescheitert, nicht an Korrektheit:
- Relevanz-Batch (8.502): 116 min = **73 req/min** — okay, aber:
- Extraktions-Batch (6.998): **0 verarbeitet nach ~12 h** (Queue-Stall, best-effort).
- Lokal qwen3:8b **single-slot** (Normallauf): **49 req/min** — künstlich langsam,
  weil **unparallelisiert** (`OLLAMA_NUM_PARALLEL=1`, ein llama.cpp-Slot).

→ Der Engpass war nie „GPU zu langsam", sondern der **fehlende Durchsatz im
Serving-Stack**. Ein lokaler Batch-Inferenz-Server mit Continuous Batching liegt
projiziert bei **~500–1.000 req/min** → 8.5k Relevanzen in **~10–15 min, $0,
vorhersehbar**. Siehe Memory [[batch-api-latency-vs-local]].

## Die nötigen Features (warum vLLM/SGLang statt Ollama)

| Feature | Wirkung | Ollama (Ist) | vLLM/SGLang |
|---|---|---|---|
| **Continuous / in-flight batching** | 20–50 Sequenzen parallel = #1-Durchsatz-Hebel | ✗ (1 Slot) | ✓ |
| **Prefix-/KV-Cache des System-Prompts** | großer, identischer Classify-System-Prompt (Mega-Trend-Block) einmal cachen | teilw. | ✓ (Auto Prefix / RadixAttention) |
| **Constrained/Grammar-JSON-Decoding** | schema-valider Output beim 1. Versuch, keine Retries | ✗ | ✓ (xgrammar / outlines) |
| **PagedAttention** | effizientes KV-Memory → höhere Batchgröße | ✗ | ✓ (vLLM) |
| **Bounded gen, kein CoT** | `max_tokens`~300, `enable_thinking=false` | ✓ | ✓ |

## Modellwahl (Throughput vs. Unified)

Auf der **RTX 3090 (24 GB)** ist die Abwägung VRAM-Gewichte vs. KV-Cache:

| Modell (Q4/AWQ) | Gewichte | frei für KV | parallele Seqs | Eignung |
|---|---|---|---|---|
| **Qwen3-8B dense** ⭐ | ~5–6 GB | ~18 GB | viele | **Throughput-optimal**, Qualität = Ist-Bar (DE+EN) |
| Qwen3-4B dense | ~3 GB | ~21 GB | sehr viele | max Throughput, Qualität prüfen |
| Qwen3-30B-A3B (MoE) | ~18–19 GB | ~5 GB | wenige | „ein Modell für classify+gen" (unified), aber VRAM-bound beim Batching |

**Default: Qwen3-8B dense** (matcht die gemessene Klassifizierungs-Qualität, lässt
VRAM für hohe Nebenläufigkeit). MoE 30B-A3B nur als optionaler „Unified-Stack"-Pfad.

## Architektur

```
unprocessed raw_entries (scoped: --verticals / --limit)
   │
   ▼  vLLM offline-batch (LLM.generate über ALLE Prompts einer Stage)
Stage 2 Relevanz   → guided_json=RelevanceResult     → filter (is_relevant & conf≥0.6)
Stage 3 Extraktion → guided_json=ExtractionResult    (nur Survivors)
Stage 4 Classify   → guided_json=ClassificationResult (nur Survivors)
   │
   ▼  bestehend wiederverwenden:
Stage 5 Embeddings (lokal, numpy-Dedup)  →  Stage 7 Insert status='signal'
```

- **Wiederverwenden, nichts neu erfinden:** System-Prompts (`RELEVANCE_SYSTEM`,
  `EXTRACTION_SYSTEM`, `CLASSIFICATION_SYSTEM`), Pydantic-Schemas, `validate_mega_trend`,
  `compute_crs`, die numpy-Dedup- und Insert-Logik aus `signal_batch.py`.
- **Neu:** ein lokaler Backend-Adapter + Batch-Runner; nur die *Ausführung* der
  Stages 2–4 wechselt von `anthropic_client.batch_classify` zu vLLM-Offline-Batch.

## VRAM-Koexistenz

vLLM braucht die GPU exklusiv für den Klassifizierungs-Lauf → gleiches Muster wie
bisher: **llama-server vor dem Lauf stoppen, danach starten** (die
`free_vram_for_embeddings`-Logik in `signal_batch.py` verallgemeinern). Da
Klassifizierung + Embeddings beide lokal/GPU sind, läuft der ganze Lauf in **einem**
GPU-Fenster — kein Off-GPU-Warten mehr.

## Phasen

1. **P1 — vLLM-Setup + Smoke.** vLLM (oder SGLang) im `.venv`/eigenem Env, Qwen3-8B
   (AWQ/FP8) laden, `enable_thinking=false`, **guided JSON** gegen *einen*
   Beispiel-Prompt pro Schema validieren (Relevance/Extraction/Classification).
   Prefix-Caching aktivieren. DoD: 3 valide strukturierte Outputs.
2. **P2 — Offline-Batch eine Stage.** Relevanz für die 8.502 FOOD-Entries als
   *ein* `LLM.generate(prompts)` → **req/min messen** (`max_num_seqs` tunen). DoD:
   Durchsatz-Zahl + Vergleich zu Batch (73) und single-slot (49).
3. **P3 — Voller 3-Stage-Runner.** `scripts/classify_local.py` (analog
   `signal_batch.py`, aber vLLM statt Anthropic), inkl. Filter zwischen Stages,
   Embeddings, Insert. DoD: FOOD end-to-end lokal → echte Signale + Yield-Report.
4. **P4 — Benchmark + Tuning.** Lokal-vLLM vs. Anthropic-Batch vs. Ollama-single
   (Wall-Time, $, Vorhersehbarkeit). Modellgröße (4B/8B/30B-A3B), Quantisierung,
   `max_num_seqs`, Prefix-Cache-Hit-Rate. DoD: belastbare Vergleichstabelle.
5. **P5 — A3-Entscheidung.** Mit den Zahlen: lokal-parallel vs. Cloud-Batch für
   den 74k-Voll-Lauf. Erwartung: lokal gewinnt auf allen Achsen außer
   „GPU-Block-Dauer bei Nicht-Pausierbarkeit des Normalbetriebs".

## Risiken / offene Punkte

- **vLLM-Footprint:** schwere Dep (CUDA/torch) — eigenes Env empfohlen, nicht ins
  Pipeline-`.venv` mischen. SGLang als Alternative (RadixAttention, oft schneller
  bei geteiltem Prefix).
- **Guided-Decoding-Backend:** `xgrammar` (schnell) vs. `outlines` (langsamer) —
  in P1 vergleichen.
- **Qwen3 Thinking:** `enable_thinking=false` über Chat-Template/Sampling sicherstellen.
- **Schema-Quirks:** dieselben Pydantic-Schemas; vLLM guided_json akzeptiert
  Constraints, die Anthropic ablehnt (kein `_strict_schema`-Workaround nötig).
- **VRAM-Fenster:** llama-server-Stopp während des Laufs (fcc-Stack währenddessen down).

## Verweise
- Code zum Wiederverwenden: `scripts/signal_batch.py` (Flow, numpy-Dedup, Insert),
  `pipeline/llm_processor.py` (Prompts/Schemas), `pipeline/models.py`.
- Hintergrund: Memory [[batch-api-latency-vs-local]], [[stages-8b-llamacpp-implementation]].
