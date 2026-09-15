# Emerging-Nester: die zweite Schicht neben den Clustern (2026-09-15)

Auftrag des Owners nach der Cluster-Überarbeitung: „was müsste man tun, dass
wirklich Trends entdeckt werden?" Umgesetzt sind die beiden ersten Punkte der
Antwort — Nester suchen statt aufteilen, und nach Neuheit bewerten statt nach
Anteil. Die Schicht liegt **neben** `/trends/foresight/clusters`, sie ersetzt
nichts.

## Warum die Cluster-Schicht keine Trends finden kann

k-Means teilt den Bestand restlos auf. Jedes Dokument landet in einer von 28
Zellen, also ist eine Zelle ein Themengebiet mit 20.000 Einträgen. Ein Trend ist
die umgekehrte Form: eine kleine, dichte, junge Stelle, zu der der allergrößte
Teil des Bestands **nicht** gehört. Solange der Algorithmus alles einsortieren
muss, kommt diese Form nicht heraus.

## Verfahren

**Schritt 1, Nester finden.** Ein frischer Zeitschnitt (Default 90 Tage) wird
fein zerlegt, dann bleiben nur die Zellen, die wirklich dicht sind (mittlerer
Kosinus zum Zentrum ≥ 0,75), und Zellen mit fast gleichem Zentrum werden wieder
zusammengefügt. Alles andere ist Rauschen: global bleiben 12 % des Schnitts
übrig, 83 Nester aus 784 Zellen.

Gemessene Alternativen am selben Tag, 314.000 Dokumente über 90 Tage:

| Verfahren | Ergebnis | Kosten |
|---|---|---|
| HDBSCAN, Standardauswahl, PCA-50 | 2 Klumpen mit 6.000 und 12.000 Einträgen | 114 s auf 60.000 Zeilen |
| HDBSCAN, Blattauswahl, PCA-50 | 58 Nester, 93 % Rauschen, Median 44 | 104 s auf einer **Stichprobe** von 60.000 |
| feines k-Means + Dichtefilter | 83 Nester, 88 % Rauschen, Median 60 | 40 s auf **allen** 314.000 |

Die Blattauswahl trifft die richtige Form, sieht aber wegen des überlinearen
Aufwands nie den ganzen Schnitt. Deshalb k-Means. `DOCS_PER_CELL` ist ein
Rechenbudget, kein Prinzip: der Aufwand wächst mit n·k·d, also bekommt der
globale Schnitt eine grobe Zerlegung und findet nur die größeren Nester, während
kleine Bereiche 40 Dokumente je Zelle bekommen. DESIGN hatte bei 58 Zellen genau
eine Zelle über der Dichteschwelle und bei 120 Zellen zweiundzwanzig — die
Zellzahl war der Engpass, nicht die Daten.

**Schritt 2, datieren.** Für jedes Nest läuft der **gesamte** Bestand am
Zentrumsvektor vorbei, und es wird je Monat gezählt, wie viele Dokumente
irgendeines Alters dem Nest ähneln. Der Speicher bleibt bei einem Block, weil
nur Zähler überleben. 1.749.202 Dokumente über 449 Monate in 212 Sekunden.

Daraus:

- **first_month / age_months** — erster Monat mit mindestens drei Ähnlichen.
  Das ist die Messung, die die Cluster-Schicht nicht machen kann.
- **novelty_lift** — Anteil der Treffer eines Nests in den letzten sechs Monaten,
  geteilt durch den Anteil, den der **Korpus** dort hat. 1,0 heißt: verteilt wie
  das Archiv. 4,5 ist die Sättigung, also jede Spur stammt aus den letzten sechs
  Monaten. Korpus-normiert, damit unser eigenes Mengenwachstum nichts erfindet.
- **accel** — Rate der letzten drei Monate gegen die der neun davor, beides
  korpus-normiert. `null` heißt: vorher gab es gar nichts.
- **new_terms** — Schlagworte des Nests, die vor 24 bis 36 Monaten im Korpus
  selten waren und heute häufig sind.

## Erster Lauf, global

83 Nester. Was oben steht, ist spezifisch und datiert:

