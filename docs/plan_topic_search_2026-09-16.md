# Plan: Themensuche als Hauptmodus, Entdeckung als Vorschlagslieferant

Owner-Entscheid 2026-09-16, nach der Messung vom Vortag: der Nutzer gibt einen
Begriff ein und bekommt die Trenddaten dazu. Die Cluster- und Nest-Entdeckung
bleibt, verliert aber ihren Platz als Produkt und wird zum Zulieferer von
Vorschlägen.

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
- `scripts/validate_emerging.py` — ist technisch **bereits** ein Anfrage-Modus:
  bettet 20 Anfragen ein und baut Monatskurven je Ebene
- der CPU-Embedder auf `:8091` und der HNSW-Index auf `embedding_1024`

Was wegfällt: Zellgrößen, Verschmelzungsschwellen, k-Wahl, Benennung,
Titel-Eindeutigkeit — der größte Teil der Tuning-Arbeit vom 15.09.

---

## Stufe 1 — Die Anfrage-Maschine (`pipeline/topic_report.py`)

Eingang ein Begriff, Ausgang ein Bericht. Kein Modell außer dem Embedder.

**1.1 Abruf je Ebene, nicht global.** Vier ANN-Abfragen statt einer. Grund ist
gemessen: die Einbettung kodiert den Sprachstil mit, eine wissenschaftlich
formulierte Anfrage liefert Wissenschaft (Perowskit: 40 von 40 Treffern
Forschung). Wer die Marktebene nicht getrennt abfragt, sieht sie leer, obwohl
sie es nicht ist. `hnsw.ef_search = 1000` ist die gemessene Obergrenze je
Abfrage, 1.000 Nachbarn in 0,10 s.

**1.2 Schwelle relativ je Ebene.** Eine feste Zahl geht schief: gut formulierte
Anfragen treffen bei 0,82–0,93, die Marktbelege zu Wärmepumpen lagen bei
0,60–0,65. Genommen wird je Ebene der Abstand zum eigenen Verteilungskopf, mit
absolutem Boden, und **der Schnitt wird angezeigt**. Der Nutzer sieht, wie weit
die Belege vom Thema weg sind.

**1.3 Kurve und Kennzahlen.** Die Treffer werden nach Monat und Ebene gezählt,
dann läuft die vorhandene Bewertung darüber: Erstauftritt je Ebene, Reihenfolge
der Ebenen, Abstand Forschung → Markt, Neuheits-Hebel, Beschleunigung,
Quellenkonzentration, etablierte Quellen, genannte Firmen.

