# Quellen-Triage WP2b (2026-09-04, #97): `feed_error`-Kandidaten und internationale Tech-Quellen

Stand: 2026-09-04. Fortsetzung von `source_candidates_2026-09-04.md` (708 Kandidaten, 294 `feed_error`). Hier: (1) manuelle Feed-Suche für die wertvollsten `feed_error`-Kandidaten (Forschungseinrichtungen, Behörden, Deep-Tech-Fachmedien, AI-Labs, Normung) — RSS-/Presse-Seiten, `/rss`, Subdomains, Feed-Übersichtsseiten, `<link rel=alternate>` auf Unterseiten, CMS-typische Pfade (TYPO3 `?type=9818`, Plone `@@rss`, Arc `outboundfeeds`) — und (2) die benannte Liste internationaler Tech-Quellen. Alle gefundenen Feeds durch `scripts/probe_source_compliance.py`. Etikette: ehrlicher Bot-UA, robots.txt vor jedem Request (Werkzeug-`RobotsCache`), 1 Request/s/Host, je Site höchstens ~10 Feed-/Seiten-Requests, keine Crawls. Requests gesamt: 1715 (Feed-Suche, 4 Läufe) + 220 (Probe).

## Zahlen

- **Triage `feed_error`:** 213 Kandidaten manuell gesucht (von 294; Rest siehe „Nicht priorisiert“) — Feed gefunden 39, davon `tdm_status: ok` 30 (KIT nach manueller Artikelprüfung), blocked 49 (Bot-Wall/robots), kein Feed oder unbrauchbar 134; aufgenommen 26.
- **International (benannte Liste):** 70 geprüft — gefunden 37, ok 35, blocked 12, kein Feed 23; aufgenommen 30. Bereits aktiv (nicht erneut geprüft): Apple Newsroom, Crunchbase News, EU-Startups, Google DeepMind, IEEE Spectrum (+AI, Robotics), KrASIA, McKinsey, NVIDIA Blog, Quanta Magazine, Rest of World, Samsung Newsroom, Sifted, Tech.eu.
  - (a) Asien/Global: 8 geprüft / gefunden 7 / ok 6 / blocked 2 / kein Feed 0 / aufgenommen 2
  - (b) Europa außerhalb DACH: 14 geprüft / gefunden 9 / ok 8 / blocked 2 / kein Feed 4 / aufgenommen 8
  - (c) Analystenhäuser/Newsrooms: 10 geprüft / gefunden 1 / ok 1 / blocked 2 / kein Feed 7 / aufgenommen 1
  - (d) Normung/Policy: 10 geprüft / gefunden 5 / ok 5 / blocked 2 / kein Feed 3 / aufgenommen 5
  - (e) Vendor-Newsrooms: 15 geprüft / gefunden 7 / ok 7 / blocked 4 / kein Feed 4 / aufgenommen 6
  - (f) AI-Labs/Deep-Tech-Medien: 13 geprüft / gefunden 8 / ok 8 / blocked 0 / kein Feed 5 / aufgenommen 8
- **Neu in `sources.yaml`: 56** (davon `fulltext: true` mit offener Lizenz 4: JRC CC BY 4.0, USPTO + Census Bureau Public Domain, ITU News CC BY-SA 3.0 IGO). Je Vertikale: BIZ 7, CROSS 1, DESIGN 2, ECO 7, FOOD 3, HEALTH 2, TECH 34. Aktive RSS-Quellen 414 → 470, mit Volltext 161 → 165. `verify_feed` 56/56, pytest 648 passed.
- **Bemerkenswert:** viele Institutionen haben Feeds nur an CMS-spezifischen Pfaden (UBA `/rss/presse`, KIT `kit.edu/pi.rss`, Jülich Plone-`@@rss`, JRC `node/2/rss_en`, USPTO `/rss.xml`, EMA `/en/news.xml`, DIW `/de/rss_press.xml`, Chemistry World `/409.rss`, Fraunhofer IVV `/de/rss/news.rss`, TYPO3 `?type=9818` bei DUH/ZHAW). Bund.de-Ressorts (BMFTR, BSI) sperren den `/SiteGlobals/`-Feedpfad per robots.txt (Owner-Entscheid wie Förderinfo/idw offen). Bot-Walls (403/401/429 auf allen Pfaden): IRENA, Empa, DFKI, CACM/ACM Queue, WEF, IMF-RSS, Gartner, IDC, PitchBook, ISO, IEC, Sony, TSMC, Ericsson, Nokia, e27, EDN, Embedded, Cosmos, The Scientist, MD+DI, Digital Health, Packaging Digest/World, Chain Store Age, Mining Weekly, PhocusWire, Travel Weekly, Library Journal, SportsPro, Computing, Discover. Feed offen, Artikel 403 (→ WP4-Kontaktliste): OpenAI, Spektrum der Wissenschaft, Labiotech, Psychiatric Times, electrive, Windpower Monthly, L'Usine Digitale, strategy+business, Tech in Asia. Leere Feeds (RSS ohne Items): Metropolis, Interior Design, Fitt Insider, H2 View, RNE, Fashion for Good, IISD, WWF, USGS, Startup Valley. Kein Feed (auch auf RSS-/Presse-Seiten nicht verlinkt): DLR, DKFZ, IEA, NREL (nicht erreichbar), NICE, C&EN (Feed-Verweise 404), Agora, dena, Öko-Institut, Ellen MacArthur Foundation, Max Rubner-Institut, Thünen, DLG, TU Wien, CSIRO, ENISA, CORDIS, Anthropic, Stanford HAI, Berkeley BAIR (Timeout), Meta AI Blog, Qualcomm, Bosch, ABB, Schneider, Deloitte, Accenture, Dealroom, UNESCO, BCG, Bain.
- **Owner-Entscheide (ok geprüft, nicht eingetragen):** Nikkei Asia (`rss/feed/nar`), Japan Times (`/feed/`), Korea Herald (`rss/newsAll`) — nur breite Gesamt-Feeds ohne Tech-Sektion (Regel 6: Tageszeitungen); Eurostat (nur Datensatz-Update-Feed); APA-OTS Wirtschaft ist eingetragen, `fulltext` analog PR Newswire offen; Phoronix/SecurityWeek (Regel 5), Understanding AI (Regel 1).

