# Query-Quality-Gate für die Technologie-Suche (#67) — Messung und Regel, 2026-09-04

**Frage:** Woran erkennt die Technologie-Suche (`/trends/foresight/technology`, `scripts/tech_analyze.py`)
GPU-frei, dass eine Anfrage keine Technologie ist („unicorn breeding", „my cat is sad on tuesdays") oder
still im falschen Patentfeld landet („quantum error correction" → klassische Kanalcodierung H03M13)?
Das alte Gate war reine Nächst-Distanz (`OFF_TOPIC_DIST = 0.55`); der Audit-Kommentar vom 15.08. schlug
Margin, Volltext-Treffer und Kohärenz vor. **Ergebnis: Margin und Kohärenz trennen nicht — der 20. Nachbar
und der Titel-Index tun es.**

## Testset und Messung

* **26 Technologien** (die vier Beispiel-Chips + bekannte Domänen quer durch die CPC-Sektionen),
  **25 Unsinns-/Alltagsanfragen**, **8 graue Phrasen** (abstrakte Trends, Firmenname, Ein-Wort-Begriffe —
  informativ, zählen nicht in die Abnahme).
* Vektoren: Qwen3-Embedding-8B-Q4_K_M (Produktionsmodell, 1024-dim-Truncation wie `embed_query`),
  Signale gegen die Live-DB (`cpc_fine`, `patent_search` + `patent_cpc_full`), read-only.
  Alles gecacht in `tests/fixtures/tech_query_gate.json` → `tests/test_query_gate.py` läuft ohne GPU und DB.
  Neu messen (z. B. nach Embedding-Modellwechsel): `LLAMACPP_HOST=… python scripts/measure_query_gate.py`.
* Signale pro Anfrage (alle in `pipeline/query_gate.py`, ein pgvector-Query + zwei GIN-Lookups, 0,03–0,33 s):
  `d1` (nächste Klasse), `d20` (20. Klasse, `n_patents ≥ 50` wie in `resolve_domain`), Margin `d20−d1`,
  CPC-Sektionen/-Subklassen der Top-12, Titel-Treffer `and_hits` (`websearch_to_tsquery` gegen
  `patent_search.tsv`, Zählung bei 5001 gekappt) und das **Wort-Feld**: CPC-Subklassen-Verteilung von bis
  zu 300 Titeltreffern (Y-Sektion ausgeschlossen — Y02E dominiert jeden Batterie-/Solar-Titel, ist aber
  kein Feld).

## Trennschärfe

| Signal | Technologie (min … max) | Unsinn (min … max) | trennt? |
|---|---|---|---|
| Nächst-Distanz d1 | 0.145 (heat pump) … 0.304 (quantum error correction) | 0.228 (recipe for pancakes) … 0.573 (cheap flights to rome) | nein |
| Margin d20−d1 | 0.025 (semiconductor lithography) … 0.141 (carbon capture and storage) | 0.021 (lorem ipsum dolor) … 0.212 (the weather tomorrow) | nein |
| CPC-Sektionen in Top-12 | 1 (CRISPR base editing) … 4 (organic light-emitting diode display) | 1 (dragon taming school) … 5 (my neighbour is loud) | nein |
| 20. Nachbar d20 | 0.202 (semiconductor lithography) … 0.343 (quantum error correction) | 0.381 (recipe for pancakes) … 0.605 (cheap flights to rome) | **ja** (Lücke 0,343–0,381) |
| Titel-Treffer (AND, Clamp 5001) | 4 (perovskite tandem photovoltaics) … 5001 (wireless charging) | 0 (asdf qwerty) … 5001 (what time is it) | teilweise (0 bei 14/25 Unsinn, tech ≥ 4) |

* **d1 trennt nicht** (Kernbefund von #67): „recipe for pancakes" liegt bei 0,228 näher an A21D13/44 als
  „quantum error correction" (0,304) an irgendeiner Klasse; „the weather tomorrow" 0,262 (G01W2203/00).
* **Margin trennt nicht:** die „flache Schulter"-Hypothese ist widerlegt — Unsinn kann *eine* zufällig nahe
  Klasse haben und dann nichts („best pizza in berlin" Margin 0,155, „the weather tomorrow" 0,212).
* **Sektions-Streuung trennt nicht:** echte Technologien streuen oft über 2–4 Sektionen (Material + Verfahren
  + Gerät: „carbon capture and storage" 6 Subklassen, „microfluidic lab-on-a-chip" 6).
* **d20 trennt mit Lücke:** eine echte Technologie hat ≥ 20 Geschwisterklassen innerhalb ~0,34; eine
  Unsinnsphrase höchstens ein paar zufällige Nachbarn, dann nichts. Grauzone 0,343–0,381 ist leer.
* **Titel-Index** ist das zweite, unabhängige Signal (Absicherung gegen Embedding-Drift: ein Modellwechsel
  verschiebt alle Distanzen, `tech_query.py:218`): 14/25 Unsinnsphrasen haben 0 Titel mit allen Termen,
  jede Technologie ≥ 4.
* **Wort-Feld-Abgleich** findet den Issue-Fall: „quantum error correction" embedded zu 92 % in H03M
  (klassische Fehlerkorrektur), aber 55 % der Titeltreffer tragen G06N (Quantencomputing, G06N10/70 =
  „Quantum error correction"). Bei den Technologien, deren Wort-Feld vom Embedding-Feld abweicht, bleibt
  der Anteil unter 0,13 („metal powder 3D printing" B33Y 0,12, „heat pump" D06F 0,06).

## Gate-Regel (`pipeline/query_gate.py`)

```
off_topic   d20 > D20_MAX (0,36)  oder  and_hits == 0  oder  d1 > 0,55 (Sanity)
ambiguous   Wort-Feld (≥ FT_FIELD_MIN_HITS = 20 Titeltreffer, Anteil ≥ FT_FIELD_MIN_SHARE = 0,40,
            ohne Y) ist NICHT unter den Embedding-Subklassen der Top-12
ok          sonst — unveränderter schneller Pfad
```

* `off_topic` antwortet ehrlich: „We don't see a technology signature for …" + 2–3 nächste **echte** Felder
  (eine pro CPC-Hauptgruppe, lesbare Titel ohne Querverweise) als klickbare Vorschläge — keine Zahl.
* `ambiguous` zeigt die Feldwahl (Wort-Feld zuerst, dann die Embedding-Felder je Subklasse) **vor** jeder
  Analyse; der Klick läuft `?q=…&codes=…` → Analyse exakt dieser Klassen (Vektor aus dem Cache in `data/`,
  kein zweiter GPU-Handover).
* Ein LLM-Klassifikator (8B) war nicht nötig — die Heuristik trennt das Testset vollständig.

## Ergebnis auf dem Testset

| Gruppe | ok | ambiguous | off_topic |
|---|---|---|---|
| Technologie (26) | 25 | 1 („quantum error correction" — der Issue-Fall) | 0 |
| Unsinn/Alltag (25) | 0 | 0 | 25 |
| grau (8) | 2 („artificial intelligence", „nanotechnology") | 0 | 6 |

Abnahme (Issue): „unicorn breeding" → Rückfrage mit *Animals characterised by species · Instruments or
methods for reproduction or fertilisation · Rearing or breeding invertebrates* (0,5 s statt 88 s falscher
Analyse); „quantum error correction" → Feldwahl G06N (Quantum error correction, detection or prevention …)
vs. H03M vs. H04L (1,9 s); Beispiel-Chips → `ok`, Gate-Overhead 0,03–0,27 s bei ~60–100 s Gesamtlaufzeit
(Trajektorien-SQL dominiert, vorher wie nachher). „my cat is sad on tuesdays" (d1 0,515, unter dem alten
Gate): d20 0,572 → Rückfrage.

**Bekannte Grenzen:** breite Ein-Wort-Begriffe fallen auf die Unsinns-Seite der Lücke („blockchain" d20
0,396 trotz d1 0,258 auf H04L9/50 — die Vorschläge führen aber direkt in das Feld). Die Schwellen gelten
für das aktuelle Embedding-Modell; nach einem Wechsel Fixture neu messen und `D20_MAX` gegen die neue
Lücke setzen (Test `test_d20_threshold_sits_in_the_measured_gap` schlägt sonst an).

## Messtabelle (alle 59 Phrasen)

`emb top` = dominante Embedding-Subklasse der Top-12, `words top (share)` = dominante Subklasse der
Titeltreffer (ohne Y) mit Anteil an der 300er-Stichprobe.

| group | query | d1 | d20 | margin20 | sect12 | subcl12 | emb top | and_hits | words top (share) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| tech | processed cheese | 0.187 | 0.222 | 0.035 | 1 | 2 | A23C | 2911 | A23C (0.60) | **ok** |
| tech | solid-state battery electrolyte | 0.152 | 0.270 | 0.119 | 1 | 1 | H01M | 1340 | H01M (0.06) | **ok** |
| tech | mRNA vaccine manufacturing | 0.274 | 0.327 | 0.053 | 2 | 2 | C12N | 37 | A61K (0.27) | **ok** |
| tech | perovskite tandem solar cells | 0.243 | 0.334 | 0.091 | 1 | 2 | H10F | 13 | H02S (0.08) | **ok** |
| tech | perovskite tandem photovoltaics | 0.245 | 0.327 | 0.083 | 1 | 3 | H10F | 4 | H10K (0.25) | **ok** |
| tech | CRISPR base editing | 0.237 | 0.336 | 0.098 | 1 | 1 | C12N | 626 | C12N (0.46) | **ok** |
| tech | quantum error correction | 0.304 | 0.343 | 0.039 | 1 | 2 | H03M | 1227 | G06N (0.55) | **ambiguous** |
| tech | lithium-ion battery cathode | 0.224 | 0.261 | 0.037 | 1 | 1 | H01M | 280 | H01M (0.09) | **ok** |
| tech | heat pump | 0.145 | 0.242 | 0.097 | 2 | 4 | F24D | 5001 | D06F (0.06) | **ok** |
| tech | vertical farming | 0.224 | 0.302 | 0.078 | 1 | 1 | A01G | 1000 | A01G (0.21) | **ok** |
| tech | hydrogen electrolysis | 0.157 | 0.242 | 0.085 | 3 | 4 | C25B | 5001 | C25B (0.46) | **ok** |
| tech | carbon capture and storage | 0.174 | 0.314 | 0.141 | 4 | 6 | Y02C | 673 | G06Q (0.08) | **ok** |
| tech | metal powder 3D printing | 0.172 | 0.222 | 0.051 | 1 | 1 | B22F | 556 | B33Y (0.12) | **ok** |
| tech | lidar sensors for autonomous vehicles | 0.215 | 0.272 | 0.057 | 3 | 5 | G01S | 423 | G01S (0.71) | **ok** |
| tech | organic light-emitting diode display | 0.162 | 0.223 | 0.061 | 4 | 4 | H10K | 556 | H10K (0.67) | **ok** |
| tech | wind turbine blade | 0.153 | 0.246 | 0.093 | 2 | 5 | B29L | 5001 | F03D (0.60) | **ok** |
| tech | semiconductor lithography | 0.177 | 0.202 | 0.025 | 1 | 2 | G03F | 310 | G03F (0.48) | **ok** |
| tech | precision fermentation | 0.237 | 0.264 | 0.028 | 2 | 5 | A23V | 636 | C12R (0.07) | **ok** |
| tech | gene therapy viral vectors | 0.193 | 0.228 | 0.035 | 1 | 1 | C12N | 1661 | C12N (0.56) | **ok** |
| tech | wireless charging | 0.270 | 0.332 | 0.063 | 2 | 3 | H02J | 5001 | H02J (0.47) | **ok** |
| tech | robotic surgery | 0.181 | 0.248 | 0.067 | 1 | 1 | A61B | 4901 | A61B (0.67) | **ok** |
| tech | microfluidic lab-on-a-chip | 0.204 | 0.273 | 0.069 | 2 | 6 | B81B | 12 | B01L (0.33) | **ok** |
| tech | plant-based meat extrusion | 0.168 | 0.256 | 0.088 | 1 | 4 | A22C | 56 | A23J (0.41) | **ok** |
| tech | sodium-ion battery | 0.268 | 0.315 | 0.047 | 1 | 1 | H01M | 1289 | H01M (0.03) | **ok** |
| tech | silicon photonics | 0.259 | 0.338 | 0.079 | 2 | 4 | G02F | 987 | G02B (0.41) | **ok** |
| tech | insulin pump | 0.285 | 0.328 | 0.042 | 1 | 1 | A61M | 1403 | A61M (0.56) | **ok** |
| nonsense | unicorn breeding | 0.350 | 0.395 | 0.045 | 1 | 3 | A01K | 2 | A01K (0.50) | **off_topic** |
| nonsense | my cat is sad on tuesdays | 0.515 | 0.572 | 0.056 | 2 | 6 | A01K | 0 | — | **off_topic** |
| nonsense | best pizza in berlin | 0.347 | 0.502 | 0.155 | 2 | 3 | A21D | 0 | — | **off_topic** |
| nonsense | how to be happy | 0.459 | 0.503 | 0.044 | 2 | 5 | A47G | 2305 | G06F (0.18) | **off_topic** |
| nonsense | what time is it | 0.354 | 0.418 | 0.064 | 2 | 4 | G04G | 5001 | — | **off_topic** |
| nonsense | birthday party ideas | 0.414 | 0.476 | 0.063 | 2 | 4 | A41B | 0 | — | **off_topic** |
| nonsense | why is the sky blue | 0.436 | 0.494 | 0.058 | 3 | 4 | C09B | 1128 | A61B (0.09) | **off_topic** |
| nonsense | cheap flights to rome | 0.573 | 0.605 | 0.031 | 3 | 5 | A23L | 0 | — | **off_topic** |
| nonsense | funny dog videos | 0.483 | 0.536 | 0.053 | 1 | 4 | A47K | 0 | — | **off_topic** |
| nonsense | meaning of life | 0.474 | 0.503 | 0.029 | 2 | 7 | A41B | 5001 | G06F (0.14) | **off_topic** |
| nonsense | harry potter fan fiction | 0.553 | 0.585 | 0.031 | 1 | 2 | H04L | 0 | — | **off_topic** |
| nonsense | football world cup winner | 0.392 | 0.520 | 0.128 | 2 | 3 | A63B | 1 | A63F (1.00) | **off_topic** |
| nonsense | asdf qwerty | 0.356 | 0.420 | 0.064 | 3 | 5 | B41J | 0 | — | **off_topic** |
| nonsense | lorem ipsum dolor | 0.447 | 0.468 | 0.021 | 2 | 3 | G09F | 0 | — | **off_topic** |
| nonsense | my neighbour is loud | 0.401 | 0.437 | 0.036 | 5 | 5 | E04B | 5 | H04R (0.40) | **off_topic** |
| nonsense | recipe for pancakes | 0.228 | 0.381 | 0.153 | 1 | 2 | A21D | 13 | A21D (0.54) | **off_topic** |
| nonsense | who won the election | 0.413 | 0.533 | 0.120 | 3 | 6 | A63F | 18 | A63F (0.28) | **off_topic** |
| nonsense | tax return deadline | 0.378 | 0.502 | 0.124 | 1 | 3 | G06Q | 0 | — | **off_topic** |
| nonsense | monday morning blues | 0.507 | 0.537 | 0.030 | 1 | 2 | C07K | 0 | — | **off_topic** |
| nonsense | the weather tomorrow | 0.262 | 0.474 | 0.212 | 4 | 6 | G01W | 10 | G06F (0.20) | **off_topic** |
| nonsense | love poems for her | 0.522 | 0.549 | 0.027 | 1 | 4 | A41B | 4 | E04H (0.25) | **off_topic** |
| nonsense | dragon taming school | 0.374 | 0.425 | 0.051 | 1 | 2 | A63H | 0 | — | **off_topic** |
| nonsense | invisible pink elephant | 0.363 | 0.411 | 0.048 | 2 | 5 | A63J | 0 | — | **off_topic** |
| nonsense | hello world | 0.527 | 0.551 | 0.025 | 2 | 3 | C12Y | 3 | G06F (0.33) | **off_topic** |
| nonsense | stock market crash prediction | 0.338 | 0.446 | 0.109 | 3 | 6 | G06Q | 0 | — | **off_topic** |
| grey | future of work | 0.394 | 0.464 | 0.070 | 1 | 2 | G06Q | 3132 | G06Q (0.42) | **off_topic** |
| grey | artificial intelligence | 0.305 | 0.349 | 0.044 | 2 | 6 | Y10S | 5001 | G06F (0.31) | **ok** |
| grey | blockchain | 0.258 | 0.396 | 0.139 | 2 | 2 | H04L | 5001 | G06Q (0.24) | **off_topic** |
| grey | sustainable fashion | 0.334 | 0.391 | 0.057 | 3 | 6 | A41F | 162 | A61K (0.41) | **off_topic** |
| grey | Tesla | 0.382 | 0.420 | 0.038 | 2 | 7 | B60Y | 1404 | G06F (0.26) | **off_topic** |
| grey | climate change | 0.366 | 0.428 | 0.062 | 3 | 5 | Y02A | 2445 | G06Q (0.21) | **off_topic** |
| grey | digital transformation | 0.353 | 0.392 | 0.040 | 1 | 2 | G06Q | 5001 | G06T (0.18) | **off_topic** |
| grey | nanotechnology | 0.245 | 0.322 | 0.078 | 3 | 6 | B82Y | 2025 | A61K (0.33) | **ok** |

## Nachtrag 04.09. (09:00): breite Ein-Wort-Begriffe

Owner-Vorgabe: breite, aber echte Technologiebegriffe dürfen nicht als `off_topic` enden. Regel ergänzt
(`pipeline/query_gate.py`, Commit `8fa24bb`): bei d20 > `D20_MAX` mit ≥ `FT_BROAD_MIN_HITS` Titeltreffern
**und** Feldüberlappung der Wort-Treffer mit den Embedding-Nachbarn → `ambiguous` mit `broad=True`
(Feldwahl „zu breit — meintest du …?") statt Sperre. Fixture auf 68 Einträge erweitert (Live-Vektoren
04.09. vor dem Cycle, CPU-only-Embedding-Server).

| Set | Query | Verdict |
|---|---|---|
| breit/Technologie | blockchain | **ambiguous** (broad) |
| breit/Technologie | graphene, photonics, biometrics, robotics | ok |
| breit/Unsinn | happiness, tuesday, unicorn, weather | off_topic |
| breit/Unsinn | pizza | **ambiguous** (broad) — echtes Patentfeld A21D13/41 (Pizza-Herstellung), bewusst: Feldwahl statt Sperre |

Akzeptanz unverändert: 0 falsche Freigaben im Unsinns-Set, keine Sperre einer echten Technologie; 39 Gate-Tests.
