# Issue-Status (Stand 2026-08-28 — Audit nach dem Geschäftsmodell-Wechsel)

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
- **#81**-Rest: stille Quellen klären (40 Stück), ChemRxiv-Backend, The-Conversation-Backfill

## 🔵 Welle 2 — das verkaufte Produkt (nach dem Launch)

- **#92** Radar-Comeback als Analyst-Produkt: Baustein 1 Verankerung (3–5 T) → Baustein 2 Ehrlichkeit
  (3–4 T) → Baustein 3 Freigabe-UI. **Querverbindung:** die Regulatorik-Schwäche (#91) braucht harte
  Evidenz — genau das lieferte **#5** (EDGAR 8-K Material Events, Phase 1 isoliert machbar).
- **#67** Query-Quality-Gate (Analysten-Werkzeugqualität; Heuristik + LLM-Graubereich)
- **#7**-Reste: Legal-Events-Cap aufheben, Familien-Dedup im Analyse-Layer
- **#73** Research Pulse / Explorer-Refinement — nach realem Analystenbedarf priorisieren
- **#94** Startup-Explorer-Reste

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
