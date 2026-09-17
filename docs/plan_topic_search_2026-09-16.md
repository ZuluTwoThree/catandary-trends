# Plan: Themensuche als Hauptmodus, Entdeckung als Vorschlagslieferant

> **Intern.** Dieses Papier hält Messungen an einzelnen Fällen fest. Owner
> 2026-09-16: daraus kommt **nichts ins Frontend**; allgemeine Zusammenhänge
> dürfen ins Produkt, der einzelne Fall nicht. Gerendert wird aus `docs/`
> ohnehin nur `docs/ops/logbook.md` — dieses Papier nicht.

Owner-Entscheid 2026-09-16: der Nutzer gibt einen Begriff ein und bekommt die
Trenddaten dazu. Die Cluster- und Nest-Entdeckung bleibt, verliert aber ihren
Platz als Produkt und wird zum Zulieferer von Vorschlägen.

*Konsolidiert am 2026-09-16 abends. Die erste Fassung vom Vormittag wurde durch
drei Messreihen an mehreren Stellen widerlegt; die Stufen unten tragen den
korrigierten Stand, die Belege stehen gesammelt unter „Befunde".*

## Warum diese Richtung, in Zahlen

| | Entdeckung (heute) | Suche (geplant) |
|---|---|---|
| Antwortzeit | 6 min je Lauf, 220 s Archiv-Scan | 0,30 s einbetten + 0,10 s suchen |
| Trefferqualität, gemessen | 9 von 20 bekannten Trends | echte Themen 0,82–0,93, Gegenproben ≤ 0,62 |
| bestimmt das Thema | Dichte des Korpus | der Nutzer |
| Lücken im Korpus | unsichtbar | sind die Antwort |

Die Suche ist der am besten gemessene Teil des Systems, die Entdeckung der
schwächste. Das Versprechen schrumpft von „wir finden Trends für dich" auf „wir
zeigen die Datenlage zu deinem Thema" — und nur das zweite ist heute belegbar.

## Was wiederverwendet wird

Fast alles Wertvolle rechnet auf einer **Monatskurve** und ist deshalb
unabhängig davon, ob die Kurve aus einem Nest oder aus einer Anfrage stammt:

- `score_nests` — Erstauftritt, Neuheits-Hebel (korpus-normiert), Beschleunigung,
  Wächter gegen zu junge Quellen, neues Vokabular
- `pipeline/tiers.py` — Zuordnung jeder Zeile zu Forschung / Patente / Förderung /
  Markt, plus die Ebenen-Auswertung aus `score_nests`
- Akteurszählung aus den Markt-Ähnlichen
- `scripts/validate_emerging.py` — technisch **bereits** ein Anfrage-Modus
- der CPU-Embedder auf `:8091`, der HNSW-Index und `idx_trends_fts`

Was wegfällt: Zellgrößen, Verschmelzungsschwellen, k-Wahl, Benennung,
Titel-Eindeutigkeit — der größte Teil der Tuning-Arbeit vom 15.09.

---

## Stufe 1 — Die Anfrage-Maschine (`pipeline/topic_report.py`)

Eingang ein Begriff, Ausgang ein Bericht. Kein Modell außer dem Embedder.
**Hybrid, nicht vektorbasiert** — das ist die wichtigste Korrektur gegenüber der
ersten Fassung.

**1.1 Vektorsuche je Ebene, nicht global.** Vier Abfragen statt einer, weil die
Einbettung den Sprachstil mitkodiert: eine wissenschaftlich formulierte Anfrage
liefert Wissenschaft. Häkchen je Ebene entscheiden, welche laufen; mehrere
Häkchen zeigen die Ebenen **nebeneinander** und **addieren sie nie**.

**1.2 Schwelle relativ je Ebene, und sichtbar.** Eine feste Zahl scheitert
nachweislich. Genommen wird je Ebene der Abstand zum eigenen Verteilungskopf mit
absolutem Boden; der angewandte Schnitt steht im Bericht.

