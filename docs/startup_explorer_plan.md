# Startup Explorer — Plan (Datenakquise zuerst)

**Stand:** 2026-08-20 · **Status:** freigegeben (Owner 19.08.), Phase 0 abgeschlossen — Issue [#87](https://github.com/ZuluTwoThree/catandary-trends/issues/87)
**Owner-Vorentscheidungen (19.08.):** Geo-Fokus global (US-Dominanz akzeptiert, transparent ausgewiesen) · Grundeinheit = **Firma mit Event-Historie** · Paid-API-Budget bis ~100 €/Monat, falls der Hebel groß ist.
**Recherche-Grundlage:** Drei Web-Verifikationsläufe am 2026-08-19 (freie Register, freie Startup-Signal-APIs, Paid-Anbieter-Preise) + lokale DB-Vermessung. Alle Preise/Limits/Lizenzen wurden live geprüft, nicht aus Erinnerung übernommen; Schätzungen sind als solche markiert.

---

## 1. Produktbild

Der Startup Explorer ist die dritte Explorer-Stufe der Foresight-Kette:

```
Research Explorer      Patent Explorer       Startup Explorer      Trends
(45M Papers)      →    (19,6M Patente)   →   (Venture-Stufe)   →   (Markt-Signale)
Wissenschaft           Technologie           Kommerzialisierung    Konsum/Markt
```

- **Einheit:** Firmenprofil mit datierter Event-Historie (Funding-Runden, Grants, Marken, Produktreife-Signale) — aufgebaut über einem Event-Korpus.
- **Route (analog zu den bestehenden):** `/trends/foresight/ventures` (Suche + Facetten + Stats-Header) und `/trends/foresight/ventures/company/[id]` (Profilseite mit Timeline).
- **Alleinstellungsmerkmal:** die Brücken. Firma ↔ ihre Patente (22,6M Zeilen `patent_assignee_raw` liegen bereits vor) ↔ ihre Papers/Grants (45M-Research-Korpus) ↔ Trend-Signale. Kein freier Wettbewerber zeigt Reg-D-Funding, Patent-Aktivität und Grant-Historie derselben Firma nebeneinander. Perspektivisch: TIR-Anbindung („Firmen in schnell verbessernden Technologiefeldern").
- **Positionierung (Ehrlichkeitsregeln!):** „Funding- und Innovations-Evidenz-Explorer auf Primärquellen" — ausdrücklich **kein** Crunchbase-Klon. Coverage wird benannt: US-Privatplatzierungen (Reg D, gesetzliche Meldepflicht — kein Sample), US/EU/UK-Förderungen, UK-Register, Presse-verifizierte Runden. Keine Bewertungen, keine „alle Startups weltweit"-Claims.

---

## 2. Verifizierte Datenlage (2026-08-19)

### 2a. Frei nutzbar UND im Produkt anzeigbar

| Quelle | Inhalt | Volumen / Historie | Frische | Lizenz |
|---|---|---|---|---|
| **SEC Form D** (Datasets) | US-Privatplatzierungen: Issuer, Ort, Branche, Beträge (total/sold), Officers („Related Persons"), Gründungsjahr-Bucket | Bulk-Datasets real **ab 2012** (2008q1 ist ein Stub, 2008–2011 publiziert die SEC nicht als Bulk); **im Haus komplett: 119.999 Einträge 2012–2026Q1 = ~115k Firmen, 100 % datiert** (Datumsreparatur 2026-08-20) | quartalsweise (2026Q2 noch nicht erschienen) | Public Domain |
| **SBIR/STTR** (sbir.gov API/Bulk) | Staatliches Startup-R&D-Funding: Firma, UEI, Betrag, Agency, Phase, **Mitarbeiterzahl**, Company-URL, Abstract | alle Awards seit 1983 (Größenordnung ~180k; beim Ingest verifizieren) | laufend; API aktuell „undergoing maintenance" → Bulk-CSV-Fallback | Public Domain |
| **CORDIS** (HE + H2020 + FP7, data.europa.eu) | EU-Förderprojekte: Organisationen mit **SME-Flag**, Land, ecContribution, Projekt-Abstract; **EIC-Accelerator-Grants enthalten** (702 Companies, 4,7 Mrd. € seit 2021) | drei Rahmenprogramme, Bulk CSV/JSON | **monatlich** (letzter Dump 2026-08-07) | **CC BY 4.0** (Attribution) |
| **Bereits im Haus** | NIH/NSF/OpenAIRE/UKRI-Awards (265k) + **~23k Presse-Funding-Meldungen** aus Fachpresse/Wires („raises $X", „Series B"; die frühere 106k-Zählung enthielt die Form-D-Signale selbst) + 219.832 Trends mit `trend_signal_type='funding'` | seit ~2005 bzw. 2014 | täglich (Full Cycle) | Eigenkorpus |
| **Companies House UK** | UK-Vollregister: Name, Nummer, **Gründungsdatum, SIC-Codes**, Adresse, Status; Officers via API | Monats-Snapshot ~470 MB (~5,5M Firmen, Schätzung) | monatlich + **Echtzeit-Streaming-API** (600 req/5min REST) | OGL v3 (Attribution) |
| **GLEIF LEI** (Golden Copy) | 3,02M aktive LEIs global: Name, Adressen, Rechtsform, **Registerbehörde + lokale Register-ID** | global, Level-2-Eigentumsketten | 3×/Tag Bulk, Delta-Files | **CC0** |
| **Wikidata** (SPARQL) | Enrichment: ~765k Firmen-Items, 171k mit Gründungsdatum; Gründer, Website, Querverweise zu Registern/LEI | Top-Firmen („notable") | laufend | **CC0** |
| **EUIPO-Marken** | „Junge Firma meldet Marke an"-Frühsignal: Anmelder + Adresse + Nizza-Klassen (Branchenproxy) | EUTM-Vollregister, Bulk-XML | **täglich** | royalty-free (Klauseln im Detail prüfen) |
| **USPTO-Marken** | dito für US (TSDR API 60 req/min, Bulk via ODP) | vollständig | laufend; **seit 18.06./18.08.2026 Login-/Profilpflicht ODP** | Public Domain |
| **Hacker News** (Firebase + Algolia) | **„Launch HN"/„Show HN"** = Launch-Signal (deckt YC-Batches legal ab) | Volltext durchsuchbar | Echtzeit; „currently no rate limit" | MIT |
| **ClinicalTrials.gov v2 + openFDA** | Produktreife HEALTH: Trials je Sponsor (INDUSTRY-Klasse), 510(k)/PMA-Clearances | vollständig | laufend; 120k Calls/Tag mit Free-Key | US-Gov Open Data |
| **GitHub API** | Dev-Tool-Traction: Org-Metadaten, Repos, Stars | 5.000 req/h mit PAT | Echtzeit | frei (ToS-Detail prüfen) |
| **USAspending** | „Startup gewinnt Regierungsauftrag" (Filter `Small Business`; kein Alters-Filter) | vollständig | laufend, keine Auth | Public Domain |

### 2b. Eingeschränkt oder gesperrt

| Quelle | Befund | Konsequenz |
|---|---|---|
| **Product Hunt API** | „must not be used for commercial purposes" — nur mit schriftlicher Freigabe (hello@producthunt.com) | Optional: Genehmigung anfragen; bis dahin **nicht** nutzen |
| **Y Combinator Directory** | ToS verbieten Data-Mining + kommerzielle Auswertung; keine offizielle API; yc-oss-Spiegel hat **keine Lizenz** | **Nicht ingesten.** Ersatz: „Launch HN" (legal, gleiches Signal). Optional YC um Freigabe bitten |
| **OpenCorporates** | kein Free-Tier mehr (Pläne ab £2.250/Jahr); Open-Data-Route ist Share-Alike → inkompatibel mit Paid-Tiers | Nicht nutzen |
| **Handelsregister DE** | keine legale API (~60 Abfragen/h-ToS, HVD-Pflicht seit 2024 **nicht umgesetzt**); offeneregister.de = statischer **2019**-Snapshot | 2019-Snapshot als historischer Sockel; HVD-Umsetzung als Wiedervorlage-Issue |
| **EU BRIS / ESAP** | BRIS ohne API; ESAP-Go-live 07/2027, Abschlüsse ab 2028 | Roadmap-Punkt, heute nichts |

---

## 3. Suffizienz-Check: Trägt der Free-Stack ein Explorer-Produkt?

Geprüft gegen die fünf Anforderungen, die Research/Patent Explorer definieren:

1. **Großer durchsuchbarer Korpus** — ✅ **Ja.** Realistisch **250–400k startup-relevante Firmen** mit mindestens einem datierten Event (gemessen nach Phase 0: 115k Form-D-Firmen 2012–2026, 126,6k SBIR-Firmen, ~52k CORDIS-SME-Beteiligungen, 20k Presse-Runden; + junges UK-Subset in Phase 1; Überschneidungen löst die Entity Resolution). Kleiner als 19M Patente — aber die Einheit ist reicher (Profil statt Dokument).
2. **Facetten** — ✅ Vertical (vorhandene Distill-Heads klassifizieren Abstracts/Beschreibungen GPU-frei), Geografie, Event-Typ (Reg D / Grant / SBIR-Phase / Presse-Runde / Marke / Clearance), Betragsklasse, Jahr.
3. **Detailseiten mit Substanz** — ✅ Funding-Timeline + Patent-Brücke + Grant-/Paper-Historie + Marken. Das ist mehr Tiefe pro Firma als jede freie Alternative.
4. **Frische** — ✅ mit Transparenz: Presse täglich, CH-Streaming Echtzeit, CORDIS monatlich, **Form D quartalsweise (Lag offen ausweisen, wie beim Research-Korpus üblich)**.
5. **Ehrliche Vermarktbarkeit** — ✅ wenn als Evidenz-Explorer positioniert. Form D ist keine Stichprobe, sondern die **gesetzliche Meldepflicht** für praktisch jede US-Venture-Runde — ein echter Vollständigkeits-Claim für dieses Segment.

**Strukturell nicht frei verfügbar** (auch mit allen obigen Quellen): Bewertungen/Valuations, vollständige Investoren-Graphen (nur presse-extrahiert), EU/DACH-Privatrunden ohne Presseecho, Mitarbeiter-Historien (nur SBIR-Snapshots). → Das ist genau der Inhalt der Paid-Abwägung in §7.

**Fazit: Die Informationsgrundlage reicht für ein Explorer-Produkt aus** — vorausgesetzt, das Produkt verkauft Primärquellen-Evidenz + Brücken, nicht Crunchbase-Vollständigkeit.

---

## 4. Datenmodell (Skizze, Konventionen wie `patent_search`/`research_corpus`)

```sql
CREATE TABLE startup_companies (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,              -- kanonischer Name
    aliases JSONB DEFAULT '[]',
    country TEXT, region TEXT, city TEXT,
    founded_date DATE,               -- exakt (CH/Wikidata) …
    founded_bucket TEXT,             -- … oder Bucket (Form D: "<5y"/">5y")
    verticals JSONB DEFAULT '[]',    -- Distill-Klassifikation
    website TEXT,
    -- Entity-Resolution-Anker (jeweils UNIQUE wo vorhanden):
    uei TEXT, lei TEXT, cik TEXT, ch_number TEXT, wikidata_qid TEXT,
    first_event_at DATE, last_event_at DATE, event_count INTEGER,
    total_funding_usd NUMERIC,       -- nur belegte Beträge, NULL-tolerant
    search_tsv TSVECTOR              -- GIN-Index, wie idx_re_patent_fts
);

CREATE TABLE startup_events (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES startup_companies(id),
    event_type TEXT CHECK (event_type IN ('regd_offering','sbir_award','grant',
        'press_round','trademark','launch','clinical','fda_clearance','gov_contract')),
    event_date DATE NOT NULL,
    amount_usd NUMERIC, currency TEXT,
    round_label TEXT,                -- "Series B" etc. (nur Presse-Extraktion)
    investors JSONB DEFAULT '[]',    -- nur Presse-Extraktion
    meta JSONB DEFAULT '{}',         -- Agency/Phase/Nizza-Klassen/…
    source TEXT NOT NULL, source_url TEXT NOT NULL,   -- Quellennennung Pflicht
    raw_entry_id INTEGER             -- Rückverweis wo vorhanden
);

CREATE TABLE startup_patent_links (company_id INTEGER, pub_number TEXT, match_conf REAL);
CREATE TABLE startup_research_links (company_id INTEGER, openalex_id TEXT, kind TEXT);
```

**Entity Resolution (Produktqualität hängt hieran):** dreistufig, konservativ.
1. **Harte Anker:** UEI (SBIR↔USAspending), LEI↔Register-IDs (GLEIF als Brückentabelle), CIK, CH-Nummer, Wikidata-QID → automatischer Merge.
2. **Normalisierter Name + Geo** (Suffix-Stripping Inc/Ltd/GmbH, Jurisdiktion): Merge nur bei eindeutigem Treffer.
3. **Embedding-Fuzzy** (bestehende Embedding-Infra) nur als Kandidaten-Vorschlag mit hoher Schwelle; darunter **ungemergt lassen** — ein Duplikat ist billiger als ein falscher Merge.

---

## 5. Akquise-Plan in Phasen

**Phase 0 — Bestand heben (CPU/Netz, keine neuen Quellenverträge): ✅ abgeschlossen 2026-08-20**
1. ~~Form-D-Backfill~~ → Bestand war bereits vollständig (SEC-Bulk existiert real erst ab 2012); stattdessen **Datumsreparatur**: 62.761 Zeilen nachdatiert (`--repair-dates`, Parser-Fix für das alte FILING_DATE-Format), Korpus jetzt 100 % datiert. 2026Q2 erscheint erst noch (Quartals-Pull als Folgeaufgabe).
2. ✅ `scripts/ingest_sbir.py`: **183.944 SBIR/STTR-Awards** (1983–2024) aus dem offiziellen Bulk-CSV (die Awards-API liefert derzeit 403 „maintenance"), 126.577 Firmen; CSV-Cache in `data/` behält DUNS/Website/Mitarbeiterzahl für Phase 1. Frische-Lag der Quelle: neueste Awards ~2024.
3. ✅ `scripts/ingest_cordis.py`: **51.815 CORDIS-SME-Förderungen** (HE 21.314 + H2020 30.501; Filter SME=true ∧ activityType=PRC) mit Land, ecContribution, Projekt-Abstract.
4. ✅ `scripts/extract_press_rounds.py` + Staging-Tabelle `startup_press_rounds`: Regex-Volllauf über **22.991 Presse-Meldungen → 20.099 (87 %) mit Firma+Betrag**, 265 VC-Fonds-Meldungen ausgefiltert. Investoren-Namen liefert die LLM-Stufe: 200er-Sample validiert (91 % Firma+Betrag, Investoren sauber); **Folgeaufgabe:** `--mode upgrade` über die ~20k Zeilen (~5 h auf dem lokalen LLM, außerhalb des Nachtlauf-Fensters).

**Phase 1 — Firmenstamm + Entity Resolution:**
5. GLEIF Golden Copy (CC0) als Resolution-Backbone laden.
6. Companies-House-Snapshot: Subset junger Firmen + tech-relevante SIC-Codes (nicht alle ~5,5M).
7. Wikidata-Enrichment für gematchte Firmen (Gründer, Website, Gründungsdatum).
8. Resolution-Lauf nach §4; `startup_companies` aufbauen; Distill-Vertical-Klassifikation.

**Phase 2 — Signale:**
9. HN Launch/Show HN (Backfill via Algolia-Suche + laufend), EUIPO-Marken-Bulk, USPTO-Marken (nach ODP-Login-Einrichtung), ClinicalTrials/openFDA fürs HEALTH-Subset, GitHub-Orgs fürs TECH-Subset, USAspending (Small-Business).

**Phase 3 — Brücken + Frontend:**
10. Patent-Brücke: Assignee-Namen aus `patent_assignee_raw` gegen den Firmenstamm matchen (gleiche Normalisierung wie §4 Stufe 2).
11. Research-/Grant-Brücke analog.
12. Frontend `/trends/foresight/ventures` (Explorer-Seite nach dem Muster von `patents/page.tsx`: Suche, Facetten, Stats, PAGE_SIZE 25) + Profilseite. TierGate-Vorschlag: Teaser frei, Suche Starter, Timeline/Brücken Pro — finale Gating-Entscheidung beim Owner.
13. Cron-Integration: CORDIS/CH/GLEIF monatlich (Muster `sync_openalex_monthly.sh`), Form D quartalsweise, SBIR + Presse-Extraktion in `weekly_ingesters.sh`.

**Aufwandsschätzung:** Phase 0 ≈ 3–5 Tage · Phase 1 ≈ 1 Woche · Phase 2 ≈ 1 Woche · Phase 3 ≈ 1–2 Wochen. GPU nur für Presse-Extraktion (+ optionale Embeddings später); alles andere CPU/Netz — kollidiert nicht mit dem Nachtlauf.

---

## 6. Paid-API-Gegenüberstellung (verifiziert 2026-08-19)

**Kernbefund vorab:** Der Engpass ist nicht der Preis der Daten, sondern die **Display-/Redistribution-Rechte**. Daten im eigenen Free+Paid-Produkt anzuzeigen ist bei fast allen Anbietern ein eigenes, teures Lizenzprodukt oder schlicht verboten.

| Anbieter | Realer Preis (API-tauglich) | Was man bekommt | Im Produkt anzeigen? | Urteil |
|---|---|---|---|---|
| Crunchbase | API nur Enterprise, **Median $20k/Jahr** (Vendr, n=70); Basic-API abgeschafft | globale Runden-Historie, Investoren | nur „Applications License" (der teure Pfad) + Attributionspflicht | ❌ 15–20× Budget |
| Dealroom | Premium **$14,5k/Jahr** (3 Seats); API erst Enterprise | beste EU-Abdeckung | nicht dokumentiert, Enterprise-Verhandlung | ❌ 12× Budget |
| PitchBook / CB Insights | $12–30k bzw. ~$30–100k/Jahr | Research-Terminals | Internal-Use | ❌ |
| Tracxn | Premium ~$6,6k/Jahr (Sekundärquelle); **Lite-Tier kostenlos** (manuell) | 7,7M Firmen | **einziger Anbieter mit offiziellen „Commercial Redistribution Packs"** — quote-only | ⚠️ Lite kostenlos mitnehmen; Redistribution-Quote nur bei erwiesener Nachfrage einholen |
| Harmonic.ai | quote-only (Gerüchte ~$99/Mo Starter, unverifiziert) | Startup-Graph inkl. Headcount | verhandelbar | ⚠️ Sales-Call-Pflicht, unklar |
| Exploding Topics | API real **~$1.249/Monat** ($249 Business + $1.000 API-Add-on); Produkteinbau erfordert Custom-Lizenz | Trend-Keywords (keine Firmendaten!) | Extra-Lizenz | ❌ überlappt mit eigener Signal-Pipeline |
| SimilarWeb / BuiltWith | API quote-only bzw. ab $295/Mo | Traffic/Tech-Stack-Proxies | ungeklärt | ❌ / ⚠️ BuiltWith-Free-Trends-API kostenlos nutzbar |
| **PredictLeads** | **$40–90/Monat** (100 Credits frei, dann $40 Min. + $0,04/Call degressiv) | Hiring-/News-/Tech-Signale, Financing-Events, Historie bis 2015 | **❌ Redistribution ausdrücklich verboten** — nur intern | ✅ **Budget-Fit als internes Momentum-Scoring** (nicht anzeigbar) |
| **People Data Labs** | **$0–100/Monat** (Free 100 Records/Mo; Pro $100 = 1.000 Firmen-Records à ~$0,10) | Firmographics: Größe, Branche, Standort, Gründungsjahr, LinkedIn-URL | Lizenz vergleichsweise offen („any way compliant with AUP") — **Anzeige von Firmendaten vor Einsatz schriftlich klären**; Personendaten wegen DSGVO meiden | ✅ **Budget-Fit als Enrichment-Pilot nach v1** |

### Kosten-Nutzen-Antwort auf die Ausgangsfrage

**Kann Paid die Informationsgrundlage überproportional steigern?** Inhaltlich ja — aber nur in der Crunchbase/Dealroom-Klasse (globale Rundenvollständigkeit, Investoren-Graphen, Bewertungen, EU-Privatrunden), und die kostet **mit Display-Rechten ≥ $15–20k/Jahr = das 12–20-fache des Budgets**, bei einem Free-Content-Lead-Generator ohne belegten Umsatz dahinter. Gleichzeitig deckt der Free-Stack das juristisch belastbare Kernsegment (US-Reg-D vollständig, US/EU/UK-Förderungen vollständig) bereits ab, und die Presse-Extraktion holt einen relevanten Teil der „benannten Runden mit Investoren" für 0 €. **→ Nicht verhältnismäßig. Empfehlung: v1 komplett frei bauen.**

**Im Budget sinnvoll (optional, nach v1):**
- **PDL-Pilot ≤100 €/Monat:** gezieltes Enrichment der Top-N angezeigten Firmen (Größe/Gründungsjahr/Website-Lücken füllen) — erst nach schriftlicher AUP-Klärung für die Anzeige.
- **PredictLeads ~$40–90/Monat:** Hiring-Momentum als *internes* Scoring-Feature (fließt in Ranking/Trend-Score, wird nie roh angezeigt).
- **Kostenlos mitnehmen:** Tracxn Lite (manuelle Einzelchecks), BuiltWith Free/Trends-API.

---

## 7. Risiken & offene Prüfpunkte

| Risiko | Umgang |
|---|---|
| Entity-Resolution-Fehler (falsche Merges) | konservative Schwellen (§4); Duplikate tolerieren; Merge-Audit-Stichprobe vor Launch |
| Coverage-Ehrlichkeit (Truth Matrix) | Formulierungen fixieren: „US Reg-D filings (complete by law), EU/UK/US public funding, press-verified rounds" — nie „alle Startups" |
| SBIR-API „maintenance" (Stand 19.08.) | Bulk-CSV-Fallback; beim Bau erneut prüfen |
| USPTO-ODP-Login-Umstellung (18.08.2026!) | Konto + Profilfelder vor Marken-Ingest einrichten; exakte Rate-Limits klären |
| DACH-Lücke | benennen statt kaschieren; HVD-Umsetzung DE + ESAP 2027 als Wiedervorlage-Issue |
| Offene ToS-Details | openFDA-510(k)-Applicant-Feld, GitHub-ToS-Weiterverwendung, EUIPO-Lizenzklauseln, EIC-Data-Hub-Export — je beim Bau der Quelle verifizieren |
| Product Hunt / YC | nur nach schriftlicher Freigabe; bis dahin Launch-Signal ausschließlich via Hacker News |

## 8. Nächste Schritte

1. Owner-Review dieses Plans (insb. TierGate-Zuordnung §5.12 und ob der PDL/PredictLeads-Pilot grundsätzlich gewollt ist).
2. Bei Freigabe: GitHub-Issue mit diesem Plan als Referenz + Feature-Branch `feature/startup-explorer`, Start mit Phase 0.
