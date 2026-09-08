# Grounding-Bestandsprüfung 2026-09-05 (#11)

Erzeugt von `scripts/recheck_published_grounding.py`. Kontext und Bewertung: siehe Abschnitt am Ende / Issue #11.

## Lauf 2026-09-05 — status=published, DRY-RUN

- Checks: garbage names
- Gescannt: 89,388 Artikel in 54 s
- Treffer: 742 Artikel (0.83%) — garbled 46, name 696; davon nur too_short: 37

### Garbage-Gründe

| Grund | Artikel |
|---|---|
| too_short | 37 |
| glued_repetition | 6 |
| script_leak | 2 |
| low_diversity | 1 |

### Je Monat

| Monat | garbled | name |
|---|---|---|
| 2026-03 | 0 | 2 |
| 2026-04 | 2 | 56 |
| 2026-05 | 3 | 45 |
| 2026-06 | 8 | 177 |
| 2026-07 | 24 | 228 |
| 2026-08 | 6 | 169 |
| 2026-09 | 3 | 19 |

### Je Quelle (Top 40)

| Quelle | garbled | name |
|---|---|---|
| Lebensmittelzeitung | 3 | 90 |
| Horizont | 1 | 76 |
| Trends in Food Science & Technology | 0 | 44 |
| Handelsblatt Schlagzeilen | 1 | 37 |
| Trends in Biotechnology | 0 | 35 |
| Project Syndicate | 0 | 23 |
| Politico Europe | 0 | 19 |
| The Lancet | 0 | 17 |
| The Register | 1 | 14 |
| Tagesschau Wirtschaft | 2 | 13 |
| WirtschaftsWoche | 1 | 14 |
| heise online | 3 | 11 |
| Nature (main) | 0 | 12 |
| Food Policy | 0 | 12 |
| Ars Technica | 0 | 12 |
| NYT Business | 1 | 11 |
| TechCrunch | 0 | 11 |
| Axios | 3 | 8 |
| Renewable Energy World | 0 | 11 |
| Gründerszene | 0 | 9 |
| Science Magazine News | 0 | 9 |
| Hypebeast | 3 | 4 |
| STAT News | 0 | 7 |
| idw Pressemitteilungen | 0 | 7 |
| Fast Company | 2 | 4 |
| Wired | 1 | 5 |
| Robb Report | 0 | 6 |
| WWD | 0 | 6 |
| The Conversation | 1 | 5 |
| Guardian Business | 0 | 6 |
| Business of Fashion | 1 | 4 |
| Guardian Culture | 0 | 5 |
| Carbon Brief | 1 | 4 |
| Packaging Dive | 2 | 2 |
| Grist | 1 | 3 |
| Highsnobiety | 2 | 2 |
| t3n | 0 | 4 |
| Creative Bloq | 0 | 4 |
| The Verge | 0 | 4 |
| Fierce Biotech | 0 | 4 |

### Häufigste beanstandete Namen

- Donald Trump (67)
- Alois Rainer (7)
- Emmanuel Macron (7)
- Lars Klingbeil (6)
- Jeff Bezos (5)
- Sam Altman (5)
- Oliver Blume (5)
- Friedrich Merz (5)
- Xi Jinping (4)
- Jerome Powell (4)
- Ursula von der Leyen (4)
- Gianni Infantino (4)
- Ron DeSantis (3)
- Lionel Messi (3)
- Vladimir Putin (3)
- Alexander Dobrindt (3)
- Gavin Newsom (3)
- Volodymyr Zelenskyy (3)
- Christian Lindner (3)
- Gabriela Ramos (3)
- Clément Delangue (3)
- Pavel Durov (3)
- Joachim Rukwied (2)
- Pepper (2)
- Rafael Oliveira (2)

## Lauf 2026-09-05 — status=published, APPLY

