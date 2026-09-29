# Signalraum in 3D — Methode, Messungen, Grenzen (2026-09-27)

Owner-Frage: *„Welche Möglichkeiten gibt es, die Cluster in den Daten visuell im
Frontend in 3D und im Zeitverlauf sichtbar zu machen?"* — Antwort in Code:
`/trends/foresight/map`, zwei Ansichten auf einem Renderer.

Der Befund vorweg, weil er die ganze Bauweise bestimmt: **die Daten waren schon
da.** Jedes Nest aus `emerging_nests` trägt seinen 1024-dimensionalen Zentroid
und, aus dem Archiv-Scan, seine Treffer in jedem der 449 Monate. Es fehlten nur
Koordinaten und eine Uhr. Die Seite rechnet deshalb **nichts** nach: kein Cron,
kein Modell, keine GPU, keine neue Tabelle, keine Migration.

## Zwei Koordinatenquellen

| | Messachsen (Default) | Karte |
|---|---|---|
| Position | Alter × Anteil je 10.000 × Wachstum | 1024 → 3 per klassischem MDS |
| bewegt sich über die Zeit | **ja** — ein Monat ist ein Schritt auf der Bahn | nein, nur die Größe atmet |
| Achsen beschriftet | ja, mit Einheit und Ticks | **nein** — sie haben keine |
| Aussage | Messung | Orientierung |

Die Trennung ist der Kern. Eine bunte 3D-Wolke aus einer Projektion sieht nach
Präzision aus und ist keine; die Seite sagt das an der Stelle, an der es jemand
liest, und stellt daneben die Ansicht, deren Achsen tatsächlich etwas bedeuten.

## Was die Projektion kostet (gemessen)

Klassisches MDS über die Zentroide, also PCA — die Zentroide sind L2-normiert,
damit ist der euklidische Abstand eine monotone Funktion des Kosinus.

| Lauf | Nester | Shepard r | gehaltene Varianz | 5 nächste Nachbarn bleiben |
|---|---|---|---|---|
| `global` (43) | 83 | **0,474** | 24,4 % | 47 % |
| `tier:science` (52) | 94 | **0,731** | 29,4 % | 55 % |
| `tier:market` (55) | 55 | **0,635** | 26,8 % | 49 % |

Lesart auf der Seite: ab 0,8 sind Abstände grob ablesbar, ab 0,6 Nachbarschaften,
darunter nur die Gruppierung. Der globale Lauf liegt **darunter** — die Karte ist
dort ein Navigationsbild und sonst nichts.

Der TypeScript-Eigensolver (Potenziteration mit Gram-Schmidt-Deflation, fester
Startvektor, feste Vorzeichenkonvention) reproduziert `numpy.linalg.eigh` auf drei
Stellen: 0,474 / 24,4 % / 47 % in beiden Implementierungen. Er ist deterministisch,
weil das Bild zwischen zwei Renderings nicht spiegeln darf.

### Negativergebnis: lokale Nachoptimierung bringt es nicht

Naheliegend wäre, nach dem MDS lokal nachzuoptimieren (Sammon-Stress, Gewicht
1/d, 400 Schritte Gradientenabstieg vom MDS-Start). Gemessen:

| Lauf | Shepard r | Nachbarn bleiben |
|---|---|---|
| `global` | 0,474 → **0,727** | 0,472 → 0,554 |
| `tier:market` | 0,635 → **0,707** | 0,491 → **0,436** |

Der Abstandsfehler sinkt deutlich, die **Nachbarschaftstreue** — das, wofür eine
Karte benutzt wird — verbessert sich in einem Lauf und verschlechtert sich im
anderen. Ein Verfahren mit Lernrate, das die entscheidende Größe nicht verlässlich
verbessert, ist den Zuwachs an Beweglichkeit nicht wert. Bleibt bei MDS: ohne
Parameter, exakt reproduzierbar, und sein Fehler ist rein „drei Achsen können 1024
nicht halten".

## Normalisierung: der Korpus zum Laufzeitpunkt

Lautstärke ist ein **Anteil je 10.000 Signalen desselben Monats**, nie eine
Zählung — rohe Zahlen zeichnen unsere eigene Sammelrampe (von einigen hundert
Signalen je Monat auf über hunderttausend). Dieselbe Einheit wie in den
Field-Watch-Blättern, aus demselben Grund.

Entscheidend ist das **Wann** des Korpus. Gebunden an `trends.created_at <=
Laufzeitpunkt`:

| | Zeilen |
|---|---|
| heute, datiert, gleiche Filter | 1.812.312 |
| zum Laufzeitpunkt (16.09. 00:26) | 1.749.548 |
| vom Schnappschuss tatsächlich gescannt | 1.749.204 |

