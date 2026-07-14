# Issue-Status (Stand 2026-07-14)

Übersicht aller offenen GitHub-Issues nach der Alpha-Epic-Arbeit. **Wichtig:** Fast
alle „erledigten" Deliverables liegen auf Branch `epic/alpha` und sind noch **nicht
nach `main` gemergt** — daher formal offen. Merge nach `dev` läuft (2026-07-14).

## 🟢 Inhaltlich fertig — schließbar (bzw. nach Merge)

| # | Titel | Stand |
|---|---|---|
| **#45** | TIR Age-3-Cap z-Score | fullz3 als Default, Richtungs-Labels entfernt, Karten neu gebaut, verifiziert. Schließbar. |
| **#2** | Foresight-Engine v1 | Kern komplett: Cluster-Lineage (GLP-1-validiert), Noise-Weighting, Mega-Review. Rest (S-Kurven-Fit, Alt-Skript-Archiv) = Politur. Schließbar. |
| **#13** | Quellen-Qualität | `monthly_source_check.py` + Cron automatisiert, erster Report gepostet (41 Alerts). Schließbar oder als lebendes Quality-Log offen lassen. |

## 🟡 Gebaut auf `epic/alpha` — wartet auf Owner-Gates / Merge

| # | Titel | Was fehlt |
|---|---|---|
| **#17** | Monetarisierung | Auth+Entitlement+Stripe+Rechtstexte gebaut (flag-gegated). Fehlt: Stripe-Account, Resend-DNS, Preispunkte, Prod-Merge. |
| **#3** | Foresight-Viz | Radar + Evolution + Export/Dossier fertig. Offen: Workbench (Saved Queries/Velocity-Alerts). |
| **#16** | Newsletter-Automatisierung | Sender + Unsubscribe + Cron-Zeile fertig. Fehlt: Resend-DNS-Verifizierung. |
| **#44** | UX-Überarbeitung | Landing „What's moving" fertig. Offen (Owner-UX-Review): Filter-Bar einklappen, Lead-Time-Story-Grafik, Artikel-Lesbarkeit. |
| **#40** | Mega-Taxonomie LIFESTYLE | 3 Kandidaten fertig (`lifestyle_mega.candidate.yaml`). Fehlt: Owner-Label-Kuratierung → Retrain + Reclassify. |

## 🔴 Echte offene Folge-Features (Pläne liegen als Issue-Kommentare)

| # | Titel | Umfang |
|---|---|---|
| **#4** | Quellen-Acquisition | Market-Backfill war schon erledigt. Offen: CMS-Verallgemeinerung, OpenAlex-Concept-Expansion, Brand-Newsrooms, pytrends. |
| **#5** | Regulatory Disclosures | EDGAR-efts entsperrt (Blocker weg), Plan da — Ingester nicht gebaut. |
| **#7** | Patent-Layer | EPO-OPS-Credentials funktionieren (verifiziert). Offen: Assignee-Persistenz, INPADOC Legal Events, Family-Dedup. |
| **#9** | OpenAlex Graph-Layer | Nur noch Research Fronts (Co-Citation-Cluster). |
| **#11** | Content-Qualität | Grounding-Gate live. Offen: Volltext-Fetcher (wartet auf trafilatura-Dep-Entscheidung), reiche Extraktion. |
| **#27** | Multilingualer Patent-Korpus | Gated auf #35-Swap. Datencheck (lohnt sich CJK-Embed?) zuerst. |
| **#43** | CPC-Ripple (feine Codes) | On-Demand-Pfad + Karten auf main; fullz3 jetzt Default. Rest: `technology_domain`-Tabelle, feine Tier-Serien. |

## Zusammenfassung
- **3 schließbar:** #45, #2, #13
- **5 warten auf Owner-Gates/Merge:** #17, #3, #16, #44, #40
- **7 Folge-Features fürs Backlog:** #4, #5, #7, #9, #11, #27, #43
- **Kein Issue blockiert die Alpha.**
