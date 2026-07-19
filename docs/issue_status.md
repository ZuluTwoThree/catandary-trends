# Issue-Status (Stand 2026-07-19)

Übersicht der offenen GitHub-Issues. **Merge-Status:** Das Alpha-Epic ist inzwischen
**vollständig in `dev`** — `epic/alpha` ist ein direkter Vorfahr von `dev` (0 eigene
Commits, 32 dahinter). Ein Merge epic/alpha→dev ist ein No-op; der Branch kann
nachgezogen oder gelöscht werden. Seit dem letzten Stand (14.7.) kam die
**TIR-Vertiefung** (geschlossenes Zitiernetz, MIT-Kalibrierung, cited-Prädiktor
live) plus die Alpha-Review-Fixes (#52–#56) und neue Backlog-Issues hinzu.

## 🟢 Inhaltlich fertig — schließbar

| # | Titel | Stand |
|---|---|---|
| **#45** | TIR-Daten-Genauigkeit (Age-3-Cap z-Score) | **Original-Scope erledigt UND deutlich übertroffen.** fullz3 Default; dazu seit 15.7.: geschlossenes Zitiernetz (113,6M Kanten), substrat-bewusster TRUNC, MIT-Kalibrierung, **cited-Prädiktor scharf** (R² 0,574 vs 0,521, Kontrollgruppe 10/11). Der Kern („Kompositions-Drift neutralisieren") ist erledigt → schließbar. Restarbeit (temporale Konstruktion, WS2 PageRank) lebt in `docs/tir_reliability_plan.md`/`tir_cited_predictor.md`. |
| **#2** | Foresight-Engine v1 | Kern komplett + verifiziert (`pipeline/foresight.py`: `window_bounds`/`build_lineage`, GLP-1-validiert, 2 Bugs gefixt). Rest (S-Kurven-Fit, Alt-Skript-Archiv) = Politur. Schließbar. |
| **#13** | Quellen-Qualität | `scripts/monthly_source_check.py` + Cron (`deploy/crontab.txt`, 1./Monat 08:00, `--post-issue`) automatisiert, Erstreport gepostet (41 Alerts). Schließbar **oder** als lebendes Quality-Log offen lassen (Owner-Wahl). |

## 🟡 Gebaut (in dev) — wartet auf Owner-Gates / externes Setup

| # | Titel | Was fehlt (keine Merges) |
|---|---|---|
| **#17** | Monetarisierung | Auth+Entitlement+Stripe+Rechtstexte flag-gegated. Fehlt: Stripe-Account, Resend-DNS, Preispunkte. |
| **#3** | Foresight-Viz | Radar + Evolution + Export/Dossier fertig. Offen: Workbench (Saved Queries/Velocity-Alerts). |
| **#16** | Newsletter-Automatisierung | Sender + Unsubscribe + Cron fertig. Fehlt: Resend-DNS-Verifizierung. |
| **#44** | UX-Überarbeitung | Landing „What's moving" fertig. Offen: Owner-UX-Review (Filter-Bar, Lead-Time-Grafik, Lesbarkeit). |
| **#40** | Mega-Taxonomie LIFESTYLE | 3 Kandidaten fertig. Fehlt: Owner-Label-Kuratierung → Retrain + Reclassify. |

## 🔵 Neu seit 14.7. — TIR-Vertiefung + Alpha-Review-Fixes

| # | Titel | Stand |
|---|---|---|
| **#57** | Wettbewerbs-/IP-Analyse TIR | **Fertig** (GetFocus/TechNext auf SPNP, Patent US12099572B2 kein EU-Blocker, unsere Methode nicht patentierbar). Referenz-Issue → schließbar oder als Doku offen. |
| **#49/#50** | BDDS-Patent-Aktualität + Wochen-Cron | Backlog aufgeholt + Cron gebaut (`weekly_patents.sh`, Dichte-Wächter m-3). Prüfen ob schließbar. |
| **#52/#53/#54** | Fixes: embedding_1024, source_lead_time_tier, Interval-Filter | Prod-hygiene aus dem Alpha-Review — offen, prio-high. |
| **#55/#56** | Trajectory-API gaten/rate-limiten · /api/search bounden | Ops/Sicherheit — offen. |
| **#58** | TIR-Prädiktor: Spillover (Pichler & Lafond) | Neu, Backlog (echte Methoden-Erweiterung, +20-28% OOS). |
| **#59** | TIR-Domänen: Embedding-Landscape + Multilayer | Neu, Backlog (überlappt #43/#9). |
| **#47/#48** | Content-Reparatur 30B-Ära · Source-Link-Integrität | offen. |
| **#60** | Newsletter-Ausgaben erzeugen (ohne Versand) | **Erledigt 2026-07-19:** Lücke W22–W29 rückwirkend generiert (Backend llama.cpp, geladenes Qwen3.6-35B auf :8090), `newsletter_editions` damit lückenlos W15–W29, HTML/JSON-Previews unter `data/newsletters/` (`latest.html` = W29). Kein Versand — `newsletter_sender.py` unangetastet, kein Resend-Call. Schließbar. |

## 🔴 Backlog-Folge-Features

#4 (Quellen-Acquisition), #5 (Regulatory Disclosures), #7 (Patent-Layer), #9/#51
(OpenAlex-Layer — #51: Korpus zitationsselektiert, erst lösen), #11 (Content-Volltext),
#27 (Multilingualer Patent-Korpus), #43 (CPC feine Codes), #46 (Firmen-Newsrooms).

## Zusammenfassung
- **3 schließbar:** #45 (übertroffen), #2, #13 · dazu #57 (Referenz) evtl. schließbar.
- **5 Owner-Gates:** #17, #3, #16, #44, #40 (extern: Stripe/Resend; Owner: UX/Labels).
- **Prod-Hygiene offen:** #52, #53, #54, #55, #56.
- **Backlog:** #4, #5, #7, #9/#51, #11, #27, #43, #46, #47, #48, #58, #59.
- **Kein Issue blockiert die Alpha** — sie hängt an externem Setup + Owner-Entscheidungen.