## Tabelle: Triage der `feed_error`-Kandidaten

Status = `tdm_status` der Probe (`ok*` = KIT, manuell verifiziert), sonst Befund der Feed-Suche. Bemerkung nennt den Grund („Feed an nicht-standardisiertem Pfad“ / „Bot-Wall“ / „kein Feed“ / „Feed leer“ / „robots sperrt Feed-Pfad“).

| Name | Vertikale | gefundene Feed-URL | Status | Lizenz | Entscheidung | Bemerkung |
|---|---|---|---|---|---|---|
| AlphaGalileo | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| APA-OTS | BIZ | https://www.ots.at/rss/wirtschaft | ok |  | aufgenommen als „APA-OTS Wirtschaft“ (cross_industry press_wires, press_wire, market) | Feed an nicht-standardisiertem Pfad |
| aws Austria Wirtschaftsservice | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Bain | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BDI | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BFS Bundesamt für Statistik | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BusinessWire | BIZ |  | blocked |  | gesperrt | robots.txt sperrt feed.businesswire.com, Feed-Pfade 403 |
| Census Bureau | BIZ | https://www.census.gov/economic-indicators/indicator.xml | ok | Public Domain (US federal) | aufgenommen als „Census Bureau Economic Indicators“ (BIZ science, research, now · fulltext) | Feed an nicht-standardisiertem Pfad |
| Chain Store Age | BIZ |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| DIHK | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| DIW Berlin | BIZ | https://www.diw.de/de/rss_press.xml | ok |  | aufgenommen als „DIW Berlin“ (BIZ science, research, future) | Feed an nicht-standardisiertem Pfad |
| EurekAlert | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Eurostat | BIZ | https://ec.europa.eu/eurostat/api/dissemination/catalogue/rss/en/statistics-update.rss | ok |  | nicht aufgenommen (Datensatz-Update-Feed, 1.522 Eintraege; News-Release-Feeds 404) | Feed an nicht-standardisiertem Pfad |
| EZB | BIZ | https://www.ecb.europa.eu/rss/press.html | ok |  | aufgenommen als „EZB Pressemitteilungen“ (BIZ science, research, market) | Feed an nicht-standardisiertem Pfad |
| FinTech Futures | BIZ |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Handelszeitung | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| ifo Institut | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| IfW Kiel | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| IMF | BIZ |  | blocked |  | gesperrt | Bot-Wall auf den RSS-Pfaden (403), Seiten 200 |
| Innosuisse | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Internet World | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| IW Köln | BIZ |  | blocked |  | gesperrt | RSS-Pfade 401 (Zugriffsschutz), rss.html 401 |
| KfW | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Mining Weekly | BIZ |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| NRF | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Packaging Digest | BIZ |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Packaging World | BIZ |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Schweizer Bund (admin.ch Medienmitteilungen) | BIZ |  | feed_error |  | kein Feed | kein Feed unter admin.ch-Pfaden (Zusatzkandidat fuer BAFU/BAG/Agroscope/BFS) |
| Startup-Verband | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| startupticker | BIZ | https://www.startupticker.ch/en/rss/news | ok |  | aufgenommen als „startupticker“ (BIZ sources, trade_media, market) | Feed an nicht-standardisiertem Pfad |
| Statistik Austria | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| strategy+business | BIZ | https://www.strategy-business.com/all_updates.xml | blocked |  | gesperrt | Bot-Wall (Artikel 403 fuer CatandaryTrendsBot; Feed offen) → WP4-Kontaktliste |
| The Paypers | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| World Bank | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| World Economic Forum | BIZ |  | blocked |  | gesperrt | Bot-Wall (403 auf allen Pfaden) |
| ZEW | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Architonic | DESIGN |  | blocked |  | gesperrt | Bot-Challenge (HTTP 202 auf allen Pfaden) |
| Baublatt | DESIGN |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Bundesstiftung Baukultur | DESIGN |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| competitionline | DESIGN |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Design World | DESIGN | https://www.designworldonline.com/feed/ | ok |  | aufgenommen als „Design World“ (DESIGN sources, trade_media, market) |  |
| DGNB | DESIGN |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Disegno | DESIGN |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| form | DESIGN |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Frame | DESIGN |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Gebäude-Energieberater | DESIGN |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Hochparterre | DESIGN |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Interior Design | DESIGN |  | feed_error |  | kein Feed | Feed leer (RSS ohne Eintraege) |
| MaterialDistrict | DESIGN |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Messe Frankfurt | DESIGN |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Metropolis | DESIGN |  | feed_error |  | kein Feed | Feed leer (RSS ohne Eintraege) |
| ndion German Design Council | DESIGN |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Nielsen Norman Group | DESIGN | https://www.nngroup.com/feed/rss/ | ok |  | aufgenommen als „Nielsen Norman Group“ (DESIGN science, research, future) |  |
| Red Dot | DESIGN |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Agora Energiewende | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BAFU | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BDEW | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BEE Erneuerbare Energie | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BMWE | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BWE Windenergie | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| CSIRO | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| dena | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Deutsche Umwelthilfe | ECO | https://www.duh.de/presse/pressemitteilungen/?type=9818 | ok |  | aufgenommen als „Deutsche Umwelthilfe“ (ECO sources, trade_media, now) | Feed an nicht-standardisiertem Pfad |
| edie | ECO | https://www.edie.net/feed/ | ok |  | aufgenommen als „edie“ (ECO sources, trade_media, market) |  |
| electrive | ECO | https://www.electrive.net/feed/ | blocked |  | gesperrt | Bot-Wall (Artikel 403 fuer CatandaryTrendsBot; Feed offen) → WP4-Kontaktliste |
| Ellen MacArthur Foundation | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Empa | ECO |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Energie & Management | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| EPA News Releases | ECO |  | blocked |  | gesperrt | robots.txt sperrt /newsreleases/search (einziger RSS-Pfad) |
| erneuerbareenergien.de | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| EUWID Recycling | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Forschungszentrum Jülich | ECO | https://www.fz-juelich.de/++api++/@@rss?portal_type=Meldung&path=/Plone/de/aktuelles&Subject=Pressemitteilungen | ok |  | aufgenommen als „Forschungszentrum Jülich“ (ECO science, research, future) | Feed an nicht-standardisiertem Pfad |
| Green Car Journal | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| H2 View | ECO |  | feed_error |  | kein Feed | Feed leer (RSS ohne Eintraege) |
| Hydrogen Insight | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| IEA | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| IISD | ECO |  | feed_error |  | kein Feed | Feed leer (RSS ohne Eintraege) |
| IRENA | ECO |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| JRC Joint Research Centre | ECO | https://joint-research-centre.ec.europa.eu/node/2/rss_en | ok | CC BY 4.0 | aufgenommen als „JRC Joint Research Centre“ (ECO science, research, future · fulltext) | Feed an nicht-standardisiertem Pfad |
| Kunststoffe | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| neue verpackung | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| NREL News | ECO |  | feed_error |  | kein Feed | nicht erreichbar (Connect-Fehler/Timeout) |
| Rat für Nachhaltige Entwicklung | ECO |  | feed_error |  | kein Feed | Feed leer (RSS ohne Eintraege) |
| Recycling International | ECO |  | blocked |  | gesperrt | Bot-Wall auf dem Feed-Pfad (403), Homepage 200 |
| Recyclingmagazin | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| reNews | ECO |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Resource | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| RIFS Potsdam | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Umweltbundesamt | ECO | https://www.umweltbundesamt.de/rss/presse | ok |  | aufgenommen als „Umweltbundesamt“ (ECO science, research, future) | Feed an nicht-standardisiertem Pfad |
| Umweltbundesamt Österreich | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| USGS | ECO |  | feed_error |  | kein Feed | Feed leer (RSS ohne Eintraege) |
| VKU | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Windpower Monthly | ECO | https://www.windpowermonthly.com/rss/news | blocked |  | gesperrt | Bot-Wall (Artikel 403 fuer CatandaryTrendsBot; Feed offen) → WP4-Kontaktliste |
| World Resources Institute | ECO | https://www.wri.org/insights/rss.xml | ok |  | aufgenommen als „World Resources Institute“ (ECO science, research, future) |  |
| WWF Deutschland | ECO |  | feed_error |  | kein Feed | Feed leer (RSS ohne Eintraege) |
| Öko-Institut | ECO |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Advanced Textiles Source | FASHION |  | feed_error |  | kein Feed | nicht erreichbar (Connect-Fehler, auch www.) |
| BeautyMatter | FASHION |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| CosmeticsDesign Europe | FASHION |  | feed_error |  | kein Feed | Arc-Feedpfad HTTP 410 (Feed entfernt) |
| DITF Textil- und Faserforschung | FASHION |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Fashion for Good | FASHION |  | feed_error |  | kein Feed | Feed leer (RSS ohne Eintraege) |
| FashionNetwork DE | FASHION |  | blocked |  | gesperrt | Bot-Wall auf dem Feed-Pfad (403), Homepage 200 |
| FashionUnited International | FASHION |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Fibre2Fashion | FASHION |  | blocked |  | gesperrt | Bot-Wall (405/403 auf Feed-Pfaden) |
| Gesamtverband textil+mode | FASHION |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Hohenstein | FASHION |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| ISPO.com | FASHION |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Jing Daily | FASHION |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Nonwovens Industry | FASHION |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Swiss Textiles | FASHION |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Textile Web | FASHION |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| The Fashion Law | FASHION |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| AGES | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Agroscope | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BigHospitality | FOOD | https://www.bighospitality.co.uk/arc/outboundfeeds/rss/ | ok |  | aufgenommen als „BigHospitality“ (FOOD sources, trade_media, market) |  |
| Brauwelt | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Deutsche Gesellschaft für Ernährung | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| DLG | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Farmers Weekly | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Food Logistics | FOOD |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| foodaktuell | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| foodwatch | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Fraunhofer IVV | FOOD | https://www.ivv.fraunhofer.de/de/rss/news.rss | ok |  | aufgenommen als „Fraunhofer IVV“ (FOOD science, research, future) | Feed an nicht-standardisiertem Pfad |
| IFT Food Technology | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Julius Kühn-Institut | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Lebensmittelverband Deutschland | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Max Rubner-Institut | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| New Food Magazine | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| ProFood World | FOOD |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| The Drinks Business | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| The Morning Advertiser | FOOD | https://www.morningadvertiser.co.uk/arc/outboundfeeds/rss/ | ok |  | aufgenommen als „The Morning Advertiser“ (FOOD sources, trade_media, now) |  |
| Thünen-Institut | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Ökolandbau.de | FOOD |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BAG Bundesamt für Gesundheit | HEALTH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BfArM | HEALTH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BioTechniques | HEALTH | https://www.biotechniques.com/feed/ | ok |  | aufgenommen als „BioTechniques“ (HEALTH science, research, future) |  |
| BPI | HEALTH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BVMed | HEALTH |  | feed_error |  | kein Feed | kein direkter Feed — /rss ist eine JS-Generatorseite |
| Digital Health | HEALTH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| DKFZ | HEALTH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| EMA | HEALTH | https://www.ema.europa.eu/en/news.xml | ok |  | aufgenommen als „EMA News“ (HEALTH science, research, market) | Feed an nicht-standardisiertem Pfad |
| European Pharmaceutical Review | HEALTH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Fitt Insider | HEALTH |  | feed_error |  | kein Feed | Feed leer (RSS ohne Eintraege) |
| Labiotech | HEALTH | https://www.labiotech.eu/feed/ | blocked |  | gesperrt | Bot-Wall (Artikel 403 fuer CatandaryTrendsBot; Feed offen) → WP4-Kontaktliste |
| LISAvienna | HEALTH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| MassDevice | HEALTH |  | blocked |  | gesperrt | Bot-Wall auf dem Feed-Pfad (403), Homepage 200 |
| Max Delbrück Center | HEALTH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| MD+DI | HEALTH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Medizin & Technik | HEALTH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| NICE | HEALTH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Pharmazeutische Zeitung | HEALTH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Psychiatric Times | HEALTH | https://www.psychiatrictimes.com/rss.xml | blocked |  | gesperrt | Bot-Wall (Artikel 403 fuer CatandaryTrendsBot; Feed offen) → WP4-Kontaktliste |
| Swiss Biotech | HEALTH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Swiss Medtech | HEALTH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| vfa | HEALTH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Blickpunkt:Film | LIFESTYLE |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| buchreport | LIFESTYLE |  | feed_error |  | kein Feed | nicht erreichbar (Connect-Fehler/Timeout) |
| DAAD | LIFESTYLE |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Goethe-Institut | LIFESTYLE |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| kress | LIFESTYLE |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Kulturmanagement Network | LIFESTYLE |  | blocked |  | gesperrt | Bot-Wall auf dem Feed-Pfad (403), Homepage 200 |
| Library Journal | LIFESTYLE |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Meedia | LIFESTYLE |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Music Week | LIFESTYLE |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| PhocusWire | LIFESTYLE |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Press Gazette | LIFESTYLE |  | blocked |  | gesperrt | Bot-Wall auf dem Feed-Pfad (403), Homepage 200 |
| Smithsonian Magazine | LIFESTYLE |  | blocked |  | gesperrt | robots.txt sperrt /rss/ fuer den Bot |
| SPONSORs | LIFESTYLE |  | feed_error |  | kein Feed | nicht erreichbar (Connect-Fehler/Timeout) |
| SportsPro | LIFESTYLE |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Tes | LIFESTYLE |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| The Bookseller | LIFESTYLE |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Travel Weekly | LIFESTYLE |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| ACM Queue | TECH |  | feed_error |  | kein Feed | Feed entfernt (queuecontent.xml HTTP 410), Homepage 403 |
| Automation (automationnet) | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| BMFTR | TECH |  | blocked |  | gesperrt | robots.txt sperrt /SiteGlobals/ (Feed-Pfad, wie Foerderinfo Bund) |
| Chemical & Engineering News | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Communications of the ACM | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Computer & Automation | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Computerwelt | TECH |  | feed_error |  | kein Feed | nicht erreichbar (Connect-Fehler/Timeout) |
| Computing | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| CORDIS | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Cosmos | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| DFKI | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Discover | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| DLR | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| EDN | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| Embedded | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| EPFL | TECH | https://actu.epfl.ch/feeds/rss/mediacom/en/ | ok |  | aufgenommen als „EPFL News“ (TECH science, research, future) | Feed an nicht-standardisiertem Pfad |
| EU Science (Horizon) | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| EuroScience | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Falling Walls | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Google Research Blog | TECH | https://research.google/blog/rss/ | ok |  | aufgenommen als „Google Research Blog“ (TECH sources, brand, future) |  |
| HPCwire | TECH | https://www.hpcwire.com/feed/ | ok |  | aufgenommen als „HPCwire“ (TECH sources, trade_media, market) |  |
| Hugging Face Blog | TECH | https://huggingface.co/blog/feed.xml | ok |  | aufgenommen als „Hugging Face Blog“ (TECH sources, brand, future) |  |
| International Railway Journal | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| KIT | TECH | https://kit.edu/pi.rss | ok* |  | aufgenommen als „KIT Karlsruher Institut für Technologie“ (TECH science, research, future) | Feed an nicht-standardisiertem Pfad (kit.edu/pi.rss); Probe: juengster Eintrag 404 (verwaister Link), 2. Eintrag manuell: robots allow, 200, kein TDM-Signal |
| Microsoft Research | TECH | https://www.microsoft.com/en-us/research/feed/ | ok |  | aufgenommen als „Microsoft Research“ (TECH sources, brand, future) |  |
| OpenAI | TECH | https://openai.com/news/rss.xml | blocked |  | gesperrt | Bot-Wall (Artikel 403 fuer CatandaryTrendsBot; Feed offen) → WP4-Kontaktliste |
| Phoronix | TECH | https://www.phoronix.com/rss.php | ok |  | nicht aufgenommen (Regel 5: Entwickler-/Enthusiasten-IT) |  |
| RFID im Blick | TECH |  | feed_error |  | kein Feed | nicht erreichbar (Connect-Fehler/Timeout) |
| SecurityWeek | TECH | https://www.securityweek.com/feed/ | ok |  | nicht aufgenommen (Regel 5: US-Enterprise-IT/Security) |  |
| Spektrum der Wissenschaft | TECH | https://www.spektrum.de/alias/rss/spektrum-de-rss-feed/996406 | blocked |  | gesperrt | Bot-Wall (Artikel 403 fuer CatandaryTrendsBot; Feed offen) → WP4-Kontaktliste |
| The Robot Report | TECH | https://www.therobotreport.com/feed/ | ok |  | aufgenommen als „The Robot Report“ (TECH sources, trade_media, market) |  |
| The Scientist | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| TU Dresden | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| TU Wien | TECH |  | feed_error |  | kein Feed | kein Feed; TYPO3 ?type=9818 Timeout |
| Understanding AI | TECH | https://www.understandingai.org/feed | ok |  | nicht aufgenommen (Regel 1: Einzelautor-Newsletter) |  |
| USPTO News | TECH | https://www.uspto.gov/rss.xml | ok | Public Domain (US federal) | aufgenommen als „USPTO News“ (TECH science, research, market · fulltext) |  |
| VDE | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| VDI | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| VDMA | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| Weizenbaum-Institut | TECH | https://www.weizenbaum-institut.de/rss/ | feed_error |  | nicht verwendbar | Feed gefunden, Eintraege ohne Link (Poller unbrauchbar) |
| ZHAW | TECH | https://www.zhaw.ch/de/medien/?type=9818 | feed_error |  | nicht verwendbar | TYPO3-Feed gefunden, Eintraege ohne Link (Poller unbrauchbar) |

