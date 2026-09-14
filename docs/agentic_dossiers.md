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
| Entscheidungsebene | `pipeline/dossier_structure.py` | deterministisch, kein Modell: verbindliche Gliederung (**7 Pflichtabschnitte**, seit R8-1 mit dem Katalysator-Kalender „What happens next"), 200-Woerter-Kappe der Kurzfassung, **Faktenquote** als primaeres Mass (`fact_density` — datierte, primaerbelegte Angaben je 100 Woerter Fliesstext, Untergrenze 2,0; seit R9-3 ist sie der Neuwurf-Grund, die Wortzahl-**Obergrenze** 2.800 bleibt daneben bestehen, die Untergrenze 2.200 ist nur noch Protokollzahl), **Katalysator-Kalender** (`calendar_rows`/`calendar_findings` — mindestens 5 Tabellenzeilen mit Datum im Laufjahr oder spaeter UND Beleg, seit R9-4 zusaetzlich aus mindestens **3 verschiedenen Quellen** und keine davon mit der Mehrheit der Zeilen), **Abdeckung der Innovationskette** (`chain_coverage` — je Ebene Wissenschaft/Patente/Foerderung/Markt eine datierte und belegte Aussage im Fliesstext, Anhaenge zaehlen nicht), **Rangregel fuer Kernaussagen** (`weak_source_claims` — seit R9-1 braucht **jede Aussage** in Kurzfassung, Recht/IP, Kalender und Optionen eine Quelle vom Rang 0/1, nicht nur jede Praezisionszahl; sonst Kennzeichnung „(secondary source only)", in der Kurzfassung Streichung. `weak_source_figures` ist nur noch der Zahlen-Teil davon), Pflichtfelder je Option (Auslöser/Zeithorizont/Aufwand/Risiko/Dagegen spricht) — seit R9-4 gilt ein Feld mit Platzhalter („keine Zahl", „unbekannt", „n/a") als **nicht erfüllt** (`is_placeholder`); erlaubt sind eine belegte Größenordnung oder der Wegfall des Feldes samt belegter Begründung im Optionstext (`_explained_omission`), **Verwendbarkeitsregel gemessener Größen** (`measure_inventory`/`measure_use_findings` — eine gerechnete Zahl darf nur in den Text, wenn sie nicht unter Kalibrierungsvorbehalt steht, im Anhang mit n/Zeitraum/Rechenweg belegt ist und im Dokument genau einen kanonischen Wert hat; eine Option ohne verwendbare Zahl ist zulässig, ohne Zahl UND ohne Beleg nicht), **Branchenabdeckung** (`sectors_from_question` — die Optionen müssen jedes in der Frage genannte Feld bedienen) und die Beleg-Verifikation `verify_cited_figures`: Zahlen eines Satzes gegen den Volltext genau der zitierten Web-Seite, Gegenstand des Satzes (`unverified_subjects`), Präzisionszahlen ohne Beleg (`sourceless_figures`) und **verdrehte Wiedergabe** (`qualifier_conflicts` / `magnitude_conflicts` / `category_conflicts`) und **Zuordnung innerhalb der Quelle** (`context_conflicts` — nennt ein Satz einen Studiennamen, müssen seine Zahlen im Kontextfenster dieser Nennung stehen) und **Reichweite** (R8-3: `artefact_conflicts` — beruft sich ein Satz auf ein Register/eine Datenbank/ein Amtsblatt, muss die zitierte Seite das auch führen; und in `measure_use_findings` die vierte Bedingung: zieht ein Satz einen Schluss aus einer gemessenen Größe, muss er den gemessenen Gegenstand benennen). `split_claims` trennt Sätze nie innerhalb eines Zitat-Links. `revision_prompt` = der EINE Neuwurf, `drop_unverified` = die Streichung danach. `AUDIT_ANNEX_MARK`/`delivered`/`join_document` trennen ausgeliefertes Dokument und Prüfanhang |
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
Report-Prompt (`corpus_research.report_system`) schreibt Pflichtabschnitte
vor — *Decision summary* (max. 200 Wörter, drei belegte Aussagen), *What is
moving*, *Regulatory and IP status*, seit R8-1 *What happens next*, *What the
evidence does not support*, *Options for a mid-sized European company*, *Open
questions and limits* — und ein Längenband von **2.200–2.800 Wörtern
Fließtext** (Anhänge zählen nie mit; gezählt wird ohne Zitatapparat, damit
dieselbe Zahl vor und nach der Kanonisierung gilt). Deutsche Fassung
gleichwertig.

**S2 — Rechts- und Zulassungsstatus.** Der entscheidungstragende Befund des
Siegertexts war ein Rechtsstatus: EU-Grundpatent Semaglutid ausgelaufen, aber
**SPC-Schutz bis März 2031**, gerichtlich durchgesetzt, während Generika in
Indien/Brasilien/China starten. Unser Korpus *zählt* Patente, führt aber keinen
Rechtsstatus, und die allgemeine Web-Stufe verwarf solche Treffer still gegen
die gemeinsame Kappe (der Askea-Fall). `sweep_regulatory()` ist deshalb eine
eigene Suchrichtung: feste Muster (SPC/Patentablauf Europa · EMA · FDA ·
anstehende Entscheidungstermine · Gerichtsentscheidung/Verfügung ·
EFSA-Health-Claim · EU-Regulierung) auf die
messnormalisierte Themenphrase, Treffer **verpflichtend im Volltext gefetcht**
(ein Snippet trägt hier kein Zitat), eigener Katalogbereich `[legal]` mit
reserviertem Budget (`REG_MAX_SOURCES` 27 / `REG_MAX_FETCH` 14, Stand R8-1), das die
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

**Ein gezielter Neuwurf, dann Mechanik — seit 2026-09-12 mit genau einem
Nachzug.** Struktur- und Belegbefunde gehen als *ein* Revisionsauftrag zurück
ans Modell (`revision_prompt`; Evidenzblock nur, wenn ein Befund verlangt zu
ERGÄNZEN). Danach werden verbliebene, nicht gedeckte Sätze
`drop_unverified()`-mechanisch gestrichen. Stehen danach noch
**Strukturbefunde**, folgt ein zweiter Neuwurf nur für diese
(`DOSSIER_REWRITES`, Default 2); senkt er die Zahl nicht, ist Schluss.
**Kein Kritiker-Modell** (Owner 2026-09-06,
`docs/newsletter_agentic_prototype_2026-09-06.md`) — beide Aufträge entstehen
vollständig aus deterministischen Befunden. Siehe Runde 15.

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
Zahl: der Neuwurf, danach `drop_unverified()`.

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

**Web-Cache (seit 2026-09-12, `pipeline/web_cache.py`):** Brave-Treffer (72 h)
und Seitentexte (7 Tage) liegen in `data/web_cache.sqlite`; dieselbe Frage und
dieselbe Seite kosten innerhalb der Frist weder Kontingent noch Abruf — auch
über Läufe hinweg (drei LFP-Läufe am 12.09.: 340 Brave-Aufrufe, 156
verschiedene; das Kontingent war nachmittags erschöpft, 402). Gespeichert
werden nur stabile Ausgänge (Text, robots/TDM, Botsperre, 404/410, zu kurz);
Timeouts, 5xx und 202-Warteseiten werden neu versucht. `result.web.cache`
zählt je Lauf `brave_api`/`brave_cached`/`page_fetch`/`page_cached`.
`WEB_CACHE=0` schaltet ab; `python -m pipeline.web_cache stats|purge|clear`.

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

### Runde 7 (2026-09-07) — die vier Befunde der Jurys 9 und 10

Die neunte und zehnte Bewertung schlossen den Abstand auf 1,0 Punkt (7,6 gegen
8,6). Vier Mängel blieben, alle vier sind hier geschlossen:

- ~~Die Messzahlen tragen nicht, sie schmücken~~ → **R7-1**: Der Nennungszwang
  aus Runde 6 ist ersetzt durch die **Verwendbarkeitsregel**
  (`pipeline/dossier_structure.measure_inventory`). Gesperrt ist, was der
  Anhang als „not reportable" führt (Take-off ohne berichtsfähige Vorlaufzeit
  oder am Rand des Datenfensters), was unter dem Kalibrierungsvorbehalt steht
  (jeder Jahreswert der K(t)-Kurve — genau die 6,1 %/yr der B6-Kurzfassung)
  und was im Anhang ohne n und Zeitraum steht. Je Kennzahl genau ein
  kanonischer Wert; ein zweiter nur in EINEM Satz gegenübergestellt. Verstöße
  laufen durch den bestehenden Kanal (ein Neuwurf, dann Streichung) — in einer
  Optionszeile fällt nur die Teilaussage, damit kein Pflichtfeld verlorengeht.
  Gegenprobe am gespeicherten B6-Dossier: 9 Verstöße, darunter alle vom
  Gutachten benannten.
- ~~Zwei von fünf geprüften Quellen waren Fan-Wikis~~ → **R7-2**: `LOW_TRUST_SOURCES`
  in `scripts/corpus_research.py` — benannte Konstante, jede Zeile mit
  Kategorie und Begründung (Wiki ohne Redaktion, Content-Farm,
  Selbstpublikation, Presse-Wiederveröffentlicher, Forum), dazu zwei Regeln
  statt Namenslisten (Forum-Subdomains, Ein-Wirkstoff-Domains wie
  `retatrutide.med`). Rang 3 kommt an keiner Aufnahmestelle in den Katalog,
  auch nicht über die Rückfallschwelle. Fachjournale steigen auf Rang 1.
  Abgewiesene erscheinen mit Host und Kategorie im Prüfanhang und als Zahl im
  ausgelieferten Prüfnachweis. Bewusst nicht abgewiesen: Wikipedia und
  kommerzielle Marktforschung.
- ~~Falschzuordnung innerhalb einer Quelle (TRIUMPH-4 → TRANSCEND-T2D-2)~~ →
  **R7-3**: `context_conflicts` prüft die Nähe — nennt ein Satz einen
  Studiennamen, müssen seine Zahlen im Umfeld dieser Nennung stehen (±400
  Zeichen), und das über alle zitierten Seiten hinweg. Beim Nachstellen kam der
  eigentliche Grund heraus: der Satz zitierte zwei Quellen der zweiten Welle
  (kind `entity`), und `entity` fehlte in `_VERIFIABLE_KINDS` — die gesamte
  Beleg-Verifikation hat ihn nie gesehen. Jetzt deckt sie am B6-Dokument 36
  statt 33 Sätze ab und meldet den Fund.
