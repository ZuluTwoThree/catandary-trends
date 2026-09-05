# Backfill-Analyse der #97-Quellen — Archivtiefe, Menge, Aufwand (2026-09-05)

Frage des Owners: *„Wie weit zurück würde ein Backfill der neuen Quellen wirken und wie viele Signale müssten verarbeitet werden?"*

Read-only-Analyse (keine DB-Schreibbefehle, keine GPU, keine Ingest-Läufe). Rohdaten der Sondierung: `data/backfill_probe_2026-09-05.json` (gitignored, `data/`).

## Zusammenfassung

1. Von den 277 neuen Quellen (DB `sources.created_at >= 2026-09-05`; das Issue nennt 275) erreichen **187 ein echtes Archiv** — 87 über die WordPress-REST-API (gemessen), 100 über XML-Sitemaps (geschätzt); die erreichbare Tiefe liegt im **Median bei ~11 Jahren** (WP: ältester Post im Median 2010), während 48 Quellen nur ihren Feed tragen (Median 17 Tage), 10 nur eine 2-Tage-News-Sitemap haben und 29 Sitemaps keine verwertbaren Datumsangaben liefern (3 WP-Archive haben defekte Datumsfelder).
2. Ein **24-Monats-Fenster** bedeutet **~358.000 Einträge** (156.000 WP gemessen + 201.000 Sitemap geschätzt), **12 Monate ~186.000**, **6 Monate ~93.000**; bei der Durchlassquote des heutigen Erst-Polls (59 %) würden daraus **~200.000 / 104.000 / 52.000 Signale**.
3. Der Verarbeitungsaufwand ist klein — **7,8 / 4,0 / 2,0 GPU-Stunden** Distill (12,8 Einträge/s) und ~10 / 5 / 2,6 GB Speicher (der 4096-dim Embedding-Blob dominiert mit 14 KB je Eintrag) — der **Netzaufwand aber asymmetrisch**: der WP-Pfad braucht ~1 Stunde für 24 Monate (100 Posts je Request), der Sitemap-Pfad ~56 Stunden seriell bei 1 Request/s je Host (1 Fetch je Artikel; ~7 h Wandzeit mit 8 parallelen Hosts, längster Host The Next Web ~6 h).
4. **Vor jedem Lauf sind drei Anpassungen Pflicht**: `ingest_wordpress.py` fordert `content` an und speichert bei leerem `excerpt` `content.rendered[:2000]` als Teaser (= Teil-Volltext, auch bei `fulltext: false`) → nur `excerpt`; beide Ingester prüfen keine robots.txt und laufen mit falscher Kennung (`CatandaryBot/1.0` bzw. ein Chrome-Fake-UA im Sitemap-Ingester) → Produktions-UA `CatandaryTrendsBot/1.0`, robots-Verdikt je URL, 1 s Abstand; und Backfill-Zeilen müssen **noch am selben Abend** per `signal_batch --backend distill` verarbeitet werden, weil der 04:00-Cycle sonst je Quelle 200 unverarbeitete Altzeilen in die Artikelgenerierung zieht bzw. am 50k-Guard abbricht (277 × 200 = 55.400).
5. **Empfehlung: Phase 1 = WP-Pfad, 12 Monate, alle 87 messbaren Quellen** (80.000 Einträge, 1,7 GPU-h, < 1 h Netz, ~44.000 Signale, robots-konform, exakt datiert); **Phase 2 = Sitemap-Pfad nur für die 57 Sitemap-Quellen mit ≥ 60 % Durchlass** (52.000 Einträge, ~14 h Netz), und 24 Monate erst, wenn die Distill-Keep-Quote der Phase 1 ≥ 50 % bestätigt — Feed-only-Quellen bleiben, was sie sind.

## Datengrundlage und Methode

**Quellen.** 277 Zeilen in `sources` mit `created_at >= '2026-09-05'` (00:51–00:56 Uhr, Erst-Poll), alle in `sources.yaml` mit `tdm_status: ok`, 24 mit `fulltext: true` und offener Lizenz (CC BY / OGL / US Public Domain). Typen: 167 trade_media, 95 research, 12 brand, 3 press_wire. Verteilung: TECH 72, ECO 41, FOOD 33, BIZ 31, LIFESTYLE 31, HEALTH 26, DESIGN 26, FASHION 14, CROSS 3.

