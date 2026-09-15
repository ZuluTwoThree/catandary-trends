# Cluster-Schicht: Befund und Überarbeitung (2026-09-15)

Anlass: Owner-Frage „was genau zeigen die Karten im Cluster-Discoverer an, warum
ist das wichtig und was könnte man verbessern?" Geprüft wurde der frische Lauf
93 (global, 1.749.201 Signale, k=27) und Lauf 99 (FASHION) vom selben Tag.

Die Schicht ist der einzige Ort im Produkt, an dem der Korpus die Kategorie
selbst vorschlägt, statt sie aus den 28 kuratierten Mega-Themen zu übernehmen.
Deshalb wiegt es schwer, wenn die Bewegungsrichtung falsch liegt.

## Befund

**1. Momentum maß den eigenen Quellenausbau, nicht die Aufmerksamkeit.**
Der Code verglich den Anteil eines Clusters im frühen gegen das späte Drittel
der letzten 36 Monate. Der Kommentar dazu setzte voraus, dass der Quellenmix
innerhalb dieses Fensters stabil ist. Das galt nicht mehr:

| Jahr | Fachpresse | Forschung | Signale |
|---|---|---|---|
| 2023 | 49 % | 28 % | 18.368 |
| 2024 | 45 % | 31 % | 110.726 |
| 2025 | 36 % | 46 % | 115.645 |
| 2026 | 19 % | 56 % | 415.018 |

Das Monatsvolumen stieg von rund 10.000 (2025) auf 129.124 (August 2026), die
Quellenzahl von 226 auf 560. Entsprechend standen im Lauf 93 oben ausschließlich
Cluster mit Nature-, OpenAlex- und Patentbelegen und unten die Fachpresse-Themen
(Plant-Based, Elektroautos, Markenstrategie).

**2. Die Karte war eine Sackgasse.** Ein Cluster mit 94.889 Signalen zeigte drei
Titel. Die Zugehörigkeit wird nicht gespeichert, die Spalte `centroid` existierte
seit der ersten Migration, wurde aber nie geschrieben, und es gab keine
Detailseite.

**3. Belege waren die zentrumsnächsten, also die durchschnittlichsten.** Für den
zweitgrößten Cluster waren es fünf Google-Patente mit Titeln wie „Information
processing method and equipment", aus 2018 bis 2024.

**4. „Confirmed by 419 independent sources"** behauptete eine Prüfung, die nicht
stattfindet. Die Zahl ist die Feed-Breite eines 95k-Eimers.

