# Agentic Scouting-Dossiers (Owner-only) — `/trends/dossiers`

Stand 2026-09-07 (Runde 3: Themenschärfe R3-1 bis R3-4 — s. „Die dritte
Runde" weiter unten; davor am selben Tag Entscheidungsebene S1-S4 und
Messkette M1/M2/M3/M4/M6, davor 2026-09-03
Frontend-Integration #95, Branch `Agentic-Dossiers` am 2026-09-03 nach `dev`
gemergt). Baut den agentischen Rechercheur (`scripts/corpus_research.py`,
Skizze in `docs/corpus_research_sketch.md`) zum Owner-Werkzeug aus: Der Owner
bestellt Scouting-Dossiers zu Technologiefeldern, der Agent analysiert die
gesamte Innovationskette (Text **und** Messung) und liefert einen zitierten
Bericht samt eigener Endkontrolle — die finale Durchsicht bleibt beim Owner.

## Owner-Festlegungen (2026-09-01, Konstruktionsprinzip)

1. **Nur der Owner erteilt Aufträge.** Dossiers sind kein Kundenfeature; die
   Seite `/trends/dossiers` ist owner-only (s.u.), es gibt keinen Kundenpfad.
2. **Streng lokal.** Recherche, Bericht und Endkontrolle laufen vollständig
   auf dem lokalen Modell (Qwen3.8-27B via llama-server :8090). Kein
   Cloud-Hop — Dossiers sind proprietäre Dokumente mit vertraulichem Inhalt.
