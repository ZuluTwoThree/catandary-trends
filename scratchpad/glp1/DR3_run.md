# DR-Lauf 3 (2026-09-07) — Runde 13, Dossier #28 `glp1-dr3` v1

Auftrag #22, dieselbe Frage wie DR1/DR2. Laufzeit 1614 s. Kein Denken
(Bericht und Revision `enable_thinking: false`), Sampling nicht-denkend nach
Modellkarte mit presence_penalty 0,5.

## Was der Lauf anders gemacht hat

| | DR2 (jury_17: 5,7) | DR3 |
|---|---|---|
| Websuchen | 61 | 87 (+26 Katalysator-Welle) |
| Akteur-Anfragen an Scheinentitäten | 16 („Phase phase 3 …", „polypeptide court ruling …") | **0** |
| Entitäten 2. Welle | semaglutide, **polypeptide**, orforglipron, tirzepatide | semaglutide, tirzepatide, liraglutide, orforglipron, retatrutide, bofanglutide, dulaglutide, exenatide |
| Faktenzettel | 29 Fakten / 12 Quellen | 48 Fakten / 18 Quellen |
| Kalender-Kandidaten vorgelegt | — | 28 aus 21 Quellen |
| Aufwands-Anker vorgelegt | — | 5 |
| Primärquellen-Lesungen (Auffangnetz, Logzeilen) | 26 | 34 |
| Kalenderzeilen im Bericht | 3 (alle Horizon Europe, 1 Quelle, 0 mit Themenbezug) | 6 (alle GLP-1, 4 Quellen: CagriSema-FDA H2 2026, Retatrutid-BLA Q1 2027, Wegovy-Pille ex-US H2 2026, Preisschritt 31.08.2026, CHMP Q3 2026) |
| Aufwandsfeld beziffert (nach R13-4b) | 0 von 3 | 3 von 3 (EIC Accelerator ≤ 2,5 Mio. €, 24 Monate, mit Beleg) |
| Gestrichen nach der Revision | 23 Sätze | 36 Sätze (8 Zahlen ohne Beleg, 12 themenfremde Zitate, 4 quellenlose Zahlen) |
| Strukturbefund nach Revision | 6 | 1 (Fließtext 2.926 Wörter, Obergrenze 2.800) |

## Jury-nahe Messung (`jury_metrics.py`)

| | C_sonnet (Deep Research) | DR2 | **DR3** |
|---|---|---|---|
| Einschlägige Zukunftstermine | 9 auf 15 Quellen | 9 auf 11 | **22 auf 16** |
| Benannte Akteure | 23 | 17 | 23 |
| … davon mit Zahl im selben Satz | **14** | 5 | 8 |
| Sätze mit Zahl | 25 (1.997 Wörter) | 11 (2.888) | 28 (4.327 inkl. Tabellen) |
| Optionen / Aufwand beziffert | 0 / 0 | 3 / 0 | **3 / 3** |
| Kettenabdeckung (Wiss./Pat./Förd./Markt) | 18/12/5/15 | 10/14/10/12 | 9/9/10/25 |

Was die Messung vorab sagt: die beiden größten Abstände aus jury_17 — Termine
und Aufwand — sind gedreht; die Spezifität (Akteure mit Zahl) ist von 5 auf 8
gestiegen und liegt weiter unter den 14 des Deep-Research-Texts.

## Bekannte Schwächen vor dem Gutachten

- Kurzfassung trägt **zwei** statt drei Aussagen (die dritte fiel der
  Primärquellen-Regel zum Opfer).
- Kalender: drei von sechs Zeilen aus derselben Sekundärquelle (ObesityIntel),
  als „(secondary source only)" markiert; die Katalysator-Muster fanden zu
  orforglipron/retatrutide keine CHMP-Termine — der Bericht sagt das.
- Fließtext 126 Wörter über der Obergrenze.

## Ergebnis: jury_18 — Deep Research 6,3 · DR3 5,9 · Sieger Deep Research

| Kriterium | jury_17 DR2 : Sonnet | jury_18 **DR3** : Sonnet |
|---|---|---|
| Belegbarkeit | 6 : 6 | **7** : 5 |
| Spezifität | 5 : 8 | 5 : 8 |
| Handlungsrelevanz | 6 : 7 | **6** : 5 |
| Abdeckung | 5 : 8 | 5 : 8 |
| Zeitliche Einordnung | 3 : 7 | **5** : 6 |
| Ehrlichkeit | 8 : 6 | **8** : 5 |
| Struktur | 7 : 6 | 5 : 7 |
| Durchschnitt | 5,7 : 6,9 | **5,9 : 6,3** |

Abstand 1,2 → 0,4 (anderer Gutachter, Sonnet-Text 6,9 → 6,3 — Gutachterstreuung
ist Teil des Abstands). Drei Kriterien gedreht (Belegbarkeit, Handlungsrelevanz,
Zeit), Spezifität und Abdeckung unverändert 5:8, Struktur von 7 auf 5 gefallen:
„fünf beschädigte Stellen" — Satzbruchstücke, die die mechanische Streichung von
36 Sätzen hinterlassen hat („calcium (863 mg vs. 8–18 mg)", „Named actors and
figures: in H2 2026", verwaiste Absätze). Aufwand: der Gutachter zählt nur 1/3,
weil eine EIC-Förderobergrenze kein Kostenmaßstab ist. Kalender: 2 von 6 Zeilen
am Prüfdatum vergangen (31.08.2026, Q3 2026) — Jahresvergleich statt Stichtag,
seither behoben (`_label_passed`, `CAL_MAX_PER_SOURCE` 4 → 2).
