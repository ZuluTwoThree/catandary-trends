# Plan: Der Dossier-Agent als nutzen- und lernbasierter Auftragnehmer

> **Intern.** Messungen an einzelnen Läufen; nichts davon ins Frontend. Grundlage:
> 48 Dossiers vom 26.08. bis 18.09.2026 (Tabelle `dossiers` + `dossier_orders`),
> die Chronik `docs/agentic_dossiers.md` (Runden 1–21) und Issue #107.

Owner-Auftrag 2026-09-18: die zehn Hebel aus Runde 21 so umsetzen, dass ein
**nutzenbasierter** (jede Aktion nach erwartetem Beitrag zur Dossierqualität je
Kosten) und **lernender** (Erfahrung aus früheren Läufen fließt in die nächsten)
Agent das Dossier erstellt — domänenübergreifend, ohne dass der Besteller das
Thema kennt.

## 1. Was die 48 Entwürfe zeigen

| Messung (Läufe seit 12.09., n = 19) | Wert |
|---|---|
| Vom Owner abgenommen (alle 48) | 3 (perovskite v1/v2, LFP v9) |
| Leser: „beantwortet die Frage" (Leser seit 14.09., n = 8) | 0 von 8 |
| Leser-Befunde nach Art | **missing 39**, off_topic 12, coherence 1 |
| Strukturbefunde nach dem Neuwurf | Dichte 13, Optionen 12 (Altpfad), Kalender 12, Akteurtabelle 12, Länge 8, Kette 7 |
| Faktenquote nach dem Neuwurf ≥ 2,0 | 8 von 19 — alle acht im DR-Modus |
| Dichte fällt durch den Neuwurf (nachher < vorher) | 9 von 19 (datacenter v2 1,18 → 0,80, v3 1,24 → 0,57) |
| Primäranteil der zitierten Quellen | 22–70 %, Median ~40 % |
| Laufzeit | 25–49 min (27B), 84–95 min (Flash-Next) |

Drei Lesarten, die den Plan tragen:

1. **Der dominante Fehler ist Fehlen, nicht Falschheit.** 39 von 52 Leser-Befunden
   sagen „das steht nicht drin": keine Empfehlung, keine Kostenstruktur, kein
   Grund für „why it matters", nur vier von acht Teilfeldern. Die Prüfkette ist
   auf Streichen gebaut (Zahl nicht auf der Seite → weg) und sichert damit die
   Richtigkeit des Verbleibenden, aber sie erzeugt Lücken: in 9 von 19 Läufen
   ist die Faktenquote nach dem Neuwurf niedriger als davor.
2. **Nur eine Maßnahme hat je verlässlich gewirkt: der DR-Vorlauf** (Primärseiten
   zuerst, Faktenzettel). Alle acht Läufe über der Dichte-Untergrenze sind
   DR-Läufe. Alles andere (Best-of-2, zweiter Neuwurf, stärkerer Schreiber)
   verschiebt einzelne Kennzahlen und lässt das Leser-Urteil unverändert.
