# Migration: Ollama → llama.cpp als Inferenz-Engine

## Status quo (Stand 2026-05-19)

### Wo Ollama heute angefasst wird

| Datei | Funktion | Was Ollama liefert |
|---|---|---|
| `pipeline/ollama_client.py` | `chat()`, `chat_structured()`, `generate_embedding()`, `check_model_available()` | Zentrale Wrapper — hier sitzt 100 % der LLM-Logik. **Ein einziger Austauschpunkt.** |
| `pipeline/run_full_cycle.py` | `check_ollama()` (`/api/tags`), `check_gpu()` (`/api/generate` + `/api/ps`) | Health-Check + Partial-Offload-Detection via Ollama-spezifischer `/api/ps`-Felder (`size_vram`, `size`) |
| `pipeline/config.py` | `OLLAMA_HOST`, Model-Konstanten | Adresse und Modell-Namen |

Aufrufer: `llm_processor.py`, `reclassify.py`, `mega_trend_reviewer.py` — alle nur über die o. g. Wrapper. **Kein Code-Pfad kennt Ollama direkt.**

### Tatsächlich genutzte Modelle

Wichtige Beobachtung aus `llm_processor.py:237`:

```python
model=MODEL_EXTRACT if MODEL_EXTRACT != "nuextract" else "qwen3:8b"
```

NuExtract ist seit längerem **deaktiviert** — der Code fällt immer auf `qwen3:8b` zurück. Real laufen also nur drei Modelle:

| Stage | Modell | Quant | VRAM | Aufrufe pro Batch (600) |
|---|---|---|---|---|
| 2 Relevanz | `qwen3:8b` | Q4_K_M | ~5 GB | 600 |
| 3 Extract | `qwen3:8b` | Q4_K_M | ~5 GB | ≤ 450 |
| 4 Classify | `qwen3:8b` | Q4_K_M | ~5 GB | ≤ 450 |
| 5 Embeddings (dedup) | `qwen3-embedding:8b` | Q4_K_M | ~5 GB | ≤ 450 |
| 6 Content-Gen | `qwen3:14b` | Q4_K_M | ~9 GB | ≤ 445 (1 EN-Artikel) |
| 8 Reclassify | `qwen3:8b` | Q4_K_M | ~5 GB | ≤ 445 |

DE-Übersetzungen sind ebenfalls deaktiviert (`body_de` etc. nur historisch befüllt).

### Was Ollama uns heute abnimmt

1. **Hot-Swap zwischen Modellen** — `client.chat(model="qwen3:14b")` lädt das Modell on-demand und unloadet das vorige nach `keep_alive=5m`.
2. **Structured Output via JSON-Schema** — `format=schema.model_json_schema()` constraint-decoded, kein Grammar-Build nötig.
3. **`think=False`** — schaltet Qwen3-CoT-Bloat ab (Ollama-spezifisches Feature, in llama.cpp anders gelöst).
4. **`/api/ps`** mit `size_vram`/`size` — fängt Partial-CPU-Offload ab (siehe Vorfall 2026-05-09).
5. **Single Process** — ein `ollama serve` für alle Modelle.

---

## Warum llama.cpp evaluieren

| Vorteil | Realität für unsere Pipeline |
|---|---|
| 5–15 % mehr Throughput (Ollama-Overhead entfällt) | ~3 h/Cycle könnten auf 2:30 h fallen — moderat, nicht dramatisch |
| Volle Kontrolle über Quantisierung, `-fa` (Flash Attention), `-ngl`, `--batch-size` | Heute keine Tuning-Möglichkeit; bei VRAM-Druck (siehe 09.05.) wären granulare Flags Gold wert |
| Direkter Zugriff auf neueste Modelle (Tag der Veröffentlichung auf HF, statt warten bis Ollama-Pull-Liste) | Wir würden Qwen3.5/Mistral Small 3.2 schneller testen können |
| Keine Schwarzbox-Modellverwaltung — Modelle liegen als `.gguf` im Filesystem | Klare Backups, einfacher Hardware-Wechsel (siehe `migration_to_3090.md`) |
| OpenAI-kompatibler `/v1/chat/completions`-Endpoint | Standard-SDKs (openai-python, vercel ai-sdk) funktionieren direkt — Frontend-Nebeneffekt für später |