**5. Weitere Mängel.** Zwei FASHION-Cluster trugen denselben Titel bei
gegenläufigem Momentum. Abkürzungen wurden verstümmelt („Nft", „Sbir Funding",
„Eu Funding"). Kohäsion (0,51 bis 0,73) und Mega-Reinheit (0,23 bis 0,99) wurden
berechnet und nie angezeigt, obwohl auf jeder Karte gleich selbstbewusst
„Part of …" stand. Der laufende Monat lief als halber Monat in Sparkline und
Vergleichsfenster. k wurde per Silhouette auf einer Stichprobe von 4.000 aus
1,75 Mio. Punkten gewählt und landete bei 27 von maximal 30, also an der Decke.

## Umbau

**Fenster.** Snapshots clustern die letzten 24 Monate (`--window-months`, 0 =
ganzes Archiv). 1,75 Mio. Signale zurück bis 1983 beantworteten eine andere
Frage als „What's moving now" und ergaben 27 Eimer à 65.000 Einträgen. Global
sind es jetzt 567.911 Signale, der Lauf über alle neun Scopes dauert 3,5 statt
10,5 Minuten. k=28 wird frei gewählt (Decke jetzt 36), nicht mehr erzwungen.

**Festes Quellenpanel.** In die Anteilsrechnung gehen nur Quellen ein, die im
frühen *und* im späten Vergleichsfenster geliefert haben, wie ein Preisindex
seinen Warenkorb festhält. Global sind das 122 Quellen mit 44 % der Zeilen in
den Fenstern. Deckt das Panel weniger als 25 % ab, wird es verworfen und im Lauf
als `cohort_applied = 0` vermerkt, statt still zu wirken. Rohzahlen (Größe,
Quellenzahl, Monatszählung) bleiben ungefiltert.

**Dämpfung je Quelle.** Auch eine Quelle im Panel kann ein Fenster verzerren,
indem sie ihre eigene Rate ändert. Im FASHION-Lauf sprang ein Haus von rund 50
auf 378/353/347 Beiträge in April bis Juni, ein Nachtrags-Ingest, und erzeugte
allein den einzigen Aufsteiger (+18,4 pp). Monate über dem Median einer Quelle
werden auf diesen Median gedämpft; der Ausschlag fiel damit auf +4,2 pp, die
Verteilung von 1 Aufsteiger gegen 6 Absteiger auf 2 gegen 3.

**Laufender Monat raus.** Er endete jede Sparkline auf einem halben Monat und
ließ den letzten Ingest das späte Fenster steuern.

**Zweite Zahl statt Nullsummen-Einzelwert.** Anteil am Gehör ist zwischen den
Clustern eine Nullsumme. Die Karte nennt deshalb die beiden Anteile selbst
(„2,2 % der Panel-Signale im frühen Fenster, 4,5 % im späten"). Die rohe
Mengenänderung steht nur noch auf der Detailseite: im aktuellen Korpus wuchs
jeder Cluster um 20 bis 5.000 %, weil der Korpus wuchs, also misst sie die
Beschaffung, nicht das Thema.

**Belege.** Zentralität ist jetzt ein Tor statt einer Rangfolge: wer über dem
60. Perzentil der Ähnlichkeit liegt, kommt in Frage, und darunter gewinnen die
**neuesten**, höchstens einer je Quelle. Einzelquellen-Cluster werden aufgefüllt.

**Ehrlichere Karte.** Die größte Einzelquelle steht mit ihrem Anteil da
(Streetwear: 41 % Hypebeast), Kohäsion in Worten (tight/broad/loose), der
Mega-Trend erst ab 50 % Reinheit und mit Prozentangabe. Titel sind innerhalb
eines Laufs eindeutig, Abkürzungen stimmen. In einem vertikal-gescopten Lauf
entfällt die redundante Vertikal-Angabe.

**Detailseite `/trends/foresight/clusters/<id>`.** Der Schwerpunktvektor wird
persistiert, damit „zeig mir diesen Cluster" eine pgvector-Abfrage ist statt
einer gespeicherten Mitgliederliste (global wären das 568.000 Zeilen je Lauf).
Die Seite zeigt Messwerte, den großen Anteilsverlauf, die 12 zentrumsnächsten
und die 12 neuesten Signale der Nachbarschaft im selben Scope und Fenster, alle
Tags und einen Absatz zur Methode. Beide Listen streuen über Quellen: ohne das
war „am nächsten" acht von zwölf aus einer Zeitschriftenfamilie und „am neuesten"
zwölf Zeilen aus einem einzigen Bulk-Ingest vom selben Tag. Abfragezeit 0,09 s
bei angehobenem `hnsw.ef_search`.

## Was offen bleibt

- **Vertikal-Verschmutzung.** Im FASHION-Lauf steckt ein Cluster „Electric
  Vehicles · Luxury Automotive" mit 573 Signalen und einer über Musikwirtschaft.
  Das ist die Klassifizierung aus Stage 3/8, nicht die Cluster-Schicht.
- **Panel-Abdeckung 44 % global.** Die Hälfte des Korpus stammt aus Quellen, die
  es im frühen Fenster noch nicht gab. Das ist korrekt behandelt, heißt aber:
  die Momentum-Aussage stützt sich auf die ältere Hälfte.
- **k bleibt eine Schätzung** auf einer 4.000er-Stichprobe.
- **Alte Läufe** vor dem 15.09. haben die neuen Spalten nicht; die Seite liest
  sie als „kein Panel" und zeigt die Zusatzzahlen nicht.