3. **Die Fragen, die abgenommen wurden, waren Evidenzfragen** (Perowskit, LFP:
   „was bewegt sich, was ist belegt"). Die Fragen, die scheitern, verlangen ein
   Urteil („which stack", „which sub-fields move fastest"). Das Artefakt
   Scouting-Dossier ist seit Runde 19 bewusst urteilsfrei — der Widerspruch
   liegt im Auftrag, nicht im Text.

## 2. Zielbild: Nutzenfunktion und Lernschleife

**Nutzen U eines Dossiers** — messbar, aus den vorhandenen Prüfern, gewichtet
nach dem Auftrag:

```
U = w1·answered(must_answer)        # Anteil der Pflichtpunkte des Auftrags, die belegt beantwortet sind
  + w2·density_norm                 # Faktenquote, normiert auf 2,0
  + w3·primary_share                # Anteil Rang ≤ 1 unter den zitierten Quellen
  + w4·(1 − contradiction)          # Kurzfassung ↔ Rest widerspruchsfrei
  + w5·on_topic(calendar, actors)   # Themenbezug der Tabellen
  + w6·reader_answers               # Leser-Urteil „beantwortet"
  − c·(minutes/60) − c2·web_calls   # Kosten
```

Die Gewichte kommen aus dem Auftrag (Fragetyp), nicht aus dem Code: eine
Landschaftsfrage gewichtet Teilfeld-Abdeckung, eine Regulatorikfrage den
Primäranteil. Jede Entscheidung des Agenten — welche Lücke zuerst, welche Seite
lesen, wann aufhören, welcher Schreiber, ob ein zweiter Neuwurf — wird als
**erwarteter Nutzenzuwachs je Kosten** getroffen (Value of Information), nicht
nach festen Schrittzahlen (heute: 6 Korpus-Schritte, 14 Web-Schritte, 5 Zeilen,
zwei Neuwürfe, fertig).

**Lernen** heißt hier nicht Modelltraining, sondern eine **Erfahrungsbasis**, die
der Agent zur Planungszeit liest und nach jedem Lauf fortschreibt:

| Tabelle | Inhalt | Quelle | Verwendung |
|---|---|---|---|
| `dossier_run_outcomes` | U und alle Komponenten je Lauf, Leser-Urteil, Owner-Abnahme, Owner-Änderungsdiff | jeder Lauf, Desk-Sign-off, Desk-Editor | Kalibrierung der Gewichte, Scoreboard, Regression |
| `dossier_source_priors` | je (Feld, Host): wie oft gelesen, zitiert, gestrichen, Rang bestätigt | Faktenzettel + Streichprotokoll | Rangbonus je Feld, Reihenfolge des Primärquellen-Vorlaufs |
| `dossier_query_stats` | je (Lückenart, Anfrage-Schablone): Treffer, zugelassen, gelesen, zitiert | Web-Agent, Sweeps | Bandit über Schablonen (Thompson-Sampling), Dedup |
| `dossier_field_profiles` | je Feld: Profil, bestätigte Regulatoren/Instrumente, Quellklassen, Owner-Korrekturen | Profilschritt + Checkpoint | Wiederverwendung beim nächsten Auftrag im selben Feld |

Der Owner-Sign-off und vor allem der **Diff zwischen geliefertem und
freigegebenem Text** sind das teuerste Signal — sie werden ab Stufe 1 erfasst,
auch wenn Stufe 5 sie erst auswertet. Modell-Feintuning (DPO auf Entwurf →
freigegebene Fassung) ist erst ab ~100 freigegebenen Dossiers sinnvoll und
steht hier nur als Ausblick.

## 3. Stufen

### Stufe 0 — Messlatte zuerst (1 Tag)

`scripts/dossier_eval.py`: rechnet U und alle Komponenten für jeden vorhandenen
Lauf aus `dossiers.result` (Struktur, Leser, Zitate, Quellen liegen dort schon)
und schreibt `dossier_run_outcomes` (additive Migration). Scoreboard je Serie,
Regressionstest gegen die 48 Läufe (`tests/test_dossier_eval.py`: U ist
deterministisch, die drei abgenommenen Dossiers liegen im oberen Drittel).
Desk: dritte Ampel **„abgabereif"** (Leser beantwortet ∧ kein Widerspruch ∧
Dichte ≥ Floor ∧ Tabellen themenbezogen) neben Endkontrolle und Leser.
*Abnahme:* Baseline-Zahlen im Bericht; kein Lauf ohne Outcome-Zeile.

**Stand Stufe 0 (2026-09-19, gebaut — Runde 22 in `docs/agentic_dossiers.md`):**
`pipeline/dossier_utility.py` (Komponenten, U, Presets je Fragetyp, Ampel,
`record_run`), `scripts/migrate_dossier_run_outcomes.py` (auf der Live-DB
ausgeführt), `scripts/dossier_eval.py --backfill|--scoreboard [--json]`, Worker-
Hook am Laufende (nie sperrend), dritte Ampel „delivery-ready" im Desk,
`tests/test_dossier_utility.py`. Baseline über 48 Läufe: **0 abgabereif**,
7 mit Leser / 0 „beantwortet", mean U 0,476; LFP v9 Platz 4 von 48 (oberes
Drittel), perovskite v1/v2 Platz 40/41 — **nicht messbar** (kein Struktur-
protokoll, keine Ränge vor dem 07.09.), also nur für LFP als Regression belegt.
`answered_must` ist als Komponente vorgesehen (Gewicht 0,25, herausnormiert,
solange None) und wartet auf die Pflichtpunkte aus Stufe 1. Der Regressionstest
gegen die 48 Läufe ist ein Scoreboard-Ausdruck, kein Assert: die drei
abgenommenen Läufe sind mit heutigem Protokollstand nicht vergleichbar.