Rest 0,02 % — Zeilen, deren Publikationsdatum am Lauftag noch in der Zukunft lag
und die der Scan deshalb übersprang. Die Seite nennt den Rest, statt Exaktheit zu
suggerieren. Gegen den **heutigen** Korpus sähe jedes Nest aus wie am Verblassen:
die jüngsten Monate sind seit dem Schnappschuss um 63.000 Zeilen gewachsen, die
Nest-Treffer sind darin eingefroren.

## Bauweise

Keine 3D-Bibliothek. Bei 55–94 Punkten sind es eine Rotationsmatrix, eine
Perspektivdivision und ein Tiefensortieren; jede Spur ist **ein** `<path>` statt
zwölf Segmenten, macht rund 250 SVG-Knoten und bleibt beim Drehen flüssig — ohne
WebGL und ohne 150 KB three.js auf einer Seite, die es nicht braucht.

- Mathematik: `frontend/src/lib/clusterMap.ts` (rein, 20 Vitests)
- Renderer: `frontend/src/components/foresight/ClusterSpace.tsx`
- Seite: `frontend/src/app/trends/foresight/map/page.tsx`
- Daten: `getEmergingSpace` in `frontend/src/lib/emerging.ts`

Laufzeit: 3,2 s beim ersten Aufruf je Bereich (die Monatssumme des Korpus, danach
eine Stunde im TTL-Cache), 0,12 s warm. Nutzlast 232 KB für 83 Nester × 204 Monate.
Gezeigt werden 180 Monate, 24 weitere werden nur geladen, um die rollenden Fenster
zu füllen.

Drei Entscheidungen, die im Bild sichtbar sind:
- **Eine** Größenskala für den ganzen Durchlauf, nicht je Monat — sonst sähe jeder
  Monat gleich voll aus, und die Animation zeigte nichts.
- Spuren **brechen** in Monaten ohne Treffer, statt vom Achsenboden quer durch den
  Würfel zu laufen.
- Die Karte wird auf das 92-%-Quantil der Auslenkung gerahmt (ein Faktor für alle
  drei Achsen, die Form bleibt); ein einzelnes exzentrisches Nest drückte sonst
  alle anderen zu einem Punkt.

## Stufe 3 — die Signale selbst (gebaut am selben Tag)

Owner-Entscheid: **UMAP** statt t-SNE (neue Abhängigkeit `umap-learn` mit numba und
pynndescent). Gate vor dem Bau: `pip install --dry-run` durfte numpy 2.4.6, scipy
1.18.0 und sklearn 1.9.0 nicht anfassen — tat es nicht, nur Zusätze. Wichtig dabei:
die venv von `ct-dev` ist ein **Symlink auf die von `main`**, die Installation war also
sofort auch dort. Volle pytest-Suite danach grün.

**Stichprobe.** 600 je Monat aus den letzten 180 Monaten, deterministisch (kleinste
`(id·2654435761) mod 2³²` je Monat; der Schnitt ist eine Fensterfunktion in der DB, es
wandern nur die gewählten IDs). Alle 180 Monate erreichen die Quote: 108.000 Signale,
Stichprobe in 6,4 s. Gleiche Anzahl je Monat, weil eine proportionale Stichprobe die
Sammelrampe zeichnete — Helligkeit bedeutet damit Zusammensetzung, nie Menge.

**Projektion.** L2 → PCA 50 (hält 39,2 % der Varianz) → UMAP 3D (n_neighbors 30,
min_dist 0,1, Seed 42). Der Seed zwingt UMAP einfädig; das ist der Preis für dasselbe
Bild bei gleichen Daten (Test: zwei Läufe → byte-identischer Blob) und wird bewusst
gezahlt. Die 83 Nester des globalen Emerging-Laufs 43 werden per `transform` in
dieselbe Wolke gesetzt; jeder Punkt erhält sein Nest nach der Regel des Archiv-Scans
(Kosinus ≥ Schwelle des Nests).

| Erster Lauf (27.09.) | |
|---|---|
| Laufzeit | 110 s (davon UMAP 88 s) |
| Spitzen-RSS | 2,4 GB |
| Blob | 1,7 MB (16 B/Punkt) |
| PCA-50-Varianz | 39,2 % |
| Trustworthiness @10 | **0,938** |
| 10 nächste Nachbarn bleiben | **23,9 %** |
| Punkte in einem Nest | 2.373 (2,2 %) |

