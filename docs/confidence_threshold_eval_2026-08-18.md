# Trennt die Auto-Publish-Schwelle von 0,85 gute von schlechten Artikeln?

**Anlass (Owner, 18.08.2026):** Von rund 800 täglich erzeugten Trends bleiben
~320 unveröffentlicht. 97,5 % davon scheitern allein an der Confidence, nur 8 an
den Qualitätsgates. Die Draft-Halde steht bei ~9.900 und wächst um ~340 pro Tag.

**Was „Confidence" ist:** der Relevanzwert aus **Stufe 1** („ist das überhaupt ein
Trendsignal?"). Er wird unverändert in den Trend übernommen und entscheidet neun
Stufen später über die Veröffentlichung — über den fertig geschriebenen Text sagt
er nichts. `trend_score` taugt nicht als Gegenprobe, er wird aus der Confidence
selbst berechnet (`crs.py:102`, Korrelation 0,91).

## Aufbau

`scripts/eval_confidence_threshold.py`, fester Seed, Zeitfenster 14 Tage.

- **A** — zurückgehalten, `status='draft'`, Confidence 0,75–0,85
- **B** — automatisch veröffentlicht, Confidence ≥ 0,85

Erst deterministische Maße ohne GPU. Dann ein **blinder Richter** über den
gemischten Pool: Qwen3.8-27B, bewusst eine andere Modellfamilie als der
Gemma-Generator, ohne Kenntnis von Gruppe, Confidence oder Reihenfolge.
Schema-validierte Antwort, n=200 je Gruppe.

## Ergebnis

| | A zurückgehalten | B veröffentlicht | Differenz | |
|---|---|---|---|---|
| als echtes Signal | 62,5 % | 80,0 % | +17,5 pp | **p=0,0002** |
| als quellentreu | 24,0 % | 27,0 % | +3,0 pp | p=0,57 |
| Substanz (Mittel 1–5) | 2,30 | 2,56 | +0,26 | **p=0,00001** |
| Wörter (Median) | 109 | 108 | — | |
| abgeschnittener Body | 0 % | 0 % | — | |

**Die Schwelle ist nicht willkürlich.** Sie trennt Relevanz deutlich und Substanz
schwach, aber real. Das war zu erwarten — sie misst ja Relevanz.

**Sie trennt aber keine Faktentreue.** 24 % gegen 27 %, statistisch nicht
unterscheidbar. Wer die Schwelle für ein Qualitätssieb hält, irrt.

**Und sie hält viel Brauchbares zurück.** 62,5 % des Bandes 0,75–0,85 werden
blind als echte Signale eingestuft — bei ~110 Artikeln täglich in diesem Band
sind das rund **70 verlorene Signale pro Tag**. Ein Absenken der Schwelle ist
damit kein reiner Gewinn, sondern ein Zielkonflikt: es brächte auch die 37,5 %
mit, die keine Signale sind.

## Zwei Nebenbefunde, die schwerer wiegen

**1. Die Artikel sind zu kurz — und zwar seit dem Modellwechsel.**

Zielkorridor 150–250 Wörter. Median heute **109**, im Ziel nur **2,5 %**
(n=5.308, veröffentlicht, 14 Tage). Der Einbruch ist tagesgenau:

| | Median |
|---|---|
| 08.–12.07. | 131–133 |
| **14.07. (Umstieg auf Gemma-4-26B, #11)** | **105** |
| 15.–20.07. | 108 |

Monatsmedianen: Mai 168, Juni 203, Juli 121, August 109. Die Begründung für #11
in `CLAUDE.md` lautet, Gemma treffe „zudem das 150–250-Wörter-Ziel, das das 30B
unterschritt". Die Produktionsdaten widersprechen dem. Der A/B-Test damals hatte
n=70; der Dauerbetrieb sagt etwas anderes.

**2. Der Grounding-Gate prüft Zahlen, keine Aussagen.**

Der Richter beanstandet in beiden Gruppen fast immer denselben Bautyp:
„spekulative Prognose ohne Quellendeckung", „erfindet Verifikationsverfahren,
die nicht in der Quelle stehen". Deterministisch nachgezählt an 3.000
veröffentlichten Artikeln: **43,7 %** enthalten eine Spekulationsformel
(„will likely", „is expected to", „positions X to"), **38,4 %** davon im
Schlusssatz.

Das ist dasselbe Muster, das am 04.08. als „erfundene Zeithorizonte" verworfen
wurde — nur breiter, und es passiert den Gate ungehindert, weil dort keine
Ziffer steht. Die 0 % „erfundene Zahl" in Gruppe B sind also kein Freispruch,
sondern die Reichweite des Messgeräts.

## Was daraus folgt (Entscheidung offen)

Die Schwelle zu senken löst das kleinere Problem und schafft ein neues. Die
beiden Nebenbefunde betreffen **alles, was veröffentlicht wird**, nicht nur den
Rand — und wären damit vorrangig.

Rohdaten: `data/eval_confidence_threshold_n200.json` (n=200/Gruppe, Seed 20260818).
