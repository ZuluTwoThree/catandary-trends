# Signalwolke: bessere Projektion? Messlatte + Hebel 1 und 2 (2026-09-28)

**Frage (Owner, 27.09.):** Wie werden Suche und Clusterung in der 3D-Wolke
(`/trends/foresight/map`, *Signal cloud*) besser? Zwei Hebel standen zur Wahl:

1. **PCA-Engpass.** Produktion: L2 → PCA 50 (hält 39 % der Varianz) → UMAP 3D.
2. **Schreibstil.** Forschung, Patente, Förderung und Fachpresse liegen auch beim
   selben Thema als eigene Kontinente — die Einbettung kodiert das Register mit.

**Kurzantwort:** Beide Hebel wirken, und sie addieren sich. Am besten ist
**„Ebenen-Mittel abziehen + UMAP mit Kosinus direkt auf 1024 Dimensionen"**: die Treffer
eines Suchbegriffs liegen um gut 60 % dichter beisammen (0,21 → 0,34, bei allen 28 Begriffen besser),
Forschung und Markt zum selben Thema rücken auf weniger als die Hälfte des alten Abstands
zusammen, und die Nachbarschaften stimmen öfter mit den Prüfer-CPC-Klassen und den
OpenAlex-Themen überein. Preis: etwa 4 Minuten mehr Rechenzeit je Wolkenlauf.

