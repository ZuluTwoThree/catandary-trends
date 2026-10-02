# Relevanz-Schranken im Embedding geprüft — Stufen 1 und 2 (02.10.2026)

Owner 02.10.: „Können wir anhand der Embeddings nachprüfen, ob die deterministische
Aussortierung robust ist, oder ob uns gute Signale verloren gehen?" Skript
`scripts/eval_filter/filter_audit.py` (nur lesend, CPU, 159 s), Rohdaten `data/filter_audit.json`.

## Bestand

`raw_entries`: 22,7 Mio. Zeilen; 19,6 Mio. unverarbeitet (fast alles der BDDS-Patent-Rückstand,
bewusst außen vor), **2,02 Mio. behalten, 1,08 Mio. aussortiert** (35 % der verarbeiteten).
Nichts davon ist gelöscht — `filtered_out` + `filter_reason`, Vektor in `embedding_blob`, wo er
vorlag.

| Ebene | Relevanz-Kopf | Relevanz 8B | Duplikat | sonst |
|---|---|---|---|---|
| Presse | 320.757 | 123.294 | 20.054 | 68.057 (u. a. „noise" 65.964) |
| Forschung | 91.804 | 40.308 | 68.509 | 78 |
| Patente | 39.613 | 17.527 | 21.293 | — |
| Förderung/API | 137.368 | 3.471 | 130.285 | 1 |

Mit Vektor (prüfbar): 283.000 relevanz-verworfene Einträge. Ohne Vektor sind vor allem die
290.000 Presse-Einträge eines Nachlaufs vom Juli 2026; seit August hat jeder verworfene Eintrag
seinen Vektor.

Zwei Schranken: Nachtlauf (Presse) Kopf < 0,3 verwerfen, 0,3–0,7 das 8B, ≥ 0,7 behalten;
Signal-Pfad (`signal_batch`, Forschung/Patente/Förderung) Kopf < 0,5 verwerfen, ohne zweite
Meinung — was dort fällt, kommt nie in den Signalraum.

## Stufe 1a — Nähe zum Behaltenen (Kosinus zum nächsten behaltenen Signal derselben Ebene, Median)

| Kopf-Wert | Forschung | Patente | Förderung | Presse |
|---|---|---|---|---|
| 0,0–0,1 | 0,58 | 0,73 | 0,81 | 0,59 |
| 0,2–0,3 | 0,66 | 0,73 | 0,84 | 0,66 |
| 0,4–0,5 | 0,71 | 0,76 | 0,86 | 0,67 |
| 8B verworfen | 0,73 | 0,73 | 0,73 | 0,66 |
| **behalten (Kontrolle)** | **0,75** | **0,75** | **0,80** | **0,72** |

Presse und Forschung: Verworfenes liegt deutlich weiter weg, je niedriger der Kopf-Wert, desto
weiter — die Schranke trennt. **Patente:** schon bei Kopf-Wert 0,0–0,1 liegt das Verworfene so
nah am Behaltenen wie Behaltenes untereinander, bei 0,4–0,7 näher (≥ 0,85: 14–18 % gegen 8 %) —
die Schranke schneidet durch die Themen. **Förderung:** Verworfenes liegt näher als Behaltenes
untereinander — gleichförmige Förder-Meldungen („X wins $Y SBIR Phase I award"), die der Kopf
nach Rauschen aufteilt.

## Stufe 1b — Was weggeworfen wird (Nester im Verworfenen, je Ebene 30.000)

„Waise" = dichte Tasche im Verworfenen, in der weniger als ein behaltenes Signal je zwei
verworfene liegt — ein Thema, das die Schranke praktisch ganz entfernt.

- **Presse** (7 Taschen, 2 % des Verworfenen): Ticket-Werbung, Podcasts, Sammelklagen-Aufrufe,
  Schnäppchen, Wochenrückblicke. Zu Recht weg.
- **Forschung** (28): historische Quellentexte, MPEC-Bahnmeldungen, Fallberichte, Erwiderungen,
  Publikationslisten. Zu Recht weg.
- **Patente** (68, davon 22 Waisen): Pflanzensorten (Soja, Phalaenopsis), Sharps-Behälter — zu
  Recht; aber auch Mobilfunk-Verfahren (1.047), Bild-/Videoverarbeitung (590), Medizingeräte
  (403), Wirkstoff-Derivate (224), Sekundärbatterien (145, Kopf-Wert ~0,39) — Technik, die eine
  Foresight-Schicht braucht.
- **Förderung** (21, 6 Waisen): Platzhalter „HOST", Studentschaften — zu Recht; SBIR/STTR-Zuschläge
  mit Kopf-Wert 0,2–0,3 — dieselbe Meldungsart wie die behaltenen.

## Stufe 2 — Verlorene Frühsignale (Treffer in den aktuellen Nestern aller Scopes)

| Ebene | Verworfen in einem Nest | Behalten in einem Nest | Verworfen in jungem Nest | Behalten in jungem Nest | ≈ verworfene in jungen Nestern |
|---|---|---|---|---|---|
| Forschung | 6,5 % | 22,8 % | 0,72 % | 2,07 % | ~430 |
| Patente | **11,7 %** | **11,2 %** | 3,27 % | 4,12 % | **~1.860** |
| Förderung | 2,7 % | 5,0 % | 0,17 % | 0,17 % | ~14 |
| Presse | 0,5 % | 2,0 % | 0,05 % | 0,32 % | ~80 |

## Befund

- **Presse: robust.** Der Kopf wirft Werbung, Podcasts und Rauschen weg; Verworfenes liegt fern
  und fast nie in Nestern.
- **Forschung: überwiegend robust**, Grauzone 0,3–0,5 (~7.000 Arbeiten) liegt näher am Behaltenen.
- **Patente: nicht robust.** Der Kopf wurde auf 8B-Urteilen über Presseartikel trainiert („taugt
  das als Trend-Artikel?") und misst bei Patenten Nachrichtenwert, nicht Technikgehalt. Verworfene
  Patente liegen so oft in Nestern wie behaltene; ~1.860 lägen in jungen Nestern.
- **Förderung: die Schranke teilt gleichförmige Meldungen zufällig auf**; der eigentliche Müll
  (Platzhalter, Studentschaften) wäre per Regel erkennbar.

Nächster Schritt (Stufe 3, offen): geschichtete Stichprobe unabhängig beurteilen — Patente je
Band, Förderung, Forschung 0,3–0,5 — und daraus Schwellen bzw. Regeln je Ebene ableiten.
