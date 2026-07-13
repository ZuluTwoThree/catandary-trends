# Epic-Plan: Von heute zur kundenzeigbaren Alpha

Stand 2026-07-13. Synthese aus den Plänen aller 19 offenen Issues (Kommentare vom 2026-07-13) plus übergreifenden Lücken, die kein Issue abdeckt. Kriterium jeder Aufgabe: **umsetzbar durch Code-Agent-Harnesses** (Claude Code + Subagents) mit klar markierten Owner-Gates.

**Owner-Entscheidungen (2026-07-13):** Stripe-Testmode reicht für die Alpha · Radar UND Lineage gehören rein · Market-Backfill jetzt (GPU-Nächte einplanen) · Zielsegment = **alle drei** (B2B-Innovationsteams + Agenturen/Berater + Prosumer) → Saved Queries/Alerts + Export sind Alpha-Scope (W3.6/3.7).

---

## 1. Alpha-Definition — was ein Kunde sieht

Ein Prospect bekommt einen Link auf catandary.de/trends und kann ohne Anleitung:

1. **Landen und Wert sehen:** „Was sich gerade bewegt"-Streifen (steigende Cluster), ehrlicher Korpus-Zähler (1,1M Signale), Lead-Time-Story-Grafik — in 10 Sekunden ist klar, was das Produkt kann.
2. **Foresight erleben:** Cluster-Explorer → **Trend-Radar** (der Deliverable-Standard im Foresight-Markt) → Technology Explorer mit K(t)-Trajektorie → Lead-Time-Ansicht. Jede Zahl mit klickbarer Evidenz (Primärquelle/Patent).
3. **Trend-Evolution sehen:** Cluster-Lineage (Emergenz/Split/Merge über Zeitfenster) — das Feature, das „wir sehen Trends früher" beweisbar macht.
4. **Account anlegen** (Magic-Link), Tier-Gating erleben (Free-Teaser → Starter/Pro-Inhalte), einen Checkout im **Stripe-Testmode** durchspielen.
5. **Newsletter abonnieren und wirklich erhalten** (Resend, Montag 09:00).
6. **Vertrauen fassen:** Methodik-Seite, Grounding-Gate (keine erfundenen Zahlen), publizierte Validierungsergebnisse.

Dazu unsichtbar, aber alpha-kritisch: die Plattform überlebt einen Reboot, Cycles laufen beaufsichtigungsfrei, Qualität wird monatlich automatisch gemessen.

**Bewusst NICHT in der Alpha:** Live-Zahlungen (Testmode reicht zum Zeigen), #5 Disclosures, #7 Patent-Enrichment, #27 Multilingual, #4-Restkanäle (außer Market-Backfill-Klassifikation, s. W1.4), API-Zugang (Super Pro+ bleibt „coming soon").

---

## 2. Arbeitswellen

Aufwandseinheit: **AB = Arbeitsblock** ≈ eine fokussierte Agent-Session (halber Tag Äquivalent). Kalenderzeit wird von Owner-Gates und Nacht-Compute dominiert, nicht von Codierzeit.

### Welle 0 — Fundament & Hygiene (2–3 AB, sofort startbar)

| # | Aufgabe | Quelle | AB | Gate |
|---|---|---|---|---|
| 0.1 | systemd-Units für Frontend 3001 (+optional 3002), Linger prüfen, Deploy-Doku, pm2-Leiche entfernen | #38 | 0,5 | — |
| 0.2 | Working-Tree-Hygiene: `train_distill_heads.py`-Diff sichten/committen, Candidate-YAMLs versionieren | #40-Vorarbeit | 0,5 | — |
| 0.3 | `monthly_source_check.py` (Pass-Rate + Vertical-Balance + Feed-Health + RSS≪WP-Detektor) + Cron + Auto-Kommentar in #13; einmalige Neumessung | #13 | 1 | — |
| 0.4 | Hybrid-Cycle-Beobachtung abschließen (Kennzahlen aus 2–3 Nacht-Cycles, CLAUDE.md-Pipeline-Doku aktualisieren) → #41 schließen | #41 | 0,5 | — |
| 0.5 | #28 + #35 formal schließen (Abgleiche liegen als Kommentare vor) | — | 0,1 | Owner-OK |
| 0.6 | `epic/alpha`-Branch anlegen + **Restore-Test** des DB-Backups (Leitplanke 1) | 2c | 0,5 | — |

