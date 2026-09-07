# DR-Lauf 2026-09-07 (`glp1-dr` v1, `dossiers.id=26`)

Ein Lauf, wie beauftragt. Modellparameter und Prompt so verändert, dass der 27B
arbeitet wie ein Deep-Research-Agent; verglichen gegen die neun Runden davor,
die nicht darauf optimiert sind. Frage wörtlich identisch mit R8/R9
(`dossier_orders` #17/#19), Modell identisch (Qwen3.8-27B), GPU-Ruhezustand
vorher und nachher hergestellt.

## 1. Was am DR-Modus anders ist

| | vorher (R9) | DR-Modus |
|---|---|---|
| Lesereihenfolge | Auffangnetz liest 12 Seiten in Fundreihenfolge | zusätzlich `read_primary_first`: bis zu 28 ungelesene Treffer **nach Rang** (0 vor 1), Rang 2 gar nicht; Auffangnetz 20 statt 12, 3 statt 2 je offener Frage |
| vor dem Schreiben | Rohtext-Notizen ("key passages of …") | `harvest_facts`: eine Extraktion je Primärquelle → datierte Einzelaussagen mit Katalog-ID, jede **deterministisch gegen ihren Quelltext geprüft** (Datum und jede Präzisionszahl müssen dort stehen) |
| Schreib-Prompt | Regelwerk + Rohevidenz | zusätzlich das **Faktenbuch** und eine Arbeitsanweisung („HOW YOU WORK": aus den Notizen schreiben, Sätze ohne Datum/Akteur/Zahl streichen) |
| Sampling | temp 0.4 (Bericht), 0.3 (Neuwurf) | Modellkarte nicht-denkend: temp 0.7, top_p 0.80, top_k 20, presence_penalty 1.5 |

Alles hinter `dr` (Default aus). Code: `feat(dossier): DR-Modus`.

## 2. Was der Lauf gemacht hat

- **Primärquellen zuerst gelesen:** 8 von 25 Kandidaten gelesen, 17 an
  Botsperren gescheitert. Darunter EMA (GLP-1-Lieferengpässe), EU-Kommission
  (Nährwertkennzeichnung) und fünf PMC-Volltexte.
- **Faktenbuch:** 21 geprüfte datierte Aussagen aus 6 Quellen. 30 Quellen
  wurden befragt; die meisten lieferten nichts, weil der Rang-0-Vorlauf
  überwiegend **Patente ohne Abstract** enthält (ihr „snippet" ist ein
  Ein-Zeiler). Der Rang-1-Vorrat (Paper mit echtem Abstract) kam dadurch nicht
  mehr an die Reihe — die Kappe von 30 war vorher voll. Das ist der klarste
  Verbesserungspunkt für eine nächste Runde.
- **Dauer:** 1.638 s (R9 v2: 1.427 s, R9 v1: 1.721 s).

## 3. Zahlen gegen die Läufe davor

Gleiche Zähler für alle (`pipeline.dossier_structure.fact_density`,
Rangauflösung über `source_rank`), gerechnet über `scratchpad/glp1/metrics.py`:

| Lauf | sec | Fließtext | datierte Aussagen | davon primärbelegt | Angaben/100 W. | zitiert | davon Rang 0/1 | gelesene Seiten | Notizen |
|---|---|---|---|---|---|---|---|---|---|
| A_baseline (id 13) | 463 | 1.819 | 3 | 2 | 0,11 | 14 | 3 | 4 | — |
| B8 v2 (id 23) | 1.076 | 1.705 | 18 | 3 | 0,41 | 34 | 10 | 62 | — |
| B9 v1 (id 24) | 1.721 | 1.712 | 31 | 4 | 0,23 | 26 | 8 | 62 | — |
| B9 v2 (id 25) | 1.427 | 2.418 | 34 | 3 | 0,25 | 25 | 6 | 61 | — |
| **DR (id 26)** | 1.638 | **2.981** | 33 | **14** | **0,94** | 32 | **12** | **72** | **21** |

**Die Faktenquote ist von 0,25 auf 0,94 gestiegen** — der beste Wert aller
vierzehn Läufe (bisheriges Maximum 0,68, B8 v1). Primärbelegte datierte
Aussagen: 3 → 14. Das ist genau die Größe, an der die Runde 9 gescheitert war.

**Zum Vergleichstext.** Derselbe Zähler ergibt am Siegertext der vierzehnten
Bewertung (`C_sonnet.md`) heute **0,81** je 100 Wörter (16 Angaben in 1.968
Wörtern) — nicht die 1,83, die als `OPPONENT_FACT_DENSITY` im Code stehen. Die
1,83 sind mit einer laxeren Rangregel gemessen worden (sie entstehen, wenn
jedes Zitat als primär gilt); reproduzierbar ist der Wert mit dem
ausgelieferten Zähler nicht. Beide Zahlen gehören nebeneinander genannt, und
die Untergrenze 2,0 im Code ist an der laxen Messung geeicht.

## 4. Was der Lauf gekostet hat

- **Kurzfassung auf einen Satz geschrumpft.** 24 Kernaussagen ruhten nur auf
  Rang-2-Material; die Regel aus R8-2/R9-1 kennzeichnet sie und streicht sie in
  der Kurzfassung. Übrig blieb eine einzige Aussage. Die Jurys haben die
  Kurzfassung bisher gelobt — das ist ein sichtbarer Rückschritt.
- **Katalysator-Kalender nur 3 statt 6 belegte Zeilen** (Untergrenze 5). Die
  Terminzeilen hingen an Sekundärquellen und wurden gekennzeichnet.
- **Fließtext 2.981 Wörter, 181 über der Obergrenze.**
- Endkontrolle: 5 Befunde, davon 2 Zahlen ohne Beleg und 7 gestrichene Zitate.

## 5. Bewertung

Blindgutachten `jury_15.md` — DR-Dokument gegen B9 v2, anonymisiert (M/N),
Zuordnung erst nach dem Urteil aufgelöst (`M = B9 v2`, `N = DR`). Gutachter
prüfte je Dokument fünf Zitate per WebFetch.

| Kriterium | B9 v2 | **DR** |
|---|---|---|
| Belegbarkeit | 4 | **6** |
| Spezifität | 6 | **7** |
| Handlungsrelevanz (EU-Mittelstand) | 4 | **6** |
| Abdeckung Wissenschaft/Patente/Förderung/Markt | 5 | 5 |
| Zeitliche Einordnung | **6** | 4 |
| Ehrlichkeit über Grenzen | 6 | 6 |
| Struktur | 3 | **4** |
| **Durchschnitt** | 4,9 | **5,4** |

**Sieger: das DR-Dokument.** Begründung des Gutachters, verkürzt: 4 von 5
geprüften Belegen halten stand (B9: 2 von 5); das Belegrückgrat besteht aus
PNAS, BMC Medicine, Nutrients, auflösbaren Patentnummern und Firmen-IR statt
aus SEO-Blogs (FormBlends, GreyB, Tech Times) und einem Coaching-Blog; zwei
von vier Optionen tragen alle fünf Felder intakt und mit bezifferter
Aufwandsspanne — bei B9 ist kein einziges Aufwandsfeld intakt.

**Wo B9 besser ist** (und das ist die Rechnung des DR-Modus): die Zeitachse.
Fünf datierte Termine auf fünf Quellen gegen drei auf zwei Quellen. Dazu
verwendet B9 die eigene Messung im Argument, während sie im DR-Dokument
ungenutzt im Anhang liegt.

**Fehler, die der Gutachter im DR-Dokument gefunden hat** — sie gehören in die
nächste Runde: ein *Appetite*-Papier von 2014 als „peer-reviewed evidence
(PMC, 2026)" ausgegeben, Nutrients unter falschem Journalnamen zitiert, die
28,7 %-TRIUMPH-Daten auf Juni 2026 statt Dezember 2025 datiert, zwei unbelegte
FDA-Zulassungsdaten.

**Was beide nicht können:** keine Empfehlung, keine Priorisierung, und kein
einziges europäisches Förderinstrument, obwohl „Förderung" im Auftrag steht.

## 6. Einordnung

Der Vergleich ist DR gegen die eigene Vorrunde, **nicht** gegen die
Deep-Research-Vergleichsanalyse. Die vierzehn Bewertungen davor liefen gegen
`C_sonnet.md`; ob der DR-Modus auch dort gewinnt, ist nicht getestet — es war
ein Lauf, wie beauftragt.
