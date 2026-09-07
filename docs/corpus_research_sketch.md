# Deep Research über den eigenen Korpus (Skizze, 2026-08-26)

`scripts/corpus_research.py` — ein agentischer Rechercheur, der über die
publizierten Trends läuft statt über das Web: Plan → Schleife → Audit → zitierter
Bericht. Gedacht als Vorstufe für das Foresight-Dossier, das heute ein einziger
Retrieval-Durchgang in einen einzigen Prompt ist.

## Ablauf

| Phase | Modell-Hop | Rückgabe |
|---|---|---|
| `plan` | Planer | `{title, steps:[{title, query}]}` |
| Schleife | Agent, bis zu `--steps` mal | `search` \| `open` \| `finish` + `researchState` |
| `audit` | Beleg-zu-Behauptung | `supported[]` (jede mit Trend-ids), `inferences[]`, `contradictions[]`, `missing[]` |
| `report` | Bericht | Markdown mit `[Titel](URL)` |

Danach werden alle Zitate gegen den Katalog kanonisiert: was nicht auf einen
gesammelten Artikel zeigt, wird gestrichen, eine selbstgeschriebene Quellenliste
abgeschnitten, unsere generiert.

## Drei Entscheidungen

**Das Modell ruft kein Werkzeug auf.** Jeder Hop liefert striktes JSON mit der
nächsten Aktion, ausgeführt wird sie vom Runner. `chat_structured` erzwingt das
über `response_format: json_schema`, aus dem llama.cpp eine Grammatik baut —
`action` ist ein `Literal`, eine ungültige Aktion ist also nicht darstellbar.

**Der Zitat-Katalog ist geschlossen.** Anders als bei Web-Recherche ist eine
erfundene URL hier beweisbar falsch, nicht nur verdächtig.

**Retrieval per Volltext (`idx_trends_fts`), nicht per Vektor — als Default.**
Auf einer 24-GB-Karte passen das 27B und `qwen3-embedding` nicht gleichzeitig
hinein. `--retrieval vector` existiert für den Fall eines zweiten
Embedding-Endpunkts (oder Ollama auf CPU; ~10 Queries pro Lauf).

Dabei ein Fallstrick: `websearch_to_tsquery` UND-verknüpft alle Terme, eine
Agent-Query aus acht Wörtern traf damit 1 von 80.712 Artikeln. `search_fts()`
läuft deshalb zweistufig — strenge UND-Lesart, dann OR über die inhaltstragenden
Wörter, nach `ts_rank` sortiert.

## Zwei Belegarten: Artikel und Signale

Der publizierte Bestand ist nur die Spitze. `trends` enthält (Stand 2026-08-26):

| status | Zeilen | body_en | title_en | embedding_1024 |
|---|---|---|---|---|
| `signal` | 1.498.066 | 0 | alle | alle |
| `published` | 81.397 | alle | alle | alle |
| `draft` | 4.358 | alle | alle | alle |

Die 1,5 Mio. Signale sind klassifiziert und eingebettet, aber nie durch die
Content-Generierung gelaufen. Sie haben Titel, Quelle, Datum, Vertikale,
Mega-Trend und Tags — kein `summary_en`. Öffnen lässt sich ein Signal über
`raw_entries.excerpt` (rund 60 % haben einen brauchbaren), `raw_content` ist bei
ihnen leer.

Warum das zählt, am Beispiel „solid-state battery":

```
publizierte Artikel:   45   2026-03 … 2026-08   22 Quellen
Signale:              320   2011    … 2026      34 Quellen
                            2026:111 2025:47 2024:44 2023:26 2022:22 2021:31 2020:19
```

Die Historie fehlt dem Korpus also nicht — sie liegt nur nicht in den Artikeln.
In den Signalen stecken zusätzlich OpenAlex-Paper und EPO-Patentsätze.