**Erst-Poll (heute).** 7.314 `raw_entries`; Median-Zeitspanne je Feed 14,5 Tage, p90 80 Tage. Bis 10:45 Uhr waren 6.438 Einträge relevanz-bewertet (`classification_json` gesetzt oder `filtered_out`), 3.816 davon durchgelassen → **Durchlassquote 59,3 %** (je Vertikale: ECO 81 %, HEALTH 74 %, TECH 66 %, BIZ 61 %, FOOD 55 %, FASHION 41 %, DESIGN 37 %, LIFESTYLE 20 %, CROSS 13 %). Die Quote stammt aus dem hybriden RSS-Gate (Distill-Ränder + 8B-Band); der reine Distill-Pfad mit Schwelle 0,5 kann abweichen (heutiger Samstagslauf: 11.351 von 14.974 = 76 % behalten, anderer Korpus).

**Sondierung.** 273 Hosts (frontiersin.org trägt 4 Quellen, spectrum.ieee.org 2 — deren Zahlen sind anteilig aufgeteilt). Je Host: `robots.txt` + höchstens 3 Content-Requests, insgesamt 778 Content-Requests + 273 robots.txt, UA `CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology; trends@catandary.de)`, ≥ 1 s Abstand je Host, 8 Hosts parallel, 15 s Timeout, 184 s Laufzeit. robots-Verdikt per `pipeline.article_fetcher.robots_allows` (RFC 9309) für `/wp-json/wp/v2/posts`, Sitemap-URL und eine Beispiel-Artikel-URL aus der DB. Kein Crawl, keine Artikelseiten.

- **WP-Pfad:** `GET /wp-json/wp/v2/posts?per_page=1&orderby=date&order=asc` → `X-WP-Total` (Gesamt) + ältestes Datum; dann `after=2025-09-05` und `after=2024-09-05` → Zählung 12 / 24 Monate (gemessen). 6 Monate = 12 M / 2 (Schätzung). Nur, wenn robots `/wp-json/` erlaubt.
- **Sitemap-Pfad:** robots-`Sitemap:`-Zeilen, sonst `/sitemap.xml`, `/sitemap_index.xml`; bei Index genau **eine** Teil-Sitemap gelesen (bevorzugt post/article/news-Muster). urlset: URLs + `lastmod`-Verteilung gezählt. Index: Gesamt ≈ Content-Teil-Sitemaps × URLs der gelesenen Teil-Sitemap; Jahresrate aus lastmod-Spanne der Teil-Sitemap, sonst Jahreszahlen in Sitemap-Namen, sonst Index-lastmod-Spanne (≥ 365 d), sonst Feed-Rate des Erst-Polls; Deckel 3 × Feed-Rate und 150/Tag; Tiefe bei 30 Jahren gekappt. **`lastmod` ist ein Änderungs-, kein Publikationsdatum** — alle Sitemap-Zahlen sind Schätzungen und vor einem Lauf per `--dry-run` nachzumessen.
- **nur Feed:** weder WP noch Sitemap erreichbar → Tiefe = Erst-Poll-Spanne.

**Kostenmodell.** Distill 12,8 Einträge/s (heute: 16.562 → 14.974 nach Titel-Dedup in 1.106 s inkl. Embeddings). Netz: WP `⌈n/100⌉ + Monate` Requests je Host, Sitemap `n + 3` (1 Fetch je Artikel für og:title/og:description), je 1 s; Wandzeit = max(seriell/8, längster Host). Speicher: `raw_entries`-Zeile der neuen Quellen Ø 15,8 KB (14,1 KB `embedding_blob`, 0,5 KB Teaser), Signal-Zeile in `trends` Ø 21 KB (Vektor). Relevanz je Quelle = Durchlass des Erst-Polls (≥ 5 bewertete Einträge, sonst Vertikalen-Durchschnitt).

## Ergebnis je Vertikale

