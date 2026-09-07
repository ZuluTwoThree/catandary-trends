# B8 — Runde 8, Läufe vom 2026-09-07 (`glp1-r8`)

Zwei Läufe, beide vom selben Auftragstext, beide mit `scripts/lib/gpu_guard.sh`
davor und Ruhezustand danach (llama-server aktiv auf `start-qwen3-8b-208k.sh`,
21.986 MiB).

| | v1 (`dossiers.id=22`, 1.194 s) | **v2 (`dossiers.id=23`, 1.077 s) = ausgeliefert** |
|---|---|---|
| Code | R8 mit drei eigenen Fehlern | R8 nach `b1edd2d` |
| Fließtext (vor → nach Neuwurf) | 1.511 → **1.335** (geschrumpft) | 1.590 → **1.705** (gewachsen) |
| Kalenderzeilen mit Datum + Beleg | 2 | **6** |
| mechanisch gestrichene Sätze | 9 | **0** |
| Befunde nach dem Neuwurf | 11 Beleg + 5 Struktur | **0 Beleg + 1 Struktur** |

**Warum zwei Läufe.** v1 hat drei Fehler des eigenen Codes aufgedeckt und ist
an ihnen gescheitert (Fix + Tests in `b1edd2d`):

1. **Der Revisionsauftrag widersprach sich.** Er verlangte „689 Wörter belegte
   Fakten ergänzen" *und* „keine neuen Fakten, keine neuen Zitate" — und der
   Neuwurf-Prompt führte den Evidenzblock gar nicht mit. Das Modell konnte gar
   nicht ergänzen und hat gekürzt. Seit `b1edd2d` erkennt `needs_expansion`
   den Fall, der Auftrag verlangt dann ausdrücklich einen **längeren** Bericht
   aus dem mitgelieferten Material.
2. **Fehlalarme der Gegenstandsprüfung** (die Regel aus Runde 3, seit B6
   notiert): „Confirms", „Adds", „Expands Mounjaro's", „Missing" am Anfang
   einer Tabellenzelle wurden als Eigennamen gelesen. Drei der fünf
   Themenbefunde waren das — sie kosteten Option 1 ihr „Against it", Option 4
   ihr „Risk" und zwei Kalenderzeilen.
3. **Ein „|" im Quellentitel** („… 2025-2026 | Telehealth Ally") zerlegte die
   Kalenderzeile, in der es stand, als Tabellenzelle.

Ausgeliefertes Dokument: `B8_final.md` · Prüfanhang: `B8_annex.md`
(beides in `dossiers.report_md`, getrennt durch `<!-- catandary:audit-annex -->`).
Logs: `B8_run.log` (v2) und `B8_run_v1_buggy.log` im Session-Scratchpad.

## 1. Umfang

| | B7 | **B8 (v2)** | Gegner (jury_11) |
|---|---|---|---|
| ausgeliefert gesamt | 4.195 W. | **4.609 W.** | 2.833 W. |
| davon Fließtext | 1.621 | **1.705** | 1.997 |
| Prüfanhang (separat) | 2.725 | 2.872 | — |
| gelesene Domains | 46 | **48** | 48 |
| Quellen / zitiert | 194 / 25 | 187 / **34** | ~60 |

## 2. Lücke 1 — Abdeckung und zeitliche Einordnung (R8-1)

**Katalysator-Kalender.** Der Pflichtabschnitt „What happens next" steht mit
**6 datierten und belegten Zeilen** im Dokument (B7: kein solcher Abschnitt).
Inhalt: Mounjaro-CV-Indikation (Mid-2026), orales Foundayo (Late-2026),
CagriSema-Kombination (2026), Orforglipron-PDUFA (2026), CagriSema-Phase-3
(2026), **Novo Nordisk Capital Markets Day am 21. September 2026**. Die
Prüfung im Lauf zählte 5 von 6 (sie las „Mid-2026" mit Bindestrich nicht als
Datum — nachgezogen, mit Test); am ausgelieferten Dokument sind es 6.

