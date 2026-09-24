# Issue-Status (Stand 2026-08-28 — Audit nach dem Geschäftsmodell-Wechsel; Nachträge bis 2026-09-09)

> **Nachtrag 24.09.2026 — vier Issues geschlossen, #79 wartet auf einen Handgriff:**
> - **#95** Korpus-Rechercheur und **#96** Newsletter-Deep-Dive: mit dem Dossier-Rückbau vom 19.09. gegenstandslos, als „nicht weiterverfolgt" geschlossen.
> - **#67** Query-Quality-Gate: gebaut, gemessen, `tests/test_query_gate.py` 18 passed; einziger Rest ist der Betriebshinweis „nach Embedding-Modellwechsel Fixture neu messen" (steht in `docs/tech_query_gate_2026-09-04.md`).
> - **#73** Research Pulse: Merge erfolgt, `kind` ohne NULL, Cron seit 18.09.; W35 heute komplett nachgerechnet (28 Themes, 18 mit Text, 0 Fehler, 62 s). ResearchGate-DOIs als Owner-Frage nach #103 übertragen.
> - **#79** patent_cpc: Parse-Fehler-Bucket = 0; die 4.421.765 JP-F-Term-Zeilen hat der Owner am 24.09. abends von Hand gelöscht (`DELETE 4421765`, `subclass IS NULL` = 0), Issue geschlossen. Nachwirkung: `cpc_cooccurrence` verliert beim nächsten Rebuild 397.128 Pseudo-Code-Paare, SPNP-Sektion für 235.898 JP-Patente wieder bestimmbar. Rest-Kosmetik: 1.490.819 Zeilen tragen im Feld `cpc` noch die Editionsziffer (`4H04N19/463`), Subclass ist korrekt.

