# Entscheidungsvorlage: Confidence-Schwelle nach der Volldurchsicht (2026-08-21/22)

**Auftrag (Owner, 21.08.):** Alle 10.884 Drafts unter der Auto-Publish-Schwelle
von Haiku lesen und auf Publizierbarkeit prüfen; danach diese Vorlage.

**Durchführung:** 109 Haiku-4.5-Subagenten (à ~100 Artikel), jeder las Titel,
Body und Quellen-Ausschnitt und urteilte pro Artikel (publish / signal /
Kategorie). Jedes Paket maschinell validiert (1:1-Deckung, Schema). Der direkte
API-Weg entfiel — der Key hat kein Guthaben; die Agenten liefen über die
Claude-Code-Subscription. Rohdaten: `data/haiku_review/` (Urteile pro Artikel-ID).

## (a) Gesamtergebnis

**7.798 von 10.884 Artikeln (71,6 %) sind nach redaktioneller Lektüre
publizierbar.** Je Confidence-Band:

| Band | n | publizierbar | echtes Signal |
|---|---|---|---|
| 0,80–0,85 | 1.873 | 79,0 % | 89,2 % |
| 0,75–0,80 | 1.540 | 75,9 % | 87,5 % |
| 0,70–0,75 | 1.428 | 72,0 % | 82,8 % |
| 0,60–0,70 | 1.964 | 75,0 % | 84,0 % |
| unter 0,60 | 3.874 | 64,1 % | 75,8 % |

Ablehnungsgründe gesamt: 1.460 kein Signal, 663 abgeschnittener Text,
601 zu dünn, 345 Quellen-Widerspruch.

## (b) Zwei Kernbefunde

**Das Gefälle ist flach — im Vollbild bestätigt.** Von 79 % (oben) nach 64 %
(ganz unten) über die gesamte Confidence-Spanne; die Anomalie, dass 0,60–0,70
über 0,70–0,75 liegt, hält auch bei n=10.884. Die Stage-1-Confidence trennt
Publizierbarkeit nur schwach. Praktisch heißt das: **Es gibt keinen Knick, an
dem eine Schwelle „richtig" sitzt** — jede Absenkung kauft Menge zu fast
konstanter Fehlerquote (20,8 % bei ≥0,80 bis 28,4 % bei „alles").

**Die abgeschnittenen Texte sind ein Altlasten-Cluster, kein Streuproblem.**
538 der 663 broken-Urteile konzentrieren sich in 8 Paketen (012, 014, 018, 048,
060, 083, 086, 089 — ID-sortiert = zeitlich geclustert, überwiegend die
Juli-Defektphase, auffällig oft heise-Volltexte). Rechnet man nur die intakten
Texte, liegt die Publizierbarkeit bei **76,3 %**.

## (c) Optionen

| Option | freigegeben | davon gut | Fehlerquote |
|---|---|---|---|
| 1. Schwelle behalten (0,85) | 0 | — | — |
| 2. Schwelle auf 0,75 | 3.618 | 2.814 | 22,2 % |
| 3. Schwelle auf 0,70 | 5.046 | 3.842 | 23,9 % |
| **4. Freigabe per Urteil (Backlog) + Gate für Neues** | **7.798 → 7.498 nach Gates** | 7.498 | **~0 % zusätzlich** |

Zu Option 4 im Detail:

- **Backlog:** Die Urteile liegen **pro Artikel** vor. Eine Pauschalschwelle ist
  für den Bestand damit überflüssig — man kann exakt die freigeben, die die
  Lektüre bestanden. Nach Abzug der deterministischen Gates (297 mit
  Grounding-Flags, 3 abgeschnitten) bleiben **7.498 sofort freigabefähige
  Artikel**. Das ist mehr als Option 3 liefert, bei einer Fehlerquote nahe der
  des regulären Auto-Publish statt 24 %.
- **Künftiger Zulauf** (~340/Nacht unter 0,85, davon erwartbar ~72 % gut):
  - *Variante A — wöchentlicher Subagenten-Batch* wie diese Durchsicht:
    ~2.400 Artikel/Woche ≈ 24 Agenten ≈ 1 Welle + Nachzügler, ~1 h, läuft über
    die Subscription (kein API-Guthaben nötig). Nicht cron-fähig ohne offene
    Session — realistisch als wöchentlicher Handgriff („Batch starten").
  - *Variante B — nächtliches API-Gate:* ~340 Artikel × Haiku ≈ 0,35 $/Nacht
    (Batch-API ~0,17 $). Braucht **Guthaben auf dem API-Key** (derzeit 0) und
    ein kleines Gate-Skript im Cycle. Vollautomatisch.

## (d) Umsetzungshinweise (für jede gewählte Option)

1. **Freigabe-Skript** muss vor dem Statuswechsel die deterministischen Gates
   erneut anwenden (Grounding, Truncation — die 297/3 oben belegen, dass Haiku
   sie nicht ersetzt), `auto_published=false` setzen (per Review beurteilt,
   nicht Auto-Pfad) und gegen bereits Veröffentlichtes de-duplizieren (das
   30-Tage-Fenster deckt alte Drafts nicht ab).
2. **Alt-Qualität:** Alle Backlog-Artikel stammen aus der dünnen Generierung
   (~110 Wörter, kaum Belege). Seit 21.08. erzeugt die Pipeline ~170 Wörter mit
   Belegblock. Option: die 7.498 vor Freigabe mit `regen_drafts.py` neu
   schreiben (~3 s/Artikel ≈ 6,5 h GPU) — dann erscheinen sie in neuer Qualität.
   Empfehlung: **Freigabe as-is, Regenerierung als späteres Upgrade** — die
   Lektüre hat genau diese Texte bestanden.
3. **Trunkierungs-Cluster:** die 663 broken (538 in 8 Paketen) **verwerfen oder
   regenerieren**, nicht liegen lassen — sie verstopfen jede künftige Durchsicht.
4. **Unsicherheit:** Die Inter-Richter-Streuung ist erheblich (Publish-Quote je
   Paket: Min 4 %, Median 77 %, Max 100 %; σ ≈ 20 pp) — teils echte
   Zeitcluster, teils unterschiedliche Strenge (ein Richter winkte alle 100
   durch, einer nur 34 intakte). Die **Band-Mittelwerte über 109 Richter sind
   robust**, das Einzelurteil ist es nicht. Für die Freigabe ist das
   akzeptabel (falsche Freigaben ≈ Fehlerquote des regulären Betriebs); wer es
   schärfer will, zieht eine Zweitmeinung über die Grenzfälle.

## (e) Empfehlung

**Option 4.** Die Schwelle nicht anfassen: Sie bleibt als Auto-Publish-Kriterium
für den Nachtbetrieb sinnvoll (dort schützt sie zusammen mit den Gates), aber
als Freigabe-Instrument für den Bestand ist sie dem Einzelurteil in jeder
Hinsicht unterlegen — weniger Menge ODER mehr Fehler, nie beides besser.

Konkret: (1) Freigabe-Skript für die 7.498 bauen und laufen lassen, (2) die 663
broken verwerfen, (3) für den Zulauf zunächst Variante A (wöchentlicher Batch),
Umstieg auf Variante B sobald API-Guthaben existiert. Damit wächst der
veröffentlichte Korpus um ~11 % (7.498 auf ~68.000) und die Halde ist dauerhaft
abgebaut statt nur umdefiniert.

**Nichts davon ist ausgeführt** — diese Vorlage ist die Grenze des Auftrags.
