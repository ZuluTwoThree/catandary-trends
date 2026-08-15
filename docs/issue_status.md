# Issue-Status (Stand 2026-08-15 — Launch-Audit)

Vollständiges evidenzbasiertes Audit **aller** offenen Issues am 2026-08-15 (Referenz `main`
= `5a38f50`, gegengeprüft gegen `dev` und `feature/foresight-radar`). Jede „erledigt"-Aussage
wurde gegen Code, Datenbank, crontab und die laufenden Instanzen geprüft — nicht gegen die
Issue-Kommentare. **Ergebnis: 8 geschlossen, 2 neu → Backlog 31 → 25 offen.**

**Der Taktgeber ist der Countdown auf catandary.de: 01.09.2026, 09:00 CEST.**

## ✅ Geschlossen 2026-08-15 (verifiziert erledigt)

| # | Titel | Beleg |
|---|---|---|
| #40 | Megatrend-Taxonomie + Retrain | 28 Keys in `mega_trends.yaml`, `models/distill/meta.json` trained 2026-08-07 mit `classes: 28`, Reclassify-Zahlen alle > 0, LIFESTYLE-Abstain 6,5 % |
| #75 | PATSTAT-Runde 2 | alle 8 `tip_*`-Tabellen in der DB mit den genannten Zeilenzahlen, Frontend-Panel rendert |
| #74 | Patent Explorer | `patents/page.tsx` live, `patent_search` 19,67 M, `patent_explorer_cpc` alle ~650 Subclasses |
| #49 | Patent-Aktualität + Cron | Cron aktiv, neuestes Patent 2026-08-05, Catch-up-Kurve auf ~104 % Normalniveau, TIR-Re-Eval abgeschlossen |
| #63 | Header-Login/Logout | `Header.tsx` session-aware (Sign in / Account) |
| #66 | USP-Ehrlichkeit | Copy sagt aktiv „Method · peer-reviewed, not proprietary" (App **und** Live-Landing) |
| #44 | UX-Epic | alle vier Pakete umgesetzt (FilterBar-Collapse, Lead-Time-Story, Artikel-Typo, Signup above fold) |
| #4 | Quellen-Acquisition | CMS-Adapter + Router-Cleanup + Sitemap-Scope in main, Weekly-Ingester laufen; Reste → #81 |

## 🆕 Neu angelegt

| # | Warum |
|---|---|
| **#82** | **Public Hosting** — `catandary.de/trends` = **404**. Die Domain zeigt auf Hetzner *Webhosting* (shared Apache, kann kein Next). Die App läuft nur auf `localhost:3001`. Stand vorher in keinem Issue und blockt #64/#17/#16. |
| **#81** | Quellen-Hygiene — 6 tote Feeds, 40 stille Quellen, drei fehlende Wächter; bündelt die Kleinreste aus #4/#46/#51/#76. |

## 🔴 Welle 0 — Launch-Blocker (bis 01.09.)

| # | Was konkret fehlt | Gate |
|---|---|---|
| **#82** | Hosting-Variante entscheiden + aufsetzen. Empfehlung: kleiner Hetzner-VPS als TLS-Kopf, App + 391-GB-DB bleiben lokal, Verbindung über den bereits laufenden Tailscale-Tunnel — passt zum „runs on our local infrastructure"-Claim. Geprüfter Aufbau inkl. Caddyfile im Issue. **Vor dem DNS-Umzug Pflicht:** `nl_client_ip()` patchen, sonst speichert die DOI-Strecke die Proxy-IP statt der des Anmelders und der Einwilligungsnachweis ist wertlos. Postgres läuft zudem auf Werkseinstellungen (`shared_buffers` 128 MB bei 62 GB RAM). | Owner-Entscheid |
| **#64** | Vier P0-Punkte, drei davon Minuten-Arbeit: Impressum-Platzhalter (`imprint/page.tsx:13-15`), falscher Claim „Saved searches & alerts" (`page.tsx:431` + live), `REVIEW_ENABLED=0` für die öffentliche Umgebung, OG-Bild fehlt. | — |
| **#78/#80** | Beides fertig auf `dev`, unmerged: Patent-Ranking (Prod zahlt 22,4 s auf Phrasensuche) und der 45-M-Research-Explorer (Prod zeigt noch 510k). Ein Merge erledigt beide. | — |
| **#16** | Versandkette an vier Stellen offen: `AUTH_SECRET` in `.env` ≠ `frontend/.env.local` → **jeder Abmeldelink ungültig**; `export.php` nicht deployed; kein Sync-Cron; Abmelde-Route nicht öffentlich. | dep #82 |
| **#17** | Stripe-Testmode ist real eingerichtet (3 Prices lösen auf: 99/499/799 €). Fehlt: E2E-Beleg (braucht öffentliche Webhook-URL), Rechtstexte in der App, Admin-Rolle statt „jeder darf reviewen", Gates umlegen. | dep #82 |