- Checks: garbage names
- Gescannt: 89,402 Artikel in 52 s
- Treffer: 742 Artikel (0.83%) — garbled 46, name 696; davon nur too_short: 37
- Angewendet: 742 Zeilen → status='review', review_reason='recheck_2026-09-05:…'

### Garbage-Gründe

| Grund | Artikel |
|---|---|
| too_short | 37 |
| glued_repetition | 6 |
| script_leak | 2 |
| low_diversity | 1 |

### Je Monat

| Monat | garbled | name |
|---|---|---|
| 2026-03 | 0 | 2 |
| 2026-04 | 2 | 56 |
| 2026-05 | 3 | 45 |
| 2026-06 | 8 | 177 |
| 2026-07 | 24 | 228 |
| 2026-08 | 6 | 169 |
| 2026-09 | 3 | 19 |

### Je Quelle (Top 40)

| Quelle | garbled | name |
|---|---|---|
| Lebensmittelzeitung | 3 | 90 |
| Horizont | 1 | 76 |
| Trends in Food Science & Technology | 0 | 44 |
| Handelsblatt Schlagzeilen | 1 | 37 |
| Trends in Biotechnology | 0 | 35 |
| Project Syndicate | 0 | 23 |
| Politico Europe | 0 | 19 |
| The Lancet | 0 | 17 |
| The Register | 1 | 14 |
| Tagesschau Wirtschaft | 2 | 13 |
| WirtschaftsWoche | 1 | 14 |
| heise online | 3 | 11 |
| Nature (main) | 0 | 12 |
| Food Policy | 0 | 12 |
| Ars Technica | 0 | 12 |
| NYT Business | 1 | 11 |
| TechCrunch | 0 | 11 |
| Axios | 3 | 8 |
| Renewable Energy World | 0 | 11 |
| Gründerszene | 0 | 9 |
| Science Magazine News | 0 | 9 |
| Hypebeast | 3 | 4 |
| STAT News | 0 | 7 |
| idw Pressemitteilungen | 0 | 7 |
| Fast Company | 2 | 4 |
| Wired | 1 | 5 |
| Robb Report | 0 | 6 |
| WWD | 0 | 6 |
| The Conversation | 1 | 5 |
| Guardian Business | 0 | 6 |
| Business of Fashion | 1 | 4 |
| Guardian Culture | 0 | 5 |
| Carbon Brief | 1 | 4 |
| Packaging Dive | 2 | 2 |
| Grist | 1 | 3 |
| Highsnobiety | 2 | 2 |
| t3n | 0 | 4 |
| Creative Bloq | 0 | 4 |
| The Verge | 0 | 4 |
| Fierce Biotech | 0 | 4 |

### Häufigste beanstandete Namen

- Donald Trump (67)
- Alois Rainer (7)
- Emmanuel Macron (7)
- Lars Klingbeil (6)
- Jeff Bezos (5)
- Sam Altman (5)
- Oliver Blume (5)
- Friedrich Merz (5)
- Xi Jinping (4)
- Jerome Powell (4)
- Ursula von der Leyen (4)
- Gianni Infantino (4)
- Ron DeSantis (3)
- Lionel Messi (3)
- Vladimir Putin (3)
- Alexander Dobrindt (3)
- Gavin Newsom (3)
- Volodymyr Zelenskyy (3)
- Christian Lindner (3)
- Gabriela Ramos (3)
- Clément Delangue (3)
- Pavel Durov (3)
- Joachim Rukwied (2)
- Pepper (2)
- Rafael Oliveira (2)

## Lauf 2026-09-05 — status=draft, APPLY

- Checks: garbage 
- Gescannt: 7,352 Artikel in 1 s
- Treffer: 29 Artikel (0.39%) — garbled 29, name 0; davon nur too_short: 22
- Angewendet: 29 Zeilen → status='review', review_reason='recheck_2026-09-05:…'

### Garbage-Gründe