3. **Kein Automatikbetrieb.** Kein Cron. Aufträge werden nur abgearbeitet,
   wenn der Owner den Worker startet — von Hand im Terminal oder per Knopf
   im Desk („Run now" / „Recompute"; seit 2026-09-03). (Deckt sich mit der
   älteren Radar-Regel in `save_dossier`: „a dossier is a dated document,
   never a cron job".)
4. **Endkontrolle: erst der Agent, dann der Owner.** Jeder Lauf endet im
   Status `review` mit dem maschinellen Prüfbefund; `done` gibt es nur per
   Owner-Abnahme („Sign off").

## Ablauf

```
Owner: Auftragszettel                    Owner: Worker-Start (Knopf oder Terminal)
/trends/dossiers  ──▶  dossier_orders  ──▶  scripts/dossier_worker.py
                        (queued)              │  (lib/dossierWorker.ts spawnt
                                              │   detached, Lock + Log unter data/)
                                              ▼  Phase 1 (Embedding-Handover)
                                    pipeline/dossier_quant.py
                                    Messkaskade → CPC → TIR-Trajektorie →
                                    Lead-Time → Zykluszeit/Zentralitaet →
                                    Leitpatente  ➜  zitierbarer Messblock
                                    (Quelle "Q1" + Hub-Patente) + Messanhang
                                              │
                                              ▼  Phase 1b (CPU/SQL, kein Modell)
                                    pipeline/dossier_corpus_stats.py
                                    zaehlt Markt- und Forschungsschicht
                                    ➜  Quelle "Q0" + Korpus-Anhang
                                              │
                                              ▼  Phase 2 (27B-Handover, Guards)
                                    scripts/corpus_research.py run()
                                    Plan → Korpus (Artikel+Signale) → Audit →
                                    Paper/Patent-Sweep (audit-unabhaengig) →
                                    Rechts-/Zulassungs-Sweep (feste Muster,
                                    Volltext, eigenes Budget) → Web →
                                    Re-Audit → EINE Sweep-Nachrunde →
                                    Bericht (verbindliche Gliederung) →
                                    Struktur- + Beleg-Pruefung → EIN Neuwurf →
                                    Zitat-Kanonisierung (Katalog-IDs) →
                                    Ausgeliefertes Dokument | Pruefanhang
                                    → dossiers(slug, v+1)
                                              │
                                              ▼
                                    pipeline/dossier_check.py (deterministisch)
                                    Zahlen-Grounding · Zitat-Bilanz · offene
                                    Fragen · Messung ausgefallen/ungenutzt
                                    ➜  check_json, Status 'review'
                                              │
Owner: /trends/dossiers/[slug]  ◀─────────────┘
Bericht + Endkontrolle + Versionshistorie · „Sign off" → 'done'
```

## Bausteine

| Teil | Datei | Rolle |
|---|---|---|
| Auftragszettel | `pipeline/dossier_orders.py` | Tabelle `dossier_orders`, Statusfluss `queued→running→review→done` (nie automatisch über `review` hinaus), `cancelled`/`failed`/requeue |
| Quant-Vorstufe | `pipeline/dossier_quant.py` | Messkaskade (`measure_topic`) auf `scripts/tech_analyze` (deterministisch, vor dem ersten Modell-Hop), formatiert Messblock + Katalogquellen + **codegenerierten Messanhang**; jede Zahl trägt ihre Ehrlichkeitsgrenze (TIR kalibriert bis ~2019, Patent ≠ Produkt, Datenfenster ab 1990). Degradiert ohne GPU/Postgres zum protokollierten Fehlgrund — und der Fehlgrund steht sichtbar im Dossier |
| Korpus-Zählung | `pipeline/dossier_corpus_stats.py` | zweite deterministische Vorstufe (CPU/SQL): zählt Markt-/Signalschicht (`trends`) und Forschungsschicht (`research_corpus` + Förderer) je Jahr/Vertikale/Signaltyp/Quelle ➜ Katalogquelle `Q0` + Anhang „Was der Korpus zählt". Jeder Block eigenes `statement_timeout`, degradiert einzeln |
| Rechercheur | `scripts/corpus_research.py` | `run(..., quant=..., corpus_stats=..., measure=True)` injiziert Messquellen+Notizen (gepinnt), sweept audit-unabhängig, zitiert per Katalog-ID und hängt die codegenerierten Anhänge an; Result enthält `evidence`, `quant`, `corpus_stats`, `measure`, **`audit_annex`** (Suchprotokoll, getrennt vom Bericht); CLI `--quant`, `--measure`/`--no-measure` |
| Entscheidungsebene | `pipeline/dossier_structure.py` | deterministisch, kein Modell: verbindliche Gliederung (6 Pflichtabschnitte), 200-Woerter-Kappe der Kurzfassung, harte Obergrenze 2.800 Woerter Fliesstext, Pflichtfelder je Option (Auslöser/Zeithorizont/Aufwand/Risiko/Dagegen spricht), **Messbezug je Option** (`measured_needles` — jede Option muss eine gerechnete Zahl tragen), **Branchenabdeckung** (`sectors_from_question` — die Optionen müssen jedes in der Frage genannte Feld bedienen) und die Beleg-Verifikation `verify_cited_figures`: Zahlen eines Satzes gegen den Volltext genau der zitierten Web-Seite, Gegenstand des Satzes (`unverified_subjects`), Präzisionszahlen ohne Beleg (`sourceless_figures`) und **verdrehte Wiedergabe** (`qualifier_conflicts` / `magnitude_conflicts` / `category_conflicts`). `split_claims` trennt Sätze nie innerhalb eines Zitat-Links. `revision_prompt` = der EINE Neuwurf, `drop_unverified` = die Streichung danach. `AUDIT_ANNEX_MARK`/`delivered`/`join_document` trennen ausgeliefertes Dokument und Prüfanhang |
| Endkontrolle | `pipeline/dossier_check.py` | deterministisch: `ungrounded_specifics` (pipeline/grounding.py) über den modellgeschriebenen Berichtsteil (Coverage-, Mess- und Korpus-Anhang abgetrennt) gegen das gesamte gesammelte Material; plus gestrichene Zitate, Zitatquote, offene Fragen (Plan-Schritte zählen nicht mit) und **Messbefund** (ausgefallen / gemessen aber ungenutzt) |
| Worker | `scripts/dossier_worker.py` | Owner-getriggert, zweiphasig (ein Embedding- + ein 27B-Handover für alle Aufträge); `--list`, `--order N`, `--order-new "topic" [--run]`, `--assume-model-up`, `--skip-quant` |
| GPU-Guards | `pipeline/gpu_handover.py` `model_on_llamacpp` | generischer Handover mit striktem VRAM-Vorab-Check (27B braucht <1100 MiB Fremdbelegung — 2026-08-26-Vorfall) + Identitäts-Check via `/v1/models`; 27B-Startskript in `MODEL_START_SCRIPTS` registriert |
| Frontend | `frontend/src/app/trends/dossiers/*`, `lib/dossiers.ts`, `lib/dossier-access.ts`, `lib/dossierWorker.ts` | Owner-Desk (Formular mit „sofort starten", Worker-Status, Auftragsliste mit Run now/Run again/Cancel/Sign off, Serienliste mit „Recompute · v(n+1)") + Leseansicht: Herkunftskopf (Frage, Belegmix, zitiert/gestrichen, Messblock-Kurzfassung, Modell/Retrieval/Dauer/Sprache), Endkontroll-Panel, Bericht (Markdown-Renderer des Repos inkl. Pipe-Tabellen, Links via `safeHref`), strukturierter Coverage-Anhang, Versionswechsler, Sign-off. Server Actions: `canManageDossiers()` + Same-Origin (`isSameOriginHeaders`) |

## Zugriff & Deployment

- **Flag:** lokal **standardmäßig AN** (Owner-App, seit 2026-09-03 — die
  Auth/Tier-Schicht ist mit #93 weg). `DOSSIERS_ENABLED=0` ist der Not-Aus
  (404). Regel in `lib/dossier-access.ts`, gleiche Form wie `review-access.ts`:
  offen auf der Owner-Instanz, immer zu unter `PUBLIC_MODE=1` und im
  statischen Export.
- **PUBLIC_MODE / Export:** `/trends/dossiers` steht in `BLOCKED_PREFIXES`
  (`lib/publicMode.ts`, Matcher in `src/proxy.ts`) und in
  `frontend/static-export.exclude`; `staticExport.test.ts` wacht über die
  Parität. Die öffentliche Seite kennt die Route nie (Smoke 2026-09-03:
  `:3999/trends/dossiers` → 404, Export ohne `dossiers`-Dateien).
- **Worker-Start aus dem Desk:** `lib/dossierWorker.ts` spawnt
  `<repo>/.venv/bin/python -m scripts.dossier_worker [--order N]` detached
  (cwd = Repo-Root neben `frontend/`, überschreibbar mit
  `DOSSIER_WORKER_ROOT`), setzt `XDG_RUNTIME_DIR`/`DBUS_SESSION_BUS_ADDRESS`
  für den systemd-Handover, schreibt `data/dossier_worker.lock` (pid, Log)
  und leitet die Ausgabe nach `data/dossier_worker/<stamp>.log`. Ein Worker
  zugleich; ein aus dem Terminal gestarteter Worker ist dem Lock unbekannt,
  der Desk zeigt dann den DB-Status `running`.
- **Ruhezustand:** der Worker merkt sich, ob llama-server vor dem Lauf lief,
  und startet ihn danach wieder (Symlink zeigt nach dem Handover aufs
  208K-8B) — auch wenn der GPU-Guard den Lauf verweigert hat.
- **Migration (einmalig, von Hand, auf dem Host mit DATABASE_URL):**

  ```bash
  .venv/bin/python scripts/migrate_dossier_orders.py
  ```

  Bekannte Repo-Falle (siehe `migrate_dead_links.py`): additive Migrationen
  laufen nie automatisch. Bis zum Lauf zeigt die Seite einen Hinweis statt zu
  crashen (to_regclass-Guard), und der Worker legt sich sein Schema selbst an.
  **Auf der Live-DB am 2026-09-03 ausgeführt** (zweimal — idempotent:
  `dossier_orders` neu, `dossiers` bestand aus den CLI-Läufen, Indizes
  `idx_dossier_orders_status`, `idx_dossiers_slug`).

## Bedienung (Owner-Runbook)

```bash
# Auftrag über die Seite ODER per CLI:
.venv/bin/python -m scripts.dossier_worker --order-new "solid-state batteries" --run

# Alle offenen Aufträge abarbeiten (nicht parallel zum 04:00-Full-Cycle!):
.venv/bin/python -m scripts.dossier_worker

# Auftragslage:
.venv/bin/python -m scripts.dossier_worker --list

# 27B läuft schon (z. B. nach Draft-Richter-Session):
.venv/bin/python -m scripts.dossier_worker --assume-model-up
```

Gleiches Thema erneut bestellen ⇒ nächste Version derselben Serie
(`dossiers(slug, version)`); die Leseansicht verlinkt alle Versionen —
„was hat sich seit dem letzten Lauf verschoben" ist selbst das Signal.

## Die Messkette (2026-09-07)

Ausgangsbefund der Vorab-Analyse (Testthema GLP-1): in **13 von 13** gespeicherten
Läufen wurde die Messquelle `Q1` **kein einziges Mal** zitiert, und auf dem
Testthema selbst startete die Messung gar nicht erst — `dossiers.id=13` trägt
`quant = {"off_topic": true}`. Damit konkurrierte das Werkzeug auf dem Feld
„gut geschriebene Web-Zusammenfassung", wo ein starkes Cloud-Modell mit vollem
Websuchzugang strukturell überlegen ist. Fünf deterministische Eingriffe, alle
hinter einem Schalter (`--measure` / `--no-measure`, `DOSSIER_MEASURE=0`,
Auftragsparameter `measure`; Default **an**, der alte Pfad bleibt exakt
reproduzierbar):

**M1 — die Messung fällt nicht mehr still aus** (`pipeline/dossier_quant.py`).
`pipeline/query_gate.verdict` verlangt Patent-Volltexte mit ALLEN Wörtern der
Auftragsphrase: „GLP-1 and incretin technology" → **0** Treffer (Kette aus),
„GLP-1 receptor agonist" → **≥ 2.000**. Das Wort „technology" schaltete die
gesamte Messung ab. `normalize_topic()` entfernt Füllwörter (and/technology/
market/sector/…), `measure_topic()` fährt die Kaskade:

1. volle Auftragsphrase → 2. normalisierte Phrase → 3. Kernbegriffe einzeln →
4. Kandidaten eines `ambiguous`-Gates (`analyze_query(..., codes=…)`, der Pfad
existierte und wurde nie benutzt) → 5. `fine_codes_in()`: Embedding-Nachbarschaft
∩ CPC-Subklassen aus dem eigenen Korpus (`signal_cpc`) → 6. die groben
Subklassen (als „broad" gekennzeichnet).

Der `Q1`-Snippet behauptet im `ambiguous`-Fall keine TIR-Messung mehr, und
**fällt die Messung trotzdem aus, steht jeder Versuch mit seinem Gate-Befund
im Dossier** statt spurlos zu verschwinden.

**M2 — die gerechneten Zeitreihen erreichen den Bericht.**
`tech_analyze.leadtime()` liefert je Reifegrad ein Jahres-`series`-Dict,
`tir_trajectory.trajectory()` `points` (K(t) je Jahr mit n) — beides wurde
gerechnet und vor dem ersten Modell-Hop weggeworfen. Beides steht jetzt in der
Messnotiz **und** in `measurement_appendix()`, einem codegenerierten Abschnitt
(wie der Coverage-Anhang, nicht vom Modell geschrieben): Zeitreihe je Ebene,
Take-off-Jahre, Patent→Markt-Vorlauf, K(t) mit n, **Zykluszeit** (neu:
`cycle_time()` über `patent_links`, gedeckelt + degradierend) und
**Zentralitäts-Peak** (neu: `trajectory()` liefert additiv `x_by_year`, also
keine zweite Query über 42 Mio Zeilen). Die Messnotiz ist gegen den
FIFO-Verwurf **gepinnt** (`evidence_block(notes, pinned)`) — sie war `notes[0]`
und flog in beiden Perowskit-Läufen (42,8k / 48,3k Zeichen Evidenz) als Erstes
aus dem Report-Prompt.

**M3 — der Korpus wird gezählt, nicht nur durchsucht**
(`pipeline/dossier_corpus_stats.py`). In `corpus_research.py` gibt es keine
einzige Aggregat-Query; der Schreiber sah von 1.366 GLP-1-Marktsignalen und
21.590 Arbeiten rund 45 Titel. Die neue Vorstufe zählt Markt-/Signalschicht
(Jahresreihe, Vertikale, Signaltypen, Top-Quellen; 14 s) und Forschungsschicht
(Jahresreihe, Reviews, Zitationen, Top-Geldgeber; 3 s) und liefert `Q0` plus
Anhang. Bewusst **nicht** gezählt und im Anhang benannt: Patente (~130 s
Textzähler, und der Messanhang erfasst sie bereits CPC-nativ), die
Venture-Schicht (420.564 `startup_events` tragen keinen Text, die Brücke über
`startup_patent_links` kostet ~350 s) und `raw_entries` (kein FTS-Index).

**M4 — Zitate per Katalog-ID.** Der Report-Prompt zeigt keine URLs mehr; das
Modell zitiert `[[T412335]]`, `canonicalize_citations(..., markers=True)`
rendert daraus den kanonischen Link. Was nicht im Prompt steht, kann nicht
halbrichtig abgetippt werden (Perowskit v1: 46,7 % der Zitat-Instanzen
gestrichen, zwei davon 404-tote Pfade auf echten Domains). Der
Freitext-URL-Pfad bleibt bestehen und streicht weiterhin.

**M6 — Sweep vom Audit entkoppelt.** Der Paper-/Patent-Sweep lief nur bei
Audit-Befund (kein Befund ⇒ kein Paper, kein Patent); er nimmt jetzt auch die
Plan-Schritte mit. Kappen 12/8 → **24/16** als ein gemeinsames Budget (sie
banden in 12 von 13 Läufen), Paper-Budget hälftig „meistzitiert"/„neueste"
(Zitationsfame liefert für ein schnelles Feld die alten Klassiker),
Relevanzschwelle `on_topic()` gegen themenfremde Treffer (ein Lauf nahm ein
Patent auf, das der Bericht selbst als „unrelated to GLP-1 technology"
bezeichnete) und **genau eine** Nachrunde über die Lücken, die erst der
Re-Audit benennen konnte. Keine Schleife: der Schreib-Kritik-Loop bleibt
verworfen (Owner 2026-09-06, `docs/newsletter_agentic_prototype_2026-09-06.md`)
— hier geht es nicht um Textpolitur, sondern um fehlende Evidenz.

**Endkontrolle** meldet jetzt zusätzlich „Messung ausgefallen" und „gemessen,
aber im Berichtstext nicht verwendet"; die audit-unabhängig gesweepten
Plan-Schritte zählen nicht als offene Fragen.

Nicht umgesetzt (bewusst): M5 (Akteurszählung aus `trends.brands/companies`,
`patent_assignee_norm`, `research_work_inst`), M7 (Evidenzbudget nach Wert
statt Alter — nur das Pinning ist da, `MAX_EVIDENCE_CHARS` bleibt 30.000) und
M8 (URL-Liveness, `ungrounded_names`, Sprachprüfung, `lang` in
`ALLOWED_PARAMS`, Stale-Reset hängender Aufträge).

## Die Entscheidungsebene (2026-09-07)

Zwei Blindgutachten über dieselben drei GLP-1-Dossiers (Gutachter in der Rolle
„Strategieverantwortung eines europäischen Lebensmittelmittelständlers") haben
unser Dossier mit **51/70** bzw. **54/70** hinter eine reine Sonnet-Web-Recherche
(**59/70** bzw. **62/70**) gesetzt. Verloren wurde nicht an der Recherche,
sondern an drei Dingen — jedes davon ist jetzt Mechanik, nicht Prompt-Hoffnung:

**S1 — Entscheidungsebene.** „Mit 5.906 Wörtern zu lang und nicht auf eine
Entscheidung zugeschnitten"; der Gutachter gab den Text „ans Entwicklungs- und
Regulatory-Team, nicht ins Gremium". Der Sieger brauchte 2.833 Wörter. Der
Report-Prompt (`corpus_research.report_system`) schreibt jetzt sechs
Pflichtabschnitte vor — *Decision summary* (max. 200 Wörter, drei belegte
Aussagen), *What is moving*, *Regulatory and IP status*, *What the evidence does
not support*, *Options for a mid-sized European company*, *Open questions and
limits* — und eine Obergrenze von **2.800 Wörtern Fließtext** (Anhänge zählen
nie mit; gezählt wird ohne Zitatapparat, damit dieselbe Zahl vor und nach der
Kanonisierung gilt). Deutsche Fassung gleichwertig.

**S2 — Rechts- und Zulassungsstatus.** Der entscheidungstragende Befund des
Siegertexts war ein Rechtsstatus: EU-Grundpatent Semaglutid ausgelaufen, aber
**SPC-Schutz bis März 2031**, gerichtlich durchgesetzt, während Generika in
Indien/Brasilien/China starten. Unser Korpus *zählt* Patente, führt aber keinen
Rechtsstatus, und die allgemeine Web-Stufe verwarf solche Treffer still gegen
die gemeinsame Kappe (der Askea-Fall). `sweep_regulatory()` ist deshalb eine
eigene Suchrichtung: sechs feste Muster (SPC/Patentablauf Europa · EMA · FDA ·
Gerichtsentscheidung/Verfügung · EFSA-Health-Claim · EU-Regulierung) auf die
messnormalisierte Themenphrase, Treffer **verpflichtend im Volltext gefetcht**
(ein Snippet trägt hier kein Zitat), eigener Katalogbereich `[legal]` mit
reserviertem Budget (`REG_MAX_SOURCES` 12 / `REG_MAX_FETCH` 8), das die
allgemeine Web-Kappe nicht berührt. Jedes Muster steht im Suchprotokoll, auch
das ohne Treffer — „dazu nichts gefunden" muss im Abschnitt stehen können.
Die Ledger-Zeilen tragen `kind: "legal"` und zählen nicht als offene Frage.

**S3 — Entscheidungsgerüst.** Allen drei Texten fehlte ein Go/No-Go. Jede
Option trägt jetzt verpflichtend *Trigger · Time horizon · Effort · Risk ·
Against it*, dazu einen Absatz zur Kannibalisierung des Bestandsgeschäfts; die
kaufmännischen Fragen (Investitionshöhe, Amortisation, gefährdetes Volumen)
werden im Schlussabschnitt als offen benannt statt geschätzt. Fehlt ein Feld,
ist das ein mechanischer Befund.

**S4 — Beleg-Verifikation (Beleg-Stichprobe, `jury_2.md`).** Unser Dossier
behauptete „GKV +1,2 Mio. Patienten/Jahr" mit Link auf einen ING-Artikel, der
diese Zahl nachweislich nicht enthält. Die Kanonisierung belegt nur, dass die
URL im Katalog liegt. `verify_cited_figures()` prüft deshalb jeden Satz, der
**ausschließlich** gefetchte Web-/Rechtsquellen zitiert, gegen den Volltext
genau dieser Seite — mit `ungrounded_specifics` aus `pipeline/grounding.py`,
verschärft um eine Dezimalprüfung: dessen Normalisierung entfernt Punkt *und*
Komma (deutsch/englisch tauschen die Trennzeichen), macht also aus „1.2" ein
„12" — und „12" stand auf der Seite. Sätze mit Korpuszitat bleiben beim
bestehenden Pfad (ihr Beleg ist der Evidenzblock, keine Seite).

**Genau ein Neuwurf, dann Mechanik.** Struktur- und Belegbefunde gehen als *ein*
Revisionsauftrag zurück ans Modell (`revision_prompt`, ohne Evidenzblock — es
soll nichts Neues holen). Danach werden verbliebene, nicht gedeckte Sätze
`drop_unverified()`-mechanisch gestrichen. **Keine Schleife, kein
Kritiker-Modell** (Owner 2026-09-06,
`docs/newsletter_agentic_prototype_2026-09-06.md`).

**Zitat-URL-Hygiene.** `valid_url`/`citable_url`: eine URL mit Leerzeichen im
Host (Artefakt der Anonymisierung, aber real im Bericht) fällt aufs Original
zurück; ist auch das kein URI, trägt die Quelle kein Zitat. Das
Quellenverzeichnis dedupliziert (die Stichprobe fand zwei Doppeleinträge).

**Schalter.** Alles hängt am bestehenden `measure` (`DOSSIER_MEASURE=0` oder
Auftrags-`params {"measure": false}`) — `report_system(False, …)` ist wörtlich
der alte `REPORT_SYSTEM`, der alte Pfad bleibt reproduzierbar.

## Die dritte Runde (2026-09-07) — Themenschärfe und Belegdisziplin

Nach der Entscheidungsebene lief dasselbe Blindverfahren erneut: zwei Jurys
(`scratchpad/glp1/jury_3.md`, `jury_4.md`) verglichen unser Dossier
`glp1-decision` mit einer reinen Web-Recherche. Ergebnis **33/70 gegen 57/70**
bzw. **40/70 gegen 61/70** — deutlicher als in Runde 1/2. Vier Befunde gaben
den Ausschlag; alle vier sind jetzt Mechanik.

**R3-1 — die Eigenmessung war zu grob und galt beiden Jurys als „Zahlenschmuck".**
Die CPC-Auswahl landete auf `A61P3/10` („for hyperglycaemia, e.g.
antidiabetics", **70.991 Patente**) — dem ganzen Antidiabetika-Feld, nicht
Inkretinen. Folgen im eigenen Anhang: die Verbesserungsrate schwankte über 42
Jahre nur zwischen 2,9 und 4,4 %, die Leitpatente hießen „Humanized
immunoglobulins", und der Bericht musste seine eigene Top-Liste als „kein
Themenranking" ausweisen. Ursache im Code: `resolve_candidates()` wählt in
Distanzreihenfolge vor, bis `DENSITY_TARGET` (8.000 Patente) erreicht ist — eine
einzige breite Auffangklasse reißt dieses Budget in einem Schritt um das
25-fache. `pipeline/dossier_quant.topical_precision()` misst deshalb je Klasse
die **Trefferdichte**: welcher Anteil ihrer Patente nennt das Thema überhaupt im
Titel/Abstract (`patent_search`-Volltext, ~3 s)? `sharpen_selection()` behält
nur Klassen ab `max(2 %, ⅓ der besten Klasse)`. Auf GLP-1 gemessen:
`C12N2501/335` 10,0 % · `A61P5/48` 5,8 % · `A61P3/10` **2,2 % → raus**;
Messbasis 49.913 → **2.688 Patente**. Trägt die scharfe Basis keine Trajektorie
mehr oder bleibt keine Klasse übrig, **entfällt der Messblock** und der Anhang
schreibt hin, warum (`verdict: base_too_broad`) — ein fehlender Block kostet
weniger als ein irreführender. Die Leitpatente führt `topical_hubs()` nur noch,
wenn der Titel einen Themenbegriff trägt; sonst entfällt der Block ganz.
Behalten wurde die Kennzahl, die trug: „kein Technologie-Cliff trotz
Marktdynamik" (Zykluszeit 11,0 Jahre).

**R3-2 — Fehlzuordnung einer Quelle.** Ein CNBC-Artikel über Novos
Wegovy-Pille wurde zweimal als Beleg für Lillys Orforglipron-Zulassung geführt.
`verify_cited_figures()` prüfte Zahlen — und die Zahl stimmte ungefähr;
geprüft wurde nie der **Gegenstand**. `dossier_structure.subject_names()`
zieht die Firmen-, Produkt- und Wirkstoffnamen aus dem Satz (Eigennamen-Phrasen
plus INN-Endungen: -tide, -glipron, -mab …), `unverified_subjects()` verlangt
jeden davon wortweise im Volltext der zitierten Seite (`grounding._in_source`,
diakritika- und possessivtolerant). Fehlt einer, wird das **Zitat abgelehnt**.
Bewusst nicht geprüft werden reine Abkürzungen (FDA, EMA) und Einzelwörter
hinter einem Artikel („the Hague") — dort wäre die Falsch-Ablehnung
wahrscheinlicher als der Fund.

**R3-3 — quellenlose Präzisionszahlen.** „North America held 77.72% … CAGR of
14.6% through 2035 ." — der Satz endet auf einen freistehenden Punkt, wo das
Zitat stehen sollte. `sourceless_figures()` verlangt für jede Präzisionszahl
(Dezimalwert, Prozent, Betrag, Größenordnung) im Fließtext **ein Zitat im
selben Satz** — oder die Zahl muss aus dem eigenen Messanhang stammen, der
codegeneriert im selben Dokument steht. Jahreszahlen und kleine ganze Zahlen
sind keine Präzisionszahlen (sie zu streichen würde jeden zweiten Satz kosten,
ohne einen Beleg zu erzwingen). Befund geht denselben Weg wie eine widerlegte
Zahl: **ein** Neuwurf, danach `drop_unverified()`.

**R3-4 — interne Belege sind für Dritte unprüfbar.** Die Messquellen zeigen auf
`catandary.de`, das Bot-UAs mit 403 abweist (unsere eigene KI-Crawler-Sperre,
`frontend/src/lib/aiCrawlers.ts`) — beide Jurys konnten die zentralste Quelle
des Berichts nicht abrufen. Die Sperre bleibt. Stattdessen weist sich der
Messanhang selbst als der Beleg aus: Rechenweg, Klassenauswahl mit
Trefferdichte, n und Zeitraum stehen im Dokument, plus der Satz, dass hinter dem
Link kein öffentlich abrufbares Dokument liegt und keine Fremdquelle diese
Zahlen trägt.

**R3-5 (aus `jury_4.md`) — Abdeckungslücke des Sweeps.** Dem Siegertext lagen
Ereignisse vor, die uns komplett fehlten: das Bietergefecht um Metsera,
Frankreichs Erstattungspremiere, der NHS-Rollout, die Wirkstoff-Pipeline. Das
ist kein Schreib-, sondern ein Sweep-Problem: die allgemeine Web-Stufe folgt den
Lücken, die das Audit benennt, und ein Audit über einem technologielastigen
Korpus benennt keine Erstattungsentscheidung. `sweep_regulatory()` ist deshalb
zu `sweep_fixed()` verallgemeinert (feste Muster, eigenes Katalogbudget,
Volltextpflicht, Protokoll auch über die Muster ohne Treffer), und
`sweep_market()` ist die **zweite feste Richtung**: Erstattungsentscheidung
(FR/DE) · nationaler Rollout · Übernahme/Bietergefecht · Phase-3-Ergebnisse ·
Quartalszahlen · Markteintritt und Preis. Eigener Katalogbereich `[market]`
(`MKT_MAX_SOURCES` 12 / `MKT_MAX_FETCH` 8) — Recht und Markt konkurrieren nicht
um dieselbe Kappe. Ledger-Zeilen `kind: "market"` zählen wie die
Rechts-Zeilen **nicht** als offene Frage (Python wie Frontend).

**Schalter unverändert:** alles hängt am bestehenden `measure`
(`DOSSIER_MEASURE=0` / Auftrags-`params {"measure": false}`); der alte Pfad
bleibt reproduzierbar. Kein Kritiker-Modell, keine Schreib-Kritik-Schleife.

## Tests

- `tests/test_dossier_orders.py` — Statusfluss-Invarianten (nie automatisch
  `done`, mark_running gewinnt genau einmal, requeue).
- `tests/test_dossier_check.py` — Grounding inkl. Coverage-Anhang-Abtrennung,
  Zitat-Bilanz.
- `tests/test_dossier_quant.py` — Messblock-Formatierung (Ehrlichkeitsgrenzen,
  Established-Fall, off-topic), Degradierungspfade.
- `tests/test_dossier_worker.py` — Worker-Kontrakt ohne GPU (review+Version,
  failed, Identitäts-Guard, Quant-Durchreichung).
- `tests/test_dossier_measure.py` — die Messkette: Normalisierung und Kaskade
  an genau den beiden gemessenen Phrasen, sichtbarer Fehlschlag, Zeitreihen im
  Messanhang, Pinning gegen den FIFO-Verwurf, ID-Zitate (auflösen/streichen/
  alter Pfad), Sweep-Budget + Relevanzschwelle, Messbefunde der Endkontrolle,
  Reproduzierbarkeit des alten Pfads.
- `tests/test_dossier_corpus_stats.py` — Korpus-Zählung: Q0, Jahresreihen im
  Anhang, benannte Grenzen, Teil- und Totalausfall.
- `tests/test_dossier_decision.py` — die Entscheidungsebene: Pflichtabschnitte,
  Längenobergrenze, 200-Wörter-Kappe, Pflichtfelder je Option, Stabilität der
  Wortzahl über die Kanonisierung; Rechts-Sweep (jedes Muster gesucht und
  protokolliert, „nichts gefunden" steht drin, ungelesene Seite ist nicht
  zitierbar, Fetch-Budget, Suchausfall killt den Lauf nicht, `[legal]` ist
  keine offene Frage); Beleg-Verifikation an genau dem durchgerutschten Fall
  („1,2 Mio." gegen die ING-Seite) inkl. Streichung; URL-Hygiene und
  Doppeleinträge. Dazu Runde 3: Themenschärfe der Messbasis (breite
  Auffangklasse fliegt raus, Dichte-Query-Ausfall ändert nichts, Messung
  entfällt statt zu täuschen, themenfremde Leitpatente), Themenprüfung der
  Zitate (genau der CNBC/Lilly-Fall), quellenlose Präzisionszahlen (inkl. der
  Ausnahme „steht im eigenen Messanhang") und der Markt-/Erstattungs-Sweep.
- Frontend: `dossier-access.test.ts` (Guard: Default an, Not-Aus, PUBLIC_MODE/
  Export zu; Slug-Parität zu Python), `publicMode.test.ts` + `staticExport.test.ts`
  (Blockliste ↔ Export-Ausschluss), `markdown.test.ts` (Pipe-Tabellen),
  `apiGuards.test.ts` (`isSameOriginHeaders`).

## Abnahmelauf 2026-09-03 (#95 §1) — „perovskite tandem photovoltaics"

Erster Lauf über die integrierte Kette (Auftrag #1 → Worker → `dossiers` v1 →
Desk), Themen-Modus, Quant-Vorstufe an, Web-Sweep mit Brave-Key.

| Kriterium | Ziel | Gemessen |
|---|---|---|
| Zitate im **fertigen** Dossier belegt (jede zitierte URL im gesammelten Katalog) | ≥ 95 % | **8/8 = 100 %** (Kanonisierung erzwingt es; unabhängig nachgeprüft) |
| Zitate im **Roh-Bericht** des Modells belegt | — | 8 von 15 Zitat-Instanzen (53 %); 7 Instanzen auf 3 katalogfremde URLs gestrichen |
| Erfundene URLs im fertigen Dossier | 0 | **0** — alle 8 per robots-treuem HEAD/GET erreichbar (8× 2xx/3xx, 0 tot, 0 geblockt) |
| Erfundene URLs im Roh-Bericht | — | 3: `us.qcells.com/blog/…korea/` 404, `pv-magazine.de/2025/10/01/oxford-pv-…` 404, `energysolutionsintelligence.com/…` Domain nicht erreichbar → alle gestrichen |
| Zahlen-Grounding (Endkontrolle) | 0 unbelegt | **0** unbelegte Zahlen (1.630 Wörter) |
| Wörtliche Zitate (Anführungszeichen, ≥ 4 Wörter) | ≥ 95 % | 1/1 wörtlich im Material |
| Coverage-Ledger | vollständig | 6 Zeilen, alle Felder befüllt (Paper/Patente/Web-Queries/-Treffer/-Fetches); die 4 Lücken + 2 Widersprüche des Erst-Audits sind gesweept; **Prüfpunkt:** 1 der 4 nach dem Re-Audit verbleibenden Lücken (Profitabilität der Pilotlinien) entstand erst im Re-Audit und hat keine Ledger-Zeile |
| Streichungsquote | niedrig | 7/15 Zitat-Instanzen = **46,7 %** (nach distinkten URLs 3/11 = 27 %) — offener Punkt, s. u. |
| Dauer | 10–15 min | Recherche 476,6 s; Wandzeit inkl. beider Handover 568 s (20:07:08 → 20:16:36) |
| Belegmix | — | 58 Quellen: 7 Artikel / 11 Signale / 12 Paper / 9 Patente / 18 Web; Messblock: 8 CPC-Klassen, „Improving fast (median ~13 %/yr)", Lead-Times nicht messbar |
| Handover | Ruhezustand | Emb-8B → 27B (Pre-Flight, VRAM 172 MiB) → Symlink zurück auf `start-qwen3-8b-208k.sh`; llama-server danach manuell neu gestartet (Restore seit `22e9c83` im Worker) |
| v2 per Desk-Knopf (Recompute) | E2E | Server Action → Worker detached: 562 s, 58 Quellen (6A/8S/12P/12N/20W), 13 zitiert, 4 gestrichen, `review`, im Desk als v2; Ruhezustand danach automatisch wiederhergestellt (llama-server aktiv, 8B-208k) |

Befund: Belegtreue und URL-Echtheit des **fertigen** Dossiers erfüllen die
Ziele; die Schwäche liegt vor der Kanonisierung — das Modell zitiert
plausible, aber nicht existierende Pfade bekannter Domains (zwei 404 auf
qcells/pv-magazine). Die Streichung fängt das ab, kostet aber Belege im Text.

## Messlauf 2026-09-07 — „GLP-1 and incretin technology" (A/B)

Derselbe Auftrag, dieselbe Frage, einmal ohne (`glp1-baseline` v1, 2026-09-06)
und einmal mit Messkette (`glp1-measured` v1). Alle Zahlen aus
`dossiers.result`.

| | A (ohne) | B (mit Messkette) |
|---|---|---|
| Messung gelaufen | **nein** — `quant = {"off_topic": true, "nearest_dist": 0.266}` | **ja**, 2. Kaskadenstufe (`GLP-1 incretin`) |
| Messanhang / Korpus-Anhang im Dossier | nein / nein | **ja / ja** |
| Katalog | 57 Quellen | **96** (8 Artikel / 12 Signale / 32 Paper / 22 Patente / 20 Web / 2 Messung) |
| Zitiert | 14 | **21**, darunter erstmals die Messquelle (0 in 13 Läufen davor) |
| Zitat-Instanzen im Roh-Bericht | 20 URL-Freitexte | **73 Katalog-IDs** |
| Streichungsquote (Instanzen) | 5/20 = **25,0 %** | 7/73 = **9,6 %** |
| **erfundene Zitatziele** | **2** (`fdaapprovaltimeline.com/orforglipron`, ein `fool.com`-Pfad) | **0** — jeder Marker ist eine echte Katalog-ID; die 7 Streichungen sind ungefetchte Web-Treffer, die per Konstruktion nicht zitierbar sind |
| Sweep-Ausbeute | 12 Paper / 7 Patente | **32 Paper / 22 Patente**, 2 Treffer als themenfremd verworfen |
| Ledger | 6 Zeilen (nur Audit-Lücken) | 19 = 7 Audit-Lücken + 6 Plan-Schritte + **6 Re-Audit-Lücken** (Nachrunde) |
| Audit | 5 supported | **14 supported** |
| Bericht | 2.078 Wörter | **3.323 Wörter** |
| Dauer | 464 s Recherche | 693 s Recherche, 815 s Wandzeit inkl. Messung + Zählung |

Gemessen wurden u. a.: CPC-Auswahl `A61P5/48` / `C12N2501/335` / `A61P3/10`
(49.913 Patente im Zitationsgraphen, 1984–2026), K(t)-Median 3,1 %/yr,
**Zykluszeit 11,0 Jahre über 157.545 datierte Zitationskanten** (deckt sich mit
der unabhängigen Handmessung), Take-offs Forschung 1990 / Patente 2004 /
Förderung 2005 / Markt 1990. Eine Patent→Markt-Vorlaufzeit wurde **nicht**
berichtet, weil der Markt-Take-off auf dem Rand des Datenfensters liegt — der
Anhang schreibt das hin. Korpus-Zählung: 1.366 Markt-/Signaltreffer (495
Artikel), 21.590 Arbeiten / 542.118 Zitationen, Top-Geldgeber NIH 937 ·
NIDDK 900 · Novo Nordisk 841.

Endkontrolle: `ok=false`, 3 Befunde (3 „Zahlen ohne Beleg" = Abschnitts-
nummern des Modells, 7 Streichungen, 13 offene Fragen), **`measurement_used =
true`** — die Messung steht im Text, nicht nur im Anhang.

Zwei Funde aus dem Lauf, beide behoben:

* `b3d51dc` — der erste Anlauf brach nach 10 min mit `KeyError('measurement')`
  ab: die codegenerierte Quellenliste hatte kein Label für die Quellenart
  „measurement". 13 Läufe lang unentdeckt, **weil die Messquelle nie zitiert
  wurde**; mit ID-Zitaten zitierte das Modell sie sofort.
* `cd80a8e` — der Zentralitäts-Peak fiel auf 2026, also auf das letzte, noch
  unvollständige Jahr, mit dem sinnlosen Zusatz „seither rückläufig". Der Peak
  kommt jetzt nur noch aus gesetzten Jahrgängen (TRUNC_YEARS).
  *(Der abgelegte Berichtstext ist der Stand vor diesem Fix — es wurde bewusst
  nur ein Lauf gerechnet.)*

Offen geblieben (nicht Teil von M1–M6): die CPC-Auflösung nimmt mit `A61P3/10`
(70.991 Patente) eine breite Klasse mit, weshalb die Leitpatente „Humanized
immunoglobulins" heißen statt GLP-1-Analoga. Der Anhang trägt die Einschränkung
im Klartext, das Ranking selbst bleibt unverändert.

## Entscheidungslauf 2026-09-07 (B2) — „GLP-1 and incretin technology"

Erster Lauf über die Entscheidungsebene (`dossiers glp1-decision` v1, Auftrag
#9, 724 s gegen 815 s des Messlaufs am selben Thema).

- **Gliederung im ersten Wurf bestanden** — alle sechs Pflichtabschnitte da,
  Kurzfassung 195 von 200 Wörtern, drei Optionen mit vollständigem Gerüst;
  `rewritten=false`, der eine erlaubte Neuwurf wurde nicht gebraucht.
- **Rechts-Sweep:** 6 Muster → 35 Treffer → 12 aufgenommen → **8 im Volltext
  gelesen, alle 8 zitiert** (EMA, FDA/CNBC, National Law Review, Maucher
  Jenkins, EFSA Art. 13, EU-Register Health Claims, EU-Kommission, DDReg).
  Der Abschnitt schreibt selbst hin, was er nicht fand (SPC-Daten, europäische
  Verfügung). Erstmals beantwortet das Dossier die **positive** Claim-Frage:
  kein GLP-1-Claim im EU-Register, gangbar wäre ein substanziierter
  Muskelerhalt-Claim.
- **Beleg-Verifikation:** 21 Sätze mit 26 konkreten Angaben gegen den Volltext
  genau der zitierten Seite — **0 nicht gedeckt**, 0 Streichungen. Die
  Endkontrolle meldete **0 Zahlen ohne Beleg** (Messlauf: 3).
- **Fließtext 1.907 Wörter** (Messlauf 2.554, Sonnet-Vergleichstext 1.968) —
  unter dem Zielband 2.200–2.800. Kein Neuwurf-Grund, seither `length_advisory`
  im Prüfbefund.
- **Ein Rückschritt:** 10 von 51 Zitat-Markern gestrichen (19,6 %; Messlauf
  9,6 %) — ausnahmslos ungefetchte Web-Treffer, deren IDs nur in den
  Evidenznotizen stehen; **keine Erfindung**. Behoben nach dem Lauf (`30acacd`:
  Prompt benennt die nicht zitierbaren IDs, `_tidy_after_strip` schließt die
  hängenden Satzenden) und daher noch ungemessen.

Protokoll und Bericht liegen im Scratchpad (`B2_run.md`, `B2_decision.md`).

## Bewusste Grenzen / offene Punkte

- ~~Streichungsquote (46,7 % der Zitat-Instanzen im Abnahmelauf)~~ → **M4
  umgesetzt 2026-09-07**: Zitate laufen über Katalog-IDs, URLs stehen nicht
  mehr im Prompt.
- ~~Lücken, die erst das Re-Audit aufwirft, werden nicht mehr gesweept~~ →
  **M6 umgesetzt 2026-09-07**: genau eine Nachrunde, mit eigener Ledger-Zeile
  (`kind: "followup"`).
- ~~Die Quant-Vorstufe misst das Thema (Freitextphrase) — eine Phrase mit
  Füllwörtern schaltet die Messung ab~~ → **M1 umgesetzt 2026-09-07**
  (Kaskade); dass eine eigene `question` die Recherche ändert, nicht die
  Messung, gilt weiter.

- ~~Kein Rechts-/Zulassungsstatus im Dossier~~ → **umgesetzt 2026-09-07**
  (`sweep_regulatory`, Abschnitt „Regulatory and IP status").
- ~~Eine zitierte Zahl kann in der zitierten Seite fehlen~~ → **umgesetzt
  2026-09-07** (`verify_cited_figures` + `drop_unverified`); für
  Korpus-Quellen gilt weiterhin nur der Evidenzblock-Pfad.
- ~~2.563 der 6.775 Wörter waren Suchprotokoll~~ → **umgesetzt 2026-09-07**
  (R6-1): das ausgelieferte Dokument endet an `AUDIT_ANNEX_MARK`; Coverage-
  Ledger, Fetch-Log, Budget-Meldungen und Beleg-Verifikation stehen darunter,
  werden mitgespeichert und im Desk aufklappbar gezeigt.
- ~~Die Messung stand unverbunden neben den Optionen~~ → **umgesetzt
  2026-09-07** (R6-2): jede Option ohne gemessene Zahl ist ein Strukturbefund;
  der Prompt listet die gemessenen Werte wörtlich.
- ~~Die Optionen bedienten nur eines der drei in der Frage genannten Felder~~ →
  **umgesetzt 2026-09-07** (R6-3): `sectors_from_question` liest die Felder aus
  der Frage, `uncovered_sectors` prüft den Optionsabschnitt.
- ~~Eine richtige Zahl in verdrehter Wiedergabe blieb unentdeckt~~ →
  **umgesetzt 2026-09-07** (R6-4): Qualifizierer („at least" → „only"),
  Größenordnung (>25 % vom Quellwert derselben Sache) und Kategoriewort
  (generic/hybrid/biosimilar/originator).
- **Lauf B6 (2026-09-07, `glp1-r6`, dossiers.id=19, 1.272 s).** Ausgeliefert
  5.477 Wörter (R5: 6.773), davon 0 Suchprotokoll (R5: 2.557; jetzt 2.551
  Wörter Prüfanhang). 4 von 4 Optionen tragen eine gemessene Größe (R5: 0 von
  4), die Kurzfassung führt in Satz 1 die gemessene Verbesserungsrate.
  Beleg-Verifikation: 37 Sätze, 10 Befunde vor dem Neuwurf (3 Zahl nicht auf
  der Seite, 5 Gegenstand, 1 quellenlos, **1 verdrehte Größenordnung**), 4
  Sätze danach gestrichen. Offen geblieben: Fließtext 2.901 Wörter (Kappe
  2.800, ein Neuwurf ohne Loop); „health technology" nur nachgesprochen statt
  bedient; die Streichung nahm Option 2 ihren Zeithorizont — beide Löcher sind
  seit `251985b` sichtbar (Prüfung nach der Streichung, Aufzählung zählt nicht
  als Abdeckung). Protokoll: `scratchpad/glp1/B6_run.md`.
- Drei der vier Streichungen in B6 gingen auf **Fehlalarme der
  Gegenstandsprüfung** zurück („Time", „Permitted", „A FoodNavigator" am
  Anfang eines Listenpunkts). Die Regel stammt aus Runde 3; sie kostet hier ein
  Pflichtfeld und ist der nächste Kandidat.
- Die Verdrehungsprüfung braucht **gelesenen** Seitentext. Der zweite
  Faktenfehler des R5-Dossiers („5 Mio. Wegovy-Rezepte") zitierte eine Seite,
  die mit HTTP 403 nie gelesen wurde — mechanisch nicht zu fangen; die Regel
  greift erst, wenn die Seite im Katalog steht. Für den Fall bleibt es beim
  bestehenden Grundsatz: was nicht gelesen wurde, kann kein Zitat tragen.
- Die Beleg-Verifikation greift nur bei Sätzen, die **ausschließlich**
  gefetchte Web-/Rechtsquellen zitieren. Mischt ein Satz Korpus- und
  Web-Beleg, bleibt er ungeprüft — bewusst, sonst würde jede Zahl aus einem
  geöffneten Artikel-Volltext falsch angeschlagen.
- Kein Versions-**Diff** in der Ansicht (nur Versionswechsler) — Kandidat für
  den nächsten Schritt, die Versionierung existiert genau dafür.
- `--retrieval vector` bleibt wie in der Skizze ungetestet; Worker-Default
  ist FTS.
- Die offenen Kanten der Skizze gelten weiter (Web-Treffer ungeranked,
  Patent-Sweep titelbasiert).
