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