**1.4 Ehrlichkeits-Gates, die es schon gibt.**
- Dämpfung von Mengenausschlägen je Quelle (ein Nachtrags-Ingest ist kein Trend)
- Wächter etablierter Quellen (ein neues Abo ist kein neues Thema)
- Rückfrage statt Fehlantwort bei mehrdeutigen Kurzbegriffen — dasselbe Muster
  wie das Query-Quality-Gate der Technologie-Suche (#67)
- **Neu und nötig:** eine Aussage „dazu haben wir zu wenig". Hyrox liefert sechs
  Belege im gesamten Korpus. Das ist die richtige Antwort, nicht eine Kurve aus
  sechs Punkten.

**1.5 Zwischenspeicher.** Jeder Bericht wird gespeichert (`topic_reports`,
additiv). Wiederholte Anfragen sind sofort da, und die Liste der gestellten
Fragen ist später die ehrlichste Vorschlagsquelle, die es gibt.

---

## Stufe 2 — Die Seite (`/trends/foresight/topic?q=…`)

Ein Suchfeld, darunter der Bericht. Aufbau der Karte ist schon entworfen und
getestet, er wird übernommen:

- Kopf: Begriff, Belegzahl je Ebene, angewandter Schnitt
- Ebenen-Streifen: wann jede Konversation begann, Abstand Forschung → Markt
- Kurve je Ebene über 60 Monate
- neues Vokabular rund um den Begriff
- die neuesten Belege je Ebene, höchstens einer je Quelle
- Schwächen offen: Quellenzahl, größte Einzelquelle, Anteil etablierter Quellen,
  Anteil klassifizierter Dokumente

Owner-Werkzeug wie der Rest des Cockpits, also unter `PUBLIC_MODE` gesperrt und
nicht im statischen Export.

---

## Stufe 3 — Der Vorschlagslieferant

Die Nest-Läufe bleiben, wandern aber unter das Suchfeld. Drei Quellen für
Vorschläge, alle schon vorhanden:

1. **Nest-Namen.** Der Benennungsschritt vom 15.09. zahlt genau hier ein: der
   Name eines Nests ist der Begriff, den man eingeben würde
   („World-Action Models", „Self-Assembled Monolayers for Perovskite Solar
   Cells"). 311 von 328 Nestern haben einen.
2. **Neues Vokabular.** Begriffe, die es im Korpus vor 24 Monaten kaum gab und
   heute häufig sind — fällt im Datierungs-Scan bereits ab, ohne dass ein Nest
   nötig wäre.
3. **Gestellte Fragen.** Was schon gesucht wurde, mit dem Ergebnis daneben.

Vorgeschlagen wird mit Etikett: Alter, Belegzahl, welche Ebene. Ein Vorschlag
darf danebenliegen — er ist eine Einladung zur Suche, kein Befund. Damit
verliert der Pseudowissenschafts-Fund vom 15.09. seine Sprengkraft: als
Vorschlag ist er harmlos, als Spitzenmeldung war er peinlich.

---

## Stufe 4 — Prüfung des Suchmodus

Der Rücktest wird umgebaut, und zwar auf die Erkenntnis vom 15.09.: Perowskit
+26 und GLP-1 +18 waren **Forschungs**-Erstauftritte, gemessen gegen ein
**Markt**-Datum. Zwei verschiedene Trends gegeneinander gehalten.

- `known_trends.yaml` bekommt je Trend **zwei** Daten: wann die Forschung
  begann und wann der Markt es aufnahm.
- Geprüft wird je Ebene gegen das passende Datum.
- Die Kennwort-Regel bleibt (ohne sie meldete der Test 15 von 20 statt 9).
- Zielgröße ist die **Trefferquote je Ebene**, nicht der Vorlauf.

Erst diese Zahl rechtfertigt nach außen ein Wort wie Vorlaufzeit.

---

## Stufe 5 — Was zurückgebaut wird

Nichts sofort. Wenn die Suche steht und Stufe 4 eine Zahl liefert:

- Nest-Läufe von 13 Bereichen auf global plus die vier Ebenen kürzen
- die Cluster-Schicht (`/clusters`) weiter beobachten, aber nicht mehr tunen
- keine Arbeit mehr in Zellgrößen, Verschmelzung, k-Wahl

## Aufwand und Reihenfolge

| Stufe | Aufwand | hängt ab von |
|---|---|---|
| 1 Anfrage-Maschine | ~1 Tag | nichts, alles vorhanden |
| 2 Seite | ~0,5 Tag | Stufe 1 |
| 3 Vorschläge | ~0,5 Tag | Stufe 1, Nest-Läufe (da) |
| 4 Prüfung | ~0,5 Tag | Stufe 1 + Owner-Daten je Ebene |

Stufe 4 braucht eine Owner-Entscheidung: die zweiten Daten in
`known_trends.yaml` sind eine fachliche Einschätzung, keine Messung.

## Was der Plan nicht löst

Die Quellen. Bei fünf der zwanzig bekannten Trends fand der Rücktest nicht
einmal das Feld, die Marktebene ist auf vielen Themen dünn, und nur 13 % der
Fachpresse-Zeilen tragen einen extrahierten Firmennamen. Die Suche macht diese
Lücken sichtbar und beantwortbar — sie schließt sie nicht. Der größte Hebel für
die Qualität bleibt die Extraktion auf dem Signalpfad und die Marktabdeckung,
nicht der Algorithmus.