| Vertikale | Quellen | WP nutzbar | Sitemap nutzbar | Sitemap unbestimmt | News-Sitemap | nur Feed | Tiefe Median / Max (J.) | Einträge 6 M | 12 M | 24 M | GPU-h 6/12/24 | Netz-h seriell 24 M | Durchlass Erst-Poll |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|---:|---:|
| FOOD | 33 | 13 | 10 | 1 | 4 | 5 | 13.7 / 30.0 | 5.910 | 11.817 | 23.324 | 0.1 / 0.3 / 0.5 | 3.3 | 55 % |
| TECH | 72 | 18 | 30 | 10 | 1 | 13 | 9.5 / 30.0 | 27.268 | 54.110 | 98.935 | 0.6 / 1.2 / 2.1 | 21.3 | 66 % |
| HEALTH | 26 | 7 | 11 | 4 | 0 | 4 | 9.5 / 26.7 | 4.875 | 10.606 | 21.030 | 0.1 / 0.2 / 0.5 | 3.0 | 74 % |
| ECO | 41 | 11 | 16 | 7 | 0 | 7 | 11.9 / 30.0 | 9.049 | 17.867 | 35.709 | 0.2 / 0.4 / 0.8 | 3.8 | 81 % |
| DESIGN | 26 | 9 (+1 defekt) | 9 | 1 | 0 | 6 | 18.6 / 30.0 | 4.339 | 8.580 | 16.985 | 0.1 / 0.2 / 0.4 | 3.3 | 37 % |
| FASHION | 14 | 7 (+2 defekt) | 2 | 1 | 0 | 2 | 8.2 / 26.1 | 4.684 | 9.233 | 17.645 | 0.1 / 0.2 / 0.4 | 1.9 | 41 % |
| BIZ | 31 | 10 | 11 | 1 | 2 | 7 | 12.3 / 30.0 | 13.908 | 27.771 | 54.109 | 0.3 / 0.6 / 1.2 | 7.0 | 61 % |
| LIFESTYLE | 31 | 12 | 10 | 3 | 2 | 4 | 13.6 / 30.0 | 20.953 | 41.859 | 81.500 | 0.5 / 0.9 / 1.8 | 11.1 | 20 % |
| CROSS | 3 | 0 | 1 | 1 | 1 | 0 | 3.3 / 3.3 | 2.104 | 4.198 | 8.396 | 0.0 / 0.1 / 0.2 | 2.3 | 13 % |
| **Gesamt** | 277 | 87 (+3 defekt) | 100 | 29 | 10 | 48 | 11.0 / 30.0 | 93.090 | 186.041 | 357.633 | 2.0 / 4.0 / 7.8 | 57.1 | 59 % |

„Sitemap unbestimmt" = Sitemap vorhanden, aber ohne Datum/Teil-Sitemap (z. B. Inside Higher Ed 97.500 URLs, HZDR 20.198, Swiss IT Magazine 27.064, Bauwelt 16.126 — zusammen ~285.000 URLs ohne Zeitachse, nicht in den Summen). „defekt" = WP-API antwortet, aber alle Posts tragen das heutige Datum (Apparel Resources 52.228, Textile World 26.594, UX Magazine 2.420) — `after=` filtert dort nicht. GPU-h = Distill-Durchsatz; die Netzstunden sind seriell bei 1 Request/s (WP-Anteil gesamt ~1 h, Sitemap ~56 h).

### Pfade im Detail

| Pfad | Quellen | Archiv gesamt | 6 M | 12 M | 24 M | Netz seriell 24 M | Bemerkung |
|---|---:|---:|---:|---:|---:|---:|---|
| WordPress-API | 87 (+3 defekt) | 1.390.000 Posts | 40.000* | 80.000 | 156.000 | 1,0 h | gemessen; 100 Posts/Request; ältester Post Median 2010 |
| Sitemap (schätzbar) | 100 | — | 53.000 | 106.000 | 201.000 | 56,0 h | 1 Fetch je Artikel; lastmod ≠ Publikationsdatum |
| Sitemap (unbestimmt) | 29 | ≥ 285.000 URLs | – | – | – | – | keine Zeitachse, Nachmessung per `--dry-run` nötig |
| News-Sitemap | 10 | 2 Tage | 0 | 0 | 0 | – | Arc/„news-sitemap" (Bakery and Snacks, Confectionery News, Morning Advertiser, BigHospitality, UKTN, manager magazin, IT Finanzmagazin, DWDL, Human Resources Manager, APA-OTS) — wie Feed |
| nur Feed | 48 | Erst-Poll (Median 17 d) | 0 | 0 | 0 | – | 8 × 401/403/429 (GlobalData ×2, HPCwire, Robot Report, edie, Design World, Art Newspaper, EMA), Rest ohne WP/Sitemap unter der Root (Fraunhofer-Institute, KIT, ETH, CDC, FDA, FTC, Fed, BLS, W3C …) |

\* 6-Monats-Wert des WP-Pfads = 12 M / 2 (Schätzung).