**1.3 Seltene Ebenen exakt statt über den Index.** Der HNSW-Index holt die
global nächsten Nachbarn und filtert erst danach — eine kleine Ebene verhungert
dabei. Regel: häufige Ebenen über den Index, seltene exakt, automatisch
umgeschaltet. Selbstregulierend, weil die kleinen Ebenen die billige exakte
Suche sind.

**1.4 Volltextsuche für die Vergangenheit.** Die Vektorsuche verfehlt die alten,
konkreten Wortprägungen nachweislich vollständig. `idx_trends_fts` liegt vor,
0,5 s je Anfrage.

**1.5 Wortketten-Lauf mit Vektor-Bremse.** Aus den ältesten Treffern eines
Begriffs werden auffällige Wortpaare gezogen; jeder Kandidat wird per Einbettung
gegen den Themenschwerpunkt geprüft, und nur wer nah bleibt, wird ein Glied der
Kette. Ohne die Bremse driftet der Lauf in Allgemeinplätze.

**1.6 Ehrlichkeits-Gates.**
- Dämpfung von Mengenausschlägen je Quelle (ein Nachtrags-Ingest ist kein Trend)
- Wächter etablierter Quellen (ein neues Abo ist kein neues Thema)
- Rückfrage statt Fehlantwort bei mehrdeutigen Kurzbegriffen (Muster: #67)
- „dazu haben wir zu wenig" als eigene Antwort, nicht als Kurve aus sechs Punkten

**1.7 Zwischenspeicher.** Jeder Bericht wird gespeichert (`topic_reports`,
additiv). Wiederholte Anfragen sind sofort da, und die Liste der gestellten
Fragen ist später eine Vorschlagsquelle.

### Stand Stufe 1 — gebaut am 2026-09-17 (`pipeline/topic_report.py`)

Die Maschine steht als Modul + CLI (`python -m pipeline.topic_report "<Begriff>"
[--tiers science,patent,funding,market] [--no-walk] [--fresh] [--json]`). Die
Messungen vor dem Bau haben zwei Punkte des Plans korrigiert:

**„Exakt statt Index" ist auf den großen Ebenen nicht 2 s, sondern 47–94 s.**
Die 2,1 s galten nur für die Patentebene (124k Zeilen); Markt (625k) und
Forschung (607k) laufen als Seq-Scan über TOAST bei 128 MB `shared_buffers`
in Minuten, und die Hälfte der Zeit war der Join durch die 22-Mio.-Tabelle
`raw_entries`. Der Plan sah „seltene Ebenen exakt" vor — das trägt nicht.

**Die Lösung ist ein Index je Ebene, und der braucht eine Nebentabelle.**
Ein partieller HNSW-Index braucht ein Spaltenprädikat; für Forschung und
Markt kommt die Ebene aus `sources.source_type`, also musste sie auf die
Zeile. Der erste Versuch — Spalte `trends.tier` per UPDATE — war ein Fehler:
jedes Non-HOT-Update auf `trends` schreibt einen neuen Eintrag in den 14-GB-
HNSW-Index; ein 50k-Batch hing fünf Minuten in `DataFileRead` und hinterließ
285k tote Indexeinträge, bevor er abgebrochen wurde. Deshalb `topic_vectors`
(trend_id, tier, Kopie des 1024er-Vektors): 1,76 Mio. Zeilen in 2 min
eingefügt, 7,2 GB, vier `CREATE INDEX CONCURRENTLY` (~100 s je 124k Zeilen).
Ebenen in der Tabelle: Markt 603k, Forschung 420k, Förderung 215k, Patente
60k, keine 391. Neue Zeilen holt jede Anfrage per `topup()` nach (ids über
dem Höchststand), Nachzügler einmal täglich per Anti-Join.

**Der Teilindex wirkt, gemessen auf Patenten:** global+Filter gegen Ebenen-Index
bei 1.000 Nachbarn ≥ 0,62 — GLP-1 8 : 34, Perowskit 0 : 14, Präzisions-
fermentation 1 : 58, Natrium-Ionen 0 : 32.

**Schwellen, kalibriert am 17.09.:** Kopf = Mittel der fünf besten
Ähnlichkeiten je Ebene. Gegenproben (Falknerei, Töpferei, Cembalo) kamen auf
0,52–0,63, echte Themen in ihrer starken Ebene auf 0,74–0,91, Patente sprechen
tiefer (0,68–0,69 für echte Themen, 0,52–0,57 für Gegenproben). Daher
`HEAD_MIN` je Ebene (Forschung/Markt 0,68, Förderung 0,66, Patente 0,64), Cut =
max(Kopf − 0,08, 0,62); beides steht im Bericht. 0,08 statt 0,12: mit 0,12 zog
die Forschungsebene bei Präzisionsfermentation das ganze Feld herein (tragend
seit 2001-02, 616 Zeilen), mit 0,08 datiert sie das Thema (2020-01, 155
Zeilen) und der erste Markttreffer fällt auf 2020-05 — beides deckt sich mit
den unabhängig notierten Daten in `known_trends.yaml`. Offen bleibt der Boden
0,62 auf der Förderebene: Projektbeschreibungen sprechen breit, für Perowskit
kamen dort Solarprojekte seit 1990 herein — Stufe 4 misst das. Hyrox in der Forschung: Kopf
0,62 → „nichts Nahes" — korrekt.

**Was der Bericht je Ebene sagt:** Status (none / thin < 5 / ok), Kopf, Cut,
Treffer roh und quellengedämpft, erster Treffer, erster *tragender* Monat
(≥ 3 Treffer, Regel des Nest-Scorers), Alter, Treffer der letzten 6 Monate,
Index (tier / scan), größte Quelle mit Anteil, `capped` wenn die Treffer das
1.000er-Fenster füllen (die Kurve ist dann ein Boden). Übergreifend: Reihenfolge
der Ebenen, Abstand Forschung → Markt, Neuheits-Hebel, Beschleunigung, Anteil
etablierter Quellen, Marktakteure früh/spät. Dazu die ältesten Volltext-Treffer
(Vektor-gegated ≥ 0,62) und der Wortketten-Lauf (Wortpaare der ältesten Titel,
eingebettet, behalten ab cos 0,72 zur Anfrage, per Volltext datiert — 0,70
ließ „dairy products“ und „starter cultures“ durch).
Kurzanfragen (≤ 2 Wörter), deren Nachbarn sich über Vertikale verteilen
(größte < 40 %) oder deren bester Kopf unter 0,75 bleibt („rag“ wird als Lappen
eingebettet, Kopf 0,686), kommen als Rückfrage zurück. Laufzeit warm ≈ 2,5 s
(Einbetten 0,5, vier Suchen je 0,2–0,3, Wortkette 1,4), Korpus-Monatszahlen
7,6 s einmal je 24 h, aus dem Cache 0,9 s. Berichte liegen in
`topic_reports` (7 Tage Cache), Korpus-Monatszahlen in `topic_cache` (24 h).

---

## Stufe 2 — Die Seite (`/trends/foresight/topic?q=…`)

Suchfeld, Häkchen je Ebene, darunter der Bericht:

- Kopf: Begriff, Belegzahl je Ebene, **angewandter Schnitt**
- **Wortgenerationen** mit ihren Daten — kein Beiwerk, sondern das Ergebnis:
  es macht sichtbar, wann ein Thema wie hieß
- Ebenen-Streifen: wann jede Konversation begann, Abstand zwischen ihnen
- Kurve je Ebene über 60 Monate
- die neuesten Belege je Ebene, höchstens einer je Quelle
- Schwächen offen: Quellenzahl, größte Einzelquelle, Anteil etablierter Quellen,
  Anteil klassifizierter Dokumente

Owner-Werkzeug wie der Rest des Cockpits: unter `PUBLIC_MODE` gesperrt, nicht im
statischen Export.

---

## Stufe 3 — Der Vorschlagslieferant

Die Nest-Läufe bleiben, wandern aber unter das Suchfeld. Drei Quellen, alle
vorhanden:

1. **Nest-Namen.** Der Benennungsschritt vom 15.09. zahlt hier ein: der Name
   eines Nests ist der Begriff, den man eingeben würde. 311 von 328 haben einen.
2. **Neues Vokabular** — fällt im Datierungs-Scan bereits ab.
3. **Gestellte Fragen** mit ihrem Ergebnis.

Vorgeschlagen wird mit Etikett: Alter, Belegzahl, welche Ebene. Ein Vorschlag
darf danebenliegen — er ist eine Einladung zur Suche, kein Befund.

---

## Stufe 4 — Prüfung des Suchmodus

- Die 20 Daten in `known_trends.yaml` sind **Marktdaten** (Owner bestätigt) und
  werden gegen die **Markt-Ebene** geprüft. Dafür ist keine weitere Eingabe nötig.
- `research_institutional` wird nur dort geprüft, wo es gesetzt ist (bisher ein
  Trend). Das Feld heißt bewusst nicht `research`: bei Technologien, die in einem
  Unternehmen entstehen, **folgt** die institutionelle Forschung dem Proof of
  Concept.
- Zwei Trends sind als `uncertain` markiert und zählen nicht in die Kopfzahl.
- Die Kennwort-Regel bleibt: ohne sie meldete der Test 15 von 20 statt 9.
- Zielgröße ist die **Trefferquote je Ebene**, nicht der Vorlauf.

---

## Stufe 5 — Was zurückgebaut wird

Erst wenn die Suche steht und Stufe 4 eine Zahl liefert:

- Nest-Läufe von 13 Bereichen auf global plus die vier Ebenen kürzen
- die Cluster-Schicht weiter beobachten, aber nicht mehr tunen
- keine Arbeit mehr in Zellgrößen, Verschmelzung, k-Wahl

## Stand Stufen 2–5 — gebaut am 2026-09-17 (alles auf `dev`, Owner testet vor dem Merge)

**Stufe 2, Seite `/trends/foresight/topic?q=…&tiers=…`.** GET-Formular ohne
JavaScript (die URL ist die Anfrage), Häkchen je Ebene, darunter der Bericht in
der Reihenfolge des Plans: Belegzahl je Ebene mit Kopf und angewandtem Cut,
**Wortgenerationen** (frühere Wortpaare mit Datum, älteste Volltext-Belege),
Ebenen-Streifen (tragender Monat je Konversation, Abstand in Monaten, erster
Treffer daneben), Kurve je Ebene über 60 Monate, neueste Belege je Ebene
(höchstens einer je Quelle, verlinkt auf Artikel oder Quelle), Schwächen auf
jedem Block (dünn, Fenster voll, Quellenzahl, größte Quelle ≥ 50 %, gedämpfte
Ausschläge, Anteil klassifizierter Zeilen, Anteil etablierter Quellen, Index
fehlt). Rückfrage bei mehrdeutiger Kurzanfrage als eigener Block mit drei
Feldern. Die Seite ruft `python -m pipeline.topic_report --json` (execFile,
ein argv-Element, nie interpoliert); `frontend/src/lib/topicReport.ts`,
`topicView.ts` (reine Helfer, Vitest), `components/foresight/TopicReportView.tsx`.

**Stufe 3, Vorschläge unter dem Suchfeld** (`lib/topicSuggestions.ts`,
`components/foresight/TopicSuggestions.tsx`): (1) die Namen der Nester aus dem
jeweils letzten Lauf von global + vier Ebenen, mit Etikett Ebene · Alter ·
Zeilen; (2) neues Vokabular (`new_terms` der Nester); (3) gestellte Fragen mit
ihrem Ergebnis (aus `topic_reports`: seit wann, Markt-Erstauftritt, „asked
back", „nothing close"). Jede Nest-Karte trägt außerdem „search →". Ein
Vorschlag darf danebenliegen — er ist eine Einladung.

**Stufe 4, Rücktest** (`scripts/validate_topic_search.py`, Ergebnis
`data/topic_validation.json`, 10 s für 20 Trends + 3 Gegenproben): **Markt-
Ebene 18 von 18 gezählten Trends gefunden** (Ebene antwortet UND ein Kennwort
steht in einem Treffer-Titel; 0 Antworten ohne Kennwort; die beiden `uncertain`
zählen nicht), **Gegenproben 0 von 3 beantwortet**. Forschung nur bei
Präzisionsfermentation prüfbar: tragend 2020-01 = `research_institutional`.
Vorlauf ist nicht die Zielgröße, wird aber ausgewiesen: der erste *tragende*
Marktmonat liegt im Median **23 Monate nach** dem Marktdatum (nur 3 von 18
davor), der erste *Einzeltreffer* im Median 72 Monate davor. Lesart: die Suche
findet jedes bekannte Thema, aber die Marktebene des Korpus ist vor 2024 dünn
(Quellenausbau) — drei Treffer in einem Monat gibt es für die meisten Themen
erst, seit die Fachpresse breit abonniert ist. Das ist eine Aussage über die
Quellen, nicht über das Verfahren, und der Anteil etablierter Quellen auf der
Seite sagt es je Anfrage.

**Stufe 5, Rückbau.** Der Desk-Knopf „Recompute pockets" rechnet nur noch
global + vier Ebenen (`--scope global --all-tiers`), nicht mehr 13 Bereiche;
die Vertikal-Reiter auf `/emerging` sind weg (ein alter Vertikal-Lauf bleibt
per URL erreichbar, als solcher beschriftet). Zellgrößen, Verschmelzung, k-Wahl
werden nicht mehr angefasst; die Cluster-Schicht bleibt, ungetunt. Das Cockpit
führt die Themensuche als ersten Einstieg.

## Aufwand und Reihenfolge

| Stufe | Aufwand | hängt ab von |
|---|---|---|
| 1 Anfrage-Maschine | ~1,5 Tage (hybrid; war ~1) | nichts, alles vorhanden |
| 2 Seite | ~0,5 Tag | Stufe 1 |
| 3 Vorschläge | ~0,5 Tag | Stufe 1, Nest-Läufe (da) |
| 4 Prüfung | ~0,5 Tag | Stufe 1 |

---

## Befunde, auf denen der Plan steht (2026-09-15/16 gemessen)

**Abruf ist schnell genug.** 0,30 s einbetten, 0,10 s suchen, bis zu 1.000
Nachbarn je Abfrage (`hnsw.ef_search` deckelt bei 1.000). Vier Ebenen-Abfragen
bleiben unter einer Sekunde.

**Die feste Schwelle scheitert je Ebene.** Bei einer Anfrage lag der beste
Patenttreffer bei 0,72, der beste Marktreffer bei 0,77. Mit einem festen Schnitt
von 0,75 hätte die Patentebene null gemeldet, obwohl der Spitzentreffer den
gesuchten Wirkstoff im Titel führt.

**Der Index hungert seltene Ebenen aus.** Von 1.000 global nächsten Nachbarn
blieben nach dem Ebenenfilter 12 übrig. Die exakte Suche über die 123.846
Vektoren derselben Ebene dauert 2,1 s und findet die richtigen.

**Die Einbettung folgt dem Sprachstil.** Über 400.000 Dokumente traf eine
fachsprachliche Anfrage 146 Forschungs- und 2 Marktzeilen. Das Marktgespräch
existiert, es spricht nur anders. Die Ebene lässt sich deshalb **nicht**
nachträglich aus einem gemeinsamen Nest lösen — daher Scope `tier:<t>`.

**Ein Thema ist keine Vokabel, sondern eine Wortfolge.** Drei Begriffe für
dasselbe Thema haben drei verschiedene Anfangsdaten: 2014-12, 2018-03, 2020-03.
Eine Anfrage in der heutigen Sprache erreicht die Frühphase nicht — der älteste
Beleg war **nicht** unter den 1.000 nächsten Nachbarn, und auch das Weiterhangeln
von Dokument zu Dokument führte nicht hin. Die Volltextsuche fand ihn in 0,5 s.

**Der Wortketten-Lauf trägt, driftet aber.** Zwei Runden führten von der heutigen
Fachvokabel über einen Firmennamen zur Vorgängervokabel — und daneben in
Allgemeinplätze wie „whey protein" (1992) und „ice cream" (1996). Daher die
Vektor-Bremse.

**Die Reihenfolge der Ebenen ist kein Gesetz.** An einem durchgerechneten Fall:
Unternehmen im Jahr 0 sichtbar, Produkt und institutionelle Forschungswelle in
Jahr +4, Förderung in Jahr +5. Patente halfen nicht (beste Treffer 0,62–0,66,
thematisch daneben). Das früheste beobachtbare Signal war das **Unternehmen**.

**Umbenennungen brechen die Akteursverfolgung.** Früherer Name erstmals 2019-12,
heutiger Name erst 2021-09 — 21 Monate Unterschied. Der Firmenstamm führt keine
früheren Namen: `gleif_entities` nur `name` aus `Entity.LegalName`,
`ch_companies` nur `name`. Beide Quellen liefern die Historie mit (GLEIF
`Entity.OtherEntityNames`, Companies House `previous_company_names`), der Ingest
liest sie nicht. **Vorbedingung** für die Akteursverfolgung: Aliasse im Stamm
(Nebentabelle `company_names`: Name, Gültigkeit, Quelle). Namenssuche per
Textvergleich bleibt unbrauchbar.

---

## Was der Plan braucht und was er nicht löst

**Volltext ist der Rohstoff.** Am 16.09. fehlten **12.360** Volltexte der letzten
14 Tage bei Quellen, die auf Volltext stehen, und keiner war je nachgeholt
worden. Von 25 schwachen Quellen antworten 24 mit HTTP 200, nur eine mit 403 —
es war nie ein Sperr-, sondern ein Abholproblem. Der Nachhollauf ist
Voraussetzung, nicht Beiwerk: die Suche kann nur finden, was als Text dasteht.

**Archivtiefe entscheidet über jede Aussage zur Frühphase.** Ein Feed zeigt zehn
Einträge. `scripts/ingest_sitemap_archive.py` liest das Archiv einer erlaubten
Quelle über ihre Sitemaps ein (Issue #105 für den ersten großen Lauf).

**Die Quellen bleiben der Engpass.** Bei fünf von zwanzig bekannten Trends fand
der Rücktest nicht einmal das Feld, die Marktebene ist auf vielen Themen dünn,
und nur 13 % der Fachpresse-Zeilen tragen einen extrahierten Firmennamen. Die
Suche macht diese Lücken sichtbar und beantwortbar — sie schließt sie nicht.

**Nicht geplant** (Owner 2026-09-16): die adaptive Drossel. Nach der Messung
haben wir uns nirgends ein 429 eingefangen; die fehlende Rückstufung bei 429/503
und das ignorierte Crawl-delay bleiben notiert, aber nicht terminiert.

---

## Stand 2026-09-17 abends: zurückgebaut, Redesign Issue #106

Der Owner hat die Seite getestet: zu überladen mit Beispielen, verwirrend,
Sprache unklar, Inhalt nicht nachvollziehbar. Die Umsetzung der Stufen 1–5 ist
auf `feature/topic-search` (e2907f4) geparkt, auf `dev` zurückgenommen, die
Tabellen aus der Live-DB gelöscht. Was bleibt: die Messungen oben (Ebenen-
Index, Kalibrierung, Rücktest 18/18) und die Lehre, dass die *Maschine* trägt
und die *Darstellung* neu gedacht werden muss — eine Frage je Seite, Klartext,
Belege erst in der Tiefe. Wiederaufnahme: Issue #106.