| Nest | erstmals | neue Begriffe |
|---|---|---|
| Retrieval Augmented Generation | 2025-12, 10 Monate | retrieval augmented generation |
| Robotics · Vision Language Models | 2026-04, 6 Monate | vision_language_models |
| LLM Optimization · Attention Mechanisms | 2025-12, 10 Monate | kv cache compression |
| Battery Technology · Battery Management | 2026-07, 3 Monate | state of charge estimation, soh estimation |
| Defect Passivation · Electron Selective Layer | 2026-07, 3 Monate | electron selective layer |

Und was oben steht, ist teilweise Müll. Das stärkste Nest des ersten Laufs waren
647 Dokumente Pseudowissenschaft („E8 Intelligence Research") aus einem
Massen-Ingest, tatsächlich dicht, tatsächlich brandneu. Genau dafür trägt jede
Karte ihre Schwächen offen: Quellenzahl, Anteil der größten Quelle und
`tagged_share`, also wie viel des Nests je eine Klassifizierungsstufe der
Pipeline gesehen hat. Bei diesem Nest ist das 0 %.

**Die Schicht ist ein Sucher, kein Urteil.** Sie sortiert nach Aktualität der
Belege, und das hebt zwangsläufig auch Tagesnachrichten („Apple · Executive
Move") und alles, womit eine Massenquelle den Korpus flutet.

## Der Fehler, der sich wiederholt hat: neue Quelle ist nicht neuer Trend

Der erste FOOD-Lauf füllte seine Spitzenplätze mit Agronomie-Nestern, alle
„erstmals vor 3 bis 5 Monaten" — und alle aus Journal-Sweeps, die vor 3 bis 5
Monaten zu liefern begannen. Das Alter maß unsere Abonnements, nicht die Welt.
Das ist derselbe Fehler wie beim Cluster-Momentum vor dem festen Quellenpanel,
nur an anderer Stelle: **jedes Neuheitsmaß über einem wachsenden Korpus muss den
Quellenzugang kontrollieren.**

Gegenmittel: der Archiv-Scan merkt sich nebenbei, in welchem Monat jede Quelle
zum ersten Mal im Korpus auftaucht. Daraus je Nest `established_share`, der
Anteil seiner Dokumente aus Quellen, die schon vor 24 Monaten gelesen wurden.
Unter 50 % gilt das Alter nicht als Aussage über die Welt: das Nest zählt nicht
als „jung", das Alter bekommt ein Fragezeichen, und die Karte sagt den Grund.

## Betrieb

    python -m pipeline.emerging_snapshot --all-verticals
    python -m pipeline.emerging_snapshot --scope vertical:FOOD --window-days 120

Nur CPU, kein Modell, keine GPU. Global rund 5 Minuten, kleine Vertikale
Sekunden. Kein Cron (Radar-Regel); auf der Seite steht der Knopf
**Recompute pockets**, der wie die anderen Desk-Jobs in einem eigenen
systemd-Scope läuft. Tabellen `emerging_runs` / `emerging_nests`, additiv
angelegt, je Scope bleibt ein Lauf stehen.

Ein Bereich, der im 90-Tage-Schnitt zu dünn ist oder in dem keine Zelle die
Dichteschwelle erreicht, bekommt **einmal** ein 180-Tage-Fenster, bevor er
übersprungen wird.

## Was noch fehlt

Aus der Antwort an den Owner sind die Punkte 3 bis 6 offen:

- **Bestätigung über die vier Ebenen** (Forschung → Patente → Förderung →
  Markt). Die Ebenen gibt es bereits als `TIER_FILTERS`; ein Nest, das in allen
  vieren in sinnvoller Reihenfolge vorkommt, wäre ein belegter Trend. Das ist
  der größte offene Hebel und der einzige, der wirklich unterscheidbar wäre.
- **Akteure zählen statt Artikel.** Die Extraktion zieht Marke, Produkt und
  Geografie je Artikel; für die Trendfindung wird davon nichts benutzt. Die Zahl
  verschiedener Akteure über die Zeit misst Ausbreitung, Artikelzahl nur
  Berichterstattung.
- **Namen vom Modell.** Zwei Schlagworte mit Mittelpunkt sind kein Trendname.
  Bei 83 Nestern kostet ein Aufruf je Nest fast nichts, mit Prüfung gegen die
  Mitglieder.
- **Prüfung gegen bekannte Trends.** Ohne einen Test an 20 datierbaren, wirklich
  eingetretenen Trends ist alles hier Meinung. Erst diese Zahl rechtfertigt nach
  außen das Wort Früherkennung.