## Tabelle: Internationale Tech-Quellen (benannte Liste)

| Gruppe | Name | Vertikale | gefundene Feed-URL | Status | Lizenz | Entscheidung | Bemerkung |
|---|---|---|---|---|---|---|---|
| a | TechNode | TECH | https://technode.com/feed/ | ok |  | aufgenommen als „TechNode“ (TECH sources, trade_media, market) |  |
| a | KrASIA | TECH | https://console.kr-asia.com/feed | ok |  | bereits aktiv (console.kr-asia.com/feed) |  |
| a | Tech in Asia | TECH | https://feeds.feedburner.com/PennOlson | blocked |  | blocked — Feed nur via Feedburner, Artikel 403 → WP4 | Bot-Wall (Artikel 403 fuer CatandaryTrendsBot; Feed offen) → WP4-Kontaktliste |
| a | e27 | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| a | Korea Herald Tech | TECH | https://www.koreaherald.com/rss/newsAll | ok |  | Owner-Entscheid (nur Gesamt-Feed `newsAll`, Sektionsfeeds leer) | Feed an nicht-standardisiertem Pfad |
| a | Japan Times Tech | TECH | https://www.japantimes.co.jp/feed/ | ok |  | Owner-Entscheid (nur Gesamt-Feed, Tech-Feed 404/leer) |  |
| a | Nikkei Asia | TECH | https://asia.nikkei.com/rss/feed/nar | ok |  | Owner-Entscheid (breiter Zeitungs-Feed `nar`, kein Tech-Sektionsfeed) | Feed an nicht-standardisiertem Pfad |
| a | DigiTimes | TECH | https://www.digitimes.com/rss/daily.xml | ok |  | aufgenommen als „DigiTimes“ (TECH sources, trade_media, market) | Feed an nicht-standardisiertem Pfad |
| b | Silicon Republic | TECH | https://www.siliconrepublic.com/feed | ok |  | aufgenommen als „Silicon Republic“ (TECH sources, trade_media, market) |  |
| b | Silicon Canals | TECH | https://siliconcanals.com/feed/ | ok |  | aufgenommen als „Silicon Canals“ (TECH sources, trade_media, market) |  |
| b | Maddyness | BIZ | https://www.maddyness.com/feed/ | ok |  | aufgenommen als „Maddyness“ (BIZ sources, trade_media, market) |  |
| b | L'Usine Digitale | TECH | https://www.usine-digitale.fr/rss | blocked |  | gesperrt | Bot-Wall (Artikel 403 fuer CatandaryTrendsBot; Feed offen) → WP4-Kontaktliste |
| b | Le Monde Informatique | TECH | https://www.lemondeinformatique.fr/rss/rss.xml | ok |  | aufgenommen als „Le Monde Informatique“ (TECH sources, trade_media, market) |  |
| b | The Next Web | TECH | https://thenextweb.com/feed | ok |  | aufgenommen als „The Next Web“ (TECH sources, trade_media, market) |  |
| b | Sifted Alt: Tech.eu | TECH |  | blocked |  | bereits aktiv | robots.txt sperrt den Feed-Pfad (wie Foerderinfo Bund) |
| b | Sifted Alt: EU-Startups | TECH |  | feed_error |  | bereits aktiv | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| b | Sifted Alt: Startup Valley | TECH |  | feed_error |  | kein Feed | Feed leer (RSS ohne Eintraege) |
| b | Sifted Alt: Tech Funding News | TECH | https://techfundingnews.com/feed/ | ok |  | aufgenommen als „Tech Funding News“ (BIZ sources, trade_media, now) |  |
| b | Sifted Alt: UKTN | TECH | https://www.uktech.news/feed | ok |  | aufgenommen als „UKTN“ (TECH sources, trade_media, market) |  |
| b | Sifted Alt: Nordic 9 | TECH |  | feed_error |  | kein Feed | kein Feed |
| b | Nordic 9 | TECH |  | feed_error |  | kein Feed | kein Feed |
| b | Sifted Alt: ArcticStartup | TECH | https://arcticstartup.com/feed/ | ok |  | aufgenommen als „ArcticStartup“ (TECH sources, trade_media, market) |  |
| c | Gartner Newsroom | BIZ |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| c | IDC | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| c | Forrester Blogs | BIZ | https://www.forrester.com/blogs/feed/ | ok |  | aufgenommen als „Forrester Blogs“ (BIZ sources, trade_media, future) |  |
| c | Deloitte Insights | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| c | BCG | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| c | Accenture Newsroom | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| c | McKinsey | BIZ |  | feed_error |  | bereits aktiv | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| c | PitchBook News | BIZ |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| c | Crunchbase News | BIZ |  | feed_error |  | bereits aktiv | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| c | Dealroom | BIZ |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| d | ITU | TECH | https://www.itu.int/hub/feed/ | ok | CC BY-SA 3.0 IGO | aufgenommen als „ITU News“ (TECH science, research, future · fulltext) |  |
| d | ETSI | TECH | https://www.etsi.org/rss | ok |  | aufgenommen als „ETSI Newsroom“ (TECH science, research, future) |  |
| d | ISO | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| d | IEC | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| d | W3C | TECH | https://www.w3.org/news/feed/ | ok |  | aufgenommen als „W3C News“ (TECH science, research, future) |  |
| d | IETF Blog | TECH | https://www.ietf.org/blog/feed/ | ok |  | aufgenommen als „IETF Blog“ (TECH science, research, future) |  |
| d | OECD.AI | TECH | https://wp.oecd.ai/feed/ | ok |  | aufgenommen als „OECD.AI“ (TECH science, research, future) |  |
| d | UNESCO | LIFESTYLE |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| d | ENISA | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| d | BSI | TECH |  | blocked |  | gesperrt | robots.txt sperrt /SiteGlobals/ (Feed-Pfad, wie Foerderinfo Bund); RSS-Seite 404 |
| e | Sony Newsroom | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| e | Siemens Press | TECH | https://press.siemens.com/global/en/rss.xml | ok |  | aufgenommen als „Siemens Press“ (TECH sources, brand, market) |  |
| e | Bosch Media | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| e | ABB News | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| e | Schneider Electric Newsroom | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| e | Ericsson News | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| e | Nokia Newsroom | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| e | TSMC | TECH |  | blocked |  | gesperrt | Bot-Wall (Homepage/Feed-Pfade 403/401/429 fuer den Bot-UA) |
| e | Arm Newsroom | TECH | https://newsroom.arm.com/rss | ok |  | aufgenommen als „Arm Newsroom“ (TECH sources, brand, market) |  |
| e | AMD News | TECH | https://ir.amd.com/rss/news-releases.xml | ok |  | aufgenommen als „AMD News“ (TECH sources, brand, market) | Feed an nicht-standardisiertem Pfad |
| e | Qualcomm News | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| e | Microsoft News | TECH | https://news.microsoft.com/feed/ | ok |  | verwaist (letzter Eintrag 2025-05-07) — ersetzt durch Microsoft Source |  |
| e | Microsoft Source | TECH | https://news.microsoft.com/source/feed/ | ok |  | aufgenommen als „Microsoft Source“ (TECH sources, brand, market) |  |
| e | Meta Newsroom | TECH | https://about.fb.com/news/feed/ | ok |  | aufgenommen als „Meta Newsroom“ (TECH sources, brand, market) |  |
| e | Amazon Science | TECH | https://www.amazon.science/index.rss | ok |  | aufgenommen als „Amazon Science“ (TECH sources, brand, future) | Feed an nicht-standardisiertem Pfad |
| f | Meta AI Blog | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| f | Anthropic News | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| f | Mistral AI | TECH | https://mistral.ai/rss.xml | ok |  | aufgenommen als „Mistral AI“ (TECH sources, brand, future) |  |
| f | Stanford HAI | TECH |  | feed_error |  | kein Feed | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| f | Berkeley BAIR | TECH |  | feed_error |  | kein Feed | nicht erreichbar (Connect-Fehler/Timeout) |
| f | MIT CSAIL | TECH |  | feed_error |  | verwaist (rss.xml letzter Eintrag 2019) | kein Feed (Pfade/Seiten ohne RSS-Verweis) |
| f | New Atlas | TECH | https://newatlas.com/index.rss | ok |  | aufgenommen als „New Atlas“ (TECH sources, trade_media, market) | Feed an nicht-standardisiertem Pfad |
| f | Interesting Engineering | TECH | https://interestingengineering.com/feed | ok |  | aufgenommen als „Interesting Engineering“ (TECH sources, trade_media, market) |  |
| f | Singularity Hub | TECH | https://singularityhub.com/feed/ | ok |  | aufgenommen als „Singularity Hub“ (TECH sources, trade_media, future) |  |
| f | Nautilus | TECH | https://nautil.us/feed/ | ok |  | aufgenommen als „Nautilus“ (TECH science, research, future) |  |
| f | Chemistry World | TECH | https://www.chemistryworld.com/409.rss | ok |  | aufgenommen als „Chemistry World News“ (TECH science, research, future) | Feed an nicht-standardisiertem Pfad |
| f | IEEE Spectrum Semiconductors | TECH | https://spectrum.ieee.org/feeds/topic/semiconductors.rss | ok |  | aufgenommen (Topic-Feed, TECH science) | Feed an nicht-standardisiertem Pfad |
| f | IEEE Spectrum Energy | TECH | https://spectrum.ieee.org/feeds/topic/energy.rss | ok |  | aufgenommen (Topic-Feed, ECO science) | Feed an nicht-standardisiertem Pfad |