`--scope both` (Default) teilt das Katalogbudget und verschränkt beide Pools;
sonst begraben 18-mal so viele Signale die eigene Analyse. Jeder Katalogeintrag
ist als `[article]` oder `[signal]` markiert, die Prompts erklären den
Unterschied, und ein Signal wird an seiner **Ursprungs-URL** zitiert — es hat
keine Artikelseite, ein `catandary.de`-Link liefe ins Leere. In der Quellenliste
steht bei ihnen `*(signal — not written up)*`.

## Erster Lauf (2026-08-26, Qwen3.8-27B auf `-c 65536`)

Frage: Stand der Solid-State-Kommerzialisierung — laufende Pilotlinien, belegte
Energiedichte-Angaben, Nähe zur Serienfertigung.

```
169 s gesamt | 3 Suchen, 2 Volltexte, dann finish (nicht ins Limit gelaufen)
11 Artikel im Katalog, 11 zitiert, 0 Zitate gestrichen
Audit: 7 belegte Behauptungen, 3 Inferenzen, 1 Widerspruch, 4 Lücken
Bericht: 16.383 Zeichen
```

Der Bericht benennt seine Lücken selbst („The provided corpus does not contain
specific details on the operational status of pilot lines for Toyota, Samsung,
QuantumScape"). Stichprobe: „84 % Kapazität nach 350 Zyklen" deckt sich wörtlich
mit dem zitierten Artikel.

## Vergleichslauf mit Signalen (gleiche Frage, `--scope both`)

```
                   nur Artikel   Artikel+Signale
Sekunden                 168,9             187,8
Katalog                     11    15 (6 Art./9 Sig.)
zitiert                     11                11
gestrichene Zitate           0                 0
Belegzeitraum      2024-05 … 2026-08   2020-04 … 2026-08
```

Inhaltlich ist der Unterschied größer als die Zahlen andeuten:

* **QuantumScape** war im Artikel-Lauf eine ausdrückliche Lücke („cannot be
  established from this evidence"). Mit Signalen entsteht eine Bahn: B-Samples
  für OEM-Tests (10/2024) → Corning-Partnerschaft (09/2025) → Eagle-Line-Pilot
  (02/2026).
* **Eine gemessene Prognose-Korrektur:** Solid Power stellte 2022 Feststoff-EVs
  „ab 2028" in Aussicht, CATL verschob 2026 auf „nicht vor 2030". Vier Jahre
  Differenz zwischen zwei Akteuren, im Bericht ausdrücklich als Widerspruch
  benannt. Im Artikel-Lauf war das strukturell unmöglich — 2022 liegt außerhalb
  des publizierten Bestands.
* Die Audit-Lücken wurden **schärfer** statt weniger: aus „wir wissen nichts über
  QuantumScapes Pilotlinien" wurde „uns fehlt die Kapazitätsangabe der
  Eagle Line".

Nebenbeobachtung: der Audit-Hop lief einmal in `finish_reason=length` bei
`max_tokens=1024` und wurde von `llamacpp_client` automatisch mit 2048
wiederholt — die vorhandene Retry-Logik trägt.

## Web-Stufe: Lückenschluss über die Brave Search API (2026-08-26)

Nach dem Korpus-Audit kann eine zweite Schleife die dort benannten Lücken
(`missing` + `contradictions`) gezielt im Web verfolgen: eigener Agent-Loop
(`search`/`fetch`/`finish`), eigener System-Prompt mit Quellendisziplin
(Primärquelle > Peer-Review > Behörde > Fachpresse), danach Re-Audit über den
kombinierten Katalog und erst dann der Bericht.

* **Suche:** Brave Search API (`BRAVE_SEARCH_API_KEY` aus `.env`) — vertraglich,
  kein SERP-Scraping. Damit bleibt das Primärquellen-Prinzip intakt; die
  Suche *findet* eine Primärquelle, gelesen wird die Quelle selbst.
* **Fetch:** `pipeline.article_fetcher.fetch_fulltext` — robots.txt-treu,
  per-Host gedrosselt, trafilatura-Extraktion. Kein neuer Fetch-Pfad.
* **Katalog:** Web-Treffer werden als dritte Belegart `[web]` geführt, an ihrer
  Original-URL zitiert und in der Quellenliste als
  `*(web — fetched to close a gap)*` markiert. Reine UGC-Plattformen (Reddit,
  X, YouTube …) sind hart geblockt — Prompt-Disziplin allein reicht nicht,
  weil Suchtreffer automatisch in den Katalog wandern.
* **Budget:** `--web-steps` (Default 0 = aus), `--web-sources` (Default 10).

### Dritter Lauf, gleiche Frage (`--web-steps 6`)

```
                   v1 Artikel   v2 +Signale   v3 +Web
Katalog                    11            15        25 (6/9/10)
zitiert                    11            11        13
erfundene Zitate            0             0         0
Audit-Lücken                4             5         4 (schärfer)
Dauer                   169 s         188 s     323 s
Brave-Queries               —             —         3
```

Was die Web-Stufe konkret schloss: **Honda pilotiert seit 01/2025 im Werk
Sakura** und ist seit 06/2026 QuantumScape-Partner; **BYD nennt 400 Wh/kg** und
den Zeitplan Einbau 2027 / Masse 2030; **CATL stufte sich 06/2026 selbst auf
TRL 4 von 9** ein — die beste einzelne Erdung des gesamten Dossiers, weil sie
die eigene 2027-Ankündigung relativiert. Kernaussage v3: die Chinesen-Incumbents
sind am nächsten dran, aber selbst der Führende steht bei TRL 4.

### Ehrliche Schwächen des Laufs

* Der Agent hat nur gesucht, nie gefetcht — alle Web-Belege stützen sich auf
  Such-Snippets statt auf gelesene Seiten. Für Zahlenangaben sollte der Prompt
  künftig einen Fetch vor dem Zitieren verlangen.
* Zwei zitierte Web-Quellen sind Graubereich (ts2.tech ist Aggregator-Content,
  neware.net ein Herstellerblog, der BYD-Angaben nacherzählt). Die Blockliste
  fängt UGC, aber keine minderwertige Fachpresse — hier fehlt entweder eine
  Qualitäts-Heuristik oder die Fetch-Pflicht, die dünne Quellen von selbst
  aussortiert.

## Ausbau 2026-08-26 (abends): Fetch-Pflicht, Resolver, Dossier-Store, Schablone

1. **Fetch-vor-Zitat-Pflicht.** Nur gefetchte Web-Seiten sind zitierfähig; der
   Bericht bekommt nur sie in den Zitat-Katalog, `canonicalize_citations` läuft
   gegen diesen gefilterten Katalog. Ein Auto-Fetch-Nachlauf liest bis zu 3 der
   zuerst zugelassenen Treffer (robots-erlaubt), damit die Regel dünne Quellen
   aussiebt statt die Web-Stufe zu löschen. Eine robots-geblockte Seite wird
   nie zitierfähig.
2. **Fetch-Resolver:** URL, Katalog-id (T9........) oder Titel-Containment.
   (Vorher scheiterte ein Fetch, weil das Modell den Titel statt der URL übergab.)
3. **Dossier-Store:** Tabelle `dossiers` (slug, version, topic, question,
   report_md, result JSONB, model, created_at; UNIQUE slug+version), angelegt
   on-demand vom Skript. `--slug X` speichert den Lauf als nächste Version —
   damit ist ein Refresh gegen den Vorstand diffbar („BYD hat seit dem letzten
   Stand erneut verschoben" ist selbst ein Signal). Refresh bleibt on-demand
   (CLI mit demselben Slug), analog zur Radar-Regel: Dossier = datiertes
   Dokument, kein Cron.
4. **Foresight-Schablone:** `--foresight TOPIC` baut die Standardfrage
   (Versprechen → Korrekturen → verifizierter Stand → Musterlesung) und nennt
   bewusst **keine Akteure** — die liefert der Signalraum. Genau ein Argument:
   Frage ODER --foresight.

### Zweiter Themenlauf: Präzisionsfermentation von Milchproteinen

Pool: 175 Artikel + 825 Signale zu „precision fermentation" (37/255 dairy-
spezifisch). Lauf: `--foresight "precision fermentation of dairy proteins
(animal-free casein and whey)" --slug precision-fermentation-dairy --steps 8
--web-steps 8`.

```
850 s | Katalog 36 (11 Artikel / 15 Signale / 10 Web) | 24 zitiert
Audit 16 → Re-Audit 23 belegte Behauptungen | 8 benannte Restlücken
Fetch-Pflicht: 3 gefetchte Web-Seiten alle zitiert, 7 Snippet-only alle
ausgesiebt (4 Zitatversuche entlinkt) — DairyNews7x7/Cultivated X/NXTaltfoods
flogen automatisch raus
dossiers: slug=precision-fermentation-dairy version=1
```

14 Akteure, alle aus dem Korpus (Perfect Day, Formo/Those Vegan Cowboys, Eden
Brew, Standing Ovation, Alpine Bio ex-Nobell, Verley ex-Bon Vivant, New
Culture, TurtleTree, Nestlé, FrieslandCampina …). Kernbefund: Whey ist
kommerziell (Produkt, Verträge, Gujarat-Werk), Casein bleibt ein
Wissenschaftsproblem (Mizellen-Assemblierung, 2026er-Review in Trends in Food
Science & Technology) — und die Korrekturlesung (Rebrands, Gründerabgänge,
Patent-Angriffe, FrieslandCampina-Ausstieg 08/2025) mündet in eine prüfbare
Abzinsungsregel: Casein-Zeitpläne um 2–4 Jahre diskontieren.

## Ausbau 2026-08-26 (spät): interne Korpora, Abdeckungspflicht, Coverage-Ledger

Anlass war eine Owner-Rückfrage zum PF-Dossier v1: „bezieht das auch den
Patent- und Research-Body ein, und wurde zu den offenen Fragen wirklich im Netz
gesucht?" Beide Antworten waren Nein — v1 durchsuchte nur `trends`, und 6 von 8
Lücken wurden nie im Web angefasst. Drei Umbauten stellen das ab:

1. **Interne Korpora-Stufe (immer an, deterministisch).** Nach dem ersten Audit
   wird JEDE Lücke gegen `research_corpus` (45,6 Mio. Arbeiten, `idx_rc_tsv`)
   und `patent_search` (19,7 Mio. Filings, Titel via `raw_entries.pub_number`)
   gefahren — kein Agent-Ermessen. Neue Belegarten `[paper]` (zitiert am DOI)
   und `[patent]` (Google-Patents-Link; „belegt eine beanspruchte Erfindung,
   nie ein funktionierendes Produkt"). Query-Bau: `(topic-Kopf, UND-verknüpft)
   & (Lücken-Terme, ODER)` — der UND-Kopf aus den ersten zwei Topic-Wörtern
   ist die Selektivitätsbremse (ein ODER-Anker traf Millionen Zeilen und lief
   in den Sort-Tod); Ranking `ts_rank_cd` vor Zitatzahl (Zitatzahl allein
   spülte berühmte, themenfremde Paper nach oben). `statement_timeout 20s`.
2. **Web-Abdeckungspflicht.** `WebAction.target_gap` nummeriert, welcher Lücke
   eine Aktion gilt; `finish` wird abgelehnt, solange Lücken unbehandelt sind
   und Budget bleibt. Nach der Agent-Phase läuft ein deterministischer
   Coverage-Sweep: jede nie angefasste Lücke bekommt genau eine Brave-Query;
   der Fetch-Backstop liest eine Seite pro Lücke (global gedeckelt). „Nicht
   gesucht" kann damit nicht mehr still passieren.
3. **Coverage-Ledger.** Pro Lücke wird deterministisch protokolliert: Paper-/
   Patent-Treffer, Web-Queries, zugelassene Quellen, gefetchte Seiten. Der
   Ledger geht als Daten in den Report-Prompt („charakterisiere offene Fragen
   aus dem Ledger, behaupte nie Recherche, die nicht stattfand") und wird
   zusätzlich als code-generierter Anhang „Research coverage" unter das
   Dossier gesetzt — die Abdeckungsauskunft hängt damit nicht am Modell.

Dazu: `chat_structured` hat jetzt einen `max_tokens`-Parameter (Audit-Hops
starten bei 4096 statt 1024 — vorher zwei Trunkierungs-Retries pro Audit),
und `--web-steps` Default ist 14 (Web-Stufe an; 0 = offline; war 8 bis Runde 5, s. u.).

**v3-Lauf (dossiers v3, 752 s):** 18/65 zitiert über alle fünf Belegarten
(5 Artikel / 6 Signale / 2 Paper / 5 Web), **1** gestrichenes Zitat statt 11 in
v2. Alle 12 Lücken mit vollem Ledger-Nachweis: jede mindestens eine Web-Query,
7 mit gefetchter Seite, 5 mit Papern, 6 mit Patent-Filings. Der code-generierte
Coverage-Anhang steht unter dem Dossier — „unbeantwortet" heißt jetzt belegbar
„gesucht in 45M Papern + 19M Patenten + Web, nichts Belastbares gefunden"
statt „nicht nachgeschaut".

**Zitat-Kanonisierung, Origin-Mapping (nach dem v2-Lauf):** v2 strich 11
Zitate, weil das Modell Korpus-Artikel an ihrer Original-URL zitierte (die
steht in den Evidenznotizen direkt neben dem Eintrag) — bei 54 Katalog-
einträgen wird das häufig. Der Kanonisierer löst jetzt auch die Origin-URL
eines Eintrags auf und schreibt sie auf den kanonischen Link um; nur wirklich
unbekannte URLs werden weiter gestrichen. `result.report_raw` bewahrt den
Bericht vor der Kanonisierung für Diagnosen auf.

## Firmen-Dossiers: `--company` — auch etablierte KMU (2026-08-30, Issue #95)

Owner-Anforderung: Dossier auf Firmennamen-Eingabe, ausdrücklich nicht nur
Startups. Testfall Askea Feinmechanik (Amtzell): 0 Treffer in trends, 0 im
Startup-Korpus, 0 Patent-Assignees — der Normalfall für KMU. Der Modus dreht
die Pipeline deshalb um:

1. **Firmenauflösung web-first:** Brave-Suche Name+Ort → Modell wählt die
   firmeneigene Domain aus den Treffern (`SiteChoice`), bis zu 4 Seiten werden
   robots-treu gelesen (Startseite immer), daraus extrahiert ein zweiter Hop
   das Profil (`CompanyProfile`: Branche, Produkte, Technologien,
   Abnehmerbranchen — auf Englisch, denn sie seeden die Korpussuchen). Die
   gelesenen Firmenseiten sind zitierfähige Primärquellen im Katalog.
2. **Umfeld über Technologie-Begriffe:** `topic` = Profil-Technologien (bei
   Askea: CNC milling/turning, laser processing, precision metrology) — damit
   laufen Korpus-Schleife, interner Sweep und Web-Abdeckung unverändert, nur
   eben übers Feld statt über den Namen.
3. **Berichtssprache Deutsch** (Owner-Entscheidung für Firmen-Dossiers;
   `--lang` überschreibt): Anweisung am ANFANG des Report-System-Prompts plus
   als Schlusszeile des User-Prompts — ans Ende des System-Prompts gehängt
   wurde sie vom 27B ignoriert (Askea v1 kam englisch heraus). Quellen-/
   Coverage-Abschnitte, Marks und Herkunftskopf sind sprachbewusst (`_L10N`).

Nebenbefunde aus Askea v1, beide gefixt: (a) eine abgelehnte Fetch-Aktion
wurde dem Modell nicht zurückgemeldet — es wiederholte denselben Fetch
fünfmal und verbrannte die Agent-Phase; Ablehnungen gehen jetzt mit Grund in
den Folge-Prompt, und die Liste schon gelesener Seiten steht im Prompt.
(b) Der Planer-Hop lief bei den längeren Firmen-Fragen in die
1024er-Trunkierung → Startbudget 2048.

Bewusste Grenzen: keine Handelsregister-/Bilanzdaten; Firmen ohne
Korpus-Präsenz bekommen ihr Umfeld ausschließlich über die
Technologie-Begriffe — der Ledger weist die Web-Lastigkeit aus.

## Offen

* Ranking: das OR-Retrieval holt breit; bei größeren Katalogen prüfen, ob
  Randtreffer die Belegdichte verwässern.
* `--retrieval vector` ist implementiert, aber ungetestet (Embedding-Endpunkt).
* Qualitätsranking der Web-Treffer (Primärdomain > Fachpresse > Rest) — die
  Fetch-Pflicht siebt zwar, aber die Fetch-Auswahl des Agenten ist ungeranked.
* Patent-Sweep-Präzision: `patent_search.tsv` ist dünn (Titelbasis), irrelevante
  Filings erreichen den Katalog und müssen vom Audit ignoriert werden — CPC-
  Vorfilter über die Vertikale wäre die saubere Kur.
* Kein Streaming, keine Persistenz — ein Lauf, eine Datei. Für ein Produkt
  bräuchte es Lauf-Zustand in der DB.

## Herkunft

Die Ablaufform (planen, iterieren, vor dem Schreiben auditieren, Zitate
nachträglich kanonisieren) ist Unsloth Studios Web-Deep-Research abgeschaut.
**Kein Code und kein Prompt daraus übernommen** — jener Code ist AGPL-3.0-only
und würde diese Lizenz auf das Produkt ziehen. Prompts und Implementierung hier
sind eigenständig.

---

## Runde 5 (2026-09-07) — die Web-Schicht auf Augenhöhe

**Anlass:** `docs/dossier_vs_deepresearch/00_ergebnis.md`. Sechs blinde Jurys, sechs
Niederlagen gegen eine Web-Recherche. Zwei der drei belegten Verlustgründe sind
strukturell (kein Rechtsstatus im Korpus, CPC ist für Wirkstoffe unscharf), der dritte
ist handwerklich: der Sieger las ~45 Primärseiten, unser Sweep 6–16 — und verwarf im
Askea-Lauf belegbar echte Treffer still („8 hits, 0 new", Katalog voll).

### 1. Budget und Tiefe — Ziel 40–60 gelesene Seiten je Lauf

| Stelle | vorher | jetzt |
|---|---|---|
| `--web-steps` / `--web-sources` | 8 / 12 | **14 / 32** |
| Recht/IP-Sweep | 6 Muster × 2 Treffer, 8 Volltexte | **8 Muster × 3, 12 Volltexte** |
| Markt/Erstattung | 6 × 2, 8 Volltexte | **8 × 3, 12 Volltexte** |
| Wirkstoff-/IP-Welle (neu) | — | **3 Entitäten × 4 Muster × 2, 8 Volltexte** |
| Akteur/Ereignis-Welle (neu) | — | **4 Entitäten × 4 Muster × 2, 8 Volltexte** |
| Abdeckungs-Sweep | 2 Treffer je offener Frage | **4** |
| Lese-Auffangnetz | 6 Seiten, 1 je Frage | **12 Seiten, 2 je Frage** |

Obergrenze: 44 feste Suchanfragen + Agentenstufe, 40 Volltexte aus den festen
Richtungen plus bis zu 12 aus dem Auffangnetz und ~8 aus der Agentenstufe. Real landet
das nach robots/403 im Zielband. Die globalen Kappen (`*_MAX_SOURCES`) liegen bewusst
auf `Muster × per_pattern`, damit die späten Muster nicht von den frühen ausgehungert
werden.

### 2. Query-Vielfalt statt mehr vom Gleichen — die zweite Welle

`harvest_entities()` zieht **deterministisch** (kein Modell-Hop, damit reproduzierbar
und GPU-frei testbar) Akteure aus Titeln und Snippets des bisherigen Katalogs: 1- bis
3-Gramme aus Großschreibungsläufen mit Dokumentfrequenz ≥ 2 (Title-Case-Füllwörter und
Outlet-Namen fallen raus), dazu Wirkstoffnamen an ihren INN-Endungen. Danach laufen

* `sweep_substance_legal` — `"<Wirkstoff>" SPC …`, `supplementary protection
  certificate <Wirkstoff> expiry`, `<Wirkstoff> patent expiry Europe`,
  `<Wirkstoff> court ruling generic`
* `sweep_entity_market` — `<Entität> acquisition deal …`, `… reimbursement pricing
  decision`, `… phase 3 trial results readout`, `… revenue guidance quarterly results`

Das ist der Mechanismus, über den der Siegertext auf Metsera, Frankreichs
Erstattungsentscheidung und den NHS-Rollout kam: nicht mehr Suche nach dem *Thema*,
sondern nach den *Akteuren*, die das Thema hervorgebracht hat.

### 3. Quellenrang und Relevanzfilter vor dem Abruf

`source_rank()`: Rang 0 = Register/Behörde/Gericht/Gesetzgeber (Hostliste +
`.gov`/`.europa.eu`/`.gouv.fr`/… -Endungen), Rang 1 = eigene Seite einer bekannten
Entität (Domain trägt den Namen — Firmen-Newsrooms ohne Firmenliste), Rang 2 = Rest.
`rank_hits()` liest Primärquellen zuerst.

`web_relevant()` filtert **vor** dem Abruf gegen Themen- und Entitätsbegriffe
(`entity_terms()` = Themenanker + Entitäten + deren Einzeltoken). Zwei Sicherungen:
Rang-0-Seiten sind vom Filter ausgenommen (Gerichte nennen den Gegenstand oft erst im
Volltext), und eine **Rückfallschwelle** lässt den bestplatzierten Treffer herein, wenn
eine Anfrage sonst komplett verstummen würde.

### 4. Kein stilles Verwerfen mehr

Jeder Verwurf am Budget wird gezählt (`budget_dropped`), in den Evidenznotizen benannt
(„… usable result(s) were NOT admitted — the web source budget was full") und im
Coverage-Anhang wie in der Dossier-Ansicht ausgewiesen. Jeder Abruf trägt seinen Grund
(`fetch_log`: `fetched` / `robots` / `blocked` (401/403/429/451) / `timeout` /
`too_short` / `tdm` / `budget`) statt eines pauschalen „nicht lesbar". Der
Produktions-UA bleibt — eine Botsperre wird **ausgewiesen, nicht umgangen**.

### 5. Kein Aufblähen des Berichts

Gefetchte Seiten gehen als **Schlüsselpassagen** (`key_passages()`: Absätze mit
Themenbegriffen und Zahlen, Lead immer dabei, ~1.200 Zeichen) in die Evidenznotizen;
der Volltext bleibt an der Quelle, wo die Beleg-Verifikation ihn braucht. Audit und
Bericht bekommen ein eigenes Evidenzbudget (78k statt 30k Zeichen), die Agenten-Hops
nicht. Die Längenbremse des Berichts (2.200–2.800 Wörter) ist unverändert.

### Probe zur SPC-Frage (6 echte Suchanfragen, 2026-09-07)

Die vier Wirkstoff-Rechtsmuster gegen „semaglutide" erreichen **alle drei** Belege, an
denen jede Jury das Dossier scheitern ließ:

* `semaglutide patent expiry Europe` → „The compound patent … EP 1 863 839 — expired in
  March 2026" (techtimes.com)
* `"semaglutide" SPC supplementary protection certificate` → „SPC extending the patent
  term by five years until 2031" (patentlawyermagazine.com) und die
  Novo-Nordisk-Mitteilung zum Urteil (globenewswire.com)
* `semaglutide court ruling generic` → „District Court of The Hague … preliminary
  injunction on August 5"

Die beiden themenbasierten Gegenproben (`"GLP-1 receptor agonist" SPC …`,
`GLP-1 receptor agonist patent expiry Europe generic entry`) erreichten **keinen** davon
— sie lieferten Übersichtsartikel und Fachliteratur. Der fehlende Hebel war also der
**Wirkstoffname**, nicht die Suchmenge. Alle drei Seiten sind mit dem Produktions-UA
abrufbar (`fetched`, je 2.400 Zeichen).