### Welle 1 — Foresight-Produktkern (7–9 AB + 2 Nacht-Compute-Jobs)

| # | Aufgabe | Quelle | AB | Gate |
|---|---|---|---|---|
| 1.1 | **Cluster-Lineage** (Engine `window_bounds`/`lineage`, 3 Tabellen, CLI, Tests, Known-Trend-Validierung GLP-1) | #2 Ph.1 | 2–3 | Validierung = Launch-Gate |
| 1.2 | **Trend-Radar** `/trends/foresight/radar` (SVG, Tier-Ringe, Momentum-Farbe, Vertical-Segmente, Drilldown) + Read-API; Tier-gescopte Snapshot-Läufe | #3 S.1 | 2 | Owner-Screenshot-Review |
| 1.3 | **Evolution-Ansicht** (Lineage-Graph im Frontend: Emergenz/Split/Merge-Zeitstrahl, liest `foresight_lineage_*`) | #3←#2 | 1,5 | nach 1.1 |
| 1.4 | **Market-Backfill-Klassifikation** der ~236k historischen trade_media-Einträge (Distill, GPU-Nachtslots) → Tier-Serien-Rebuild → „Market beginnt 2020"-Kante weg | #4 S.1 | 0,5 aktiv + 2–3 Nächte | Owner: GPU-Slot |
| 1.5 | **TIR z3-Build** (`--randomize 100 --age-cap 3`, ~2,4 h) + Rekalibrierung + 4-Kriterien-Validierung + dreiarmige Entscheidung | #45 | 1 + 1 Nacht | Akzeptanzkriterien fix |
| 1.6 | **Mega-Taxonomie LIFESTYLE** (Kuratierung aus Candidates, Head-Retrain, Abstain-Refix, Messung) | #40 | 1,5 | Owner: finale Label-Auswahl |
| 1.7 | Noise-Weighting in die Engine (`source_weights` in `analyze()`, `--noise-weight`-Flag) | #2 Ph.2 | 1 | — |

### Welle 2 — Kunden-Schale (7–9 AB, Owner-Gates parallel anstoßen!)

| # | Aufgabe | Quelle | AB | Gate |
|---|---|---|---|---|
| 2.1 | **Auth.js Magic-Link** + users/sessions-Schema + Email-Gate am Mehrwert-Drilldown | #17 Ph.1 | 2 | Owner: **Resend-Account + DNS (SPF/DKIM)** |
| 2.2 | **Entitlement-Schicht** (`users.tier`, serverseitiges Gating aller `/api/foresight/*`, Free-Teaser-Definition, Admin-Override für Pilotkunden) | #17 Ph.2 | 1,5 | Owner: Feature-Matrix-Abnahme |
| 2.3 | **Stripe Testmode** (Checkout, Portal, Webhook→tier, 3 Prices) | #17 Ph.3 | 1,5 | Owner: **Stripe-Account** (früh beantragen!), Preispunkte |
| 2.4 | **Pricing-Seite** mit echten (Testmode-)Buttons + Trust-Verlinkung | #17 Ph.4 | 0,5 | — |
| 2.5 | **Newsletter-Versand** (`newsletter_sender.py`, Unsubscribe/List-Unsubscribe, Idempotenz, Cron Mo 09:00) | #16 | 1,5 | teilt Gate mit 2.1 |
| 2.6 | **Landing value-first** (Bewegungs-Streifen, Sub-Hero, Filter-Collapse) + Lead-Time-Story-Grafik + Newsletter-Conversion-Umbau | #44 P.1/2/4 | 2 | Owner-Screenshot-Review |
| 2.7 | **Rechtstexte einbinden** (Impressum/Datenschutz/AGB/Widerruf — Pflicht ab Accounts+Checkout in DE) | neu | 0,5 | Owner: **Texte liefern/freigeben** |

### Welle 3 — Vertrauens-Feinschliff + Segment-Features + Alpha-Abnahme (8–10 AB)