## Nicht priorisiert (Rest der 294 `feed_error`-Kandidaten, keine erneute Anfrage)

Gründe: idw-Redundanz (Regel 2), Consumer-/Einzelblogs (Regel 1), Landesförderbanken, Paywall-/Marketing-Titel, sowie die im WP3-Lauf schon mit Homepage-403 belegten Bot-Walls.

| Name | Vertikale | Land | Grund |
|---|---|---|---|
| brand eins | BIZ | DE | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Börse Online | BIZ | DE | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Campaign | BIZ | UK | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| Citywire | BIZ | UK | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| Format trend | BIZ | AT | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| IB.SH | BIZ | DE | Landesfoerderbank (geringer Trend-Scouting-Wert) |
| IBB Berlin | BIZ | DE | Landesfoerderbank (geringer Trend-Scouting-Wert) |
| Investment Week | BIZ | UK | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| L-Bank | BIZ | DE | Landesfoerderbank (geringer Trend-Scouting-Wert) |
| LfA Förderbank Bayern | BIZ | DE | Landesfoerderbank (geringer Trend-Scouting-Wert) |
| Marketing Week | BIZ | UK | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| NRW.BANK | BIZ | DE | Landesfoerderbank (geringer Trend-Scouting-Wert) |
| Universität Hohenheim | BIZ | DE | Hochschul-/Klinik-Pressestelle (laeuft ueber idw, Regel 2) |
| WIBank | BIZ | DE | Landesfoerderbank (geringer Trend-Scouting-Wert) |
| Archello | DESIGN | NL | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| Architect Magazine | DESIGN | US | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| Australian Design Review | DESIGN | AU | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| AW Architektur + Wettbewerbe | DESIGN | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| Bauhaus Dessau | DESIGN | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| BDA Bund Deutscher Architekten | DESIGN | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| DETAIL | DESIGN | DE | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| Domus | DESIGN | IT | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| DPA Design Products & Applications | DESIGN | UK | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| German-Architects | DESIGN | DE | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| iF Design | DESIGN | DE | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| Print & Produktion | DESIGN | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| Publishing Praxis | DESIGN | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| Schweizer Holzzeitung | DESIGN | CH | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| Swiss-Architects | DESIGN | CH | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| Vitra Magazine | DESIGN | CH | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| Zuschnitt proHolz | DESIGN | AT | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| BMWK | ECO | DE | nicht priorisiert (Verband/Medium ohne erkennbaren Feed-Hinweis, geringer Scouting-Wert) |
| ENDS Report | ECO | UK | nicht priorisiert (Verband/Medium ohne erkennbaren Feed-Hinweis, geringer Scouting-Wert) |
| HNEE Eberswalde | ECO | DE | Hochschul-/Klinik-Pressestelle (laeuft ueber idw, Regel 2) |
| Orion Magazine | ECO | US | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Resurgence & Ecologist | ECO | UK | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Sierra Club | ECO | US | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| TMG Think Tank | ECO | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| Zeitschrift für Umweltrecht | ECO | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| 032c | FASHION | DE | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Beauty Packaging | FASHION | US | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| beauty-forum | FASHION | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| Cosmetic Business | FASHION | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| Fantastic Man | FASHION | NL | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Fashion Magazine | FASHION | CA | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| FashionUnited | FASHION | DE | nicht priorisiert (Verband/Medium ohne erkennbaren Feed-Hinweis, geringer Scouting-Wert) |
| Global Cosmetic Industry | FASHION | US | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| Happi | FASHION | US | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| IKW Körperpflege | FASHION | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| IndiaRetailing | FASHION | IN | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| L'Officiel | FASHION | FR | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Madame | FASHION | DE | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Professional Jeweller | FASHION | UK | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| Sportswear International | FASHION | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| The Face | FASHION | UK | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| WatchPro | FASHION | UK | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| Anuga Koelnmesse | FOOD | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| BDSI Süßwarenindustrie | FOOD | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| Beverage Digest | FOOD | US | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| Der Feinschmecker | FOOD | DE | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Food Business News | FOOD | US | Homepage 403 fuer den Bot-UA laut WP3-Lauf (Bot-Wall, nicht erneut angefragt) |
| gastroinfoportal | FOOD | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| Konsument VKI | FOOD | AT | Verbrauchertest / Owner-Entscheid analog Oeko-Test |
| Vinum | FOOD | CH | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Wein+Markt | FOOD | DE | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Journal für die Apotheke | HEALTH | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| MedUni Wien | HEALTH | AT | Hochschul-/Klinik-Pressestelle (laeuft ueber idw, Regel 2) |
| MHH Hannover | HEALTH | DE | Hochschul-/Klinik-Pressestelle (laeuft ueber idw, Regel 2) |
| Pharmakon | HEALTH | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| U.S. Pharmacist | HEALTH | US | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| UMG Göttingen | HEALTH | DE | Hochschul-/Klinik-Pressestelle (laeuft ueber idw, Regel 2) |
| Universitätsklinikum Bonn | HEALTH | DE | Hochschul-/Klinik-Pressestelle (laeuft ueber idw, Regel 2) |
| Universitätsklinikum Heidelberg | HEALTH | DE | Hochschul-/Klinik-Pressestelle (laeuft ueber idw, Regel 2) |
| Universitätsklinikum Würzburg | HEALTH | DE | Hochschul-/Klinik-Pressestelle (laeuft ueber idw, Regel 2) |
| Creative COW | LIFESTYLE | US | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Kindergarten heute | LIFESTYLE | DE | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Medium Magazin | LIFESTYLE | DE | Finanz-/Marketing-Fachpresse mit Paywall oder geringem Foresight-Bezug |
| Nexus Mods | LIFESTYLE | UK | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| The Red Bulletin | LIFESTYLE | AT | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |
| Working@office | LIFESTYLE | DE | Consumer-/Lifestyle-Magazin oder Einzelblog (Regel 1) |

