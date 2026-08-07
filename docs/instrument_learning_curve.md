# Wie viele Bewertungen braucht das Interessensmodell?

**Messung 2026-08-07, Feld `search:dairy` (4.144 Signale mit Embedding).**
Anlass: die Frage, ab wann der Algorithmus den Rest eines Felds selbst
verlässlich einordnen kann.

## Aufbau

Fünf Zielkonzepte innerhalb des Felds, **lexikalisch** definiert (Cheese,
Sustainability, Precision Fermentation, M&A/Funding, Regulation) — bewusst
unabhängig vom Embeddingraum, damit der Test nicht zirkulär wird. Grundrate
7,5 % im Mittel, also nah an der real beobachteten Positivrate des Owners
(16 von 157 ≈ 10 %).

Je Durchlauf: *n* Signale zufällig ziehen, Rocchio darauf trainieren (identisch
zu `relevance_direction`), die restlichen ~4.100 ranken, gegen die wahren
Labels messen. 30–60 Wiederholungen je Punkt.

## Befund 1 — der Engpass sind die Positiven, nicht die Bewertungen

| bewertet | ≈ Stichproben à 48 | Modell springt an (≥5 Positive) | Ø Positive |
|---:|---:|---:|---:|
| 24 | 0,5× | 0 % | 1,9 |
| 48 | 1,0× | 31 % | 3,7 |
| 72 | 1,5× | 63 % | 5,5 |
| 96 | 2,0× | 77 % | 7,4 |
| 144 | 3,0× | 92 % | 10,7 |
| 192 | 4,0× | 99 % | 14,6 |

Eine Stichprobe von 48 reicht in **zwei von drei Fällen nicht**, um das Modell
überhaupt freizuschalten.

## Befund 2 — Güte nach Zahl der Positiven

Ohne die Konditionierung von Befund 1 (die kleine *n* künstlich gut aussehen
lässt, weil nur die glücklichen Ziehungen die 5-Positiven-Hürde nehmen):

| Positive | AUC | Präzision@50 | Präzision@200 | Recall@200 | Lift |
|---:|---:|---:|---:|---:|---:|
| 3–4 | 0,838 | 50 % | 41 % | 30 % | 7,4× |
| 5–7 | 0,838 | 52 % | 44 % | 32 % | 7,5× |
| 8–11 | 0,873 | 60 % | 49 % | 37 % | 8,4× |
| 12–17 | 0,875 | 71 % | 53 % | 38 % | 9,5× |
| 18–27 | 0,885 | 72 % | 57 % | 40 % | 9,4× |
| 28–44 | 0,893 | 76 % | 58 % | 41 % | 10,2× |
| 45+ | 0,942 | 82 % | 70 % | 45 % | 9,3× |

Der Sprung liegt zwischen 8 und 17 Positiven; danach flacht es deutlich ab.

## Eichung gegen die Wirklichkeit — die Simulation ist optimistisch

Reale Anker aus dem Bestand des Owners: **98 Bewertungen → AUC 0,700**,
**146 → 0,753**. Die Simulation liegt bei vergleichbarem Volumen bei 0,86–0,87.

Ursache: ein lexikalisches Konzept („cheese") ist konsistent, ein menschliches
Interesse nicht — dieselbe Meldung bekommt an verschiedenen Tagen 1 oder 3.
**Die Tabellen sind deshalb eine Obergrenze; in der Praxis ist etwa ein Eimer
weiter zu rechnen** (statt 12–17 also 18–27 Positive anpeilen).

## Befund 3 — Vorschlagsgesteuertes Bewerten kollabiert

Naheliegende Produktidee: nicht zufällig vorlegen, sondern das, was das Modell
für relevant hält — dann sammelt man Positive viel schneller. Gemessen (Start
48 zufällig, dann 8 × 24 nach Modellrang statt zufällig):

| bewertet | Positive zufällig | Positive vorgeschlagen | AUC zuf. | AUC vorg. | P@50 zuf. | P@50 vorg. |
|---:|---:|---:|---:|---:|---:|---:|
| 48 | 3,6 | 3,6 | 0,848 | 0,848 | 58 % | 58 % |
| 96 | 7,4 | **30,1** | 0,863 | 0,861 | 63 % | **70 %** |
| 144 | 11,0 | 61,2 | 0,873 | 0,849 | 68 % | 64 % |
| 192 | 14,7 | 91,8 | 0,878 | 0,850 | 71 % | **51 %** |
| 240 | 18,2 | 119,8 | 0,883 | **0,833** | 74 % | **48 %** |

Positive kommen 7× schneller — und das Modell wird **schlechter**. Wer nur noch
hoch bewertete Kandidaten vorgelegt bekommt, liefert keine repräsentativen
Negativbeispiele mehr; der Rocchio-Vektor (Positiv-Schwerpunkt minus
Negativ-Schwerpunkt) degeneriert. Kurz nützlich (72–96), danach schädlich.

**Konsequenz: die geschichtete Zufallsstichprobe in `sample_for_rating` bleibt.
Eine „Bewerte, was wir vorschlagen"-Warteschlange wäre ein Rückschritt.**

## Grenze, die keine Menge Bewertungen aufhebt

Selbst bei 45+ Positiven enthalten die Top-200 nur **45 %** aller relevanten
Signale des Felds. Das Modell **ordnet** gut (die Spitze stimmt zu 70–82 %),
aber es **klassifiziert** die 4.144 nicht vollständig — der Schwanz bleibt
unsicher. Für „zeig mir mehr davon" ist das genau richtig, für „sortiere das
ganze Feld abschließend" nicht.

## Praktische Ableitung

Der billigste Hebel ist nicht mehr Bewerten, sondern eine **engere Suche**:
`dairy` ist breit, die Positivrate entsprechend niedrig. `plant-based dairy`
oder `dairy fermentation` heben die Grundrate und senken damit direkt die Zahl
der nötigen Bewertungen — der Engpass sind die Positiven.