**Umgestellt am 28.09. (Owner: „Ja … und den bisherigen Stil per Schalter behalten"):**
*Topic* ist die Standard-Anordnung der Wolke, die alte heißt *Style* und liegt hinter dem
Schalter *Layout*. Ein Lauf rechnet beide auf derselben Stichprobe und lädt jedes Signal
einmal. Lauf 4: 1.224 s (vorher 597 s — der zweite Transform über 1,4 Mio. Signale und
das Kosinus-Einsetzen kosten mehr als hochgerechnet), Spitze 4,0 GB, 52 MB; Topic 25,1 %
Nachbarn@10 / Trust 0,923, Style 23,9 % / 0,937 — deckungsgleich mit der Messlatte.

## Die Messlatte (`scripts/space_eval/eval_projection.py`)

Reine CPU, liest nur, schreibt nichts in die Datenbank. Für jede Variante gleich:

| | |
|---|---|
| **Basis** | 200 Signale je Monat über das Fenster des jüngsten Wolkenlaufs (2011-10 bis 2026-09) = **36.000**, derselbe Hash wie `pipeline.signal_space`. Darauf wird die Projektion **gelernt**. |
| **Treffer** | 28 feste Suchbegriffe über die drei Quellen der Wolkensuche (Titel/Zusammenfassung/Tags, Forschungs-Abstracts, Patent-Abstracts), je Begriff höchstens 600 und je Ebene höchstens 150 → **13.996**, per `transform` **eingesetzt** wie im Produktionslauf die 1,4 Mio. |
| **Treue** | Nachbarn@10 bleiben + Trustworthiness des 3D-Bilds gegen den **ursprünglichen** 1024er-Raum (eine Variante darf nicht gewinnen, indem sie den Raum umdefiniert). |
| **Reinheit** | Anteil der 10 nächsten beschrifteten Nachbarn mit derselben Beschriftung: CPC-Unterklasse der Prüfer (4.369 Patente), OpenAlex-Thema (7.188 Arbeiten über die DOI) und -Subfeld. |
| **Begriffszusammenhalt** | Für die Treffer eines Begriffs: Anteil ihrer 10 nächsten Nachbarn (unter Basis + allen Treffern), die Treffer desselben Begriffs sind. Leuchtet eine Suche eine Region auf oder verstreuten Staub? |
| **Ebenenabstand** | Je Begriff mit ≥ 10 Treffern in mindestens zwei Ebenen: mittlerer Abstand der Ebenen-Schwerpunkte ÷ Median-Abstand zweier Zufallssignale. 0 = Forschung und Markt am selben Fleck, ~1 = so weit wie zwei beliebige Signale. |

## Ergebnis (Seed 42; Seeds 7 und 1234 weichen je Kennzahl um höchstens ±0,01 ab)

| Variante | Nachbarn@10 | Trust | CPC | Thema | Subfeld | Begriffs­zusammenhalt | Ebenen­abstand |
|---|---|---|---|---|---|---|---|
| *Obergrenze: 1024er-Raum, Kosinus* | — | — | *0,644* | *0,243* | *0,340* | *0,543* | *0,182* |
| **Produktion** (PCA 50, euklidisch) | 0,239 | 0,937 | 0,470 | 0,123 | 0,226 | 0,207 | 0,469 |
| PCA 256 | 0,263 | 0,937 | 0,502 | 0,162 | 0,270 | 0,286 | 0,357 |
| Kosinus auf 1024 | 0,256 | 0,928 | 0,514 | 0,168 | 0,270 | 0,295 | 0,332 |
| Ebenen-Mittel abziehen | 0,226 | 0,928 | 0,529 | 0,126 | 0,231 | 0,229 | 0,216 |
| Ebenen-Richtungen herausprojizieren | 0,234 | 0,927 | 0,530 | 0,126 | 0,229 | 0,239 | 0,192 |
| Ebenen-Mittel + PCA 256 | 0,253 | 0,919 | 0,541 | 0,167 | 0,274 | 0,321 | 0,214 |
| **Ebenen-Mittel + Kosinus 1024** | 0,258 | 0,924 | **0,554** | **0,177** | **0,288** | **0,336** | **0,203** |

Lesart:

- **Hebel 1 (Engpass)** hebt vor allem die **Themen**: OpenAlex-Thema 0,12 → 0,16–0,17,
  Begriffszusammenhalt 0,21 → 0,29. Mehr Dimensionen vor UMAP heißt: feinere
  Unterschiede überleben die Kompression. Die Treue zum Original steigt leicht mit.
- **Hebel 2 (Schreibstil)** hebt vor allem die **Ebenen-Mischung**: Ebenenabstand
  0,47 → 0,19–0,22, CPC-Reinheit 0,47 → 0,53. Die Themen innerhalb der Forschung
  gewinnen dadurch nichts (0,126) — dort war der Stil nicht das Problem.
- **Zusammen** addieren sie sich. Die Trustworthiness sinkt dabei von 0,937 auf
  0,92: das Bild wirft etwas mehr Fremde zusammen. Das ist der gewollte Effekt —
  Patent und Fachartikel zum selben Thema *sollen* Nachbarn werden, obwohl sie im
  Original weiter auseinander liegen.
- **Abstand zur Obergrenze bleibt groß.** Im 1024er-Raum teilen 64 % der Nachbarn eines
  Patents eine CPC-Klasse, in 3D bestenfalls 55 %; beim Begriffszusammenhalt 0,54 gegen
  0,34. Drei Achsen können nicht alles tragen. Für „was liegt neben diesem Signal"
  bleibt die Vektorsuche im Originalraum der richtige Weg, nicht die Position im Bild.
- **Der Stil-Befund verschwindet mit Hebel 2 aus dem Bild.** Die Kontinente „Forschung /
  Patente / Presse" sind heute selbst eine Aussage (docs/emerging_nests_2026-09-15.md).
  Nach dem Umbau zeigt die Färbung nach Ebene ein gemischtes Bild; wer die Trennung
  sehen will, bräuchte die alte Projektion als zweite Ansicht.

Begriffszusammenhalt je Begriff (Produktion → Ebenen-Mittel + Kosinus 1024), bei allen 28
besser: *wind turbine* 0,27 → 0,62, *perovskite* 0,29 → 0,56, *green hydrogen* 0,20 →
0,46, *3D printing* 0,10 → 0,44, *biodegradable packaging* 0,26 → 0,44, *microbiome*
0,14 → 0,31; kaum: *gene therapy* 0,19 → 0,20, *wearable* 0,12 → 0,14, *plant-based*
0,20 → 0,20, *solar panel* 0,20 → 0,22.

## Kosten im Produktionslauf

Gemessen: gelernt auf 18.000, eingesetzt 18.000 (nach JIT-Aufwärmen), einfädig wie die
Produktion (Seed).

| Variante | Lernen 18k | Einsetzen/s | 1,4 Mio. einsetzen | Lauf gesamt (heute ~10 min) |
|---|---|---|---|---|
| Produktion | 8,3 s | 6.251 | ~3,7 min | ~10 min |
| Ebenen-Mittel + PCA 256 | 8,6 s | 4.925 | ~4,8 min | ~11 min |
| Ebenen-Mittel + Kosinus 1024 | 11,1 s | 3.019 | ~7,7 min | ~14 min |

Speicher 2,3 GB Spitze in der Messung (36k), in der Produktion zuletzt 2,8 GB.

## Der Umbau (28.09. umgesetzt)

- `pipeline/signal_space.py`: Ebenen-Mittel aus der Stichprobe lernen und mit dem Lauf
  speichern; jede Zeile vor PCA/UMAP um das Mittel ihrer Ebene verschieben und neu
  normieren (die Ebene kennt `place_all` schon, `tier_of`). Nest-Zentroide mischen
  Ebenen — sie bekämen das nach Mitgliedern gewichtete Mittel abgezogen.
- UMAP `metric="cosine"` ohne PCA, oder PCA 256.
- Die Nest-**Zugehörigkeit** (Kosinus zum Zentroid ≥ Schwelle) bleibt im Originalraum,
  sie hängt nicht an der Projektion.
- Ein neuer Lauf per *Recompute cloud*; die Seite nennt die neuen Treuewerte von selbst.

## Wiederholen

```bash
.venv/bin/python scripts/space_eval/eval_projection.py                    # alle 7 Varianten, ~5 min
.venv/bin/python scripts/space_eval/eval_projection.py --seed 7 --out eval_projection_seed7.json
.venv/bin/python scripts/space_eval/eval_projection.py --variants baseline,pca256 --terms 5
```

Rohdaten `data/space_eval/eval_projection*.json` (nicht versioniert), enthalten auch den
Begriffszusammenhalt je Begriff.