Lesart der beiden Gütezahlen, beide auf 3.000 gleichmäßig verteilten Punkten gegen die
1024-dim Vektoren: Die Wolke erfindet kaum falsche Nachbarschaften (Trustworthiness
0,94), verliert aber die genauen Nachbarn (24 %). Taugt für Regionen und Dichte, nicht
für „was liegt direkt neben diesem Signal".

**Befund im Bild.** Die Einbettung trennt nach Schreibstil: Fachpresse, Forschung,
Patente und Förderung bilden eigene Kontinente. Die Nester liegen fast alle an der
Nahtstelle Forschung/Markt. Das bestätigt von außen, was der Emerging-Rücktest am
15.09. fand (die Ebene lässt sich nicht nachträglich aus einem gemeinsamen Nest lösen).

**Bauweise.** Eine Zeile je Lauf in `signal_space_runs`, Punkte als ein gepackter
BYTEA (x/y/z u16 · Monat u16 · Ebene u8 · Vertikale u8 · Nest u16 · trend_id u32,
little-endian; die Code-Tabellen liegen mit im Lauf). Kein Tabellenzeilen-je-Punkt,
kein Index, kein Schreiben auf `trends`. Renderer WebGL2 von Hand
(`ClusterCloud.tsx`): ein Puffer, ein Shader, additive Mischung; der Vertex-Shader ist
der Zwilling von `projectPoint`/`pointState` in `lib/spaceCloud.ts`, gepickt wird auf
der CPU (~108.000 Projektionen je Mausbewegung, rund eine Millisekunde). Die Deckkraft
fällt mit der Zahl leuchtender Punkte — bei „alle Monate" sättigte die additive
Mischung sonst zu Weiß.

Zwei Funde beim Bau: `active` ist in GLSL ES 3.0 ein reserviertes Wort (der Fehler
erschien dank der Fehleranzeige als Meldung statt als leere Fläche); und die
Nest-Beschriftungen drängen sich an der Nahtstelle, deshalb werden nur die sechs
größten beschriftet, die einander nicht überdecken — die übrigen tragen den Namen
als Tooltip.

## Navigation und Suche (27.09., abends)

Owner-Wunsch: näher heran und weiter heraus zoomen. Die Grenzen allein (×0,4–×3) waren
nicht das Problem, sondern dass der Zoom um die Würfelmitte ging — bei ×10 sieht man nur
die Mitte, und es gab kein Verschieben. Jetzt:

- **Drehpunkt** `View.center`, im Shader und in `projectPoint` identisch zuerst
  abgezogen. `screenToWorld` ist die exakte Umkehrung der Projektion in der Ebene des
  Drehpunkts (Test über vier Blickwinkel, 6 Stellen). Darauf bauen `zoomAt` (Mausrad:
  der Punkt unter dem Cursor bleibt stehen) und `panBy` (Shift-/Rechts-Ziehen).
  Doppelklick setzt den Drehpunkt auf ein Signal oder eine Tasche.
- **Zoom ×0,15 bis ×50.** Obergrenze aus der Speicherung: 16 Bit über ±1,53 ergeben bei
  ×50 ein 0,55-px-Raster, ab ~×90 rasteten die Punkte sichtbar ein.
- **Nahschnitt:** Mit dem Drehpunkt am Rand geraten ferne Punkte hinter die Kamera; die
  Perspektivdivision würde sie gespiegelt zeichnen. Sie werden ausgeblendet und sind
  nicht anklickbar; die Punktgröße ist nach oben begrenzt.
- **Tooltip** nach 1 s für Signale (Titel, Quelle, Datum, einmal je Signal geholt) und
  Ringe (Name, Größe). Das Drehen pausiert, solange der Cursor über der Wolke ist.
- **Suche** = die Feed-Suche (`websearch_to_tsquery` auf `idx_trends_fts`), beschränkt
  auf die IDs des Laufs: `Solar Panel` 112, `"solar panel"` 94, `perovskite` 137,
  `AI` 3.399 Treffer, 0,12–0,57 s. Treffer werden groß gezeichnet, der Kontext
  schwächer; eine neue Suche öffnet das Fenster auf alle Monate (im 12-Monats-Fenster
  blieben von 112 Treffern 7 — zwischen 100.000 Schattenpunkten unsichtbar). Das Bild
  zu „Solar Panel" zeigt einen dichten Knoten in der Fachpresse und eine eigene kleine
  Patentgruppe daneben.

Ein Fehler beim Bau, im Browsertest gefunden: Mit dem 10-px-Klickband auf den
SVG-Ringen begann ein Zug, der auf einem Ring startete, keine Drehung — und in der Mitte
liegen die Ringe dicht. Ringe werden jetzt wie die Punkte auf der CPU getroffen
(`pickRing`), die SVG-Ebene nimmt gar keine Zeigerereignisse mehr an.