**Abdeckung je Kette-Ebene.** Wissenschaft, Patente, Förderung und Markt
tragen je mindestens eine Aussage mit Datum **und** Zitat im selben Satz —
mechanisch geprüft, nicht erhofft. Anhänge zählen dabei nicht (genau der
jury_11-Vorwurf „Förderung nur über die eigene Tabelle").

**Untergrenze.** 2.200 Wörter sind wieder ein Neuwurf-Grund. Der Neuwurf hat
zum ersten Mal in die richtige Richtung gearbeitet (1.590 → 1.705), das Ziel
aber **nicht erreicht** — das ist der offene Punkt dieses Laufs (§6).

## 3. Lücke 2 — Quellenqualität bei Kernzahlen (R8-2)

- **Kernzahlen ohne Primärbeleg im ausgelieferten Dokument: 0.** Gegenprobe am
  Endstand (`weak_source_figures`): keine. Am gespeicherten **B7**-Dokument
  meldet dieselbe Regel **3** — darunter der von beiden Jurys benannte
  Lilly-Quartalsumsatz auf `tikr.com`.
- Im Lauf v1 traf die Regel genau diese Stelle: `['$19.8', '56%'] (tikr.com)`.
  In v2 hat der erste Wurf sie gar nicht erst gesetzt.
- Katalogränge v2: **23 Rang 0** (Behörde/Register/Gericht), **19 Rang 1**
  (Firmen-IR/Fachjournal), 63 Rang 2. Der Berichtsprompt weist Rang 0/1 im
  Katalog als `(primary)` aus.
- **Selbstauskunft-Regel** (`self_unverified`): 0 Seiten in diesem Lauf. Die
  von jury_11 zitierte Stelle auf `formblends.com` („not been able to verify …
  from a primary register") steht im heute abgerufenen Volltext nicht mehr —
  die Regel greift, der Auslöser ist auf dieser Seite verschwunden. Die Seite
  trägt in B8 keine Kernzahl in einem der drei Kernabschnitte.

## 4. Lücke 3 — Reichweite (R8-3)

- **Verstöße gegen die Verwendbarkeitsregel im ausgelieferten Dokument: 0**
  (einschließlich der neuen Reichweiten-Bedingung).
- Gegenprobe am gespeicherten **B7**-Dokument: **1 Verstoß**, und zwar genau
  der von jury_11 §4.5 zitierte Satz — „The measured median improvement rate
  of 3.3%/yr suggests that natural modulators may not offer a significant
  advantage over synthetic drugs", gemessen wurde `A61P5/48` /
  `C12N2501/335`.
- Die Quellen-Reichweite (`artefact_conflicts`) hat in v2 nicht ausgelöst: der
  Bericht beruft sich nirgends auf ein Register, das die zitierte Seite nicht
  führt. Die EFSA-Registeraussage aus B7 kommt nicht wieder vor.

## 5. Abgelehnte Sätze je Prüfregel (v2)

| Regel | vor dem Neuwurf | danach (= gestrichen) |
|---|---|---|
| Zahl steht nicht in der zitierten Seite | 1 | 0 |
| Seite handelt von etwas anderem (Gegenstand) | 1 | 0 |
| Präzisionszahl ohne Beleg im Satz | 0 | 0 |
| verdrehte Wiedergabe | 1 | 0 |
| falsche Zuordnung in der Quelle | 0 | 0 |
| gesperrte/nicht reichende Messgröße | 0 | 0 |
| **Kernzahl nur auf Rang 2 (neu)** | **0** | 0 |
| Summe | 3 | **0 → 0 Sätze gestrichen** |

Geprüft wurden **26 Sätze mit 76 Angaben und 45 benannten Gegenständen**
(B7: 18 / 52 / 26). Strukturbefunde: 2 vor, 1 nach dem Neuwurf (die Länge).
Abgewiesene Treffer des Rangfilters: 7 aus 4 Domains (`glp3.wiki`,
`retatrutide.med`, `openpr.com`, `beyondapprovalpharma.substack.com`) — beide
von jury_10 beanstandeten Quellen erneut abgewiesen.

## 6. Was offen bleibt

1. **Fließtext 1.705 Wörter** — 495 unter dem Zielband. Der Neuwurf wächst
   jetzt (v1: −176 Wörter, v2: +115), aber nicht bis 2.200. Ohne einen zweiten
   Neuwurf (bewusst ausgeschlossen: kein Loop) bleibt das eine Vorgabe, die
   der eine erlaubte Durchgang nicht ganz einholt.
2. **Optionen ohne Messbezug: 4 von 4** (B7: 2 von 4 trugen eine Messgröße).
   Seit R7-1 ist das zulässig — alle vier Optionen sind belegt —, und die
   Messung trägt in v2 den ersten Satz der Kurzfassung. Es ist trotzdem ein
   Rückgang gegenüber B7 und gehört beobachtet: jury_12 hat „tragend, nicht
   Dekoration" ausdrücklich gelobt.
3. **74 Seiten nicht lesbar** (Botsperre/Zeitüberschreitung) — unverändert die
   größte Materialbremse.
4. Die Rangregel gilt per Auftrag nur für die drei Kernabschnitte. Marktzahlen
   im Abschnitt „What is moving" dürfen weiter auf Rang-2-Presse ruhen.