## Top-20 nach Archivtiefe × Relevanz

Relevanz = Durchlass des Erst-Polls (n = bewertete Einträge); nur Quellen mit erreichbarem Archiv und gemessener Quote.

| # | Quelle | Vert. | Pfad | Tiefe (J.) | Durchlass (n) | Einträge 12 M | 24 M | erw. Signale 24 M | Basis |
|---:|---|---|---|---:|---:|---:|---:|---:|---|
| 1 | Electronics Weekly | TECH | wp | 29.3 | 100 % (10) | 2.854 | 5.651 | 5.651 | Rate total/n12 (Datumsfeld defekt) |
| 2 | PharmaTimes | HEALTH | wp | 26.7 | 100 % (10) | 367 | 769 | 769 | ältester WP-Post |
| 3 | TriplePundit | ECO | wp | 26.8 | 90 % (10) | 177 | 515 | 464 | ältester WP-Post |
| 4 | Digital Commerce 360 | BIZ | wp | 26.7 | 90 % (10) | 1.007 | 2.150 | 1.935 | ältester WP-Post |
| 5 | Innovation in Textiles | FASHION | wp | 22.9 | 100 % (9) | 626 | 1.221 | 1.221 | Rate total/n12 (Datumsfeld defekt) |
| 6 | Prepared Foods | FOOD | sitemap | 30.0 | 73 % (30) | 782 | 1.564 | 1.147 | total/Rate (≥30 J., gekappt) |
| 7 | Semiconductor Digest | TECH | wp | 24.4 | 87 % (100) | 1.184 | 2.532 | 2.203 | ältester WP-Post |
| 8 | Solarserver | ECO | sitemap | 22.7 | 92 % (75) | 3.476 | 6.952 | 6.396 | ältestes lastmod |
| 9 | Food Engineering | FOOD | sitemap | 30.0 | 67 % (30) | 476 | 952 | 635 | total/Rate (≥30 J., gekappt) |
| 10 | TechNode | TECH | wp | 20.5 | 95 % (208) | 1.055 | 2.220 | 2.113 | ältester WP-Post |
| 11 | Laboratory News | TECH | wp | 21.6 | 90 % (10) | 252 | 486 | 437 | ältester WP-Post |
| 12 | PV Tech | ECO | wp | 19.9 | 95 % (150) | 1.856 | 3.711 | 3.513 | ältester WP-Post |
| 13 | Ernährungs Umschau | FOOD | wp | 26.7 | 70 % (10) | 114 | 225 | 158 | ältester WP-Post |
| 14 | Medical Design & Outsourcing | HEALTH | wp | 23.1 | 80 % (25) | 562 | 1.144 | 915 | ältester WP-Post |
| 15 | Chemistry World News | TECH | sitemap | 30.0 | 62 % (13) | 3 | 7 | 4 | Jahre in Sitemap-Namen (≥30 J., gekappt) |
| 16 | Anthropocene Magazine | ECO | wp | 16.6 | 100 % (30) | 215 | 428 | 428 | ältester WP-Post |
| 17 | Germanwatch | ECO | sitemap | 30.0 | 55 % (20) | 58 | 117 | 64 | ältestes lastmod (≥30 J., gekappt) |
| 18 | Mongabay | ECO | wp | 21.4 | 75 % (32) | 1.877 | 3.521 | 2.641 | ältester WP-Post |
| 19 | futurezone | TECH | sitemap | 24.7 | 65 % (20) | 22 | 45 | 29 | Jahre in Sitemap-Namen |
| 20 | Longevity.Technology | HEALTH | wp | 16.5 | 96 % (200) | 2.058 | 3.011 | 2.906 | ältester WP-Post |

Die reine Tiefe belohnt alte WP-Blogs mit kleinen Jahresmengen (PharmaTimes 367/Jahr, Laboratory News 252/Jahr). Für die Planung zählt eher, **wo die Signale liegen**:

### Top-15 nach erwarteten Signalen (24 Monate)