## 🟡 Welle 1 — Vertrauensschulden, bevor Publikum draufschaut

| # | Restscope |
|---|---|
| #67 | Query-Gate greift nicht — reproduziert: „my cat is sad on tuesdays" → CPC *cat toilets*, `off_topic:false`. Distanzschwelle allein reicht nicht; Vorschlag Margin + Korpus-Treffer + ehrliche Rückfrage. |
| #3 | Saved Queries + Velocity-Alerts liefern (oder den Claim streichen, s. #64) + Ehrlichkeitstest auf die Landing-Copy ausweiten. |
| #48 | Link-Rot: Skript da (`check_source_links.py`), aber kein Cron und kein Frontend-Fallback für tote Backlinks. |
| #71 | Benachrichtigung läuft; offen: Zugriffsschutz (`canReview()` = true für jeden bei `AUTH_ENABLED=0`) und die Halde selbst (29 Holds, ältester 29.07.). |
| #81 | Quellen-Hygiene (s. o.). |
| #11 | Nur noch `key_implication`/`what_to_watch` — erst Eval-Harness-Variante + A/B, dann DB/Anzeige. |

## 🔵 Welle 2 — Produkt-Tiefe nach dem Launch

#73 Research Pulse (0 % umgesetzt; Explorer als Vorbedingung steht) · #9 Co-Citation Research-Fronts
(`build_research_fronts.py` fehlt; **Achtung:** der #80-Snapshot speichert kein `referenced_works`) ·
#43 `technology_domain` + domänen-gekeyte Tier-Serie (auf allen Branches unangetastet) ·
#79 5,9 M `patent_cpc`-Zeilen ohne Subclass (rein datenseitig, kein Gate) · #46 Reddit/HN-Demand-Tier

## ⚪ Welle 3 — Forschung / Ausbau

#7 Legal Events skalieren + Familien-Dedup im Analyse-Layer · #77 Patent-Embeddings (bewusst
ruhend; erbt den Patent-Signal-Embedding-Rest aus #49) · #27 Multilingual — Gate durch #35
gefallen, Schritt 1 ist billig und rein lesend · #5 EDGAR/DART/EDINET/RNS (0 % Code; Form D
gehört zu #4, nicht hierher) · #58 TIR-Spillover · #59 Embedding-Domänen + Multilayer ·
#76 PATSTAT-Editions-Rhythmus (nächster Refresh ~Okt 2026)

## Systemzustand am Audit-Tag

- **Tests grün:** 191 pytest (8 skipped) · 162 vitest (14 Dateien) · eslint sauber · `npm run build` erfolgreich · alle 18 lokalen Routen HTTP 200
- **Pipeline gesund:** Full Cycle 14.08. exit 0; 69.542 published (2.507 in 7 Tagen), 1.331.106 Signale
- **DB:** 391 GB — `research_corpus` 141 GB · `trends` 45 GB · `raw_entries` 41 GB · Patent-Layer ~125 GB. Root-FS zu 86 % voll; **35 GB in `*_old`-Tabellen** (`patent_cpc_full_old`, `patent_spnp_full_old`, `patent_spnp_full_z3_old`) sind reklamierbar. `~/logs` = 11 GB ohne Rotation.
- **Quellen:** 325 aktiv (CLAUDE.md nennt noch 257 — in #81 zum Nachziehen vermerkt)
- **Branches:** `main` = deployte Instanz (:3001); `dev` liegt vor main (#78 Stufe 3 + #80-Strecke); `feature/foresight-radar` geparkt (39 Commits) und enthält **keinen** Restscope aus #3/#43/#58/#59
- **Nicht-Blocker, aber Hygiene:** `tsc --noEmit` meldet 7 Fehler — 2 aus stale `.next/dev`-Typen (gelöschte Route `trends/cross-vertical`), 5 aus `stripe.test.ts` (`/s`-Regex-Flag bei `target: ES2017`). Beide harmlos, beide in einer Minute weg.
