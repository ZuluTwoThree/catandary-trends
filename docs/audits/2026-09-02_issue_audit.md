# Issue-Audit 2026-09-02 — 24 offene Issues gegen Code / DB / Cron / laufende Instanzen

Referenz: Worktree `/home/dirk/projects/ct-dev`, Branch `dev` @ `21b3059` (= `main` @ `6ad36bb` + 1 Commit).
Read-only-Audit. Jede Aussage unten ist mit Datei:Zeile, Kommando oder DB-Abfrage belegt; Issue-Texte
wurden nur als Soll-Liste benutzt, nicht als Ist-Beleg.

Rahmen (Owner 02.09.): kein SaaS (#93), **statischer Export aufs bestehende Hetzner-Webhosting** als
Ziel-Hosting, Owner-App = `:3001` (main), Countdown 01.10., Budget knapp → Priorität vor Vollständigkeit.

Laufende Instanzen (verifiziert per `ss -tlnp`, `/proc/<pid>/environ`, curl):
- `:3001` = systemd `catandary-frontend`, cwd `/home/dirk/projects/catandary-trends/frontend` (main), **kein** PUBLIC_MODE
- `:3004` = `next dev` aus `ct-dev` (dev), **kein** PUBLIC_MODE (Foresight/Pricing = 200) — nur `/trends/review` 404 (REVIEW_ENABLED ungesetzt)
- `:3999` = `next dev` aus `ct-dev`, `PUBLIC_MODE=1`, `NEXT_DIST_DIR=.next-public` → das ist die PUBLIC_MODE-Vorschau (nicht :3004)

---

## 1. Übersichtstabelle

| # | Titel (kurz) | Ist-Stand (verifiziert) | Fehlt | Relevanz | Aufwand | Empfehlung |
|---|---|---|---|---|---|---|
| **#93** | Website → Lead-Gen-Schaufenster | Gate (`proxy.ts`), 30-Tage-Fenster, `/analysis` + `/enquiry`, OG/Favicon, Impressum: **gebaut** | Landing-Copy (6 tote Links auf :3999), 1. echte Analyse, LinkedIn-URL, physischer Auth/Stripe-Rückbau (im statischen Export **Pflicht**, Gate greift dort nicht), noindex, Resend-DPA | WEBSITE-01.10 | M | **JETZT** |
| **#82** | Public Hosting | VPS-Runbook + PHP-Proxy-Patch vorbereitet; `export_public_slice.py` fehlt; kein `output: export` | Kompletter Export-Pfad: 8 `force-dynamic`-Seiten, `searchParams`-Suche, `/api/newsletter`, `/api/track`, Unsubscribe serverseitig → alles ersetzen; Upload-Pfad | WEBSITE-01.10 | M–L | **JETZT** (Issue neu schneiden: statischer Export; VPS-Teil + `nl_client_ip`-Patch OBSOLET) |
| **#16** | Newsletter-Versandkette | Sender fertig; Website-Edition-Cron aktiv (W33–W35); W32 einmal versendet (12.08.) an den 1 Abonnenten | AUTH_SECRET-Angleich (Hash-Diff bestätigt), `NL_EXPORT_*` fehlen, `export.php` live 404, `sync_subscribers.py` nicht in `scripts/`, `PUBLIC_BASE_URL`=localhost, Unsubscribe-Weg für statisches Hosting (PHP-Paket hat **kein** unsubscribe.php) | WEBSITE-01.10 (Lead-Magnet), Versand selbst DANACH | S (Secrets) + M (Export-Umbau) | **JETZT** (nur Secret/URL-Angleich + Unsubscribe-Entscheid), Versand-Cron DANACH |
| **#96** | Newsletter-Deep-Dive (27B) | 0 % — kein `deep_dive`-Feld, kein Code (`grep` = nur Prosa in `analysis/page.tsx`) | alles (Phasen 1–3) | SPÄTER | L | OWNER-ENTSCHEID (Start nach 01.10.; hängt an #95) |
| **#95** | Korpus-Rechercheur Tests + Frontend | `corpus_research.py` mit `--company/--focus/--lang` **liegt in main** (FF-Merge 01.09.); 6 Dossiers in DB; Frontend-Desk nur auf `origin/Agentic-Dossiers` (2 Commits, Basis `e675595` = vor `--company` → Konflikt real) | Abnahmekriterien, de-Streichungsquote, weitere Domänen; Agentic-Dossiers-Rebase | OWNER-APP | M | DANACH |
| **#92** | Radar-Comeback | unverändert: `radar_cells` 2.430 / **0 Overrides**; `feature/radar-rebase` 30 Commits (letzter 25.08.), main 39 Commits weiter → Rebase nötig | Bausteine 1–3 komplett | SPÄTER | L (10–15 T) | DANACH (nur bei Kundenauftrag) |
| #86 | Research-Embeddings | 0 % (keine Embedding-Spalte in `research_corpus`) | alles | SPÄTER | L | DANACH (ruhend) |
| #85 | Autoren-/Instituts-IDs | 0 % (`research_work_author`/`research_authors` fehlen) | alles | SPÄTER | L | DANACH (ruhend) |
| #84 | Paper-Zitationsgraph | 0 %; `research_corpus` hat **keine** `referenced_works`-Spalte (Substrat fehlt) | alles | SPÄTER | L | DANACH (ruhend) |
| **#81** | Quellen-Hygiene | Hygiene **angewandt** (9 Quellen `active=false`, 323 aktiv), 3 Wächter im Code, OpenAlex-Fresh im Samstagslauf, CONCEPT_SHARDS-Fix | **Bug:** OpenAlex-Wächter crasht unter Postgres (s. u.); stille Quellen (§2), ChemRxiv, CMS-Probe, TC-Backfill, Reddit/HN | OWNER-APP | S (Bugfix) / M (Reste) | **JETZT** nur Bugfix (S), Rest DANACH |
| **#79** | patent_cpc ohne Subclass | Ingest-Filter (`ingest_patents.py:600` CPCI), `cpc_subclass` gehärtet, **Backfill ausgeführt** (NULL 5,91 M → 4.421.765 = exakt F-Term-Rest) | nur Owner-Entscheid zu 4,4 M F-Term-Zeilen | OWNER-APP | S | **SCHLIESSEN** (Owner-Entscheid „liegen lassen, dokumentiert") |
| #77 | Patent-Embeddings | 0 % (keine `patent*`-Embedding-Spalte) | alles | SPÄTER | L | DANACH (ruhend) |
| #73 | Research Pulse | 0 % Pulse; Autoren nur als Anzeige (`AuthorLine`), kein Index/Suche | alles | SPÄTER (Owner-Werkzeug) | M–L | DANACH |
| **#71** | Grounding-Holds Review | Mail läuft (`full_cycle_cron.sh:60`), `/trends/review` gebaut, Queue = **1** (Log 01.09.: „0 held today, 1 total"), PUBLIC_MODE → 404 (auf :3999 verifiziert) | nichts Wesentliches | OWNER-APP | — | **SCHLIESSEN** |
| #67 | Query-Quality-Gate | unverändert `OFF_TOPIC_DIST = 0.55` (`tech_analyze.py:41,175`) | Margin/Korpus-Signal | SPÄTER (Owner-Werkzeug) | S–M | DANACH |
| #59 | Embedding-Domänen/Multilayer | 0 % (grep leer) | alles | SPÄTER | L | DANACH (ruhend) |
| #58 | Spillover-Prädiktor | 0 % (grep leer) | alles | SPÄTER | L | DANACH (ruhend) |
| **#48** | Source-Link-Integrität | `--mark` da, `dead_links` migriert (**124 Zeilen**), Cron **installiert + gelaufen** (02.09. 07:03: 12 bestätigt tot), Frontend-Fallback (`deadLinks.ts`, `TrendArticle.tsx`) | nichts | OWNER-APP + WEBSITE | — | **SCHLIESSEN** (+ CLAUDE.md-Zeile korrigieren) |
| #43 | CPC feine Codes Ripple | unverändert: `TechContext.tsx:60` Einzelwert, `tir/route.ts:40` Subklassen-Regex, `build_cpc_tier_series.py:113` Subclass, kein `technology_domain` | Rest-Ripple | SPÄTER | L | DANACH (ruhend) |
| #27 | Multilingual Patente | 0 %; `data/multilingual_patent_audit.md` fehlt | Datencheck (S), Stufen 1+2 | SPÄTER | S+L | DANACH |
| #11 | Content-Qualität | alles bis auf `key_implication/what_to_watch` (grep leer); Volltext-Fix 25.08. drin | Neumessung 71,6 %-Benchmark (kein neues Doc seit 21.08.), Report-Felder | OWNER-APP | S / M | DANACH; nach Neumessung schließen |
| #9 | OpenAlex Graph-Layer | 3,5/4; Research Fronts fehlen (kein Skript, keine Tabelle) | `build_research_fronts.py` | SPÄTER | M | DANACH (ruhend) |
| #7 | Patent-Layer Ausbau | ~70 %: Familien/Assignees da; Legal Events **Pilot unverändert** (10.359); kein Family-Dedup in `tir_metrics`/`tir_graph`; Full-Text skip (`ingest_patents.py:382`) | Legal-Cap, Dedup, Full-Text, CQL | SPÄTER | L | DANACH (splitten) |
| #5 | Regulatory Disclosures | 0 % (`ingest_disclosures.py` fehlt; einzige Treffer = Form D/Company-Norm) | Phase 1 EDGAR | SPÄTER | M | DANACH |

---

## 2. Priorisierte JETZT-Reihenfolge (Budget-Sicht)

1. **#82 neu schneiden → statischer Export.** Entscheidung ist gefallen, das Runbook (`docs/launch/HOSTING_PUBLIC_VPS.md`) beschreibt das Gegenteil und markiert den Export explizit als „verworfen". Zu bauen: Export-Build (`output: "export"`, `force-dynamic` aus 8 öffentlichen Seiten raus, `generateStaticParams` für `trends/[slug]` + `mega/[m]`, Sitemap statisch), Suche `?q=` client-seitig oder streichen, Newsletter-Signup auf die vorhandene PHP-DOI-Strecke umbiegen, Editions-Liste als Build-JSON, `/api/track` raus, Unsubscribe-Weg (s. #16), Upload nach dem 04:00-Cycle. **Der `nl_client_ip()`-Proxy-Patch entfällt komplett** (kein Proxy vor dem Webhosting). Aufwand M–L (1–2 Tage).
2. **#93 Rest.** Landing-Copy: `frontend/src/app/page.tsx:77,268,288` → `/trends/foresight*`, `:431,452,475` → `/trends/pricing` — auf `:3999` sind das **6 tote Links** (curl-verifiziert). Im statischen Export ist das Gate (`proxy.ts`) wirkungslos → geblockte Routen dürfen gar nicht erst gebaut werden (physischer Rückbau oder Build-Ausschluss wird Pflicht). Erste echte Analyse (heute nur `_template.md`), LinkedIn-URL, `noindex` (Live-Landing hat es noch, `preview.html:7`), Resend-DPA (Owner).
3. **#16 Minimal.** AUTH_SECRET angleichen (Owner, 5 min), `PUBLIC_BASE_URL` (aktuell `localhost:3004` in `.env`, `localhost:3001` in `.env.local`), `export.php` hochladen (Owner), `sync_subscribers.py` nach `scripts/`; **Entscheid Unsubscribe im statischen Hosting** (PHP `unsubscribe.php` bauen oder Resend-gehostete Abmeldung) — ohne das darf kein Versand an Fremdadressen raus.
4. **#81 Bugfix (S):** `monthly_source_check.py:270` `LIKE 'OpenAlex%'` → unter psycopg2 mit Parametern `IndexError` (Log 01.09. 08:00). Die drei neuen Wächter sind produktiv **nie gelaufen**; Fix = `%%` oder Parameter.

Alles andere: DANACH. Schließen: **#48, #71, #79** (nach Owner-Entscheid F-Terms).

---

## 3. Detailabschnitte

### #93 — Website-Umbau
- **(a) Ist:** `frontend/src/proxy.ts` (Next-16-Name für middleware) blockt `/account*`, `/trends/foresight*`, `/trends/review*`, `/trends/quality-preview*`, `/trends/pricing`, `/api/auth*`, `/api/stripe*`, `/api/foresight*`; auf `:3999` (PUBLIC_MODE=1) verifiziert: alle → 404, `/trends`, `/analysis`, `/enquiry`, `/trends/newsletter` → 200. 30-Tage-Fenster: `lib/entitlement.ts:49` `PUBLIC_ARCHIVE_DAYS = 30`, Artikel außerhalb → 404 (`181fcaf`). Routen `app/analysis/page.tsx`, `app/analysis/[slug]/page.tsx` (mit `generateStaticParams`, draft-Gate), `app/enquiry/page.tsx` (mailto v1). `app/opengraph-image.tsx` + `app/icon.tsx` (kein `public/`-Ordner — Assets sind generierte Routen). Impressum: echter Betreiberblock (`imprint/page.tsx:12`). `lib/nav.ts:17` zeigt „Analyses". DB: 19.516 published Artikel in den letzten 30 Tagen.
- **(b) Fehlt:** Landing-Copy/Links (s. o.), erste Analyse (`content/analyses/` enthält nur `_template.md`), LinkedIn-URL (`enquiry/page.tsx:89` nur Text), physischer Rückbau (noch vorhanden: `lib/auth.ts`, `stripe.ts`, `tiers.ts`, `entitlement.ts`, `CheckoutButton/CheckoutSuccessBanner/LogoutButton/SignInForm/TierGate.tsx`, 5 API-Routen auth/stripe, `app/account*`, `app/trends/pricing`), `noindex`, Resend-DPA, Owner-Entscheid Punkt 1 (30 Tage vs. Archiv indexiert).
- **(c)** WEBSITE-01.10. **(d)** M. **(e)** #82 (Export-Pfad bestimmt, ob Gate oder Build-Ausschluss). **(f) JETZT** — ohne Landing-Fix geht die Site mit sechs toten Links live; im statischen Export müssen die geblockten Routen physisch raus.
- **Static-Export-Wirkung:** Etappe 6 „Deploy auf kleinsten VPS" entfällt. `PUBLIC_MODE` bleibt als Build-Flag sinnvoll (Nav/Teaser-Ausblendung in 13 Dateien), aber die Route-Sperre muss zur Build-Zeit passieren.

### #82 — Public Hosting
- **(a) Ist:** `docs/launch/HOSTING_PUBLIC_VPS.md` (VPS CX22, Export „verworfen"), `deploy/Caddyfile`, `deploy/deploy.sh` (nennt PM2 — stale), PHP-Paket mit `NL_TRUSTED_PROXIES`-Fix. `scripts/export_public_slice.py` **fehlt**. `next.config.ts`: kein `output`, nur `distDir` per Env (`21b3059`). Live: `catandary.de/` 200 (statische Landing, `noindex`), `catandary.de/trends` weiterhin 404 (Webhosting). Postgres: `shared_buffers=160 MB`, `random_page_cost=4`, `work_mem=4 MB` (Defaults, nur Owner-App-relevant).
- **(b) Fehlt (für statischen Export):** `export const dynamic = "force-dynamic"` in `page.tsx:12`, `trends/(feed)/page.tsx:25`, `trends/[slug]/page.tsx:15`, `mega/page.tsx:6`, `mega/[megatrend]/page.tsx:10`, `methodology/page.tsx:4`, `sitemap.ts:5`, `newsletter/unsubscribe/page.tsx:5`; `searchParams` in Feed (`:28-32`, Suche `?q=`) und Unsubscribe; Client-Fetches `/api/newsletter` (Signup POST + Editions GET, `newsletter/page.tsx:98,262,274,275`), `/api/track` (`TrendArticle.tsx:42`); `trends/[slug]` ohne `generateStaticParams`; `robots.ts` verweist auf `catandary.de/sitemap.xml` (ok). Vorhanden und nutzbar: PHP-DOI-Strecke auf dem Webhosting (`subscribe.php`, `confirm.php`, `cron.php`).
- **(c)** WEBSITE-01.10. **(d)** M–L. **(e)** #93 (Rückbau), #16 (Unsubscribe). **(f) JETZT** — Launch-Blocker; VPS-Runbook als verworfen markieren, `nl_client_ip`-Patch als obsolet streichen (kein Proxy).

### #16 — Newsletter-Automatisierung
- **(a) Ist:** `pipeline/newsletter_sender.py` (Resend-Batch, HMAC-Unsubscribe, `--latest`, `--dry-run`; **kein** Test-Empfänger-Flag), `pipeline/newsletter_generator.py`; Cron `0 9 * * 1 weekly_newsletter_publish.sh` **aktiv** (DB: Editionen 26/27/28 = W33/W34/W35, W35 am 31.08., `sent_at NULL`); Edition 25 (W32) hat `sent_at 2026-08-12` → einmal real versendet. `newsletter_subscribers`: 1 Zeile, `confirmed=true`. `docs/launch/newsletter-doi-php/NEWSLETTER_GOLIVE.md` (9 Schritte) + `EINBAU.md` vorhanden. `.env` ohne `NL_EXPORT_URL/TOKEN` (grep = 0). `AUTH_SECRET` `.env` ≠ `frontend/.env.local` (sha256-Präfixe `aa52…` vs `0c50…`). `https://catandary.de/newsletter/export.php` → **404**. `scripts/sync_subscribers.py` fehlt (nur Referenzkopie im PHP-Paket). Nebenfund #95 bestätigt: `weekly_newsletter_publish.sh:79` hängt `start-active.sh` auf Gemma und stellt nichts zurück (kein zweites `ln -sfn`, kein `trap`).
- **(b) Fehlt:** Schritte 1–5 der GOLIVE-Liste; zusätzlich durch statischen Export: `trends/newsletter/unsubscribe/page.tsx:30` macht ein DB-UPDATE serverseitig → im Export unmöglich → PHP-`unsubscribe.php` (fehlt im Paket) oder Resend-Unsubscribe; Signup-Formular muss auf `subscribe.php` zeigen statt `/api/newsletter`.
- **(c)** WEBSITE-01.10 für Signup/Abmeldung; Versand DANACH. **(d)** S (Secrets/URLs) + M (Unsubscribe/Signup-Umbau). **(e)** #82. **(f) JETZT** für Secret-Angleich + Unsubscribe-Entscheid (rechtlich heikelster Punkt), Versand-Cron erst nach Testversand mit Abmeldeklick.

### #96 — Newsletter-Deep-Dive
- **(a)** `newsletter_editions`-Spalten: id, year, week, editorial, vertical_summaries, mega_trend_radar, trend_refs, total_signals, created_at, sent_at, recipients_count — **kein** `deep_dive`. `git grep deep_dive` trifft nur Prosa. Rechercheur-Baustein existiert (`corpus_research.py --foresight`, 27B-Swap-Muster in `draft_judge.py`).
- **(b)** Alles. **(c)** SPÄTER. **(d)** L (3 Phasen ≈ 3–4 Tage). **(e)** #95-Freigabe, #16-Versand, GPU-Fenster Montag. **(f) OWNER-ENTSCHEID** — Startfrage im Issue offen; bei knappem Budget nicht vor 01.10.

### #95 — Korpus-Rechercheur
- **(a)** `scripts/corpus_research.py:1462-1482` hat `--foresight`, `--company`, `--lang`, `--focus`, `--slug`, `--web-steps`; Commits `5c0e982`/`5770060` sind in **main** (FF-Merge 01.09.) — der „nicht vor Release mergen"-Hold ist faktisch überholt; Code ist CLI-only/inert. DB `dossiers`: 6 Zeilen (precision-fermentation-dairy v1–v3, askea-feinmechanik v1–v3, alle Qwen3.8-27B). Frontend-Desk `/trends/dossiers` nur auf `origin/Agentic-Dossiers` (`d90f822`, `6b4bf0a`, 01.09.), Basis `e675595` = **vor** `--company/--focus`; dessen `corpus_research.py` kennt beide Flags nicht (grep = 0) und weicht um −648 Zeilen ab → Konflikt real. `dossier_orders`-Tabelle existiert nicht (Migration nur auf dem Branch).
- **(b)** Abnahmekriterien, Streichungsquote `lang=de`, weitere Domänen, Rebase + Merge-Entscheid Agentic-Dossiers, Frontend-Integration.
- **(c)** OWNER-APP. **(d)** M. **(e)** GPU-Fenster (27B), Owner-Freigabe. **(f) DANACH** — Owner hat 02.09. „nicht mergen" gesagt; erst Rebase auf main.

### #92 — Radar-Comeback
- **(a)** `radar_cells`: 2.430 Zeilen, **0** `override_horizon`. `feature/radar-rebase` @ `35f179d` (25.08.), 30 Commits vor main; main 39 Commits weiter → erneuter Rebase. `scripts/radar_query.py` nur dort.
- **(b)** Bausteine 1–3. **(c)** SPÄTER. **(d)** L. **(e)** Kundenauftrag. **(f) DANACH** — Produktionswerkzeug pro Individualanalyse, kein Launch-Bezug.

### #86 / #85 / #84 / #77 — Research-/Patent-Embeddings, Autoren-IDs, Zitationsgraph
- **(a)** `information_schema`: keine Embedding-Spalte an `research_corpus`, keine an `patent*`; keine `research_work_author`/`research_authors`/`research_fronts`; `research_corpus` ohne `referenced_works` (grep auf `%referenced%` = 0) → #84-Substrat fehlt weiterhin. Kein 0.6B-Benchmark-Artefakt.
- **(b)** Alles. **(c)** SPÄTER. **(d)** L je Issue. **(e)** GPU-Tage, HDD-Platz, #77↔#86-Entscheid. **(f) DANACH (ruhend)** — Forschung ohne Launch- oder Owner-App-Bezug.

### #81 — Quellen-Hygiene
- **(a)** DB: `count(*) FROM sources WHERE active` = **323**; alle 9 Hygiene-Quellen (BMJ, Environmental Leader, Euractiv, Förderinfo Mobilität, Healthcare IT News, MobiHealthNews, Rock Health Blog, Shopify News, WorkLife) `active=false` → `apply_source_hygiene.py --apply` ist gelaufen. Wächter: `monthly_source_check.py:69` `BRAND_SHARE_ALERT`, `:72` `PATSTAT_REMINDER_MONTHS`, `:217ff` OpenAlex-Dichte. OpenAlex-Fresh im Samstagslauf (`weekly_ingesters.sh:58-59`), Patent-Signale (`:94 --patents-only`). Monats-Check 01.09. gelaufen, Issue-Kommentar gepostet (#13).
- **Bug (neu):** Log `~/logs/catandary-source-check.log` 01.09. 08:00: `Traceback … monthly_source_check.py:269 check_openalex_density … psycopg2 … IndexError: tuple index out of range`. Ursache `:270` `s.name LIKE 'OpenAlex%'` mit Parametern — Postgres-Treiber interpretiert `%` als Platzhalter; Tests laufen auf SQLite (conftest) und sehen es nicht. Folge: Wächter 5–7 (OpenAlex, TIP-Erinnerung, Brand-Balance) sind produktiv nie ausgeführt worden.
- **(b)** Bugfix; §2 stille Quellen (Log zeigt FAIL: IFPRI, EE Times 403, Inside Climate 403, New Scientist 406 …), ChemRxiv, CMS-Probe, TC-Backfill, Reddit/HN.
- **(c)** OWNER-APP. **(d)** S (Fix) / M (Reste). **(f) JETZT** Bugfix; Reste DANACH; CLAUDE.md-Zahl 322/319 → 323 korrigieren.

### #79 — patent_cpc Subclass
- **(a)** `scripts/ingest_patents.py:593-600` filtert auf `scheme=="CPCI"`; `SELECT count(*) FROM patent_cpc WHERE subclass IS NULL` = **4.421.765** (vorher 5.912.584; Differenz 1,49 M = exakt der Parse-Fehler-Bucket) → `backfill_cpc_subclass.py --apply` wurde ausgeführt; Stichprobe `subclass IS NULL AND cpc ~ '^\d[A-HY]\d{2}[A-Z]'` liefert 0 Zeilen.
- **(b)** Owner-Entscheid F-Terms (raus/kennzeichnen). **(c)** OWNER-APP. **(d)** S. **(f) SCHLIESSEN** mit Vermerk „F-Terms bleiben, neue entstehen nicht mehr".

### #73 — Research Pulse
- **(a)** kein `research_pulse`-Code; `research_signals` ohne Autoren-Spalte; Explorer zeigt `AuthorLine` aus API-Parsing (`research/page.tsx:10,90`). **(b)** alles. **(c)** SPÄTER (Owner-Werkzeug seit #93). **(d)** M–L. **(f) DANACH**.

### #71 — Grounding-Holds
- **(a)** `scripts/full_cycle_cron.sh:60` ruft `scripts.review_notify`; Logs: 26.08.–01.09. „queue: 0–5 held today, 1–6 total, oldest 2026-07-29"; DB heute: 1 Draft ≥0,85. `lib/review-access.ts:19-23` (`REVIEW_ENABLED` → `AUTH_ENABLED` → Session); PUBLIC_MODE → `/trends/review` 404 (`:3999` verifiziert); im statischen Export existiert die Route ohnehin nicht. `trends.reviewed_at` + `judged_at` vorhanden.
- **(b)** nichts (Verfallsregel optional). **(f) SCHLIESSEN**.

### #67 — Query-Quality-Gate
- **(a)** `scripts/tech_analyze.py:41` `OFF_TOPIC_DIST = 0.55`, `:175` reine Distanzprüfung; kein Margin/Korpus-Signal. **(c)** SPÄTER (Foresight-Werkzeug nur intern). **(d)** S–M. **(f) DANACH**.

### #59 / #58 — TIR-Methodik
- **(a)** `git grep -i spillover|pichler|fitness.landscape|multilayer|network_time` in scripts/pipeline/frontend = 0. **(f) DANACH (ruhend)**, L.

### #48 — Source-Link-Integrität
- **(a)** `scripts/check_source_links.py:134 --mark`; DB-Tabelle `dead_links` = 124 Zeilen; Crontab: `0 7 2 * * … check_source_links.py --per-source 12 --mark` **installiert**, Log 02.09. 07:03: „55 erster Fehlschlag, 12 bestätigt tot, 0 wieder lebendig"; Frontend `lib/deadLinks.ts`, `TrendArticle.tsx` (Hinweis + web.archive.org), `trends/[slug]/page.tsx:2` `isSourceLinkDead` (serverseitig → im statischen Export zur Build-Zeit ausgewertet, funktioniert).
- **(b)** nichts; Politik implementiert. **(f) SCHLIESSEN**. Doku: CLAUDE.md:516 „noch NICHT in die echte crontab installiert" ist falsch.

### #43 — CPC-Ripple
- **(a)** `TechContext.tsx:60-63` Einzelwert `tir_pct`; `api/foresight/tir/route.ts:40` `^[A-H][0-9]{2}[A-Z]$`; `build_cpc_tier_series.py:113-120` `pc.subclass`; `technology_domain`/`cpc_tier_series_fine`/`domain_tier_series` = 0 Treffer; keine pytest auf benannte Domänen. **(f) DANACH (ruhend)**, L.

### #27 — Multilingual
- **(a)** `data/multilingual_patent_audit.md` fehlt; `patent_title_translations` = 0 Treffer; nur `scripts/test_multilingual_embed.py`. **(b)** Datencheck (S, rein lesend) → Go/No-Go. **(f) DANACH**.

### #11 — Content-Qualität
- **(a)** `key_implication|what_to_watch` = 0 Code-Treffer; Volltext/Grounding/Prompt v2/Harness in main; neuestes Eval-Doc `confidence_threshold_entscheidung_2026-08-21.md`; Draft-Richter-Zahlen laufen (Log 01.09.: 75 released / 212 held). **(b)** Neumessung 71,6 %, Report-Felder. **(c)** OWNER-APP. **(d)** S / M. **(f) DANACH**, nach Neumessung schließen.

### #9 — OpenAlex Graph-Layer
- **(a)** `build_research_fronts|research_fronts` = 0 Treffer; `openalex_citations` existiert. **(b)** Research Fronts. **(f) DANACH (ruhend)**, M; Substrat-Vorbehalt (#84) bleibt.

### #7 — Patent-Layer
- **(a)** `patent_family`, `patent_assignee_raw`, `patent_legal_events` (**10.359** Zeilen — Pilot unverändert), `tip_leading_applicants` vorhanden; `grep -i family scripts/tir_metrics.py tir_graph.py` = 0; `ingest_patents.py:382` skips claims/description. **(b)** Legal-Cap, Family-Dedup im Analyse-Layer, Full-Text, CQL. **(f) DANACH** (splitten), L.

### #5 — Regulatory Disclosures
- **(a)** `scripts/ingest_disclosures.py` fehlt; `edgar|edinet|8-K`-Treffer nur in `company_norm.py`, `startup_resolution.py`, `ingest_secform_d.py` (Form D ≠ 8-K). **(f) DANACH**, M (Phase 1).

---

## 4. Doku-Drift (CLAUDE.md / README / docs vs. Realität)

| Stelle | Doku sagt | Realität |
|---|---|---|
| CLAUDE.md:516 (Cron-Block) | Link-Check-Cron „noch NICHT in die echte crontab installiert" | `crontab -l`: `0 7 2 * * … check_source_links.py --mark` installiert, lief 02.09. |
| CLAUDE.md:155-156, 878 | 322 aktive Quellen; „DB-Flag-Schreibvorgang noch NICHT ausgeführt"; „nach voller Anwendung 319" | `apply_source_hygiene.py --apply` ist gelaufen; DB = **323** |
| CLAUDE.md:593 | „Hosting: Hetzner VPS (bestehend)" | Es gibt keinen VPS; catandary.de = Hetzner-Webhosting (statische Landing); Ziel = statischer Export |
| CLAUDE.md:592, 646-648 | Auth/Paywall/Stripe als Tech-Stack; Routing mit `/trends/pricing`, `/account` | Code noch da, aber per #93 zum Rückbau bestimmt; PUBLIC_MODE-Gate nirgends in CLAUDE.md erwähnt |
| CLAUDE.md:868 | „Deployment auf Hetzner — Caddy + PM2" | systemd seit #38; `deploy/deploy.sh` nennt weiterhin PM2 (`:29,37,39`) |
| CLAUDE.md:919-920 | „Ollama läuft als Windows-Exe", Windows-Python-Pfad | Linux-Workstation, llama.cpp produktiv |
| CLAUDE.md Cron-Block | fehlt: `monthly_startup_sources.sh` (6. 12:00) steht drin, ok; aber `deploy/crontab.txt` ≠ live | `deploy/crontab.txt`: ohne `monthly_startup_sources`, ohne `cycle_watchdog`, `--keep-days 7` statt 4 |
| docs/issue_status.md (28.08.) | „Kein Newsletter-Cron"; „dev +7 (Rechercheur)"; `issue-audit`-Branch; 4 manuelle DB-Schritte offen | Website-Edition-Cron seit 29.08.; Rechercheur in main; `issue-audit` gemergt/gelöscht; `migrate_dead_links` ✓, `apply_source_hygiene` ✓, `backfill_cpc_subclass` ✓, `idx_re_patent_fts` gedroppt ✓ (`pg_indexes` = 0) — alle vier erledigt |
| docs/launch/HOSTING_PUBLIC_VPS.md | VPS-Empfehlung, Export „verworfen" | Owner-Entscheid 02.09.: statischer Export |
| docs/launch/newsletter-doi-php/NEWSLETTER_GOLIVE.md Schritt 7 | `NL_TRUSTED_PROXIES` auf VPS-IP | entfällt ohne Proxy |
| README.md:267, 404 | „behind deploy/Caddyfile", „Hetzner deployment" als aktiver Fokus | kein Caddy im Einsatz; Hosting-Ziel geändert |
| Memory/Task-Text | „:3004 = PUBLIC_MODE-Vorschau" | `:3999` ist die PUBLIC_MODE-Instanz; `:3004` läuft ohne Flag |
| CLAUDE.md „Reklamierbar" (issue_status) | `*_old`-Tabellen ~35 GB | weiterhin da: `patent_cpc_full_old` 27 GB, `patent_spnp_full_old` 4,4 GB, `patent_spnp_full_z3_old` 4,4 GB; DB 448 GB |

---

## 5. Uncommittete / unfertige Arbeit auf `dev`, Branch-Lage

- `git status`: nur `frontend/tsconfig.json` modifiziert (fügt `.next-public/types/**` zu `include` hinzu — gehört zu `21b3059`, harmlos, sollte committed werden).
- `dev` vs `main`: **1 Commit** (`21b3059` distDir per `NEXT_DIST_DIR`). Kein Stash.
- `origin/Agentic-Dossiers`: 2 Commits (01.09.), Basis `e675595`, 29 Dateien / +2.538 −648; `corpus_research.py` dort ohne `--company/--focus` → Konflikt mit main sicher. Owner: nicht mergen (02.09.).
- `feature/radar-rebase` (`/home/dirk/projects/ct-radar`): 30 Commits, letzter 25.08.; main 39 Commits weiter.
- Worktrees: `/catandary-trends`=main (`:3001`), `/ct-dev`=dev (`:3004`, `:3999`), `/ct-radar`=radar-rebase.
- Drei `next dev`-Prozesse aus `ct-dev` (einer seit 16 Tagen) — nicht kritisch, aber Ressourcen.

---

## 6. Test-Suiten (heute ausgeführt, GPU unberührt: SQLite-conftest, LLM gemockt)

- **pytest:** `358 passed, 17 skipped in 11.7 s` (ohne `tests/test_extract_press_rounds_investors.py`, das laut Docstring ebenfalls mockt — vorsorglich ausgelassen; 28.08.-Doku: 336). 
- **vitest:** `20 files, 287 passed` (28.08.-Doku: 285).
- **tsc --noEmit:** **5 Fehler**, alle `src/lib/stripe.test.ts` TS1501 (Regex-Flag `/s` bei `target: ES2017`); Datei seit 19.07. unverändert → kein Regressionsbefund, `next build`/CI offenbar nicht betroffen; erledigt sich mit dem Stripe-Rückbau (#93).
- `npm run lint`/`next build` nicht ausgeführt (Zeitbudget).

---

## 7. Die wichtigsten Überraschungen

1. **Die vier „manuellen" DB-Schritte aus dem 28.08.-Audit sind alle erledigt** (dead_links + Cron aktiv, Hygiene angewandt, CPC-Backfill, GIN-Index gedroppt) — CLAUDE.md/issue_status.md behaupten das Gegenteil. #48/#71/#79 sind damit schließbar.
2. **Statischer Export hebelt das PUBLIC_MODE-Gate aus** (`proxy.ts` läuft nur serverseitig) und kollidiert mit 8 `force-dynamic`-Seiten, der `?q=`-Suche, `/api/newsletter`, `/api/track` und der serverseitigen Unsubscribe-Route; dafür wird der komplette `nl_client_ip`-Proxy-Patch (#82/#16) obsolet.
3. **Produktionsbug #81:** OpenAlex-Wächter crasht unter psycopg2 (`LIKE 'OpenAlex%'`), Lauf 01.09. abgebrochen — SQLite-Tests verdecken es.
4. Landing auf der PUBLIC_MODE-Vorschau hat 6 tote Links; `newsletter_editions` W32 wurde am 12.08. real versendet (an den einzigen Abonnenten); AUTH_SECRET-Diff besteht seit 15.08. unverändert.