| # | Quelle | Vert. | Pfad | Einträge 24 M | Durchlass | erw. Signale 24 M | Tiefe (J.) | Schätzbasis |
|---:|---|---|---|---:|---:|---:|---:|---|
| 1 | The Next Web | TECH | sitemap | 21.074 | 90 % | 18.967 | 10.5 | total≈Teil-Sitemaps×URLs/Teil-Sitemap; Rate=total/Index-lastmod-Spanne |
| 2 | Interesting Engineering | TECH | sitemap | 13.505 | 100 % | 13.505 | 9.7 | total≈Teil-Sitemaps×URLs/Teil-Sitemap; Rate=Teil-Sitemap/lastmod-Spanne |
| 3 | etailment | BIZ | sitemap | 10.950 | 90 % | 9.855 | 5.5 | total≈Teil-Sitemaps×URLs/Teil-Sitemap; Rate=Feed-Rate (Erst-Poll) |
| 4 | pv magazine International | ECO | wp | 8.753 | 90 % | 7.878 | 16.3 | n6≈n12/2 |
| 5 | Solarserver | ECO | sitemap | 6.952 | 92 % | 6.396 | 22.7 | total≈Teil-Sitemaps×URLs/Teil-Sitemap; Rate=Teil-Sitemap/lastmod-Spanne |
| 6 | Silicon Canals | TECH | sitemap | 15.000 | 40 % | 6.000 | 2.4 | total≈Teil-Sitemaps×URLs/Teil-Sitemap; Rate=total/Index-lastmod-Spanne |
| 7 | GamesMarkt | LIFESTYLE | sitemap | 17.219 | 33 % | 5.740 | 2.7 | total≈Teil-Sitemaps×URLs/Teil-Sitemap; Rate=Teil-Sitemap/lastmod-Spanne |
| 8 | Electronics Weekly | TECH | wp | 5.651 | 100 % | 5.651 | 29.3 | n6≈n12/2; depth |
| 9 | Elektronik Praxis | TECH | sitemap | 7.300 | 75 % | 5.475 | 2.9 | total≈Teil-Sitemaps×URLs/Teil-Sitemap; Rate=Feed-Rate (Erst-Poll) |
| 10 | Tech.eu | BIZ | sitemap | 5.488 | 95 % | 5.214 | 7.6 | total≈Teil-Sitemaps×URLs/Teil-Sitemap; Rate=Teil-Sitemap/lastmod-Spanne |
| 11 | Trending Topics | BIZ | wp | 6.037 | 70 % | 4.226 | 12.3 | n6≈n12/2 |
| 12 | HIT Consultant | HEALTH | wp | 4.148 | 100 % | 4.148 | 10.2 | n6≈n12/2; depth |
| 13 | CGIAR | FOOD | sitemap | 3.981 | 90 % | 3.583 | 5.0 | total≈Teil-Sitemaps×URLs/Teil-Sitemap; Rate=Teil-Sitemap/lastmod-Spanne |
| 14 | PV Tech | ECO | wp | 3.711 | 95 % | 3.513 | 19.9 | n6≈n12/2 |
| 15 | Tech Funding News | BIZ | wp | 4.916 | 70 % | 3.441 | 5.1 | n6≈n12/2 |

Die Sitemap-Werte von The Next Web, Interesting Engineering, Silicon Canals, GamesMarkt und etailment sind Rate-Extrapolationen über große Archive (109.000 / 62.000 / 15.000 / 23.000 / 30.000 URLs) und daher die unsichersten Zahlen der Tabelle.

## fulltext-Quellen (offene Lizenz)

Nur diese 24 Quellen dürfen überhaupt Volltext tragen — und selbst dort ist Volltext im Backfill nutzlos, weil `purge_raw_content.py` ihn nach 14 Tagen wieder löscht (Richter-Fenster) und der Distill-Pfad nur Titel + Teaser einbettet. **Backfill = Titel/Teaser für alle 277, ohne Ausnahme.**

