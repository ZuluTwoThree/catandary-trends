# Research Pulse (#73 Teil 1) — Datenlage, Methode, Betrieb

Stand 2026-09-05 (Werk-Typ-Filter, Abschnitt 1a). Code: `pipeline/research_pulse.py` (Kern), `scripts/research_pulse.py`
(CLI), `scripts/migrate_research_pulse.py` (Tabelle), Frontend
`/trends/foresight/research/pulse` (+ `/[theme]`), Wrapper `scripts/weekly_research_pulse.sh`.

## 1. Datenlage (geprüft 2026-09-04)

- **Wo liegen die frischen Forschungssignale?** In `research_signals` (Research-Explorer-Index,
  Voll-Rebuild durch `scripts/build_research_index.py` am Ende von `weekly_ingesters.sh`,
  Samstag 06:00). 545.399 Zeilen; `published` = Publikationsdatum des Papers (nicht Ingest-Datum),
  Maximum 2026-08-29 = letzter Samstagslauf. Letzte 14 Tage: **17.317** Zeilen (35 Tage: 58.915).
  Quellen der 14 Tage: `OpenAlex fresh: <Konzept>` (zitationsfreier Wochen-Sweep, ~65 %),
  `arXiv Preprints` 2.263, `medrxiv Preprints` 492, `biorxiv Preprints` 349, dazu Journal-/Presse-
  Feeds (Trends in Food Science & Technology, Trends in Biotechnology, …).
- **Theme-Zuordnung:** `research_signals.mega_trend` (aus `trends.mega_trend`, Distill-Head im
  Samstagslauf). 22 der 28 Themes tragen in 14 Tagen Signale; 6 sind praktisch leer
  (Platformization of Culture, Experience Economy, Cultural Heritage, Virtual Worlds, Orbital
  Economy, Evolution of Work). ~7 % der frischen Zeilen haben kein Theme (`mega_trend` NULL,
  Abstain) — sie fließen in keinen Pulse. `concept` = OpenAlex-Konzept bzw. arXiv-Kategorie
  aus dem Routing-Präfix des Excerpts.
- **Embeddings:** ja, vollständig. Der Join `research_signals → trends` liefert für **20.084 von
  20.084** Zeilen der letzten 14 Tage sowohl `embedding` (4096) als auch `embedding_1024`
  (1024, HNSW-indiziert). Der Pulse nutzt `embedding_1024` (klein genug für den Transfer, gleiche
  Distill-Basis wie die Klassifikation). Daher **KMeans auf Embeddings**, keine Konzept-Gruppen;
  das Konzept bleibt sekundäres Cluster-Label.
