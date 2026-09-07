# Wo der Hebel liegt — Dossier-Werkzeug vs. Deep Research (Testthema GLP-1)

Stand 2026-09-06 · Repo `/home/dirk/projects/ct-dev`, Branch `dev` · READ-ONLY-Analyse
Zielbild: Arm A (heute) / Arm B (überarbeitet) / Arm C (Sonnet-Deep-Research über das offene Web),
blind bewertet nach Belegbarkeit, Spezifität, Handlungsrelevanz, Korrektheit, Abdeckung der
Innovationskette, Ehrlichkeit über Grenzen.

---

## 0. Das Ergebnis in zwei Sätzen

Das Werkzeug **misst** zwar (`pipeline/dossier_quant.py` → `scripts/tech_analyze.py`), aber die
Messung erreicht den Bericht nie: In **13 von 13** gespeicherten Läufen wurde die Mess-Quelle
`Q1` **kein einziges Mal zitiert**, und auf dem Testthema selbst hat die Messkette gar nicht erst
gestartet — der GLP-1-Lauf von heute Abend (`dossiers.id=13`) trägt
`quant = {"off_topic": true, "nearest_dist": 0.266}`, weil die Auftragsphrase
„GLP-1 **and incretin technology**" **null** Patenttreffer erzeugt (nachgemessen; „GLP-1 receptor
agonist" erzeugt ≥ 2.000). Was bleibt, ist ein Web-Rechercheur mit einem schwächeren Modell und
einem kleineren Web — genau der Vergleich, den Arm C gewinnt.

Der Hebel liegt deshalb **nicht** in besserer Prosa, sondern darin, (1) die Messung auf dem
Thema überhaupt anspringen zu lassen und (2) gerechnete Zeitreihen bis in den Berichtstext zu
bringen. Die Zeitreihen existieren bereits berechnet und werden vor dem ersten Modell-Hop
weggeworfen (§1 Phase 1, §3.1).

---

## 1. Ist-Analyse: der Ablauf in Phasen

Einstieg: `scripts/dossier_worker.py` → Phase 1 `pipeline/dossier_quant.build_quant_evidence`
(Embedding-Handover) → Phase 2 `scripts/corpus_research.run()` (27B-Handover) →
`pipeline/dossier_check.py` → `dossiers(slug, version)`, Status `review`.

### Phase 0 — Auftrag und Fragebau