### Was llama.cpp **nicht** out-of-the-box hat

- **Kein Hot-Swap.** Ein `llama-server` = ein Modell. Zum Wechseln: zweiten Server starten oder den laufenden killen + neu starten (~5–15 s Reload bei großen Modellen).
- **Kein `/api/ps`-Äquivalent.** GPU-Offload-Verifikation muss anders gebaut werden (Process-VRAM via `nvidia-smi` oder Startup-Log parsen).
- **`think=False` ist Ollama-Wording.** In llama.cpp via `system_prompt` + `--reasoning-budget 0` (neuere Builds) oder Chat-Template-Override.

---

## Architektur-Entscheidung: Server-Topologie

Drei Optionen, gerankt:

### Option A (empfohlen): **2 persistente Server**

- **Server 1 — Generation:** `qwen3:14b-Q4_K_M.gguf`, Port 8081, alle Generationsaufgaben (Stages 2, 3, 4, 6, 8 — siehe „Modell-Konsolidierung" unten).
- **Server 2 — Embedding:** `qwen3-embedding-8b-Q4_K_M.gguf` oder leichter `nomic-embed-text` (~700 MB), Port 8082, nur `/embedding`.

**Modell-Konsolidierung:** Da `qwen3:8b` für Stages 2-4 + 8 reicht und Ollama heute zwischen 8b und 14b hin-und-her swappt, ist die saubere llama.cpp-Lösung: **alles auf qwen3:14b** als single Generation-Modell. Ein Server, keine Swaps. VRAM-Bilanz auf RTX 5080:

| | VRAM |
|---|---|
| Generation (qwen3:14b Q4_K_M) | 9.0 GB |
| KV-Cache (16k context, fp16) | ~1.5 GB |
| Embedding (qwen3-embedding 8B Q4_K_M) | 5.0 GB |
| **Σ** | **15.5 GB** auf 16.3 GB ⇒ knapp |

→ Sicherer mit **nomic-embed-text** (768-dim, 700 MB) oder **bge-m3** (1.5 GB) statt qwen3-embedding:
| Generation 9.0 + KV 1.5 + nomic 0.7 = **11.2 GB** ⇒ deutlich Headroom. |

Trade-off: Embedding-Dim wechselt von 1024 (qwen3-embed) auf 768 (nomic) → **alle gespeicherten 22k Embeddings müssen neu berechnet werden**. Bei 22k × ~50ms/Embed ≈ 20 min Re-Index — vertretbar.

### Option B: **3 sequenzielle Server (Hot-Swap manuell)**

`qwen3:8b` + `qwen3:14b` + Embedding, einer aktiv pro Stage. Spart VRAM, aber kostet bei jedem Stage-Wechsel ~10 s Reload-Latenz × 6 Stages × 600 Items wäre absurd; deshalb gruppieren wir pro Stage → 6 Reloads/Cycle = ~60 s overhead, vertretbar.

Aufwand: Server-Lifecycle-Code im Python-Wrapper (Process-Spawn, Health-Wait, Graceful-Stop).

### Option C: **Embedding bleibt Ollama, Generation auf llama.cpp**

Hybrid. Spart Migration der Embedding-Pipeline, dafür zwei Inferenz-Stacks gleichzeitig zu warten. **Nicht empfohlen.**

---

## Phasen

### Phase 1 — llama.cpp aufsetzen (1 Tag, parallel zu produktiver Pipeline)

**Voraussetzungen prüfen:**
```powershell
# CUDA Toolkit für CUDA-Build (RTX 5080 = SM_120, llama.cpp kompiliert seit 2024 ohne Probleme)
nvcc --version  # >= 12.4
```

**Optionen:**
- **A. Prebuilt Windows-Binary:** GitHub Releases (`llama-b<NNNN>-bin-win-cuda12-x64.zip`), ZIP entpacken nach `C:\tools\llama.cpp\`.
- **B. Selbst bauen:** `git clone https://github.com/ggerganov/llama.cpp; cmake -B build -DGGML_CUDA=ON; cmake --build build --config Release -j`. ~10 min auf RTX 5080.

**Modelle herunterladen (HF GGUF):**
```powershell
mkdir C:\tools\llama.cpp\models
# Qwen3 14B Q4_K_M
huggingface-cli download Qwen/Qwen3-14B-Instruct-GGUF Qwen3-14B-Instruct-Q4_K_M.gguf --local-dir C:\tools\llama.cpp\models
# nomic-embed-text v1.5
huggingface-cli download nomic-ai/nomic-embed-text-v1.5-GGUF nomic-embed-text-v1.5.Q4_K_M.gguf --local-dir C:\tools\llama.cpp\models
```

**Smoke-Test:**
```powershell
C:\tools\llama.cpp\llama-server.exe -m C:\tools\llama.cpp\models\Qwen3-14B-Instruct-Q4_K_M.gguf -ngl -1 -c 8192 --port 8081 -fa
# In zweitem Fenster:
curl http://127.0.0.1:8081/health
curl http://127.0.0.1:8081/v1/models
```

### Phase 2 — Abstraktionsschicht (1 Tag)

Neuer File `pipeline/llamacpp_client.py` mit **gleichen Signaturen** wie `ollama_client.py`:

```python
# Drop-in: liefert dieselben Pydantic-Modelle wie chat_structured() heute
def chat(model: str, prompt: str, system: str | None = None,
         temperature: float = 0.0) -> str: ...
def chat_structured(model: str, prompt: str, schema: type[T],
                    system: str | None = None, temperature: float = 0.0,
                    fallback_model: str | None = None) -> T | None: ...
def generate_embedding(model: str, text: str) -> list[float] | None: ...
def check_model_available(model: str) -> bool: ...
```

**Mapping intern:**

| Ollama-Funktion | llama.cpp-Äquivalent |
|---|---|
| `client.chat(format=schema.model_json_schema())` | OpenAI-kompatibel: `POST /v1/chat/completions` mit `response_format={"type": "json_schema", "json_schema": {"schema": ...}}` (llama-server 2024-06+) — funktioniert via openai-python |
| `client.embed(model, input=text)` | `POST /embedding` mit `{"content": text}` → `{"embedding": [...]}` |
| `think=False` | System-Prompt-Prefix oder `--reasoning-budget 0` Server-Flag |
| `MODEL_FILTER == "qwen3:8b"` → Routing | `MODEL_FILTER → "http://127.0.0.1:8081"` (in Option A immer derselbe Port) |

**Switching-Mechanismus:**
- Neue Env-Var `INFERENCE_BACKEND=ollama|llamacpp` in `config.py`.
- `llm_processor.py` etc. ändern sich **nicht** — sie importieren weiterhin `from pipeline.ollama_client import chat_structured`. Stattdessen wird `ollama_client.py` in `inference_client.py` umbenannt und entscheidet anhand der Env-Var, welches Backend es nutzt.
- Vorteil: A/B-Switch zur Laufzeit, kein Aufrufer wird angefasst.

### Phase 3 — Server-Management (0.5 Tage)

`scripts/start_llamacpp_servers.bat`:
```batch
@echo off
start "llamacpp-gen" /B C:\tools\llama.cpp\llama-server.exe ^
  -m C:\tools\llama.cpp\models\Qwen3-14B-Instruct-Q4_K_M.gguf ^
  -ngl -1 -c 8192 --port 8081 -fa --jinja ^
  > C:\Users\Dirk\projects\catandary-trends\data\llamacpp_gen.log 2>&1

start "llamacpp-emb" /B C:\tools\llama.cpp\llama-server.exe ^
  -m C:\tools\llama.cpp\models\nomic-embed-text-v1.5.Q4_K_M.gguf ^
  -ngl -1 --embedding --port 8082 ^
  > C:\Users\Dirk\projects\catandary-trends\data\llamacpp_emb.log 2>&1
```

**Persistenz auf Windows:** Per NSSM als Service (wie für Frontend in `migration_to_3090.md` skizziert):
```powershell
nssm install LlamaCppGen "C:\tools\llama.cpp\llama-server.exe" "-m ..."
nssm set LlamaCppGen Start SERVICE_AUTO_START
```

**Auto-Restart bei Crash:** NSSM macht das per default.

### Phase 4 — GPU-Check für llama.cpp

Ersatz für `run_full_cycle.py::check_gpu()`. llama-server hat kein `/api/ps`. Optionen:

1. **`nvidia-smi pmon` parsen** (empfohlen):
   ```python
   def check_gpu_llamacpp() -> bool:
       """Verify llama-server process holds >= 80% of expected model VRAM."""
       result = subprocess.run(
           ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits"],
           capture_output=True, text=True, timeout=5,
       )
       expected_gb = 9.0  # qwen3:14b Q4_K_M
       for line in result.stdout.splitlines():
           pid, name, mem_mib = [x.strip() for x in line.split(",")]
           if "llama-server" in name.lower():
               used_gb = int(mem_mib) / 1024
               if used_gb / expected_gb >= 0.80:
                   return True
       return False
   ```

2. **Server-Startup-Log parsen** (Backup):
   `data\llamacpp_gen.log` enthält Zeile `offloaded N/N layers to GPU`. Wenn `N != total`, ist Partial-Offload aktiv.

3. **`/props` Endpoint** (in neueren llama-server-Builds):
   ```python
   resp = httpx.get(f"{LLAMACPP_GEN_HOST}/props").json()
   # resp["default_generation_settings"] enthält "n_gpu_layers"
   ```

Plan: alle drei kombinieren. Primär `nvidia-smi`, Fallback Log-Parse.

### Phase 5 — Side-by-Side-Validierung (2–3 Tage)

**Kein Hard-Cutover** auf produktive Pipeline — erst Beweis dass Qualität nicht abfällt.

1. Letzte 100 raw_entries durch beide Pipelines laufen lassen (Ollama-Pfad + llama.cpp-Pfad, gleicher Code-Pfad oben drüber). Output in separate `trends_test_llamacpp`-Tabelle.
2. **Manuelle Diff-Sichtung** auf:
   - Relevance-Filter: stimmen Entscheidungen überein?
   - Vertical-Classification: stimmen Verticals überein?
   - Content-Quality: Stichprobe von 20 Bodies vergleichen — ist der Stil noch okay?
   - Embedding-Dim: 768 statt 1024 — sind die Cosine-Similarities noch sinnvoll? (Re-Embed der letzten 100 Trends, Top-10-Nachbarn vergleichen.)
3. **Speed-Metrik:** Wall-Clock pro Stage auf gleichem Sample.

Akzeptanzkriterien:
- ≤ 5 % Divergenz in `primary_vertical` (manuell als „Tie" gewertet wenn beide vertretbar).
- Content-Qualität visuell ≥ Ollama (kein systematischer Regress).
- Cycle-Zeit ≤ aktueller Stand.

### Phase 6 — Cutover (1 Nacht)

1. Ollama-Pipeline pausieren (eine Nacht aussetzen).
2. **Embeddings neu berechnen** falls Embed-Modell gewechselt: `python -m pipeline.reindex_embeddings` (neuer Helper-Script). Dauer: ~20 min.
3. `INFERENCE_BACKEND=llamacpp` in `.env` setzen.
4. NSSM-Services starten, `python -m pipeline.run_full_cycle --dry-run`.
5. Manueller Smoke-Run mit `--batch 50`. Wenn sauber: produktive Nacht.
6. Ollama als Backup installiert lassen — Rollback via Env-Var-Flip + Embedding-Restore aus Backup.

### Phase 7 — Cleanup

- BACKLOG.md: Eintrag „NuExtract entfernt, Modelle konsolidiert auf qwen3:14b".
- README.md: Setup-Anweisungen erweitern.
- `ollama_client.py` als deprecated-Wrapper stehen lassen (Rollback-Pfad) oder löschen wenn 4 Wochen stabil.

---

## Risiken

| Risiko | Wahrscheinlichkeit | Mitigation |
|---|---|---|
| qwen3:14b für Filter/Classify (statt qwen3:8b) ist langsamer | hoch | Akzeptieren (~80 t/s statt 129 t/s), durch Wegfall der Stage-Wechsel-Latenz teils kompensiert. Falls zu langsam: Option B mit Hot-Swap. |
| `response_format: json_schema` in llama-server reift gerade — Edge-Cases bei komplexen Schemata | mittel | Fallback auf GBNF-Grammar (llama.cpp bringt `examples/json_schema_to_grammar.py` mit). Im Validation-Phase erkennbar. |
| Embedding-Wechsel (qwen3-embed → nomic) ändert Duplicate-Detection-Verhalten | mittel | Threshold (heute 0.92) neu kalibrieren — auf 200 manuell gelabelten Paaren validieren. |
| llama-server crasht ohne Logging | niedrig | NSSM-Restart + Pipeline `check_gpu` failed-fast. Falls häufiger: stderr-Log permanent rotieren. |
| RTX 5080 SM_120 Compute-Cap Compile-Issues | niedrig | Prebuilt-Binary mit CUDA 12.4+ funktioniert. Falls eigenes Build: `-DCMAKE_CUDA_ARCHITECTURES=120`. |
| User-Experience: zwei zusätzliche Services im System | niedrig | Klar dokumentiert in README + Hetzner-Deploy-Notes. |

---

## Aufwand (Schätzung)

| Phase | Aufwand | kann parallel laufen mit Pipeline? |
|---|---|---|
| 1 Setup + Smoke-Test | 1 Tag | ✓ |
| 2 Abstraktionsschicht | 1 Tag | ✓ |
| 3 Server-Management | 0.5 Tage | ✓ |
| 4 GPU-Check | 0.5 Tage | ✓ |
| 5 Side-by-Side-Validierung | 2–3 Tage | ✓ |
| 6 Cutover-Nacht | 1 Nacht | ✗ — Pipeline-Pause |
| 7 Cleanup | 0.5 Tage | ✓ |
| **Σ** | **~6–7 Arbeitstage** | |

---

## Entscheidungs-Trigger

Migration lohnt **definitiv** wenn einer dieser Punkte zutrifft:
- Wir wollen ein Modell testen, das Ollama nicht in der Library hat (z. B. Mistral Small 3.2, custom finetunes).
- Pipeline-Geschwindigkeit wird kritisch (täglicher Backlog > Capacity).
- VRAM-Druck bleibt akut (Partial-Offload-Vorfälle häufen sich).

Migration lohnt **nicht jetzt** wenn:
- Pipeline läuft stabil, Backlog ist konstant 0 (aktueller Zustand).
- Migration nach lmaschine mit RTX 3090 noch nicht durch (`migration_to_3090.md`) — dann zuerst Hardware-Migration abschließen, danach Inferenz-Stack evaluieren.

**Empfehlung:** Phase 1-2 jetzt machen, Phase 3-5 parallel zur lmaschine-Migration vorbereiten, Phase 6 erst nach erfolgreichem 3090-Cutover. Inferenz-Engine und Hardware-Migration nicht in derselben Nacht.

---

## Out of Scope

- TGI / vLLM / SGLang — heavier server stacks, für ein Single-User-System overkill.
- Multi-Modal (Vision-LLMs für Bild-Inputs aus RSS-Feeds) — separates Thema.
- Speculative Decoding, Draft-Models — Tuning für später.
- Eigenes Finetuning auf gefilterte Trends — separates Backlog-Thema.
