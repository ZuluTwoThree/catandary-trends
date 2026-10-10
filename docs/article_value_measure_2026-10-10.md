# Artikel vs. Signalkarte vs. Story-Artikel — Messung 10.10.2026

Owner-Frage 10.10.: Was bringt der generierte Artikel gegenüber der Quelle plus Embedding? Zwei
Richtungen: (A) Signalkarte statt Artikel, (B) weniger, stärkere Artikel je Story mit Messblock.
Beide Messungen nur lesend, CPU, Skripte im Scratchpad der Sitzung (nicht versioniert).

## Basis (veröffentlicht, sort_date letzte 14 Tage)
14.843 Artikel = 1.060/Tag, Ø 150 Wörter, 16 % aus Quellen < 1.000 Zeichen.
`trends` gesamt: 2.082.049 Signale, 128.419 veröffentlicht.

## 1. Story-Ausbeute (Gruppierung ohne Markenschlüssel)
Paare innerhalb 48 h, Union-Find, „Story“ = ≥ 2 verschiedene Hosts.

| Variante | Stories/Tag | davon ≥ 3 Hosts (14 T.) | Artikel in Stories | größte |
|---|---|---|---|---|
| A Kosinus ≥ 0,80 | **67** | 314 | 2.723 (18 %) | 20 |
| B Kosinus ≥ 0,85 | 47 | 200 | 1.793 (12 %) | 18 |
| C ≥ 0,75 + seltener Titelbegriff | 75 | 354 | 3.127 (21 %) | 46 |
| D ≥ 0,80 + seltener Titelbegriff | 64 | 297 | 2.522 (17 %) | 20 |

Handprüfung 20 Gruppen je Variante: **A 19 von 20 dasselbe Ereignis** (eine Gruppe: zwei Meldungen
zur selben Initiative). C verkettet zu Themenblöcken (GPT-6-Astra-Absage + UK-Warnung, 46 Artikel).
Die bestehende Gruppierung (#109, Markenschlüssel) fasst nur 9 % (1.337 Artikel in 625 Gruppen).
Nebenbefund: ~127 Artikel/Tag sind Folgeberichte desselben Ereignisses.

## 2. Messkontext je Artikel (Stichprobe 1.500)
Nächste Nachbarn in **Primärdaten** der letzten 24 Monate (Domain-Service-Kopie, Stand 02.10.):
Wissenschaft = OpenAlex/arXiv/bioRxiv/medRxiv/Journale (372 k), Patente (168 k), Förderregister
(57 k). Vektoren je Ebene um den Ebenen-Mittelwert zentriert (Stil raus, wie Signal Space „Topic“).
Schwellen per Handeichung an Beispielen: Wissenschaft 0,55 · Patente 0,52 · Förderung 0,55
(darunter locker/falsch; „streng“ = 0,60/0,58/0,60).

| | normal | streng |
|---|---|---|
| Wissenschaft | 17 % | 7 % |
| Patente | 5 % | 1 % |
| Förderung | 6 % | 2 % |
| **≥ 1 Ebene** | **21 %** | 9 % |
| ≥ 2 Ebenen | 7 % | 2 % |

Je Vertikale (≥ 1 Ebene, normal): HEALTH 43 %, TECH 27 %, FOOD 23 %, ECO 16 %, LIFESTYLE 16 %,
FASHION 8 %, BIZ 7 %, DESIGN 0 %. Story-Artikel haben nicht mehr Kontext (18 %) als Einzelmeldungen.
In einem Nest (333 Nester der Läufe vom 03.10., Regel des Archiv-Scans): **6,7 %**.

Grenze: gemessen wird gegen das EINGEBETTETE (Fresh-Sweeps, Food-Pilot, 60-Tage-Patente) — nicht gegen
47,7 Mio. `research_corpus` oder den Patent-Volltext. Ein phrasenbasierter Kontext (wie Field Watch)
erreicht mehr, braucht aber Suchbegriffe je Artikel.

## Folgerung
- Ein Messblock trägt nur bei ~1 von 5 Artikeln (BIZ/DESIGN/FASHION kaum). „Jeder Artikel mit
  Einordnung“ geht mit dem eingebetteten Bestand nicht; „nur Artikel mit Einordnung“ wären ~220/Tag
  (≥ 1 Ebene) bzw. ~75/Tag (≥ 2 Ebenen).
- Story-Gruppierung A ist sofort brauchbar (67/Tag, ~95 % sauber) und spart als Einheit ~127
  Generierungen/Tag — Kontext bringt sie nicht mit.

## Nachtrag: Wirkung von Dedup und Relevanzfilter (Owner-Frage 10.10.)
- **Stories:** Stage 5 verwirft Presse-Einträge mit Kosinus > 0,92 zu einem Artikel der letzten 30 Tage
  (14 Tage: 499 mit Vektor, Median-Kosinus zum Treffer 0,947) plus 170 Titel-Dubletten ohne Vektor.
  Wieder eingerechnet: **67 → 76 Stories/Tag** (≥ 3 Hosts 22 → 25). Mit den vom Relevanzfilter
  verworfenen Presse-Einträgen (7.531 mit Vektor) 100/Tag (≥ 3 Hosts 32) — der Zuwachs enthält aber
  Ereignisse, die nie Trendsignal sind.
- **Kontext:** Dedup entfernt Kopien, nicht Themen — ein naher Vertreter bleibt im Bestand. Die
  gefilterten Forschungs-/Förderzeilen mit Vektor (37.010 Wissenschaft, davon 33.415 Relevanz;
  23.780 Förderung, alle Dedup) hinzugenommen: Wissenschaft 17,2 → 18,2 %, Förderung 6,5 → 6,7 %.
  Der begrenzende Faktor ist, was überhaupt eingebettet ist, nicht was aussortiert wurde.