| Grund | Artikel |
|---|---|
| too_short | 25 |
| whitespace_run | 3 |
| glued_repetition | 2 |
| empty | 2 |
| non_latin_script | 1 |
| word_repetition | 1 |
| low_diversity | 1 |

### Je Monat

| Monat | garbled | name |
|---|---|---|
| 2026-07 | 13 | 0 |
| 2026-08 | 6 | 0 |
| 2026-09 | 10 | 0 |

### Je Quelle (Top 40)

| Quelle | garbled | name |
|---|---|---|
| SEC Form D (Startup Private Offerings) | 4 | 0 |
| The Conversation | 4 | 0 |
| Hypebeast | 2 | 0 |
| Lebensmittelzeitung | 2 | 0 |
| idw Pressemitteilungen | 2 | 0 |
| ScienceDaily Top | 2 | 0 |
| Tubefilter | 1 | 0 |
| ArchDaily | 1 | 0 |
| Creative Bloq | 1 | 0 |
| Music Business Worldwide | 1 | 0 |
| Ars Technica | 1 | 0 |
| Endpoints News | 1 | 0 |
| PocketGamer.biz | 1 | 0 |
| Canary Media | 1 | 0 |
| Trends in Food Science & Technology | 1 | 0 |
| Electrek | 1 | 0 |
| Deutsches Ärzteblatt | 1 | 0 |
| Food Safety News | 1 | 0 |
| New Scientist Technology | 1 | 0 |

## Lauf 2026-09-05 — status=review, APPLY

- Checks: garbage names
- Gescannt: 831 Artikel in 0 s
- Treffer: 825 Artikel (99.28%) — garbled 129, name 696; davon nur too_short: 59
- Angewendet: 825 Zeilen → status='review', review_reason='recheck_2026-09-05:…'

### Garbage-Gründe

| Grund | Artikel |
|---|---|
| too_short | 75 |
| script_leak | 41 |
| whitespace_run | 17 |
| non_latin_script | 16 |
| glued_repetition | 15 |
| word_repetition | 8 |
| low_diversity | 3 |
| empty | 2 |

### Je Monat

| Monat | garbled | name |
|---|---|---|
| 2026-03 | 0 | 2 |
| 2026-04 | 4 | 56 |
| 2026-05 | 8 | 45 |
| 2026-06 | 41 | 177 |
| 2026-07 | 37 | 228 |
| 2026-08 | 12 | 169 |
| 2026-09 | 27 | 19 |

### Je Quelle (Top 40)

| Quelle | garbled | name |
|---|---|---|
| Lebensmittelzeitung | 5 | 90 |
| Horizont | 1 | 76 |
| Trends in Food Science & Technology | 1 | 44 |
| Handelsblatt Schlagzeilen | 2 | 37 |
| Trends in Biotechnology | 0 | 35 |
| Project Syndicate | 1 | 23 |
| Politico Europe | 1 | 19 |
| The Lancet | 0 | 17 |
| The Register | 2 | 14 |
| Tagesschau Wirtschaft | 2 | 13 |
| WirtschaftsWoche | 1 | 14 |
| heise online | 3 | 11 |
| The Conversation | 9 | 5 |
| Nature (main) | 1 | 12 |
| Ars Technica | 1 | 12 |
| NYT Business | 2 | 11 |
| idw Pressemitteilungen | 6 | 7 |
| Food Policy | 0 | 12 |
| TechCrunch | 0 | 11 |
| Axios | 3 | 8 |
| Renewable Energy World | 0 | 11 |
| Hypebeast | 6 | 4 |
| ScienceDaily Top | 9 | 1 |
| Gründerszene | 0 | 9 |
| Science Magazine News | 0 | 9 |
| Guardian Business | 2 | 6 |
| STAT News | 0 | 7 |
| Fast Company | 2 | 4 |
| Business of Fashion | 2 | 4 |
| Wired | 1 | 5 |
| Highsnobiety | 4 | 2 |
| Robb Report | 0 | 6 |
| Guardian Culture | 1 | 5 |
| WWD | 0 | 6 |
| Golem | 2 | 4 |
| Creative Bloq | 1 | 4 |
| Phys.org | 1 | 4 |
| Electrek | 1 | 4 |
| Carbon Brief | 1 | 4 |
| SEC Form D (Startup Private Offerings) | 5 | 0 |

