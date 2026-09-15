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

## Namen (Punkt 5, seit 2026-09-15 abends)

Zwei Schlagworte mit Mittelpunkt sind kein Trendname. „World · Action" war in
Wahrheit ein Nest über World-Action-Modelle in der Robotik, und die Schlagworte
konnten das nicht sagen.

`pipeline/nest_naming.py` legt dem lokalen Modell die **zentrumsnächsten**
Titel eines Nests vor und lässt es benennen. Das Modell sieht ausdrücklich
**keine** Messwerte, nur Titel und Schlagworte; die Zahlen bleiben beim Code,
der sie gerechnet hat.

Jeder Name wird geprüft, bevor er angenommen wird:

- 2 bis 7 Wörter, keine Endsatzzeichen, keine Anführungszeichen
- **jedes bedeutungstragende Wort muss im Nest selbst vorkommen** (Titel oder
  Schlagworte), Plurale eingerechnet. Dieselbe Regel wie beim Grounding-Gate der
  Artikel: „Perovskite Tandem Modules" für ein Nest, in dem „tandem" nie
  vorkommt, ist ein plausibles Etikett für etwas, das wir nicht gemessen haben.
- keine leeren Kategorien („Machine Learning Research")
- innerhalb eines Laufs eindeutig — zwei FASHION-Nester kamen beide als
  „Cosmetic Composition" zurück
- Hausschreibweise, weil Patenttitel in Großbuchstaben schreien

Fällt ein Name durch, bleibt das deterministische Schlagwort-Label stehen und
der Grund wird gespeichert (`llm_label_note`). Die Karte zeigt **beides**: oben
den Namen, darunter klein „tags say: …". Damit wird die Benennung nie zur
Wahrheitsquelle — steht daneben etwas anderes, sieht man es sofort.

Der Namensschritt ist der **einzige** GPU-Schritt der Schicht (eine Übergabe für
alle Nester, wie beim Research Pulse; ~0,2 s je Nest). Er ist abschaltbar
(`--no-llm-names`), und eine verweigerte Übergabe lässt einfach die
Schlagwort-Labels stehen.

## Prüfung gegen bekannte Trends (Punkt 6)

`scripts/validate_emerging.py` beantwortet die einzige Frage, die zählt: findet
die Schicht Dinge, die nachweislich stattgefunden haben, und wie früh?

Die Prüfmenge steht in `known_trends.yaml` — 20 datierbare Trends mit dem Monat,
in dem sie unstrittig im Mainstream ankamen, **und der Begründung für dieses
Datum**. Die Daten sind eine begründete Einschätzung, keine Messung; sie liegen
bewusst als Datei vor, damit der Owner sie korrigiert. Dazu drei Gegenproben
(mittelalterliche Falknerei, Studio-Töpferei, Cembalo-Stimmung), die nie
auftauchen dürfen.

Verfahren: für eine Reihe von Stichtagen läuft die Erkennung auf dem
Zeitschnitt, der **vor** diesem Tag endet, und jeder bekannte Trend wird gegen
die Nest-Zentren gehalten. Der erste Stichtag mit Treffer, verglichen mit dem
Mainstream-Monat, ist die Vorlaufzeit.

Die Schwelle ist gemessen, nicht geraten: echte Themen trafen ihr eigenes Nest
mit Kosinus 0,82 bis 0,86, die drei Gegenproben kamen auf 0,53 bis 0,60. 0,75
liegt in der leeren Mitte, und der Bericht druckt jeden Abstand mit.

**Was der Test nicht kann.** Er ist ein Rücktest auf `published_date`, keine
Rekonstruktion des damaligen Wissensstands. Eine Quelle, die wir erst 2026
angeschlossen haben, liefert für einen 2024er-Schnitt nichts, weil es keinen
Backfill gibt. Für frühe Stichtage ist das Ergebnis deshalb konservativ, für
späte ehrlich. Der Bericht druckt zu jedem Stichtag die Schnittgröße mit, damit
ein Vorlauf aus 3.000 Dokumenten nicht als Befund gelesen wird.

## Ergebnis des ersten Rücktests (2026-09-15)

21 Stichtage von 2021-07 bis 2026-09, 90-Tage-Schnitte, je 60 dichteste Nester,
Treffer ab Kosinus 0,75 **und** einem Kennwort des Trends im getroffenen Nest.

**9 von 20 bekannten Trends gefunden, 5 davon vor dem Mainstream, Median-Vorlauf
6 Monate.** Die drei Gegenproben lagen nie über 0,62, die Zuordnung selbst ist
also sauber.

| | |
|---|---|
| gefunden, mit Kennwort im Nest | 9 von 20 |
| davon vor dem Mainstream | 5 |
| Median-Vorlauf der frühen Funde | 6 Monate |
| nie gefunden | 11 |
| davon: nicht einmal das Feld im Korpus | 5 |
| höchste Ähnlichkeit einer Gegenprobe | 0,62 |

**Die erste Fassung des Tests log, und zwar nach oben.** Ohne die Kennwort-Regel
meldete er 15 von 20 und 23 Monate Median-Vorlauf. Der Grund stand in den Daten:
ein einziges Nest mit 134 Dokumenten namens „Machine Learning · Neural Networks"
lag nahe genug an *LLM-Agenten*, *kleinen Sprachmodellen* und
*Vision-Language-Action-Modellen*, um allen dreien 26 Monate Vorlauf zu
schenken. Gemessen wurde das Feld, nicht der Trend. Seitdem muss das getroffene
Nest eines der Kennwörter des Trends auch wirklich enthalten; beide Zahlen
stehen im Bericht nebeneinander, die lockere als Obergrenze.

**Auch die verbliebenen 5 frühen Funde sind nicht alle bare Münze.** Bei
Perowskit (+26) und GLP-1 (+18) ist das Kennwort älter als der Trend: Perowskit-
Forschung lief 2021 längst, das Thema war aber die *Tandem*-Zelle; GLP-1 war seit
Jahren Diabetes-Forschung, der Trend war die Adipositas-Welle. Wo das Feld dem
Trend um Jahre vorausgeht, trennt eine Stichwortprüfung die beiden nicht.
Belastbar früh sind damit eher **3 von 20**.

**Was die 11 Fehlschläge sagen.** Bei fünf Trends fand der Test nicht einmal das
Feld: Inferenz-Effizienz, Psychedelika, Wärmepumpen, Quiet Luxury, Hyrox. Das
ist kein Erkennungs-, sondern ein Quellenproblem — dieselbe Lücke, die schon die
dünnen Vertikalen DESIGN, FASHION und LIFESTYLE zeigen. Bei den übrigen sechs
war das Feld da, aber nie ein Nest, das den Trend beim Namen nennt.

**Ehrliche Lesart.** Der Detektor findet Themen, die im Korpus dicht vertreten
sind, und er findet sie manchmal früh. Er ist keine Früherkennung, solange er
die Hälfte der Prüfmenge nicht findet und der Vorlauf bei den gefundenen so weit
streut. Die Zahl, die sich lohnt zu verfolgen, ist nicht der Median-Vorlauf,
sondern die Trefferquote — und die hängt an den Quellen.

Wiederholen mit `.venv/bin/python scripts/validate_emerging.py`; Bericht nach
`data/emerging_validation.json`. Die Mainstream-Daten in `known_trends.yaml`
sind eine begründete Einschätzung des Modells, keine Messung — jede Korrektur
durch den Owner ändert die Vorlaufzeiten unmittelbar.

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
