# B7 — Runde 7, Lauf vom 2026-09-07 (`glp1-r7`)

Zwei Läufe, beide vom selben Auftragstext, beide mit `scripts/lib/gpu_guard.sh`
davor und Ruhezustand danach (llama-server aktiv auf `start-qwen3-8b-208k.sh`,
21.986 MiB).

| | v1 (`dossiers.id=20`, 1.739 s) | **v2 (`dossiers.id=21`, 1.256 s) = ausgeliefert** |
|---|---|---|
| Code | R7 mit Nadel-Fehler | R7 nach `0786ab0` |
| Fließtext | 2.776 | **1.623** |
| eigene Messzahl im Text | **keine** | 3,3 %/yr + Zykluszeit 12,0 J. |

**Warum zwei Läufe.** v1 hat einen eigenen Fehler aufgedeckt und ist daran
gescheitert: der gesperrte K(t)-Jahreswert **3,0** trägt die Ganzzahlform „3"
als Nadel, und die traf mitten in „**3.3** % per year". Fünf Sätze, die den
kanonischen Median korrekt mit n und Zeitraum führten, wurden deshalb
mechanisch gestrichen — das Dossier kam ohne eine einzige eigene Messzahl
heraus. Fix + Regressionstest in `0786ab0` (`_entry` filtert Nadeln unter
`MIN_NEEDLE_CHARS`, `_needle_hit` schaut nach rechts auch auf ein
Dezimaltrennzeichen). v2 ist der Lauf auf korrigiertem Code; v1 bleibt als
`B7_run_v1_buggy.log` liegen.

Ausgeliefertes Dokument: `B7_final.md` · Prüfanhang: `B7_annex.md`
(beides in `dossiers.report_md`, getrennt durch `<!-- catandary:audit-annex -->`).

## 1. Umfang

| | B6 | B7 (v2) | Gegner (jury_9) |
|---|---|---|---|
| ausgeliefert gesamt | 5.477 W. | **4.195 W.** | 2.833 W. |
| davon Fließtext | 2.901 | **1.623** | 1.999 |
| Prüfanhang (separat) | 2.551 | 2.725 | — |
| gelesene Domains | 43 | **46** | 48 |
| Quellen / zitiert | 192 / 32 | 194 / 25 | — |