### Häufigste beanstandete Namen

- Donald Trump (67)
- Alois Rainer (7)
- Emmanuel Macron (7)
- Lars Klingbeil (6)
- Jeff Bezos (5)
- Sam Altman (5)
- Oliver Blume (5)
- Friedrich Merz (5)
- Xi Jinping (4)
- Jerome Powell (4)
- Ursula von der Leyen (4)
- Gianni Infantino (4)
- Ron DeSantis (3)
- Lionel Messi (3)
- Vladimir Putin (3)
- Alexander Dobrindt (3)
- Gavin Newsom (3)
- Volodymyr Zelenskyy (3)
- Christian Lindner (3)
- Gabriela Ramos (3)
- Clément Delangue (3)
- Pavel Durov (3)
- Joachim Rukwied (2)
- Pepper (2)
- Rafael Oliveira (2)

## Kontext und Bewertung (Engineer, 05.09.2026)

**Auslöser.** Owner-Review der gehaltenen Drafts (Issue #11, Kommentar vom
05.09.): (A) 14 Token-Suppen-Drafts aus dem Backlog-Lauf (12:17 Uhr) plus
43 published Artikel April–Juni mit eingestreuten CJK-Zeichen — alle 57 vom
Owner per SQL auf `status='review'` gesetzt; (B) erfundene Vornamen/Titel
(„Henkel CEO **Markus** Knobel" für „Henkel-Chef Knobel"), die das reine
Zahlen-Grounding nicht sieht. Owner hat die Bestandsprüfung über alle
published Artikel freigegeben (Treffer → `review`).