### Stufe 1 — Auftrags-Intake und Owner-Checkpoint (2 Tage)

`pipeline/dossier_brief.py`: aus Thema + Fragefeld ein **strukturierter
Auftrag** (27B, strukturiert, plus deterministische Prüfung): Fragetyp
(Technikwahl / Landschaft / Regulatorik / Markt / Evidenz), die Entscheidung,
der Leser, Randbedingungen, **Pflichtpunkte** (`must_answer`, 3–6 Sätze, die das
Dossier belegt beantworten muss), Artefakt-Weiche (Dossier / Dossier + Advisor),
Zeit- und Kostenbudget. Ein Fragefeld ohne Frage wird zurückgewiesen, nicht
interpretiert (v1-Fehler). Die Pflichtpunkte werden zu w1 der Nutzenfunktion, zur
Checkliste des Lesers und zur Gliederung des Abschnitts „Decision summary".

**Checkpoint:** nach Profil + Plan (~2 min) Status `awaiting_confirmation`; der
Desk zeigt Auftrag, Feldprofil, Plan, Quellklassen und einen Freitext
„Korrektur in einem Satz". Bestätigung oder Korrektur fließt in
`dossier_field_profiles`. Ohne Antwort läuft der Auftrag nach
`DOSSIER_CHECKPOINT_MIN` (Default 0 = warten; Cron-Pfade wie der
Newsletter-Deep-Dive setzen 0 = nicht warten) weiter.
*Abnahme:* datacenter v1 wird am Intake abgewiesen; ein Test-Auftrag „which stack"
wird als Dossier + Advisor geroutet.