## Lizenzbelege der neuen `fulltext: true`-Quellen

| Quelle | Lizenz | Beleg (2026-09-04) |
|---|---|---|
| JRC Joint Research Centre | CC BY 4.0 | Site-Footer verlinkt commission.europa.eu/legal-notice_en (EU-Kommissions-Inhalte CC BY 4.0, wie EU Presscorner) |
| USPTO News | Public Domain (US federal) | US-Bundeswerk, 17 U.S.C. §105 |
| Census Bureau Economic Indicators | Public Domain (US federal) | US-Bundeswerk, 17 U.S.C. §105 |
| ITU News | CC BY-SA 3.0 IGO | Probe: strukturierter Link creativecommons.org/licenses/by-sa/3.0/igo/ auf der Artikelseite |

Nicht als offen gewertet: WRI (kein Lizenzhinweis auf Artikelseite, Terms-Seiten 404), EPFL (CC-Vermerk nur als Bildnachweis), Singularity Hub (CC nur bei übernommenen The-Conversation-Texten), EZB/EMA/UBA/KIT/Jülich/DIW (Wiedergabe mit Quellenangabe, keine benannte Lizenz), OECD.AI, W3C/IETF/ETSI (eigene Dokumentlizenzen).

## Nebenfunde

- `sources.yaml` enthält den Namen „Nation's Restaurant News“ doppelt (bestand schon vor WP2b).
- Feed-Autodiscovery des Werkzeugs findet TYPO3-Feeds (`?type=9818`) und Plone-`@@rss`-Feeds nicht — Erweiterungsidee für `discover_feed`.
- EMA rate-limitet den Bot (429) schon bei wenigen Requests; der Poller (1×/Tag) ist unkritisch, die Monatsprüfung sollte `--delay` ≥ 3 s nutzen.
- Weizenbaum-Institut und ZHAW liefern gültige Feeds, deren Einträge keinen `<link>` tragen — für den Poller unbrauchbar (`feed_error`).