**Ursache A (Code, belegt).** `pipeline/llamacpp_client.py` gab nach
aufgebrauchtem Soft-Guard-Budget das letzte Ergebnis trotzdem zurück
(Docstring: „a flagged body beats None"; `return result  # validate budget
spent → accept the last result`). Stage 6 nutzte nur diesen Soft-Guard
(`max_validate_retries=3`, `MAX_RETRIES=3` → Log „retry 1/3, 2/3", dann
Annahme). `content_is_clean` verwarf die Suppe zwar (< 25 Wörter, kein
Satzende), aber Verwerfen hieß nur „neu würfeln", nie „nicht speichern".
Stage 7 fügte den Body dann mit der Relevanz-Confidence (0,93) als Draft ein.
Der Owner-Sweep fand 14 der Suppen; in Verarbeitungsreihenfolge waren es
**22 in Folge** (1718638–1718659, davon 8 vom Owner-SQL verpasst: 1718640,
641, 647, 648, 649, 651, 652, 659 — Bodies wie `testing(`, `:`, leer).
Alle 22 hatten Volltext-Quellen an der 4000-Zeichen-Prompt-Kappe (User-
Prompt 4,8–5,9k Zeichen ≈ 2k Tokens = `-ub 2048` des Gemma-Starts); 114
andere lange Prompts desselben Laufs und alle Teaser-Prompts waren sauber,
der 23. Eintrag danach wieder sauber. llama-server: `n_slots = 4`, unified
KV, Stage 6 sequenziell auf einem Slot „selected by LCP similarity" (Prompt-
Prefix-Wiederverwendung, f_keep 0,34–0,86), keine Fehler/Truncation im Log.
Der Content-Prompt speist **nicht** 12.000 Zeichen ein, sondern 4.000
(`CONTENT_CHARS`, jetzt `STAGE6_SOURCE_MAX_CHARS`); die 12.000 gelten für
die Extraktion. Verdacht: transienter Slot-/Cache-Zustand nach Prefix-Reuse,
nicht eine Eigenschaft der Prompts — offen bis zum GPU-Repro
(`scripts/repro_stage6_garbage.py`, drei Arme).

**Detektor.** `pipeline/content_guard.py`: (a) Nicht-Latein-Anteil > 0,5 %
(Griechisch ausgenommen), (b) Wort ≥ 4× in Folge / Buchstabengruppe ≥ 3×
geklebt (URLURLURL), (c) Unikat-Anteil < 35 % ab 40 Wörtern, (d) < 60 Wörter,
(e) Nicht-Wort-Zeichen > 25 %, (f) ≥ 6 Leerzeichen in Folge, (g) Script-Leak:
Nicht-Latein-Zeichen, die die Quelle nicht enthält. Kalibrierung: 22/22
Suppen (Body allein), 40/43 Alt-CJK (nur mit Quelle sichtbar — 2 Zeichen in
1.700 sind 0,1 %), 2.615 zufällige published Bodies → 2 Treffer, beide
`too_short` (13 bzw. 48 Wörter). Die 3 nicht erkannten Alt-Fälle sind
**legitim** (11779/26685 „Chopstick 箸", 12977 ByteDance „您" — das Zeichen
steht in der Quelle); sie bleiben ohne `review_reason` in `review` — Owner
kann sie zurück publizieren.

**Namen.** `grounding.ungrounded_names`: Vorname (2.367 Einträge,
`pipeline/first_names.py`; Alltagswörter/Orte/Marken wie Will, May, Morgan,
Paris, Mercedes, Eli, Abu ausgeschlossen) oder Titel davor (CEO, Minister,
Dr., Chef …) + Nachname; jedes Wort muss in Titel+Teaser+Volltext+Extraktion
stehen (Umlaut-Transliteration, Possessive, Partikel „von der", Satzgrenzen).
Institutionen/Marken/Instrumente mit Personennamen (Justus Liebig University,
James Webb Space Telescope, Eli Lilly) schlagen nicht an. Stichprobe 2.615:
31 Treffer (1,2 %), alle regelkonform — darunter ein echter Fehler („Simona
Reiche", real Katherina Reiche) und regelkonforme Ergänzungen („Bernard
Arnault" bei Quelle „Arnault").

**Ergebnis (Apply).** published 89.388 gescannt → **742 nach review** (0,83 %):
garbled 46 (37 nur `too_short`, 6 `glued_repetition`, 2 `script_leak`, 1
`low_diversity`), name 696 (632 verschiedene Namen; „Donald Trump" allein
67 = 10 % — regelkonform, aber sicher korrekt ergänzt; die ersten Kandidaten
für Publish aus der Queue). Je Monat (name): Apr 56 · Mai 45 · Jun 177 ·
Jul 228 · Aug 169 · Sep 19. Drafts: 29 garbled → review (inkl. der 8
verpassten Suppen). Bestehende review-Zeilen: 825 von 831 mit Grund gestempelt
(garbled 129, name 696), 6 ohne Grund (3 legitime CJK, 3 FoodNavigator-
Zeilen des Owners von Juli). `reviewed_at` wurde **nicht** gesetzt — in
`review.ts`/Handbuch heißt das „Mensch hat entschieden"; der Marker ist
`review_reason` (Tab *Re-check* auf `/trends/review`).

**Vorbehalt.** Geprüft wird gegen das, was die DB heute hält. Nach
`purge_raw_content.py` gelöschte Volltexte fehlen — ein Name, den das Modell
damals im Artikel las (Autorenlisten in „Trends in Biotechnology", „Food
Policy"), erscheint heute „ungrounded". Deshalb Hold, kein Urteil; Publish
aus der Queue ist die richtige Antwort auf solche Fälle.

## Nachtrag 2026-09-08 — Re-check-Queue komplett neu geschrieben

Owner-Entscheid: die 813 Zeilen in `review` (807 mit `recheck_2026-09-05`-
Grund, 6 ohne) nicht einzeln durchsehen, sondern alle neu schreiben lassen.
Ausgeführt 18:47 Uhr mit genau der Semantik des *Write again*-Knopfs
(`requeueForRegeneration`): alte Zeilen → `rejected` + `reviewed_at`
(`review_reason` bleibt als Audit-Spur), 813 `raw_entries` → unverarbeitet.
Vorher: 0 mit früherem Neuschreib-Versuch, 0 mit veröffentlichtem Geschwister-
Artikel, 787 waren einmal published.

Befund vorab, der die Erwartung dämpft:

| | Zeilen |
|---|---|
| `raw_content` bereits genullt (14-Tage-Purge) | 803 |
| davon Opt-in-Quelle → Volltext wird vor dem Lauf neu geholt | 340 (77 Quellen: Handelsblatt, Politico Europe, Tagesschau, WiWo, heise, Ars Technica, TechCrunch …) |
| davon Vorbehalts-/Sperr-Quelle → nur Titel + Teaser (Median 120 Zeichen) + gecachte Extraktion (463 Zeilen haben eine) | 463 (54 Quellen: Lebensmittelzeitung 95, Horizont 77, Trends in Food Science 45, Trends in Biotechnology 35, Project Syndicate 24, The Lancet 17 …) |
| Quelldatum älter als 30 Tage → Neufassung liegt außerhalb des öffentlichen Fensters, nur Korpus | 617 |

Zwei Pipeline-Fehler dabei gefunden und im selben Zug behoben (Tests
`tests/test_run_full_cycle_order.py`, `tests/test_deduplication.py`):

1. `run_full_cycle` holte den Volltext erst **nach** Phase 1 (Backlog) —
   jeder *Write again*-Eintrag lief textlos in die Content-Generierung.
   Jetzt läuft `fetch_batch` unmittelbar vor jedem LLM-Lauf.
2. `get_recent_titles` (Stage-1-Titel-Dedup) enthielt die per Hand
   verworfenen Vorgänger; 142 der 813 lagen im 30-Tage-Fenster und hätten
   ihre eigene Neufassung als `title_duplicate` töten können. Jetzt gleiche
   Ausnahme wie in `get_recent_embeddings`.

Lauf: `scripts/scheduled_cycle.sh 1500` in tmux-Session `rewrite` aus dem
main-Worktree, Log `~/logs/catandary-scheduled-20260908-19*.log`
(erster Start 18:50 vor dem Fix abgebrochen, nichts verändert). Ergebnis
(created/filtered/held) steht in der Morgen-Mail vom 09.09. bzw. im Log.
Die 813 alten Zeilen sind per `status='rejected' AND reviewed_at::date =
'2026-09-08' AND review_reason LIKE 'recheck_%'` auffindbar.

**Lauf 19:11 — dritter Fehler.** Stage 6 meldete „564 cache hits": der
Crash-Resume-Cache `raw_entries.content_en_json` hielt noch den verworfenen
Text, der Cycle fügte ihn wortgleich wieder ein und Stage 7 scheiterte 564-mal
an `trends_slug_key` (Slug = Titel + Roheintrag-ID = der Slug des
zurückgezogenen Vorgängers); die Einträge wurden trotzdem als `processed`
markiert. 16 Einträge ohne Cache wurden echt neu geschrieben, 244 vom
Relevanz-Gate verworfen (208 Distill, 32 8B-Band, 3 Titel-Dubletten, 1
Extraktionsfehler). Korrektur 19:14: Cache für alle 813 gelöscht, 548
verlorene Einträge wieder geöffnet (553 offen), der laufende Cycle nimmt sie
in Phase 3 mit. Fixes: `requeueForRegeneration` löscht den Cache mit,
`llm_processor.unique_slug` hängt bei Kollision `-r2` an.
