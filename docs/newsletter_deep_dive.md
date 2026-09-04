# Newsletter „Deep Dive of the Week" (#96) — Phase 1: Dry-Run-Kette

Stand 2026-09-04 (Phase 1 auf `dev`, **nicht scharf**). Owner-Auftrag 2026-08-30:
der Wochen-Newsletter (Website-Edition, Mo 09:00) bekommt eine rechercheur-
gestützte Sektion zum stärksten Wochenthema — zitierte Einordnung aus den
internen Korpora, nicht neue Prosa-Freiheit. Phase 1 baut die komplette Kette,
lässt sie aber nur als **Dry-Run** laufen: das Ergebnis wird gespeichert und
dem Owner gezeigt, öffentlich erscheint nichts. Scharfschaltung (`--apply`, Cron)
erst nach Owner-Blick auf 2–3 Wochen Dry-Run-Dossiers (#95-Hold).

## Ablauf (ein Aufruf, `scripts/newsletter_deep_dive.py`)

```
weekly_newsletter_publish.sh                      (Mo 09:00, unverändert bis hier)
  Kollisionswächter → Idempotenz → Gemma-Swap → Edition W-1 → newsletter_editions
  └─ NUR wenn NEWSLETTER_DEEP_DIVE=dry-run:   scripts.newsletter_deep_dive --dry-run
        1  Themenwahl        SQL: Signal-Anteil der Woche vs. Anteil der 4 Vorwochen
                             je Mega-Theme; Varianz-Regel (Themen der letzten 4
                             Editionen mit deep_dive ausgeschlossen); Ranking gespeichert
        2  Recherche         dossier_orders.create_order(slug newsletter-deepdive-<J>-w<KW>)
           (Qwen3.8-27B)     → scripts.dossier_worker.run_worker(--order N, --skip-quant)
                             → model_on_llamacpp (VRAM < 1100 MiB, Identitäts-Check)
                             → corpus_research.run (web_steps 0 in Phase 1)
                             → dossiers(slug, v) + Endkontrolle → Status 'review' (Desk)
                             Zeitbudget 20 min per SIGALRM → Auftrag 'failed', Handover räumt auf
        3  Gate              Audit + Endkontrolle des Dossiers (Startwerte unten)
        4  Kondensat         content_gen_on_llamacpp(Gemma-4-26B): 300–500 Wörter,
           (Gemma)           bis zu 3 Versuche (Seed 96+i); Nachprüfung deterministisch
        5  Speichern         newsletter_editions.deep_dive (JSON, dry_run=true)
                             frontend/content/analyses/newsletter-deepdive-<J>-w<KW>.md (draft: true)
                             data/newsletter_deep_dive_last.json (Morgen-Mail-Zeile)
        Ruhezustand          start-active.sh → start-qwen3-8b-208k.sh, llama-server aktiv
```

Handover-Reihenfolge: 27B → (Ruhezustand durch den Worker) → Gemma → Ruhezustand.
Der Worker stellt nach der Recherche den Ruhezustand selbst her; der Gemma-Handover
danach stoppt/startet die Unit erneut, das Skript startet sie am Ende wieder
(`_restore_resting_server`). E2E 2026-09-04: danach `is-active` = active, `/v1/models`
= Qwen3-8B-UD-Q4_K_XL.

**Graceful Degradation** — nie ein Blocker für die Edition: kein Thema über dem
Mindestvolumen / Handover verweigert / Zeitbudget gerissen / Gate verfehlt →
die Edition bleibt wie sie ist, `deep_dive` protokolliert den Grund
(`status`: `no_theme` · `research_failed` · `gate_failed` · `ok`), die Wrapper-
end-Zeile trägt `dd=<rc>`, der Exit-Code der Edition bleibt unberührt.

## Themenwahl (deterministisch, auditierbar)

`theme_deltas()`: je `mega_trend` die published Signale der ISO-Woche (`created_at`,
wie der Generator) und der vier Vorwochen; Anteile statt Rohzahlen (Normierung wie
`pipeline.mega_momentum`); Ranking nach relativer Anteilsänderung, Themen ohne
Vorwochen-Basis (< 5) als „emerging" ganz oben. `pick_theme()`: erstes Thema mit
≥ 15 Signalen in der Woche, das nicht in den letzten 4 Editionen Deep-Dive war
(Dry-Runs zählen mit, sonst käme in Phase 2 viermal dasselbe Thema). Das Ranking
(Top 8), die Ausschlussliste und die 6 stärksten Wochensignale des Themas werden
in `deep_dive.theme_choice` gespeichert. `--theme KEY` = Owner-Override,
`--theme-only` zeigt Ranking und Wahl ohne Modell.

Die Rechercheur-Frage ist **nicht** die Foresight-Standardfrage (die zielt auf eine
Technologie), sondern eine Newsletter-Rahmung mit Wochenanker: Thema + Beschreibung,
die 6 stärksten Wochensignale, dann „Historie / Akteure / Korrekturen / was heute
läuft / Firmen-Claims vs. validierte Fakten / was die Paper-/Patentkorpora
beitragen / was der Korpus nicht beantworten kann" (`build_question()`).

## Ehrlichkeits-Gates (Startwerte — im Dry-Run kalibrieren)

| Gate | Startwert | Quelle | Begründung |
|---|---|---|---|
| `supported_claims` | ≥ 8 belegte Kernaussagen | Rechercheur-Audit (`audit.supported`, Re-Audit nach dem Korpus-Sweep) | Issue-Startwert X=8 |
| `contradictions` | < 3 offene Widersprüche | `audit.contradictions` | Issue-Startwert |
| `citations_canonical` | 100 % der Links im fertigen Berichtsteil kanonisch | eigener Re-Check gegen `cited`/`sources` (Quellenliste + Coverage-Anhang abgetrennt) | Issue: „Zitatquote 100 % kanonisiert" — die Kanonisierung erzwingt es; der Check ist der unabhängige Beleg |
| `dossier_grounded` | 0 unbelegte Zahlen im Dossier | Endkontrolle (`pipeline/dossier_check.py`) | Kondensat darf nur Zahlen tragen, die im Dossier belegt sind — also muss das Dossier selbst sauber sein |
| `condensate` | Nachprüfung des Kondensats (s. u.) | `verify_condensate()` | Gemma formuliert nur |

Kondensat-Nachprüfung (deterministisch, alle fünf müssen halten): Wortzahl 300–500 ·
alle Links im Zitat-Katalog des Dossiers (Origin-URLs werden auf die kanonische
URL umgeschrieben, katalogfremde gestrichen → Verstoß) · alle Zahlen im
Dossier-Material (`pipeline.grounding.ungrounded_specifics` gegen Bericht +
Katalog-Titel/-Snippets + Wochensignal-Titel; **nicht** gegen die rohen
Evidenznotizen — eine Zahl, die nur dort steht, hat der Owner im Dossier nie
gesehen) · ≥ 4 distinkte Belege · reine Prosa (keine Headings/Listen).

`gate_passed = alle Dossier-Gates ∧ condensate`. Im **Dry-Run** wird das Kondensat
auch bei verfehltem Dossier-Gate erzeugt (Kalibrier-Material für den Owner); mit
`--apply` entfällt es dann (kein Gemma-Swap für nichts). Nicht als Gate, aber als
Kennzahl gespeichert: `stripped` (Zitate, die das Modell erfand und die die
Kanonisierung strich), `open_questions`, `inferences`, `missing`, Belegmix.

## Frontend

- `newsletter_editions.deep_dive` (JSONB; `scripts/migrate_newsletter_deep_dive.py`,
  **auf der Live-DB am 2026-09-04 ausgeführt**). SQLite-Zweig: TEXT; der Generator-
  Upsert schreibt die Spalte nie (ON CONFLICT DO UPDATE statt INSERT OR REPLACE).
- Eine Render-Regel, an drei Stellen durchgesetzt (`lib/newsletterEditions.ts`
  `isPublicDeepDive`): öffentlich nur `gate_passed && !dry_run && body_md`.
  API-Route filtert unter `PUBLIC_MODE`, `rewriteEditionForExport` filtert den
  statischen Export, `EditionBody` prüft zusätzlich `isStaticExport()`.
- Owner-Instanz: `DeepDiveOwnerNote` — „Deep-Dive Dry-Run — not public" zwischen
  Editorial und Vertikalen: Thema, Gate-Chips (ok/fail je Gate), Audit-Zahlen,
  Gründe, Link „Open the dossier in the desk →" (`/trends/dossiers/<slug>?v=<n>`),
  Kondensat-Vorschau mit Belegart-Badges.
- Öffentlich (Phase 2): `DeepDiveSection` — Themenname, Absätze mit Belegart-
  Badges (`article`/`signal`/`paper`/`patent`/`web` aus `citations[]`, per URL
  zugeordnet), Herkunftsfußzeile (Korpus-Stand, Belegmix, Modelle, Dossier-Serie).
- Abschnittsnummern der Edition werden jetzt dynamisch vergeben (01 Overview,
  [02 Deep Dive], Vertical Signals, Radar); das Archiv trägt keine Nummer mehr.
- Export-Nachweis 2026-09-04 (`scripts/build_public_static.sh`, rc 0, 33.089 Dateien):
  in **keiner HTML-Datei** „Deep-Dive Dry-Run" / `data-owner-note` / „Condensate
  preview" / „Deep Dive of the Week"; `newsletter-deepdive` kommt im gesamten
  `out/`-Baum nicht vor (kein Draft, kein Dossier-Slug); die Strings existieren nur
  als Komponenten-Code in einem `_next/static/chunks/*.js` (die Render-Regel liegt
  in den Daten, nicht im Bundle). Draft-Markdown nie gerendert (`lib/analyses.ts`
  filtert `draft: true` in Liste und Slug-Lookup).

## /analysis-Draft

Jeder Lauf legt `frontend/content/analyses/newsletter-deepdive-<J>-w<KW>.md` ab:
Frontmatter aus den Dossier-Metadaten (`draft: true`, `corpus_asof` =
Dossier-Stand, `image: <slug>.png` als Platzhalter, Autor-Zeile als „draft, not
reviewed"), dann Hinweiskopf mit Gate/Audit, Kondensat, danach das vollständige
Dossier. Der Owner reviewt/schärft, setzt `draft: false`, legt das Bild ab und
committet — vorher ist die Datei nur ein untracked Arbeitsstand (nie `git add -A`).
Ein erneuter Lauf derselben Woche überschreibt den Draft (Dossier wird v+1).

## Wächter / Morgen-Mail

`data/newsletter_deep_dive_last.json` (date, year/week, theme, status, gates,
audit, words, seconds, dossier_slug/version, analysis_draft, error).
`scripts/review_notify.py` hängt daraus eine Zeile an die Morgen-Mail, solange die
Datei < 36 h alt ist (Montagslauf → Dienstag-Mail); ein Dry-Run wird bewusst
gemeldet. Der Cycle-Wächter (`cycle_watchdog.py`) prüft die Datei noch nicht —
das kommt mit der Scharfschaltung (bis dahin wäre ein Montags-„missing" Rauschen).

## Dry-Run-Ergebnisse (Kalibrier-Protokoll)

### 2026-09-04 — Edition 2026-W35, Thema `digital_trust_and_data_sovereignty`

Themenwahl: 216 Signale (7,0 % Wochenanteil vs. 5,4 % Vorwochen, **+31,5 %**),
keine Ausschlüsse; über dem Mindestvolumen lagen nur noch `future_of_food` (+11,7 %),
`clean_energy_transition` (+10,6 %), `climate_resilience` (+9,5 %),
`personalized_health` (+5,5 %). Wochensignale: Meta-Teen-Safety-Settlement (3 Fassungen),
EPA-Datacenter-Emissionen, Cyberangriffe auf polnische Solarparks / UK-Kleinkraftwerke.

| Lauf | Recherche | Audit (supported / contradictions / missing) | Belegmix (A/S/P/N/W) | zitiert / gestrichen | Endkontrolle | Gate | Kondensat |
|---|---|---|---|---|---|---|---|
| v1 (Auftrag #3) | 226 s, 5 Agenten-Schritte, Korpus-Sweep +12 Paper +8 Patente | 6 / 1 / 8 | 3/3/12/8/0 | 4 von 26 / 0 | **3 „unbelegte Zahlen" = Slug-IDs in Zitat-URLs** (False-Positive → Fix in `dossier_check.py`) | verfehlt (`supported_claims` 6 < 8, `dossier_grounded`) | 362 Wörter, 4 Belege (3 article, 1 patent), Nachprüfung 5/5 ok im 1. Versuch (7,6 s) |
| v2 (Auftrag #4, nach Fix 1) | 231 s, Korpus-Sweep +12 Paper +8 Patente | 7 / 2 / 5 | 6/6/12/8/0 | 14 von 32 / 1 | **2 „unbelegte Zahlen" = Ordinalzahlen der code-generierten Quellenliste** (zweiter False-Positive → Fix 2) | verfehlt (`supported_claims` 7 < 8, `dossier_grounded`) | 345 Wörter, 5 Belege, 5/5 ok im 1. Versuch |
| v3 (Auftrag #5, nach Fix 2) | 270 s, Korpus-Sweep +12 Paper +8 Patente | 6 / 2 / 5 | 6/6/12/8/0 | 14 von 32 / 0 | **0 unbelegte Zahlen**, ok=True (1 Befund: 8 offene Fragen) | verfehlt **nur** an `supported_claims` (6 < 8) | 324 Wörter, 6 Belege, 5/5 ok im 1. Versuch |

Gesamtlaufzeiten: v1 **260 s**, v2 **268 s**, v3 **300 s** (Themenwahl < 1 s, 27B-Handover
+ Recherche 230–270 s, Gemma-Handover + Kondensat ~20 s). Ruhezustand nach jedem
Lauf verifiziert (`is-active` active, Symlink 8B-208k, `/v1/models` Qwen3-8B).
Die drei Läufe liegen als v1–v3 der Serie `newsletter-deepdive-2026-w35` im Desk
(Aufträge #3–#5, Status `review`); die Edition trägt den v3-Datensatz.

Lesart für die Kalibrierung:

- **`supported_claims` ist das bindende Gate.** Ohne Web-Stufe (Phase 1) trägt der
  Korpus zu einem nachrichtengetriebenen Wochenthema ~6 belegte Kernaussagen —
  drei Artikel + drei Signale zum Meta-Settlement, die Paper/Patente des Sweeps
  waren thematisch nur lose verbunden (Zero-Trust-Patent). Der Startwert 8 bleibt
  bis zu 2–3 weiteren Wochen stehen; die Phase-2-Web-Stufe (`--web-steps 6`) ist
  der erwartete Hebel, nicht das Senken der Schwelle.
- **Das Kondensat hält die Zitierdisziplin:** alle Zahlen ($17 bn/$18 bn, 29/47
  Staaten, $1,5 bn Kalifornien, 10 Jahre) stammen aus dem Dossier, der Widerspruch
  der Quellen wird als Widerspruch benannt, offene Fragen als offen. Kein Link
  außerhalb des Katalogs, kein Neuwurf nötig.
- **Zwei Endkontroll-False-Positives gefunden und behoben** (`pipeline/dossier_check.py`,
  betrifft alle Desk-Dossiers): (1) Slug-IDs (`…-24632113`) und Patentnummern in
  Zitat-URLs zählten als unbelegte Zahlen — Links werden jetzt auf ihr Label
  reduziert; (2) die Ordinalzahlen der code-generierten Quellenliste (`12.`, `14.`)
  zählten mit — die Liste wird wie der Coverage-Anhang abgetrennt
  (`tests/test_dossier_check.py::TestCitationUrlsAreNotFigures`). Nach beiden
  Fixes: v3 mit 0 unbelegten Zahlen bei 24 Links im Berichtsteil.
- **Streuung zwischen den Läufen** (gleiche Frage, gleicher Korpus, T=0.3/0.4 im
  Rechercheur): 6 / 7 / 6 belegte Aussagen, 1 / 2 / 2 Widersprüche, 4 / 14 / 14
  zitierte Quellen, 0 / 1 / 0 gestrichene Zitate — das Audit-Gate liegt bei diesem
  Thema konstant knapp unter 8, die Zitier-Kennzahlen schwanken stärker (v1 zitierte
  nur 4 Quellen). Für die Kalibrierung heißt das: ein einzelner Lauf pro Woche reicht
  als Gate-Grundlage, aber die Schwelle 8 darf erst nach mehreren Wochen und
  Themen bewegt werden.
- Dossier-Wortzahl 1.484 / 1.956 / 1.786, 9 / 6 / 8 offene Fragen im Ledger — das
  Dossier ist ehrlich über die Korpuslage („no evidence for EPA / Polish solar /
  UK power plants").

## Betrieb

```bash
# Ranking + Wahl ansehen (kein Modell)
.venv/bin/python -m scripts.newsletter_deep_dive --year 2026 --week 35 --theme-only

# Dry-Run für eine Edition (Edition muss existieren; ~4–5 min; GPU frei halten)
.venv/bin/python -m scripts.newsletter_deep_dive --year 2026 --week 35

# Owner-Override des Themas
.venv/bin/python -m scripts.newsletter_deep_dive --year 2026 --week 35 --theme quantum_information_science

# Im Montagslauf (crontab-Zeile ergänzen, NICHT Default):
0 9 * * 1  NEWSLETTER_DEEP_DIVE=dry-run scripts/weekly_newsletter_publish.sh
```

Kollisionsregel wie Dossier-Worker/Research-Pulse: nicht parallel zum 04:00-Full-Cycle
(der Wrapper wartet ohnehin auf dessen Ende) und nicht parallel zu einem Desk-Lauf —
das Skript schreibt `data/dossier_worker.lock` mit seiner PID, der Desk zeigt
„running" und startet keinen zweiten Worker.

## Phase 2 (Schalter, nicht Code)

1. `--web-steps 6` (Brave, fetch-pflichtig) — vorher Domain-Qualitätsliste ergänzen
   (bekannte Schwäche: Blockliste fängt UGC, keine minderwertige Fachpresse).
2. Gate-Schwellen aus den Dry-Run-Zeilen oben kalibrieren (Owner-Entscheid).
3. `--apply` im Wrapper (`NEWSLETTER_DEEP_DIVE=apply` wäre ein neuer Wert — bewusst
   noch nicht implementiert, damit Phase 1 nichts scharf schalten kann) + E-Mail-
   Template mit der Versandkette (#16). Export: Artikel-Links im Kondensat
   (`https://catandary.de/trends/<slug>`) durch die Fensterregel führen
   (`resolveEditionHref` kennt heute nur relative Links).
4. `cycle_watchdog.py` auf `newsletter_deep_dive_last.json` verdrahten.

## Tests

- `tests/test_newsletter_deep_dive.py` (24): Themenwahl/Varianz-Regel/Frage,
  Gate-Auswertung, Kondensat-Nachprüfung inkl. Retry, Spalte/Upsert/Decode auf
  SQLite, Draft-Frontmatter, Orchestrator-Degradation (kein Thema, Recherche
  failed, Dry-Run-E2E mit Fakes, `--apply` ohne Kondensat), Morgen-Mail-Zeile.
- `tests/test_dossier_check.py::TestCitationUrlsAreNotFigures` (Regression).
- Frontend: `newsletterEditions.test.ts` (public-Regel, Export-Filter, Desk-Pfad),
  `api/newsletter/route.test.ts` (Owner sieht Dry-Run, PUBLIC_MODE nicht).
