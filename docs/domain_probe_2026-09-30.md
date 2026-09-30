# Eine Domäne im Vektorraum abgrenzen — Food-Sonde (2026-09-30)

**Frage (Owner):** zweistufige Nester-Suche — erst die Signale über ihre **Embeddings** auf
eine Domäne („Food") eingrenzen, nicht über das Vertikal-Etikett, dann darin Nester suchen.
Hier gemessen: Stufe 1. Skript `scripts/space_eval/eval_domain_probe.py` (CPU, nur lesend,
~3 min), Rohdaten `data/space_eval/eval_domain_probe.json`.

## Aufbau

Lineare Sonde (logistische Regression, `class_weight='balanced'`) auf dem 1024er-Präfix,
trainiert mit Beschriftungen, die **nicht** aus unseren eigenen Klassifikatoren stammen:

- **Patente:** food = eine Prüfer-CPC-Unterklasse aus A23*, A21B/C/D, A22B/C, C12C/G/J,
  C13B/K (`patent_cpc`). 205.198 beschriftete Patentsignale, 68.104 food.
- **Forschung:** food = OpenAlex-Hauptthema in *Food Science* oder *Nutrition and
  Dietetics* (über die DOI). Die Pilot-Arbeiten aus #114 sind mit `--clean-text` (ohne
  „[Science · …]") eingebettet, alle anderen mit — eine Sonde könnte das Präfix lernen.
  **Training und Prüfung deshalb nur auf Forschung außerhalb des Pilots**; die Pilot-Arbeiten
  sind eine eigene Gegenprobe.
- Je Ebene und Klasse höchstens 40.000, jedes fünfte (Hash) zurückgelegt.
- Zwei Varianten: roh und ebenen-zentriert (Mittelvektor je Ebene abgezogen, wie die
  Themen-Anordnung der Wolke).

## Ergebnis (zurückgelegte Daten, Schwelle 0,5)

| | Präzision | Recall | AUC | Recall bei Präzision ≥ 0,9 |
|---|---|---|---|---|
| Patente, roh | 0,949 | 0,975 | 0,993 | 0,99 (Schwelle 0,21) |
| Patente, zentriert | 0,948 | 0,978 | 0,993 | 0,99 |
| Forschung, roh | 0,741 | 0,829 | 0,972 | 0,32 |
| Forschung, zentriert | 0,761 | 0,830 | 0,975 | 0,42 |
| Pilot-Arbeiten (Gegenprobe), Anteil als food erkannt | 0,72 roh / 0,69 zentriert | | | |

- **Patente trennt die Sonde fast fehlerfrei** von den Prüfer-Klassen.
- **Forschung gut, aber die Beschriftung ist unscharf:** unter den „falsch positiven"
  stehen Arbeiten, die offensichtlich Ernährung sind (Ernährungsempfehlungen, Mikrobiom und
  Ernährung, Blaubeer-Extrakt) — OpenAlex hat sie unter Medizin einsortiert. Die echte
  Präzision liegt über der gemessenen.
- Die Ebenen-Zentrierung hilft nur leicht (Forschung +0,02 Präzision).

## Anwendung auf den 90-Tage-Ausschnitt der Emerging-Schicht

346.637 Signale seit 02.07., davon 16.290 mit Etikett FOOD (4,7 %).

| | roh | zentriert |
|---|---|---|
| Sonde sagt food | 21.174 | 20.469 |
| davon mit Etikett FOOD | 10.164 | 9.750 |
| food laut Sonde, anderes Etikett | 11.010 | 10.719 |
| Etikett FOOD, laut Sonde nicht food | 6.126 | 6.540 |

- **Die Region ist eine andere Menge als das Etikett:** nur knapp die Hälfte trägt FOOD.
  Dazu kommen Ernährungsstudien (Etikett HEALTH), Lebensmitteltechnik-Patente (TECH),
  Lebensmittelhandel und Zölle (ECO) — genau das, was ein einziges Etikett abschneidet.
- **Was das Etikett FOOD mehr hat, ist Landwirtschaft:** Reis-Landrassen, Maisanbau,
  Buchweizen-Erträge, Schädlinge, Düngung. Die Sonde kennt Landwirtschaft nicht, weil ihre
  Beschriftung sie nicht enthält (CPC A01 und die OpenAlex-Subfelder Agronomy/Plant Science
  fehlen). Die Domäne ist damit **„Lebensmittel und Ernährung"**, nicht „Agrar und Food".
- Fehltreffer um 0,5 gibt es (Stahl-Gießmaschine, Wärmetauscher, Tierarzneimittel gegen
  Parasiten); eine Schwelle von ~0,7 räumt sie weitgehend ab.

## Folgerung

Stufe 1 trägt. Vor Stufe 2 (eigener Emerging-Bereich `domain:food`) ist zu entscheiden, ob
die Domäne **Lebensmittel und Ernährung** bleibt oder um **Landwirtschaft** erweitert wird
(CPC A01B/C/G/H/K/N/P, OpenAlex *Agronomy and Crop Science*, *Horticulture*, *Soil Science*,
*Animal Science and Zoology* als zusätzliche Positive) — beides ist mit derselben Sonde
machbar, nur mit anderen Beschriftungen.