| Quelle | Vert. | Lizenz | Pfad | nutzbar | Einträge 24 M | Tiefe (J.) |
|---|---|---|---|---|---:|---:|
| BLS Latest | BIZ | Public Domain (US federal) | feed | nein | – | 0.0 |
| Census Bureau Economic Indicators | BIZ | Public Domain (US federal) | sitemap | ja | 120 | 4.9 |
| FTC Press Releases | BIZ | Public Domain (US federal) | feed | nein | – | 0.0 |
| Federal Reserve Press Releases | BIZ | Public Domain (US federal) | feed | nein | – | 0.2 |
| SEC Press Releases | BIZ | Public Domain (US federal) | sitemap | ja | 276 | 29.4 |
| EU Commission Press Corner | CROSS | CC BY 4.0 | sitemap | nein | – | 0.0 |
| GOV.UK News and communications | CROSS | OGL v3.0 | sitemap | ja | 8.396 | 3.3 |
| Clean Energy Wire | ECO | CC BY 4.0 | sitemap | ja | 1.683 | 11.9 |
| Frontiers in Energy Research | ECO | CC BY 4.0 | sitemap | ja | 0 | 4.7 |
| JRC Joint Research Centre | ECO | CC BY 4.0 | sitemap | ja | 572 | 10.6 |
| Frontiers in Nutrition | FOOD | CC BY 4.0 | sitemap | ja | 0 | 4.7 |
| CDC | HEALTH | Public Domain (US federal) | feed | nein | – | 0.2 |
| ECDC | HEALTH | CC BY 4.0 | sitemap | ja | 243 | 9.3 |
| FDA | HEALTH | Public Domain (US federal) | feed | nein | – | 0.1 |
| Frontiers in Bioengineering and Biotechnology | HEALTH | CC BY 4.0 | sitemap | ja | 0 | 4.7 |
| eLife | HEALTH | CC BY 4.0 | sitemap | ja | 4.082 | 13.9 |
| Global Voices | LIFESTYLE | CC BY 3.0 | wp | ja | 1.726 | 21.9 |
| Hochschulforum Digitalisierung | LIFESTYLE | CC BY-SA 4.0 | sitemap | ja | 168 | 11.9 |
| DARPA | TECH | Public Domain (US federal) | sitemap | ja | 328 | 11.3 |
| Frontiers in Materials | TECH | CC BY 4.0 | sitemap | ja | 0 | 4.7 |
| ITU News | TECH | CC BY-SA 3.0 IGO | feed | nein | – | 0.1 |
| NIST News | TECH | Public Domain (US federal) | sitemap | ja | 230 | 17.6 |
| SciDev.Net | TECH | CC BY 4.0 | feed | nein | – | 0.2 |
| USPTO News | TECH | Public Domain (US federal) | sitemap | ja | 6.097 | 5.6 |