## Alle Signale eingeordnet, Suche über den ganzen Bestand (27.09., spät)

Die Wolkensuche fand nur, was in der Stichprobe lag: 5–8 % der Treffer („solar panel"
112 von 1.619 im Bestand). Seitdem ordnet der Lauf **jedes Signal des 15-Jahres-Fensters**
in die Wolke ein: die Stichprobe (600 je Monat) bestimmt die Form, alle übrigen werden
mit dem gelernten PCA + UMAP per `transform` eingesetzt, ein Stichprobenpunkt behält
seine gelernte Position (Test: identische Koordinaten in beiden Blobs).

| | |
|---|---|
| eingeordnet | 1.522.042 Signale, davon 1.414.042 per Transform |
| Tempo Transform | ~6.750 Punkte/s nach einmaligem JIT; mit Laden 484 s |
| Lauf gesamt | 597 s, Spitze 2,8 GB |
| Blob `all_points` | 24,4 MB, nach trend_id sortiert (Binärsuche im Server) |

Die Suche fragt drei Quellen parallel (Titel/Zusammenfassung/Tags, Forschungs- und
Patent-Abstracts; jede darf einzeln scheitern, die Seite meldet es) und liefert die
Treffer als gepackte Datensätze, die der Browser als zweite Punktschicht zeichnet:

| Suche | vorher (Stichprobe) | jetzt | vor dem Fenster | Dauer |
|---|---|---|---|---|
| solar panel | 112 | 2.288 | 217 | 0,6 s |
| "solar panel" | 94 | 1.742 | 178 | 0,2 s |
| perovskite | 137 | 2.946 | 76 | 0,2 s |
| battery | — | 19.214 | 734 | 1,1 s |
| AI | 3.399 | 88.698 | 957 | 0,4 s |

Bei 88.698 Treffern läuft die Animation weiter mit 61 Bildern/s. Deckkraft und
Punktgröße der Treffer fallen mit ihrer Zahl — sonst liefen Tausende zu Weiß zusammen
und die Ebenenfarbe ginge verloren. Abstract-Treffer bedeuten „kommt vor", nicht
„darum geht es" (Stichprobe: ein Offshore-Wind-Paper, dessen Abstract Solarmodule nennt).

## Grenzen

- Die Karte ist eine Projektion, kein Messwert — s. o.
- Ein dichtes, brandneues Nest kann ein einzelner Massen-Ingest sein. Das Panel
  nennt deshalb immer die größte Quelle mit Anteil, den Anteil klassifizierter
  Mitglieder und den Anteil etablierter Quellen; unter 50 % steht ausdrücklich da,
  dass das Alter eher etwas über unsere Abonnements aussagt als über die Welt.
- Die Signalwolke (Stufe 3) ist eine Stichprobe von 6 % des Korpus und eine
  Projektion — sie zeigt Dichte und Löcher, keine Messung. Seit 28.09. zeichnet der
  Schalter *All signals* stattdessen alle 1,52 Mio. eingeordneten Signale (Blob
  `all_points`, 24,4 MB, Laden 0,3 s lokal); dann ist Helligkeit Menge, nicht
  Zusammensetzung. Die Form bestimmt weiter die Stichprobe.
- Suche nach Bedeutung (28.09.): Schalter Text · Meaning · Both; *Meaning* holt die 250/500/1.000
  nächsten Signale per HNSW (pgvector 0.6: höchstens 1.000 je Anfrage). Gemessen: `Pflanzenkäse
  aus Cashew` 971 Treffer (Text 0, Ähnlichkeit 0,76–0,58), `solar panel` in *Both* 106 beides /
  2.186 nur Text / 825 nur Bedeutung (0,84–0,63), 0,3–1,3 s. Eine Rangfolge, keine Menge —
  die Treffer verblassen mit dem Rang.
- Ob eine andere Projektion Themen besser ordnet, misst `docs/space_eval_2026-09-28.md`
  (Ebenen-Mittel abziehen + Kosinus auf 1024 ist besser). Seit 28.09. ist das die
  Standard-Anordnung *Topic*; die hier beschriebene ist *Style* (Schalter *Layout*).
  Lauf 4: 108.000 + 1.523.285 Signale in beiden Anordnungen, 1.224 s, Spitze 4,0 GB,
  52 MB; Topic 25,1 % Nachbarn@10 / Trust 0,923, Style 23,9 % / 0,937.
- Owner-only wie das ganze Cockpit (`PUBLIC_MODE` 404, nie im Export). Genau
  deshalb darf sie interaktiv sein, wo die öffentlichen Seiten deterministisch
  sein müssen.
