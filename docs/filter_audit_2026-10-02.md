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

## Stufe 3 — unabhängiges Urteil an 305 Einträgen (02.10.)

Geschichtete Stichprobe (Hash-Auswahl, letzte 120 Tage), gemischt und **blind** beurteilt —
beim Lesen war weder Kopf-Wert noch „behalten/verworfen" sichtbar, nur die Ebene. Kriterien
VOR dem Lesen festgelegt: *Signal* = konkrete Entwicklung, die als Trend-Beleg taugt (Technik,
Produkt, Verfahren, Forschungsergebnis in einem der acht Vertikal-Felder, Förderung eines
benannten F&E-Vorhabens, Markt-/Regulierungsschritt; bei Patenten jede beschriebene technische
Erfindung). *Kein Signal* = Werbung, Rabatte, Klage-Aufrufe, Podcasts/Listen,
Verwaltungs-Platzhalter, Pflanzensorten, Errata, historische Texte, Lokales/Persönliches. Dazu
*unklar*. Urteilende Instanz: Claude, eine Person — Grenzfälle sind subjektiv, die Kategorien
nicht. Stichprobe und Urteile: `data/filter_audit_stage3_{sample,labels}.json`.

| Schicht | n | Signal | kein | unklar | Signal-Anteil (ohne unklar) | 95 %-Bereich |
|---|---|---|---|---|---|---|
| Patente verworfen, Kopf 0,0–0,1 | 25 | 23 | 2 | 0 | 92 % | 75–98 % |
| Patente verworfen, Kopf 0,1–0,3 | 25 | 24 | 1 | 0 | 96 % | 80–99 % |
| Patente verworfen, Kopf 0,3–0,5 | 25 | 23 | 2 | 0 | 92 % | 75–98 % |
| Patente behalten | 25 | 25 | 0 | 0 | 100 % | 87–100 % |
| Förderung verworfen, Kopf 0,0–0,3 | 20 | 8 | 11 | 1 | 42 % | 23–64 % |
| Förderung verworfen, Kopf 0,3–0,5 | 20 | 13 | 2 | 5 | 87 % | 62–96 % |
| Förderung behalten | 20 | 20 | 0 | 0 | 100 % | 84–100 % |
| Forschung verworfen, Kopf 0,0–0,3 | 20 | 5 | 13 | 2 | 28 % | 12–51 % |
| Forschung verworfen, Kopf 0,3–0,5 | 30 | 8 | 5 | 17 | 62 % | 36–82 % |
| Forschung verworfen, 8B | 15 | 5 | 5 | 5 | 50 % | 24–76 % |
| Forschung behalten | 20 | 16 | 2 | 2 | 89 % | 67–97 % |
| Presse verworfen, Kopf 0,2–0,3 | 20 | 10 | 7 | 3 | 59 % | 36–78 % |
| Presse verworfen, 8B | 20 | 4 | 9 | 7 | 31 % | 13–58 % |
| Presse behalten | 20 | 10 | 5 | 5 | 67 % | 42–85 % |

**Befund:**
- **Patente:** 92–96 % der verworfenen Patente sind nach dem Kriterium Signale, in jedem
  Kopf-Band. Die einzigen „kein Signal" sind **Pflanzensorten** (Luzerne, Tomate, Soja,
  Leucanthemum) — per Titel/CPC A01H erkennbar. Der Kopf trägt bei Patenten nichts bei.
  Vorbehalt: das Kriterium zählt jede technische Erfindung; viele verworfene Patente sind
  kleinteilig (Rezepturen, Haushaltsgeräte), aber dieselbe Art steht auch im Behaltenen.
- **Förderung:** Was der Kopf verwirft, ist zur Hälfte bis zu 87 % Signal; was zu Recht fällt,
  ist per Regel erkennbar: SEC-Form-D-Meldungen von Immobilien-/Holding-/Dienstleistungs-/Bau-/
  Restaurant-Vehikeln, NIH-„subproject"-Buchungszeilen, SAMHSA-Zeilen ohne Abstract, absurde
  Beträge („$6").
- **Forschung:** der Kopf trennt (verworfen 0,0–0,3: 28 % Signal gegen behalten 89 %); im Band
  0,3–0,5 sind 17 von 30 unklar (alte OpenAlex-Werke ohne Abstract, generische HRM-Studien).
- **Presse:** das 8B-verworfene ist überwiegend kein Signal (31 %); das Kopf-Band 0,2–0,3 (59 %)
  unterscheidet sich in dieser kleinen Stichprobe nicht sicher vom Behaltenen (67 %) — die
  Bereiche überlappen, n = 20 reicht für eine Aussage nicht.

**Empfehlung:** Patente: Relevanz-Kopf im Signal-Pfad abschalten, nur Pflanzensorten per Regel
aussortieren, die verworfenen Patente (mit Vektor) als Signale nachholen. Förderung: Kopf durch
Regeln ersetzen (Form-D-Branchen, Buchungszeilen, fehlender Abstract, Mindestbetrag), Verworfenes
nach diesen Regeln neu prüfen. Forschung und Presse: Kopf behalten; Presse-Band 0,2–0,3 bei
Gelegenheit mit größerer Stichprobe nachmessen.


## Umsetzung (02.10.)

- `pipeline/signal_rules.py` entscheidet im Signal-Pfad für Patente und Förderung; Presse und
  Forschung bleiben beim Head. Tests `tests/test_signal_rules.py`, `tests/test_signal_batch_rules.py`.
- Regel-Feinschliff am Probelauf: ein Förder-Eintrag ohne Abstract bleibt, wenn sein Titel ein
  Projekttitel ist (OpenAIRE/NSF: „Rank-based Decomposable Losses for Machine Learning"); er
  fällt, wenn der Titel nur eine Zuschlagsmeldung ist („X wins $50k SBIR Phase I award", N/A).
- `scripts/recover_rule_signals.py` holt Verworfenes mit gespeichertem Vektor nach
  (Probelauf 194 s): **Patente 51.813 zurück**, 2.229 Duplikate, 2.805 Pflanzensorten;
  **Förderung 3.945 zurück**, 554 Duplikate, 4.058 ohne Beschreibung, 141 Form-D-Vehikel/
  -Branchen/-Beträge. Ohne gespeicherten Vektor (v. a. der Förder-Nachlauf vom Juli, ~132.000
  Zeilen) bräuchte es den GPU-Einbetter — nicht Teil dieses Schritts.