**Stand Stufe 1 (2026-09-19, gebaut — Runde 24 in `docs/agentic_dossiers.md`):**
`pipeline/dossier_brief.py` (Brief-Schema, deterministischer Fragecheck,
Advisor-Weiche, `build_brief`, `must_answer_scores` mit Zitat-Prüfung),
`scripts/migrate_dossier_brief.py` (auf der Live-DB ausgeführt: `brief_json /
plan_json / profile_json / confirmed_at / owner_note`, Status
`awaiting_confirmation`), Worker-Phase 0 (Fragecheck → Intake → Halt;
`--confirm N [--note …]`), `run(brief=, profile=, plan=)` (Profil und Plan
werden hereingereicht, nur der Auftrag ist ein zusätzlicher Aufruf), MUST-
ANSWER-Block + Kurzfassungs-Gliederung + Leser-Checkliste, `answered_must`
belegt und Preset nach Fragetyp, Desk-Panel mit Bestätigen/Korrigieren und
Fragecheck im Formular. **Beide Abnahmepunkte per Test belegt** (v1-Text
abgewiesen, „which stack should" → Dossier + Advisor). **Abweichungen vom
Plan:** kein `DOSSIER_CHECKPOINT_MIN` — der Halt ist ohne Frist, Cron-Pfade
(Deep-Dive) schalten den Checkpoint ab; `dossier_field_profiles` (Stufe 5)
nicht angelegt, die Korrektur steht als `owner_note` am Zettel; das Zeit-/
Kostenbudget im Auftrag fehlt noch. Erster Live-Lauf mit Intake offen.

### Stufe 2 — Beschaffung aus dem Profil, Primärquellen je Feld (2 Tage)

Feste Sweep-Muster (`REGULATORY_PATTERNS` …) nur noch ohne Profil. Das Profil
nennt je Feld **Quellklassen** („who publishes the authoritative facts": Register,
Hersteller-Doku, Normen, CVE-Datenbank, Aufsicht, Börsenpflicht); Instrumente
werden vor dem Sweep gegen den Korpus gezählt (wie Landschafts-Teilfelder,
< 5 Signale fällt). Hosts, die das Profil nennt oder die in
`dossier_source_priors` für das Feld als zitiert-und-nie-gestrichen stehen,
bekommen Rang 1 — verifiziert durch Abruf. Primärquellen-Vorlauf liest in der
Reihenfolge des erwarteten Nutzens (Prior × Pflichtpunkt-Bezug), nicht in
Trefferreihenfolge.
*Abnahme:* Primäranteil der zitierten Quellen ≥ 60 % auf der datacenter-Serie
(heute 29–41 %); keine AI-Act-/Abwärme-Zeile in einem Virtualisierungs-Dossier.

**Stand Stufe 2 (2026-09-19, gebaut — Runde 25 in `docs/agentic_dossiers.md`):**
`TopicProfile.source_classes` (Register/Aufsicht/Gericht/Norm/Hersteller-Doku/
CVE-Datenbank/Statistik/Börsenpflicht/Journal/Presse, mit Hosts) — die Hosts
sind je Lauf Rang 1 (`set_run_primary_hosts`); generische Doku-/Normen-Hosts
(`is_doc_host`: learn.microsoft.com, knowledge.broadcom.com, pve.proxmox.com,
docs.*, *.readthedocs.io, iso/etsi/cve …) Rang 1; `profile_queries` baut
Recht/Markt/Förderung/Kalender nur aus Kern + Profil (Regulatoren,
Ereignistypen, Akteurtypen), Rückgrat der Vertikale und feste Listen nur noch
je Feld als Rückfall (< 2 brauchbare Regulatoren / < 2 echte Ereignisse /
kein Profil; `fallback`-Schlüssel); Instrumente werden vor dem Sweep gegen den
Korpus gezählt und danach geordnet, **nicht gestrichen** (Abweichung vom Plan:
kein „< 5 Signale fällt" — der Korpus ist presselastig), 0-Korpus-und-0-Web-
Instrumente stehen im Ledger/den Notizen; `dossier_source_priors`
(`pipeline/dossier_priors.py`, Migration auf der Live-DB ausgeführt, Backfill
über 49 Läufe: 12 Felder, 916 Hosts, 84 Rang-1-Kandidaten) — Rang 1 bei
n_cited ≥ 2, n_dropped = 0 **und n_read ≥ 1** (Zusatz gegenüber dem Plan:
sonst wäre Fachpresse als Original unserer Korpus-Artikel „Erfahrung");
Entitätshygiene (`sweep_entities`: Stopliste, ≥ 2 Katalogeinträge oder
Profil-Saat, typisiert, gedeckelt); Primärquellen-Vorlauf nach Rang ×
Prior × Pflichtpunkt-Bezug; `structure["calendar_off_profile"]` als Vermerk.
**Abnahme:** die AI-Act-/SPC-/Erstattungs-Anfragen sind per Test aus einem
Virtualisierungs-Profil verschwunden; der Primäranteil ≥ 60 % braucht den
nächsten Live-Lauf der datacenter-Serie (offen). `dossier_query_stats` und
`dossier_field_profiles` bleiben für Stufe 3/5.

### Stufe 3 — Der nutzenbasierte Rechercheur (2 Tage)

Ersetzt feste Schrittzahlen im Korpus- und Web-Agenten durch einen
**VOI-Planer**: jede offene Lücke trägt Gewicht (Pflichtpunkt > Audit-Lücke >
Planschritt), Deckung (0–1) und Erfolgswahrscheinlichkeit (aus
`dossier_query_stats` je Lückenart/Schablone und `dossier_source_priors`); die
nächste Aktion ist die mit dem höchsten `weight·(1−coverage)·p_success / cost`.
Abbruch, wenn der beste erwartete Zuwachs unter die Kostenschwelle fällt oder das
Budget aus dem Auftrag erreicht ist. Fast-Dubletten (Cosinus ≥ 0,9 über den
CPU-Embedder) werden verworfen; Budget je Lücke statt global. Schreiberwahl
nach Budget: 27B (≈ 30 min) oder Flash-Next (≈ 85 min, +0,6 Dichte im Vergleich
v3/v4) — der Auftrag entscheidet, nicht die Env.
*Abnahme:* gleiche Dichte bei ≤ 70 % der Web-Aufrufe auf der LFP-Serie; keine
zwei Anfragen mit Cosinus ≥ 0,9 in einem Lauf.

**Stand Stufe 3 (2026-09-19, gebaut — Runde 26 in `docs/agentic_dossiers.md`):**
`pipeline/dossier_planner.py` (Lücken mit Gewicht 3/2/1/0,7, Deckung sättigend
bei 3, `p_success` aus `dossier_query_stats` + Prior-Bonus, Kosten 1/2/0,5,
Argmax, Stopp bei Zuwachs < `DOSSIER_VOI_MIN_GAIN` = 0,15 oder Budget aus,
Budget je Lücke 3, Trace in `result["voi"]`), verdrahtet in Korpus- UND
Web-Agent (das Modell formuliert, der Planer wählt Lücke und Ende; „finish"
nur mit Zustimmung); Pflichtpunkte sind Lücken ersten Ranges; Fast-Dubletten
(Cosinus ≥ 0,9 über den CPU-Embedder, sonst Jaccard ≥ 0,8) in beiden
Schleifen und im Coverage-Sweep; `dossier_query_stats` (Migration auf der
Live-DB ausgeführt, Backfill 549 Anfragen → 542 Schablonen, nur 6 ≥ 2×);
dazu die drei Lehren des Handdurchgangs: Rechtstexte artikelweise
(`pipeline/legal_text.py`, `fetch_fulltext_result(max_chars=)`), zwei Seiten
je Hersteller-Aussage (`marketing_only_claims` + Doku-Suche vor der
Streichung), Leser-Urteil an den Pflichtpunkten (`answered_items`/
`unanswered_items`, Empfehlung ausdrücklich nicht erwartet). **Abweichungen:**
keine Schreiberwahl nach Budget (Auftrag trägt noch kein Budget;
`DOSSIER_WRITER_MODEL` bleibt Env); feste Sweeps ohne Planer. Offline: 4 von
367 Web-Suchen der alten Läufe wären Dubletten gewesen; die Abnahme (≤ 70 %
Web-Aufrufe bei gleicher Dichte) braucht den nächsten LFP-/datacenter-Lauf.

### Stufe 4 — Prüfen statt Streichen (2 Tage)

1. **Aussagenprüfung** für Kernsektionen: Satz + zitierte Seite → `supported /
   contradicted / unrelated` (27B, strukturiert, T = 0); Token-Abgleich bleibt
   Vorfilter. `contradicted` ist ein sperrender Befund (v3: „Data Act does not
   apply"). Subjektabgleich stamm- und wortweise, nicht als Phrase (v4: „BSI
   Baustein").
2. **Reparieren vor Streichen, mit Nutzen-Abwägung:** ein Satz mit
   Pflichtpunkt-Bezug wird zweimal repariert (Seite neu lesen, Zahl ersetzen)
   bevor er fällt; ein Füllsatz fällt sofort. Ziel: Dichte nach dem Neuwurf
   ≥ Dichte davor (heute in 9 von 19 Läufen verletzt).
3. **Widerspruchs-Gate:** Leser-Befund `coherence`/„contradiction" zwischen
   Kurzfassung und einer anderen Sektion → gezielter Neuwurf NUR dieser zwei
   Sektionen mit dem Befund als Direktive; Ganzdokument-Neuwurf entfällt.
4. **Quoten aus dem Material:** Akteurtabelle und Beobachtungspunkte wie der
   Kalender aus dem Faktenzettel bemessen (`max(2, min(5, belegte Kandidaten))`),
   Lücke ausdrücklich benannt statt gefüllt.
*Abnahme:* datacenter v3 (Data-Act-Satz) und v4 (Widerspruch) werden im Replay
gefangen; Dichte nach Neuwurf ≥ vorher in ≥ 90 % der Läufe.

**Stand Stufe 4 (2026-09-19, gebaut — Runde 23 in `docs/agentic_dossiers.md`):**
`pipeline/dossier_entailment.py` (Aussagenprüfung je zitierter Seite, ein
strukturierter Aufruf je Seite, Urteile je (Satz, Seite) gecacht, ≤ 25 Seiten
je Durchgang, `DOSSIER_ENTAILMENT=0` schaltet ab), Subjektabgleich per Stamm
(`_in_source_phrase`: lange Wörter stammweise, kurze Qualifizierer wie „BSI"
nicht verlangt), zweiter Reparaturdurchgang nur für Kern-/Themen-Sätze
(`repair_sentences(pass_no=2, only=…)`, Seite breiter neu gelesen),
Widerspruchs-Gate (`contradiction_findings` mechanisch: Urteil der Kurzfassung
gegen verneintes Urteil in „does not support"/„Decision points";
`contradiction_from_reader` für `coherence`/„contradict") mit gezieltem
Neuwurf NUR der beiden Sektionen (`rewrite_sections`, `replace_section`),
danach sperrend; Quoten aus dem Material (`actor_min_from_material`,
`watch_min_from_material`, Befund nennt das Soll und verlangt die Lücke in
„Open questions"); Kalendertermine vor dem Laufdatum zählen als `passed`;
PDF-Titel aus Dateiname statt erster Textzeile; `scripts/dossier_replay.py`.
Replay über 48 Läufe: v3-Satz ist ein Modellurteil (im Replay nicht
ausführbar, Unit-Test mit Fake-Modell), **v4 wird mechanisch gefangen**
(dazu datacenter v2 und quantum v2 — 3 Läufe, 4 Paare; vor der
Urteils-Bedingung 7 Läufe, 14 Paare, 11 davon Einschränkungen), 22 Kalender-
zeilen in 13 Läufen mit am Laufdatum vergangenem Termin (datacenter v3: 4), 25 von 135 gespeicherten
Subjekt-Befunden würde der Stammabgleich jetzt akzeptieren, von 243
gestrichenen Sätzen standen **169 in einer Kernsektion oder nannten das
Thema** (bekämen jetzt zwei Reparaturen), 74 waren Füllsätze. Die
Dichte-Abnahme (≥ 90 %) braucht Live-Läufe — offen bis zum nächsten
datacenter-/LFP-Vergleichslauf.

### Stufe 5 — Die Lernschleife (1–2 Tage)

Nach jedem Lauf: `dossier_run_outcomes` (Stufe 0) + Fortschreibung von
`dossier_source_priors` (aus Faktenzettel, Zitaten, Streichungen) und
`dossier_query_stats` (aus Sweeps und Web-Agent). Desk: „Edited version"
speichern → Diff zur gelieferten Fassung als Owner-Signal; Sign-off ohne Edit =
positives Label. `scripts/dossier_replay.py`: spielt die Prüf- und Planungslogik
auf gespeicherten Läufen nach (ohne Modell), damit jede Regeländerung gegen 48+
Läufe gemessen wird, bevor sie live geht. Wöchentlicher Block auf
`/trends/dossiers`: „Was der Agent gelernt hat" (neue Rang-1-Hosts je Feld,
beste Schablonen, U-Trend).
*Abnahme:* zweiter Lauf im selben Feld liest die bestätigten Hosts zuerst und
braucht weniger Web-Aufrufe; U steigt über die Serie, nicht nur die Dichte.

### Stufe 6 — Scouting-Umbau (Owner-Ziel 19.09.)

Owner-Ziel 2026-09-19: „Umbau des Dossiers zum Scouting-Bericht basierend auf
Daten des Korpus und Messblock. Websuche und Deep Research nur für Bereiche
zur Ergänzung oder Beleg dessen, was im Korpus dünn ist. Alles mit lokalen
Tools, keine Cloud-Modelle." Der Korpus wird vom Suchraum zur Grundlage: ein
deterministischer Durchgang VOR Plan und Agenten liefert Signale je Ebene und
Quartal (roh + Anteil je 10.000), Akteure, Quellen, repräsentative Signale als
zitierbare Katalogeinträge und die **dünnen Bereiche**; nur diese bekommen
Web-Schritte, Sweeps und Budget. Der Bericht folgt einem Scouting-Grundriss
(Reifegrad aus dem Messblock, Bewegung korpus-zuerst, „Wo die Belege dünn
sind" als Pflicht). Nutzen: `corpus_share` als Komponente, Reifegrad als
Bedingung der dritten Ampel.
*Abnahme:* datacenter-Serie im Scout-Grundriss mit ≥ 60 % Korpus-Zeilen in
der Bewegungs-Tabelle, ≤ 50 % der bisherigen Web-Aufrufe, Reifegrad-Sektion
mit ≥ 2 gemessenen Größen; Werkzeugvorschlag für Reranker/NER/Archivabruf.

**Stand Stufe 6 (2026-09-19, gebaut — Runde 27 in `docs/agentic_dossiers.md`):**
`pipeline/dossier_corpus_evidence.py` (`build`, `web_gating`, `thin_yield`;
Treffer-Regel mit grobem Stamm über Titel + Teaser + Tags, FTS-Vorauswahl ohne
Präfix), verdrahtet in `run()` direkt nach dem Quant-Vorspann; Gating vor den
Sweeps und der Web-Stufe (`result["web_gating"]`), DR-Vorlauf liest nur Seiten
der Web-Lücken; Scout-Grundriss `outline="scout"` (Default, `params
{"outline": "decision"}` = alt) mit `maturity_findings` (≥ 2 gemessene
Größen), `moving_corpus_findings` (≥ 60 %), `thin_findings`; `corpus_share`
0,15 in jedem Preset, `maturity_present` in `delivery_ready`; Desk-Block
„Corpus evidence" über dem Bericht; Werkzeugvorschlag (Reranker
bge-reranker-v2-m3, GLiNER/spaCy-NER, Wayback/CC-Client, PDF-Tabellen,
Zitations-Resolver) in Runde 27. Messung datacenter (Live-DB, read-only):
31 Signale seit 2024-09, 26 in 12 Monaten (science 2 · patent 6 · funding 0 ·
market 17), dünn: science, funding, regulatory, calendar; die Sweeps Markt
entfällt, Regulatorik/Förderung/Katalysator laufen. **Abweichungen:** der
Kalender bleibt eine eigene Sektion (`next`, kleinere Änderung als die
Verschmelzung mit Regulatorik — alle Kalenderprüfungen hängen an dem
Schlüssel); „does not support" bleibt optional parsbar; die Abnahme (≥ 60 %
Korpus-Zeilen, ≤ 50 % Web-Aufrufe) braucht den ersten Live-Lauf der Serie.

### Ausblick (nicht im Plan)

Feintuning des Schreibers auf Paare (Entwurf → freigegebene Fassung), sobald
≥ 100 freigegebene Dossiers vorliegen; bis dahin wäre es Training auf 3 Beispielen.

## 4. Aufwand und Reihenfolge

| Stufe | Tage | Voraussetzung |
|---|---|---|
| 0 Messlatte | 1 | — |
| 1 Intake + Checkpoint | 2 | 0 |
| 2 Profilbeschaffung | 2 | 1 |
| 4 Prüfen statt Streichen | 2 | 0 |
| 3 VOI-Planer | 2 | 1, 2 |
| 5 Lernschleife | 1–2 | 0, 2, 3 |
| 6 Scouting-Umbau (Owner 19.09.) | 1 | 1, 3 |

Zehn bis elf Tage. Stufe 4 kann parallel zu 1/2 laufen (unabhängig). Nach den
Stufen 0, 1, 2, 4 ist der Zustand „Dossier + Advisor ohne Redaktion" für
Evidenzfragen realistisch; Stufe 3 und 5 machen ihn günstiger und über die
Zeit besser. Jede Stufe endet mit einem Replay über alle bisherigen Läufe und
einem Vergleichslauf auf `datacenter-virtualization` und `iron-phosphate-battery`.

## 5. Qwen-Agent: hilft die Installation?

**Nein, nicht für diese Hebel.** Qwen-Agent (QwenLM) liefert eine
Werkzeugaufruf-Schleife für Qwen-Modelle, RAG über Dokumente, Code-Interpreter,
MCP-Anbindung und eine Chat-Oberfläche. Das ist die Mechanik, die
`corpus_research.py` schon hat — mit Dingen, die Qwen-Agent nicht hat:
grammatikgebundene JSON-Antworten über llama.cpp (`chat_structured`), Budgets und
Ledger je Schritt, Web-Cache, Rangfilter, Faktenzettel, Zitatprüfung,
Modell-Identitätscheck, GPU-Handover. Die zehn Hebel liegen in Intake,
Quellmodell, Prüfung, Nutzenplanung und Erfahrungsbasis — davon bringt
Qwen-Agent nichts mit. Dagegen stünden zwei Risiken: die Werkzeugaufrufe laufen
über Qwens Funktions-Prompt-Format (`--jinja`-Template auf dem llama-server,
Parser auf Client-Seite) statt über die Grammatik, und ein zweiter Agenten-Zustand
neben dem eigenen. Wo Qwen-Agent später sinnvoll wäre: als MCP-Host, wenn
Korpussuche, Patentmessung und Dossierstand als Werkzeuge für andere Clients
angeboten werden sollen — ein anderes Ziel als bessere Dossiers.