Die vier Frontiers-Journale teilen sich frontiersin.org (Teil-Sitemap „research-topic-magazines" ohne Artikelrate → 0); für sie und eLife ist der bestehende OpenAlex-Pfad (`research_corpus`, Metadaten) der richtige Archivzugang, nicht die Sitemap.

## Compliance-Filter

**robots.txt sperrt den Archiv-Endpunkt** (`/wp-json/` Disallow für unseren UA): **CGIAR, Silicon Canals** → nicht per WP nutzbar, beide fallen auf die Sitemap zurück (in den Zahlen so gerechnet). Kein Host sperrt die Beispiel-Artikel-URL für `CatandaryTrendsBot`.

**Technisch geblockt (401/403/429, kein robots-Verbot, aber Betreiber-Wille):** Just Drinks, Just Style (GlobalData 401), Food Safety Tech, Swiss IT Magazine, Microsoft Source, CERN, Solarserver, BSW-Solar, IT Finanzmagazin, EHI Retail Institute, Human Resources Manager, Hochschulforum Digitalisierung (WP-API 401 — API abgeschaltet, teils Sitemap nutzbar); The Robot Report, HPCwire, edie, db deutsche bauzeitung, Design World, The Art Newspaper, APA-OTS (403 — Bot-Block); EMA (Sitemap 429). Für diese gilt: **kein Backfill über den geblockten Endpunkt**, auch nicht mit anderem UA.

**Was die Ingester heute speichern — und was zu ändern ist:**

| Skript | Befund | Anpassung vor dem ersten Lauf |
|---|---|---|
| `scripts/ingest_wordpress.py` | `_fields=date,link,title,excerpt,content` — fordert den Volltext an; bei leerem `excerpt` wird `content.rendered[:2000]` als Teaser gespeichert (`ingest_one`, Z. 200) → Teil-Volltext auch bei `fulltext: false`. UA `Mozilla/5.0 (compatible; CatandaryBot/1.0; …)` ≠ Produktions-UA. Keine robots.txt-Prüfung. `sleep(0.3)` zwischen Seiten. Kein `raw_content` (gut). | **nur `excerpt`** (Feld `content` aus `_fields` streichen; leerer excerpt → Titel-only-Eintrag oder überspringen), `pipeline.article_fetcher.UA` verwenden, `robots_allows()` für `/wp-json/wp/v2/posts` vor dem ersten Request, `sleep(1.0)`. `fulltext: true` ändert nichts — Volltext gehört nicht in den Backfill (14-Tage-Retention). |
| `scripts/ingest_sitemap.py` | UA ist ein **Chrome-Fake** (`Mozilla/5.0 (Windows NT 10.0 …) Chrome/120.0`) — verstößt gegen die ehrliche Crawler-Identität aus der Compliance-Review 2026-09-02. Keine robots-Prüfung je Artikel-URL. `sleep(0.8)`. Speichert og:title/og:description (Teaser, gut). `--max-fetch 300` Default. | Produktions-UA, `robots_allows()` je Artikel-URL und Sitemap, `sleep(1.0)`, TDM-Header/Meta der Artikelseite auswerten (`tdm_reservation_in_headers/_html` existieren im Fetcher). |
| `scripts/ingest_backfill.py` / `probe_source_apis.classify` | Routet `type: research` ohne WP-Treffer nach **OpenAlex** (`ingest_openalex.py`) — 41 der 95 research-Quellen (28 nur-Feed + 13 unbestimmte Sitemaps: Fraunhofer, KIT, ETH, Helmholtz, Leibniz, CERN, Microsoft Research …) haben dort kein Journal → stiller 0-Treffer. WP-Probe ohne robots-Check, UA `CatandaryBot/1.0`. | Institutionelle research-Quellen per `ingest_via: OTHER` (oder `PRESS_HOSTS`) markieren; Probe robots-treu und mit Produktions-UA. |
| Markierung | Beide Ingester schreiben `raw_entries` mit `processed=false`, echtem `published_date`, **ohne Backfill-Flag** — unterscheidbar nur über `fetched_at`/id-Wasserzeichen. | Vor dem Ingest `max(id)` notieren und den Distill-Lauf mit `--min-id` scopen (siehe Risiko 1). |

**30-Tage-Export.** Der Distill-Pfad legt Backfill-Treffer als `trends.status='signal'` an; der statische Export und alle Feed-Queries filtern `status='published'` und `sort_date` (Trigger: `COALESCE(raw_entries.published_date, created_at)`) — alte Signale erscheinen weder im Export noch in den 30-Tage-Zählern. Diese Sicherheit gilt **nur, solange kein Backfill-Eintrag den Artikel-Cycle erreicht** (Risiko 1).

## Empfehlung

1. **Fenster: 12 Monate.** 186.000 Einträge, 4 GPU-h, ~104.000 Signale — ausreichend für Cluster-/Momentum-Historie der neuen Quellen; 24 Monate verdoppeln die Menge, bringen aber vor allem Sitemap-Schätzwerte. 6 Monate lohnen den Aufwand kaum (die Feeds tragen bereits 14–80 Tage).
2. **Phase 1 — WP-Pfad zuerst** (87 Quellen, 80.000 Einträge, 1,7 GPU-h, ~0,5 h Netz, ~44.000 erwartete Signale): exakt datiert, 100 Posts je Request, robots-konform, bei 1 Request/s in einem Abend erledigt. Reihenfolge nach erwarteten Signalen (12 M): pv magazine International, Electronics Weekly, Trending Topics, Tech Funding News, Longevity.Technology, HIT Consultant, PV Tech, Energy-Storage.news, Innovations in Food Technology, Mongabay, Quantum Computing Report; LIFESTYLE-Archive (Musikwoche 3.041/Jahr bei 20 % Vertikalen-Durchlass) mit `ingest_cap` drosseln.
3. **Phase 2 — Sitemap-Pfad selektiv:** nur die 57 Sitemap-Quellen mit ≥ 60 % Durchlass (52.000 Einträge/12 M, ~14 h Netz, hosts-parallel ~2–3 h Wandzeit), jede vorher per `--dry-run` nachgemessen; Kandidaten mit hoher Signalerwartung: Interesting Engineering, The Next Web, etailment, Solarserver, Tech.eu, Elektronik Praxis, CGIAR. Quellen mit < 40 % Durchlass (GamesMarkt, Silicon Canals, Design-/Lifestyle-Sitemaps) auslassen — jeder Artikel kostet einen Fetch.
4. **Nicht anfassen:** 48 Feed-only-, 10 News-Sitemap-, 20 geblockte Quellen und die 4 Frontiers-Journale (OpenAlex-Pfad).
5. **Betriebsablauf je Abend:** `max(raw_entries.id)` notieren → Ingest (Batch ≤ ~40 Quellen) → sofort `scripts/signal_batch.py --backend distill --min-id <id> --execute` (GPU-Handover wie in `weekly_ingesters.sh`) → Kontrolle, dass vor 04:00 keine unverarbeiteten Backfill-Zeilen übrig sind. Kein Lauf an einem Freitag (Samstags-Ingester) und nicht parallel zum Full Cycle.
6. **Vorher ändern** (Tabelle oben): excerpt-only + `content` aus `_fields`, Produktions-UA in beiden Ingestern, robots-Verdikt je Endpunkt/URL, 1 s Abstand, `ingest_via: OTHER` für institutionelle research-Quellen. Tests für `ingest_wordpress.ingest_one` (leerer excerpt → kein content-Fallback) ergänzen.

## Risiken

1. **Backfill läuft in die Artikelgenerierung.** `scheduled_cycle.sh` arbeitet mit `WATERMARK=0`; `get_unprocessed_entries` nimmt je Quelle bis zu `CYCLE_MAX_PER_SOURCE=200` **älteste** unverarbeitete Zeilen (`ORDER BY fetched_at, id`). Bleiben Backfill-Zeilen über Nacht liegen, werden bis zu 200 je Quelle zu Artikeln (Verstoß gegen „nur Signale für Altbestand"), und bei mehr als ~250 betroffenen Quellen kippt der 50k-Sanity-Guard den ganzen Nachtlauf (277 × 200 = 55.400). Gegenmittel: Distill im selben Abend, Batches ≤ 40 Quellen, `--min-id`.
2. **Sitemap-Zahlen sind Schätzungen.** `lastmod` ist ein Änderungsdatum; Teil-Sitemaps mischen Seitentypen (Drupal `sitemap.xml?page=N`), Gesamt ≈ Teil-Sitemaps × Stichprobe. Die 201.000 Sitemap-Einträge (24 M) können real um den Faktor 2 in beide Richtungen abweichen; 29 weitere Sitemaps (≥ 285.000 URLs) sind gar nicht datierbar. Nur der WP-Anteil (156.000 / 80.000) ist belastbar.
3. **Durchlassquote ≠ Distill-Keep.** 59 % stammen aus dem hybriden RSS-Gate auf heutigen Nachrichten; ältere Einträge, Feeds mit vielen Produktmeldungen (about-drinks 17 %) und die Distill-Schwelle 0,5 können die Signalzahl deutlich ändern. Erst nach Phase 1 messen.
4. **Speicher wächst durch Embeddings, nicht durch Text.** 15,8 KB je Eintrag (auch gefilterte, Trend-Drift-Hedge) + 21 KB je Signal: 12 Monate ≈ 5 GB, 24 Monate ≈ 10 GB in einer 44-GB-`raw_entries`-Tabelle — tragbar, aber Backup-Dumps (~113 GB, 18 min) wachsen mit.
5. **Netz-Etikette beim Sitemap-Pfad.** 1 Fetch je Artikel: The Next Web allein ~6 h für 24 Monate. Bot-Blocker (Cloudflare) reagieren auf Volumen; 429 bei EMA zeigt, dass auch öffentliche Stellen drosseln. Pro Host nie mehr als 1 Request/s, bei 403/429 sofort abbrechen (Circuit-Breaker wie im WP-Ingester fehlt im Sitemap-Ingester).
6. **Defekte Datumsfelder** (3 WP-Archive, Electronics Weekly `0209-01-10`, Retail Gazette `0202-11-26`, ARTnews `1965-01-01`) verfälschen `published_date` und damit `sort_date`; Backfill-Insert sollte Daten vor 1990 und nach „heute" verwerfen.
7. **Geteilte Hosts** (frontiersin.org, spectrum.ieee.org) und Zweit-Domains (BigHospitality → restaurantonline.co.uk, Natural Products Insider → supplysidesj.com, It's Nice That via Feedburner) — WP-/Sitemap-Zahlen gelten je Host, nicht je Feed; ein Ingest je Quelle würde doppelt ziehen (URL-Dedup fängt Duplikate, aber nicht die Requests).

## Rohdaten

- `data/backfill_probe_2026-09-05.json` — je Host: robots-Verdikte, WP-Gesamt/ältestes Datum/12 M/24 M, Sitemap-Index/Teil-Sitemap-Zählungen, Request-Log (gitignored).
- Berechnung reproduzierbar aus dieser JSON plus `sources`/`raw_entries` (Erst-Poll-Durchlass, Feed-Spannen); Rechenregeln oben unter „Methode".
