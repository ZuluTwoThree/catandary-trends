# Attributions-Matrix — welche Quelle welchen Lizenzhinweis braucht

Stand: 2026-09-02 (Folge des Compliance-Reviews `docs/audits/2026-09-02_compliance_review.md`,
Abschnitt 2 + 6). Zahlen = Read-only-SELECTs auf der Live-DB am 2026-09-02.

## Befund: es gibt kein Attributions-Feld

- `sources` hat **keine** Spalte für einen Lizenz-/Attributionstext (Spalten:
  id, name, feed_url, source_type, vertical, sub_categories, active,
  auto_discovered, discovery_count, last_fetched, created_at, llm_pipeline).
- `sources.yaml` kennt kein `attribution:`/`license:`-Feld (grep leer).
- Ein Trend-Artikel trägt nur `trends.source_name` (= `sources.name` der
  Ingester) + `source_url`. Das Frontend rendert Name + Link
  (`TrendArticle.tsx`), die Ventures-Seite einen festen Attributionsblock
  (`VentureAttribution.tsx`, nur `/trends/foresight/ventures`, PUBLIC_MODE-geblockt).

**Konsequenz:** Der Lizenzhinweis muss im Frontend über `source_name` gemappt
werden (Vorschlag: kleine Tabelle `lib/attribution.ts`, Schlüssel = exakter
`source_name` bzw. Präfix `OpenAlex`), bis ein Feld existiert. Ein DB-/YAML-Feld
ist erst sinnvoll, wenn mehr als die untenstehenden Namen betroffen sind —
zurzeit reicht das Mapping. **Umsetzung im Frontend: nicht Teil dieser Runde.**

## Matrix

`source_name` exakt wie in der DB. „Artikel" = `trends.status='published'`
(öffentlich sichtbar), „Signale" = `status='signal'` (nur intern/Foresight).

| `source_name` (DB) | Lizenz / Basis | Pflicht-Hinweis (EN, Artikel-Footer) | Artikel heute | Signale | Priorität |
|---|---|---|---|---|---|
| `OpenAIRE Projects (EU + National Funders)` | OpenAIRE Graph, **CC BY 4.0** (zu verifizieren: openaire.eu Terms) | *Contains data from the OpenAIRE Graph (© OpenAIRE), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); processed by Catandary.* | **40 published** | 8.505 | **HOCH — einzige Quelle mit CC-BY-Pflicht und live Artikeln** |
| `CORDIS EU Research Projects (SME Participations)` | EU CORDIS, **CC BY 4.0** (Legal-Notice der Kommission) | *Contains data from the European Union's CORDIS database (© European Union), licensed under CC BY 4.0; processed by Catandary.* — Text existiert bereits in `VentureAttribution.tsx` | 0 | 46.731 | MITTEL — Hinweis vorbereiten, greift sobald ein CORDIS-Eintrag Artikel wird (llm_pipeline ist TRUE) |
| `UKRI Gateway to Research (UK)` | **OGL v3** (zu verifizieren: gtr.ukri.org Terms) | *Contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).* | 0 | 4.485 | MITTEL — wie CORDIS |
| `NSF Awards (US Federal Research Funding)` | US-Government, Public Domain | keiner nötig; freiwillig *Source: NSF Award Search* | 0 | 10.550 | NIEDRIG |
| `NIH RePORTER (US Biomedical Funding)` | US-Government, Public Domain | keiner nötig; freiwillig *Source: NIH RePORTER* | 0 | 170.515 | NIEDRIG |
| `SBIR/STTR Awards (US Startup R&D Funding)` | US-Government, Public Domain | keiner nötig | 0 | 105.487 | NIEDRIG |
| `SEC Form D (Startup Private Offerings)` | Public Domain; `llm_pipeline=false` seit 2026-08-24 | keiner nötig (Backlink zur Filing-Seite genügt); **59 Alt-Artikel** stammen aus der Zeit vor dem Schalter | 59 | 7.103 | NIEDRIG |
| `arXiv cs.AI`, `arXiv Preprints` | arXiv-API-ToU: Metadaten frei, Attribution erwünscht; Volltexte je Paper lizenziert (nicht genutzt) | *Source: arXiv* + Backlink (bereits so) | 1.807 (cs.AI, Altbestand) | 30.619 | NIEDRIG — zu verifizieren: arXiv „Terms of Use for arXiv APIs" |
| `biorxiv Preprints`, `medrxiv Preprints` | API frei; Abstract-Nutzung — zu verifizieren | *Source: bioRxiv / medRxiv* + Backlink (bereits so) | 0 | 44.570 | NIEDRIG |
| `OpenAlex Science (…)`, `OpenAlex: …`, `OpenAlex fresh: …` (≈70 Pseudoquellen) | **CC0** | keiner nötig; Transparenz-Nennung *Data: OpenAlex (CC0)* steht auf der Paper-Seite | 0 | ~450.000 | NIEDRIG |
| `Hacker News Best` | HN-API (MIT), Algolia-Suche — ToS zu verifizieren | *Source: Hacker News* + Backlink (bereits so) | 445 | 17 | NIEDRIG |
| Companies House (nur `startup_companies`, keine `trends`) | OGL v3 + *Contains Companies House data © Crown copyright and database right* | in `VentureAttribution.tsx` vorhanden | — | — | OK (solange Ventures nicht öffentlich) |
| GLEIF, Wikidata (nur `startup_companies`) | CC0 | freiwillig, vorhanden | — | — | OK |
| openFDA 510(k), ClinicalTrials.gov (nur Ventures-Timeline) | Public Domain; openFDA-Disclaimer „not validated for clinical use" | in `VentureAttribution.tsx` vorhanden; **fehlt auf `/trends/methodology`** | — | — | NIEDRIG (Methodik-Seite) |
| RSS-Fachmedien (323 aktive Quellen) | Feed-Nutzung wie vorgesehen; Volltext = §44b UrhG (TDM) | Name + Backlink (100 % erfüllt: 0 NULL in 84.563 published) | 84.563 gesamt | — | OK |

## Was konkret zu tun ist (Frontend, später)

1. `source_name`-Mapping → Lizenzzeile im Artikel-Footer (unter der bestehenden
   Quellenzeile), für **OpenAIRE** sofort (40 live Artikel), **CORDIS** und
   **UKRI** vorbereitet. Gleiche Zeile in der Newsletter-Edition, falls ein
   solcher Artikel in die Wochenauswahl kommt (`newsletter_generator.py` nutzt
   `summary_en` + `source_name`).
2. `/trends/methodology`: openFDA-Disclaimer + OGL/CC-BY-Sammelhinweis
   (Text aus `VentureAttribution.tsx` übernehmen) + Link auf die
   Removal-Request-Sektion (`docs/compliance/takedown_notice.md`).
3. Statischer Export: dieselbe Footer-Zeile muss mit exportiert werden (kein
   API-Call nötig — reine Render-Logik).

## Offen / zu verifizieren (aus dem Audit übernommen)

- OpenAIRE-Lizenz (CC BY 4.0) und UKRI-GtR-Lizenz (OGL v3) schriftlich prüfen.
- Ob die 40 OpenAIRE-Artikel überhaupt im 30-Tage-Public-Fenster liegen
  (`published_at`), entscheidet, ob der Hinweis vor dem 01.10. live sein muss —
  das Mapping ist so oder so nötig, weil `llm_pipeline` für OpenAIRE TRUE ist.