| # | Aufgabe | Quelle | AB | Gate |
|---|---|---|---|---|
| 3.1 | **Volltext-Fetch** (trafilatura, robots.txt, opt-in je Quelle) + A/B-Messlauf (Fabrikationsrate) | #11 S.1 | 2 | Owner: Quellen-Opt-in-Liste |
| 3.2 | Reichere Extraktion + `key_implication`/`what_to_watch` (Report-only → bei bestätigter Qualität DB+Anzeige) | #11 S.2/3, #44 P.3 | 1,5 | A/B-Ergebnis |
| 3.3 | Artikel-Lesbarkeit + „Was das bedeutet"-Zeile | #44 P.3 | 0,5 | — |
| 3.4 | **Research Fronts** (Co-Citation) als Korroborations-Badge im Cluster-Explorer | #9 | 1,5 | optional für Alpha |
| 3.6 | **Workbench Stufe 1:** Saved Queries (account-gebunden, nutzt 2.1) + Velocity-Alerts (Batch-Delta zwischen Snapshot-Läufen → Badge) | #3 S.2 | 2 | Segment Agenturen/Prosumer |
| 3.7 | **Export:** Cluster-/Technology-Ansicht als CSV + druckfähige Dossier-Seite (Print-CSS, kein PDF-Stack) | #3 Ph.3 (vorgezogen) | 1 | Segment Agenturen |
| 3.5 | **Alpha-E2E-Abnahme:** Demo-Drehbuch je Segment (3 Varianten der Prospect-Journey), 2 Seed-Accounts je Tier, Smoke-Test-Suite gegen Prod, Uptime-/Reboot-Probe, Checkliste in `docs/alpha_checklist.md` | neu | 1 | Owner: Demo-Durchlauf |
| 3.8 | **UX-Qualitäts-Gate mit Optimierungsloop** (s. Abschnitt 2a — muss bestanden sein, bevor das Epic abgeschlossen werden kann) | Owner-Vorgabe | 1–3 (loopabhängig) | Gate-Kriterien fix |

### Welle 3a — UX-Qualitäts-Gate (Pflicht-Gate vor Epic-Abschluss)

**Bewerter: der Code-Agent (Claude).** Nach Abschluss der W2/W3-Feature-Arbeit läuft ein strukturierter UX-Audit über **alle kundensichtbaren Seiten** (Landing, Artikel, alle Foresight-Ansichten, Radar, Lineage, Pricing, Newsletter, Auth-Flows) — auf dem Dev-Server, screenshot-gestützt, Desktop + Mobile-Viewport, Light + Dark.