Die Obergrenze von 2.800 Wörtern hält zum ersten Mal (B6: 2.901). Sie hält
allerdings mit Abstand nach unten: 1.623 liegt **unter** dem Zielband
2.200–2.800, und das ist der offene Punkt dieses Laufs (s. §6). Der
Längenbefund nennt seit R7 den Betrag („mindestens N Wörter streichen"); in v2
gab es gar keinen Längenbefund mehr.

## 2. Optionen: Messbezug nur, wo er trägt (R7-1)

| | B6 | B7 (v2) |
|---|---|---|
| Optionen | 4 | 4 |
| davon mit gemessener Größe | 3 | **2** |
| davon ohne Messgröße **und** ohne Beleg | 0 | **0** |
| Pflichtfelder vollständig | 3 von 4 | **4 von 4** |
| Felder der Frage unbedient | health technology | **keins** |

- **Option 1 (Companion Nutrition)** und **Option 4 (Natural GLP-1 Modulators)**
  tragen die gemessene Verbesserungsrate 3,3 %/yr — in Option 4 als
  *Gegenargument* („legt nahe, dass natürliche Modulatoren kurzfristig keinen
  Vorteil bieten").
- **Option 2 (Digital Health)** und **Option 3 (US/UK-Markteintritt)** haben
  **keine** Messgröße, und das ist seit R7 zulässig: beide begründen sich aus
  datierten Belegen (orale GLP-1-Zulassungen; EFSA-Claim-Lage gegen US/UK).
  Der Nennungszwang aus Runde 6 hätte hier eine Zahl erzwungen, die nichts
  trägt — genau der Vorwurf aus jury_9.

Die Kurzfassung führt beide verwendbaren Größen (3,3 %/yr, 12,0 Jahre) und
stellt sie dem Marktbild gegenüber; der Abschnitt „What the evidence does not
support" löst diese Spannung ausdrücklich auf, statt sie stehen zu lassen.

## 3. Selbstwidersprüche und gesperrte Größen

**Verstöße gegen die Verwendbarkeitsregel im ausgelieferten Dokument: 0.**
Gegenprobe am Endstand (`measure_use_findings` über `B7_final.md`): keine.
Im Lauf selbst gab es 0 Verstöße schon vor dem Neuwurf.

Gesperrt und im Text nirgends verwendet: alle 21 Jahreswerte der K(t)-Kurve
(Kalibrierungsvorbehalt bis ~2019, 2026er Fenster unvollständig — darunter die
**6,1 %/yr**, die in B6 in der Kurzfassung standen) und alle vier Take-off-Jahre
(1990/2002/2005/1990 — der Anhang führt sie als „not reportable as a lead
time"). Verwendbar und im Anhang mit n, Zeitraum und Rechenweg belegt:
Median 3,3 %/yr (n=1.878, 2005–2026), Zykluszeit 12,0 J. (7.667 Kanten, ab
2015), Zentralitäts-Peak 2017 (n=115), Patentzahl, Korpuszählungen.

## 4. Abgewiesene Quellen nach Rang (R7-2)

9 Treffer aus 4 Domains kamen nicht in den Katalog:

| Kategorie | Domain | Verwürfe |
|---|---|---|
| Wiki ohne Redaktion | `glp3.wiki` | 3 |
| Ein-Wirkstoff-Domain | `retatrutide.med` | 4 |
| Presse-Wiederveröffentlicher | `openpr.com` | 1 |
| Selbstpublikation | `beyondapprovalpharma.substack.com` | 1 |

**Beide von jury_10 beanstandeten Quellen wurden erneut angeboten und diesmal
abgewiesen.** In B6 trugen genau sie die zentralen Phase-3-Daten. Die
Retatrutide-Zahl steht in B7 stattdessen auf einem Korpus-Artikel und einer
Fachseite. Der Verwurf steht mit Host und Kategorie im Prüfanhang und als Zahl
im ausgelieferten Prüfnachweis.

## 5. Abgelehnte Sätze je Prüfregel

| Regel | vor dem Neuwurf | danach (= gestrichen) |
|---|---|---|
| Zahl steht nicht in der zitierten Seite | 2 | 0 |
| Seite handelt von etwas anderem (Gegenstand) | 3 | 2 |
| Präzisionszahl ohne Beleg im Satz | 0 | 0 |
| verdrehte Wiedergabe | 0 | 0 |
| **falsche Zuordnung in der Quelle (neu)** | **0** | 0 |
| **gesperrte Messgröße (neu)** | **0** | 0 |
| Summe | 5 | 2 → **2 Sätze gestrichen** |

Geprüft wurden 18 Sätze mit 52 Angaben und 26 benannten Gegenständen. Die
Prüfbreite deckt seit R7 auch die Quellen der zweiten Welle ab (`entity` fehlte
in `_VERIFIABLE_KINDS`) — am gespeicherten **B6**-Dokument steigt sie dadurch
von 33 auf 36 Sätze und von 104 auf 121 Angaben, und die Zuordnungsprüfung
meldet dort genau den Jury-Fund (75 % Schmerzreduktion, auf der Seite bei
TRIUMPH-4 statt bei TRANSCEND-T2D-2).

Beide Streichungen in B7 sind **Fehlalarme derselben Regel wie in B6**: die
Gegenstandsprüfung liest „Regarding" und „Other" am Satzanfang als Eigennamen.
Das ist die Regel aus Runde 3 und weiterhin der nächste Kandidat.

## 6. Was offen bleibt

1. **Fließtext 1.623 Wörter** — 577 unter dem Zielband. Die Längenbremse hält
   jetzt nach oben, aber der Lauf ist unter das Ziel gerutscht; der kurze Text
   deckt weniger Wirkstoffe und Akteure ab als der Gegner. Kein Neuwurf, weil
   „zu kurz" per Vorgabe ein Hinweis ist und kein Neuwurf-Grund (ein Neuwurf
   lädt zum Auffüllen ein).
2. **29 offene Fragen** nach dem Audit (B6: 27) — im Prüfanhang belegt, wo
   gesucht wurde.
3. **2 Fehlalarme der Gegenstandsprüfung** kosteten je einen Satz (s. §5).
4. **3 gestrichene Zitate** (das Modell zitierte URLs außerhalb des Katalogs).
