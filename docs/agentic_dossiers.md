# Agentic Scouting-Dossiers (Owner-only) — `/trends/dossiers`

Stand 2026-09-07 (Messkette M1/M2/M3/M4/M6 — s. „Die Messkette" weiter unten;
davor 2026-09-03 Frontend-Integration #95, Branch `Agentic-Dossiers` am
2026-09-03 nach `dev` gemergt). Baut den agentischen Rechercheur (`scripts/corpus_research.py`,
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
                                    Web → Re-Audit → EINE Sweep-Nachrunde →
                                    Bericht → Zitat-Kanonisierung (Katalog-IDs)
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
| Rechercheur | `scripts/corpus_research.py` | `run(..., quant=..., corpus_stats=..., measure=True)` injiziert Messquellen+Notizen (gepinnt), sweept audit-unabhängig, zitiert per Katalog-ID und hängt die codegenerierten Anhänge an; Result enthält `evidence`, `quant`, `corpus_stats`, `measure`; CLI `--quant`, `--measure`/`--no-measure` |
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

- Kein Versions-**Diff** in der Ansicht (nur Versionswechsler) — Kandidat für
  den nächsten Schritt, die Versionierung existiert genau dafür.
- `--retrieval vector` bleibt wie in der Skizze ungetestet; Worker-Default
  ist FTS.
- Die offenen Kanten der Skizze gelten weiter (Web-Treffer ungeranked,
  Patent-Sweep titelbasiert).
