# Startup Explorer — Datenakquise-Plan und Suffizienz-Prüfung

**Status: Vorschlag, nicht umgesetzt.** Stand 2026-08-21. Alle Quellen-Angaben
wurden am 2026-08-19 gegen die Primärquellen verifiziert, alle Korpus-Zahlen
gegen die Live-DB gemessen.

Auftrag des Owners: einen Startup Explorer analog zu Research Explorer und Patent
Explorer bauen, Datenakquise zuerst, Schwerpunkt auf frei zugänglichen Quellen und
Free-Tier-APIs. Vorab zu prüfen: reicht die Informationsgrundlage für ein
Explorer-Produkt? Und lässt sie sich über bezahlte APIs überproportional steigern?

Owner-Vorgaben aus der Rückfrage-Runde: global mit akzeptiertem US-Übergewicht ·
Grundeinheit ist die **Firma mit Event-Historie** (nicht das Einzel-Event) ·
Budget-Komfortzone für bezahlte APIs bis ~100 €/Monat.

---

## 1. Suffizienz-Urteil (die Vorab-Prüfung)

**Für einen Crunchbase-artigen Deal-Explorer reicht die freie Datenlage nicht.**
**Für einen Technologie-Substanz-Explorer reicht sie — und dort ist Catandary
den kommerziellen Anbietern sogar überlegen.**

Das ist kein Ausweichen, sondern das Ergebnis der Prüfung. Was den freien Quellen
strukturell fehlt, ist genau das, was Crunchbase & Co. verkaufen:

| Fehlt in allen freien Quellen | Konsequenz |
|---|---|
| Rundenbezeichnung (Seed/Series A/B) | SEC Form D kennt nur „Reg-D-Offering", keine Runden-Semantik |
| Investorenliste pro Runde | Form D nennt Executives, nicht die Kapitalgeber |
| Bewertungen (Valuations) | Nirgends frei; auch nicht ableitbar |
| Mitarbeiterzahl-Zeitreihen | Nur Punktwerte (SBIR `number_employees`), keine Historie |
| Gründungsdatum flächendeckend | Form D nur als Bucket („within last 5 years"); präzise nur UK/Wikidata |
| Firmen-Vollkorpus außerhalb US/UK | DE hat keine legale API, EU-BRIS/ESAP erst ab 2027 |

Ein Produkt, das „Startup-Finanzierungsdaten" verspricht, wäre auf dieser Basis
unehrlich. Ein Produkt, das fragt **„welche Firmen haben in dieser Technologie
belegbare Substanz — und wo steht die Technologie?"**, ist auf dieser Basis
belegbar und ohne Vergleich am Markt, weil es vier Ebenen verbindet, die kein
Deal-Anbieter zusammenführt:

    Paper (45M) → Patent (19,6M) → öffentliche Förderung (SBIR/CORDIS)
                → privates Kapital (Form D) → Produktreife (Trials/FDA) → Launch (HN)

Diese Kette ist bereits das Rückgrat des Foresight-Produkts (TIR, Lead-Time,
Innovation Chain). Der Startup Explorer ist die **Firmen-Achse** durch dieselbe
Kette — nicht ein neues, fremdes Produkt.

### Was das Produkt konkret beantworten kann

- „Zeig mir Firmen mit Festkörperbatterie-Patenten, die seit 2023 Kapital
  aufgenommen haben" — Patent-Achse × Funding-Event, mit Datum.
- „Welche SBIR-Phase-II-Firmen in Quantum haben danach privat weiterfinanziert?"
  — der Übergang staatlich → privat ist ein hartes, datiertes Reifesignal.
- „Welche Health-Startups sind von der Studie zur FDA-Clearance gekommen?"
  — Produktreife-Achse mit echten Stufen statt Selbstauskunft.
- „Wer forscht öffentlich gefördert an X, ohne je patentiert zu haben?"
  — die Lücke ist selbst ein Signal.

### Was es nicht kann (und wo das hingehört)

Keine Runden-Semantik, keine Investoren, keine Bewertungen, keine
Vollständigkeit außerhalb US/UK. Das gehört **explizit auf die Methodik-Seite**,
nach dem Muster der bestehenden Ehrlichkeitsregeln (`docs/launch/`) und der
Radar-Kalibrierung: lieber eine klar begrenzte Aussage als eine unbelegbare.

### Der gemessene Kernbefund, der den Zuschnitt bestimmt

Ich habe die Firma→Patent-Brücke auf der Live-DB getestet (`patent_assignee_raw`,
22,6 Mio. Zeilen, Trigram-Index):

| Grundgesamtheit | Firmen mit Patent-Treffer |
|---|---|
| Alle SEC-Form-D-Filer (Stichprobe n=60) | **3 %** |
| Nur Biotechnology / Other Technology / Computers (n=115) | **27 %** |

Der Mechanismus funktioniert (Gegenprobe: Moderna, OpenAI, Anthropic, Databricks,
Rivian, Ginkgo — alle mit Patenten im Korpus gefunden). Die 3 % sind die Realität:
**Der Form-D-Bestand ist überwiegend kein Startup-Korpus.** Reg D nutzt jede Firma,
die privat Kapital aufnimmt — Immobilienprojekte, lokale Betriebe, Fondsvehikel.

Zugleich zeigte der Test **Fehltreffer** bei naivem Namens-Matching: „Realize, Inc."
liefert 60 angebliche Patente, weil „realize" in vielen Anmeldernamen vorkommt.

Daraus folgen die zwei wichtigsten Konstruktionsentscheidungen:

1. **Der Korpus wird kuratiert, nicht geflutet.** Aufnahme nur bei
   Technologie-Evidenz (siehe Aufnahmeregel, §3). Ein Explorer über 500k
   Reg-D-Filings wäre eine Suchmaschine für Immobilien-Zweckgesellschaften.
2. **Entity Resolution läuft ID-first, Fuzzy nur mit Kontext-Gate** (§4).
   Ein falsch zugeordnetes Patent zerstört die Glaubwürdigkeit der ganzen
   Substanz-Aussage — das ist das zentrale Qualitätsrisiko des Produkts.

---

## 2. Datenlage: was bereits im Haus ist

Gegen die Live-DB gemessen (2026-08-21). Das ist der Grund, warum dieses Produkt
überhaupt in Reichweite ist — die halbe Datenakquise ist erledigt:

| Bestand | Menge | Anmerkung |
|---|---|---|
| SEC Form D | **119.999** Filings, 2020-07 bis 2026-03 | `scripts/ingest_secform_d.py` kann bis 2008 backfillen |
| NIH RePORTER | 234.763 Awards, ab 2005 | Biomedizin-Förderung |
| NSF Awards | 13.014 | |
| OpenAIRE (EU + national) | 11.612 | |
| UKRI | 6.000 | |
| Presse-Funding-Signale | ~106.417 Roh-Einträge mit Funding-Titelmuster | 9–14k/Jahr seit 2020 |
| Patent-Anmelder | **22,6 Mio.** Zeilen + Trigram-Index | die Firma→Patent-Brücke |
| Patent-Korpus | 19,6 Mio. | mit CPC, SPNP, TIR |
| Research-Korpus | 45 Mio. Werke | mit Topics, Institutionen, Funder |

Ebenfalls vorhanden und wiederverwendbar: der **Distill-Embedding-Pfad**
(GPU-frei, ersetzt drei LLM-Calls), das **Live-Layer-Muster** des Research
Explorers (`frontend/src/lib/openalex-live.ts`: Tier-Gate, Tagesbudget, Cache)
und die **Explorer-Seitenarchitektur** (Suchfeld mit Smart-Router, Facetten,
Tier-Gates, Export).

Von Form D sind bislang 7.103 Einträge zu Trends verarbeitet, 112.896 wurden
gefiltert — die Filterung war für den Content-Cycle richtig, für den Explorer
sind die gefilterten Daten aber die eigentliche Substanz. Sie liegen vollständig
vor und müssen nur anders erschlossen werden.

---

## 3. Datenakquise: der Free-Stack

Alle Quellen am 2026-08-19 gegen die Primärquelle verifiziert. Reihenfolge nach
Ertrag pro Aufwand.

### Stufe 1 — Das Fundament (ohne neue externe Abhängigkeit)

**1a. SEC Form D Backfill 2008–2020.** Der Ingester existiert und läuft; es fehlen
nur die älteren Quartale. Bringt den Bestand auf geschätzt 400–500k Filings und
damit eine 18-Jahres-Funding-Historie. Public Domain, 10 req/s, Q2/2026 bereits
online. *Aufwand: gering (Skript-Lauf + Ladezeit).*

**1b. Firma→Patent-Brücke bauen.** Der wertvollste Schritt, weil er
ausschließlich vorhandene Daten verbindet: kanonische Firmennamen gegen
`patent_assignee_raw` auflösen, mit dem Kontext-Gate aus §4. *Aufwand: mittel,
Qualität entscheidet über das Produkt.*

**1c. Firma→Paper-Brücke.** Analog über `research_institutions` /
`research_work_inst` — Firmen publizieren (Pharma, Deep Tech). Ergänzt die
Substanz-Achse um Wissenschaft. *Aufwand: mittel.*

### Stufe 2 — Die Funding-Achse vervollständigen

**2a. SBIR.gov (US, ~40 Jahre).** Die stärkste einzelne Neuquelle: staatliches
Startup-R&D-Funding seit 1982/83, mit Firma, Betrag, **Phase I/II/III**, Abstract,
Mitarbeiterzahl, **UEI** (harte ID!), Adresse. Der Phase-I→II-Übergang ist ein
hartes Reifesignal, das kein kommerzieller Anbieter so sauber führt.
⚠️ Die API meldete am 2026-08-19 Wartungsarbeiten — Verfügbarkeit vor dem Bau
testen, Bulk-Download (XLS/JSON/XML) als Fallback einplanen. 100 Rows/Request.
Keine expliziten Nutzungsbedingungen gefunden; de facto Public Domain.

**2b. CORDIS / EIC (EU).** Lizenzrechtlich die sauberste Quelle überhaupt:
**CC BY 4.0**, kommerzielle Nutzung ausdrücklich erlaubt. Bulk-CSV/JSON, monatlich
aktualisiert, mit **SME-Boolean-Flag**, `ecContribution`, Land, Rolle, Abstract.
Das ist das einzige wirksame Gegengewicht zum US-Bias. Der EIC-Accelerator-Anteil
(702 Firmen, 4,7 Mrd. € seit 2021) steckt in den HE-Daten (Filter auf
`HORIZON-EIC` + SME); das separate EIC-Dashboard braucht es nicht — unklar ist
ohnehin, ob es einen maschinenlesbaren Export hat, und die Equity-Beträge sind
dort nur bei Zustimmung der Firma offengelegt.
*Empfehlung: als erste externe Quelle bauen — passt exakt auf das bestehende
`sync_openalex_monthly.sh`-Muster.*

### Stufe 3 — Reife- und Launch-Signale

**3a. ClinicalTrials.gov v2 + openFDA 510(k).** Beide ohne Auth, sponsor- bzw.
anmelder-gefiltert (`query.spons`, `applicant` — beide verifiziert). Liefert die
Produktreife-Achse für HEALTH mit echten, datierten Stufen. openFDA hat **keinen
De-Novo-Endpoint** (separater FDA-Download). Mit kostenlosem Key 120.000 req/Tag.
Der openFDA-Disclaimer („not validated for clinical use") gehört auf die
Methodik-Seite.

**3b. Hacker News (Firebase + Algolia).** MIT-lizenziert, **kein Rate Limit**,
Historie ab 2007. „Launch HN" (YC-Batch-Launches) und „Show HN" (Produkt-Launches)
mit score/comments als Resonanz-Proxy. Trivialer Ingest.

### Stufe 4 — Stammdaten und Anreicherung

**4a. GLEIF LEI (CC0).** 3,02 Mio. aktive LEIs, Golden Copy 3×täglich, und —
entscheidend — **Register-IDs der nationalen Register plus Konzernstrukturen**.
Das ist der Entity-Resolution-Backbone, nicht ein Firmenkorpus.

**4b. UK Companies House (OGL, Attribution).** Monats-Snapshot (~470 MB CSV) mit
**exaktem Gründungsdatum** und SIC-Codes, plus Streaming-API für Echtzeit-Deltas.
Macht UK zum einzigen vollständig abgedeckten Nicht-US-Markt.

**4c. Wikidata (CC0).** ~765k Firmen-Items; 172k mit Gründungsdatum, aber nur 86k
mit Branche — als Basiskorpus untauglich, als Enrichment (Website, Gründer, Logo,
Register-Querverweise) für bekannte Firmen gut.

**4d. USPTO/EUIPO-Marken.** Markenanmeldung als Frühsignal („junge Firma meldet
Marke an"), mit Nizza-Klassen als Branchenproxy. EUIPO: täglicher Bulk-XML,
kostenlos. ⚠️ USPTO Open Data Portal verlangt seit 2026-06-18 Login, seit
2026-08-18 zusätzliche Profilfelder — sonst Verlust des API-Keys.

**4e. GitHub API.** Org-`created_at` als Gründungs-Proxy, Stars/Commits als
Traktion für Dev-Tool-Startups. 5.000 req/h mit Token.

**4f. USAspending.gov.** ⚠️ **Firmen-Alter ist nicht filterbar**, nur
`recipient_type_names = "Small Business"`. Deshalb kein eigener Ingest, sondern
reine Anreicherung bereits bekannter Firmen („gewinnt Regierungsauftrag").

### Rechtlich gesperrt — nicht bauen

| Quelle | Grund |
|---|---|
| **Product Hunt API** | ToS: „must not be used for commercial purposes." Nur mit schriftlicher PH-Freigabe. |
| **YC-Directory / yc-oss/api** | YC-ToS verbietet Scraping *und* kommerzielle Reproduktion; das Community-Repo hat **keine Lizenz** (`license: null`). Launch-Signal stattdessen über HN „Launch HN" — gleiches Signal, saubere Rechtslage. |
| **OpenCorporates** | Kein Free-Tier mehr; Open-Data-Route ist **Share-Alike** → mit Paid-Tiers inkompatibel. Ab £2.250/Jahr. |
| **Handelsregister.de** | Keine offizielle API, ToS-Limit ~60 Abfragen/h, Verweis auf §§303a/b StGB. Die HVD-Verordnung verpflichtet seit Juni 2024 zu API+Bulk — 2026 weiterhin nicht umgesetzt. `offeneregister.de` ist ein statischer 2019-Snapshot. **Als Issue zur Wiedervorlage, nicht als Grauzonen-Scraping.** |
| **EU BRIS / ESAP** | BRIS nur menschlich durchsuchbar. ESAP: erste Datensammlung ab 2026-07-10, Go-live **2027-07-10** → Roadmap-Punkt. |
| **Dealroom-Scraper** | Genau das Aggregator-Scraping, das die Quellenstrategie ausschließt. |

### Ergebnis der Quellen-Suche nach freien VC-Datensätzen

Es gibt **keinen** substanziellen freien Startup-/Funding-Datensatz 2024–2026 unter
diesen Randbedingungen. OpenVC ist eine Investoren-, keine Startup-Datenbank (und
mit ungeklärten Weiterverwendungsrechten). VC-Portfolio-Seiten sind als
Primärquelle legal und zulässig, brauchen aber pro Seite einen eigenen Parser —
sinnvoll als kuratiertes Nebenprojekt für 10–20 Top-VCs, nicht als Fundament.

---

## 4. Entity Resolution — das Kernrisiko

Der 27-%-Test hat gezeigt: naives Namens-Matching produziert Fehltreffer. Deshalb
strikt gestuft, und **jede Zuordnung trägt ihre Herkunft**:

**Stufe A — harte IDs (fehlerfrei).** CIK (SEC), UEI (SBIR/USAspending), Company
Number (Companies House), PIC (CORDIS), LEI (GLEIF). GLEIF liefert zusätzlich die
Brücke zwischen LEI und nationalen Register-IDs — damit koppeln US-, UK- und
EU-Records ohne Namensvergleich.

**Stufe B — normalisierter Name + Kontext-Gate.** Rechtsform und Interpunktion
entfernen, dann Match **nur wenn** ein zweites Merkmal stimmt: Land/Bundesstaat,
Stadt oder Technologiefeld (CPC-Subklasse gegen Sektor). Ohne dieses Gate entsteht
der „Realize, Inc."-Fehler.

**Stufe C — Fuzzy als Vorschlag, nie als Fakt.** Trigram-Similarity mit Score;
unterhalb der Schwelle wird die Kante als „unbestätigt" gespeichert und im
Frontend **nicht** als Substanz gezählt.

Jede Kante speichert `match_method` und `match_score`. Das Frontend zeigt nur
Stufe A und B als belegte Substanz — dieselbe Logik wie beim Grounding-Gate der
Artikel: lieber schweigen als falsch behaupten.

**Aufnahmeregel für den Korpus** (gegen die 3-%-Verwässerung): Eine Firma kommt
in den Explorer, wenn mindestens eines zutrifft — Patent-Treffer (Stufe A/B),
Paper-Treffer, SBIR-/CORDIS-Award, Trial/FDA-Eintrag, oder Form-D-Filing **in
einer Technologie-Industriegruppe**. Reine Immobilien-/Fonds-Filings bleiben
draußen, sind aber in `raw_entries` weiter vorhanden.

---

## 5. Datenmodell

Analog zu `research_*` / `patent_*`:

```sql
startup_company     -- kanonische Firma: name, slug, country, region, sector,
                    -- founded_year (falls belegt), cik, uei, lei, ch_number, pic
startup_alias       -- Namensvarianten je Firma (Quelle + Schreibweise)
startup_event       -- dated: funding_private (Form D), funding_public (SBIR/CORDIS),
                    -- launch (HN), clearance (FDA), trial (CT.gov), contract (USAspending),
                    -- trademark (USPTO/EUIPO); mit amount, currency, source_url
startup_link        -- Brücken: -> patent (pub_number), -> research work,
                    -- mit match_method, match_score
startup_search      -- FTS-Index (GIN) über Name, Alias, Abstracts
```

Die Event-Tabelle ist bewusst breit und dated — sie ist die Grundlage für die
Zeitachse auf dem Firmenprofil und für alle Lead-Time-Auswertungen.

---

## 6. Produkt: die Oberfläche

Route `/trends/foresight/startups`, konsistent mit den zwei bestehenden Explorern.

**Suchseite:** Suchfeld mit Smart-Router (Firmenname · Technologie/CPC · Sektor ·
Land · Jahr), Facetten für Sektor, Land, Signaltyp, Substanz-Achsen. Ergebnisliste
mit Firmenkarte: Name, Ort, Sektor, letztes Event, Substanz-Marker (Patente /
Paper / Förderung / Zulassung).

**Firmenprofil `/startups/[slug]`:** Stammdaten mit Quellenangabe je Feld ·
**Zeitachse aller Events** (das Herzstück) · Substanz-Block mit Links in Patent-
und Research-Explorer · Technologie-Einordnung über die CPC-Achsen der Patente,
inkl. TIR-Stand des Felds · offene Lücken werden benannt, nicht kaschiert.

**Technologie-Sicht:** „Wer arbeitet an X" — Firmen entlang einer CPC-Achse oder
eines Research-Topics, mit Reifeverteilung (nur Förderung / patentiert /
kapitalisiert / zugelassen). Das ist die Brücke zurück ins Foresight-Cockpit.

**Tier-Gating** nach bestehendem Muster („gate at the value drill-down"): Suche
und Basisprofil frei; Zeitachse, Technologie-Sicht und Export in den bezahlten
Stufen. Ein Live-Layer (frische SEC-/HN-Abfragen) analog zum Research-Live-Layer
mit Tagesbudget wäre die Super-Pro-Zugabe.

---

## 7. Kosten-Nutzen: bezahlte APIs

Die Frage war, ob bezahlte APIs die Informationsgrundlage **überproportional**
steigern. Antwort: **Inhaltlich ja, praktisch nein** — und der Grund ist nicht der
Preis allein, sondern das Recht.

### Der entscheidende Befund: Anzeigerechte sind fast nie im Preis enthalten

Öffentliche Anzeige in einem Free-Content-Produkt mit Paid-Tiers ist bei fast allen
Anbietern **nicht im Self-Serve-Zugang enthalten**. Sie ist entweder ein eigenes,
teures Lizenzprodukt (Crunchbase „Applications License" mit Attributionspflicht,
Tracxn „Commercial Redistribution Packs", Exploding Topics „Custom") oder
ausdrücklich verboten (PredictLeads-Standard-T&C: „Republish… Redistribute" —
untersagt). Man kauft also Daten, die man nicht zeigen darf.

### Was das Budget hergibt

| Anbieter | Preis (verifiziert 2026-08-19) | Was man bekommt | Anzeigen erlaubt? |
|---|---|---|---|
| **People Data Labs** | Free: 100 Records/Mon · **Pro 100 $/Mon** = 1.000 Firmen (~0,10 $/Firma) | Firmographics: Größe, Branche, Standort, Gründungsjahr | Lizenz vergleichsweise offen („any way… compliant with AUP"); **vor Einsatz schriftlich klären**, Personendaten wegen DSGVO meiden |
| **PredictLeads** | Free: 100 Credits/Mon · **ab 40 $/Mon** + 0,04 $/Credit (degressiv bis 0,002 $) | Hiring-, News-, Tech-, Financing-Signale; Job-Historie ab 2015 | **Nein** — nur als *internes* Scoring-Feature |
| **BuiltWith** | Free-API + Trends-API kostenlos (Pläne ab 295 $/Mon) | Tech-Adoption als Traktions-Proxy | Free-Teil nutzbar, T&C-Prüfung nötig |
| **Tracxn Lite** | **0 €** | 7,7M Firmen, manuelles Nachschlagen | Nur Recherche, keine Weiterverwertung |

### Was außerhalb des Budgets liegt

| Anbieter | Preis (verifiziert) | Urteil |
|---|---|---|
| Crunchbase | API nur noch **Enterprise, quote-only**; Free-Tier abgeschafft. Vendr-Median **20.000 $/Jahr** (4.396–51.639 $) | 200× über Budget; Anzeige nur mit Applications License |
| Dealroom | Premium **14.500 $/Jahr** (3 Seats), Plus 20.000 $; **API erst Enterprise** | 12× über Budget; die freien Regierungsportale darf man lesen, nicht ernten |
| Exploding Topics | Basis 249 $/Mon, **API-Add-on 1.000 $/Mon** (1.000 Requests) → real ~1.249 $/Mon | Liefert Trend-Keywords, **keine Firmendaten**; überlappt mit der eigenen Embedding-Pipeline; Produkteinbau braucht Extra-Lizenz |
| Harmonic.ai | Preise komplett quote-only | Fachlich der beste Startup-Graph, aber Sales-Call-Pflicht, realistisch 4–5-stellig |
| PitchBook / CB Insights | 12.000–30.000 $ bzw. 29.800–100.000+ $/Jahr | Research-Terminals, kein Fit |
| Specter / Sifted Pro / StartupBlink | quote-only bzw. ~1.350 $/Jahr ohne echte API | Kein Fit |
| SimilarWeb | Self-Serve-Pläne **enthalten kein API**; API nur quote-only | Kein Self-Serve-Weg |

### Empfehlung

**Kein bezahltes Abo zum Start.** Begründung: Die einzige Lücke, die Geld
schließen könnte (Runden-Semantik, Investoren, Bewertungen), kostet fünfstellig
pro Jahr — und selbst dann darf man die Daten nur mit einer gesonderten
Lizenz anzeigen. Für 100 €/Monat bekommt man Firmographics-Anreicherung
(PDL) und interne Signale (PredictLeads), aber **keinen einzigen anzeigbaren
Deal-Datensatz**.

Das Geld ist besser in die Brücken investiert, die niemand sonst hat: Firma→Patent
und Firma→Paper. Deren Kosten sind Rechenzeit, nicht Lizenzgebühr.

**Wiedervorlage-Kriterium für PDL (100 $/Mon):** wenn nach Stufe 1–3 gemessen wird,
dass bei mehr als ~30 % der Korpus-Firmen Standort oder Sektor fehlen und diese
Lücke die Facettensuche unbrauchbar macht. Vorher ist es Geld für ein Problem,
das noch niemand gemessen hat.

---

## 8. Reihenfolge und Aufwand

| # | Paket | Aufwand | Ertrag |
|---|---|---|---|
| 1 | Datenmodell + Entity Resolution (ID-first, Kontext-Gate) | mittel–hoch | Fundament; bestimmt die Qualität von allem Weiteren |
| 2 | Firma→Patent-Brücke auf vorhandenen Daten | mittel | **Das Alleinstellungsmerkmal**, ohne externe Quelle |
| 3 | Form-D-Backfill 2008–2020 | gering | 18-Jahres-Historie |
| 4 | CORDIS-Ingest (CC BY, monatlich) | gering–mittel | EU-Gegengewicht, sauberste Lizenz |
| 5 | SBIR-Ingest (Wartungsstatus prüfen!) | mittel | 40 Jahre US-Startup-R&D, harte UEI |
| 6 | Explorer-Seite + Firmenprofil | mittel–hoch | das sichtbare Produkt |
| 7 | Firma→Paper-Brücke | mittel | zweite Substanz-Achse |
| 8 | HN-Launch-Signal, Trials/FDA | gering je | Launch- und Reife-Achse |
| 9 | GLEIF/Companies House/Wikidata-Anreicherung | mittel | Stammdaten, UK-Abdeckung |

Pakete 1–3 sind ein sinnvoller erster Schnitt: danach steht ein durchsuchbarer
Korpus mit Substanz-Nachweis, ohne dass eine einzige neue externe Abhängigkeit
entstanden ist.

## 9. Betriebliche Randbedingungen

- **Mengenbremse beachten:** Die Massen-Ingester gehören in den Distill-Pfad
  (`signal_batch`), nicht in den Content-Cycle — `CYCLE_MAX_PER_SOURCE` (Default
  200/Quelle/Lauf) und die 50k-Sanity-Grenze in `scheduled_cycle.sh` gelten
  weiterhin. Der 235k-Zeilen-Vorfall vom 2026-08-20 ist der Präzedenzfall.
- **Cron:** CORDIS monatlich (Analog zu `sync_openalex_monthly.sh`), SBIR
  quartalsweise, Form D quartalsweise, HN täglich. Companies-House-Snapshot
  monatlich.
- **Doku-Pflicht:** Bei Umsetzung CLAUDE.md (Quellenzahl, Cron-Liste, Routing)
  im selben Zug mitziehen — konstitutionelle Bedingung des Repos.
- **US-Bias transparent machen:** Wie beim Radar (91,6 % US-Zulassungen) gehört
  die Verteilung sichtbar auf die Seite. CORDIS ist die einzige wirksame
  Gegenmaßnahme; DE bleibt bis zur HVD-Umsetzung eine offene Lücke.