> **Nachtrag 19.09.2026 — Scouting-Dossiers ENTFERNT (Owner: „Das Feature trägt nicht")**:
> - Alle Dossier-/Advisor-Module, Skripte, Tests, das Desk `/trends/dossiers` und die
>   Migrationsskripte `migrate_dossier_{orders,brief,run_outcomes,source_priors,query_stats}.py` sind aus
>   dem Code (Tag `archive/dossiers-2026-09-19` = Stand davor). Die Migrationsnotizen weiter unten
>   sind Historie: **Tabellen bleiben, Feature entfernt** — `dossier_orders`, `dossiers`,
>   `dossier_run_outcomes`, `dossier_source_priors`, `dossier_query_stats`, `advisory_notes` stehen
>   auf der Live-DB, kein DROP, nichts liest oder schreibt sie mehr; die frühere „Migrationslücke"
>   (nicht in `init_db`) ist damit gegenstandslos. #100 und #107 (in #108 zusammengeführt) tragen
>   die Nachfolge-Idee „Field Watch" (`docs/value_proposition_field_watch_2026-09-19.md`).
> - Newsletter-Deep-Dive (#96) stillgelegt: `scripts/newsletter_deep_dive.py` schreibt `status: "disabled"`.

> **Nachtrag 02.09.2026** (vollständig: `docs/audits/2026-09-02_issue_audit.md`, `_compliance_review.md`,
> `_security_review.md`, `_static_export_design.md`; Plan: `docs/launch/09_launch_plan_2026-09-02.md`):
> - Alle vier manuellen DB-Schritte des 28.08.-Audits sind **erledigt** und gegen die Live-DB verifiziert:
>   `migrate_dead_links.py` (dead_links: 124 Zeilen), `apply_source_hygiene.py --apply` (323 aktiv / 16 inaktiv),
>   `backfill_cpc_subclass.py`, `DROP INDEX idx_re_patent_fts` (`pg_indexes` = 0).
> - **#48 und #71 geschlossen** (02.09.); der Link-Check-Cron (`0 7 2 * *`) ist installiert und lief 02.09.
> - **#81-Bugfix** (`1d59124`): OpenAlex-Wächter — LIKE-Muster parametrisiert (psycopg2 IndexError durch nacktes `%`).
> - **#82 neu geschnitten**: Owner-Entscheid **statischer Export** aufs Hetzner-Webhosting statt VPS
>   (`HOSTING_PUBLIC_VPS.md` archiviert); Umsetzung = Welle 2 im Plan.
> - Überholt in diesem Dokument: „kein Newsletter-Cron" (Website-Edition läuft Mo 09:00 seit 29.08.), „dev +7 /
>   Branch `issue-audit`" (gemergt 01.09., Branch gelöscht), die „manuell ausführen"-Hinweise unten.
> - Weiterhin reklamierbar: `*_old`-Tabellen (~36 GB: `patent_cpc_full_old`, `patent_spnp_full_old`, `patent_spnp_full_z3_old`).

> **Nachtrag 03.09.2026 — #95 Korpus-Rechercheur im Frontend** (`docs/agentic_dossiers.md`):
> - Branch `Agentic-Dossiers` nach `dev` gemergt (`a73d4a9`; Konflikte in `corpus_research.py`
>   [`--company`/`--focus` + `quant`], `publicMode.ts`, `dossier-access.ts` [Auth weg → lokal offen,
>   PUBLIC_MODE/Export zu], CLAUDE.md/.env.example). Desk `/trends/dossiers` standardmäßig AN
>   (`DOSSIERS_ENABLED=0` = Not-Aus), im Export ausgeschlossen (Drift-Wächter grün).
> - `migrate_dossier_orders.py` auf der Live-DB ausgeführt (idempotent, `dossier_orders` neu).
> - Frontend: „Run now"/„Run N queued"/„Recompute · v(n+1)" starten den Worker on-demand
>   (Radar-Regel), Herkunftskopf + Coverage-Anhang, Markdown-Tabellen, Same-Origin-Check in den
>   Server Actions, Scouting Desk im Foresight-Menü/Cockpit.
> - Abnahmelauf §1 (perovskite tandem photovoltaics): fertiges Dossier 8/8 Zitate belegt, 0 tote
>   URLs, 0 unbelegte Zahlen, Ledger 6/6 befüllt; Streichungsquote 46,7 % der Zitat-Instanzen
>   (3 katalogfremde, nicht existierende URLs im Roh-Bericht) bleibt der offene Prüfpunkt.
>   Dauer 477 s Recherche / 568 s Wandzeit. **Weiterhin offen:** §1 weitere Domänen, `lang=de`-Streichungen.

> **Nachtrag 04.09.2026 — #96 Newsletter-Deep-Dive, Phase 1 (Dry-Run-Kette, NICHT scharf)** (`docs/newsletter_deep_dive.md`):
> - Komplette Kette auf `dev`: `newsletter_editions.deep_dive` (JSONB, Migration auf der Live-DB ausgeführt),
>   `scripts/newsletter_deep_dive.py` (Themenwahl per Anteils-Delta + Varianz-Regel, Rechercheur über den
>   Dossier-Auftragspfad mit 20-min-Budget, Ehrlichkeits-Gates, Gemma-Kondensat mit deterministischer
>   Nachprüfung, `/analysis`-Draft `draft: true`, Wächter-JSON + Morgen-Mail-Zeile), Wrapper-Schritt
>   `NEWSLETTER_DEEP_DIVE=dry-run|off` (Default off — Montagslauf unverändert), Frontend-Render nur bei
>   `gate_passed && !dry_run`, Dry-Run als Owner-Hinweisblock mit Desk-Link; Export/PUBLIC_MODE filtern.
> - E2E-Dry-Runs W35 (Thema `digital_trust_and_data_sovereignty`, +31,5 % Wochenanteil): 260/268 s Wandzeit,
>   Ruhezustand danach verifiziert (llama-server aktiv, 8B-208k). Gate verfehlt am Audit (6 bzw. 7 < 8
>   belegte Aussagen — ohne Web-Stufe trägt der Korpus zu einem News-Thema ~6–7); Kondensat 362/345 Wörter,
>   Nachprüfung 5/5 im ersten Versuch, alle Zahlen/Links aus dem Dossier.
> - Nebenfund, behoben: `pipeline/dossier_check.py` zählte Slug-IDs/Patentnummern in Zitat-URLs und die
>   Ordinalzahlen der code-generierten Quellenliste als „unbelegte Zahlen" (alle Desk-Dossiers betroffen).
> - **Offen (Owner):** 2–3 Wochen Dry-Run beobachten, dann Schwellen kalibrieren; Phase 2 = Web-Stufe +
>   `--apply` + E-Mail-Template (#16); Owner-Fragen aus dem Issue (ein Deep-Dive/Woche, Override-Datei,
>   Startzeitpunkt). Nicht nach `main` gemergt.

> **Nachtrag 04.09.2026 — #67 Query-Quality-Gate der Technologie-Suche** (`docs/tech_query_gate_2026-09-04.md`):
> - Gemessen statt geraten: 26 Technologien / 25 Unsinns-/Alltagsanfragen / 8 graue Phrasen mit Live-Vektoren
>   (Fixture `tests/fixtures/tech_query_gate.json`). Nächst-Distanz, Margin und Sektions-Streuung trennen
>   NICHT; der **20. Nachbar (d20)** trennt mit Lücke (tech ≤ 0,343, Unsinn ≥ 0,381) → `D20_MAX = 0,36`;
>   zweites Signal Titel-Index (`patent_search`, GIN), drittes der Wort-Feld-Abgleich (→ `ambiguous`).
> - `pipeline/query_gate.py` + `scripts/tech_analyze.py` (Gate vor jeder Zahl, `--query --codes` = Feld-Pick,
>   Vektor-Cache), `analyze`-Route (`?q=&codes=`), `TechnologyTool` (Rückfrage mit Vorschlägen / Feldwahl).
> - Akzeptanz: 0 falsche Freigaben (25/25 Unsinn → Rückfrage), 25/26 Technologien `ok`, der 26. ist der
>   Issue-Fall „quantum error correction" → Feldwahl G06N vs. H03M; Beispiel-Chips unverändert; Gate-Overhead
>   0,03–0,33 s. 18 pytest + 8 Vitest. **Offen:** breite Ein-Wort-Begriffe („blockchain", d20 0,396) fallen
>   auf die Unsinns-Seite der Lücke; Embedding-Modellwechsel = Fixture neu messen (`scripts/measure_query_gate.py`).

> **Nachtrag 05.09.2026 — #98 Ops: Kollisionswächter, Modell-Identitäts-Check, Cleanup nur eigene Server, Embedding-Fehlerpfad** (geschlossen, 4 Commits auf `dev`, nicht gemergt):
> - **(a) Kollisionswächter** `scripts/lib/gpu_guard.sh` (`gpu_guard_wait <job> [max_min]`, Default 90 min, Poll 60 s; eigene
>   Prozesskette/tote PIDs zählen nicht) in `weekly_ingesters.sh`, `monthly_startup_sources.sh`, `full_cycle_cron.sh`,
>   `scheduled_cycle.sh` (Kopf + vor Stage 10 + Ruhezustand), `weekly_newsletter_publish.sh`, `weekly_research_pulse.sh`.
>   Skip-Verhalten: Cycle bricht mit rc=75 ab ohne VRAM-Räumung; Ingester überspringen nur die GPU-Schritte, merken das
>   `min_id`-Fenster in `data/<job>_pending_min_id` (Nachholen im Folgelauf) und schreiben `data/<job>_last.json` → Zeile
>   in der Montags-Morgen-Mail (`review_notify.py`, `blocked`/`failed` erzwingt die Mail). `weekly_patents.sh`,
>   `weekly_patent_analytics.sh`, `sync_openalex_monthly.sh` sind GPU-frei → unverändert.
> - **(b) Modell-Identitäts-Check** `llamacpp_client.chat_structured(verify_model=True)` in allen llama.cpp-Pfaden der Stages
>   2/3/4/6/8: `GET /v1/models` vor dem ersten Request (TTL 30 s) und vor jedem Retry; Mismatch → `ModelMismatchError`
>   (nie retryt, nie `None`). Stage 6 bricht ab, getroffene + folgende Einträge bleiben unprocessed, `run_full_cycle` Exit 2.
> - **(c) Cleanup nur eigene Server:** `gpu_handover.llama_server_start` vermerkt `MAINPID OWNERPID` in
>   `data/llama-server.<job>.pid` und verweigert die Übernahme eines Servers, den ein lebender anderer Job vermerkt hat;
>   `llama_server_stop` stoppt nur die vermerkte MainPID (sonst Warnung, Symlink unangetastet). Richter-Block in
>   `scheduled_cycle.sh` gleich (`llama_unit_record_owner`/`_stop_owned`). Das Head-`pkill` aller manuellen Server in
>   `full_cycle_cron.sh` bleibt, läuft aber nur bei freiem Wächter.
> - **(d) Embedding-Fehlerpfad:** `signal_batch` markiert bei Server-/Transportfehlern (Connection refused, 5xx/429,
>   Timeout) nichts mehr — gleicher Chunk erneut, nach 20 Fehlern in Folge Exit 3; `embedding_error` nur noch für
>   inhaltliche Fehler. Reparatur: `scripts/reset_embedding_errors.py [--since|--min-id|--source-type] --apply`.
> - Tests: +49 (`test_gpu_guard` 15 mit Fake-pgrep/-systemctl, `test_model_identity` 13, `test_gpu_handover_ownership` 9,
>   `test_signal_batch_embed_errors` 12); Suite 824 passed / 20 skipped. Doku: CLAUDE.md, README, owner_manual §1/§11,
>   deploy/crontab.txt. Nicht angefasst: `publish_static_site.sh` (wartet nur auf den Cycle, kein GPU-Schritt),
>   `signal_batch.free_vram_for_embeddings` (Ollama-Pfad, in keinem Cron), `draft_judge.py` (hat seinen Shell-Check).
> - Bekannte Grenze: `pgrep -f` matcht auch einen Editor/Pager mit dem Skriptnamen in der Kommandozeile (z. B. `vim
>   scripts/scheduled_cycle.sh`) — der Wächter wartet dann bis zu 90 min; Besitzvermerke gelten je Worktree (`data/`).

> **Nachtrag 06.09.2026 — Newsletter-Freigabe (Human-in-the-loop) + KI-Kennzeichnung (#16, #99)**
> (Owner-Auftrag 06.09.; Handbuch § 7.5, `NEWSLETTER_GOLIVE.md` Testschritt 7):
> - **Gate:** `newsletter_editions.approved_at/approved_by/approval_note` (additive Migration
>   `scripts/migrate_newsletter_approval.py`, auf der Live-DB gelaufen — 3 Spalten). `newsletter_sender.py`
>   bricht ohne `approved_at` mit **Exit 2** ab (auch `--latest`), `send_edition` wirft zusätzlich
>   `NotReleased`; `--force` öffnet nichts, ein Abschalter existiert bewusst nicht (Test pinnt die Flag-Liste).
>   `--dry-run` bleibt erlaubt und warnt bei fehlender Freigabe.
> - **Ansicht:** `/trends/newsletter/review` (Owner-App) — Editionsliste mit Status, Vorschau **der echten
>   Mail** (Server Action ruft `python -m pipeline.newsletter_preview`; ein Renderer `render_email_html()`
>   für Mail und Vorschau), Freigabe mit Notiz, Zurückziehen solange `sent_at` leer. Drei Sperren wie beim
>   Dossier-Desk: `BLOCKED_PREFIXES` + Proxy-Matcher, `static-export.exclude`, `canReview()` + Origin-Check.
> - **Kennzeichnung (#99):** Badges je Block (Editorial/Verticals/Deep-Dive = *AI-generated*, Radar =
>   *Computed* (SQL), Trend-Links = *Curated*, verlinkte Artikel selbst modellgeschrieben) und ein
>   Hinweissatz `AI_DISCLOSURE_EN` im Mail-Fuß **und** in der Website-Edition (Python + TS-Mirror, Drift per
>   pytest gepinnt). Anwaltstext zu Art. 50 EU AI Act bleibt offen — die interne Umsetzung steht.
> - Akzeptanz: 927 pytest / 424 vitest / tsc 0 / eslint 0 Fehler / `NEXT_DIST_DIR=.next-check` Build grün;
>   statischer Export ohne eine einzige `newsletter/review`-Datei; Smoke am echten W35: Freigabe gesetzt,
>   Sender meldet „released", Freigabe wieder zurückgezogen (DB sauber).

> **Nachtrag 06.09.2026 (2) — KI-Kennzeichnung der Feed-Artikel (#99)**
> (Owner-Fund 06.09.: die Kommission stellt klar, dass Art. 50 Abs. 4 AI Act für KI-Texte zu
> Angelegenheiten öffentlichen Interesses **ohne menschliche Kontrolle** verbindlich ist; die
> EU-Icons sind fakultativ. Handbuch § 12 „KI-Kennzeichnung der Artikel".)
> - **Warum der Feed und nicht nur der Newsletter:** die Ausgabe hat seit 06.09. eine Freigabepflicht,
>   `/trends/<slug>` nicht — dort entscheiden nur Maschinen (Grounding, Garbage/Truncation, Dedup,
>   Auto-Publish ≥ 0,85, Draft-Richter = selbst ein Modell). Umgesetzt unabhängig vom offenen Anwaltstext.
> - **Sichtbar:** `components/AiArticleDisclosure.tsx` — natives `<details>` direkt unter Titel/Meta
>   (nicht im Fuß), Kurzlabel „AI-generated / not reviewed by a person" immer lesbar, voller Satz
>   `ARTICLE_DISCLOSURE_EN` beim Aufklappen, ohne JS bedienbar, `role="note"` + `aria-label`,
>   kein Bild-Asset (EU-Icon fakultativ, nachrüstbar).
> - **Wortlaut:** „This article was generated by a local language model from the single source linked
>   below, checked automatically against that source, and published without a person reading it
>   beforehand." Jede Teilaussage an eine Pipeline-Eigenschaft gebunden; Tests pinnen die Abgrenzung
>   zu `AI_DISCLOSURE_EN` (dort „released by a person").
> - **Maschinenlesbar** (kein Standard vorhanden, pragmatisch gewählt und kommentiert):
>   `<meta name="generator">` via `metadata.other` (wird in die Layout-`other` gemerged, `tdm-*` bleiben)
>   und im Article-JSON-LD `creator` = `SoftwareApplication` + `author` = Organization + `isBasedOn`.
> - Akzeptanz: 927 pytest / 434 vitest / tsc 0 / eslint 0 / `NEXT_DIST_DIR=.next-check` Build grün;
>   statischer Export **16.925 von 16.925** Artikelseiten mit Satz, Kurzlabel, Generator-Meta und
>   `SoftwareApplication` — `tdm-reservation` unverändert vorhanden, `generator` auf Nicht-Artikelseiten
>   (Feed, Methodology, Newsletter, Landing) nicht gesetzt; Smoke an zwei Artikeln auf `:3001`.
> - Nicht angefasst: Newsletter-Konstante/-Ansicht, `/analysis`, Landing.

> **Nachtrag 19.09.2026 — Stufe 0 des Dossier-Agent-Plans (Messlatte, Runde 22)** (`docs/agentic_dossiers.md`):
> - `scripts/migrate_dossier_run_outcomes.py` auf der Live-DB ausgeführt (additiv, idempotent,
>   `dossier_run_outcomes` neu — wie `dossier_orders`/`dossiers`/`advisory_notes` **nicht in `init_db`**;
>   auf einer frischen DB von Hand nachziehen, bekannte Migrationslücke).
> - `scripts/dossier_eval.py --backfill` über alle 48 Läufe: 0 abgabereif, mean U 0,476, LFP v9 Platz 4/48;
>   perovskite v1/v2 ohne Strukturprotokoll (vor 07.09.) nicht messbar. Worker schreibt seither je Lauf.

> **Nachtrag 19.09.2026 — Stufe 1 des Dossier-Agent-Plans (Intake + Owner-Checkpoint, Runde 24)** (`docs/agentic_dossiers.md`):
> - `scripts/migrate_dossier_brief.py` auf der Live-DB ausgeführt (additiv, idempotent): `dossier_orders.brief_json /
>   plan_json / profile_json / confirmed_at / owner_note`, Status-CHECK um `awaiting_confirmation` erweitert (drop +
>   re-add) — wie die anderen Dossier-Tabellen **nicht in `init_db`**; auf einer frischen DB von Hand nachziehen
>   (`ensure_schema` legt die Spalten mit an, die CHECK-Erweiterung auf einer bestehenden Postgres-Tabelle nur das Skript).
> - Desk-Aufträge halten seither am Checkpoint (`params {"checkpoint": true}`); CLI `--order-new` und der
>   Newsletter-Deep-Dive laufen ohne Halt; `DOSSIER_CHECKPOINT=0` erzwingt aus.

> **Nachtrag 19.09.2026 — Stufe 2 des Dossier-Agent-Plans (Profilbeschaffung + Primärquellen je Feld, Runde 25)** (`docs/agentic_dossiers.md`):
> - `scripts/migrate_dossier_source_priors.py --backfill` auf der Live-DB ausgeführt (additiv, idempotent):
>   Tabelle `dossier_source_priors` (PK (field, host): n_read, n_cited, n_dropped, rank_seen, updated_at) —
>   wie die anderen Dossier-Tabellen **nicht in `init_db`**; auf einer frischen DB von Hand nachziehen. Ohne
>   Tabelle liest und schreibt der Lauf nichts (Warnung im Log, Lauf endet normal).
> - Backfill über 49 gespeicherte Läufe: 12 Felder (alte Läufe ohne Profil unter ihrem Thema), 916 Hosts,
>   84 Rang-1-Kandidaten (n_cited ≥ 2, n_dropped = 0, n_read ≥ 1). `--backfill` rechnet die Tabelle NEU
>   (löscht vorher); der Worker addiert seither je Lauf.

> **Nachtrag 19.09.2026 — Stufe 3 des Dossier-Agent-Plans (nutzenbasierter Rechercheur, Runde 26)** (`docs/agentic_dossiers.md`):
> - `scripts/migrate_dossier_query_stats.py --backfill` auf der Live-DB ausgeführt (additiv, idempotent):
>   Tabelle `dossier_query_stats` (PK (gap_kind, template): n_used, n_hits, n_admitted, n_read, n_cited,
>   updated_at) — wie die anderen Dossier-Tabellen **nicht in `init_db`**; auf einer frischen DB von Hand
>   nachziehen. Ohne Tabelle rechnet der Planer mit dem Prior 0,5 und der Lauf schreibt nichts (Hinweis im Log).
> - Backfill über 49 gespeicherte Läufe: 549 Anfragen → 542 Schablonen (audit 288, plan 254), nur 6 ≥ 2×
>   — Erfahrung entsteht erst über künftige Läufe. `--backfill` rechnet NEU (löscht vorher).
> - Neue Umgebungsvariable `DOSSIER_VOI_MIN_GAIN` (Default 0,15). `fetch_fulltext_result(max_chars=)` ist
>   ein neuer optionaler Parameter, Default unverändert (Feed-Pfad unberührt).

Vollständiges Audit aller offenen Issues in der Nacht 2026-08-28 (Referenz `main` = `a6455bf`).
Jede Aussage gegen Code, DB, crontab und die laufende Instanz (:3001) geprüft.
**Ergebnis: 14 geschlossen, 1 neu (#94) → Backlog 36 → 23 offen.**

**Die Lage hat sich seit dem 15.08. zweimal grundlegend gedreht:**
1. **Radar aus dem Produkt entfernt** (25.08., `dc8cd71`): beide Inhaltsprüfungen negativ (#90 Labels
   unverankert, #91 20/28 Platzierungen falsch). Rückweg: `feature/radar-rebase`, Plan #92.
2. **Kein SaaS mehr** (Owner 26.08., #93): keine Tarife, keine Auth, keine Zahlungen. Die Website wird
   Lead-Gen-Schaufenster (30-Tage-Feed, ~83 MB, + selbst erstellte Analysen als LinkedIn-Teaser);
   verkauft wird sales-led (Super Pro+ / Individualanalysen). Countdown: **01.10.2026**.

## ✅ Geschlossen 2026-08-28

| # | Titel (kurz) | Grund |
|---|---|---|
| #80 | OpenAlex-Snapshot + Monats-Sync | **fertig** — 45.598.470 Werke live, Cron `0 7 5 * *` aktiv, Landmark-Backfill 183/183 |
| #83 | Research-Explorer-Wertschicht | **fertig** — Stufe A+B + OA-Badge + Live-API-Paket alle in main verifiziert |
| #87 | Startup Explorer | **geshippt** — 145k Firmen / 420k Events / Brücken, Crons laufen; Reste → **#94** |
| #78 | Patent-Suchfeld 3 Stufen | **fertig** — Phrasen-Fall 0,15 s (war 22,4 s); einziger Rest: `DROP INDEX CONCURRENTLY idx_re_patent_fts;` (2,7 GB, freigabepflichtig, im Issue dokumentiert) |
| #89 | Radar heben + bewerten | **fertig** — Rebase, visuelle Fixes, Bewertung; Entscheidung gefallen (Entfernung) |
| #90 | Radar-Labels unverankert | konsolidiert → **#92 Baustein 1** |
| #91 | Horizont-Platzierungen falsch | konsolidiert → **#92 Baustein 2** |
| #17 | Monetarisierung/Stripe/Auth | überholt durch **#93** (kein SaaS; Rückbau ist Etappe 1) |
| #88 | Tier-Matrix | überholt durch **#93** (keine Tarife) |
| #64 | Pre-launch-Umbrella | überholt; überlebende P0-Punkte als Kommentar in **#93** übertragen |
| #3 | Foresight-Viz auf Signal-Space | doppelt überholt: Explorer existieren; öffentlich → PUBLIC_MODE (#93) |
| #51 | OpenAlex zitationsselektiert | Kern behoben (`--fresh` auf main); Rest (wiederkehrender Lauf) → #81 §6 |
| #46 | Firmen-Newsrooms + Social | A-Teil geliefert (15 Brand-Feeds); Reste vollständig in #81 |
| #76 | TIP/PATSTAT-Rhythmus | Prozess steht; Erinnerung → #81, Runbook im Issue; nächster Refresh ~Okt 2026 |

## 🆕 Neu: #94 — Startup-Explorer-Reste (inkrementeller Firmenstamm-Update-Pfad, LLM-Investoren-Upgrade)

## In der Audit-Nacht zusätzlich erledigt (Branch `issue-audit`, Worktree `~/projects/ct-audit`)

- **#79:** Ursache gefunden und gefixt — **beide Issue-Buckets sind derselbe Bug**: der DOCDB-Ingest
  las `classification-symbol` ohne Filter auf `classification-scheme/@scheme` und nahm Japans FI-
  (führende Editions-Ziffer, matcht zufällig das CPC-Muster) und F-Term-Codes als CPC mit. Fix:
  CPCI-Schema-Filter im Ingest + `cpc_subclass()`-Härtung + 8 Tests + Backfill-Skript
  `scripts/backfill_cpc_subclass.py` (Ausführung freigabepflichtig). Offen: Owner-Entscheid zu den
  ~4,4 M **bestehenden** F-Term-Zeilen (neue entstehen durch den Filter nicht mehr).
- **#48:** `--mark` implementiert (2-Strike-Regel, 403/429 nie markiert, Wieder-Lebendig-Löschung),
  `dead_links`-Tabelle via `scripts/migrate_dead_links.py` (**manuell auf der Live-DB ausführen**,
  bekannte Migrationslücke!), Frontend-Fallback (Archiv-Link + Hinweis; fehlt die Tabelle, degradiert
  die Seite geräuschlos), Cron-Eintrag in `deploy/crontab.txt` (Installation nach Merge).
- **#81:** drei Wächter im Monats-Check (OpenAlex-Dichte, TIP-Editions-Erinnerung, Brand-Balance —
  Brand-Anteil heute 0,06 %), CONCEPT_SHARDS-Ersatz (verifizierte OpenAlex-Concepts), **6 tote Feeds
  deaktiviert — kein einziger war reparierbar** (Details je Feed im Issue-Kommentar), CLAUDE.md-
  Quellenzahl 257 → 322. **Bonus-Befund:** `active: false` in `sources.yaml` erreicht die DB nie
  (`upsert_source` aktualisiert das Flag nicht) — 3 seit Juni deaktivierte Quellen liefen still
  weiter; `scripts/apply_source_hygiene.py` behebt das nach Freigabe (9 Zeilen).

- **#93 Etappe 1 (Kern):** `PUBLIC_MODE`-Gate gebaut (`frontend/src/proxy.ts` — Next 16 hat
  `middleware.ts` zu `proxy.ts` umbenannt!) — Flag=1 blendet alle 25 „Fällt weg"-Routen aus und
  versteckt die zugehörigen Links/Teaser; ungesetzt ändert sich nichts. Live gegen die echte DB
  verifiziert (25/25 → 404, Bleibt-öffentlich → 200). Offen: Landing-Copy, physischer
  Auth/Stripe-Rückbau, Etappe 2 (`/analysis`, `/enquiry`).
- **#93 physischer Rückbau (03.09.):** Auth (Magic-Link, Session-Cookie, `/account*`, `/api/auth/*`),
  Stripe (`/api/stripe/*`, `lib/stripe.ts` — war dependency-frei, kein npm-Paket), Tiers/Entitlements
  (`lib/tiers.ts`, `lib/entitlement.ts`, `TierGate`, `/trends/pricing`) und das 28-Tage-Paywall-Fenster
  (#70) sind aus dem Code; ebenso `scripts/migrate_accounts.py` + `set_user_tier.py`. Foresight-Seiten
  und `/api/foresight/*` sind ungegated (Owner sieht alles), `review-access.ts` = „lokal ja,
  PUBLIC_MODE/Export nie" (`REVIEW_ENABLED` entfällt), `openalex-live.ts` ohne Account-Budget.
  Blockliste `publicMode.ts`/`proxy.ts`/`static-export.exclude` nur noch Foresight + Review +
  `/api/foresight`. Landing (`page.tsx`): Preistabelle → sales-led „Access"-Sektion (→ `/enquiry`),
  Privacy ohne Account-/Payments-Abschnitte. `AUTH_SECRET` bleibt (Newsletter-Abmelde-HMAC).
  DB-Tabellen `app_users`/`magic_tokens`/`research_live_usage` bleiben ungenutzt stehen (kein DROP).
  tsc 0 Fehler (die 5 `stripe.test.ts`-Fehler sind mit der Datei weg), vitest/eslint/pytest grün.

*(Details und Testergebnisse: Commits auf `issue-audit` + Status-Kommentare in den Issues.)*

## 🔴 Welle 0 — der kritische Pfad zum 01.10. (alles andere wartet)

| Schritt | Issue | Inhalt | Aufwand |
|---|---|---|---|
| 1 | **#93** Etappe 1 | Rückbau: `PUBLIC_MODE` (9 Foresight-Routen + Auth/Stripe-APIs + Review aus der öffentlichen Instanz), Landing-Versprechen „Analysen statt Plattform" | 1–2 Tage |
| 2 | **#93** Etappe 2 | Analyse-Strecke: `/analysis`-Übersicht + `[slug]` aus MDX im Repo, OG-Bild-Pflicht, CTA → `/enquiry`-Anfragestrecke | 2–3 Tage |
| 3 | **#82** | Hosting: kleiner VPS (CX22 + Caddy) als Empfehlung, Publikations-Pfad Workstation→VPS, `nl_client_ip()`-Patch **vor** DNS-Umzug | 1 Tag + Owner (VPS, DNS) |
| 4 | **#16** | Newsletter-Versandkette scharf: Secret-Angleich (Abmeldelinks!), `export.php`-Deploy, Sync-Cron, Newsletter-Cron | ½ Tag, nach #82 |
| 5 | #93-Kommentar | Ex-#64-P0: Impressum-Übertrag, OG/Favicon, `noindex` raus, Resend-DPA | Minuten + Owner |

**Owner-Gates in Welle 0:** VPS bestellen · DNS umziehen · Resend-DPA · Impressum-Freigabe ·
Entscheidung VPS vs. statischer Export (Empfehlung: VPS, s. #82-Kommentar).

**Dazu passend:** `dev` liegt 7 Commits vor `main` (agentischer Korpus-Rechercheur / Dossier-Store) —
das ist genau das Werkzeug, das die Analysen für Etappe 2 produziert. Review + Merge-Entscheidung einplanen.

## 🟡 Welle 1 — Vertrauen im öffentlichen Feed (parallel zu Welle 0 möglich)

- **`issue-audit`-Branch reviewen + mergen** (#79/#48/#81-Code), danach die vier manuellen Schritte:
  `migrate_dead_links.py` · `backfill_cpc_subclass.py --apply` · `apply_source_hygiene.py --apply` ·
  `DROP INDEX CONCURRENTLY idx_re_patent_fts` — plus Link-Check-Cron aus `deploy/crontab.txt` installieren
- **#71** Grounding-Holds: die Halde abarbeiten (Morgenroutine, Mail läuft); der Zugriffsschutz-Punkt
  erledigt sich durch PUBLIC_MODE (Review-UI bleibt Workstation-only)
- **#11** Neumessung der 71,6-%-Benchmark nach ein paar Volltext-Nächten; danach Prompt-Eval-Harness
  **Stand 2026-09-05 (Owner-Review, Garbage + Namen):** Ursache der 22 Token-Suppen belegt
  (`chat_structured` gab nach dem Soft-Guard-Budget das letzte Ergebnis zurück) und behoben —
  harter Garbage-Guard (`pipeline/content_guard.py`) in Stage 6 (frischer Request ohne Prompt-Cache,
  nach 3 Versuchen `GarbledOutputError`, Eintrag bleibt unprocessed), Auto-Publish, Draft-Richter
  (`divert_garbled` → `review`) und Review-UI; Namens-Grounding `ungrounded_names` (2.367 Vornamen,
  Titel-Regel) in Gate/Richter/UI + Prompt-Zeile; `STAGE6_SOURCE_MAX_CHARS` (Default 4000 = alte Kappe).
  Bestandsprüfung `scripts/recheck_published_grounding.py` angewendet: 742 published → `review`
  (46 garbled, 696 Namen), 29 Drafts (Suppe), `review_reason` als Marker, Tab *Re-check* auf
  `/trends/review`; Report `docs/compliance/grounding_recheck_2026-09-05.md`. **Offen:** GPU-Repro
  `scripts/repro_stage6_garbage.py` (3 Arme) → entscheidet über `cache_prompt=false` als Stage-6-Default;
  Owner arbeitet die 831 Re-check-Zeilen ab („Donald Trump" 67× = sichere Publishes).
- **#81**-Rest: stille Quellen klären (40 Stück), ChemRxiv-Backend, The-Conversation-Backfill

## 🔵 Welle 2 — das verkaufte Produkt (nach dem Launch)

- **#92** Radar-Comeback als Analyst-Produkt: Baustein 1 Verankerung (3–5 T) → Baustein 2 Ehrlichkeit
  (3–4 T) → Baustein 3 Freigabe-UI. **Querverbindung:** die Regulatorik-Schwäche (#91) braucht harte
  Evidenz — genau das lieferte **#5** (EDGAR 8-K Material Events, Phase 1 isoliert machbar).
- ~~**#67** Query-Quality-Gate~~ — **geschlossen 24.09.2026** (s. Nachtrag oben)
- **#7**-Reste: Legal-Events-Cap aufheben, Familien-Dedup im Analyse-Layer
- ~~**#73** Research Pulse / Explorer-Refinement~~ — **geschlossen 24.09.2026** (s. Nachtrag oben). Historie: **Teil 1 + billige Refinements auf dev (2026-09-04):**
  `research_pulse` (Tabelle + Skript + Seiten + Recompute-Knopf), Explorer-Facetten (Quelle/Zeitraum/Sortierung/
  Konzept), Deep-Links aus den Theme-Seiten, Cron-Vorschlag (nicht installiert). **Werk-Typ-Filter auf dev
  (2026-09-05, Owner-Befund Zenodo-Artefakt in den Top-Papers):** Ingest-Gate (nur article/preprint/review/
  book-chapter + Repository-Blockliste), `research_signals.kind` (Migration + Backfill 19.652 artifact von 545.399),
  Pulse/Explorer filtern `kind <> artifact` (Facette `?artifacts=1`), W35 neu gerechnet (AI 5.084 → 3.836 Papers),
  Index-Duplikate im Rebuild behoben — `docs/research_pulse.md` §1a. **Offen:** Owner-Entscheid Cron vs. Knopf,
  Autoren-Enrichment + Sprach-Kennzeichnung (separat), dev→main-Merge vor dem nächsten Samstagslauf (der Cron
  läuft aus main und würde `kind` beim Rebuild auf NULL setzen), 4 W35-Texte (Quantum/Food/Energy/Education) neu
  generieren, ResearchGate-DOIs (`10.13140`) als Owner-Frage.
- **#94** Startup-Explorer-Reste

## #100 — Dossier-Tool vs. Deep Research — überholt: Feature entfernt 2026-09-19, s. Nachtrag oben (Historie 2026-09-07)

Vier DR-Läufe im Blindgutachten verloren (5,57 : 7,43 · 5,7 : 6,9 · 5,9 : 6,3 ·
5,7 : 6,9). Owner hat den Stand abgenommen, Ziel nicht mehr aktuell; DR-Modus
(Default aus) nach `main` gemergt. Diagnose: Beschaffung liefert, der
Ein-Aufruf-Schreibschritt ist der Engpass. Wiederaufnahme (kapitelweises
Schreiben zuerst) und alle Kommandos: `docs/dossier_vs_deep_research_2026-09-07.md`.

## ✅ Geschlossen 2026-09-09 — #97 Quellen-Compliance, Vorbehalts-Frage entschieden

**#101** (Vorbehalts-Journale aus OpenAlex-Abstracts neu schreiben) angelegt **und noch am selben Tag
geschlossen**: der Weg wurde durch etwas Besseres ersetzt (Volltext von der offenen Fundstelle statt
Abstract) und die zurückgezogene Kohorte ist damit trotzdem nicht zu retten — 0 von 35 verwertbar.

Vier Arbeitsstränge an einem Tag, alle auf `dev`:

- **Owner-Domainliste** (`951ccae`, `cb21193`): 181 Domains abgeglichen, die 111 möglichen geprobt
  (ok 57, feed_error 47, blocked 7, reserved 0), **39 aufgenommen**. Berichte
  `docs/compliance/source_domain_check_2026-09-09.md` + `source_probe_2026-09-09.md`.
- **Titel-Artikel-Panne** (`8aeadef`): der Purge vom 04.09. leerte die Teaser der 33 Vorbehalts-Quellen,
  ließ die Zeilen aber im Pool — am 08.09. entstanden daraus **187 published Artikel aus dem nackten
  Titel**, mit 0 Grounding-Flags, weil das Gate gegen eine leere Quelle nichts prüfen kann. Alle 278
  zurückgezogen. Drei strukturelle Guards: `MIN_SOURCE_TEXT_CHARS` (80), Backlog respektiert `active`,
  `purge --also-excerpt` stillt die Zeilen. **Nebenbefund:** `run_pipeline_batch` las nie
  `raw_content` — der ganze #11-Volltext-Apparat lief im Produktionspfad ins Leere.
- **Vorbehalts-Frage entschieden** (`1b53fc0`, `2cede8f`): Ersatz statt Rückkehr (14 OA-Journale, 13 mit
  Volltext) **plus** Signalbetrieb der 33 (`llm_pipeline: false` + neues `store_excerpt: false`).
  `apply_source_hygiene.py` synct jetzt beide Flags in beide Richtungen. **Nebenbefund:** „The Spoon"
  war YAML-aktiv und DB-inaktiv — mit dem neuen Backlog-Filter wären seine Einträge stillgelegt worden.
- **Lizenz sticht Vorbehalt** (`656537b`): `pipeline/open_license.py` + `scripts/resolve_open_licence.py`,
  Cron 03:45 installiert. Ausbeute 12 % der Einträge ≈ 58 Artikel/Woche. **Compliance-Fix im selben Zug:**
  `fetch_fulltext_result` prüfte robots/TDM nur gegen die angefragte URL — ein DOI-Link umging so die
  site-weite `tdmrep.json` von nature.com.

**Offen geblieben:** die 17 Quellen mit robots-Regel nur auf der Feed-URL (Owner-Entscheid seit 04.09.);
DESIGN (Materialforschung) und FASHION (Textilforschung) ohne OA-Ersatz, weil MDPI, Royal Society Open
Science und PeerJ den Bot-UA mit 403 sperren; die juristische Bestätigung von „Lizenz sticht Vorbehalt"
beim ohnehin befassten Anwalt.

## 🆕 #102 / #103 — Embeddings und Mega-Taxonomie (2026-09-09)

Aus der Owner-Frage „Sind die Embeddings für eine Trendanalyse ausreichend?". Zwei sofort machbare
Punkte sind erledigt: die **Dossier-Vektorsuche** läuft jetzt über einen eigenen CPU-Embedder auf
`:8091` (`7112795` — auf `:8090` hätte während des Laufs das 27B-*Chatmodell* geantwortet), und der
tote SQLite-Prototyp `discover_mega_trends.py` ist raus, der lebende Vorschlagsweg
(`propose_mega_trends.py`) dokumentiert (`ee43059`, `84734f7`).

- **#102** getrennte Volltext-Embeddings. Der einzige Vektor je Trend kommt aus
  `title + excerpt[:500]` (Median 588 Zeichen) und trägt Dedup, Distill-Heads, Pulse-Cluster und
  seit dem 09.09. die Dossier-Suche. **Dringlich**, weil `raw_content` nach 14 Tagen genullt wird —
  ein Volltext-Vektor lässt sich nicht rückwirkend rechnen.
- **#103** Mega-Taxonomie: 4 zu breite Keys (SPLIT), 17 ohne messbaren Fußabdruck. Nicht vor #102
  abschließend entscheiden (Silhouette ~0,02), die SPLIT-Kandidaten sind aber schon heute prüfbar.

Beleg für beide: `docs/mega_discovery_2026-09-09.md`.

## ⚪ Welle 3 — Forschung / bewusst ruhend

#9 Research Fronts (Substrat-Vorbehalt: Snapshot hat kein `referenced_works`) · #84 Science-Zitationsgraph
(S3-Projekt) · #85 Autoren-IDs (lokaler Archivlauf; **bei einem S3-Lauf für #84 den Beifang-Katalog aus
#85 im selben Durchgang mitnehmen**) · #86 Research-Embeddings (Empfehlung im Issue: erst echte
NPL-Links statt Ähnlichkeitsraten) · #77 Patent-Embeddings · #27 Multilingual (Schritt 1 billig,
rein lesend) · #43 `technology_domain` · #58 Spillover-Prädiktor · #59 Embedding-Domänen/Multilayer

## Systemzustand am Audit-Tag

- **Pipeline gesund:** Ventures/Research/Patents live auf :3001; Phrasen-Suche 0,15 s; Crons vollständig
  (Full Cycle Mo–Fr 04:00, Backup 02:45 mit Artefakt-Wächter, Patente Di, Ingester Sa, OpenAlex 5., Startup 6.)
- **DB:** ~446 GB; reklamierbar: `*_old`-Tabellen (~35 GB) + `idx_re_patent_fts` (2,7 GB)
- **Branches:** `main` = deployte Instanz · `dev` +7 (Korpus-Rechercheur) · `issue-audit` (diese Nacht) ·
  `feature/radar-rebase` (Radar-Rückweg, 209 vitest grün) · `feature/foresight-radar` (Alt-Stand, kann nach
  #92-Start zugunsten von `radar-rebase` aufgeräumt werden)
- **Kein Newsletter-Cron** (bewusst, #16 wartet auf Hosting)