- ~~Die eigene Kennzahl ist für Käufer nicht nachprüfbar (403)~~ → **R7-4**:
  Die Crawler-Sperre bleibt; der Messanhang trägt jetzt den **Rechenweg**
  (`measurement_recipe`): je Größe Datenquelle, Auswahlregel samt CPC-Codes und
  Trefferdichte, n, Zeitfenster, Verfahren, Datenstand. Dieselben Felder
  entscheiden über die Verwendbarkeit — ohne n und Zeitraum keine Verwendung.

### Runde 8 (2026-09-07) — die drei Lücken der Jurys 11 und 12

Die elfte und zwölfte Bewertung schlossen den Abstand auf **6 Punkte**
(Jury 12: 51:57, Jury 11: 45:57) und hielten zwei Erfolge ausdrücklich fest:
unsere Messkennzahlen sind „tragend, nicht Dekoration", und die
Entscheidungsoptionen sind mit 4/4 vollständig gegen 0/7 überlegen. Drei
Lücken blieben — die ersten beiden Punktdifferenzen (Abdeckung 6:9, zeitliche
Einordnung 6:9) ergeben zusammen genau den Rückstand:

- ~~Keine zeitliche Einordnung, zu wenig Breite~~ → **R8-1**: siebter
  Pflichtabschnitt **„What happens next"** — eine Tabelle *Datum · Ereignis ·
  Quelle · Bedeutung*, geprüft auf mindestens fünf Zeilen mit Datum (im Jahr
  des Laufs oder später) **und** Beleg (`calendar_rows`/`calendar_findings`).
  Dazu die **Abdeckung je Kette-Ebene**: Wissenschaft, Patente, Förderung und
  Markt brauchen je eine Aussage mit Datum und Zitat *im Fließtext* — der
  codegenerierte Anhang zählt nicht (`chain_coverage`). Und die **Untergrenze
  2.200 Wörter** ist wieder ein Neuwurf-Grund; der Befund nennt den Betrag und
  das erlaubte Füllmaterial („belegte Fakten, keine Prosa"). Damit der Sweep
  überhaupt Termine liefert, fragen Rechts- und Marktsweep seit R8-1 auch
  vorwärts („upcoming regulatory decision expected date", „trial readout
  expected date") — weit vorne in der Musterliste, weil die Volltext-Budgets
  der Reihe nach vergeben werden.
- ~~Kernzahlen hängen an dünnen Quellen~~ → **R8-2**: jede Präzisionszahl in
  Kurzfassung, Optionen und Kalender braucht eine zitierte Quelle vom **Rang
  0/1** (Behörde, Register, Gericht, Firmen-IR/SEC, Fachjournal). Sonst wird
  der Satz mechanisch als „(secondary source only)" gekennzeichnet oder
  gestrichen (`weak_source_figures`, `mark_secondary`). `catalog_rank` gibt
  jedem Katalogeintrag seinen Rang, der Berichtsprompt weist ihn als
  `(primary)` aus. Zusätzlich: eine Seite, die **selbst einräumt**, etwas nicht
  verifiziert zu haben („not been able to verify", „remains unconfirmed"),
  kommt gar nicht erst in den Katalog (`self_unverified`, Fetch-Status
  `self-unverified`, im Prüfnachweis getrennt von Botsperren ausgewiesen).
- ~~Zwei Einzelfehler: Registeraussage ohne Register, Schluss über natürliche
  Modulatoren aus Wirkstoffklassen~~ → **R8-3**: beides ist **Reichweite**.
  `artefact_conflicts` prüft, ob ein formales Nachweisstück (Register,
  Datenbank, Amtsblatt, Docket, Rechtsprechung), auf das sich ein Satz beruft,
  in der zitierten Seite überhaupt vorkommt — Satzseite streng, Seitenseite
  großzügig. Und die Verwendbarkeitsregel hat eine vierte Bedingung: zieht ein
  Satz einen **Schluss** aus einer gemessenen Größe, muss er den gemessenen
  Gegenstand benennen (die aufgelöste Phrase oder eine ihrer CPC-Klassen).
  Gegenprobe am gespeicherten B7-Dokument: genau ein Treffer, und zwar der von
  jury_11 §4.5 wörtlich zitierte Satz.

**Kennzahlen B8 gegen B7** (Lauf `glp1-r8` v2, `dossiers.id=23`, 1.077 s):
Fließtext 1.705 statt 1.621, ausgeliefert 4.609 statt 4.195 Wörter,
Katalysator-Kalender mit 6 datierten und belegten Zeilen statt keinem,
Kettenabdeckung 4/4 mechanisch geprüft, Beleg-Verifikation 26 Sätze / 76
Angaben statt 18 / 52, Befunde nach dem Neuwurf 0 statt 2, mechanisch
gestrichene Sätze 0 statt 2, Kernzahlen ohne Primärbeleg 0 (am B7-Dokument
meldet dieselbe Regel 3), Verstöße gegen die Verwendbarkeits- und
Reichweitenregel 0 (am B7-Dokument 1).

**Der erste R8-Lauf (v1) hat drei Fehler des eigenen Codes aufgedeckt** und ist
an ihnen gescheitert; behoben in `b1edd2d`, jeder mit Test: (a) der
Revisionsauftrag verlangte gleichzeitig „ergänzen" und „keine neuen Fakten" und
führte den Evidenzblock nicht mit — das Modell kürzte folgerichtig (1.511 →
1.335); (b) die Gegenstandsprüfung las „Confirms", „Adds", „Expands Mounjaro's"
am Anfang einer Tabellenzelle als Eigennamen und kostete damit zwei
Pflichtfelder und zwei Kalenderzeilen (die Regel aus Runde 3, seit B6 als
nächster Kandidat notiert — jetzt geschlossen); (c) ein „|" im Quellentitel
zerlegte die Kalenderzeile, in der es stand.

**Offen:** Der Fließtext bleibt mit 1.705 Wörtern 495 unter dem Zielband. Der
eine erlaubte Neuwurf wächst jetzt in die richtige Richtung (+115 statt −176),
holt die Vorgabe aber nicht ein; ein zweiter Durchgang ist bewusst
ausgeschlossen. Zweitens tragen in B8 4 von 4 Optionen **keine** Messgröße
(B7: 2 von 4) — seit R7-1 zulässig, weil alle belegt sind, und die Messung
trägt den ersten Satz der Kurzfassung; jury_12 hat den Messbezug aber
ausdrücklich gelobt, also gehört das beobachtet. Protokoll:
`scratchpad/glp1/B8_run.md`.

### Runde 9 (2026-09-07) — Substanz statt Form (Jurys 13 und 14)

Die dreizehnte und vierzehnte Bewertung gingen wieder an die Web-Recherche
(7,3 zu 8,9 bei jury_14). Der Vorwurf war nicht mehr die Form, sondern der
Inhalt: „Wir gewinnen Struktur und verlieren Substanz." Daraus wurden vier
Maßnahmen (`d2e3a1c`, `0b54bda`, `426a3b2`, `3013b0a`, `41172c7`, `c04db54`):

- **R9-1 Rangregel für jede Aussage**, nicht nur für jede Zahl
  (`weak_source_claims`): Kurzfassung, Recht/IP, Kalender und Optionen
  brauchen eine Quelle vom Rang 0/1, sonst Kennzeichnung „(secondary source
  only)" — in der Kurzfassung Streichung.
- **R9-2 Selbstzitate zählen nicht** (`citable_url`, `catalog_rank`): ein
  Korpus-Artikel wird an seinem **Original** zitiert, die eigene Messung trägt
  gar kein Zitat mehr (Beleg ist ihr Rechenweg im Anhang).
- **R9-3 Faktenquote als primäres Maß** (`fact_density`): datierte,
  primärbelegte Angaben je 100 Wörter Fließtext. Die Wortzahl-Untergrenze ist
  kein Neuwurf-Grund mehr, die Obergrenze bleibt.
- **R9-4** Kalender aus mindestens drei verschiedenen Quellen,
  Platzhalter in Optionsfeldern zählen als unerfüllt.

Ergebnis der beiden R9-Läufe: Faktenquote 0,35 (v1) und 0,25 (v2) — die
Maßnahmen haben die Schwäche **gemessen**, aber nicht behoben.

### Die DR-Runde (2026-09-07) — Arbeitsweise statt Regelwerk

Owner-Auftrag: „Variiere die Modellparameter und den Prompt so, dass qwen eher
arbeitet wie ein Sonnet-Deep-Research-Agent." Ausgangsbefund am Lauf
`dossiers.id=25`: der Katalog trug 17 Patente (Rang 0), 28 Paper (Rang 1) und
11 Behördenseiten (Rang 0) — zitiert wurden davon 6, kein einziges Paper; und
**84 Sweep-Treffer blieben ungelesen** und damit nicht zitierfähig, darunter
pubmed (6×), sec.gov, investor.lilly.com, ema.europa.eu, cms.gov. Es fehlten
nicht die Fakten, es fehlte die Primärquelle unter ihnen.

Drei Änderungen, alle hinter `dr` (Default **aus**; `DOSSIER_DR=1`, `--dr`,
oder `params = {"dr": true}` am Auftragszettel):

1. **`read_primary_first`** — vor dem Schreiben werden bis zu 28 ungelesene
   Treffer **nach Rang** gelesen (0 vor 1, Rang 2 gar nicht). Das Auffangnetz
   je offener Frage steigt von 12/2 auf 20/3.
2. **`harvest_facts`** — eine Extraktion je Primärquelle (Volltext, sonst
   Abstract) liefert datierte Einzelaussagen mit Katalog-ID. Jede Notiz wird
   **deterministisch gegen ihren Quelltext geprüft**: Datum und jede
   Präzisionszahl müssen dort stehen, sonst fällt sie weg
   (`_fact_grounded`). Ergebnis ist das **Faktenbuch**.
3. **Schreiben aus dem Faktenbuch** — es steht im Berichts- *und* im
   Neuwurf-Prompt, dazu eine Arbeitsanweisung („HOW YOU WORK") statt weiterer
   Regeln. Sampling nach Modellkarte (nicht-denkend: temp 0.7, top_p 0.80,
   top_k 20, presence_penalty 1.5) statt reiner Temperatursteuerung;
   `llamacpp_client` reicht die Felder nur durch, wenn sie gesetzt sind.

**Der eine Lauf** (`glp1-dr` v1, `dossiers.id=26`, 1.638 s): 8 von 25
Primärkandidaten gelesen (17 Botsperren), Faktenbuch 21 geprüfte Aussagen aus
6 Quellen, 72 gelesene Seiten. **Faktenquote 0,94 gegen 0,25 (R9 v2)** — der
beste Wert aller vierzehn Läufe; primärbelegte datierte Aussagen 3 → 14,
zitierte Rang-0/1-Quellen 6 → 12. Preis: die Kurzfassung schrumpfte auf **eine**
Aussage (24 Kernaussagen ruhten nur auf Rang-2-Material und wurden nach R9-1
gekennzeichnet bzw. gestrichen), der Kalender trägt nur 3 statt 6 belegte
Zeilen, und der Fließtext liegt mit 2.981 Wörtern 181 über der Obergrenze.
Protokoll und Vergleichstabelle: `scratchpad/glp1/DR_run.md`.

**Nebenbefund zur Messlatte.** `OPPONENT_FACT_DENSITY = 1.83` ist mit dem
ausgelieferten Zähler nicht reproduzierbar: dieselbe Datei (`C_sonnet.md`)
ergibt mit `fact_density(..., rank_of=source_rank)` heute **0,81**. Die 1,83
entstehen nur, wenn jedes Zitat als primär gilt. Die Untergrenze 2,0 ist an
dieser laxeren Messung geeicht — ob sie bleibt, ist eine Owner-Entscheidung.

**Bewertung (jury_15, blind, Zuordnung erst nach dem Urteil aufgelöst).** Das
DR-Dokument gewinnt gegen B9 v2 mit **5,4 zu 4,9**: Belegbarkeit 6:4,
Spezifität 7:6, Handlungsrelevanz 6:4, Struktur 4:3 — verloren geht die
**zeitliche Einordnung 4:6**, genau der gemessene Preis des Kalenders. Der
Gutachter fand im DR-Dokument vier inhaltliche Fehler (ein 2014er Papier als
„(PMC, 2026)", falscher Journalname, TRIUMPH-Daten auf Juni 2026 statt
Dezember 2025 datiert, zwei unbelegte FDA-Daten). **Gegen die Deep-Research-Analyse** (jury_16, dasselbe Dokument, kein zweiter
Lauf) verliert das Dossier weiterhin: **5,57 zu 7,43**. Neu ist die Verteilung
— erstmals gewinnt das Dossier **Handlungsrelevanz 8:6** und **Ehrlichkeit
8:6** („R ist das weitaus bessere Entscheidungsdokument … P enthält im
gesamten Dokument keine einzige Aufwandszahl"), verliert aber
Belegbarkeit 4:7, Zeitachse 3:8, Abdeckung 5:9 und Struktur 5:7. Die vier
Gründe sind benannt und adressierbar: (a) vier Sachfehler, drei davon ohne
jede Quelle — ein unbelegter Satz **ohne** Präzisionszahl läuft durch alle
Gates, weil die Grounding-Prüfung an Zahlen greift, nicht an Behauptungen;
(b) nur drei Termine auf zwei Quellen, der einzige harte liegt 2031;
(c) Förderung fehlt („3/4 chain levels" im eigenen Prüfanhang), obwohl die
eigene Korpustabelle 96 Förder-Signale zählt; (d) die Kurzfassung ist ein
einziger Satz, der zehn Zeilen später wortgleich wiederholt wird.

### Runde 10 (2026-09-07) — die zwei Codefehler aus jury_16

Zwei der vier Vorwürfe waren keine Modellschwäche, sondern Lücken im eigenen
Prüfwerk. Beide sind geschlossen und **an den fünf gespeicherten Dokumenten
gegengeprüft** (kein neuer Lauf — der Owner hat genau einen freigegeben):

- **R10-1 — datierte Aussage ohne jeden Beleg** (`weak_source_claims`, Art
  `uncited`). „In the US, FDA approved oral semaglutide in February 2026"
  enthält keine Präzisionszahl, also griff `sourceless_figures` nicht, und ohne
  Zitat lief auch die Rangregel ins Leere: der Satz stand ungeprüft im
  Dokument. Jetzt ist ein Datum in Kurzfassung, Recht/IP oder Kalender ohne
  Beleg ein Befund — ein Neuwurf-Auftrag, danach Streichung. **Nicht** im
  Optionsabschnitt: der ist unsere Argumentation, keine Weltbeschreibung; und
  nicht auf den Planfeldern „Time horizon"/„Effort", die sagen, was *wir*
  vorschlagen. Gegenprobe: DR-Dokument 3 Treffer (darunter genau der von
  jury_16 gerügte Satz), B9 v2 / B8 v2 / B7 v2 je 0.
- **R10-2 — die Kurzfassung darf kein Stumpf sein** (`summary_findings`).
  Geprüft wurde bisher nur nach oben (200 Wörter). Jetzt sind eine Kurzfassung
  mit weniger als zwei Aussagen und eine wortgleiche Wiederholung im
  Fließtext Befunde. Gegenprobe: DR-Dokument 2 (ein Satz, der zehn Zeilen
  später erneut steht), B9 v2 1 (leere Kurzfassung — jury_15: „vollständig
  leer"), B8/B7 0.

- **R10-3 — die Streichung zerreißt die Tabelle nicht mehr** (`_mend_tables`).
  Eine gelöschte Kalenderzeile ließ ihre Leerzeile stehen, und Markdown machte
  daraus zwei Tabellen — die zweite ohne Kopfzeile (jury_16 wörtlich). Die
  Leerzeile wird jetzt geschlossen, wenn danach eine Datenzeile folgt und keine
  neue Tabelle beginnt (Kopf- plus Trennzeile). Gegenprobe am gespeicherten
  DR-Dokument: der Bruch ist weg, zwei echte Tabellen bleiben zwei.

Dazu die Ehrlichkeit im Prüfnachweis: eine gestrichene unbelegte Aussage wird
eigens ausgewiesen und nicht mehr unter „die zitierte Seite enthielt die Zahl
nicht" verbucht (`uncited_before`/`uncited_after`).

- **R10-4 — die Förderebene bekommt eine eigene Suchrichtung**
  (`sweep_funding`, Art `funding`, Präfix `F`). jury_16 zur Abdeckung (5:9):
  „Förderung praktisch abwesend … die eigene Korpustabelle weist 96
  Funding-Signale aus, die nicht verwendet werden." Der Grund war Bauart: es
  gab feste Muster für Recht und für Markt, aber keine für Förderung, und ein
  Audit über einem technologielastigen Korpus benennt keine Ausschreibung als
  Lücke. Sieben Muster, eigenes Budget (20 Quellen / 8 Volltexte), **öffentliche
  Programme zuerst** (Horizon Europe, EIC, nationale Programme — was ein
  Mittelständler beantragen kann), private Runden danach; Protokoll geht als
  `<untrusted_funding_record>` in den Berichts-Prompt. Ungelesene Treffer sind
  wie bei Recht und Markt nicht zitierfähig. Desk und `lib/dossiers.ts` kennen
  die Art (dabei fiel auf: `entity` wurde seit der zweiten Welle gezählt, aber
  nie angezeigt — mitgefixt).

**Was der Kalender braucht, ist damit NICHT erledigt:** die drei Termine gegen
acht sind eine Frage der Terminausbeute, nicht der Prüfregeln. Ob R10-4 und die
Vorwärtsmuster genügen, zeigt erst der nächste Lauf.

**Wichtig zur Geltung:** R10-1 bis R10-3 sind an den gespeicherten Dokumenten
gegengeprüft, R10-4 nur in Tests — seine Wirkung auf ein echtes Dossier ist
ungemessen, weil der Owner genau einen Lauf freigegeben hat.

**Offen aus dem Lauf selbst:** der Rang-0-Vorlauf des Faktenbuchs besteht
überwiegend aus **Patenten ohne Abstract** (ihr Snippet ist ein Ein-Zeiler);
sie verbrauchen die Kappe von 30 Quellen, bevor die Paper mit echtem Abstract
an die Reihe kommen. Wer die Runde fortsetzt, sortiert dort zuerst.

### Runde 11 (2026-09-07) — Denken nach Modellkarte, zweiter DR-Lauf

Owner-Freigabe für einen weiteren Lauf, ausdrücklich auch mit variiertem
Reasoning. Modellkarte (huggingface.co/Qwen/Qwen3.8-27B): Denken ist der
Default, `reasoning_effort` low/medium/xhigh, und je Modus ein eigener
Sampling-Satz (denkend temp 1.0 / top_p 0.95 / top_k 20 / presence 0).

- **Serverschalter ohne Verhaltensänderung.** `start-qwen3.8-27b.sh` liest
  `LLAMA_REASONING` (Default `off`) und `LLAMA_REASONING_EFFORT`; die Unit
  `llama-server.service` hat eine **optionale** `EnvironmentFile`
  (`~/.config/catandary/llama-server.env`). Ohne die Datei läuft alles wie
  bisher — Draft-Richter und Dossier-Worker bleiben unberührt. `DOSSIER_DR_THINK=1`
  sagt dem Lauf, dass der Server denkt; dann gilt für die Prosa der denkende
  Sampling-Satz. Schema-gebundene Aufrufe bleiben immer undenkend
  (`enable_thinking=false`) — am Server verifiziert.
- **Zwei Fehler, die erst der Denk-Lauf zeigte.** (a) Der Berichtsaufruf
  überschritt mit Denkspur die 600 s aus `LLAMACPP_TIMEOUT`; der ganze Lauf war
  verloren. Im Denkmodus hebt der Lauf die Grenze jetzt selbst auf 2.400 s
  (`DOSSIER_DR_TIMEOUT`). (b) Ist das Denk-Budget aufgebraucht, schließt
  llama.cpp die Denkmarke und das Modell **überlegt im Antwortfeld weiter** —
  51 Zeilen Selbstgespräch standen vor der Kurzfassung. `strip_preamble()`
  schneidet alles vor der ersten Pflichtüberschrift weg (R11-1).

**Ergebnis** (`glp1-dr2`, `dossiers.id=27`, 2.638 s): Faktenquote **4,15** je
100 Wörter (DR 1: 0,94, R9 v2: 0,25; Vergleichstext 0,81), primärbelegte
datierte Aussagen 34 statt 14, zitierte Rang-0/1-Quellen 28 statt 12, 14
Förderquellen im Katalog. **jury_17 (blind): Deep Research 6,9 gegen 5,7** —
Abstand von 1,86 auf 1,2 gesunken; Ehrlichkeit (8:6) und Struktur (7:6)
erstmals bei uns, verloren an Zeitachse (3:7), Spezifität (5:8) und
Abdeckung (5:8).

**Der teuerste Befund richtet sich gegen das eigene Regelwerk:** die Rangregel
drängte die tragende Europa-These (EU-Generika nicht vor 2031) als
„unsupported by primary evidence" aus dem Text — obwohl sie über die
niederländische SPC und das Haager Urteil primär belegbar gewesen wäre. Dazu:
der Kalender bestand aus Horizon-Europe-Programmjahren statt GLP-1-Terminen,
und der erste Satz las eine Studienpublikation als Zulassung.

**Was das über die Faktenquote sagt.** Sie stieg um das Vierfache, während die
Jury Spezifität senkte. Der Zähler misst *datierte, primärbelegte Angaben je
100 Wörter* — nicht, **worüber** sie gehen. Ein Text voller Verfahrensdaten
erreicht ihn und verfehlt die Frage. Gute Wächterin gegen Prosa, schlechter
Kompass für Relevanz. Protokoll: `scratchpad/glp1/DR2_run.md`.

### Runde 12 (2026-09-07) — die zwei Befunde aus jury_17, die Regeln sind

Ohne neuen Lauf, beide an den gespeicherten Dokumenten gegengeprüft:

- **R12-1 — zwei unabhängige Sekundärquellen tragen eine Kernaussage.**
  jury_17 wörtlich: „Ein Entscheidungspapier, dessen Regelwerk eine wahre und
  tragende Tatsache aus dem Text drängt, hat den Regelapparat über den Zweck
  gestellt." Genau das tat R9-1 mit der Europa-These (EU-Generika nicht vor
  2031): nur sekundär belegt, also in der Kurzfassung gestrichen — obwohl wahr
  und tragend. Jetzt trägt eine Aussage, die auf **zwei verschiedenen Hosts**
  ruht, auch die Kurzfassung — mit „(secondary source only)". Eine einzelne
  schwache Quelle tut es weiterhin nicht; das war der Befund aus jury_13, und
  er bleibt gültig.
- **R12-2 — eine Kalenderzeile muss vom Thema handeln.** jury_17: „drei
  themenfremde Horizon-Europe-Jahreszahlen", „der Kalender enthält keinen
  einzigen GLP-1-Termin". Datum und Beleg hatten diese Zeilen; sie handelten
  von der Laufzeit eines Förderprogramms. Eine Zeile zählt jetzt nur zu den
  fünf, wenn sie ein Themenwort trägt (Themenanker plus die Akteure und
  Wirkstoffe, die der Lauf selbst gefunden hat); sonst steht sie als
  „datiert und belegt, aber nicht zum Thema" im Befund. Ohne Themenwörter ist
  die Regel aus (Firmen-Dossiers).

Gegenprobe: DR 2 → 0 gültige, **3 themenfremde** Zeilen (genau die gerügten);
DR 1 → 3 gültige, 0 themenfremde; B8 v2 → 6 gültige, 0 themenfremde. Keine
Fehlalarme an den bisher besten Kalendern.

**Nicht behoben** (Modell, nicht Regel): der erste Satz des DR-2-Dokuments las
eine Studienpublikation als Zulassung. Ein semantischer Fehlgriff, den kein
Zahlen- oder Ranggate fängt.


### Runde 13 (2026-09-07) — die drei Kriterien, die den Abstand tragen

`jury_17` verlor 5,7 zu 6,9, und der Abstand steckt fast vollständig in drei
Kriterien: **Zeitliche Einordnung 3:7, Spezifität 5:8, Abdeckung 5:8**
(Ehrlichkeit 8:6 und Struktur 7:6 gingen an uns). Der Lauf sagt, warum — nicht
der Schreiber hat versagt, sondern die Beschaffung:

| Befund im Lauf `glp1-dr2` | Folge im Gutachten |
|---|---|
| Entitäten aus dem Korpuskatalog: `polypeptide, orforglipron, nonpeptide, Eli Lilly, Lilly, METHODS, Obesity, Novo` | 16 von 61 Websuchen an Scheinentitäten (`Phase phase 3 trial results`, `polypeptide court ruling generic`); `polypeptide` nahm `tirzepatide` den Platz in der zweiten Welle |
| Kein Sweep fragt nach **Terminen**, nur nach Zuständen und Vergangenem | Kalender: 3 Zeilen, alle Horizon Europe, alle aus einer Quelle, keine mit Themenbezug |
| Kein Wirkstoff der laufenden Generation im Text | „Kein einziger Wirkstoff außer orforglipron/Semaglutid, keine Studienzahl, kein Deal-Betrag" |
| Aufwand dreimal als ganzer Satz verweigert („cannot be sized from this evidence") | „Eine Geschäftsführung, die budgetieren muss, bekommt keine einzige Größenordnung" |

Sechs Regeln, alle deterministisch, alle mit Test:

- **R13-1 Entitäten-Hygiene** (`_is_substance`, `_ENTITY_STOP_SOLO`,
  `_prefer_longest`, `ENTITY_TEXT_CHARS`). Stoffklassen sind keine Wirkstoffe
  (`-peptide`, `-nucleotide`, `-saccharide` und eine benannte Liste fliegen
  raus); Abschnittsmarken aus Abstracts (`METHODS`, `RESULTS`) und generische
  Einzelwörter (`Obesity`, `Phase`, `European`) zählen nicht als Akteur, als
  Teil eines Mehrworts aber schon (`European Commission` bleibt); der volle
  Name schlägt die Kurzform, wenn er in mindestens der Hälfte derselben
  Dokumente steht (`Novo Nordisk` statt `Novo`). Und geerntet wird jetzt auch
  aus dem **Volltext** der gelesenen Seiten — die laufende Wirkstoffgeneration
  (CagriSema, retatrutide, survodutide) steht nicht in unseren Korpustiteln.
- **R13-2 Katalysator-Sweep** (`sweep_catalysts`, dritte Welle nach der
  Entitäten-Ernte). Drei Themenmuster plus vier je Akteur, die *nur* nach
  Terminen fragen (`topline results expected date`, `FDA decision PDUFA date`,
  `EMA CHMP opinion expected`). Eigenes Budget (26 Quellen / 12 Volltexte),
  eigenes Suchprotokoll im Report-Prompt.
- **R13-3 Kalender-Kandidaten** (`calendar_candidates`,
  `calendar_candidate_block`). Die Zeilen werden dem Bericht **vorgelegt**
  statt von ihm erinnert — dieselbe Bauweise, die den Rechtsabschnitt
  gerettet hat. Ein Satz kommt mit, wenn er ein Datum in der Zukunft trägt
  (`Q4 2026`, `2026 H2`, `19 March 2031`, `H2 2027`), ein Vorwärtswort und
  einen Themenbezug; URLs werden vorher entfernt (eine Jahreszahl in
  `…/glp1-regulation-2026` ist kein Termin), und je Quelle zählen höchstens
  vier Zeilen — ein Kalender aus einer Seite ist diese Seite.
- **R13-4 Aufwands-Anker** (`effort_anchors`, `_UNSIZED_RE`, zwei neue
  Förder- und ein Verfahrensmuster). Übertragbar ist, was ein Mittelständler
  selbst beantragen oder durchlaufen kann: Förderbetrag, Programmbudget,
  Verfahrensdauer — gezogen aus Förder-, Rechts- und Katalysatorseiten, nicht
  aus Pharma-Deals. Und ein ganzer Satz, der sagt, der Aufwand lasse sich
  nicht beziffern, gilt jetzt als Platzhalter; der Ausweg steht nur noch
  offen, wenn die Ankerliste leer ist.
- **R13-6 Zitatreste heilen** (`_mend_inline`). `**Trigger: ** Regulation,
  EC) 1924/2006 …` entsteht beim Streichen eines Markdown-Links. Repariert
  wird nur das mechanisch Eindeutige: verwaiste Klammern, leere Klammerpaare,
  Leerzeichen vor dem Fettdruck-Ende. Ein verstümmelter Satz bleibt
  verstümmelt — ihn zu raten wäre schlimmer.
- **R13-8 Modellparameter.** `presence_penalty` 1.5 → **0.5**: die 1.5 der
  Modellkarte sind für Chat gedacht und besteuern jedes schon verwendete
  Token — in einem Entscheidungspapier also den Wirkstoff in Kalender *und*
  Option, die Katalog-Id hinter drei Sätzen, das Jahr in fünf Kalenderzeilen.
  Und der Berichts- wie der Revisionsaufruf setzen `enable_thinking: false`
  je Anfrage: der Denk-Versuch aus Runde 11 hat das Denken ausschließlich in
  den *Schreibschritt* gelegt — die einzige Stelle, für die die Modellkarte
  den nicht-denkenden Satz vorschreibt —, und dort eine abgeschnittene
  Denkspur in den Berichtstext gespült.

Dazu drei Prompt-Schärfungen in beiden Gliederungen: „Was sich bewegt" verlangt
**mindestens fünf benannte Akteure** mit je einer Zahl oder einem Datum;
„Was die Belege nicht hergeben" verlangt einen Blick in die Suchprotokolle,
bevor eine Behauptung dort landet (jury_17: „Ein Entscheidungspapier, dessen
Regelwerk eine wahre und tragende Tatsache aus dem Text drängt, hat den
Regelapparat über den Zweck gestellt"); und die Faktenquote steht ausdrücklich
als **Untergrenze, nicht als Ziel** — „a review was published in 2024 [[id]]"
zählt für die Quote und sonst für nichts.

Belegt: `tests/test_dossier_dr_mode.py` (Klassen `TestR13*`), 1.388 pytest grün.
Live-Stichprobe der Kandidatenernte am 2026-09-07 über zwei echte
Katalysator-Anfragen: `H2 2026 · CagriSema FDA decision`, `2026 · Metsera
Phase-3-Programm, zehn Studien` — genau die Zeilen, die dem Kalender fehlten.

#### Ergebnis Runde 13 — Lauf `glp1-dr3` (#28), Blindgutachten jury_18

**Deep Research 6,3 · DR3 5,9 · Sieger Deep Research.** Abstand 1,2 → 0,4
(anderer Gutachter als jury_17; der Sonnet-Text fiel dort von 6,9 auf 6,3 —
Gutachterstreuung ist Teil des Abstands). Laufzeit 27 min, 87 Websuchen, **0**
davon an Scheinentitäten (DR2: 16 von 61), Faktenzettel 48 Fakten aus 18
Quellen (DR2: 29/12), 28 Kalender-Kandidaten aus 21 Quellen vorgelegt.

| Kriterium | DR2 : Sonnet (jury_17) | **DR3** : Sonnet (jury_18) |
|---|---|---|
| Belegbarkeit | 6 : 6 | **7** : 5 |
| Spezifität | 5 : 8 | 5 : 8 |
| Handlungsrelevanz | 6 : 7 | **6** : 5 |
| Abdeckung | 5 : 8 | 5 : 8 |
| Zeitliche Einordnung | 3 : 7 | **5** : 6 |
| Ehrlichkeit | 8 : 6 | **8** : 5 |
| Struktur | 7 : 6 | 5 : 7 |

Was gewirkt hat: der Kalender trägt sechs GLP-1-Termine auf vier Quellen
(CagriSema-FDA H2 2026, Retatrutid-BLA Q1 2027, Wegovy-Pille ex-US …) statt
drei Horizon-Jahreszahlen — Zeit 3 → 5; Belegbarkeit 6 → 7 („3 bestätigt,
davon EMA-Primärdokument wörtlich"); Handlungsrelevanz jetzt vor dem
Deep-Research-Text (5 Felder, Claims-Regime, EIC-Förderung).

Was nicht gewirkt hat, und warum — das Resümee nach drei DR-Läufen:

1. **Spezifität und Abdeckung bleiben 5 : 8.** Der Gutachter: „die Landkarte
   ist schmal (keine Mover außer Lilly/Novo/Catalent, Pipeline fehlt)". Der
   Lauf hatte 23 Akteure geerntet und nach Retatrutid, Orforglipron,
   Tirzepatid gesucht — der *Bericht* nennt sie kaum. Das ist derselbe
   Mechanismus wie beim Kalender vor R13-3: was dem Schreibaufruf nicht als
   fertige Zeile vorliegt, verschwindet in 80k Token Belegen. Der
   Deep-Research-Text gewinnt genau dort mit zwölf Wirkstoffen samt Phase,
   Endpunkt und Zahl.
2. **Die mechanische Streichung kostet Struktur** (7 → 5). 36 gestrichene
   Sätze hinterließen „fünf beschädigte Stellen" — Satzbruchstücke wie
   „calcium (863 mg vs. 8–18 mg)", „Named actors and figures: in H2 2026",
   verwaiste Absätze. Der Gutachter: „so nicht vorlegbar". Die
   Streichung arbeitet auf Satzmitte und kennt keinen Absatzzusammenhang.
3. **Aufwand: Förderobergrenze ist kein Kostenmaßstab.** Der Gutachter zählt
   1/3 statt 3/3 — „€1–3 million … anchored to the EIC grant ceiling" ist
   hergeleitet, nicht belegt. Die Aufwands-Anker liefern, was Förderseiten
   hergeben; Kostenvergleiche (Projektbudgets geförderter Konsortien,
   Dossierkosten) müssten eigens gesucht werden.
4. **Zwei Kalenderzeilen waren am Prüfdatum vergangen** (31.08.2026,
   Q3 2026): `_when_label` verglich nur das Jahr. Behoben
   (`_label_passed` rechnet Tag/Monat/Quartal/Halbjahr gegen den Stichtag;
   `CAL_MAX_PER_SOURCE` 4 → 2, weil drei Zeilen aus einem Aggregator kamen).
   Nicht erneut gelaufen.

Der Trend über die DR-Läufe: 5,57 → 5,7 → 5,9 gegen 7,43 → 6,9 → 6,3. Jede
Runde hat die benannten Kriterien gedreht und die nächsten freigelegt. Der
Rest des Abstands ist kein Regelproblem mehr, sondern zwei Bauartfragen —
die Landkarte des Feldes muss dem Schreibaufruf so vorgelegt werden wie der
Kalender (Akteur × jüngstes Ergebnis × Datum × Quelle, deterministisch), und
die Streichung muss auf Absatzebene arbeiten statt Sätze zu zerschneiden.
**Pausiert nach Owner-Vorgabe; kein weiterer Lauf ohne Freigabe.** Protokoll
`scratchpad/glp1/DR3_run.md`, Gutachten `scratchpad/glp1/jury_18.md`,
jury-nahe Messung `scratchpad/glp1/jury_metrics.py`.

> **Status 2026-09-07:** Der DR-Modus ist als **Feature in Development** nach
> `main` gemergt. Das Ziel „besser als Sonnet Deep Research" ist nicht erreicht
> und vom Owner so abgenommen; Standsdoku und Wiederaufnahme in
> `docs/dossier_vs_deep_research_2026-09-07.md`, Issue #100.

### Runde 14 (2026-09-07) — Landkarte, Absatz-Streichung, Themenneutralität

Owner-Freigabe nach jury_18 mit drei Bedingungen: (1) Feldlandkarte und
Streichung auf Absatzebene, (2) Dossiers themenagnostisch mit ähnlicher
Qualität über alle Themen, (3) vorher auf GitHub veröffentlichte
Deep-Research-Harnesses (wissenschaftlich/technologisch) auf passende
Workflows sichten (`scratchpad/glp1/harness_survey.md`).

- **R14-1 Akteur-Landkarte** (`actor_map`, `actor_map_block`;
  `dossier_structure.actor_rows`/`actor_findings`). Je geerntetem Akteur die
  jüngste belegte Aussage mit Zahl oder Datum — Faktenzettel zuerst, sonst ein
  Satz aus einer gelesenen Seite — als Liste vorgelegt. „Was sich bewegt"
  beginnt jetzt mit der Tabelle `| Actor | What happened | Date | Source |`
  (≥ 5 Zeilen, ≥ 3 Quellen, Themenbezug), mechanisch gezählt wie der
  Kalender. Dieselbe Bauweise, die die Zeitliche Einordnung von 3 auf 5 hob:
  was dem Schreibaufruf nicht als fertige Zeile vorliegt, geht in 80k Token
  Belegen unter.
- **R14-2 Streichung auf Absatzebene.** (a) Abkürzungsfester Satzsplit
  (`split_sentences`, `_ABBREV_END`: vs., e.g., Fig., Dr., U.S. …) — das
  Bruchstück „DRI 25–38 g/day; calcium (863 mg vs. …)" entstand am Split hinter
  „vs.", „in H2 2026 [link]." am Split hinter „U.S.". (b) `_mend_paragraphs`
  nach der Streichung: verwaiste Anschlüsse („These are not directly
  comparable"), nackte Etiketten („**Named actors and figures:**") und
  Restabsätze unter acht Wörtern fallen mit. (c) Ein Pflichtfeld ohne Kopfsatz
  („**Risk: Spanning …") fällt ganz statt als Torso; reparierbare Bindewörter
  (and/but/which) bleiben der bestehenden Reparatur überlassen. (d)
  `fragment_findings` als Strukturbefund vor dem Neuwurf: Etikett ohne Inhalt,
  hängender Doppelpunkt, Absatz mit Anschlusswort ohne Bezug, Absatz mit
  kleiner Präposition am Anfang. Bewusst **kein** allgemeiner
  Kleinbuchstaben-Test — „eMed", „mRNA", „iPhone" beginnen Sätze legitim.
- **Harness-Sichtung** (Bedingung 3, `scratchpad/glp1/harness_survey.md`, 8 Repos
  im Detail: STORM/Co-STORM, PaperQA2, open_deep_research, GPT-Researcher,
  DeerFlow, Tongyi DeepResearch/WebWeaver, AI-Scientist, dzhng). Übernommen:
  **M1/M3/M8** Suchrichtungen je Gliederungsabschnitt mit Stoppregeln →
  Themenprofil; **M5** Fundzeilen mit Akteur/Zahl/Datum sofort geprüft →
  `LedgerFact.actor`; **M4** Evidenzbank statt Rohdump (WebWeaver) →
  `DR_REPORT_EVIDENCE_CHARS` 40k hinter Faktenzettel, Landkarte, Kalender,
  Ankern; **M7** Kritik→Revision statt Streichung (STORM PolishPage) →
  `repair_sentences`. **Nicht übernommen:** Tool-Calling-Graphen,
  RL-trainierte Modelle, Vektorstore-Pflicht, Cloud-Bindungen, STORMs
  generierte Outline (unsere Gliederung ist fix).
- **R14-3 Themenneutralität** (`TopicProfile`, `topic_profile`,
  `profile_queries`, `VERTICAL_SETS`, `verticals_of_topic`). Die festen
  Pharma-Muster bleiben als Fallback; im Normalfall setzt sich jede
  Suchrichtung aus drei Schichten zusammen: ein **themenunabhängiger Kern**
  (Patentablauf, Gericht, Quartalszahlen, Übernahme, Förderung), ein
  **kuratiertes Rückgrat je Vertikale** (Regulatoren/Instrumente und
  Ereignistypen für alle acht Catandary-Vertikalen; die Vertikale kommt
  deterministisch aus der Mehrheit der `vertical`-Felder der nächsten
  Korpus-Treffer plus Stichwort-Votum — bei Abweichung beide Rückgrate) und
  ein **Modellprofil** (ein schema-gebundener Aufruf: Regulatoren,
  Ereignistypen, Rechts-/Marktfragen, Perspektiven, Akteur-Saatgut; alles
  gefiltert — Verweigerungen, Kategorielabels, Echo der Leitfrage; ein
  Ereignis muss ein Ereignis-Wort tragen). Saatgut und Perspektivfragen sind
  Suchbegriffe, nie Fakten. **Befund der 27B-Proben** (drei Themen, vier
  Durchläufe): mit Korpus-Schlagzeilen im Prompt übernahm das Modell deren
  Signal-Sprache als Feldstruktur („CES" als Regulator, „capital_injection"
  als Ereignis) und riet die Vertikale falsch (GLP-1 → BIZ) — STORMs
  Nachbar-Muster überträgt sich mit Schlagzeilen nicht; deshalb Nachbarn nur
  für die Vertikale, Feldwissen aus dem Modell, Rückgrat aus der Kuration.
  Probe `scripts/dossier_topic_probe.py`. Ein voller Lauf zu einem
  Nicht-Pharma-Thema steht noch aus (Owner-Freigabe für genau einen Lauf,
  Testthema GLP-1).
- **R14-4 Reparatur vor Streichung** (`repair_sentences`, `DR_REPAIR_MAX` 20).
  Jeder Satz mit ungestützter Zahl wird dem Modell mit der Liste der
  Angaben und dem Auszug der zitierten Seite vorgelegt und ohne sie neu
  geschrieben; die Zitatmarker müssen bleiben, die Angabe darf nicht
  wiederkommen, `DROP` überlässt ihn der mechanischen Streichung.

Belegt: `tests/test_dossier_dr_mode.py` (`TestR14*`), 1.445 pytest grün.

#### Ergebnis Runde 14 — Lauf `glp1-dr4` (#29), Blindgutachten jury_19

**Deep Research 6,9 · DR4 5,7 · Sieger Deep Research** — schlechter als DR3
(5,9 : 6,3). Laufzeit 28 min, 12 statt 36 gestrichene Sätze, 2 reparierte,
Struktur 6 (zwei Tabellen, Felder), Ehrlichkeit 8, Primäranteil 50 % vs.
30 %; aber Spezifität 5 : 9, Abdeckung 5 : 9, Zeit 4 : 7. Der Bericht war mit
1.911 Wörtern Fließtext und 15 Zahlensätzen (DR3: 28) der kürzeste und
zahlenärmste der Reihe.

Was der Gutachter fand, und was es im Code bedeutet:

| Befund jury_19 | Ursache | Stand |
|---|---|---|
| Erster Entscheidungssatz: 21 Monate alte FDA-Generika-Zulassung als „today" | `harvest_facts` nahm das relative Datum der Pressemitteilung; die Landkarte („jüngste Aussage je Akteur") zog Pressemeldungs-Trivia vor Studienzahlen | relative Daten verworfen (`d90f5a7`); Substanzfilter für die Landkarte offen |
| Kalender: Indien/China-Ablauf (März 2026) als „2026", Jardiance (SGLT2), Retatrutid doppelt | nackte Jahreszahl des laufenden Jahres gilt als offen; Themenbezug stand in der Begründungsspalte; keine Dublettenprüfung über Zeilen | Themenbezug im Ereignis (`69b0927`); Jahr-ohne-Monat im laufenden Jahr und Dubletten offen |
| Aufwand 0/4: Lactalis-Kaufpreis, eMed-Runde, „a fraction of that" | die Anker liefern Förderobergrenzen und Deals — es gibt keine Suchrichtung nach **Kosten** (Rezeptur, EFSA-Dossier, Linie) | offen: Kosten-Sweep |
| Option 3 EIC für > 250 MA nicht antragsfähig; Option 4 Rx-Werbeverbot | kein Rechtswissen im Optionsschritt; das Rückgrat kennt Instrumente, nicht deren Anwendungsbereich | offen |
| Wissenschaft ohne Wirkstoffzahlen trotz acht Wirkstoffen in der zweiten Welle | der Schreibaufruf bekam mehr Banken und weniger Rohtext (M4-light, 40k statt 78k) und wurde **kürzer und zahlenärmer**, nicht dichter | M4 in der Ein-Aufruf-Form hat sich nicht bewährt |

**Resümee nach vier DR-Läufen** (5,4 · 5,57 · 5,7 · 5,9 · 5,7 gegen 4,9 ·
7,43 · 6,9 · 6,3 · 6,9 — Gutachterstreuung beim Sonnet-Text ±0,6): Die
Runden haben Belegbarkeit, Ehrlichkeit, Struktur und Handlungsrelevanz
verlässlich auf oder über das Niveau des Deep-Research-Texts gebracht; die
drei Kriterien, die den Abstand tragen — Spezifität, Abdeckung, Zeit — sind
in vier Läufen nicht über 5/5/5 hinausgekommen, obwohl die Beschaffung seit
DR3 liefert (49 geprüfte Fakten, 28 Kalender-Kandidaten, acht Wirkstoffe).
Der Engpass ist damit der **Schreibschritt**: ein einzelner Aufruf des
4-Bit-27B macht aus fünfzig vorgelegten Fakten keinen dichten, zahlenreichen
Text — je mehr vorgelegt wird, desto knapper wird er. Die Harness-Sichtung
nennt den Ausweg (WebWeaver M4, Co-STORM): **kapitelweises Schreiben** mit je
eigener Evidenzbank und Wortbudget statt eines Aufrufs über alles. Das ist
ein Umbau des Schreibers, kein weiteres Regelwerk — und nicht Teil dieser
Freigabe. **Pausiert; kein weiterer Lauf ohne Owner-Wort.**

Themenneutralität (Bedingung 2): Mechanik gebaut und auf drei Themen geprobt
(Kern + Rückgrat je Vertikale + Modellprofil; Probe-Skript); „ähnlich gute
Dossiers über alle Themen" ist damit **nicht belegt** — dafür fehlt ein voller
Lauf zu einem Nicht-Pharma-Thema.

### Runde 15 (2026-09-12) — LFP-Serie: der Harness gegen ein Nicht-Pharma-Thema

Erster voller Lauf zu einem Nicht-Pharma-Thema (Serie `iron-phosphate-battery`,
v1–v8 an einem Tag, Owner-Ziel: eine veröffentlichungsfähige Analyse für #93).
Was sich dabei als Harness-Fehler zeigte und geändert wurde
(`b0a394d`, `ac4cc77`, `c5c6d6a`, `63a92e9`, `17f176e`):

| Befund | Lauf | Änderung |
|---|---|---|
| Streichung leerte die Kurzfassung (BNEF-Preise = Rang 2) | v3 | Datenhäuser mit eigener Erhebung (BNEF, Benchmark, WoodMac, Rystad, Ember) = **Rang 1**; die letzte Aussage der Kurzfassung wird **markiert statt gestrichen** |
| „tail without its head" für „In Europe …", „On 30 July 2025 …" | v3 | nur Bindewörter sind immer ein Schwanz; Präposition nur bei kleinem Anfang |
| `ok=False` an 7 ehrlich markierten Rang-2-Sätzen | v4 | **`ok` beschreibt das ausgelieferte Dokument** (unbelegt, gestrichen, Gliederung); die Nacharbeit steht als Befundzeile |
| Effort-Platzhalter + 3/5-Kalender blieben nach dem einen Neuwurf | v4 | zweiter Neuwurf nur für Strukturbefunde (`DOSSIER_REWRITES=2`) |
| Faktenquote im Erstentwurf 2,37 (v4) gegen 1,23 (v5) bei identischem Auftrag | v5 | **Best-of-2** (`DOSSIER_DRAFTS`), deterministisch bewertet (`draft_score`) |
| 6–8 „gestrichene Zitate": ids ungelesener Treffer aus dem Evidenzblock | v5/v6 | Vermerk „NOT citable" in den Notizen; **zitatgetriebener Abruf** (`_adopt_cited_unfetched`): zitierte ungelesene Seite jetzt holen, sonst Marker VOR der Prüfung weg |
| 340 Brave-Aufrufe für 156 Fragen über drei Läufe, Kontingent erschöpft | v2 | `pipeline/web_cache.py` (Brave 72 h, Seiten 7 d); v7: 92/116 Brave und 81/127 Seiten aus dem Cache |
| „line ends in a colon" vor einer Liste | v5 | Einleitung vor Liste/Tabelle ist Markdown |

Verlauf der Serie (Faktenquote nach dem Neuwurf / Strukturbefunde danach /
gestrichene Zitate): v3 0,43 / 5 / 6 · v4 2,41 / 3 / 0 · v5 1,22 / 2 / 6 ·
v6 2,01 / 1 / 8 · v7 1,27 / 2 / 0 · **v8 (DR-Modus) 2,90 / 1 / 2** — Kurzfassung
drei Aussagen, Kalender sechs Zeilen aus fünf Quellen, 2.479 Wörter; einziger
Strukturbefund: kein datierter, belegter Satz zur Wissenschaftsebene. Die drei
„unbelegten" Zahlen von v8 standen auf der zitierten Seite (`_evidence_text`
las den gelesenen Seitentext nicht mit — behoben, `dossier_check`). Damit ist
der DR-Vorlauf (Faktenzettel + Kalender-Kandidaten) der Pfad, der die Dichte
trägt; ohne ihn schwankt der Erstentwurf zwischen 1,0 und 2,4.

**v9 (2026-09-13, Order #32) — erstes `ok=True` der Serie.** DR-Vorlauf als
Default, CPC-Anker `H01M4/5825` (16.047 Patente, Messbasis 12.145 im
Zitationsgraph — nach acht Läufen ohne Messblock), Faktenzettel mit Plätzen für
Paper/Förderung: Faktenquote **3,28**, 0 unbelegte Zahlen, 0 gestrichene
Zitate, Kurzfassung drei Aussagen, alle Strukturbefunde nach EINEM Neuwurf
geschlossen (der Wissenschafts-Satz kam im Neuwurf), 1.984 Wörter (knapp unter
dem Band — Hinweis, kein Befund). Best-of-2 griff erneut (1,95 → 2,82), der
Cache trug 97 von 115 Suchanfragen und 139 von 180 Seiten. Was bleibt, ist
inhaltlich: 70 offene Fragen im Abdeckungsanhang und 17 Kernaussagen mit
Sekundär-Vermerk (Fachpresse trägt den Kalender, nicht die Firmenseiten).

**Nachtrag 13.09. — CPC-Entdecker entkoppelt (Owner: „ok für den CPC
Entdecker").** Warum die Kaskade LFP nie fand, in drei Schichten: (1) die
Themenformulierung trug Anwendungsfelder, die kein Patenttitel zusammen nennt
→ `head_phrase` misst den technischen Kern zuerst; (2) die Dichteregel teilte
durch die Klassengröße, aber im BDDS-Back-File haben nur 1–2 % der
Batteriepatente Text (H01M4/5825: 212 von 24.409) → Nenner = Patente mit
Text, Zählung direkt je Klasse statt über die 40k-gedeckelte Trefferliste
(mit Gattungswörtern hing die Dichte an der Formulierung: 1,6 % gegen 16,6 %
für dieselbe Klasse); (3) der Embedding-Nachbar von „lithium iron phosphate
cells" ist die Zellklasse H01M10/052, die Kathodenklasse heißt „Oxygenated
metallic salts or polyanionic structures, e.g. … phosphates" und liegt im
Vektorraum weit weg — im Titel steht das Wort aber → `title_candidates`
(seltene Titelstämme derselben Familie) + `sharper_title_class` (UND-Dichte,
≥ 1,5× dichter als die Basis). Ergebnis ohne Anker: „title-sharpened class
H01M4/5825: 25,9 % gegen 1,9 %". GLP-1, Perowskit und Festkörperbatterie als
Regressionsprobe (13.09., kalter Abdeckungs-Cache): LFP → `title-sharpened class
H01M4/5825` (235 s); GLP-1 → normalisierte Phrase, geschärft auf A61P5/48 +
C12N2501/335 (322 s); Perowskit-Tandem → Themenphrase, 8 Klassen H10F/H10K
(177 s); Festkörperbatterie → `dense gate candidates (H01M10/056, H01M10/058)`
(337 s) — alle vier messbar, keine Regression. Die Textabdeckung je Klasse
liegt danach in `data/cpc_text_coverage.json` (30 Tage), die Dichtemessung
kostet warm < 1 s.

**Iron-Air v1 (13.09., Order #33, ohne Anker) — Vergleich mit LFP v9 und der
zweite Harness-Fehler des Tages.** Erstentwurf-Paar 1,89/1,97 (Best-of-2 →
1,97), nach dem ersten Neuwurf noch **ein** Strukturbefund (Kalender 3/5).
Der zweite Neuwurf sollte den Kalender füllen — und jagte stattdessen der
Faktenquote nach: er zog datierte Rang-0-Fakten von Behördenseiten heran
(CEC-Förderungen für Vanadium-Flow-Speicher, Batt4EU-Fristen, EIC-Budget), die
mit Eisen-Luft nichts zu tun haben, ließ von 23 zitierten Quellen **4** übrig
und ging von 1 auf **4** Strukturbefunde — und der Harness lieferte diese
Fassung aus (Faktenquote 3,74 bei 1.793 Wörtern; Goodhart in Reinform). Fix:
ein Nachzug, der die Strukturbefunde nicht senkt, wird **verworfen**, die
Fassung davor bleibt (`second_rewrite_discarded`, E2E-Test). Patentmessung:
Gate ok, aber H01M10/36 + H01M10/05 zu breit; die Metall-Luft-Klasse
H01M12/06 heißt „with one metallic and one gaseous electrode" — kein
Themenwort im Titel, der Entdecker kann sie nicht finden → Anker-Fall
(Titelsuche jetzt mit Wortanfang statt Teilstring, sonst traf „air"
„rocking-chair"). Cache erstmals kalt für ein neues Thema: 114 Brave-Aufrufe,
5 aus dem Speicher. Die Restbefunde, die
`ok` blockieren, sind inhaltlich: Faktenquote unter 2,0 in schwachen
Entwürfen, Kalender mit weniger als fünf datierten LFP-Ereignissen, in v7 die
Innovationskette (Wissenschaft/Förderung ohne datierten Satz). Die
Patentmessung fiel in allen Läufen aus (keine CPC-Klasse mit ≥ 2 %
Trefferdichte für die Themenformulierung) — das ist ein Themenanker-Problem,
kein Prompt-Problem.

Vorbilder, gegen die der Harness gelesen wurde (Owner-Auftrag 12.09.):
hermes-deep-research (Wellen: Breite → Verifikation/Quellen-Unabhängigkeit →
Konflikte → Lücken; ≥ 20 % Budget fürs Schreiben), LangChain
open_deep_research (abschnittsweises Schreiben mit Reflexion), GPT Researcher
(Planner → parallele Executors → Publisher), arXiv 2604.03173 (3–13 %
halluzinierte URLs bei DR-Agenten — unser geschlossener Katalog ist strenger),
arXiv 2601.20843 (Kandidaten-Crossover → hier als Best-of-2). Noch nicht
übernommen: Evidenzfamilien (Syndikat/PR/Firmenseite als *ein* Beleg) und
abschnittsweises Schreiben (#100).

### Runde 16 (2026-09-13) — warum v1 nicht trug, SearXNG, Landschafts-Modus

**Ursachen, dass ein v1 bisher selten auf Anhieb brauchbar war** (aus neun
LFP- und einem Iron-Air-Lauf), und was dagegen steht:

| Ursache | Beleg | Gegenmaßnahme |
|---|---|---|
| Ein Schreibaufruf mit großer Varianz | Faktenquote 2,37 / 1,23 / 0,98 bei gleichem Auftrag | Best-of-2 (`DOSSIER_DRAFTS`) |
| Schreiben und Fakten sammeln im selben Aufruf | ohne Vorlauf 1,0–2,4, mit Vorlauf 2,5–3,3 | DR-Vorlauf Default (Faktenzettel, Kalender-Kandidaten, Plätze für Paper/Förderung) |
| Prüfer falsch kalibriert | BNEF = Rang 2, Präposition = Bruchstück, Klassengröße statt Text als Nenner | Rangliste, Fragment-Regel, Text-Nenner, Titelsuche |
| Neuwurf optimiert die Metrik statt das Thema | Iron-Air v1: Vanadium-Förderungen als „primär belegte Fakten“ | Themenbindung im Neuwurf; Kurzfassung muss das Thema nennen; verschlechternder Nachzug wird verworfen |
| Starres Kalender-Soll | 5 Zeilen bei 3 belegten Zukunftsereignissen → Fremdzeilen | Soll = max(3, min(5, Kandidaten)) |
| Zitate auf ungelesene Treffer | 6–8 gestrichene Zitate je Lauf | zitatgetriebener Abruf, Marker vor der Prüfung weg |
| Suchmaschine fällt aus | 402 am 12.09., 233 Fehlanfragen in einem Lauf | Web-Cache; **SearXNG-Fallback** (`pipeline/web_search.py`) |
| Patentmessung findet die Klasse nicht | 9 Läufe ohne Messblock | Kernphrase, Text-Nenner, schärfer per Titel; Anker als Override |

**Landschafts-Modus** (`--mode landscape`): für ein breites Feld ist die
Kommerzialisierungsfrage einer Technologie das falsche Gerüst. Neuer Vorschritt
`build_landscape_map`: das Modell schlägt 8–14 Teilfelder vor (aus Feld + 60
Korpus-Schlagzeilen), `subfield_counts` zählt jedes im Korpus nach (Trends mit
allen Begriffen, gedeckelt 20.000; Patente mit Text), unter 5 Signalen fällt es;
der Plan besteht aus einem Suchschritt je Teilfeld (deterministisch, kein
Planer-Aufruf), die Themenbegriffe umfassen alle Teilfelder, die Karte steht
gepinnt in den Notizen und als Anhang „Landscape map“ im Dossier. Erster Lauf:
`batteries-landscape` (Order #34): `ok=False` an einem Befund (Kalender 3/5),
Faktenquote 2,31, 38 Quellen, 2.644 Wörter, Messblock vorhanden — inhaltlich
Festkörper (ProLogium, BYD, Samsung SDI), Natrium-Ionen (UNIGRID, CATL),
Recycling, Batteriepass 2027, kritische Rohstoffe. Die Karte war aber dünn: 7
Teilfelder mit 6–32 Signalen, darunter „AI-driven battery management" und
„Lithium-ion degradation diagnostics" — schlagzeilengetrieben, und die
Nachzählung lief mit UND über vier Wörter („Sodium-ion battery cells" → 18
Signale, obwohl „sodium-ion" allein 54-mal in 500 Titeln steht). Nachgezogen:
`subfield_terms` zählt nur die spezifischen Wörter (ohne Gattungs- und
Feldwörter), `corpus_term_candidates` extrahiert die wiederkehrenden Komposita
und Zwei-Wort-Begriffe aus 500 Schlagzeilen (solid-state 105, sodium-ion 54,
lithium-ion 29, lithium metal 10, zinc 9, second-life 8, lfp 6, lithium-sulfur 6,
iron-air 5, anode-free 5 …) und legt sie dem Modell mit Zählung vor; 10–14
Items, Feldwort nicht wiederholen.

**v2 der Landschaft (Order #35, nach dem Karten-Fix):** 12 Teilfelder, jetzt
korpusverankert — solid-state 1.136 Signale / 19.117 Patente, sodium-ion
258 / 1.297, aqueous zinc 163 / 2.071, grid-scale storage 102, lithium-sulfur
73 / 710, lithium metal anode 71 / 797, degradation 71, second-life 67, SEI
41 / 1.442, iron-air 29 / 6, high-voltage cathode 17 / 547, black mass 9 / 75.
Endkontrolle: ein Befund (Kalender 3/5), Faktenquote 2,46, 30 Quellen,
2.233 Wörter, Messblock vorhanden, 0 unbelegt, 0 gestrichene Zitate; Cache
86 von 117 Suchanfragen, 142 von 202 Seiten. Der Kalender ist damit in vier
von fünf Läufen der EINZIGE verbliebene Sperrbefund, obwohl der Vorlauf
jeweils ≥ 5 datierte, belegte Kandidaten vorlegte — das Modell schreibt drei.
Konsequenz (R13-3 zu Ende gedacht): `fill_calendar` trägt fehlende Zeilen
aus den Kandidaten selbst ein — datiert, mit Katalog-id, themenbezogen,
sichtbar als „added from the dated-fact ledger (auto)", nur bis zum Soll und
ohne Dubletten; der Prüfnachweis nennt die Zahl (`calendar_filled`).

### Runde 17 (2026-09-13) — der Leser

Owner-Entscheid, der die Festlegung vom 06.09. („kein Kritiker-Modell, keine
Schleife") präzisiert: **ein Leser, kein Richter**, dasselbe Modell mit
eigener Systemanweisung. Anlass: Iron-Air v1 — ein Dossier über
Vanadium-Förderungen mit hoher Faktenquote; jeder Leser hätte es in zehn
Sekunden gesehen, der Prüfer sah Zahlen mit Beleg. Der Code prüft Form und
Belege, nicht Sinn.

- `reader_review(report, question, topic, landscape)`: `READER_SYSTEM` (fordernder
  Vorstand, adversarial, Rubrik: Frage beantwortet, Themenbezug je Sektion,
  Kurzfassung fasst zusammen, Optionen handlungsfähig, Landkarte abgedeckt,
  Kohärenz, Füllstoff); Ausgabe `ReaderReview` (answers_question, overall, ≤ 8
  Befunde mit Sektion, Art, Schwere, Zitatstelle, Einwand, Änderung). **Kein
  neues Faktenmaterial:** ein Vorschlag mit einer Zahl, die nicht im Entwurf
  steht, wird verworfen.
- Zwei Lesungen: (1) auf dem gewählten Erstentwurf → `reader_lines` gehen mit
  den Code-Befunden in den EINEN Neuwurf-Auftrag (ein „missing"-Befund trägt
  ERGAENZEN, damit der Evidenzblock mitkommt); (2) auf der Endfassung →
  `structure.reader_after`, im Prüfnachweis als „Leser (nicht sperrend)",
  `check.reader_ok`. Freigeben, sperren, umschreiben kann er nicht.
- Kosten: zwei Aufrufe à ~1–2 min. `DOSSIER_READER=0` schaltet ab.

**Abnahme (Blindläufe, ohne Nachjustieren):** ein Technologie-Lauf
„precision fermentation for dairy proteins" (Standardfrage, kein Anker) und ein
Landschafts-Lauf „quantum computing hardware" — Kriterium: `ok` UND der Owner
würde das Dossier einem Kunden zeigen.

**Ergebnis der Abnahme (14.09., 00:07 / 00:56):**

| | Präzisionsfermentation (#36, v4, Technologie) | Quantum-Hardware (#37, v1, Landschaft) |
|---|---|---|
| Endkontrolle | ✗ (Faktenquote 0,5; 4 primäre Belege — Fachpresse trägt das Feld) | **✓** (Faktenquote 2,45, 33 Quellen, Kalender ok) |
| Leser | ✗ „Momentaufnahme statt Trajektorie; Optionen nicht für Mittelstand; Kurzfassung wiederholt den Text“ | ✗ „nur 4 von 11 Teilfeldern der Karte; Kurzfassung vermengt Hardware mit PQC; Regulatorik-Boilerplate (SPC bei Hardware); Optionen nicht trennscharf“ |
| Kriterium erfüllt | nein | nein |

Lehren: (1) Der Code-Prüfer und der Leser messen Verschiedenes — #37 ist
mechanisch sauber und beantwortet die Frage nicht. `ok` bleibt notwendig, ist
aber nicht hinreichend; `reader_ok` steht daneben. (2) Im Landschafts-Modus
nutzt der Schreiber die Karte nicht (4 von 11) — die Karte muss eine
**Pflichtsektion mit Prüfregel** werden (je Teilfeld eine Zeile: Reife,
datierter Fakt, Beleg), nicht nur eine gepinnte Notiz. (3) Die Faktenquote
bestraft Felder, deren Primärquellen Behördenregister sind, die der Sweep
nicht trifft (FDA-GRAS-Notices, EFSA-Register) — der Rechts-Sweep fragt
pharma-geprägt (SPC, Patentablauf) und produziert dort Boilerplate. (4) Die
Leser-Befunde des ersten Durchgangs überleben den Neuwurf teilweise; ein
zweiter Neuwurf wird heute nur von Strukturbefunden ausgelöst.

### Runde 18 (2026-09-14) — die vier Lehren und abschnittsweises Schreiben

- **Abschnittsweises Schreiben** (`DOSSIER_WRITE=sections`, Default; `single`
  = der alte Ein-Aufruf-Pfad mit Best-of-2): `write_sections` schreibt je
  Pflichtsektion einen Aufruf mit dem ganzen Material und den schon
  geschriebenen Sektionen als Kontext (`<untrusted_sections_written>`), die
  Kurzfassung zuletzt; `take_section` schneidet genau die verlangte Sektion aus
  der Antwort. Reihenfolge: moving → regip → next → unsupported → options →
  open → decision; Ausgabe in Gliederungsreihenfolge. Kosten ~7 × (Prompt +
  400–700 Token) statt 2 × 2.500 Wörter.
- **Landkarte als Pflicht** (Landschafts-Modus): `_LANDSCAPE_OUTLINE_EN`
  verlangt in „What is moving" eine Tabelle `### Landscape` (Teilfeld, Reife,
  datierter Fakt, Beleg — eine Zeile je Kartenpunkt, notfalls „no dated
  evidence in this run"); `landscape_findings` meldet Teilfelder, deren
  spezifische Wörter im Text fehlen, als Strukturbefund (trägt ERGAENZEN).
- **Leser löst den zweiten Neuwurf aus:** nach dem ersten Neuwurf liest der
  Leser; schwere Einwände (oder „beantwortet die Frage nicht") gehen mit den
  Strukturbefunden in den zweiten Neuwurf; danach liest er erneut. Verworfen
  wird der Nachzug, wenn weder Strukturbefunde noch schwere Leser-Einwände
  sinken; der letzte Leser-Stand steht im Prüfnachweis (`reader_after`).
- **Regulatorik feldneutral:** die Gliederung nennt SPC nur noch für Arznei-
  und Pflanzenschutzmittel, verlangt die Instrumente des Felds (EFSA/GRAS für
  Food, CE/Export für Hardware) und verbietet Auflistungen dessen, was der Sweep
  nicht fand, als „Analyse".
- **Beide Ampeln:** Desk-Liste und Dossieransicht zeigen neben der
  Endkontrolle den Leser (`reader_ok`), ebenso `dossier_worker --list`.
- **Stärkerer Schreiber unter Test:** `DOSSIER_WRITER_MODEL` (GGUF-Name) schaltet
  vor dem Schreiben auf ein registriertes Modell um; erster Test:
  Qwen3.8-Flash-Next UD-Q2_K_XL (125B/6B aktiv, 51B n-Gramm-Tabelle lazy von
  der SSD, ~20–22 GB VRAM) auf `quantum-computing-hardware` v2 gegen v1 (27B).

**Ergebnis Flash-Next-Test (14.09., Order #38, Quantum-Hardware v2, sektionsweise,
noch ohne Wortbudgets):** Modellwechsel in 17 s, 21,5 GB VRAM, 5,5 min je Sektion,
Lauf 95 min (v1 mit 27B: 49 min). Landkarte vollständig (12/12 Teilfelder in
`### Landscape`, vier davon ehrlich „no dated evidence"), Kurzfassung mit drei
datierten Primäraussagen — inhaltlich klar über v1. Aber 4.793 Wörter
(Obergrenze 2.800; jede Sektion hielt sich für das ganze Papier → Wortbudgets
je Sektion nachgezogen, `d2946a4`), dadurch Faktenquote 1,67 trotz **80**
datierter Primärangaben (v1: 61); Kurzfassung 235 Wörter; zweiter Neuwurf
verworfen (Struktur 3 → 3, Leser 5 → 6). Leser: vier Teilfelder ohne datierten
Fakt (Evidenzlage), ein Widerspruch Kurzfassung/Fließtext (photonisch), zirkuläre
Aufwandsangaben in zwei Optionen. Urteil: mehr Substanz, keine Disziplin — ein
fairer Vergleich braucht v3 mit Budgets auf beiden Modellen.

### Runde 19 (2026-09-14) — Optionen raus, der Advisor rein

Owner-Entscheid: „Options for a mid-sized European company" war in jeder
Abnahme die schwächste Sektion, weil das Dossier seinen Leser nicht kennt. Das
Dossier endet jetzt mit **Decision points and watch items** (3–6 belegte
Auslöser mit dem, was sie entscheiden würden; Förderfristen sind keine
Auslöser; Wortband 1.800–2.400). Die Beratung ist ein eigenes Artefakt:
`advisory_notes` je Dossier-Version, Kundenprofil und Auftragsumfang als
Daten, ein Modell in der Beraterrolle **mit Denken** (`ADVISOR_SYSTEM`: Situation
→ Optionenraum mit Null-Option → je Option Trigger/Horizont/Aufwand aus
Vergleichsfall/Wer zahlt/Risiko/Abbruchkriterium/Gegenargument →
Empfehlung mit Konfidenz → benutzte Belege), geschlossener Katalog des
Dossiers, deterministische Prüfung (gestrichene Marker, Platzhalter, Zahlen
gegen Dossier + Profil), dann der Leser, dann **die Freigabe durch einen
Menschen** (`approved_at`). Die Optionsregeln des Dossiers (Effort nie aus der
Fördergrenze, Platzhalter = unerfüllt) leben im Advisor-Prompt weiter.

**Erster echter Lauf (14.09., Notiz #1, LFP v9, fiktiver DACH-Speicherintegrator):**
233 s, Denken an — und **0 Wörter**: Denkspur und Antwort zählen beide gegen
`max_tokens`, mit 6.000 blieb nach dem Denken nichts für die Antwort, und die
Prüfung nannte die leere Notiz „ok" (keine gestrichenen Marker, keine
Platzhalter …). Fix im selben Zug: `ADVISOR_MAX_TOKENS` Default 24.000, unter
`ADVISOR_MIN_WORDS` (300) ein zweiter Versuch **ohne** Denken, danach `failed`
mit klarem Fehler statt einer leeren `review`-Notiz; `ok` verlangt jetzt
zusätzlich mindestens zwei `### Option`-Blöcke (Null-Option + eine echte).
Außerdem stellt `thinking_server` den Ruhezustand her, wie er vor dem Lauf
war (8B-Server läuft wieder, wenn er vorher lief) — nach #1 stand die Unit.

**Notiz #2 (17:12, 1.034 s):** der Denk-Durchgang dachte exakt 24.000 Tokens
(800 s) und antwortete nie — das Modell kommt bei diesem 13k-Prompt nicht zum
Schluss. Die gelieferte Notiz stammt vom Rückfall ohne Denken: `ok` (11 Quellen,
3 Optionen, 1.481 Wörter, keine fremden Zahlen), Leser dagegen: beantwortet den
Auftrag nicht exakt (Hybrid-Option statt der gestellten Binärfrage, 40 M€ und
500 MWh/a nicht adressiert) und der Aufwands-Vergleichsfall (9-GWh-Liefervertrag
für 500 MWh/a) trägt nicht. Konsequenzen: **Denkbudget im Startskript**
(`~/llama.cpp/start-qwen3.8-27b-thinking.sh`: `--reasoning-budget 8192`, ~4,5 min;
llama.cpp schließt die Denkmarke dann selbst), und der Prompt verlangt jetzt
Vergleichsfälle von Art *und* Größenordnung des Kunden sowie eine Empfehlung,
die die Auftragsfrage exakt so beantwortet, wie sie gestellt ist.
