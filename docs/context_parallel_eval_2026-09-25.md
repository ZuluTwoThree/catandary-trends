# Kontextgrößen, Parallelität und Speichernutzung der Catandary-Modelle — Messbericht 2026-09-25

**Status:** Messbericht mit Empfehlungen. **Produktiv ist nichts umgestellt.** Alle neuen
Startskripte liegen als zusätzliche Dateien in `~/llama.cpp` (`start-*-ctx*.sh`); die
bestehenden Skripte, `start-active.sh`, `gpu_handover.py` und `scheduled_cycle.sh` sind
unverändert. Entscheidung: Owner.

Messfenster: Fr 25.09.2026 14:17–17:00 (Owner-Freigabe „ab jetzt bis längstens 17 Uhr").
Testserver: `~/llama.cpp/build/bin/llama-server` direkt auf `127.0.0.1:8190` mit den
Argumenten des jeweiligen Produktivskripts plus Overrides (`scripts/ctx_eval/run_server.sh`);
Produktivserver in dieser Zeit gestoppt und danach mit `gpu-mode catandary` wiederhergestellt.
Keine Downloads (Owner-Entscheid): Phase 4 vergleicht nur KV-Cache-Quantisierungen.

Werkzeuge (wiederholbar, alle unter `scripts/ctx_eval/`):

| Skript | Zweck |
|---|---|
| `llama_log_stats.py` | Kontext-/Parallelitätsstatistik aus `/tmp/llama-server.log` (Segmente je Modell-Load, `release`-Zeilen, `print_timing`, gleichzeitig belegte Slots, truncated-Fälle) |
| `build_prompts.py` | Prompt-Sätze aus echten DB-Einträgen mit den Produktions-Buildern (`data/ctx_eval/prompts/*.jsonl`) |
| `build_quality_sets.py` | Phase-4-Sätze: Handentscheidungen (`reviewed_at`, published/rejected) für Richter und Relevanz, 70 Content-Prompts + Quelltext fürs Grounding |
| `bench_parallel.py` | Lastgenerator (ThreadPool wie `_concurrent`, `response_format json_schema` wie die Pipeline), misst Anfragen/min, Prompt-/Gen-Tokens/s aus `usage`, Latenz p50/p95, Slot-Belegung, VRAM-Spitze (nvidia-smi 0,5 s) |
| `run_server.sh` | Testserver start/stop auf :8190 (nie über `start-*.sh`, Stop nur per PID) |
| `matrix.sh` | Messblöcke je Modell (gemma, 27b, emb, 8b-variants) |
| `quality_eval.py` | Phase-4-Auswertung: Übereinstimmung mit Handentscheidungen (McNemar/Fisher), erfundene Spezifika (`pipeline.grounding.ungrounded_specifics`, Fisher) |

Rohdaten: `data/ctx_eval/results.jsonl` (eine Zeile je Messstufe), `data/ctx_eval/dump_*.jsonl`
(Einzelantworten), `data/ctx_eval/server-*.log` (Serverlogs mit Speicherzeilen),
`data/ctx_eval/llama_log_stats.json`, `data/ctx_eval/prompt_token_stats.json`.

---

## Kurzfassung

Gemessen wurden 66 Laststufen über vier Modelle. Die wichtigsten Befunde:

1. **Der Kontext ist bei drei von vier Modellen 15- bis 30-fach überdimensioniert** und kostet
   4,6–5,5 GB VRAM ohne Gegenwert. Gemma und der 27B-Richter laufen mit 262 144 Token Kontext,
   ihre längsten realen Anfragen haben 3 754 bzw. 5 879 Token. Mit 16 384 Token bleibt der
   Durchsatz gleich (0 bis −4 %).
2. **Beim 8B ist der Kontext dagegen zu klein, wo es darauf ankommt:** die Extraktion kappt die
   Quelle bei 12 000 *Zeichen*; eine CJK-Quelle sind das ~8 300 *Token* und der 8 960-Token-Slot
   läuft über. In der Sonde wurden 24 von 24 Antworten abgeschnitten, der Eintrag geht als
   `extraction_error` verloren. Das ist ein Fehler unabhängig von jeder Umstellung.
3. **Parallelität nutzt die Pipeline nur in Stufen 2–4 und 5.** Der Sättigungspunkt liegt beim
   8B bei 16 Slots, bei Gemma bei 4, beim Embedder bei 4, beim Richter gibt es keinen.
   Der größte ungenutzte Hebel ist Stufe 6: sequentiell 20,3 Anfragen/min, mit 4 Slots
   **30,0/min** — das wären 35 Minuten weniger Nachtlauf, aber ein Umbau der Schleife.
4. **`--kv-unified` ist ein schlechter Tausch:** beim 8B spart es 9 GB und kostet 36 % Durchsatz.
5. **KV-Quantisierung ist kein Qualitätshebel.** q4_0 gegen q8_0 (Richter, 150 Handentscheidungen)
   und q8_0 gegen f16 (Content-Gen, 70 Artikel; Relevanz, 150 Fälle) zeigen keinen Unterschied
   (McNemar p = 0,29 / Fisher p = 1,0 / p = 1,0). Freies VRAM gehört in ein höheres
   **Modell**-Quant — das war nicht messbar, weil keine Downloads freigegeben waren.
6. **Kein Speicherproblem ohne Anlass:** die Modelle laufen nacheinander. Freies VRAM
   beschleunigt den Nachtlauf nicht; es ist nur dann wertvoll, wenn es für ein höheres Quant
   oder einen Parallelbetrieb (Unsloth Studio) gebraucht wird.

---

## 1. Ausgangslage — selbst verifiziert

### 1.1 Modelle (GGUF-Metadaten, `gguf_dump.py --no-tensors`)

| Modell | Arch | Layer | KV-Heads × Kopfdim | Nativer Kontext | KV-Bytes/Token (berechnet) | Datei |
|---|---|---|---|---|---|---|
| Qwen3-8B-UD-Q4_K_XL | qwen3 | 36 | 8 × 128 (K=V) | **40 960** | f16 147 456 · q8_0 78 336 · q4_0 41 472 | 5,1 GB |
| gemma-4-26B-A4B-it-qat-UD-Q4_K_XL | gemma4, MoE 128×2.6B (8 aktiv) | 30 (25 SWA-Layer Fenster 1 024 + 5 globale) | SWA 8 × 256, global 2 × 512 | 262 144 | global nur 5 Layer: q8_0 10 880/Token; SWA-Layer halten nur ~1 024 Token je Sequenz | 14,2 GB |
| Qwen3.8-27B-UD-Q4_K_XL | qwen35 (Gated-DeltaNet-Hybrid) | 65 (64 + 1 MTP), Attention nur jeder 4. = 16 | 4 × 256 | 262 144 | q8_0 34 816 · q4_0 18 432 (+ SSM-Zustand fester Größe je Sequenz) | 17,9 GB |
| Qwen3-Embedding-8B-Q4_K_M | qwen3 | 36 | 8 × 128 | 40 960 | wie 8B | 4,7 GB |

Rechnung KV-Bytes/Token = Layer × KV-Heads × Kopfdim × 2 (K+V) × Bytes/Wert (f16 2,0; q8_0 34/32; q4_0 18/32).
Für das 8B ergibt das bei `-c 212992` q8_0 = 16,7 GB — deckt sich mit den ~16,1 GB im Skriptkommentar.
Beim 27B deckt sich 34 816 B/Token mit dem Kommentar in `start-qwen3.8-27b.sh`.

**Nebenbefund:** Das 8B ist nativ ein 40K-Modell. Die 24 Slots à 8 960 Token liegen darunter,
`-c 212992` ist nur die Summe der Slots (kv_unified=false), kein 208K-Kontext für eine Anfrage.

### 1.2 Produktivkonfiguration heute (Startskripte, verifiziert)

| Modell | Skript | Server-Argumente | Slots × Kontext | VRAM gemessen |
|---|---|---|---|---|
| 8B | `start-qwen3-8b-208k.sh` | `-c 212992 --parallel 24 -ctk/-ctv q8_0 -ub 512 -b 512` | 24 × 8 960 (Server rundet auf 215 040), kv_unified=false | 21 806 MiB Prozess / 21 986 MiB gesamt (Testserver 14:17) |
| Gemma-26B | `start-gemma4-26b.sh` | `-c 262144 -ctk/-ctv q8_0 -ub 2048 -b 4096` (kein `--parallel` → 4 Slots auto, kv_unified=true) | 4 × 262 144 unified | s. Abschnitt 3 |
| 27B | `start-qwen3.8-27b.sh` | `-c 262144 --parallel 1 -ctk/-ctv q4_0 -ub 1024 -b 2048` | 1 × 262 144 | s. Abschnitt 3 (Skript: 23 342 MiB) |
| Embedding | `start-qwen3-emb.sh` | `--embedding --pooling last -c 8192 -ub 8192 -b 8192` (4 Slots auto, unified) | 4 × 8 192 unified | s. Abschnitt 3 |
| Embedding CPU | `start-qwen3-emb-cpu.sh` (:8091) | `-ngl 0`, `CUDA_VISIBLE_DEVICES=""` | — | 0 — nicht angefasst |

llama.cpp-Build: `c841aeeb8` (2026-08-29), unterstützt `--kv-unified`, `--kv-unified-per-slot N`, `--ctx-checkpoints`, `--slots`, `--metrics`.

### 1.3 Nutzung laut `/tmp/llama-server.log` — reproduziert

Das Log (60 MB, 41 Modell-Segmente, 69 008 `release`-Zeilen) hat keine Wanduhr; die Segmente
lassen sich über die Cycle-Logs datieren: es deckt die Nachtläufe **23.–25.09.2026** ab
(Segment 3 = Reclassify-Pass 9 397 Drafts am 23.09., Segment 15 = 9 624 am 24.09.,
Segment 37 = 1 754 am 25.09. nach dem `reclassified_at`-Fix) plus Handläufe (u. a. Segment 25 =
27B-Nachlauf über 1 942 Altfälle vom 24.09.). Die Zahlen aus der Aufgabenstellung stimmen exakt.

| Modell | n | n_tokens Mittel / Median / p99 / Max | Prompt (voll) Median / p99 / Max | Generierung Median / p99 / Max | truncated | max. gleichzeitig belegte Slots |
|---|---|---|---|---|---|---|
| 8B | 50 261 | 961 / 879 / 3 013 / 8 959 | 862 / 2 338 / 6 661 | 16 / 802 / 8 192 | 12 | **24** (Stufen 2–4), **1** (Stage 8) |
| Gemma | 6 750 | 2 011 / 2 155 / 3 046 / 3 754 | 1 788 / 2 618 / 3 402 | 327 / 587 / 2 048 | 0 | **1** |
| 27B | 3 675 | 1 881 / 1 786 / 3 937 / 5 879 | 1 747 / 3 897 / 5 843 | 39 / 46 / 1 367 | 0 | **1** |
| Embedding | 8 322 | 131 / 128 / 244 / 432 | — | — | 0 | **4** (= Slotzahl; Pipeline schickt 24) |

„Prompt (voll)" = n_tokens − Generierung; die `prompt eval`-Zahl in `print_timing` zählt nur neu
ausgewertete Tokens (Median 8B: 65 — der System-Prompt kommt aus dem Slot-Cache).

**Die 12 abgeschnittenen 8B-Anfragen** (alle in den drei parallelen Stufe-2/3/4-Segmenten,
Slot-Belegung 24): Prompt 1–889 neu evaluierte Tokens, **Generierung 6 134–8 192 Tokens**, bis der
Slot (8 960) voll war. Das sind **Ausreißer-Generierungen der Extraktion** (Truncation-Leiter in
`llamacpp_client.chat_structured`: `max_tokens` 2 048 → 4 096 → 8 192 bei `finish_reason=length`),
keine zu langen Prompts. Ein größerer Slot würde sie nicht retten, nur länger laufen lassen
(478 s für 7 624 Tokens); jede kostete ~8 min Slotzeit. Empfehlung dazu in Abschnitt 6.

### 1.4 Parallelität im Code (was die Pipeline tatsächlich schickt)

| Stufe | Modell | Code | gleichzeitig |
|---|---|---|---|
| 2/3/4 (Hybrid: Relevanz-Fallback + Extraktion; Klassifikation macht der Distill-Head) | 8B | `llm_processor._concurrent`, `CLASSIFY_WORKERS=24` (ThreadPool) | 24 |
| 5 Embeddings | Emb | `_concurrent` mit 24 Workern | 24 gesendet, Server hat 4 Slots → 4 |
| 6 Content-Gen | Gemma | `for entry in survivors:` — **sequentiell** | 1 |
| 8 Reclassify | 8B | `reclassify_drafts` — **sequentiell** | 1 |
| 10 Richter | 27B | `judge_recent_drafts` — **sequentiell** | 1 |
| 11 Review-Agent | Gemma | sequentiell (Handover auf `STAGE5_MODEL`) | 1 |
| Research Pulse / Newsletter / Nest-Naming | Gemma | `chat()` einzeln, `max_tokens` 420 / 1 400 / 32 | 1 |
| Samstags-Distill (`signal_batch`) | 8B | ThreadPool `workers=24` | 24 |

Zeitbudget Nachtlauf 25.09. (Cycle-Log): Stufen 2–4 hybrid 51 min (inkl. Volltext-Abruf),
Embeddings 1 min, **Stufe 6 101 min (1 754 Artikel, 3,5 s je Artikel, sequentiell)**, Stage 8
6 min (nach dem Fix vom 24.09.), Richter 23 min (534 Drafts, 2,6 s), Agent 1 min.
Die größte Uhrzeit hängt also an einer Stufe, die **keine** Parallelität nutzt.

### 1.5 Theoretischer Maximalbedarf je Anfrage (Code-Pfade, Tokens mit dem Qwen3-Tokenizer)

| Pfad | Aufbau | Tokens (gemessen an 1 000 echten Prompts) | Worst Case |
|---|---|---|---|
| Extraktion (8B) | System 76 + Titel + Text[:12 000 Zeichen] | Median 735 · p99 2 966 · Max 4 676 | 12 000 Zeichen Deutsch = 4 016–4 023 Tokens; **CJK-Quelle 8 302 Tokens** (1 Fall in der DB) + Ausgabe bis 2 048 (Leiter 8 192) |
| Relevanz (8B) | System 165 + Text[:1 500] | < 700 | ~800 |
| Klassifikation (8B, nur Fallback `RSS_CLASSIFY_MODE=llm`) | System **2 272** + Text[:1 000] | Median 2 640 · Max 3 209 | ~3 400 |
| Reclassify (8B) | System 792 + Titel + Summary[:500] | Median 854 · Max 956 | ~1 000 |
| Content (Gemma) | System 673 + Quelle[:4 000] + Extraktion (Zahlen, Claims, Zitate) | Median 1 884 · p99 2 813 · Max 3 463 (Qwen-Tokenizer; Log mit Gemma-Tokenizer: Max 3 402) + Ausgabe ≤ 2 048 | ~5 500 |
| Richter (27B) | System 262 + Quelle[:12 000] + Extraktion[:1 500] + Body[:2 200] | Median 1 666 · p99 3 897 · Max 4 737 (Log: 5 843) + Ausgabe ~40 | Latein ~6 500; CJK-Quelle bis ~10 000 |
| Review-Agent (Gemma) | Quelle[:9 000] + Satz | < 3 500 | ~4 000 |
| Research Pulse (Gemma) | Messblock + 2 Titel je Cluster, `max_tokens` 420 | < 2 000 | ~2 500 |
| Newsletter (Gemma) | Top-3 je Vertikale, Summaries à 80 Zeichen | < 2 500 | ~3 000 |
| Embedding | Titel + Teaser[:500] | Median 105 · Max 574 | < 800 |

### 1.6 Realer Durchsatz der Produktion (aus dem Log, je Segment ≥ 500 Anfragen)

Aus `print_timing` (Generierung/Prompt-Tokens) und den `release`-Zeitstempeln je Segment:

| Segment (Nacht) | Modell / Stufe | Anfragen | Dauer | Anfragen/min | Gen-Tokens/s | neu evaluierte Prompt-Tokens/s | Gen-Tokens je Anfrage |
|---|---|---|---|---|---|---|---|
| 5 (23.09.) | 8B Stufen 2–4, 24 parallel | 2 214 | 46 min | 47,8 | 371 | 662 | 465 |
| 17 (24.09.) | 8B Stufen 2–4 | 2 352 | 44 min | 53,2 | 374 | 724 | 422 |
| 35 (25.09.) | 8B Stufen 2–4 | 2 205 | 48 min | 45,6 | 358 | 646 | 471 |
| 3 / 15 (23./24.09.) | 8B Stage 8 (alt: ganzer Bestand), sequentiell | 9 397 / 9 624 | 29 min | 328–333 | 89 | 396–403 | 16 |
| 37 (25.09.) | 8B Stage 8 (nur neue Drafts) | 1 754 | 5,5 min | 320 | 87 | 446 | 16 |
| 6 / 18 / 36 | Gemma Stufe 6, sequentiell | 2 161 / 2 324 / 2 057 | 106 / 114 / 101 min | **20,3–20,4** | 111–113 | 308–335 | 327–334 |
| 8 / 20 / 38 | 27B Richter, sequentiell | 555 / 600 / 534 | 19–23 min | 23–29 | 15–19 | 403–560 | 39 |
| 25 (24.09., Nachlauf) | 27B Richter, 12 000-Zeichen-Quelle | 1 942 | 97 min | 20,0 | 13 | 676 | 39 |
| 4 / 16 / 34 | Embeddings, 4 Slots | 2 713 / 2 873 / 2 716 | ~2 min | **1 325–1 357** | — | — | — |

Das ist der Maßstab „heute" für alle folgenden Tabellen. Ein Testlauf mit fester Anfragenzahl
unterschätzt den Dauerdurchsatz bei hoher Parallelität (Schweif der letzten Langläufer), deshalb
misst `bench_parallel.py --duration/--ramp` zusätzlich den eingeschwungenen Zustand.

---

## 2. Phase 2 — Durchsatz vs. Parallelität (Testserver :8190)

Lastprofil: die Prompt-Sätze aus Abschnitt 1.5 (echte Einträge, Produktions-Builder,
`response_format json_schema` wie die Pipeline, `max_tokens` 2 048, Temperatur wie in Produktion).
Zwei Messarten: **fest n** (48 Anfragen je Stufe; unterschätzt bei hoher Parallelität, weil der
Schweif der letzten Anfragen mitzählt) und **Dauerlast** (`--duration/--ramp`: C Anfragen ständig
im Fluss, gewertet nur der eingeschwungene Teil). VRAM = Spitze aus nvidia-smi (0,5-s-Raster,
gesamte Karte; Grundlast ohne Server 172 MiB).

### 2.1 Qwen3-8B (Stufen 2–4: 15 % Relevanz, 85 % Extraktion)

Alle Zeilen: `data/ctx_eval/results.jsonl` (`scripts/ctx_eval/summarize_results.py 8b`).

| Konfiguration | Slots × Kontext | KV | conc | Messart | Anfragen/min | Gen-Tok/s | p50 s | VRAM MiB |
|---|---|---|---|---|---|---|---|---|
| **heute** `-c 212992 --parallel 24 -ub 512` | 24 × 8 960 | q8_0 | 1 | n=48 | 14,1 | 107 | 4,3 | 22 000 |
| | | | 2 | n=48 | 17,5 | 115 | 5,5 | |
| | | | 4 | n=48 | 16,1 | 116 | 12,5 | |
| | | | 8 | n=48 | 21,4 | 135 | 18,4 | |
| | | | 16 | n=48 | 25,0 | 168 | 28,0 | |
| | | | 24 | n=48 | 28,1 | 225 | 28,4 | |
| | | | 32 | n=48 | 38,0 | 283 | 35,7 | |
| | | | 24 | Dauer 75 s | **48,8** | 303 | 20,4 | |
| | | | 32 | Dauer 75 s | 56,0 | 358 | 25,6 | |
| | | | 24 | Dauer 150/45 s | **57,7** | 372 | 22,3 | 22 000 |
| `-c 143360 --parallel 16 -ub 2048 -b 2048` | 16 × 8 960 | q8_0 | 16 | Dauer 150/45 s | **56,0** | 359 | 15,5 | **16 506** |
| `-c 143360 --parallel 16` (`-ub 512`) | 16 × 8 960 | q8_0 | 16 | Dauer 150/45 s | 52,0 | 332 | 16,2 | 16 362 |
| | | | 24 (8 warten) | Dauer 150/45 s | **53,7** | 335 | 21,0 | 16 362 |
| `-c 215040 --parallel 24 -ub 2048 -b 2048` | 24 × 8 960 | q8_0 | 24 | Dauer 150/45 s | **59,4** | 392 | 21,7 | 22 142 |
| `-c 98304 --parallel 24 --kv-unified` | Pool 98 304 | q8_0 | 24 | Dauer 150/45 s | 37,1 | 249 | 41,2 | **12 912** |
| | | | 48 Burst (Langprompts) | Burst | 34,3 | 233 | 58,1 | 12 912 |
| `-c 98304 --parallel 48 --kv-unified` | Pool 98 304 | q8_0 | 24 | Dauer 150/45 s | 37,7 | 247 | 40,9 | 12 912 |
| | | | 48 | Dauer 150/45 s | 30,9 | 167 | 79,0 | 12 912 |
| `-c 98304 --parallel 24 --kv-unified -ub 2048` | Pool 98 304 | q8_0 | 24 | Dauer 150/45 s | 39,4 | 267 | 37,7 | 13 318 |
| `-c 73728 --parallel 8 -ctk/-ctv f16` (Relevanz-Prompts) | 8 × 9 216 | f16 | 8 | n=150 | 80,9 | 222 | 5,7 | 15 524 |
| heute (Relevanz-Prompts) | 24 × 8 960 | q8_0 | 24 | n=150 | 111,9 | 303 | 11,8 | 22 000 |

Befunde:

1. **Parallelität lohnt sich für die Extraktion bis etwa 16 Slots**; von 16 auf 24 Slots kommen
   noch +3 % (52,0 → 53,7 bei je 24 Workern), also unter der 10-%-Schwelle → **Sättigungspunkt 16**.
   Der Gewinn kommt nicht aus „mehr Slots", sondern daraus, dass die Generierung der anderen Slots
   während der 512-Token-Prefill-Schritte langer Extraktions-Prompts mitläuft (je Slot bleiben
   ~15 Tok/s, ob 8, 16 oder 24 Slots laufen). Deshalb hilft ein größerer Prefill-Block
   (`-ub 2048`) mehr als zusätzliche Slots: +10 % Durchsatz bei +150 MiB.
2. **`--kv-unified` kostet hier Durchsatz statt nur Speicher:** gleiche 24 Slots, gleiche Prompts,
   37 statt 49–54 Anfragen/min und doppelte Latenz. In einem gemeinsamen Puffer läuft die
   Attention jeder Sequenz über alle belegten Zellen; bei 24 gleichzeitig langen Extraktionen
   sind das ~36K Zellen statt ~1,5K eigener. Der Speichergewinn (12,9 statt 22,0 GB) ist echt,
   der Preis ~30 % Nachtlaufzeit in Stufe 2–4. 48 Slots im selben Pool sind noch langsamer
   (31/min) — mehr Sequenzen, mehr Maskenarbeit.
3. **Grenzfall kleiner Pool:** 48 lange Extraktionen gleichzeitig in den 96K-Pool mit 24 Slots →
   alle 48 korrekt beantwortet, 0 Fehler, 0 Abschneiden; die überzähligen 24 warten in der
   HTTP-Warteschlange des Servers (p95 82 s). Kein Abbruch, kein Datenverlust — nur Wartezeit.
4. **Die Grammatik ist nicht der Engpass** (Diagnose ohne `response_format`, gleicher Server):
   Gen-Tokens/s 262 ohne vs. 249 mit Schema bei den Extraktions-Prompts; bei den kurzen
   Relevanz-Prompts liefert der Lauf MIT Schema sogar mehr Anfragen/min (74,7 vs. 70,7 — ohne
   Grammatik schreibt das Modell längere Freitexte). Der Hauptthread bei 100 % CPU ist das
   übliche CUDA-Spinnen, keine Sampling-Bremse.
5. **Stage 8 (Reclassify, in Produktion sequentiell, 16 Ausgabetokens):** 358/min bei conc 1,
   382 bei 8, **660 bei 24** — eine Parallelisierung im Code (`reclassify_drafts` über
   `_concurrent`) würde die heute ~5,5 min auf ~3 min drücken. Kleiner Hebel, keine Priorität.
6. Kein Unterschied durch KV f16 in den Ergebnissen (Abschnitt 5.1), aber f16 mit 8 Slots
   liefert 222 Gen-Tok/s gegen 303 mit 24 Slots q8_0 — der Slot-Verlust wiegt mehr als die
   Cache-Präzision.

### 2.2 Gemma-4-26B-A4B (Stufe 6 Content-Gen, T=0,7, `max_tokens` 2 048)

Leerlauf-VRAM der Produktionskonfiguration (gemessen, Testserver): **19 530 MiB Prozess / 19 712 MiB
gesamt** — der Skriptkommentar („20,7 GB") ist um 1 GB zu hoch.

| Konfiguration | Slots × Kontext | conc | Messart | Anfragen/min | Gen-Tok/s | p50 s | VRAM-Spitze MiB |
|---|---|---|---|---|---|---|---|
| **heute** `-c 262144 -ub 2048 -b 4096` (4 Slots auto, unified) | 4 × 262 144 (Pool) | 1 | Dauer 120/30 | **19,3** | 108 | 2,9 | **19 782** |
| | | 2 | Dauer 120/30 | 21,3 | 121 | 5,6 | 19 782 |
| | | 4 | Dauer 120/30 | **24,7** | 143 | 10,4 | 19 782 |
| | | 8 (4 warten) | Dauer 120/30 | 23,3 | 135 | 21,1 | 19 782 |
| `-c 16384 --parallel 1` | 1 × 16 384 | 1 | Dauer 90/15 | 19,2 | 115 | 3,1 | **15 064** |
| `-c 32768 --parallel 4 --kv-unified` | Pool 32 768 | 2 | Dauer 90/20 | 20,6 | 124 | 5,7 | 15 630 |
| | | 4 | Dauer 90/20 | 24,0 | 140 | 9,5 | 15 638 |
| `-c 32768 --parallel 4` (**nicht** unified) | 4 × 8 192 | 2 | Dauer 90/20 | 25,7 | 149 | 4,4 | 16 160 |
| | | 4 | Dauer 90/20 | **30,0** | 177 | 7,9 | 16 168 |
| Produktion (Log, 3 Nächte, sequentiell) | | 1 | — | 20,3–20,4 | 111–113 | ~2,95 | — |

Befunde:

1. Der Testaufbau trifft die Produktion (19,3 vs. 20,3/min bei conc 1 — die Produktion hat mehr
   Cache-Treffer auf dem 673-Token-System-Prompt).
2. **Parallelität bringt bei Gemma etwas — aber nur ohne `--kv-unified`:** in der heutigen
   Konfiguration (unified) +28 % bei 4 gleichzeitigen Anfragen, bei 8 nichts mehr;
   **ohne** unified (4 × 8 192) dagegen **30,0/min = +55 %** gegenüber sequentiell.
   **Sättigungspunkt 4.** Da Stufe 6 sequentiell schickt, ist der heutige Betrieb die
   conc-1-Zeile; die 55 % bräuchten eine Code-Änderung (Abschnitt 4) und würden den Nachtlauf
   um ~35 min verkürzen.
3. **Der Kontext von 262 144 kostet 4,7 GB für nichts:** die längste je gesehene Anfrage hat
   3 754 Token, der theoretische Maximalfall (Abschnitt 1.5) ~5 500. `-c 16384 --parallel 1`
   liefert denselben Durchsatz bei 15,1 statt 19,8 GB. Der Grund, warum die 256K überhaupt
   „passen": nur 5 der 30 Layer sind globale Attention (10 880 B/Token q8_0 → 2,85 GB), die 25
   SWA-Layer halten je Sequenz nur ~1 024 Token — plus die Compute-Puffer für `-ub 2048` bei
   4 Sequenzen.
4. **KV-Quantisierung ist kein Qualitätshebel** (Abschnitt 5.2): q8_0 und f16 unterscheiden sich
   in der Erfindungsrate nicht (2/70 vs. 1/70, Fisher p = 1,0).

### 2.3 Qwen3.8-27B (Stufe 10 Richter, T=0, ~40 Ausgabetokens)

| Konfiguration | Slots × Kontext | KV | conc | Messart | Anfragen/min | p50 s | VRAM-Spitze MiB |
|---|---|---|---|---|---|---|---|
| **heute** `-c 262144 --parallel 1 -ctk/-ctv q4_0` | 1 × 262 144 | q4_0 | 1 | Dauer 90/15 | 22,4 | 2,5 | **23 094** |
| dieselbe, 150 Handentscheidungs-Drafts | | q4_0 | 1 | n=150 | 26,5 | 2,2 | 23 094 |
| `-c 16384 --parallel 1 -ctk/-ctv q8_0` | 1 × 16 384 | q8_0 | 1 | Dauer 90/15 | 21,6 | 2,6 | **17 610** |
| dieselbe, 150 Handentscheidungs-Drafts | | q8_0 | 1 | n=150 | 26,4 | 2,2 | 17 610 |
| `-c 32768 --parallel 4 --kv-unified -ctk/-ctv q8_0` | Pool 32 768 | q8_0 | 2 | Dauer 90/20 | 23,1 | 4,6 | 18 680 |
| | | q8_0 | 4 | Dauer 90/20 | 24,0 | 9,5 | 18 680 |
| Produktion (Log, 4 Läufe, sequentiell) | | q4_0 | 1 | — | 20,0–28,9 | 2,1–3,0 | 23 342 (Skript) |

Befunde:

1. Der Richter ist prefill-dominiert (Prompt Median ~1 700, Ausgabe ~40 Token); 2,2–2,6 s je
   Draft in beiden Konfigurationen — **der Kontext von 262 144 kostet 5,5 GB und bringt nichts**:
   die längste je gesehene Anfrage hat 5 879 Token, der Maximalfall mit CJK-Quelle ~10 000
   (Sonde in Abschnitt 3). `-c 16384` deckt das mit Marge 1,6 gegenüber dem Maximalfall und
   2,8 gegenüber dem Log-Maximum.
2. Mit 16K passt der KV-Cache auch in q8_0 (34 816 B/Token → 0,55 GB) — das war bei 256K der
   Grund für q4_0 (8,7 GB). Der Qualitätsvergleich (Abschnitt 5.3) zeigt aber keinen Gewinn
   durch q8_0; die Wahl ist frei, q8_0 kostet nichts mehr.
3. Frei werdende ~5,5 GB reichen rechnerisch für `Qwen3.8-27B-UD-Q5_K_XL` (20,9 GB Datei,
   +3,0 GB) oder knapp `UD-Q6_K` (22,0 GB, +4,1 GB). **Nicht gemessen** — Downloads waren
   nicht freigegeben. Ob ein höheres Quant den Richter besser macht, ist offen; Abschnitt 5.3
   zeigt, wo er heute steht.

---

## 3. Phase 1/3 — Kontextbedarf, Sonden in Maximallänge, Speicherminimum

### 3.1 Sonden: die längste erlaubte Anfrage, gegen den laufenden Server geschickt

`scripts/ctx_eval/build_probes.py` baut aus dem **CJK-lastigsten** Volltext der DB
(12 000 Zeichen ≈ 8 300 Token statt ~4 000 bei lateinischer Schrift) je eine Anfrage in der
Länge, die der Produktionscode maximal erzeugen kann, mit vollem Extraktionsblock.

| Sonde | Server | Prompt-Tokens | Ausgabe-Tokens | Slot belegt | Ergebnis |
|---|---|---|---|---|---|
| Extraktion (8B) | heute, 24 × 8 960 | 8 442 | 518 | **8 960 = Slotgrenze** | **24 von 24 abgeschnitten** (`finish_reason=length`) |
| Extraktion (8B) | `-c 143360 --parallel 16 -ub 2048`, 16 × 8 960 | 8 442 | 518 | **8 960 = Slotgrenze** | **16 von 16 abgeschnitten** |
| Richter (27B) | `-c 16384 --parallel 1 q8_0` | 9 086 | 79 | 9 165 | ok, 2,2 s |
| Content (Gemma) | `-c 16384 --parallel 1` | 4 068 | 290 | 4 358 | ok, 2,4 s |

**Befund 8B (neu, betrifft die Produktion heute):** Der Slot von 8 960 Token ist für die
Extraktion **zu klein**, sobald die Quelle nicht-lateinisch ist. `EXTRACT_CHARS = 12 000` ist eine
ZEICHEN-Kappe; in CJK sind das ~8 300 Token, plus System (76) und Ausgabebudget (2 048) sind
~10 400 nötig. Was dann passiert, ist kein Fehler, sondern stille Kürzung: der Server füllt den
Slot und bricht die JSON-Ausgabe ab, `chat_structured` sieht `finish_reason=length`, verdoppelt
das Budget (das nichts nützt, der Slot ist voll) und gibt nach drei Versuchen `None` zurück —
der Eintrag wird `mark_filtered("extraction_error")`. In der DB stehen 2 Einträge mit ≥ 12 000
Zeichen CJK-Volltext, also ist das heute ein seltener, aber echter Verlustpfad.
Zwei Wege, unabhängig von jeder Umstellung:
* **Slot ≥ 12 288 Token** (also `-c 294912 --parallel 24` oder `-c 196608 --parallel 16`), oder
* `EXTRACT_CHARS` in TOKEN statt Zeichen kappen (`/tokenize` oder konservativ 6 000 Zeichen bei
  nicht-lateinischen Quellen) — die billigere Lösung, weil sie kein VRAM kostet.

### 3.2 Benötigter Kontext je Anfrage (Phase 1)

Sicherheitsfaktor **1,5 auf den Code-Maximalfall** (nicht auf das Log-Maximum: der Code kann
mehr erzeugen als bisher vorkam, und die Sonde zeigt, dass genau das passiert).

| Modell | Log-Max | Code-Max (gemessen, CJK-Sonde) | × 1,5 | Empfohlener Slot | heute |
|---|---|---|---|---|---|
| 8B (Extraktion) | 8 959 (Slotgrenze!) | 8 442 + 2 048 Ausgabe = **10 490** | 15 735 | **12 288** (Faktor 1,17 über Code-Max) oder Token-Kappe in der Extraktion | 8 960 ❌ |
| 8B (Relevanz/Reclassify) | ~1 000 | ~1 000 | 1 500 | gedeckt | |
| Gemma (Stufe 6) | 3 754 | 4 358 (Sonde) → + Rest-Ausgabebudget ≈ 6 300 | 9 450 | **16 384** (Faktor 2,6) | 262 144 |
| 27B (Richter) | 5 879 | 9 165 (Sonde) | 13 748 | **16 384** (Faktor 1,8) | 262 144 |
| Embedding | 432 | 574 | 861 | 2 048 (Slot) / 8 192 Pool | 8 192 |

### 3.3 Kleinste Konfiguration, die Bedarf + Sättigungspunkt erfüllt (Phase 3)

VRAM = Spitze unter Last, nvidia-smi, gesamte Karte (Grundlast 172 MiB).

| Modell | heute | VRAM heute | Vorschlag | VRAM Vorschlag | Δ VRAM | Durchsatz |
|---|---|---|---|---|---|---|
| 8B Stufen 2–4 | `-c 212992 --parallel 24 -ub 512` | 22 000 MiB | `-c 143360 --parallel 16 -ub 2048 -b 2048` | **16 506 MiB** | **−5,5 GB** | 56,0 vs. 57,7 Anfragen/min (**−3 %**) |
| 8B (Speicherminimum) | dito | 22 000 MiB | `-c 98304 --parallel 24 --kv-unified` | 12 912 MiB | −8,9 GB | 37,1/min (**−36 %**) |
| Gemma Stufe 6 | `-c 262144` (4 Slots unified) | 19 782 MiB | `-c 16384 --parallel 1 -ub 2048 -b 4096` | **15 072 MiB** | **−4,6 GB** | 19,2 vs. 19,3/min (**±0**) |
| 27B Richter | `-c 262144 --parallel 1 q4_0` | 23 094 MiB | `-c 16384 --parallel 1 -ctk/-ctv q8_0` | **17 610 MiB** | **−5,4 GB** | 21,6 vs. 22,4/min (**−4 %**) |
| Embedding | `-c 8192 -ub 8192` (4 Slots) | 11 096 MiB | `-c 16384 --parallel 16 --kv-unified -ub 2048` | **8 552 MiB** | −2,5 GB | 1 674 vs. 1 680/min (**±0**) |

Wichtig: Die Modelle laufen **nacheinander**, nie gleichzeitig. Freies VRAM bringt deshalb nur
etwas, wenn es für etwas anderes gebraucht wird — ein höheres Quant, ein zweites Modell auf der
Karte (Unsloth Studio über `gpu-mode shared`), oder mehr Kontext-Sicherheit. Es beschleunigt
den Nachtlauf **nicht**.

---

## 4. Parallelität, die die Pipeline nicht nutzt (getrennt ausgewiesen)

Die Messungen oben schicken parallel; die Produktion tut das nur in Stufen 2–4 und Stufe 5.
Was eine **Code-Änderung** brächte (Zahlen aus den Dauerlast-Läufen):

| Stufe | heute | mit Parallelität | Gewinn | Code-Eingriff | Bewertung |
|---|---|---|---|---|---|
| 6 Content-Gen (Gemma) | sequentiell, 20,3/min, ~101 min je Nacht | 4 Slots **ohne** `--kv-unified` (4 × 8 192): **30,0/min**; mit unified 24,0/min | **−35 min je Nacht** (101 → ~66) | `llm_processor` Stufe-6-Schleife auf `_concurrent` umstellen; Vorsicht: `save_stage_result`, Garbled-Zähler und der `ModelMismatchError`-Abbruch („alle folgenden bleiben unprocessed") sind auf Reihenfolge gebaut | **größter Hebel im Nachtlauf**, aber echter Umbau |
| 8 Reclassify (8B) | sequentiell, 358/min, ~5,5 min | 24 parallel: 660/min | −2,5 min | `reclassify_drafts` über `_concurrent` | klein, billig |
| 10 Richter (27B) | sequentiell, 22,4/min, ~23 min | 4 Slots unified q8_0: 24,0/min | −1,5 min | `judge_recent_drafts`-Schleife | lohnt nicht |
| 11 Review-Agent (Gemma) | sequentiell, ~1 min | wie Stufe 6 | — | — | lohnt nicht |
| 5 Embeddings | 24 Worker auf 4 Slots, ~1–2 min | mehr Slots ändert nichts (Sättigung bei 4) | — | — | nichts zu tun |

Gemma-Detail: **ohne** `--kv-unified` skaliert das MoE deutlich besser (25,7/min bei 2, 30,0 bei 4)
als mit dem gemeinsamen Pool (20,6 / 24,0) — derselbe Effekt wie beim 8B in Abschnitt 2.1.

---

## 5. Phase 4 — Qualität statt Tempo (nur KV-Quantisierung; keine Downloads freigegeben)

Gleiche Eingaben je Arm, Temperatur wie in Produktion. `scripts/ctx_eval/quality_eval.py`.

### 5.1 8B, Relevanzfilter (Stufe 2) — KV q8_0 vs. f16

150 Trends mit Handentscheidung (75 published, 75 rejected, `reviewed_at` gesetzt, letzte 60 Tage),
Relevanz-Prompt auf den Rohdaten, Maßstab `is_relevant` ↔ published.

| Arm | n | Übereinstimmung | is_relevant=true | JSON ungültig |
|---|---|---|---|---|
| q8_0 (heute) | 150 | 76 (50,7 %) | 147 | 0 |
| f16 | 150 | 76 (50,7 %) | 145 | 0 |

Identische Entscheidung in 148 von 150 Fällen, mittlere |Δconfidence| 0,013, McNemar p = 1,0.
**Kein Unterschied.** Nebenbefund zum Maßstab: der Relevanzfilter hält fast alles für relevant
(147/150) — Handverwürfe passieren aus Artikelgründen (Grounding, Dünne, Spam), nicht weil das
Signal irrelevant wäre; für den 8B ist die Handentscheidung deshalb ein schwaches Kriterium.
JSON-Gültigkeit: 0 Fehler in allen 8B-Läufen (rund 1 900 Antworten mit Grammatik).

### 5.2 Gemma, Content-Gen (Stufe 6) — KV q8_0 vs. f16 (Methode A/B #11)

70 identische Produktions-Prompts (mit Extraktionsblock), T=0,7, Maß = Anteil Bodies mit mindestens
einer erfundenen Spezifik (`pipeline.grounding.ungrounded_specifics` gegen Titel + Volltext).

| Arm | n | mit erfundenen Spezifika | Rate | ⌀ erfundene Tokens | ⌀ Wörter |
|---|---|---|---|---|---|
| q8_0 (heute) | 70 | 2 | 2,9 % | 0,03 | 149 |
| f16 | 70 | 1 | 1,4 % | 0,01 | 145 |

Fisher exakt p = 1,0. **Kein Unterschied.** (Die Rate liegt unter den 8,6 % aus #11, weil der
heutige Prompt den Extraktionsblock mit den wörtlichen Zahlen trägt — der Vergleich gilt nur
innerhalb dieser Messung.) Mit n = 70 je Arm wäre erst ein Unterschied von etwa 3 % gegen 15 %
signifikant; bei 1–3 % Grundrate ist kein Gewinn mehr messbar, egal wie groß der Arm.

### 5.3 27B, Richter (Stufe 10) — KV q4_0 vs. q8_0

150 Drafts mit Handentscheidung, Richter-Prompt wie in Produktion (12 000 Zeichen Quelle +
Extraktion + Body), Maß = `publish` ↔ published.

| Arm | n | Übereinstimmung | publish bei handpubliziert (75) | publish bei handverworfen (75) | JSON ungültig |
|---|---|---|---|---|---|
| q4_0 (heute, 256K) | 150 | 86 (57,3 %) | 23 | 12 | 0 |
| q8_0 (16K) | 150 | 82 (54,7 %) | 18 | 11 | 0 |

McNemar auf denselben Drafts: 6 : 2 diskordante Paare, p = 0,29; Fisher p = 0,73. `publish`
identisch in 142/150, Kategorie identisch in 139/150 (T=0, aber Batch-Zusammensetzung nicht
bit-deterministisch). **Kein Gewinn durch q8_0.** Nebenbefund: der Richter ist stark konservativ —
52 der 75 handpublizierten Drafts hielte er zurück, 63 der 75 handverworfenen ebenfalls; die
Handentscheidung „published" fällt oft nach Reparatur, die der Richter nicht sieht.

### 5.4 Höheres Modell-Quant — nicht gemessen

Owner-Entscheid 25.09.: keine Downloads. Rechnerisch möglich nach der Kontextverkleinerung
(Abschnitt 3): 8B `Q8_0` (8,7 GB, +3,6 GB) und 27B `UD-Q5_K_XL` (20,9 GB, +3,0 GB) bzw. knapp
`UD-Q6_K` (22,0 GB). Für Gemma existiert das QAT-Modell nur als Q4_K_XL; die Non-QAT-Q5/Q6-Dateien
(21–23 GB) sind andere Gewichte und passen mit Puffern kaum in 24 GB. Qualitätsgewinn wäre mit
denselben Sätzen (`judge_hand.jsonl`, `rel_hand.jsonl`, `gemma_ab.jsonl`) zu messen — der
Richter mit 150 Handentscheidungen ist davon der einzige Maßstab mit Trennschärfe.

### 2.4 Qwen3-Embedding-8B (Stufe 5, Titel + Teaser[:500], Pipeline schickt 24 Worker)

| Konfiguration | Slots × Kontext | conc | Anfragen/min (Dauer 25/5 s) | Prompt-Tok/s | p50 s | VRAM-Spitze MiB |
|---|---|---|---|---|---|---|
| **heute** `-c 8192 -ub 8192 -b 8192` (4 Slots auto, unified) | Pool 8 192 | 1 | 1 119 | 2 082 | 0,05 | **11 090** |
| | | 2 | 1 332 | 2 477 | 0,09 | |
| | | 4 | 1 524 | 2 846 | 0,16 | |
| | | 8 | 1 536 | 2 852 | 0,30 | |
| | | 16 | 1 620 | 2 989 | 0,59 | |
| | | 24 | **1 680** | 3 083 | 0,86 | 11 096 |
| `-c 16384 --parallel 16 --kv-unified -ub 2048 -b 2048` | Pool 16 384 | 4 / 8 / 16 / 24 | 1 344 / 1 440 / 1 584 / **1 674** | 3 083 | 0,17–0,93 | **8 552** |
| `-c 8192 --parallel 8 -ub 1024 -b 1024` | 8 × 1 024 | 4 / 8 / 16 / 24 | 1 152 / 1 305 / 1 350 / 1 272 | 2 516 | 0,20–1,10 | **6 730** |
| Produktion (Log, 3 Nächte, 24 Worker auf 4 Slots) | | 24 | 1 325–1 357 | — | — | — |

Befunde: Sättigung schon bei **4** gleichzeitigen Anfragen (+37 % gegenüber 1; 4 → 24 nur noch
+10 %). Die 24 Worker der Pipeline warten auf 4 Slots, das kostet nichts außer Latenz (0,9 s).
Der Speicher steckt nicht im KV-Cache (8 192 Token q8_0 = 0,6 GB), sondern im Compute-Puffer für
`-ub 8192`: 16 Slots mit `-ub 2048` liefern denselben Durchsatz bei 8,5 statt 11,1 GB; `-ub 1024`
kostet dann ~20 %. Da die Embedding-Phase ~1–2 min je Nacht dauert und die Karte allein hat,
ist das eine Option ohne Dringlichkeit (Stufe 5 wäre der einzige Nutznießer, wenn je ein
zweiter Prozess parallel VRAM bräuchte).

---

## 6. Empfehlungen je Modell

Reihenfolge nach Nutzen. **Produktiv umgestellt ist nichts**; jede Zeile ist eine Entscheidung.

### 6.1 Sofort und ohne VRAM-Frage: die Extraktions-Kappe reparieren (8B)

Die Zeichen-Kappe `EXTRACT_CHARS = 12 000` (`pipeline/llm_processor.py:116`) sprengt bei
nicht-lateinischen Quellen den 8 960-Token-Slot; die Sonde verlor 24 von 24 Antworten
(Abschnitt 3.1). Wirkung heute klein (2 betroffene Einträge in der DB), Ursache aber real und
unabhängig von jeder Umstellung. Zwei Wege: Token-Kappe in der Extraktion (billig, kein VRAM)
oder Slot ≥ 12 288 (`-c 196608 --parallel 16`, +1,2 GB gegenüber 6.2). **Empfehlung:** Token-Kappe.
Risiko: keins, solange die Kappe nur greift, wo sie heute schon greifen müsste.

### 6.2 8B: 16 Slots statt 24, größere Prefill-Blöcke — spart 5,5 GB für 3 % Zeit

`start-qwen3-8b-208k-ctx16.sh` (neu): `-c 143360 --parallel 16 -ub 2048 -b 2048`.
16 506 statt 22 000 MiB, 56,0 statt 57,7 Anfragen/min. Der Slot bleibt 8 960 (gleiche Kapazität
je Anfrage wie heute), es fallen nur 8 Slots weg, die nach der Sättigungsmessung nichts bringen.
Risiko: In einer Nacht mit sehr vielen gleichzeitig langen Extraktionen stehen 16 statt 24
Anfragen im Fluss — gemessen kostet das 3 %. **Nur sinnvoll, wenn die 5,5 GB gebraucht werden**
(höheres Quant, Unsloth-Parallelbetrieb). Sonst: nichts ändern.

### 6.3 Gemma: Kontext 262 144 → 16 384 — spart 4,6 GB für nichts

`start-gemma4-26b-ctx16k.sh` (neu). Gleicher Durchsatz, 15 072 statt 19 782 MiB. Der einzige
Einwand: ein künftiger Pfad, der Gemma mit einem sehr langen Prompt fährt (Newsletter über viele
Artikel, ein Dossier-Nachfolger), würde am Slot scheitern statt langsam zu werden — heute liegt
der größte reale Prompt bei 3 754 Token, der Maximalfall bei ~6 300. **Empfehlung: umstellen**,
wenn VRAM gebraucht wird; die Marge 2,6 ist komfortabel.

### 6.4 27B: Kontext 262 144 → 16 384 und KV q4_0 → q8_0 — spart 5,4 GB

`start-qwen3.8-27b-ctx16k.sh` (neu). 17 610 statt 23 094 MiB, Durchsatz −4 %, Urteile
unverändert (Abschnitt 5.3). Nebeneffekt: Die heutige Konfiguration hat nur ~1,2 GB Reserve und
kippt bei jeder Fremdbelegung in den OOM (deshalb der VRAM-Vorabcheck in `scheduled_cycle.sh`);
mit 16K sind es ~6,7 GB. **Empfehlung: umstellen** — das ist die Konfiguration mit dem besten
Verhältnis, auch ohne dass die 5,4 GB anderweitig verplant sind.

### 6.5 Embedding: 16 Slots, kleinere Batch-Puffer — spart 2,5 GB

`start-qwen3-emb-16slots.sh` (neu). Gleicher Durchsatz. Nutzen nur, wenn neben dem Embedder etwas
anderes VRAM braucht; die Phase dauert 1–2 min je Nacht. **Niedrige Priorität.**

### 6.6 Was NICHT zu empfehlen ist

* **`--kv-unified` als Sparmaßnahme:** spart beim 8B 9 GB, kostet aber 36 % Durchsatz in der
  längsten parallelen Phase. Nur nehmen, wenn 12,9 GB das Ziel sind (z. B. dauerhafter
  Parallelbetrieb mit Unsloth Studio) — dann ist `gpu-mode shared` mit
  `start-qwen3-8b-shared.sh` der etablierte Weg.
* **Mehr Slots als 16–24 beim 8B:** 48 Slots sind langsamer als 24.
* **KV-Quantisierung als Qualitätshebel:** in allen drei Vergleichen kein messbarer Unterschied
  (Abschnitt 5). Die frei werdenden GB gehören, wenn überhaupt, in ein höheres **Modell**-Quant.
* **Parallelisierung von Richter oder Review-Agent:** Gewinn unter 2 Minuten je Nacht.

### 6.7 Was der Owner entscheiden muss

1. **Umstellung ja/nein je Modell** (6.2–6.5). Jede Umstellung ist ein Eingriff in
   `pipeline/gpu_handover.MODEL_START_SCRIPTS` bzw. `scripts/scheduled_cycle.sh` — also eine
   `main`-Merge-Sache nach der konstitutionellen Regel „was nachts läuft, läuft aus `main`".
2. **Downloads** für Phase 4 (höheres Quant): 27B `UD-Q5_K_XL` (20,9 GB) passt nach 6.4,
   8B `Q8_0` (8,7 GB) nach 6.2. Ohne Download bleibt offen, ob das die Qualität hebt.
3. **Code-Parallelität in Stufe 6** (Abschnitt 4): −35 min Nachtlauf, aber Umbau an der Stelle,
   an der Garbled-Behandlung und Modellwechsel-Abbruch hängen.
4. **Extraktions-Kappe** (6.1) — unabhängig von allem anderen, geringes Risiko.

---

## 7. Wiederholbarkeit

```bash
# 1. Fenster ohne GPU-Cronjobs prüfen und Produktivserver stoppen
gpu-mode status --hours 12
systemctl --user stop llama-server.service

# 2. Prompt-Sätze aus der Live-DB bauen (liest nur)
.venv/bin/python scripts/ctx_eval/build_prompts.py 1000
.venv/bin/python scripts/ctx_eval/build_quality_sets.py 75
.venv/bin/python scripts/ctx_eval/build_probes.py

# 3. Messblöcke (Testserver auf :8190, nie über start-*.sh)
scripts/ctx_eval/run_server.sh start start-qwen3-8b-208k.sh 8b-prod
.venv/bin/python scripts/ctx_eval/bench_parallel.py --prompts data/ctx_eval/prompts/8b_stage234.jsonl \
    --concurrency 8,16,24,32 --duration 150 --ramp 45 --label 8b-prod --out data/ctx_eval/results.jsonl
scripts/ctx_eval/run_server.sh stop
scripts/ctx_eval/matrix.sh gemma   # bzw. 27b | emb; 8B-Varianten: block_8b.sh

# 4. Auswertung
.venv/bin/python scripts/ctx_eval/summarize_results.py            # Markdown-Tabelle
.venv/bin/python scripts/ctx_eval/quality_eval.py --kind judge \
    q4_0=data/ctx_eval/q_judge_q4.jsonl q8_0=data/ctx_eval/q_judge_q8.jsonl
.venv/bin/python scripts/ctx_eval/llama_log_stats.py /tmp/llama-server.log

# 5. IMMER: Produktion wiederherstellen
gpu-mode catandary
readlink ~/llama.cpp/start-active.sh   # muss start-qwen3-8b-208k.sh sein
curl -s http://127.0.0.1:8090/v1/models
```

Vollständige Ergebnistabelle aller Messstufen: [`docs/context_parallel_eval_2026-09-25_results.md`](context_parallel_eval_2026-09-25_results.md) (versioniert; erzeugt aus dem nicht versionierten `data/ctx_eval/results.jsonl`).

---

## 8. Umstellung auf `dev` (25.09.2026) und Testlauf

Umgestellt wurden die beiden Modelle aus den Empfehlungen 6.3 und 6.4; das 8B und der Embedder
bleiben unverändert (6.2/6.5 werden nicht empfohlen, solange das VRAM nicht gebraucht wird).

| Stelle | vorher | jetzt (`dev`) |
|---|---|---|
| `pipeline/gpu_handover.py` `MODEL_START_SCRIPTS[gemma…gguf]` | `start-gemma4-26b.sh` | `start-gemma4-26b-ctx16k.sh` |
| `pipeline/gpu_handover.py` `MODEL_START_SCRIPTS["Qwen3.8-27B"]` | `start-qwen3.8-27b.sh` | `start-qwen3.8-27b-ctx16k.sh` |
| `pipeline/draft_judge.py` `JUDGE_START_SCRIPT` | `start-qwen3.8-27b.sh` | `start-qwen3.8-27b-ctx16k.sh` |
| `scripts/scheduled_cycle.sh` `STAGE5_START` | `start-gemma4-26b.sh` | `start-gemma4-26b-ctx16k.sh` |
| `scripts/scheduled_cycle.sh` Stage-10-`ln -sf` | `start-qwen3.8-27b.sh` | `start-qwen3.8-27b-ctx16k.sh` |
| `scripts/weekly_newsletter_publish.sh`, `scripts/newsletter_tonight.sh` | `start-gemma4-26b.sh` | `start-gemma4-26b-ctx16k.sh` |

Der Ruhezustand (`CANONICAL_RESTING_SCRIPT` → `start-qwen3-8b-208k.sh`) ist unberührt, ebenso der
Embedding-Pfad. Die alten Skripte liegen unverändert in `~/llama.cpp` — Rückweg ist, die sechs
Stellen wieder auf sie zeigen zu lassen. **Nach der konstitutionellen Regel ist die Umstellung
erst mit dem Merge nach `main` in Betrieb**; der Nachtlauf startet aus
`~/projects/catandary-trends`.

Testsuite nach der Umstellung: 1 299 bestanden, 20 übersprungen.

### 8.1 Testlauf: echter Pipeline-Batch

`scripts/ctx_eval/testrun_batch.sh 100` setzt dieselbe Umgebung wie `scheduled_cycle.sh`
(`STAGE5_BACKEND`/`STAGE_8B_BACKEND`/`EMBED_BACKEND=llamacpp`, `LLAMACPP_MAX_TOKENS=2048`,
`DISTILL_SIGNAL_TYPE=1`) und fährt `pipeline.run_full_cycle --batch 100`; ein Sampler schreibt
alle zwei Sekunden VRAM und geladenes Modell mit.

**Phase 1 (Backlog, 7 Einträge)** — testet beide Handover-Richtungen:

| Ereignis | Beobachtung |
|---|---|
| Handover 8B | `already serving Qwen3-8B-UD-Q4_K_XL.gguf — nothing to do` (Ruhezustand unverändert) |
| Stufen 2–4 (hybrid) | 3,7 s, 7 Überlebende |
| Stufe 5 (Embeddings) | 61,7 s, 7 Cache-Treffer |
| Handover Gemma | `Pre-flight OK: start-gemma4-26b-ctx16k.sh loads gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf`, danach `ready` nach 12 s |
| Server-Konfiguration | `n_slots = 1, n_ctx_slot = 16384, kv_unified = 'false'` |
| **VRAM unter Last** | **15 060 MiB** (Messung vom Nachmittag: 15 072 MiB, heute produktiv: 19 782) |
| Stufe 6 | 46,0 s, 5 Artikel, 2 vom Garbage-Guard zurückgehalten (`too_short:46w`, `too_short:53w`) |
| Rückgabe | `Restoring start-active.sh → start-qwen3-8b-208k.sh`, 8B wieder bereit nach 9 s |
| Stufen 7–9 | 5 Trends angelegt, 1 reklassifiziert, 1 auto-publiziert |

Zu den zwei zurückgehaltenen Artikeln: Beide Quellen sind dünn (384 und 657 Zeichen Quelltext),
beide Einträge wurden im Nachtlauf desselben Tages um 02:53 geholt und dort schon liegen gelassen
— der Backlog besteht genau aus den Resten, die Stufe 6 bereits einmal garbled zurückgab
(`garbled_ids`, siehe `scheduled_cycle.sh`). Der Guard `too_short` greift unterhalb von 60 Wörtern
und hat mit dem Kontextfenster nichts zu tun: Der Prompt passt in 16 384 Token mit Faktor 4.

**Phase 2 (Feed-Poll)** und **Phase 3 (Batch 100)** folgen im selben Lauf; Phase 3 durchläuft
dieselben Handover noch einmal, diesmal mit voller Batchgröße.

**Phase 3 (Batch 100 nach dem Poll)** — 2 336 neue Einträge geholt, 100 verarbeitet:

| Stufe | Dauer | Ergebnis |
|---|---|---|
| Stufe 1 (Titel-Dedup) | 9,0 s | 100 → 91 |
| Embedding-Handover | 4 s Start | `start-qwen3-emb.sh`, danach zurück aufs 8B |
| Stufen 2–4 (hybrid) | 60,4 s | 45 Distill-behalten, 13 ans 8B, 33 verworfen → 54 Überlebende |
| Stufe 5 | 53,5 s | 54 Überlebende |
| Handover Gemma | 8 s Start | `n_slots = 1, n_ctx_slot = 16384`; **VRAM 15 048–15 060 MiB** |
| Stufe 6 | 165,5 s | 50 Artikel, **4 am Guard zurückgehalten**; 3,1 s je Artikel — das ist NICHT mit dem Nachtlauf (3,47 s) vergleichbar, die Testkohorte hat kürzere Quellen und damit kürzere Prompts und Artikel (sauberer Tempo-Vergleich: 8.5) |
| Stufen 7–9 | 26 s | 50 Trends, 11 reklassifiziert, 36 auto-publiziert |
| Gesamt | 1 187 s | inkl. Poll über 560 Feeds |

Alle Handover liefen in beide Richtungen sauber, der Ruhezustand wurde jedes Mal
wiederhergestellt (`Restoring start-active.sh → start-qwen3-8b-208k.sh`), kein
`ModelMismatchError`, kein Abbruch.

### 8.2 Gegenprobe: liegt die Guard-Quote am Kontext oder an der Kohorte?

Vier von 54 Artikeln (7,4 %) hielt der harte Guard mit `too_short` zurück (40–55 Wörter), im
Nachtlauf vom 25.09. waren es 6 von 1 754 (0,3 %). Erste Erklärung liegt in den Daten:

| Kohorte | Einträge | Quelltext-Median | unter 1 000 Zeichen |
|---|---|---|---|
| Testlauf 21:27 (frisch gepollt) | 50 | **383 Zeichen** | 34 (68 %) |
| Nachtlauf 25.09. 02:45 | 1 753 | **3 314 Zeichen** | 312 (18 %) |

Das Modell kann keine Wörter schreiben, die in der Quelle nicht stehen — genau dafür wurde die
Wort-Untergrenze am 24.09. an `STAGE5_BREVITY_MIN_SOURCE_CHARS` gebunden. Die vier betroffenen
Quellen haben 188, 384, 475 und 657 Zeichen.

Weil „plausibel" kein Beleg ist, wurde gegengeprobt: dieselben 39 Content-Prompts der dünnsten
Einträge dieses Laufs (< 1 500 Zeichen Quelltext), einmal auf `start-gemma4-26b-ctx16k.sh`,
einmal auf `start-gemma4-26b.sh` (262 144), gleiche Temperatur 0,7, sequentiell
(`scripts/ctx_eval/build_thin_ab.py`, `block_thin_ab.sh`, `thin_ab_eval.py`):

| Arm (39 Prompts, Quelltext < 1 500 Zeichen) | Median Wörter | unter 60 (harter Guard) | unter 25 (Stub) |
|---|---|---|---|
| `start-gemma4-26b-ctx16k.sh` | 69 | 12 | 0 |
| `start-gemma4-26b.sh` (262 144) | 71 | 8 | 0 |

Gepaart über dieselben 39 Prompts: Fisher p = 0,44, Wilcoxon über die Wortzahlen p = 0,15.
**Beide Arme liegen bei dünnen Quellen zwischen 20 und 30 % unter der Grenze** — die Quote ist ein
Kohorten-Effekt, kein Kontext-Effekt. Der Unterschied 12 zu 8 ist bei n = 39 nicht von Rauschen zu
trennen; die Gegenprobe kann einen kleinen Nachteil also nicht ausschließen, nur einen großen.
Deshalb zusätzlich dieselbe Messung auf der **repräsentativen** Kohorte (150 Prompts, Quelltext-
Median 3 052 Zeichen, also wie im Nachtlauf mit 3 314):

| Arm (150 Prompts, Quelltext-Median 3 052 Zeichen) | Median Wörter | unter 60 | Bodies mit erfundenen Spezifika |
|---|---|---|---|
| `start-gemma4-26b-ctx16k.sh` | 154 | **5** | **5** (3,3 %) |
| `start-gemma4-26b.sh` (262 144) | 156 | **5** | **8** (5,3 %) |

Gepaart über dieselben 150 Prompts: Guard-Quote **identisch** (Fisher p = 1,0), Grounding ohne
Unterschied (Fisher p = 0,57, Richtung sogar leicht zugunsten des kleineren Kontexts),
Wortzahl-Verteilung p = 0,054 bei zwei Wörtern Median-Differenz — statistisch grenzwertig,
praktisch bedeutungslos. **Der Kontext ändert die Artikel nicht.** Die 7,4 % des Testlaufs
stammen aus seiner dünnen Kohorte, nicht aus der Umstellung.

### 8.3 Testlauf Stufe 10 (Draft-Richter auf dem 16K/q8_0-27B)

`scripts/ctx_eval/testrun_judge.sh 17` bildet den Stage-10-Block aus `scheduled_cycle.sh` nach
(Unit stoppen, VRAM-Vorabcheck, Symlink, Identitätscheck, richten, Ruhezustand per `trap`
wiederherstellen) und beurteilt die Entwürfe, die der Testlauf hinterlassen hat.

| Ereignis | Beobachtung |
|---|---|
| Symlink + Start | `start-qwen3.8-27b-ctx16k.sh`, Server nach ~12 s bereit |
| Identitätscheck | `served = models/Qwen3.8-27B-UD-Q4_K_XL.gguf` — der `grep -q "Qwen3.8-27B"` aus `scheduled_cycle.sh` greift unverändert |
| Server-Konfiguration | `n_slots = 1, n_ctx_slot = 16384, kv_unified = 'false'` |
| **VRAM unter Last** | **17 608 MiB** (Messung vom Nachmittag: 17 610; heute produktiv: 23 094) |
| Urteile | 17 beurteilt, 4 freigegeben, 13 zurückgehalten, 0 Gate-Blocks, 0 Dubletten, 0 garbled, **0 Fehler** |
| Dauer | 59 s für 17 Entwürfe = **3,5 s je Entwurf** |
| Ruhezustand | per `trap` automatisch auf `start-qwen3-8b-208k.sh` zurück, `:8090` serviert wieder das 8B |

### 8.4 Bilanz des Testlaufs

| | vorher (Produktion) | nachher (dev) |
|---|---|---|
| Gemma VRAM unter Last | 19 782 MiB | **15 048–15 060 MiB** |
| 27B VRAM unter Last | 23 094 MiB | **17 608 MiB** |
| freie Reserve beim Richter | ~1,2 GB | **~6,7 GB** |
| Stufe 6 je Artikel | 3,47 s (Nachtlauf, andere Kohorte) | 3,1 s (Testkohorte) — **nicht vergleichbar**, s. 8.5 |
| Stufe 10 je Entwurf | 2,1–3,0 s | 3,5 s (kleine Kohorte, Prefill-dominiert) |
| Artikelqualität | — | unverändert (150 gepaarte Prompts: Guard-Quote identisch, Grounding p = 0,57) |
| Fehler im Lauf | — | keine: 0 Modellwechsel-Abbrüche, 0 Gate-Blocks, 0 JSON-Fehler |

Was der Testlauf **nicht** zeigt: ob ein sehr langer Prompt (Newsletter über viele Artikel, ein
künftiger Pfad mit großem Kontext) im 16K-Fenster scheitern würde. Die Maximalfall-Sonden aus
Abschnitt 3.1 decken den heutigen Code ab (Gemma 4 358, Richter 9 165 Token), ein neuer Pfad mit
deutlich längeren Prompts müsste erneut geprüft werden.

### 8.5 Tempo: kein belastbarer Unterschied

Die Umstellung spart Speicher, nicht Zeit. Gepaart gemessen (identische Prompts, dieselbe
Maschine, nur `-c` ändert sich):

| Messung | 16 384 | 262 144 | Differenz |
|---|---|---|---|
| 150 Content-Prompts (repräsentativ) | 440,5 s | 452,4 s | **2,6 % schneller** |
| 39 Content-Prompts (dünne Quellen) | 61,1 s | 63,9 s | **4,4 % schneller** |
| Gemma Dauerlast conc 1 (Nachmittag) | 19,2 Anfragen/min | 19,3 | **0,5 % langsamer** |
| Richter Dauerlast (Nachmittag) | 21,6 Anfragen/min | 22,4 | **3,6 % langsamer** |

Die Richtung kippt zwischen den Messreihen, der Betrag bleibt unter 5 % — das ist Rauschen,
kein Effekt. Auch theoretisch ist keiner zu erwarten: Die Attention läuft über die tatsächlich
belegten Zellen, nicht über den reservierten Kontext; ein kleineres `-c` spart Allokation,
keine Rechenzeit.

**Die 3,1 s je Artikel im Testlauf gegen 3,47 s im Nachtlauf sind kein Beleg für Tempo.** Die
Testkohorte hat einen Quelltext-Median von 383 Zeichen gegen 3 314, also kürzere Prompts
(weniger Prefill) und kürzere Artikel (weniger Generierung). Ein Kohortenvergleich misst die
Kohorte, nicht die Konfiguration.