* `scripts/corpus_research.py:906-922` `foresight_question(topic)` baut die Standardfrage
  („Reconstruct the commercialisation trajectory of …"). Sie nennt bewusst **keine Akteure** —
  die sollen aus dem Korpus kommen.
* `corpus_research.py:1483-1485` `--focus` hängt einen Zusatzschwerpunkt an.
* **Was NICHT passiert:** die Frage enthält keinerlei Messauftrag. Es wird nirgends verlangt,
  Zahlen aus dem Korpus zu berichten. Der Bericht-Prompt (`REPORT_SYSTEM:267-293`) verlangt
  Zitate, Trennung von Beleg/Vermutung und Ehrlichkeit — aber **kein einziges Mal** eine
  gemessene Größe.

### Phase 1 — Messung (deterministisch, vor dem ersten Modell-Hop)

* `pipeline/dossier_quant.py:184-205` ruft `scripts/tech_analyze.analyze_query(topic)`.
* `tech_analyze.py:251-284`: Query → Embedding (`cached_embed`) → `query_gate.gate` →
  `resolve_candidates` (max `MAX_CANDIDATES = 12` CPC-Klassen, `tech_analyze.py:62`) →
  `tir_trajectory.trajectory()` (K(t) über den Patent-Zitationsgraphen) →
  `tech_analyze.leadtime()` (vier Reifegrade) → `top_patents(sel, limit=8)`.
* `dossier_quant.py:59-181` formatiert daraus **eine Textnotiz** und
  `MAX_HUB_PATENTS = 5` (`:34`) Leitpatent-Quellen `Q2…Q6`.
* Ehrlichkeitsgrenzen stehen wörtlich drin (`_CAVEATS`, `:37-43`): Kalibrierung nur bis ~2019,
  Patent ≠ Produkt, Datenfenster ab 1990.

**Was NICHT passiert (der zentrale Befund):**

`tech_analyze.leadtime()` liefert je Reifegrad ein **vollständiges Jahres-Series-Dict**
(`tech_analyze.py:162-166`: `"series": {jahr: wert}`, für science/funding/market
**anteilsnormiert** via `tech_query.share_series`, für Patente roh), und
`tir_trajectory.trajectory()` liefert `points` = K(t) **Jahr für Jahr mit n**
(`scripts/tir_trajectory.py:374-376`). `dossier_quant.py` greift auf **keines von beiden** zu —
grep auf `series|points` in der Datei findet nur einen Fließtext-Treffer (`:123`). Übernommen
werden nur die Skalare `n/first/takeoff/median` (`_fmt_tier:46-56`) und `K_median` (`:100-104`).

> **Die gemessene Entwicklung wird gerechnet und dann verworfen.** Genau die Zeitreihe, die ein
> Web-Rechercheur nicht hat, ist das Einzige, was nicht durchgereicht wird.

### Phase 2 — Agentenschleife über den Trend-Korpus

* `corpus_research.py:992-1005` Plan-Hop (`Plan`-Schema, `temperature=0.3`, ≤ `--steps` Schritte).
* `:1008-1081` Schleife, Default `--steps 6` (`:1488`). Aktionen `search|open|finish`
  (`AgentAction:104-108`).
* Retrieval: `search_corpus` (`:395-416`) über `idx_trends_fts`, zwei Durchgänge
  (strikt `websearch_to_tsquery`, dann OR-Fallback `_or_tsquery`, Wortkappe 8, `:331-347`).
  `scope="both"` teilt das Budget hälftig zwischen `status='published'` (Artikel) und
  `status='signal'` (Signale).
* Kappen: `--per-query 6` (`:1490`), `--sources 24` (`:1489`), Snippet
  `MAX_SNIPPET_CHARS = 420` (`:74`), geöffneter Volltext `MAX_BODY_CHARS = 2400` (`:75`).
* `open_item` (`:466-493`): Artikel → `body_en`; Signal → `raw_content`/`excerpt`
  (existiert für ~60 %).

**Was NICHT passiert:** Es gibt **keine einzige Aggregat-Query**. Kein `COUNT(*) … GROUP BY jahr`,
keine Akteurs-Häufigkeit, kein Erstauftritt, kein Momentum. Der Agent kann den Korpus nur
*durchsuchen*, nicht *vermessen*. Zum Vergleich: „glp-1 | semaglutide | tirzepatide | liraglutide |
incretin" trifft in `trends` **1.714 Zeilen** (532 published + 1.173 signal + 9 draft/review);
das Katalogbudget lässt davon **24** zu — **1,4 %** — und über die übrigen 98,6 % sagt der Bericht
nichts, weil sie nie gezählt werden.

### Phase 3 — Audit

* `:1088-1102`, Schema `Audit` (`:146-153`): `thesis`, `outline`, `supported[claim→source_ids]`,
  `inferences`, `contradictions`, `missing`. `temperature=0.2`, `max_tokens=4096`.
* Der Audit sieht Katalog + `evidence_block(notes)` — und damit dieselbe Kürzung wie unten.

### Phase 4 — Lückensweep in den internen Korpora (deterministisch)

* `:1104-1159`. Läuft **nur, wenn `audit.missing + audit.contradictions` nicht leer ist**
  (`:1106-1108`). Kein Audit-Befund ⇒ **kein Paper, kein Patent**.
* Je Lücke: `search_research(tsq, 3)` (`:1120`) und `search_patents(tsq, 2)` (`:1124`).
  Globale Kappen `n_papers >= 12` / `n_patents >= 8` (`:1129`, `:1136`).
* Query-Bau `_anchored_tsquery` (`:601-615`): **die ersten zwei** Inhaltswörter des Themas als
  AND-Anker, Lückenwörter als OR (Kappe 8, `_gap_terms:585`). Für „GLP-1 receptor agonists"
  ergibt das `(glp-1 & receptor) & (…)` — geprüft, valides tsquery. Für ein Thema wie
  „obesity drugs GLP-1" würde der Anker `obesity & drugs` lauten und am Thema vorbeigehen.
* `statement_timeout = '20s'` je Sweep-Query (`:629`, `:660`).
* Paper-Ranking: `ts_rank_cd` dann `cited_by_count DESC` (`:622-626`) — **Zitationsfamen statt
  Aktualität**. Patent-Ranking: `ts_rank_cd` dann `published DESC` (`:653-656`).

**Was NICHT passiert:** kein Zählen, kein Jahresprofil, keine Assignee-/Institutions-Auswertung.
Der 45-M-Forschungskorpus und der 19,8-M-Patentkorpus werden wie eine Suchmaschine benutzt, die
höchstens **12 + 8 Titel** herausgibt.

### Phase 5 — Web-Stufe

* `:1161-1355`, nur wenn `web_steps > 0` **und** `gaps` (`:1166`). Default `--web-steps 8`
  (`:1494`), `--web-sources 12` (`:1498`).
* Brave-API (`brave_search:518-559`, Rate-Limit 1,1 s `:79`), UGC-Blockliste `:507-509`.
* Coverage-Pflicht: `finish` wird abgelehnt, solange eine Lücke unbearbeitet ist (`:1203-1214`);
  danach deterministischer Coverage-Sweep je unbearbeiteter Lücke (`:1294-1329`, max 2 Treffer)
  und ein Fetch-Backstop (`fetch_budget = 6`, `:1334-1355`).
* Nur **gefetchte** Seiten sind zitierbar (`:1378-1379`).

### Phase 6 — Re-Audit

* `:1359-1373`, gleiches `Audit`-Schema über den kombinierten Katalog.
* **Was NICHT passiert:** die Lücken, die *erst hier* entstehen, werden **nicht mehr gesweept**
  und haben keine Ledger-Zeile (im Abnahmelauf 1 von 4 — `docs/agentic_dossiers.md:149,166-167`).

### Phase 7 — Bericht

* `:1393-1408`. `llamacpp_client.chat`, `temperature=0.4`, System `REPORT_SYSTEM` (`:267-293`),
  bei `lang="de"` mit vorangestelltem Deutsch-Zwang (`:1384-1392`).
* Prompt-Inhalt: Frage + Audit-JSON + Coverage-Ledger-JSON + zitierbarer Katalog + Evidenz.
* **Evidenz-Kappe `MAX_EVIDENCE_CHARS = 30_000` (`:76`), und `evidence_block` (`:811-822`)
  behält die *jüngsten* Notizen und wirft die *ältesten* ganz weg.** Die Quant-Notiz ist
  `notes[0]` (`:984-987`) — sie fliegt als Erstes raus.

  Gemessen an den gespeicherten Läufen (`dossiers.result->'evidence'`):

  | Lauf | Notizen | Evidenz gesamt | im Report-Prompt verworfen |
  |---|---|---|---|
  | id 7 perovskite v1 | 25 | 42.802 Zeichen | Notizen 1–6, **inkl. der Quant-Notiz** |
  | id 8 perovskite v2 | 28 | 48.318 Zeichen | Notizen 1–10, **inkl. der Quant-Notiz** |
  | id 12 newsletter v4 | 10 | 27.428 Zeichen | keine |

  Übrig bleibt vom Messblock nur der Katalog-Eintrag `Q1` mit einem **60 Zeichen** langen
  Snippet („Improving fast (median ~13.0%/yr over the measured history)."). CPC-Klassen,
  Patentzahlen, Reifegrad-Historie: für den Schreiber unsichtbar.

### Phase 8 — Kanonisierung der Zitate

* `canonicalize_citations` (`:847-899`): jede `[Titel](URL)` wird gegen `url`/`origin` des
  Katalogs aufgelöst; nicht auflösbare Links werden **gestrichen** (Satz bleibt, Beleg weg,
  `:868-876`), ein modellgeschriebenes Quellenverzeichnis wird abgeschnitten (`:880-883`),
  danach hängt der Code sein eigenes an.
* Anschließend hängt `:1414-1440` den **codegenerierten Coverage-Anhang** an.

### Phase 9 — Endkontrolle

* `pipeline/dossier_check.py`, deterministisch: `ungrounded_specifics` (`pipeline/grounding.py`)
  über den modellgeschriebenen Teil (Coverage-Anhang abgetrennt) gegen das **gesamte** Material,
  plus Zitatbilanz und offene Fragen. Status bleibt `review`; `done` nur per Owner-Abnahme
  (`pipeline/dossier_orders.py`).
* **Was NICHT passiert:** kein URL-Liveness-Check, keine Prüfung, ob die *gemessenen* Größen
  überhaupt im Text auftauchen, keine Widerspruchsauflösung.

---

## 2. Was der Korpus zu GLP-1 hergibt — und ein Web-Rechercheur nicht

Vollständige Herleitung mit jeder Query: `korpus_messung.md` (Begleitdatei, gleicher Ordner).
Alle Zahlen sind am 2026-09-06 lesend gemessen.

### 2.1 Die vier Schichten

| Schicht | Tabelle (Filter) | Treffer | Zeitraum |
|---|---|---|---|
| Wissenschaft | `research_corpus`, GIN `idx_rc_tsv` | **29.825 Arbeiten** (4.697 Reviews, 739.859 Zitationen) | 1964–2026, belastbar 2010–2024 |
| Patente (Text) | `patent_search`, GIN | **6.645 Publikationen**, **1.865 DOCDB-Familien** | 1990-10-04 – 2026-08-26 |
| Patente (CPC-nativ, ohne Textsuche) | `patent_cpc` in `A61K38/26`, `C07K14/605` | **13.714 Patente** | 1990–2026 |
| Markt | `trends`, `idx_trends_fts` | **2.124** (578 published + 1.537 Signale) | 2016-01-22 – 2026-09-05 |
| Forschungssignale | `research_signals`, GIN | 1.077 | 1992–2026 |
| Ventures | `startup_patent_links` ⋈ Textset | **58 Firmen** mit GLP-1-Patenten (Intarcia 49, Carmot 24, Viking 10) | Events 1985–2026 |
| Finanzierungsrunden | `startup_press_rounds` ⋈ `raw_entries` | **24 datierte Runden mit Betrag** (Kailera 600 M$, Metsera-IPO 275 M$) | 2024–2026 |

### 2.2 Die Zeitreihe, die den Unterschied macht

Vier unabhängig gemessene Reihen auf einer Jahresachse (Auszug; volle Tabelle in
`korpus_messung.md` §6):

| Jahr | Paper | Patent (Text) | Patent (CPC-nativ) | Trends (Markt) | Funding-Events |
|---|---|---|---|---|---|
| 2014 | 858 | 75 | 227 | 0 | 8 |
| 2016 | 948 | 143 | **421** | 2 | 10 |
| 2017 | 956 | **284** | **764** | 0 | 9 |
| 2020 | 1.371 | 398 | 938 | 6 | 11 |
| 2022 | 1.638 | 495 | 939 | 19 | 15 |
| 2023 | 1.888 | 614 | 1.086 | **149** | 11 |
| 2024 | 4.524 | 656 | 1.249 | 347 | 8 |
| 2025 | 6.549* | 852 | 1.494 | 318 | 8 |

\* unvollständig bzw. ingest-verzerrt.

**Ablesbare Lead-Time:** Patent-Takeoff **2016/2017** (CPC-nativ +81 %, Textreihe +99 %) →
Markt-Takeoff **2023** (Trend-Reihe 19 → 149, Faktor 7,8) ⇒ **Patent → Markt ≈ 6 Jahre.**
Der Patent-Takeoff ist sauber, weil das Patentarchiv lückenlos bis 1990 zurückreicht.
Ehrlich dazuzusagen: der Markt-Takeoff 2023 fällt mit dem Beginn der eigenen RSS-Erhebung
zusammen und ist deshalb **kein unabhängiger Nachweis**; Science → Markt ist **nicht**
belastbar, weil die Wissenschaftsreihe erst 2010 beginnt (Korpuskante) und die eigentliche
Entdeckungsphase der 1980er außerhalb liegt. Genau diese Selbstbeschränkung ist ein
Jury-Punkt („Ehrlichkeit über Grenzen") und darf nicht wegformuliert werden.

### 2.3 Was nur hier gerechnet werden kann

* **Cycle Time = 11,0 Jahre** (Median Rückwärts-Zitationsalter, 10.864 datierte Kanten in
  `patent_links`) gegen `cpc_insights.A61K` = 9 Jahre ⇒ GLP-1 erneuert sich **langsamer** als
  das Pharma-Mittel. Eine Aussage, die aus keinem Webartikel hervorgeht.
* **SPNP-Zentralität** (`patent_spnp_full_z3`): Median-Perzentil 0,354, Kohorten-Peak
  **2019 (0,603)**, seither rückläufig — die zentralen Anmeldungen des Feldes sind älter als
  der Markthype.
* **Anmelderprofil** (`patent_assignee_raw`, GIN-trgm): Eli Lilly 433 (+83), Novo Nordisk
  414 (+213 +55), Hanmi 181, Zealand Pharma 139 (+55), MedImmune 87, Amgen 72, Sanofi 70,
  Pfizer 59, Amylin 53, Gasherbrum Bio 45.
* **Top-Förderer** aus 31,4 Mio. `research_work_funder`-Zeilen: Novo Nordisk 1.570, NIH 1.180,
  NIDDK 1.155, NSFC 1.067, Eli Lilly 924. Ein privates Unternehmen als **größter** Geldgeber
  der öffentlichen Forschung im eigenen Feld — belegbar, quantifiziert, und im Web nur
  anekdotisch zu haben.
* **CPC-Domäne** mit Vollarchiv-Kontext: A61P3/10 (4.872 im GLP-1-Set / 169.479 gesamt),
  A61K38/26 „Glucagons" (3.916 / 9.900 — das Feld belegt **40 %** seiner eigenen CPC-Klasse),
  A61P3/04 Antiobesity (3.694 / 87.543), C07K14/605 (2.864 / 6.177).
  Alle sieben geprüften Feincodes tragen `embedding_1024` in `cpc_fine` — der On-demand-Pfad
  ist anschlussfähig, sobald M1 das Gate passieren lässt.

### 2.4 Wo der Korpus nichts kann (muss im Dossier stehen)

* `raw_entries` (21,9 Mio. / 41 GB) hat **keinen FTS-Index** — Volltextsuche über die Rohdaten
  ist nicht möglich.
* Die vorberechnete Lead-Time (`cpc_leadtime_summary`, `cpc_tier_series`, `cpc_insights`)
  existiert **nur auf 4-stelliger Subklasse** und ist für A61K/A61P/C07K mit `reliable=0`
  markiert — für GLP-1 unbrauchbar. Die Zahlen oben mussten frisch gerechnet werden; genau
  dafür ist der `tech_analyze`-Pfad da.
* Die Science-Reihe vor 2010 fehlt; 2026 ist durch den „OpenAlex fresh: Obesity"-Sweep
  13-fach überzeichnet; die Trend-Reihe 2026 spiegelt Pipeline-Ausbau, nicht Marktwachstum.
* `startup_research_links` hat insgesamt nur 244 Zeilen — die Brücke Forschung↔Firma trägt nicht.

### 2.5 Module, die das schon können

`scripts/tech_analyze.py` (kanonisch: CPC-Auflösung + TIR + Lead-Time), `scripts/tech_trajectory.py`,
`scripts/tech_query.py` (`share_series`, `evidence` je Tier), `scripts/tir_for_cpc.py`,
`scripts/cpc_leadtime.py`, `scripts/tir_metrics.py`, `pipeline/foresight.py` (Cluster/Trajektorien),
`pipeline/mega_momentum.py` (anteilsnormiertes Momentum), `pipeline/research_pulse.py`
(Wochenvolumen gegen Vorwochen-Median). **Keines davon liefert heute eine Zahl in ein Dossier
außer über den einen `dossier_quant`-Pfad — und der ist auf GLP-1 abgeschaltet (§4/M1).**

---

## 3. Schwachstellen des heutigen Laufs — belegt

### 3.1 Die Messung erreicht den Bericht nie (Wirkung: Abdeckung der Innovationskette, Spezifität — kritisch)

Zitierte Quellen je Typ über **alle** gespeicherten Läufe
(`dossiers.result->'cited'`, Präfix `T9…`=Web, `T…`=Korpus, `P…`=Paper, `N…`=Patent, `Q…`=Messung):

| id | Serie | v | Web | Korpus | Paper | Patent | **Messung** | Σ |
|---|---|---|---|---|---|---|---|---|
| 1 | precision-fermentation-dairy | 1 | 3 | 21 | 0 | 0 | **0** | 24 |
| 2 | precision-fermentation-dairy | 2 | 3 | 6 | 1 | 0 | **0** | 10 |
| 3 | precision-fermentation-dairy | 3 | 5 | 11 | 2 | 0 | **0** | 18 |
| 4 | askea-feinmechanik | 1 | 6 | 2 | 4 | 1 | **0** | 13 |
| 5 | askea-feinmechanik | 2 | 5 | 1 | 4 | 0 | **0** | 10 |
| 6 | askea-feinmechanik | 3 | 6 | 3 | 2 | 0 | **0** | 11 |
| 7 | perovskite (Abnahmelauf) | 1 | 5 | 3 | 0 | 0 | **0** | 8 |
| 8 | perovskite | 2 | 8 | 5 | 0 | 0 | **0** | 13 |
| 9 | newsletter-deepdive (ohne Web) | 1 | 0 | 3 | 0 | 1 | **0** | 4 |
| 10 | newsletter-deepdive | 2 | 0 | 7 | 2 | 5 | **0** | 14 |
| 11 | newsletter-deepdive | 3 | 0 | 8 | 3 | 3 | **0** | 14 |
| 12 | newsletter-deepdive | 4 | 0 | 12 | 1 | 2 | **0** | 15 |
| 13 | **glp1-baseline (06.09., das Testthema)** | 1 | 4 | 8 | 2 | **0** | **0** | 14 |

Drei Ablesungen:

1. **`Q1` wurde nie zitiert — 0 von 13 Läufen.** Der Abnahmelauf id 7 nennt im gesamten Bericht
   (1.906 Wörter) weder „13", „median", „CPC", „H10F" noch „measured" (grep, case-insensitive).
   Das Dossier, das die Abnahme bestanden hat, enthält **keine einzige eigene Messung**.
2. **Die Web-Stufe verdrängt die internen Korpora.** Läufe *mit* Web (1–8, 13): Patente
   insgesamt **1×** zitiert, obwohl jedes Mal 7–12 gesammelt wurden. Läufe *ohne* Web (9–12):
   **11×** zitiert. Das Modell greift zu Papers/Patenten nur, wenn nichts Bequemeres da ist.
   Der GLP-1-Lauf ist der Extremfall: 12 Paper und 7 Patente gesammelt, **0 Patente** zitiert —
   und der Bericht notiert im Coverage-Anhang selbst, das gelieferte Patent sei „unrelated to
   GLP-1 technology".
3. **Ausschöpfung der Sweep-Kappen:** in 11 der 12 Läufe mit Sweep exakt 12 Paper, in allen
   7–12 Patente (die Kappen `:1129`/`:1136` binden praktisch immer). Gesammelt insgesamt
   **142 Paper und 100 Patente**, zitiert **21 bzw. 12** — im Schnitt 1,6 Paper und 0,9 Patente
   je Lauf. **85 % des teuersten deterministischen Materials landet im Papierkorb.**

Für die Jury heißt das: Arm A liefert bei „Abdeckung der Innovationskette" faktisch
Marktmeldungen + Web, also genau Arm Cs Spielfeld — mit schlechterem Modell und kleinerem Web.

### 3.2 Die Leitpatente sind nicht themenscharf (Wirkung: Korrektheit, Spezifität)

Die fünf `Q2…Q6`-Leitpatente des Abnahmelaufs heißen „Photovoltaic shingle system",
„Photovoltaic module framing system", „Portable power supply", „Portable solar panel with
attachment points", „Roof Integrated Solar Power System" — Montage- und Gehäusepatente, kein
einziges zur Perowskit-Tandemzelle. Ursache: `top_patents` sortiert nach **Forward-Zitationen
in der CPC-Domäne**, was systematisch alte, breite Patente nach oben spült
(`tech_analyze.py:120-146`, `dossier_quant.py:135-141`). Ein Juror, der das prüft, liest es als
Beleg dafür, dass die „Messung" das Thema nicht trifft.

### 3.3 Streichungsquote der Zitate (Wirkung: Belegbarkeit im Text)

`docs/agentic_dossiers.md:143-150`: im fertigen Dossier 8/8 = 100 % belegt und 0 erfundene URLs
— aber im **Roh-Bericht** nur 8 von 15 Zitat-Instanzen (53 %); 7 Instanzen auf 3 katalogfremde
URLs wurden gestrichen (46,7 %; nach distinkten URLs 27 %). Zwei davon waren plausible, aber
404-tote Pfade auf echten Domains (`us.qcells.com/blog/…`, `pv-magazine.de/2025/10/01/…`).
Jede Streichung kostet einen Satz seinen Beleg — die maschinelle Prüfung der Jury („stammt jede
Zahl aus einer genannten Quelle") trifft genau diese Sätze. Ursache: der Bericht-Prompt gibt die
Zitatformen als Freitext vor (`:1405`), das Modell tippt sie ab und improvisiert dabei.

### 3.4 Der Lückensweep hängt am Audit-Befund (Wirkung: Abdeckung)

`corpus_research.py:1106-1108`: `gaps = audit.missing + audit.contradictions`. Findet der Audit
keine Lücke, gibt es **kein Paper und kein Patent** — die 45-M/19,8-M-Korpora bleiben stumm.
Ebenso hängt die gesamte Web-Stufe daran (`:1166`). Und die im **Re**-Audit neu entstehenden
Lücken werden nie mehr gesweept und fehlen im Ledger (`docs/agentic_dossiers.md:166-167`,
im Abnahmelauf 1 von 4).

### 3.5 Widersprüche werden benannt, nicht aufgelöst (Wirkung: Korrektheit, Handlungsrelevanz)

`Audit.contradictions` (`:152`) wandert in dieselbe Lückenliste wie `missing` und wird mit
denselben 3 Papern / 2 Patenten „bearbeitet". Es gibt keinen Schritt, der zwei widersprechende
Angaben datiert gegenüberstellt und die jüngere/belastbarere als Auflösung markiert.

### 3.6 Web-Kappe und Ranking (Wirkung: Korrektheit)

`--web-sources 12` (`:1498`), `--web-steps 8` (`:1494`), Coverage-Sweep max 2 Treffer je Lücke
(`:1313`), Fetch-Backstop global 6 (`:1334`). Brave-Treffer werden **ungeranked** in der
gelieferten Reihenfolge übernommen (`:1272-1277`) — es gibt keine Domänen-Qualitätsbewertung,
nur die UGC-Blockliste (`:507-509`). Gegen Arm C (Websuche ohne diese Kappe) ist die Web-Stufe
strukturell unterlegen; sie zu *gewinnen* ist nicht der Weg.

### 3.7 Keine deutschen Register, keine Aufsichtsquellen (Wirkung: Korrektheit, Abdeckung)

Für GLP-1 fehlen im Werkzeug: EMA/EPAR, FDA Drug Shortages, ClinicalTrials.gov-Abfragen im
Dossier-Pfad (der Ingester zieht sie zwar wöchentlich, aber der Dossier-Sweep durchsucht nur
`research_corpus`, `patent_search`, `trends`), DIMDI/BfArM, G-BA. Arm C findet diese Seiten über
Brave/Google mühelos; Arm A hat sie weder als Korpus noch als privilegierte Web-Quelle.

### 3.8 Evidenz-Kappe wirft das Wertvollste zuerst weg (Wirkung: alle Kriterien)

Siehe §1 Phase 7. `MAX_EVIDENCE_CHARS = 30_000` + FIFO-Verwurf trifft in beiden
Perovskite-Läufen die Quant-Notiz. Das ist kein Randfall: 42,8k und 48,3k Zeichen Evidenz bei
25 bzw. 28 Notizen sind der Normalbetrieb, sobald Web-Fetches (je bis 2.400 Zeichen) dazukommen.


### 3.9 Die Endkontrolle prüft zu wenig, um die Jury-Prüfung vorwegzunehmen (Wirkung: Korrektheit, Ehrlichkeit)

`pipeline/dossier_check.py` prüft genau vier Dinge: Zahlen-Grounding, `stripped_citations`,
Zitatbilanz, `len(ledger)`. `ok` (`:123-124`) ignoriert **offene Fragen und Wortzahl**; die
Schwelle `SEVERE_UNGROUNDED = 8` (`:48`) ändert nur das Etikett, nie `ok`.

Nicht geprüft:
* **Personennamen.** `pipeline/grounding.py` hat seit 2026-09-05 `ungrounded_names` (`:472-538`);
  `dossier_check` importiert nur `ungrounded_specifics` (`:30`). Die im Artikel-Gate gemessene
  Fehlerklasse (erfundener Vorname zu einem echten Nachnamen, 7–18 % der Bodies) ist im Dossier
  völlig unkontrolliert.
* Ob ein Zitat die Aussage **inhaltlich** trägt (geprüft wird nur, ob die URL auflöste).
* Ob die Messung überhaupt benutzt wurde.
* Die Berichtssprache — ein `lang=de`-Lauf, der Englisch liefert, ist „ok" (genau das passierte
  bei Askea v1).
* URL-Liveness. Die 404-Prüfung des Abnahmelaufs war Handarbeit, kein Codepfad.

`ungrounded_specifics` selbst ist by design großzügig (`grounding.py:200-229`): Substring-Freibrief
(`:226` — Quelle „2024" erdet die erfundene Zahl „202"), alle Kardinalwörter 1–12 und 20 gelten als
quellenseitig impliziert (`_CARDINAL_WORDS:60-68`), Währung nur `$ € £`, Jahre nur 19xx/20xx,
Prozent und Absolutwert nach `_norm_token` ununterscheidbar, nicht-numerische Erfindungen
(Firmen, Orte, Kausalbehauptungen) unsichtbar. Der Befund „0 unbelegte Zahlen" im Abnahmelauf ist
deshalb echt, aber schwächer als er klingt.

*Positiv festzuhalten:* über sechs geprüfte Läufe gab es **null** echte Zahlenerfindungen des
Modells; alle sechs ursprünglichen „ungrounded"-Meldungen waren Prüfer-Artefakte (Slug-IDs,
Ordinalzahlen) und sind mit `dc36438`/`ea0c069` behoben. Das Halluzinationsproblem liegt bei
den **URLs**, nicht bei den Zahlen.

### 3.10 Streichungsquote nach Lauf — und der deutsche Sonderfall (Wirkung: Belegbarkeit)

| Serie | Sprache | Streichquote je Lauf | Zitatquote |
|---|---|---|---|
| precision-fermentation-dairy v1/v2/v3 | en | 14,3 % / **52,4 %** / 5,3 % | hoch |
| askea-feinmechanik v1/v2/v3 | de | 0 % / **37,5 %** / **38,9 %** | 17 % / 16 % |
| perovskite v1/v2 | en | **46,7 %** / 23,5 % | 14 % / 22 % |
| newsletter-deepdive v1–v4 | en (kein Web) | 0 / 6,7 / 0 / 0 % | hoch |

Zwei Ablesungen: die Quote schwankt **stark zwischen Läufen desselben Themas** (5 %→52 % bei
identischer Konfiguration) — sie ist ein Würfelergebnis, kein stabiler Zustand; und die
Web-freien Läufe (9–12) haben praktisch **keine** Streichungen. Das Modell erfindet URLs vor
allem dann, wenn Web-URLs im Kontext stehen, die es aus dem Gedächtnis „vervollständigen" kann.
Das stützt M4 (ID-Zitate) direkt.

### 3.11 Zwei Löcher im Auftragsweg (Wirkung: Betriebsfähigkeit des Vergleichs)

* `dossier_orders.ALLOWED_PARAMS` (`:39-41`) = `steps, sources, per_query, scope, web_steps,
  web_sources, retrieval, quant` — **`lang` fehlt**. Ein über die Seite oder `--order-new`
  erteilter Auftrag kann strukturell kein deutsches Dossier erzeugen; DE geht nur über die CLI.
  Für einen Jury-Vergleich mit fixierter Sprache ist das eine Fußangel.
* Es gibt **kein Timeout und keinen Stale-Reset** im Worker: ein abgestürzter Lauf bleibt für
  immer `running` (aktuell hängt eine Order seit dem 06.09. in diesem Zustand). Bei einer
  Vergleichsserie mit mehreren Läufen blockiert das die Warteschlange.

### 3.12 Die CPC-Auswahl ist nicht korrigierbar (Wirkung: Korrektheit)

`tech_analyze.analyze_query` wird von `dossier_quant.py:196` **ohne `codes`** gerufen. Der
vorhandene Pfad für eine explizite CPC-Auswahl (`analyze_codes`, `_candidates_for_pick`) und der
gesamte `gate`-Payload inklusive `suggestions` bleiben ungenutzt. Meldet das Gate `ambiguous`,
ist `off_topic=false`, aber `trajectory` und `leadtime` sind `None` — der Messblock druckt dann
nur CPC-Codes, und der `Q1`-Snippet fällt auf den Default „Deterministic measurement: CPC
resolution, TIR trajectory, cross-tier lead-time" zurück und **behauptet damit eine Messung, die
nicht stattgefunden hat** (`dossier_quant.py:152-153`). Für GLP-1 (A61K38/26, A61P3/04 …) ist ein
`ambiguous`-Gate realistisch.

**Relevante harte Schwellen der Messkette** (für einen Umsetzungs-Agenten): `DIST_GATE = 0.55`,
`MAX_CANDIDATES = 12`, `CODE_MIN_PATENTS = 50`, Lead-Time-Cosinus-Schwelle 0,55, Jahresfenster
1990–2026, Share-Nenner < 30 verworfen, `ramp_takeoff = max(3, 0.15 × peak)`, Lead nur bei
Takeoff > 1993 / Markt ≥ 2003 / Differenz ≥ 2 J.; TIR: `WINDOW = 5`, `MIN_N = 100`,
`TRUNC_YEARS = 7`, `CALIB_MAX = 50 %/yr` (darüber wird die Zahl **unterdrückt**),
`DOMAIN_MIN_TOTAL = 500`, `DIRECTION_MIN_MEDIAN_N = 1000`; Verdict-Schwellen K ≥ 12 „fast",
K ≤ 8 „slow", Markt-n < 80 „early-stage".

---

## 4. Priorisierte Maßnahmen für Arm B (nach Wirkung pro Aufwand)

Gesamtaufwand M1–M8: **rund 15 h Agentenarbeit**. M1–M4 (≈ 9 h) sind der Kern; alles danach
ist Verstärkung.

### M1 — Die Messung auf GLP-1 überhaupt zustande bringen · **1,5 h · Risiko gering** ⚠️ zuerst

*Befund:* der GLP-1-Lauf von heute Abend (`dossiers.id=13`, Order #7, Topic
`GLP-1 and incretin technology`) hat `result->>'quant' = {"off_topic": true,
"nearest_dist": 0.266}`. Der Einbruch passiert in `pipeline/query_gate.verdict` (`:351-353`):
`and_hits == 0` → `off_topic`. `and_hits` zählt Patente, deren Volltext **alle** Wörter der
Phrase enthält (`query_gate.py:157-161`, `websearch_to_tsquery`). Nachgemessen:

| Phrase | Treffer in `patent_search` |
|---|---|
| `GLP-1 and incretin technology` (das benutzte Topic) | **0** |
| `GLP-1 receptor agonist` | ≥ 2.000 (Clamp) |
| `incretin` | 452 |
| `semaglutide` | 375 |

Das Wort **„technology"** in der Auftragsformulierung hat die gesamte Messkette abgeschaltet:
keine CPC-Auflösung, kein TIR, keine Lead-Time, keine Leitpatente, `Q1` gar nicht erst erzeugt
(`dossier_quant.py:66-75`) — stattdessen eine Notiz, die sagt, das Feld sei nicht messbar.
Arm A hat auf dem Testthema also **null** Innovationsketten-Messung.

*Was:*
1. In `pipeline/dossier_quant.build_quant_evidence` (`:184-205`) die Themenphrase vor
   `analyze_query` normalisieren: generische Wörter entfernen (`technology`, `technologies`,
   `market`, `industry`, `sector`, `and`, `trends`, `landscape`) und die Restphrase verwenden.
   Für `GLP-1 and incretin technology` bliebe `GLP-1 incretin` → messbar.
2. **Rückfallkaskade statt Aufgabe:** bei `off_topic`/`ambiguous` die Phrase in Einzelbegriffe
   zerlegen und je Begriff erneut gaten; der erste `ok`-Treffer gewinnt. Für GLP-1 greift
   `GLP-1 receptor agonist` bzw. `semaglutide` sofort.
3. **Letzte Rückfallebene, korpusgestützt:** die CPC-Klassen aus den Korpustreffern selbst
   nehmen (`signal_cpc`, 5,0 Mio. Zeilen: `trend_id → cpc, dist`, Index `idx_signal_cpc_cpc`)
   und `scripts/tech_analyze.analyze_codes(codes)` aufrufen — der Pfad existiert bereits und
   wird heute nie benutzt (`dossier_quant.py:196` ruft `analyze_query(topic)` **ohne** `codes`).
4. Den `Q1`-Snippet-Default (`dossier_quant.py:152-153`) entschärfen: er behauptet heute im
   `ambiguous`-Fall eine TIR-Messung, die nicht stattgefunden hat.

*Hebt:* Abdeckung der Innovationskette (von 0 auf vorhanden), Korrektheit, Ehrlichkeit.
*Risiko:* gering — die Gate-Logik selbst bleibt unangetastet, es kommen nur Vorverarbeitung und
Rückfallpfade dazu. Vorher/nachher an `GLP-1 and incretin technology` messbar.

### M2 — Die gerechneten Zeitreihen bis in den Bericht durchreichen · **2–3 h · Risiko gering**

*Was:* drei Eingriffe, alle deterministisch, keiner ändert das Modellverhalten.
1. `pipeline/dossier_quant.format_quant_evidence` (`:59-181`) zusätzlich
   `analysis["leadtime"]["tiers"][t]["series"]` (Jahr→Wert; science/funding/market
   anteilsnormiert, patent roh — `tech_analyze.py:162-166`) und
   `analysis["trajectory"]["points"]` (Jahr→`K`,`n` — `tir_trajectory.py:374-376`) als
   kompakte Tabellen ausgeben. **Beides wird heute berechnet und weggeworfen** (grep auf
   `series|points` in `dossier_quant.py`: ein einziger Fließtext-Treffer, `:123`).
2. In `corpus_research.run()` analog zum Coverage-Anhang (`:1414-1440`) einen
   **codegenerierten Abschnitt „Gemessene Entwicklung"** anhängen. Damit hängt die Messung nicht
   mehr daran, ob das Modell sie aufgreift — der Grund, warum sie in 13 von 13 Läufen fehlte.
3. Quant-Notiz gegen den FIFO-Verwurf schützen: in `run()` (`:979-989`) ans **Ende** von `notes`
   statt an den Anfang, oder `evidence_block` (`:811-822`) um ein `pinned`-Argument erweitern.
   Dazu den `Q1`-Snippet (`dossier_quant.py:152-153`) von 60 auf die erlaubten 420 Zeichen
   füllen — der Katalog steht garantiert im Prompt.

*Hebt:* Abdeckung der Innovationskette, Spezifität, Handlungsrelevanz.
*Risiko:* gering — rein additiv.
*Umsetzungshinweis:* der neue Anhang muss in `pipeline/dossier_check._report_body` (`:54-59`)
wie `COVERAGE_HEADINGS`/`SOURCES_HEADINGS` als Schnittmarke registriert werden — sonst zählt die
Endkontrolle die Mess-Tabellen als modellgeschriebene Prosa (der Fall ist im Repo dokumentiert:
`dc36438`/`ea0c069`).

### M3 — Korpus-Kennzahlen als zweite deterministische Vorstufe · **3–4 h · Risiko mittel**

*Was:* neues Modul `pipeline/dossier_corpus_stats.py` mit `measure_corpus(topic_terms)`:
* `trends` über `idx_trends_fts`: Treffer je **Quartal** (published/signal getrennt, `sort_date`,
  Index `idx_trends_status_sort`), je `primary_vertical`, je `trend_signal_type`, Top-20
  `source_name`, Erst-/Letztauftritt.
* `research_corpus`: Publikationen je Jahr.
* `patent_search` / `patent_cpc_full`: Anmeldungen je Jahr, Top-CPC.
* `startup_events`: `clinical` / `fda_clearance` / `grant` / `press_round` / `sbir_award` je
  Jahr — **420.564 Zeilen, darunter 24.813 `clinical` und 11.549 `fda_clearance`, für den
  Dossier-Pfad heute komplett unerreichbar** (`corpus_research.py` fragt ausschließlich
  `trends`, `research_corpus` und `patent_search` ab). Genau diese Schicht ersetzt für ein
  Pharma-Thema den externen ClinicalTrials-/FDA-Sweep, den ein Web-Rechercheur nur einzeln
  zusammensuchen kann.
*Einhängen:* wie `quant` in `run()` (`:979-989`), als Katalogeintrag `Q0` plus codegenerierter
Anhang „Was der Korpus zählt".
*Hebt:* Abdeckung, Spezifität, Ehrlichkeit (jede Zahl per Query nachprüfbar).
*Risiko:* mittel — Query-Kosten. Mit `statement_timeout` (Muster `corpus_research.py:629`),
Jahresfenstern und den vorhandenen GIN-Indizes beherrschbar.

### M4 — Zitate per Katalog-ID statt per URL-Freitext · **2 h · Risiko gering**

*Was:* `REPORT_SYSTEM` (`:267-293`) und Report-Prompt (`:1405`) auf Marker umstellen — das
Modell schreibt `[[N12]]`/`[[T334314]]`, `canonicalize_citations` (`:847-899`) löst die Marker
gegen den Katalog auf und rendert `[Titel](URL)`. Freitext-URLs bleiben verboten und werden
weiter gestrichen, kommen aber nicht mehr vor.
*Hebt:* Belegbarkeit — genau das Kriterium der maschinellen Jury-Prüfung. Erwartung:
Streichungsquote von 46,7 % (perovskite v1) bzw. 5 gestrichenen Zitaten im GLP-1-Lauf gegen ~0,
**ohne** dass Sätze ihren Beleg verlieren.
*Risiko:* gering, ein Testlauf nötig — der 27B ignoriert Prompt-Konventionen gelegentlich
(vgl. den Deutsch-Zwang, der ans Prompt-**Ende** gehängt wirkungslos war, `:1384-1392`).

### M5 — Akteure zählen statt aus dem Fließtext raten · **2 h · Risiko gering–mittel**

*Was:* aus denselben FTS-Treffern die JSONB-Felder `trends.brands`/`companies` aggregieren
(Häufigkeit, Erstauftritt, letzter Auftritt); dazu Top-Anmelder aus `patent_assignee_norm`
(4,2 Mio. Zeilen) für die gewählten CPC-Klassen und Top-Institutionen aus `research_work_inst`
(36,2 Mio. Zeilen). Ausgabe als Tabelle im Messanhang.
*Hebt:* Spezifität, Handlungsrelevanz — Sätze der Form „X erscheint seit 2014 in n Signalen,
Y erst seit 2021, mit steilerem Anstieg" sind für Arm C nicht herstellbar.
*Risiko:* Namensnormalisierung; deshalb nur Zählungen zeigen, keine Marktanteils-Deutung.

### M6 — Sweep vom Audit entkoppeln, Kappen und Ranking korrigieren · **1,5 h · Risiko gering**

*Was:* (a) `gaps` (`:1106`) um die Plan-Schritt-Titel ergänzen, damit der Paper-/Patent-Sweep
**immer** läuft statt nur bei Audit-Befund. (b) Kappen `n_papers 12→24` (`:1129`),
`n_patents 8→16` (`:1136`) — sie binden in 12 von 13 Läufen. (c) `search_research` (`:622-626`)
sortiert nach `cited_by_count` und liefert für ein aktuelles Feld wie GLP-1 systematisch alte
Klassiker: Budget halbieren in „meistzitiert" und „neueste" (`year DESC`). (d) Der GLP-1-Lauf
zeigt zusätzlich, dass der Patent-Sweep thematisch danebengreifen kann — der Bericht notiert
selbst: „the provided patent (T93553) is unrelated to GLP-1 technology". Ein
Mindest-`ts_rank_cd`-Schwellwert, unterhalb dessen ein Treffer verworfen statt aufgenommen wird,
gehört dazu.
*Reihenfolge:* erst nach M2(3)/M7, sonst wächst die Evidenz weiter über die Kappe.

### M7 — Evidenzbudget nach Wert statt nach Alter · **1 h · Risiko gering**

*Was:* `MAX_EVIDENCE_CHARS` (`:76`) 30.000 → ~60.000 und `evidence_block` (`:811-822`) nach
Kategorie priorisieren: Messnotiz und interne Korpustreffer immer behalten, Web-Volltexte
(je bis 2.400 Zeichen) zuerst kürzen. Nötig wegen der gemessenen 42,8k/48,3k Zeichen Evidenz der
Perovskite-Läufe.
*Risiko:* Laufzeit steigt (heute 226–860 s).

### M8 — Endkontrolle um vier Prüfungen erweitern · **1,5 h · Risiko gering**

*Was:* in `pipeline/dossier_check.py`: (a) **URL-Liveness** der zitierten Links (robots-treues
HEAD/GET; Muster in `scripts/check_source_links.py`, inkl. der Regel, 403/429 nie als tot zu
werten); (b) **Mess-Nutzungsquote** — taucht mindestens eine Größe aus
`result["quant"]["summary"]` bzw. aus dem Messanhang im modellgeschriebenen Berichtsteil auf?
Ein Dossier ohne eine einzige eigene Zahl muss das im Prüfbefund stehen haben; (c) den bereits
vorhandenen `ungrounded_names` (`pipeline/grounding.py:472`) importieren — `dossier_check.py:30`
holt heute nur `ungrounded_specifics`, Personennamen sind völlig ungeprüft; (d) Sprachprüfung
(ein `lang=de`-Lauf, der Englisch liefert, gilt heute als „ok").
Nebenher zwei Einzeiler aus §3.11: `lang` in `dossier_orders.ALLOWED_PARAMS` (`:39-41`)
aufnehmen und einen Stale-Reset für hängende `running`-Aufträge ergänzen — sonst lässt sich die
Vergleichsserie nicht sauber fahren.
*Hebt:* Ehrlichkeit, Belegbarkeit — und macht §3.1 dauerhaft messbar statt anekdotisch.

---

## 5. Was NICHT gemacht werden sollte

1. **Kein Schreiber-Kritiker-Überarbeiter-Loop.**
   `docs/newsletter_agentic_prototype_2026-09-06.md` ist die Akte dazu: Owner-Entscheid vom
   06.09., der Loop wird nicht integriert. Befunde aus drei Läufen: **Zahlen verschwinden**
   (ECO verliert die 189 GW, FOOD die 12,15 Mio. €), Vertikale verlieren ihr eigenes Signal,
   Länge sinkt (337 → 205 Wörter), **keine Konvergenz** (2,8/2,4/2,8/2,5/2,8 — die fünfte Fassung
   ist nicht besser als die erste), Abbruchbedingung nie erreicht, weil ein einziges hartnäckiges
   Missverständnis den Loop blockierte. Einziger Gewinn: 0 statt 2 Floskeln. Für GLP-1 wäre der
   Schaden derselbe und größer, weil hier gerade die Zahlen der Wettbewerbsvorteil sind.
   *(Merksatz aus derselben Akte: „Die Anweisung ‚mach es länger' wirkt nicht; die Anweisung
   ‚streich das' wirkt sofort." Deshalb sind alle acht Maßnahmen oben deterministisch.)*
2. **Nicht versuchen, Arm C auf dem Web zu schlagen.** Mehr `--web-steps`/`--web-sources` heben
   das Werkzeug auf ein Feld, auf dem ein starkes Cloud-Modell mit vollem Websuchzugang
   strukturell überlegen ist — und die Web-Stufe verdrängt heute nachweislich das
   Differenzierende (§3.1, Ablesung 2). Web bleibt Lückenfüller, nicht Hauptquelle.
3. **Kein Cloud-Hop und kein Modellwechsel.** Owner-Festlegung 2026-09-01, Punkt 2
   (`docs/agentic_dossiers.md:13-15`): Dossiers laufen streng lokal. Ein besseres Schreibmodell
   würde ohnehin nur die Prosa heben — das ist nicht das Kriterium, an dem Arm A verliert.
4. **Keine Prompt-Feinarbeit an der Prosa.** Die Berichte sind bereits gut geschrieben
   (1.900–4.400 Wörter, saubere Gliederung, 0 unbelegte Zahlen im Abnahmelauf). Investition dort
   bewegt kein Jury-Kriterium.
5. **`--retrieval vector` nicht als Rettung einplanen.** Ungetestet
   (`docs/agentic_dossiers.md:173-174`), und auf der 24-GB-Karte können 27B und
   qwen3-embedding nicht gleichzeitig resident sein (`corpus_research.py:24-29`). Die
   FTS-Retrieval ist nicht das Problem — die fehlende Aggregation ist es.
6. **Kein Retrain, keine neue Kalibrierung.** Der TIR-Pfad ist bis ~2019 kalibriert und trägt
   seine Grenze bereits im Klartext (`dossier_quant.py:37-43`). Ehrlich beschriftete Richtung
   schlägt für die Jury eine unbeschriftete Präzision.

---

## 6. Der größte blinde Fleck

**Das Werkzeug behandelt den eigenen Korpus wie eine Suchmaschine, nicht wie einen Messapparat.**

Jede Retrieval-Funktion in `scripts/corpus_research.py` gibt **Zeilen** zurück — `search_corpus`,
`search_vector`, `search_research`, `search_patents`, `brave_search`. Es gibt in der gesamten
Datei **keine einzige Aggregat-Query**: kein `count`, kein `group by`, keine Jahresachse, kein
Erstauftritt, kein Anteil. Der Korpus wird auf 24 Katalog-Zeilen + 12 Paper + 8 Patente
zusammengeschnitten und dann als Text gelesen. Für GLP-1 heißt das: von 2.124 Markt-Signalen,
29.825 Arbeiten, 6.645 Patentpublikationen und 13.714 CPC-nativen Patenten sieht der Schreiber
**rund 45 Titel** — 0,1 % — und über die restlichen 99,9 % darf er nichts sagen, weil sie nie
gezählt wurden.

Der einzige Gegenentwurf im Haus, `dossier_quant.py`, ist genau der richtige Ansatz und wird an
drei Stellen hintereinander entwertet: (1) das Gate schaltet ihn auf dem Testthema ganz ab
(§4/M1), (2) er wirft die berechneten Jahresreihen weg und liefert nur Skalare (§1 Phase 1),
(3) was übrig bleibt, fällt als älteste Notiz aus dem Report-Prompt (§1 Phase 7) und wird in
13 von 13 Läufen nie zitiert (§3.1).

Solange das so bleibt, konkurriert Arm A mit Arm C auf dem Feld „gut geschriebene
Web-Zusammenfassung" — und dort ist ein starkes Cloud-Modell mit vollem Websuchzugang
überlegen. Der Abstand entsteht erst in dem Moment, in dem im Dossier Sätze stehen wie:
*„Die Patentaktivität des Feldes ist 2016/17 um 81 % gesprungen, die Marktberichterstattung erst
2023 — sechs Jahre Vorlauf, gemessen an 13.714 Patenten und 2.124 Marktsignalen. Die zentralen
Anmeldungen (SPNP) datieren auf 2019 und werden seither älter, während die Zykluszeit mit 11,0
Jahren zwei Jahre über dem Pharma-Mittel liegt. Größter Geldgeber der öffentlichen GLP-1-Forschung
ist mit 1.570 geförderten Arbeiten Novo Nordisk selbst."*
Solche Sätze kann Arm C nicht schreiben — und Arm B kann sie ab M1+M2 schreiben, ohne dass ein
Modell dafür irgendetwas erfinden müsste.

---

## 7. Empfohlene Reihenfolge für den Umsetzungs-Agenten

1. **M1** (Gate/Themenphrase) — ohne das misst Arm B auf GLP-1 gar nichts. Abnahme: derselbe
   Auftrag liefert `quant.off_topic == false` und eine CPC-Auswahl.
2. **M2** (Zeitreihen + Messanhang + Pinning) — Abnahme: der Bericht enthält mindestens eine
   gemessene Jahresreihe; `grep` auf „CPC"/„%/yr" im Berichtstext ist nicht mehr leer.
3. **M4** (ID-Zitate) — Abnahme: `stripped_citations == 0` bei unveränderter Zitatzahl.
4. **M3** (Korpus-Kennzahlen inkl. `startup_events`) — Abnahme: Quartals-/Jahresreihen und
   Akteurszählungen im Anhang.
5. **M7**, dann **M6** (Budget vor Kappen), **M5**, **M8**.

Zwei Läufe pro Stufe (v(n+1) auf derselben Slug-Serie), damit die Streichungsquote als
Würfelergebnis (§3.10) nicht als Fortschritt fehlgelesen wird.