- **OA-Status:** liegt für OpenAlex-Fresh-Werke nicht vor (der Fresh-Ingest speichert keinen
  `is_oa`; `research_work_oa` ist nach OpenAlex-Work-ID geschlüsselt, die frischen URLs sind
  DOIs/arXiv-Links → 0 Treffer). OA-Badge deshalb nur für Preprint-Server (arXiv/bioRxiv/medRxiv
  = per Definition Open Access). Ehrlich gelabelt („open-access preprints").
- **Nebenbefund (behoben 2026-09-05):** `build_research_index.py` kopierte beim Rebuild mit
  `CREATE TABLE … (LIKE research_signals INCLUDING ALL)` alle bestehenden Indizes und legte drei
  neue an — die Tabelle trug 6 Sätze identischer Indizes (19 Stück). Seit 05.09. `INCLUDING
  DEFAULTS`, PK + Indizes unter Staging-Namen, Umbenennung nach dem Tausch → nach dem Rebuild
  genau 5 Indizes (`research_signals_pkey`, `_tsv_idx`, `_published_idx`, `_mega_trend_idx`,
  `_kind_idx`).

## 1a. Werk-Typen: Artefakte raus (Owner-Befund 2026-09-05)

**Befund:** In den Top-Papers des AI-Pulse W35 stand `https://doi.org/10.5281/zenodo.22080387`
(„sc26-submission/ad-artifacts: BatchFlow — SC26 Artifact v1.0.1") — ein Software-Artefakt,
das OpenAlex als Work indexiert. Messung 05.09. (Host-Heuristik, letzte 14 Tage): **2.755 von
13.367 frischen OpenAlex-Zeilen (20,6 %)** sind Repository-Einträge (2.650 davon Zenodo-DOIs,
76 github.com, 28 osf.io, 1 figshare); „Artificial intelligence" 512/1.091, „Computer vision"
304/905, „Reliability (semiconductor)" 260/1.191, „Quantum information" 171/223. Über den
ganzen Index: 16.528 von 545.399 Zeilen (3,0 %), praktisch alle aus `OpenAlex fresh: …`
(16.374) — der zitationsgegatete Korpus (154) und die Preprint-Server (0) sind sauber. Im alten
AI-Pulse standen **8 von 20 Top-Papers** auf Zenodo (neben BatchFlow u. a. vier
„E8 Intelligence Research"-Deposits). Der Fresh-Sweep las `type` gar nicht mit
(`select` ohne `type`), der zitationsgegatete Concept-Pull ebenso; nur der #9-Graph-Pfad
speicherte `openalex_meta.work_type`.

**Fix (drei Schichten, eine Regelquelle `pipeline/research_kinds.py`):**

1. **Ingest** (`scripts/ingest_openalex.py`, Concept-Sweeps inkl. `--fresh`): `admit_work`
   nimmt nur OpenAlex-`type` ∈ {`article`, `preprint`, `review`, `book-chapter`}
   (`RESEARCH_WORK_TYPES`); alles andere (`dataset`, `software`, `other`, `paratext`,
   `peer-review`, `erratum`, `editorial`, `letter`, `supplementary-materials`, `retraction`,
   `grant`, `standard`, `libguides`, `reference-entry`, auch `book`/`report`/`dissertation`
   — Dokumente, aber nicht der wöchentliche Paper-Fluss) wird je Typ gezählt und übersprungen.
   Zweites Netz: Landing-URL **oder DOI** auf einem Repository-Host (`zenodo.org`, `10.5281/`,
   `figshare`, `dryad`, `osf.io`, `github.com`, `gitlab.com`, `softwareheritage`, `dataverse`,
   `10.7910/DVN`) → Skip auch bei `type=article` (Zenodo-Deposits tragen den oft). Der
   zugelassene Typ wird mit `cited_by_count`/`counts_by_year`/`is_retracted` nach
   `openalex_meta` geschrieben; `insert_raw_entry` nimmt dafür `openalex_id` (Node-Key, bei
   Duplikat COALESCE-Backfill). Der Sweep meldet `… | 37 non-paper type (dataset 21, other 9,
   …) | 12 repository`. Nicht gefiltert: der #9-Graph-Pfad (Zitationsgraph; Typ liegt dort
   ohnehin vor) und `ingest_preprints.py` (per Konstruktion Preprints).
2. **Index** (`research_signals.kind`, additiv, Index `research_signals_kind_idx`):
   `article | preprint | review | chapter | artifact | unknown`. Regel (`kind_sql`, identisch
   im Rebuild und in `scripts/migrate_research_signals_kind.py`): Repository-Host → `artifact`;
   gespeicherter Typ → Zuordnung bzw. `artifact` außerhalb der Admission-Liste; Preprint-Server
   (`arXiv/biorxiv/medrxiv Preprints`) → `preprint`; sonst `unknown` (Journal-/Presse-RSS und
   die Fresh-/Concept-Zeilen vor dem 05.09., die keinen Typ haben). **Backfill 05.09.** (UPDATE
   auf 545.399 Zeilen, 501 s, kein DELETE): unknown 333.050, article 93.805, preprint 75.491,
   review 22.234, **artifact 19.652**, chapter 1.167. Anschließender Voll-Rebuild (100 s,
   563.504 Zeilen — der Index war seit 29.08. nicht neu gebaut): artifact 23.316.
   Die Migration ist idempotent (zweiter Lauf: 0 Zeilen).
3. **Verbraucher:** Pulse (Wochenzahl, Vorwochen-Median, Cluster, Vorwochen-Zuordnung per
   Zentroid) und Explorer (`getResearchSignals`, `getResearchStats`) filtern
   `coalesce(kind,'unknown') <> 'artifact'` — NULL-sicher, ein nicht migrierter Bestand zählt
   als Paper statt zu verschwinden. Der Messblock trägt `artifact_n` (Theme-Seite:
   „n artifacts excluded"). Explorer-Facette **„Artifacts · show datasets & software"**
   (`?artifacts=1`, Default aus, zählt als aktive Facette); Zeilen mit `kind=artifact` tragen
   ein Badge. **Deep-Dive-Themenwahl** (`scripts/newsletter_deep_dive.py::theme_deltas`)
   zählt `trends WHERE status='published'` — publizierte Artikel des RSS-Cycles, nicht
   `research_signals`; die Artefakte sind ausnahmslos `status='signal'` (0 Artefakt-Zeilen
   unter den 21.581 published Research-Trends). Dort ist deshalb kein Filter nötig; die Basen
   sind bewusst verschieden (Newsletter = Artikel-Fluss, Pulse = Paper-Fluss).

**W35 neu gerechnet (05.09., `--no-llm` alle 28 Themes 15 s; Gemma nur für das AI-Theme,
in dem der Zenodo-Link stand, 19 s inkl. Modell-Load, Text 127 Wörter).** Vorher = Lauf vom
04.09. auf dem Index vom 29.08.; „gesamt" = alle Zeilen des heutigen Index (der Rebuild brachte
zusätzlich +18k Journal-RSS-Zeilen seit dem 29.08., daher weichen auch die Gesamtzahlen ab):

| Theme | vorher week_n | heute gesamt | **Papers (neu)** | Artefakte |
|---|---|---|---|---|
| Artificial Intelligence & Automation | 5.084 | 4.919 | **3.836** | 1.083 (22 %) |
| Personalized Health & Longevity | 3.407 | 3.296 | **2.931** | 365 |
| Future of Food & Agriculture | 1.659 | 1.302 | **1.187** | 115 |
| Clean Energy Transition | 1.267 | 1.254 | **1.111** | 143 |
| Climate Resilience & Adaptation | 613 | 622 | **550** | 72 |
| Mental Health & Neuro-Wellness | 608 | 612 | **529** | 83 |
| Regenerative Design | 436 | 422 | **381** | 41 |
| Bio Revolution & New Materials | 254 | 206 | **194** | 12 |
| Financial Innovation | 242 | 241 | **206** | 35 |
| Inclusive Design | 184 | 179 | **166** | 13 |
| Digital Trust | 123 | 120 | **102** | 18 |
| Quantum Information Science | 82 | 83 | **63** | 20 (24 %) |
| Education & Lifelong Learning | 45 | 43 | **41** | 2 |
| übrige 15 Themes | ≤ 26 | ≤ 26 | ≤ 24 | ≤ 3 |

AI-Messblock: Vorwochen-Median 4.663,5 → 4.968 (auch die Vorwochen verlieren Artefakte,
gewinnen aber die nachgezogenen RSS-Zeilen), Ratio 1,09 → **0,77**. In den jüngsten W35-Zeilen
aller 28 Themes steht **kein** Repository-Link mehr (Prüfung per Regex über `clusters`).
Ruhezustand danach: `llama-server` aktiv mit `Qwen3-8B-UD-Q4_K_XL` (208K), 21,9 GB — wie vor dem
Lauf. **Nebenwirkung:** die vier anderen W35-Texte vom 04.09. (Quantum, Food, Clean Energy,
Education) sind durch die textlosen Neuzeilen abgelöst — ihre alten Zahlen stimmten nicht mehr;
`scripts/research_pulse.py --week 2026-W35 --themes quantum_information_science,future_of_food_and_agriculture,clean_energy_transition,education_and_lifelong_learning`
(~30 s) erzeugt sie neu.

**Bis zum `dev → main`-Merge gilt:** der Samstags-Cron läuft aus `/home/dirk/projects/catandary-trends`
(main) — der Fresh-Sweep dort nimmt Artefakte weiter auf, und der alte Rebuild schreibt `kind`
als NULL zurück (NULL-sicher → alles zählt wieder als Paper). Nach dem Merge einmal
`scripts/migrate_research_signals_kind.py` (idempotent) oder den neuen Rebuild laufen lassen.

## 2. Methode (deterministische Datenbasis, generierter Text)

Je Theme und ISO-Woche (Montag–Sonntag, Default = letzte abgeschlossene Woche, Regel wie der
Newsletter-Cron: `%G/%V` von vor 7 Tagen):

1. **Volumen:** Papers der Woche (nach `published`) vs. **Median der vier Vorwochen** →
   `ratio` (z. B. 1.09 = +9 %). Median statt Mittel, weil einzelne Wochen Batch-Ausreißer
   haben (W33 = 4.480 Zeilen bei sonst ~15.000: Ingest-Lücke). `ratio` NULL bei Median 0.
2. **Cluster:** L2-normierte `embedding_1024` der Wochen-Papers, **KMeans** mit
   `random_state=73`, `n_init=10`; `k = min(5, n // 8)`, unter 8 Papers ein Block. Eingabe
   sortiert nach `trend_id` → gleiche Daten, gleiche Cluster.
   - **Label:** c-TF-IDF (TfidfVectorizer über Titel×2 + Abstract[:400], Bigrams, sklearn-
     Stoppwörter + generische Wissenschaftssprache, Elsevier-RSS-Boilerplate
     „Publication date/Source/Author(s)" entfernt) → Top-3-Terme, plus die häufigsten
     `concept`-Werte des Clusters.
   - **Top-Papers:** die 4 zentroid-nächsten (Kosinus) je Cluster, mit Titel, Quelle, Datum,
     Link, OA-Badge, Similarity.
   - **Wachstum/emergent:** Vorwochen-Papers desselben Themes werden **in SQL per
     Nächster-Zentroid** (`pgvector <=>`, `CROSS JOIN LATERAL … LIMIT 1`) den Zentroiden
     zugeordnet; `growth = n_week / (prior_n / 4)`; `emerging = n ≥ 5 ∧ growth ≥ 1.5`
     (oder keine Vorwochen-Papers). Bekannter Effekt: ein Journal-Batch (z. B. 284
     „Trends in Food Science & Technology"-Zeilen in einer Woche) erscheint als „emerging
     ×22.7" — das ist die Datenrealität, die Seite weist im Fußtext darauf hin.
3. **Text:** Gemma-4-26B (llama.cpp, `RESEARCH_PULSE_MODEL`), `temperature 0.2`, `seed 73`,
   `max_tokens 420`, System-Prompt „nüchtern, nur die Zahlen aus dem Datenblock, keine
   Prognosen/Empfehlungen, ein Absatz ohne Markdown". Wortwächter 80–190 Wörter: ein zweiter
   Versuch mit `seed 74`, danach wird der letzte Text mit Notiz übernommen. Kein Text unter 5
   Papers (`MIN_PAPERS_FOR_TEXT`). Reproduzierbar per Seed, soweit llama.cpp deterministisch
   ist (Batch-Komposition kann Float-Reduktionen verschieben).
4. **Speichern:** Tabelle `research_pulse` (additiv, `scripts/migrate_research_pulse.py`;
   `ensure_schema` läuft auch vor jedem CLI-Lauf): `theme, year, week, week_start,
   computed_at, stats JSONB, clusters JSONB, text, model, seconds, note`. **Versioniert** —
   jeder Lauf ist eine neue Zeile; die Seiten lesen je (theme, year, week) die jüngste.
   `data/research_pulse_last.json` (finished_at, themes, with_text, errors, status) für den
   Wächter.

## 3. Testlauf 2026-09-04 (Woche 2026-W35, 24.–30.08.)

- `--no-llm`, alle 28 Themes: **14 s** (CPU/SQL; AI 5.084 Papers 4,7 s, Health 3.407 3,1 s,
  Rest < 2 s). 22 Themes mit Clustern, 6 leer.
- Mit Gemma, 5 Themes (AI, Quantum, Food, Clean Energy, Education): **28 s** gesamt,
  davon ~12 s Modell-Load, ~2 s je Text; Texte 126–134 Wörter, alle im Wächterfenster.
  Beispiel (Quantum): „Research volume for the week of 2026-08-24 to 2026-08-30 totaled 82
  papers, representing a 35% decrease compared to the prior four-week median of 127.0. …"
- Ruhezustand danach: `start-active.sh → start-qwen3-8b-208k.sh`, `llama-server` inactive
  (wie vor dem Lauf), 172 MiB VRAM.

## 4. Betrieb

- **Knopf:** `/trends/foresight/research/pulse/<theme>` → „Recompute" (Server Action,
  Owner-Modus + Same-Origin-Check, spawnt `scripts/research_pulse.py --themes <key> --week …`
  detached; Lock `data/research_pulse.lock`, Log `data/research_pulse/<stamp>.log`).
- **Cron-Vorschlag** (auskommentiert in `deploy/crontab.txt`, nicht installiert):
  `0 12 * * 6 scripts/weekly_research_pulse.sh` — Samstag nach dem Ingester (Ende zuletzt
  08:13), Kollisionswächter (Ingester/Dossier-Worker/Cycle, max 90 min), idempotent
  (Woche mit ≥ 20 Texten = no-op). Owner entscheidet Cron vs. Knopf; die Newsletter-Edition ist
  der Präzedenzfall für Cron.
- **Flags:** `--week 2026-W35`, `--themes a,b`, `--no-llm`, `--limit N` (die N
  volumenstärksten), `-v`.
- **Explorer-Facetten** (Signal-Schicht): `?src=arxiv,biorxiv,medrxiv,openalex,journals`,
  `?range=7d|30d|90d|1y`, `?sort=relevance|date` (Relevanz nur mit `q`), `?concept=…`
  (Konzept-Badges), `?layer=signals` (Textsuche auf der Signal-Schicht statt 45M-Korpus),
  `?artifacts=1` (Repository-Einträge/Nicht-Paper einblenden, Default aus — Abschnitt 1a).
  Deep-Links: `/trends/mega/<theme>` → Explorer `?theme=` + Pulse (nur Owner-Modus, Foresight
  ist nicht im Export).

## 5. Nicht in diesem Paket

Autoren-Enrichment, Sprach-Kennzeichnung (#73 Teil 2, separat), Wächter-Verdrahtung des
Pulse in `cycle_watchdog.py` (erst mit installiertem Cron sinnvoll). Offen aus 1a: die
ResearchGate-DOIs (`10.13140/rg.2.2.…`) laufen als `unknown` weiter mit — Preprint-artige
Selbstveröffentlichungen, kein Repository-Host; ob sie zählen sollen, ist eine Owner-Frage.
