# Issue-Status (Stand 2026-07-23 — nach Backlog-Audit)

Vollständiges evidenzbasiertes Audit **aller** offenen Issues am 2026-07-23 (Referenz
`main`=`5902e51`, „erledigt"-Basis = main **+ dev + offene PRs**, Union über
`UI_UX_Audit`=`62c610d`). Jede Close/Done-Aussage wurde adversarial gegengeprüft.
**Ergebnis:** 4 geschlossen, 5 auf Restscope reduziert, 1 neu (#66) → Backlog **24 → 21 offen**.
Jedes offene Issue hat on-GitHub einen Audit-Kommentar mit Restscope + Akzeptanzkriterien + DoR/DoD.

## ✅ Geschlossen 2026-07-23 (verifiziert erledigt)

| # | Titel | Beleg |
|---|---|---|
| #13 | Quellen-Qualität | `scripts/monthly_source_check.py` + Monats-Cron (`0 8 1 * *`), alle 4 Checks, Erstbericht gepostet |
| #47 | Content-Reparatur 30B-Ära | `scripts/regen_published.py`, 4 Batches, Audit 44,0% → 3,1% (DoD <10%) |
| #50 | Wöchentl. BDDS-Patent-Cron | `scripts/weekly_patents.sh` live, Lauf 2026-07-21 exit 0, Dichte 124% |
| #57 | Wettbewerbs-/IP-Analyse TIR | GetFocus/TechNext = identische SPNP-Methode, US12099572B2 kein EU-Blocker → **Folge #66** |

*(Bereits vor diesem Audit geschlossen: #2, #45, #52–#56, #60.)*

## 🟡 Auf Restscope reduziert (near-complete, Kern in main)

| # | Restscope |
|---|---|
| #3 | Radar/Evolution/Dossier live; offen: **Saved Queries + Velocity-Alerts** (dep #17/#16, localStorage-only startbar) + `tiers.ts`-Ehrlichkeitsfix |
| #4 | Ingester-Baukasten in main; offen: **CMS-Adapter** (Ghost/Substack/Arc/Drupal) + Router-Cleanup in `probe_source_apis` |
| #11 | Volltext-Fetch aktiv; offen: **reichere Extraktion** + neue Felder `key_implication`/`what_to_watch` |
| #40 | 1/3 Kandidat in main, Head inert; offen: **Reclassify → Retrain** (Head auf 22 Klassen) · **[P1]** |
| #43 | K(t)-Kern in main; offen: **`technology_domain`** + additive feine/domänen-gekeyte Tier-Serie + Frontend-Reihe |

## 🔴 Launch-Bündel (P1, teils `blocked` = Owner-/Extern-Gate)

| # | Stand |
|---|---|
| #64 | Umbrella-Launch. main `/`=307→/trends, `/imprint`+`/privacy`=**404**, Gates OFF. dep #44/#17/#16/#63/#66 · **[blocked]** |
| #63 | Header-Login/Logout-Fix nur auf `UI_UX_Audit` (`5bc8ef2`) → **Merge nach main** |
| #17 | Stack gehärtet, flag-OFF; offen: **Stripe-E2E-Test + Rechtstexte live + Gates AN** · **[blocked]** |
| #44 | Landing/Newsletter live; offen: FilterBar-Collapse + Lead-Time-Grafik + Owner-UX-Review |
| #16 | Sender fertig, Resend-DNS geklärt; offen: **Cron scharf + realer Sende-Beleg** (braucht Abonnenten) · **[blocked]** |
| #66 | **NEU** — kein Methoden-USP (Folge #57) → öffentliche Copy auf Kalibrierung/Korpus/GTM umstellen (gate #64) |

## 🔵 Vertrauen/Daten (vor Launch-Claims umsetzen)

| # | Restscope |
|---|---|
| #49 | Backfile aufgeholt. **SPNP-Substrate-Rebuild ERLEDIGT** — `patent_spnp_full` neu gebaut **16.07** (auf `extended_graph_cache`, 42,58M Knoten; Vorgänger → `patent_spnp_full_old`), cited-Substrat `patent_citedspnp_full_z3` **18.07**; Graph = **145,5M Kanten** (Staging, 259,6M roh → 56,1 % strictly-backward), NICHT „vom 06.07". Offen nur noch: TIR-Re-Eval (**läuft aktiv**, Direction-Holdout/Ablationen 24.07) + Catch-up-Kurve verifizieren + `--kind amend`-Nutzen. · **[P1→P2]** |
| #51 | Befund code-bestätigt (zitationsselektiert); offen: **zitationsfreier Frisch-Sweep** als eigener Ingest-Modus |
| #9 | Graph-Layer/Velocity/Fusion in main; offen: **Co-Citation Research-Fronts** (`build_research_fronts.py`, dep #51) |

## ⚪ Backlog (Akquise / Forschung)

#5 Regulatory Disclosures (EDGAR/DART/EDINET/RNS — voll offen) · #7 Patent-Layer (Legal
Events/Assignee/Family-Dedup/OPS-Citations) · #27 Multilingual Patent (Datencheck → CJK-Embedding,
dep #35) · #46 Firmen-Newsrooms + Demand-Tier (dep #11/#4) · #48 Publisher-Link-Rot-Politik +
Frontend-Fallback · #58 TIR-Spillover (Pichler & Lafond) · #59 Embedding-Domänen + Multilayer (dep #43/#9/#58)

## Umsetzungs-Wellen

- **Welle 0 (Vertrauen, vor Launch-Claims):** #51 (#49-Substrate erledigt; TIR-Re-Eval läuft)
- **Welle 1 (Launch, P1):** #66 → #63 → #44 → #17 → #16 → #64  · Enabler: `dev` → `main` + Rebuild (dev trägt jetzt UX-Sweep + #63)
- **Welle 2 (Foresight-Kern):** #9, #3, #43, #40
- **Welle 3 (Qualität/Akquise):** #11, #48, #4, #46
- **Welle 4 (Forschung):** #5, #7, #27, #58, #59

## Branch-Hinweis (Stand 24.07)

`UI_UX_Audit` wurde **in `dev` gemergt und gelöscht** — `dev` trägt jetzt den UX-Sweep inkl.
Rechtsseiten (`/imprint`+`/privacy`) und den **#63-Header-Fix** (`5bc8ef2`). `main` ist über Nacht
um ~12 Commits (TIR-Paper-Analysen + MIT-Benchmark + UX-Audit-Fixes, „from dev") vorgezogen, hat
aber den **#63-Fix noch nicht** (`/`=307, `/imprint`=404 auf main). Für den Public-Launch daher
**`dev` → `main` mergen** (dev ist jetzt der Superset), dann `main` bauen +
`systemctl --user restart catandary-frontend`. `dev`/`main` divergieren (Cherry-picks „from dev").