**Bewertungsrubrik (je Seite 1–5, Gate = keine Seite unter 4):**
1. **Niederschwelligkeit** (Owner-Vorgabe): fertige Default-Ansicht, kein leerer Zustand, kein Pflicht-Filter, max. ein sichtbarer Scope-Umschalter
2. **Klartext statt Jargon:** jede Kennzahl in einem verständlichen Satz („steigt seit 6 Monaten, 11 Quellen"), keine unerklärten Abkürzungen
3. **Evidenz einen Klick entfernt:** jede Behauptung führt zu einer Primärquelle
4. **Wert in 10 Sekunden:** versteht ein Erstbesucher ohne Anleitung, was er sieht und warum es nützlich ist
5. **Handwerk:** responsive ohne Overflow, lesbare Kontraste, konsistente Navigation, Ladeverhalten, keine toten Enden

**Optimierungsloop:** Scort eine Seite <4 → konkrete Findings dokumentieren (`docs/ux_gate_report.md`) → fixen → Re-Audit **derselben Rubrik**. Loop wiederholt sich, bis alle Seiten ≥4 sind; jede Iteration wird im Report versioniert. Erst dann gilt das Epic als abschließbar. Owner kann den finalen Report jederzeit überstimmen/verschärfen — das Gate ersetzt nicht den Owner-Review vor Prod-Merges (der bleibt), es erzwingt ein systematisches Qualitätsniveau davor.

### Welle 4 — Rollout & Lead-Generierung (3–4 AB + laufende Owner-Aktivität)

| # | Aufgabe | AB | Gate |
|---|---|---|---|
| 4.1 | **Rollout-Stufenplan:** (a) internes Go (Alpha-Checkliste + UX-Gate bestanden) → (b) **Pilot-Phase**: 3–5 handverlesene Kontakte mit Seed-Accounts (Admin-Override, kein Zahlungszwang), strukturiertes Feedback-Formular → (c) öffentliche Alpha (Pricing sichtbar, Testmode-Hinweis) → (d) Live-Zahlungen als separater Post-Alpha-Schritt | 0,5 | Owner: Pilot-Kontakte |
| 4.2 | **Lead-Funnel scharf schalten:** Email-Gate-Conversion-Punkte (aus 2.1) mit Tracking-Events belegen (`/api/track` existiert), UTM-Konvention, Conversion-Dashboard (einfache interne Seite: Signups/Woche, Gate-Konversion, Newsletter-Wachstum) | 1 | — |
| 4.3 | **Lead-Magnet-Content:** 1–2 „Foresight-Brief"-Beispieldossiers (aus echten Radar-/Lineage-Daten, via 3.7-Export) als gated Download; Newsletter-Doppelnutzung (Auszug öffentlich, Volltext per Signup) | 1 | Owner: Themenwahl |
| 4.4 | **SEO-/Share-Grundlagen:** OG-Images für Foresight-Seiten (Radar-Snapshot als Share-Bild!), Sitemap/robots prüfen, Meta-Descriptions der Top-Routen, Ladezeit-Check | 1 | — |
| 4.5 | **Outreach-Assets** (Owner führt Outreach, Agent baut Material): 1-Pager je Segment (aus den 3 Demo-Drehbüchern), Demo-Video-Skript, LinkedIn-Post-Serie als Entwürfe | 0,5 | Owner: Versand/Posting |

**Parallelisierung mit Subagents:** Welle 1 (Pipeline/Python) und Welle 2 (Frontend/TS) sind weitgehend disjunkt → zwei Worktree-Subagents parallel möglich (z. B. 1.1 Engine + 2.1 Auth). Serialisiert werden muss alles, was die Postgres schreibt (1.4, 1.5, 1.6 → nacheinander in Nachtslots) und jeder Prod-Merge. Explore-Agents für Read-only-Audits (z. B. 3.5-Smoke-Inventar).

---

## 2c. Branch-Strategie + Nicht-vergessen-Leitplanken (Owner-Vorgabe 2026-07-13)

**Branch:** Das gesamte Epic wird auf einer eigenen Branch **`epic/alpha`** (abgezweigt von `dev`) umgesetzt.
- **Wöchentlich `dev` in `epic/alpha` nachziehen** (dort landen weiter Cycle-/Hotfixes) — verhindert Drift und den Big-Bang-Merge am Ende.
- **Wellenweise Merges** `epic/alpha` → `dev` → `main` hinter **Feature-Flags/Env-Gates** (Muster: `TIR_SUBSTRATE`, `RSS_CLASSIFY_MODE`; neu z. B. `AUTH_ENABLED`, `PAYWALL_ENABLED`) — halbfertige Auth/Paid-Features sind auf Prod nie sichtbar, jeder Merge bleibt einzeln revertierbar. `main` bleibt der deploybare „Save".

**Leitplanken (keinesfalls vergessen):**
1. **Branch isoliert nur Code — DB/GPU/Crons sind geteilt:** Alle Schema-Änderungen (Auth, Lineage, Saved Queries, `sent_at`) treffen die produktive Postgres. Deshalb: **nur additive Migrationen** (self-contained-Muster), **Backup vor jeder Migration**, und einmalig ein **echter Restore-Test** des `backup_db.py`-Outputs (W0-Aufgabe). GPU-Nachtjobs mit den RSS-Cycles koordinieren.
2. **DSGVO-Kette ab dem ersten Account:** Datenschutzerklärung (Resend/Stripe als Auftragsverarbeiter, AVV), Double-Opt-In, Tracking aus W4.2 cookielos/anonymisiert aggregieren (kein Consent-Banner nötig) — Teil von 2.7, nicht erst beim Launch.
3. **Secrets-Disziplin:** NextAuth-/Stripe-Webhook-/Resend-Secrets nur in `.env`, nie committen; `.env.example` synchron; Webhook signaturgeprüft.
4. **Demo-Stabilität:** Kundendemos laufen ausschließlich auf persistierten Snapshot-Artefakten („Batch rechnet, Frontend liest"), nie abhängig von einem laufenden Nachtjob; vor jedem Termin eingefrorener, geprüfter Datenstand.
5. **Testsuite bleibt grün** bei jedem Merge (aktuell 106+); conftest-SQLite-Isolation nicht aushebeln.

## 2b. Issue-Hygiene (Pflicht, läuft in jeder Welle mit)

Jede Epic-Aufgabe ist auf Issue-Checkboxen gemappt (Spalte „Quelle"). Verbindliche Regel (deckt sich mit der bestehenden Owner-Vorgabe zur Issue-Pflege):

- **Bei Abschluss einer Aufgabe** werden im Quell-Issue die erledigten Checkboxen abgehakt (Body-Edit) + ein kurzer Ergebnis-Kommentar mit Commit-Referenz gepostet — im selben Arbeitsblock, nicht gesammelt am Ende.
- **Vollständig erledigte Issues werden geschlossen** (mit Abschluss-Kommentar). Bereits schließungsreif nach Welle 0: #28, #35, #41; nach Welle 1: #45, #40, ggf. #2; nach Welle 2: #16, #17 (Testmode-Scope), #38; nach Welle 3: #9, #44, Teile von #11/#3.
- **Neue Erkenntnisse/Ideen** aus der Epic-Arbeit, die nicht Alpha-Scope sind, werden als neues Issue angelegt statt den Scope aufzublähen (Anti-Scope-Sog-Mechanik).
- Die Alpha-Abnahme (3.5) enthält einen **Issue-Sweep**: kein Issue darf erledigten, aber unmarkierten Fortschritt tragen.

## 3. Abhängigkeits-Kritikpfad

```
0.1–0.4 ──┬─► 1.1 Lineage ─► 1.3 Evolution-View ─┐
          ├─► 1.2 Radar ─────────────────────────┼─► 2.6 Landing ─► 3.5 Abnahme
          └─► [Owner: Resend+Stripe beantragen] ─► 2.1 Auth ─► 2.2 Tiers ─► 2.3 Stripe ─► 2.4 ─┘
Nacht-Compute (unabhängig, jederzeit einschieben): 1.4 Market-Backfill, 1.5 z3, 1.6 Retrain
```
**Kalender-Treiber ist Welle 2:** Stripe-Verifizierung (Tage) und DNS-Propagation — deshalb Owner-Gates am **Tag 1** anstoßen, nicht erst wenn Welle 1 fertig ist.

---

## 4. Machbarkeitsabschätzung

**Gesamtaufwand:** ~29–37 AB aktive Agent-Arbeit + 4–6 Nacht-Compute-Jobs (inkl. Workbench/Export, UX-Gate-Loop und Rollout/Lead-Gen). Bei 1–2 AB/Tag und parallelen Subagents: **~4–5 Wochen Kalenderzeit**, davon Woche 1 fast reine Welle-0/1-Arbeit während die Owner-Gates (Accounts) reifen. Das UX-Gate (W3a) ist die größte Aufwands-Unsicherheit (1–3 AB je nach Loop-Runden) — bewusst, denn es kauft die Demo-Qualität.

**Risikobewertung je Baustein:**

| Baustein | Risiko | Einschätzung |
|---|---|---|
| Welle 0 komplett | 🟢 niedrig | Standard-Ops, Muster existieren im Repo |
| 1.1 Lineage | 🟡 mittel | Engine-Bausteine existieren alle; Risiko ist **methodisch** (Match-Schwellen erzeugen Split/Merge-Artefakte) → durch Known-Trend-Validierungs-Gate abgefangen; schlimmster Fall: Feature reift eine Woche länger, Alpha kann notfalls ohne Evolution-View zeigen |
| 1.2 Radar | 🟢 niedrig | Reine Komposition vorhandener Daten; SVG-Layout ist Fleißarbeit |
| 1.4/1.5/1.6 Compute | 🟢 niedrig | Tooling existiert und ist validiert; z3-**Ergebnis** ist offen, aber die dreiarmige Entscheidung (inkl. „ehrlich beim Status quo bleiben") ist vorab definiert — kein Alpha-Blocker |
| 2.1–2.4 Auth/Stripe | 🟡 mittel | Technisch Standardweg (Auth.js + Stripe Checkout = am besten dokumentierter Stack überhaupt, sehr agent-tauglich); Risiko liegt in den **Owner-Gates** (Account-Verifizierung, Rechtstexte) und Webhook-Korrektheit → Testmode + Webhook-Replay-Tests |
| 2.5 Newsletter | 🟢 niedrig | Generator fertig; Sender ist dünne API-Integration |
| 2.6/3.3 UX | 🟢 niedrig | Komponenten/Daten existieren; Owner-Review als Qualitätsgate |
| 3.1 Volltext | 🟡 mittel | Technisch trivial, aber Quellen-Verhalten heterogen (Paywalls, Cloudflare) → opt-in-Design begrenzt den Schaden strukturell |
| 3.4 Research Fronts | 🟡 mittel | Neue Methode auf großem Graph → als „optional für Alpha" markiert |
| 3.6/3.7 Workbench+Export | 🟢 niedrig | Saved Queries auf Auth-Schicht (2.1) + Snapshot-Deltas; Export als CSV/Print-CSS bewusst ohne PDF-Stack |
| 3a UX-Gate | 🟡 mittel | Aufwand loopabhängig (1–3 AB); Rubrik + Versionierung verhindern Endlos-Polieren — nach 3 Loops ohne Konvergenz eskaliert die Restliste an den Owner |
| W4 Rollout/Lead-Gen | 🟢 niedrig | Agent baut Assets/Tracking; Erfolgs-Risiko liegt im Markt (Owner-Outreach), nicht in der Umsetzbarkeit |

**Agent-Tauglichkeit:** Alle Bausteine sind klassische Code-/Daten-Arbeit mit testbaren Zwischenergebnissen — gut geeignet. Die drei Stellen, an denen Agents allein NICHT reichen: (a) Accounts/Keys/DNS/Rechtstexte (Owner), (b) kuratorische Entscheidungen (Mega-Labels, Preise, Feature-Matrix, Quellen-Opt-in), (c) finale UX-/Demo-Abnahme (Owner-Auge).

**Wissenslücken (Owner-Unterstützung willkommen):**
1. **TIR-Forschung nach 2021:** Implementiert ist Singh/Triulzi/Magee 2021 + Triulzi-2020-Null. Falls es neuere Arbeiten zu Kompositions-Drift-Korrektur / Zentralitäts-Normalisierung auf wachsenden Patent-Korpora gibt (post-2021), hilft das direkt beim #45-Eskalationsarm — gern Paper in `/mnt/data-hdd/shared_tir_research` legen.
2. **Preispunkte + Wettbewerbs-Feinheiten** im $100–500-Segment (Owner-Marktwissen).
3. **Rechtstexte** (DE-B2C: Impressum, Datenschutz mit Resend/Stripe-Verarbeitern, AGB, Widerruf) — Agent kann Entwürfe strukturieren, finale Texte brauchen Owner/Anwalt.

**Größtes Gesamtrisiko:** nicht Technik, sondern **Scope-Sog** — jede Welle lädt zu Vertiefung ein. Gegenmittel: die Alpha-Checkliste (3.5) ist das einzige Erfolgskriterium; alles, was dort nicht einzahlt, wandert als Issue ins Backlog.

---

## 5. Abnahme-Kriterien der Alpha (Kurzfassung für 3.5)

- [ ] Prospect-Journey 1–6 (Abschnitt 1) ohne Fehler auf catandary.de durchspielbar — in drei Demo-Varianten (Innovationsteam / Agentur / Prosumer)
- [ ] Saved Query anlegen + Alert-Badge nach Snapshot-Lauf sichtbar; Cluster-Export (CSV + Druckansicht) funktioniert
- [ ] Radar + Lineage-Evolution zeigen echte, validierte Daten (Known-Trend-Gates bestanden)
- [ ] Account-Anlage + Tier-Wechsel per Stripe-Testkarte funktioniert
- [ ] Newsletter-Testversand zugestellt (nicht Spam)
- [ ] Reboot-Probe: Alle Dienste kommen ohne Handarbeit zurück
- [ ] 0 erfundene Zahlen in 20 Stichproben-Artikeln (Grounding-Gate-Beleg)
- [ ] **UX-Gate bestanden:** alle kundensichtbaren Seiten ≥4/5 in allen fünf Rubrik-Dimensionen (`docs/ux_gate_report.md`, finale Iteration)
- [ ] **Issue-Sweep sauber:** alle erledigten Punkte in den GitHub-Issues abgehakt, vollständig erledigte Issues geschlossen
- [ ] **Rollout-Stufe (b) bereit:** Pilot-Accounts angelegt, Feedback-Formular live, Lead-Tracking-Events feuern (Testkontrolle im Dashboard)
- [ ] Demo-Drehbuch (3 Segment-Varianten) + Outreach-1-Pager + 2 Seed-Accounts liegen bereit
