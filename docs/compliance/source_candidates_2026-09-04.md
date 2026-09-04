# Kandidatenrecherche Quellenausbau (2026-09-04, #97 WP2/WP3)

Stand: 2026-09-04. Alle Kandidaten wurden mit `scripts/probe_source_compliance.py` geprüft (Feed, robots.txt für `CatandaryTrendsBot`, Bot-Status der Artikelseite, TDM-Signale, Lizenz). Aufgenommen wurden nur `tdm_status: ok`-Kandidaten, die zusätzlich die redaktionellen Regeln unten erfüllen. Rohdaten der Läufe liegen nicht im Repo (Scratchpad); das Ergebnis je Kandidat steht in der Tabelle.

## Zahlen

- Kandidaten gesamt: **708** — Status: ok 352, feed_error 294, blocked 50, reserved 12. DE/AT/CH-Kandidaten: 338.
- Aufgenommen in `sources.yaml`: **217** (davon DE/AT/CH 108, mit offener Lizenz und `fulltext: true` **16**). Zwei weitere ok-Kandidaten fielen im Nachlauf mit `verify_feeds.verify_feed` durch und wurden wieder entfernt (FFG: Redirect-Schleife der Feed-URL; absatzwirtschaft: `/feed/` leitet auf marken-award.de um).
- Je Vertikale (Kandidaten gesamt / ok / aufgenommen / davon fulltext / davon DE-AT-CH):
  - FOOD: 80 / 42 / 30 / 0 / 14
  - DESIGN: 63 / 27 / 24 / 0 / 10
  - FASHION: 79 / 44 / 14 / 0 / 3
  - ECO: 97 / 41 / 32 / 1 / 22
  - TECH: 127 / 74 / 37 / 3 / 18
  - HEALTH: 72 / 30 / 23 / 4 / 8
  - BIZ: 104 / 41 / 26 / 6 / 14
  - LIFESTYLE: 86 / 53 / 31 / 2 / 19
- Ziele: ≥ 80 Kandidaten und ≥ 12 je Schwerpunkt-Vertikale — erreicht. ≥ 40 neue ok-Quellen — erreicht. ≥ 15 offene Lizenzen mit fulltext — 16, erreicht, aber nur über US-Bundesbehörden (Public Domain), EU-/UK-Institutionen und Open-Access-Medien; **keine deutschsprachige Quelle außer dem Hochschulforum Digitalisierung (CC BY-SA 4.0) trägt eine strukturiert erkennbare offene Lizenz**. FOOD/DESIGN/FASHION je ≥ 5 — erreicht.
- Herkunft der aufgenommenen Quellen: eigenes Wissen 188, Wikipedia-Liste 11, Feedspot-Liste (manuell) 13, idw-RSS 4, Hacker-News-API 1.

## Warum so viele Kandidaten scheitern

- **feed_error (294)** ist fast immer „kein Feed gefunden“: viele deutsche Verbände, Ministerien und Institute bieten keinen RSS-Feed mehr an oder nur hinter JavaScript/Newsletter (u. a. BfR, Max Rubner-Institut, DLG, Lebensmittelverband, foodwatch, Agroscope, AGES, Umweltbundesamt, dena, Agora Energiewende, Öko-Institut (404), KfW und alle Landesförderbanken, ifo/DIW/IW/ZEW/IfW, VDMA, VDE, VDI, DAAD, Meedia, kress, Handelszeitung, startupticker, Internet World, EZB, OECD, WEF, IMF, Eurostat, Statistik Austria, BFS). Die Autodiscovery wurde dafür in drei Schritten erweitert (Commits 8d29279, 191a5b2, 6c10795: Footer-Links, unquoted href, `<base href>`, RSS-Übersichtsseiten eine Ebene tief, HTML-Kandidaten-URLs); danach fanden sich u. a. BLE, BauNetz, Bauwelt, Helmholtz, ETH, MPG, Destatis, EU-Presscorner, FDA, CDC, ECDC.
- **Homepage 403 für den Bot-UA** (Cloudflare/Akamai-Bot-Management) — de facto blocked, im Werkzeug aber `feed_error`, weil ohne Homepage keine Autodiscovery möglich ist: Thünen-Institut, Food Business News, DETAIL, German-/Swiss-Architects, iF Design, Vitra, Domus, Architect Magazine, Archello, Australian Design Review, USDA, GCI, Professional Jeweller, WatchPro, Beauty Packaging, Happi, Empa, IRENA, edie, Windpower Monthly, reNews, H2 View, electrive, DFKI, NIH, UNESCO, NOAA, OECD, ILO, WRI, EIT.
- **blocked (50)**: robots-Verbot der Feed-URL (BMLEH/bund.de-SiteGlobals wie Förderinfo, EEA, RKI, Computerwoche, The Next Platform, Die Presse, Finance Forward, Practical Ecommerce, W&V, Übermedien, Numéro, Nutrition Insight, Food Ingredients First) oder Artikel-403 (Vogue Business, Design Week, Dark Reading, Capital, Quartz, Inc., Hospitality Net, Artnet, Esports Insider, SupplySide, EIT Food 429, UNEP, Gartner).
- **reserved (12)**: TDM-Vorbehalt per Meta-Tag/tdmrep — dfv-Titel (Fleischwirtschaft, food-service, fvw), FAZ, GEN u. a.

## Redaktionelle Regeln (ok-Kandidaten, die trotzdem nicht aufgenommen wurden)

1. Keine Privat-/Consumer-Blogs und Consumer-Magazine ohne Trendwert (Feedspot-Blogs, Consumer-Mode/-Koch/-Spiele/-Wissenschaftsmagazine); FASHION verliert dadurch die meisten Wikipedia-Treffer (Dazed, i-D, Nylon, Paper …) — bewusst, die Vertikale soll Fachmedien bekommen.
2. Hochschul- und Klinik-Pressestellen laufen bereits über idw (aktive Quelle) — nicht doppelt aufnehmen; Institute mit eigenem Profil (Helmholtz, MPG, Fraunhofer-Institute, PIK, PSI, ETH, TUM, ISTA, HZDR, Weizenbaum) schon.
3. Feeds, deren jüngster Eintrag vor 2026-06-01 liegt, gelten als verwaist (JCK 2018, Dexigner 2022, US DOE 2020, Klima- und Energiefonds 2024, Fashion Revolution 02/2026).
4. Feed auf fremder Domain (Autodiscovery-Fehltreffer) oder Stellen-/Veranstaltungsfeed → nicht aufgenommen (Hereon→techfacts.de, Charité-Veranstaltungen, EIB-Jobs).
5. TECH-Balance (CLAUDE.md: TECH-Dominanz beobachten): US-Enterprise-IT- und Entwicklermedien nicht aufgenommen (InformationWeek, eWeek, Datamation, InfoWorld, Computer Weekly, SiliconANGLE, The New Stack, InfoQ, SD Times …).
6. **Owner-Entscheid** (ok geprüft, nicht aufgenommen): presseportal.de (Presseverteiler-Index laut ToS-Regel — als Quelle analog PR Newswire denkbar), Tageszeitungen mit breitem Feed (Süddeutsche Topthemen, NZZ recent, Der Standard), Verbrauchertests (Öko-Test, Stiftung Warentest).
7. `relevance_min: 0.6/0.7` für breite Feeds (Regierungs-/Zentralbank-/Statistik-Feeds, eLife, Global Voices, MPG/Helmholtz/ETH/CERN) und Now-Tier-Titel mit geringem Foresight-Wert.

## Offene Lizenzen (fulltext: true) — Belege

| Quelle | Lizenz | Beleg (2026-09-04) |
|---|---|---|
| Clean Energy Wire | CC BY 4.0 | Probe: `link rel=license` CC BY 4.0 |
| ECDC | CC BY 4.0 | ecdc.europa.eu/en/ecdc-intellectual-property-notices: most publicly available materials CC BY 4.0 |
| CDC | Public Domain (US federal) | cdc.gov/other/agencymaterials.html: public domain |
| FDA | Public Domain (US federal) | fda.gov Website Policies: not copyrighted, public domain |
| EU Commission Press Corner | CC BY 4.0 | commission.europa.eu/legal-notice_en: EU-eigene Inhalte CC BY 4.0 |
| Hochschulforum Digitalisierung | CC BY-SA 4.0 | Probe: strukturierter CC-BY-SA-4.0-Link auf der Artikelseite |
| GOV.UK News and communications | OGL v3.0 | gov.uk/help/terms-conditions: Open Government Licence v3.0 |
| NIST News | Public Domain (US federal) | nist.gov/oism/copyrights: public information |
| FTC Press Releases | Public Domain (US federal) | US-Bundeswerk, 17 U.S.C. §105 (keine Site-Ausnahme gefunden) |
| SEC Press Releases | Public Domain (US federal) | US-Bundeswerk, 17 U.S.C. §105 |
| Federal Reserve Press Releases | Public Domain (US federal) | US-Bundeswerk, 17 U.S.C. §105 |
| BLS Latest | Public Domain (US federal) | US-Bundeswerk, 17 U.S.C. §105 |
| eLife | CC BY 4.0 | elifesciences.org/terms: CC BY 4.0 |
| SciDev.Net | CC BY 4.0 | Probe: strukturierter CC-BY-4.0-Link (Republishing-Seite nennt CC BY 2.0) |
| Global Voices | CC BY 3.0 | Attribution Policy: CC BY 3.0 |
| DARPA | Public Domain (US federal) | US-Bundeswerk, 17 U.S.C. §105 |

Nicht als offen gewertet (kein fulltext): Destatis („Vervielfältigung … mit Quellennachweis gestattet“, keine benannte Lizenz), Energy Transition (Böll: „CC wo möglich“, keine Version), CERN (eigene Nutzungsbedingungen), CGIAR (kein Lizenzhinweis auf der Site), MPG/Helmholtz/ETH/Fraunhofer (kein Hinweis), BLE (CC BY-NC-ND 4.0), Mongabay/Knowable (NC/ND). EEA wäre CC BY, ihr Feed ist aber per robots.txt gesperrt; Inside Climate News ist CC-lizenziert, sperrt aber den Bot (WP4-Kontakt).

## Entdeckungs-Indizes (Protokoll laut ToS-Klärung 03.09.)

| Index | Datum | Bedingung geprüft | Ergebnis |
|---|---|---|---|
| Hacker-News-Firebase-API (top+best, 294 Stories) | 2026-09-04 | öffentliche API, `discover_from_aggregators.py` | 277 Hosts, fast nur Blogs; 6 Kandidaten geprüft |
| Wikipedia-Listen (en: trade/science/food/fashion/computer/environmental magazines; de: Liste deutschsprachiger Zeitschriften) via MediaWiki-API → Wikidata P856 | 2026-09-04 | CC BY-SA, API | 1.243 Treffer → 1.077 Hosts; 148 Kandidaten geprüft |
| idw-RSS → Institutions-Links (60 Meldungen) | 2026-09-04 | Owner-Allowlist; robots.txt sperrt die RSS-URL (im Werkzeug vermerkt) | 59 Institutionen; 20 geprüft (Rest Hochschulen = idw-redundant) |
| Feedspot-Listen (bloggers/rss/magazine.feedspot.com: german_food_blogs, german_fashion_blogs, germany_sustainability_rss_feeds, fashion_industry_rss_feeds, textile_rss_feeds, industrial_design_magazines, food_technology_magazines, sustainable_food_magazines) | 2026-09-04 | robots.txt `*` erlaubt diese Pfade; je Seite ein manueller Lesevorgang, nur Domains notiert, nichts gespeichert | 46 Kandidaten geprüft |
| Techmeme Leaderboard (`/lb`, `/lb/ai`) | 2026-09-04 | robots.txt `*` erlaubt `/lb`; manuell | Übersichtsseite ohne Ranking-Domains, `/lb/ai` 404 — keine Kandidaten |
| Reddit | — | nur mit registrierter App (sources@catandary.de) — nicht ausgeführt | — |

## Tabelle aller Kandidaten

Status = `tdm_status` des letzten Probe-Laufs; „Feed“ = gefundene Feed-URL (leer = keine gefunden). Herkunft: own = eigenes Wissen. Entscheidung „aufgenommen“ = Eintrag in `sources.yaml` (Block je Vertikale; `type: research` im `science:`-Block, Presseverteiler unter `cross_industry`).


### FOOD (80 Kandidaten, 30 aufgenommen)

| Name | Domain | Feed | Vertikale | Herkunft | Land | Status | Lizenz | Entscheidung |
|---|---|---|---|---|---|---|---|---|
| about-drinks | about-drinks.com | https://www.about-drinks.com/feed/ | FOOD | own | DE | ok |  | aufgenommen |
| agrarheute | agrarheute.com | https://agrarheute.com/rss | FOOD | own | DE | ok |  | aufgenommen |
| Anthropocene Magazine | anthropocenemagazine.org | https://www.anthropocenemagazine.org/feed/ | FOOD | feedspot | US | ok |  | aufgenommen |
| Bakery and Snacks | bakeryandsnacks.com | https://www.bakeryandsnacks.com/arc/outboundfeeds/rss/ | FOOD | own | UK | ok |  | aufgenommen |
| Beverage Industry | bevindustry.com | https://www.bevindustry.com/rss/16 | FOOD | own | US | ok |  | aufgenommen |
| BLE Bundesanstalt für Landwirtschaft und Ernährung | ble.de | https://www.ble.de/SiteGlobals/Functions/RSS/DE/MarktbeobachtungEier.xml?nn=633724 | FOOD | own | DE | ok | CC BY-NC-ND 4.0 | aufgenommen |
| BVE Ernährungsindustrie | bve-online.de | https://www.ernaehrungsindustrie.de/feed/ | FOOD | own | DE | ok |  | aufgenommen |
| CGIAR | cgiar.org | https://cgiar.org/rss.xml | FOOD | own | INT | ok |  | aufgenommen |
| Confectionery News | confectionerynews.com | https://www.confectionerynews.com/arc/outboundfeeds/rss/ | FOOD | own | UK | ok |  | aufgenommen |
| Deutscher Brauer-Bund | brauer-bund.de | https://brauer-bund.de/feed/ | FOOD | own | DE | ok |  | aufgenommen |
| DIL Deutsches Institut für Lebensmitteltechnik | dil-ev.de | https://dil-ev.de/feed/ | FOOD | own | DE | ok |  | aufgenommen |
| Ernährungs Umschau | ernaehrungs-umschau.de | https://ernaehrungs-umschau.de/feed/ | FOOD | own | DE | ok |  | aufgenommen |
| Food Engineering | foodengineeringmag.com | https://www.foodengineeringmag.com/rss/16 | FOOD | own | US | ok |  | aufgenommen |
| Food Engineering & Ingredients | fei-online.com | https://fei-online.com/feed/ | FOOD | feedspot | NL | ok |  | aufgenommen |
| Food Processing | foodprocessing.com | https://www.foodprocessing.com/__rss/website-scheduled-content.xml?input=%7B%22sectionAlias%22%3A%22home%22%7D | FOOD | own | US | ok |  | aufgenommen |
| Food Safety Tech | foodsafetytech.com | https://www.foodsafetytech.com/feed/ | FOOD | feedspot | US | ok |  | aufgenommen |
| Food Tank | foodtank.com | https://foodtank.com/feed/ | FOOD | own | US | ok |  | aufgenommen |
| FoodBev Media | foodbev.com | https://www.foodbev.com/blog-feed.xml | FOOD | own | UK | ok |  | aufgenommen |
| Future Farming | futurefarming.com | https://futurefarming.com/feed | FOOD | own | NL | ok |  | aufgenommen |
| Innovations in Food Technology | innovationsfood.com | https://innovationsfood.com/feed/ | FOOD | feedspot | UK | ok |  | aufgenommen |
| Just Drinks | just-drinks.com | https://www.just-drinks.com/feed/ | FOOD | own | UK | ok |  | aufgenommen |
| Lebensmittel Praxis | lebensmittelpraxis.de | https://lebensmittelpraxis.de/?format=feed&amp;type=rss | FOOD | own | DE | ok |  | aufgenommen |
| Milchindustrie-Verband | milchindustrie.de | https://milchindustrie.de/feed | FOOD | own | DE | ok |  | aufgenommen |
| Prepared Foods | preparedfoods.com | https://www.preparedfoods.com/rss/17 | FOOD | own | US | ok |  | aufgenommen |
| ProVeg | proveg.org | https://proveg.org/feed | FOOD | own | DE | ok |  | aufgenommen |
| Rundschau für den Lebensmittelhandel | rundschau.de | https://rundschau.de/feed/ | FOOD | own | DE | ok |  | aufgenommen |
| sweets processing | sweets-processing.com | https://sweets-processing.com/news/rss | FOOD | own | DE | ok |  | aufgenommen |
| Swiss Food & Nutrition Valley | swissfoodnutritionvalley.com | https://swissfoodnutritionvalley.com/feed/ | FOOD | own | CH | ok |  | aufgenommen |
| The Grocer | thegrocer.co.uk | https://www.thegrocer.co.uk/34272.rss | FOOD | own | UK | ok |  | aufgenommen |
| top agrar | topagrar.com | https://www.topagrar.com/feed/news.xml | FOOD | own | DE | ok |  | aufgenommen |
| AGES | ages.at |  | FOOD | own | AT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Agroscope | agroscope.admin.ch |  | FOOD | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Anuga Koelnmesse | koelnmesse.de |  | FOOD | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (23 URLs tried)) |
| BDSI Süßwarenindustrie | bdsi.de |  | FOOD | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (23 URLs tried)) |
| Beverage Digest | beverage-digest.com |  | FOOD | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BfR Bundesinstitut für Risikobewertung | bfr.bund.de | https://bfr.bund.de/feed.xml | FOOD | own | DE | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| BigHospitality | bighospitality.co.uk |  | FOOD | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BMEL | bmel.de | https://www.bmleh.de/SiteGlobals/Functions/RSSFeed/RSSNewsfeed/RSSNewsfeed_Pressemitteilungen.xml | FOOD | own | DE | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| Brauwelt | brauwelt.com |  | FOOD | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (23 URLs tried)) |
| Bäckerblume B&L Medien | blmedien.de | https://blmedien.de/feed/ | FOOD | wikipedia | DE | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2025-02-13) |
| Decanter | decanter.com | https://www.decanter.com/feeds.xml | FOOD | wikipedia | UK | ok |  | nicht aufgenommen: Consumer-Wein |
| Der Feinschmecker | der-feinschmecker.de |  | FOOD | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Deutsche Gesellschaft für Ernährung | dge.de |  | FOOD | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| DLG | dlg.org |  | FOOD | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| EIT Food | eitfood.eu | https://eitfood.eu/rss | FOOD | own | EU | blocked |  | nicht aufgenommen: blocked (article HTTP 429 for the bot UA) |
| essen & trinken | essen-und-trinken.de | https://www.essen-und-trinken.de/feed/rss/ | FOOD | wikipedia | DE | ok |  | nicht aufgenommen: Consumer-Kochmagazin |
| Farmers Guide | farmersguide.co.uk | https://farmersguide.co.uk/feed | FOOD | wikipedia | UK | ok |  | nicht aufgenommen: UK-Landtechnik (Consumer) |
| Farmers Weekly | fwi.co.uk |  | FOOD | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Fleischwirtschaft | fleischwirtschaft.de | https://www.fleischwirtschaft.de/news/feed/ | FOOD | own | DE | reserved |  | nicht aufgenommen: reserved (meta tdm-reservation: 1) |
| Food and Drink Technology | foodanddrinktechnology.com | https://www.foodanddrinktechnology.com/feed/ | FOOD | feedspot | UK | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2012-10-05) |
| Food Business News | foodbusinessnews.net |  | FOOD | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Food Ingredients First | foodingredientsfirst.com | https://resource-cns.cnsmedia.com/rss/fifnews.xml | FOOD | own | NL | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| Food Logistics | foodlogistics.com |  | FOOD | feedspot | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Food Processing Australia | foodprocessing.com.au | https://www.foodprocessing.com.au/feed | FOOD | feedspot | AU | ok |  | nicht aufgenommen: Australien-Fachblatt, geringer Bezug |
| Food Technology NZ | foodtechnology.co.nz | https://www.foodtechnology.co.nz/feed/ | FOOD | feedspot | NZ | ok |  | nicht aufgenommen: Neuseeland-Fachblatt, geringer Bezug |
| food-service | food-service.de | https://www.food-service.de/nachrichten/feed/ | FOOD | own | DE | reserved |  | nicht aufgenommen: reserved (meta tdm-reservation: 1) |
| foodaktuell | foodaktuell.ch |  | FOOD | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| foodwatch | foodwatch.org |  | FOOD | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Fraunhofer IVV | ivv.fraunhofer.de |  | FOOD | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| gastroinfoportal | gastroinfoportal.de |  | FOOD | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Harpers Wine & Spirit | harpers.co.uk | https://harpers.co.uk/news/rss.php/rss.xml | FOOD | wikipedia | UK | ok |  | nicht aufgenommen: UK-Weinhandel |
| IFT Food Technology | ift.org |  | FOOD | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Imbibe | imbibemagazine.com | https://imbibemagazine.com/feed/ | FOOD | wikipedia | US | ok |  | nicht aufgenommen: Consumer-Getränke |
| Italian Food Tech | italianfoodtech.com | https://www.italianfoodtech.com/feed/ | FOOD | feedspot | IT | ok |  | nicht aufgenommen: Italien-Fachblatt (EN, klein) |
| Julius Kühn-Institut | julius-kuehn.de |  | FOOD | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Konsument VKI | konsument.at |  | FOOD | wikipedia | AT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Lebensmittelverband Deutschland | lebensmittelverband.de |  | FOOD | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Max Rubner-Institut | mri.bund.de |  | FOOD | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| New Food Magazine | newfoodmagazine.com |  | FOOD | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| ProFood World | profoodworld.com |  | FOOD | feedspot | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| SupplySide Food & Beverage Journal | supplysidefbj.com | https://supplysidefbj.com/rss.xml | FOOD | feedspot | US | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| The Drinks Business | thedrinksbusiness.com |  | FOOD | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| The Morning Advertiser | morningadvertiser.co.uk |  | FOOD | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Thünen-Institut | thuenen.de |  | FOOD | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| USDA | usda.gov | https://www.usda.gov/about-usda/news/press-releases | FOOD | own | US | blocked |  | nicht aufgenommen: blocked (feed HTTP 403 for the bot UA) |
| VegNews | vegnews.com | https://vegnews.com/feed.rss | FOOD | wikipedia | US | ok |  | nicht aufgenommen: Consumer-Vegan |
| Vinum | vinum.info |  | FOOD | wikipedia | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Wein+Markt | wein-und-markt.de |  | FOOD | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Öko-Test | oekotest.de | https://feeds.purplemanager.com/353c4833-8b25-428b-825c-d3339038bf4c/newsfeed | FOOD | wikipedia | DE | ok |  | nicht aufgenommen: Verbrauchertests – Owner-Entscheid (Warentest-Signale?) |
| Ökolandbau.de | oekolandbau.de |  | FOOD | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |

### DESIGN (63 Kandidaten, 24 aufgenommen)

| Name | Domain | Feed | Vertikale | Herkunft | Land | Status | Lizenz | Entscheidung |
|---|---|---|---|---|---|---|---|---|
| A List Apart | alistapart.com | https://alistapart.com/main/feed/ | DESIGN | own | US | ok |  | aufgenommen |
| Architizer | architizer.com | https://architizer.com/blog/feed | DESIGN | own | US | ok |  | aufgenommen |
| Auto&Design | autodesignmagazine.com | https://autodesignmagazine.com/feed/ | DESIGN | feedspot | IT | ok |  | aufgenommen |
| Azure Magazine | azuremagazine.com | https://azuremagazine.com/feed | DESIGN | own | CA | ok |  | aufgenommen |
| BauNetz | baunetz.de | https://www.baunetz.de/meldungen/rss.xml | DESIGN | own | DE | ok |  | aufgenommen |
| Bauwelt | bauwelt.de | https://www.bauwelt.de/das-heft/rss-feed/rssfeed_ausgaben_2073556.xml | DESIGN | own | DE | ok |  | aufgenommen |
| Bundesarchitektenkammer | bak.de | https://bak.de/feed/ | DESIGN | own | DE | ok |  | aufgenommen |
| Core77 | core77.com | https://core77.com/feed | DESIGN | own | US | ok |  | aufgenommen |
| Creative Review | creativereview.co.uk | https://www.creativereview.co.uk/feed/ | DESIGN | own | UK | ok |  | aufgenommen |
| db deutsche bauzeitung | db-bauzeitung.de | https://www.db-bauzeitung.de/feed/ | DESIGN | own | DE | ok |  | aufgenommen |
| DBZ Deutsche BauZeitschrift | dbz.de | https://www.dbz.de/rss.xml | DESIGN | own | DE | ok |  | aufgenommen |
| Design Indaba | designindaba.com | https://designindaba.com/rss.xml | DESIGN | own | ZA | ok |  | aufgenommen |
| Designtagebuch | designtagebuch.de | https://www.designtagebuch.de/feed/ | DESIGN | own | DE | ok |  | aufgenommen |
| DesignWanted | designwanted.com | https://designwanted.com/feed | DESIGN | feedspot | IT | ok |  | aufgenommen |
| DEVELOP3D | develop3d.com | https://develop3d.com/feed/ | DESIGN | feedspot | UK | ok |  | aufgenommen |
| Divisare | divisare.com | https://divisare.com/publications/11/feed | DESIGN | own | IT | ok |  | aufgenommen |
| Dwell | dwell.com | https://www.dwell.com/@dwell/rss | DESIGN | own | US | ok |  | aufgenommen |
| It's Nice That | itsnicethat.com | http://feeds2.feedburner.com/itsnicethat/SlXC | DESIGN | own | UK | ok |  | aufgenommen |
| Machine Design | machinedesign.com | https://www.machinedesign.com/__rss/website-scheduled-content.xml?input=%7B%22sectionAlias%22%3A%22home%22%7D | DESIGN | feedspot | US | ok |  | aufgenommen |
| Neue Landschaft | neuelandschaft.de | https://neuelandschaft.de/rss.xml | DESIGN | wikipedia | DE | ok |  | aufgenommen |
| PAGE online | page-online.de | https://page-online.de/feed/ | DESIGN | own | DE | ok |  | aufgenommen |
| Smashing Magazine | smashingmagazine.com | https://smashingmagazine.com/feed | DESIGN | own | DE | ok |  | aufgenommen |
| Stylepark | stylepark.com | https://www.stylepark.com/en/rss | DESIGN | own | DE | ok |  | aufgenommen |
| UX Magazine | uxmag.com | https://uxmag.com/feed | DESIGN | feedspot | US | ok |  | aufgenommen |
| Archello | archello.com |  | DESIGN | own | NL | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Architect Magazine | architectmagazine.com |  | DESIGN | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Architonic | architonic.com |  | DESIGN | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Australian Design Review | australiandesignreview.com |  | DESIGN | own | AU | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| AW Architektur + Wettbewerbe | architekturundwettbewerbe.de |  | DESIGN | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Baublatt | baublatt.ch |  | DESIGN | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Bauhaus Dessau | bauhaus-dessau.de |  | DESIGN | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BDA Bund Deutscher Architekten | bda-bund.de | https://www.bda-bund.de/feed/ | DESIGN | own | DE | feed_error |  | nicht aufgenommen: feed_error (article HTTP 404 (unverified)) |
| Bundesstiftung Baukultur | bundesstiftung-baukultur.de |  | DESIGN | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| competitionline | competitionline.com |  | DESIGN | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Design Week | designweek.co.uk | https://designweek.co.uk/feed/ | DESIGN | own | UK | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| Design World | designworldonline.com |  | DESIGN | feedspot | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| DETAIL | detail.de |  | DESIGN | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Dexigner | dexigner.com | https://www.dexigner.com/feed/news | DESIGN | own | US | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2022-09-27) |
| DGNB | dgnb.de |  | DESIGN | feedspot | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Disegno | disegnojournal.com |  | DESIGN | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Domus | domusweb.it |  | DESIGN | own | IT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| DPA Design Products & Applications | dpaonthenet.net |  | DESIGN | feedspot | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Entwürfe | entwuerfe.ch | https://entwuerfe.ch/feed/ | DESIGN | wikipedia | CH | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2021-09-10) |
| form | form.de |  | DESIGN | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Frame | frameweb.com |  | DESIGN | own | NL | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Gebäude-Energieberater | geb-info.de |  | DESIGN | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| German-Architects | german-architects.com |  | DESIGN | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Hochparterre | hochparterre.ch | https://www.hochparterre.ch/rss | DESIGN | own | CH | feed_error |  | nicht aufgenommen: feed_error (HTML page, no feed found (21 URLs tried)) |
| iF Design | ifdesign.com |  | DESIGN | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Interior Design | interiordesign.net |  | DESIGN | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| MaterialDistrict | materialdistrict.com |  | DESIGN | own | NL | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Messe Frankfurt | messefrankfurt.com |  | DESIGN | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Metropolis | metropolismag.com |  | DESIGN | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| ndion German Design Council | ndion.de |  | DESIGN | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| New Design Magazine | newdesignmagazine.co.uk | https://newdesignmagazine.co.uk/feed/ | DESIGN | feedspot | UK | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2024-06-24) |
| Nielsen Norman Group | nngroup.com |  | DESIGN | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Print & Produktion | print-und-produktion.de |  | DESIGN | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Publishing Praxis | publish.de |  | DESIGN | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Red Dot | red-dot.org |  | DESIGN | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Schweizer Holzzeitung | holz-portal.ch |  | DESIGN | wikipedia | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Swiss-Architects | swiss-architects.com |  | DESIGN | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Vitra Magazine | vitra.com |  | DESIGN | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Zuschnitt proHolz | zuschnitt.at |  | DESIGN | wikipedia | AT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |

### FASHION (79 Kandidaten, 14 aufgenommen)

| Name | Domain | Feed | Vertikale | Herkunft | Land | Status | Lizenz | Entscheidung |
|---|---|---|---|---|---|---|---|---|
| Apparel Resources | apparelresources.com | https://apparelresources.com/feed/ | FASHION | own | IN | ok |  | aufgenommen |
| Beauty Independent | beautyindependent.com | https://www.beautyindependent.com/feed/ | FASHION | own | US | ok |  | aufgenommen |
| Cosmetics Business | cosmeticsbusiness.com | https://cosmeticsbusiness.com/rss | FASHION | own | UK | ok |  | aufgenommen |
| Drapers | drapersonline.com | https://www.drapersonline.com/feed | FASHION | own | UK | ok |  | aufgenommen |
| EURATEX | euratex.eu | https://euratex.eu/feed/ | FASHION | own | EU | ok |  | aufgenommen |
| GermanFashion Modeverband | germanfashion.net | https://germanfashion.net/feed/ | FASHION | own | DE | ok |  | aufgenommen |
| GZ Goldschmiede Zeitung | gz-online.de | https://www.gz-online.de/feed/ | FASHION | own | DE | ok |  | aufgenommen |
| Innovation in Textiles | innovationintextiles.com | https://innovationintextiles.com/feed/ | FASHION | own | UK | ok |  | aufgenommen |
| Just Style | just-style.com | https://www.just-style.com/feed/ | FASHION | own | UK | ok |  | aufgenommen |
| Premium Beauty News | premiumbeautynews.com | https://www.premiumbeautynews.com/spip.php?page=backend | FASHION | own | FR | ok |  | aufgenommen |
| Textile Exchange | textileexchange.org | https://textileexchange.org/feed | FASHION | own | US | ok |  | aufgenommen |
| Textile World | textileworld.com | https://www.textileworld.com/feed/ | FASHION | feedspot | US | ok |  | aufgenommen |
| Textination | textination.de | https://textination.de/rss.xml | FASHION | own | DE | ok |  | aufgenommen |
| TheIndustry.fashion | theindustry.fashion | https://theindustry.fashion/feed | FASHION | feedspot | UK | ok |  | aufgenommen |
| 032c | 032c.com |  | FASHION | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| 10 Magazine | 10magazine.com | https://10magazine.com/feed/ | FASHION | wikipedia | UK | ok |  | nicht aufgenommen: Consumer-Mode |
| Advanced Textiles Source | advancedtextilessource.com |  | FASHION | feedspot | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| AnOther | anothermag.com | https://www.anothermag.com/Feed | FASHION | wikipedia | UK | ok |  | nicht aufgenommen: Consumer-Mode |
| Beauty Packaging | beautypackaging.com |  | FASHION | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| beauty-forum | beauty-forum.com |  | FASHION | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BeautyMatter | beautymatter.com |  | FASHION | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Beautyressort | beautyressort.de | https://beautyressort.de/feed/ | FASHION | feedspot | DE | ok |  | nicht aufgenommen: Privatblog |
| Cosmetic Business | cosmetic-business.com |  | FASHION | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| CosmeticsDesign Europe | cosmeticsdesign-europe.com |  | FASHION | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Dazed | dazeddigital.com | https://www.dazeddigital.com/rss | FASHION | wikipedia | UK | ok |  | nicht aufgenommen: Consumer-Jugendkultur |
| DITF Textil- und Faserforschung | ditf.de |  | FASHION | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| E2 Tech Textiles | e2techtextiles.com | https://www.e2techtextiles.com/feed/ | FASHION | feedspot | IN | ok |  | nicht aufgenommen: Indien-Handelsportal |
| Fabric Architecture | fabricarchitecturemag.com | https://fabricarchitecturemag.com/feed | FASHION | feedspot | US | ok |  | nicht aufgenommen: Nischen-Fachblatt |
| Fair Fashion Blog | fairfashionblog.de | https://www.fairfashionblog.de/feed/ | FASHION | feedspot | DE | ok |  | nicht aufgenommen: Privatblog |
| Fantastic Man | fantasticman.com |  | FASHION | wikipedia | NL | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Fashion for Good | fashionforgood.com |  | FASHION | own | NL | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Fashion Magazine | fashionmagazine.com |  | FASHION | wikipedia | CA | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Fashion Revolution | fashionrevolution.org | https://fashionrevolution.org/feed | FASHION | own | UK | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2026-02-20) |
| FashionNetwork DE | de.fashionnetwork.com |  | FASHION | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| FashionUnited | fashionunited.de |  | FASHION | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| FashionUnited International | fashionunited.com |  | FASHION | feedspot | NL | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Fibre2Fashion | fibre2fashion.com |  | FASHION | own | IN | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Gesamtverband textil+mode | textil-mode.de |  | FASHION | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Global Cosmetic Industry | gcimagazine.com |  | FASHION | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Happi | happi.com |  | FASHION | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Hohenstein | hohenstein.de |  | FASHION | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Hypebae | hypebae.com | https://hypebae.com/feed | FASHION | own | US | ok |  | nicht aufgenommen: Consumer-Streetwear |
| i-D | i-d.co | https://i-d.co/feed/ | FASHION | wikipedia | UK | ok |  | nicht aufgenommen: Consumer-Mode |
| IKW Körperpflege | ikw.org |  | FASHION | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| INDA | inda.org | https://www.inda.org/feed/ | FASHION | feedspot | US | ok |  | nicht aufgenommen: US-Vliesstoffverband |
| IndiaRetailing | indiaretailing.com |  | FASHION | feedspot | IN | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| ISPO.com | ispo.com |  | FASHION | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| JCK | jckonline.com | https://www.jckonline.com/comments/feed/ | FASHION | own | US | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2018-06-26) |
| Jing Daily | jingdaily.com |  | FASHION | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (22 URLs tried)) |
| Journelles | journelles.de | https://www.journelles.de/feed | FASHION | feedspot | DE | ok |  | nicht aufgenommen: Privatblog |
| Kaltblut Magazine | kaltblut-magazine.com | https://www.kaltblut-magazine.com/feed/ | FASHION | feedspot | DE | ok |  | nicht aufgenommen: Indie-Modemagazin |
| L'Officiel | lofficiel.com |  | FASHION | wikipedia | FR | feed_error |  | nicht aufgenommen: feed_error (no feed found (22 URLs tried)) |
| Lucire | lucire.com | https://lucire.com/insider/feed/ | FASHION | wikipedia | NZ | ok |  | nicht aufgenommen: Consumer-Mode NZ |
| Madame | madame.de |  | FASHION | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Modepilot | modepilot.de | https://www.modepilot.de/feed/ | FASHION | own | DE | ok |  | nicht aufgenommen: Privatblog |
| NCTO | ncto.org | https://ncto.org/feed/ | FASHION | feedspot | US | ok |  | nicht aufgenommen: US-Textilverband (Lobby) |
| Nonwovens Industry | nonwovens-industry.com |  | FASHION | feedspot | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Numéro | numero.com | https://numero.com/feed/ | FASHION | wikipedia | FR | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| Nylon | nylon.com | https://www.nylon.com/rss | FASHION | wikipedia | US | ok |  | nicht aufgenommen: Consumer-Mode |
| Paper | papermag.com | https://www.papermag.com/feeds/feed.rss | FASHION | wikipedia | US | ok |  | nicht aufgenommen: Consumer-Pop |
| Professional Jeweller | professionaljeweller.com |  | FASHION | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Schön! Magazine | schonmagazine.com | https://schonmagazine.com/feed/ | FASHION | wikipedia | UK | ok |  | nicht aufgenommen: Consumer-Mode |
| Sneaker Freaker | sneakerfreaker.com | https://sneakerfreaker.com/rss.xml | FASHION | wikipedia | AU | ok |  | nicht aufgenommen: Consumer-Sneaker |
| Sourcing Journal | sourcingjournal.com | https://wwd.com/feed/rss/ | FASHION | own | US | ok |  | nicht aufgenommen: Dublette (Domain schon aktiv) |
| Sportswear International | sportswear-international.com |  | FASHION | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| StartUp Fashion | startupfashion.com | https://startupfashion.com/feed/ | FASHION | feedspot | US | ok |  | nicht aufgenommen: Ratgeber-Blog, kein Fachmedium |
| Stylist | stylist.co.uk | https://stylist.co.uk/feed | FASHION | wikipedia | UK | ok |  | nicht aufgenommen: Consumer-Mode UK |
| Swiss Textiles | swisstextiles.ch |  | FASHION | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Textile Focus | textilefocus.com | https://textilefocus.com/feed/ | FASHION | feedspot | BD | ok |  | nicht aufgenommen: Bangladesch-Fachblatt |
| textile network | textile-network.com | https://textile-network.com/rss | FASHION | own | DE | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 1789-01-20) |
| Textile Today | textiletoday.com.bd | https://textiletoday.com.bd/feed | FASHION | feedspot | BD | ok |  | nicht aufgenommen: Bangladesch-Fachblatt, geringer Bezug |
| Textile Web | textileweb.com |  | FASHION | feedspot | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Textilegence | textilegence.com | https://www.textilegence.com/feed/ | FASHION | feedspot | TR | ok |  | nicht aufgenommen: Türkei-Fachblatt |
| The Face | theface.com |  | FASHION | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| The Fashion Law | thefashionlaw.com |  | FASHION | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (23 URLs tried)) |
| Vestoj | vestoj.com | https://vestoj.com/feed/ | FASHION | wikipedia | FR | ok |  | nicht aufgenommen: Modetheorie-Journal |
| Vogue Business | voguebusiness.com | https://www.vogue.com/feed/rss | FASHION | own | UK | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the article URL) |
| WatchPro | watchpro.com |  | FASHION | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Yarns and Fibers | yarnsandfibers.com | https://www.yarnsandfibers.com/feed/ | FASHION | feedspot | IN | ok |  | nicht aufgenommen: Indien-Handelsportal |

### ECO (97 Kandidaten, 32 aufgenommen)

| Name | Domain | Feed | Vertikale | Herkunft | Land | Status | Lizenz | Entscheidung |
|---|---|---|---|---|---|---|---|---|
| AIT Austrian Institute of Technology | ait.ac.at | https://ait.ac.at/rss | ECO | own | AT | ok |  | aufgenommen |
| biooekonomie.de | biooekonomie.de | https://biooekonomie.de/rssnewsfeed | ECO | own | DE | ok |  | aufgenommen |
| BMUV | bmuv.de | https://www.bundesumweltministerium.de/umwelt.rss | ECO | own | DE | ok |  | aufgenommen |
| BSW-Solar | solarwirtschaft.de | https://solarwirtschaft.de/feed | ECO | own | DE | ok |  | aufgenommen |
| Bundesnetzagentur | bundesnetzagentur.de | https://bundesnetzagentur.de/rss | ECO | own | DE | ok |  | aufgenommen |
| Clean Energy Wire | cleanenergywire.org | https://cleanenergywire.org/rss.xml | ECO | own | DE | ok | CC BY 4.0 | aufgenommen (fulltext, CC BY 4.0) |
| Corporate Knights | corporateknights.com | https://corporateknights.com/feed/ | ECO | wikipedia | CA | ok |  | aufgenommen |
| Energiezukunft | energiezukunft.eu | https://energiezukunft.eu/rss | ECO | own | DE | ok |  | aufgenommen |
| Energy Transition | energytransition.org | https://energytransition.org/feed/ | ECO | own | DE | ok |  | aufgenommen |
| Energy-Storage.news | energy-storage.news | https://www.energy-storage.news/feed/ | ECO | own | UK | ok |  | aufgenommen |
| Fraunhofer ISE | ise.fraunhofer.de | https://www.ise.fraunhofer.de/de/rss/presseinformationen.rss | ECO | own | DE | ok |  | aufgenommen |
| Germanwatch | germanwatch.org | https://germanwatch.org/rss.xml | ECO | feedspot | DE | ok |  | aufgenommen |
| Helmholtz-Gemeinschaft | helmholtz.de | https://www.helmholtz.de/ueber-uns/wer-wir-sind/presse-medien/mediathek/rss-feeds/presseinformationen/feed.xml | ECO | own | DE | ok |  | aufgenommen |
| HZDR | hzdr.de | https://www.hzdr.de/rss_presse.xml | ECO | idw | DE | ok |  | aufgenommen |
| IDOS | blogs.idos-research.de | https://blogs.idos-research.de/feed/ | ECO | feedspot | DE | ok |  | aufgenommen |
| klimafakten | klimafakten.de | https://www.klimafakten.de/news/feed/rss.xml | ECO | own | DE | ok |  | aufgenommen |
| klimareporter | klimareporter.de | https://klimareporter.de/?format=feed&amp;type=rss | ECO | own | DE | ok |  | aufgenommen |
| Mongabay | news.mongabay.com | https://news.mongabay.com/feed | ECO | own | US | ok |  | aufgenommen |
| NABU | nabu.de | https://www.nabu.de/rssfeed.php | ECO | own | DE | ok |  | aufgenommen |
| Packaging Europe | packagingeurope.com | https://packagingeurope.com/2713.rss | ECO | own | UK | ok |  | aufgenommen |
| PIK Potsdam | pik-potsdam.de | https://pik-potsdam.de/rss.xml | ECO | own | DE | ok |  | aufgenommen |
| PSI Paul Scherrer Institut | psi.ch | https://psi.ch/rss.xml | ECO | own | CH | ok |  | aufgenommen |
| pv magazine International | pv-magazine.com | https://www.pv-magazine.com/feed/ | ECO | own | DE | ok |  | aufgenommen |
| PV Tech | pv-tech.org | https://www.pv-tech.org/feed/ | ECO | own | UK | ok |  | aufgenommen |
| RecyclingPortal | recyclingportal.eu | https://recyclingportal.eu/feed | ECO | own | DE | ok |  | aufgenommen |
| Solarserver | solarserver.de | https://www.solarserver.de/feed/ | ECO | own | DE | ok |  | aufgenommen |
| Sustain Europe | sustaineurope.com | https://www.sustaineurope.com/feed/ | ECO | wikipedia | UK | ok |  | aufgenommen |
| Sustainable Brands | sustainablebrands.com | https://sustainablebrands.com/rss | ECO | own | US | ok |  | aufgenommen |
| The Ecologist | theecologist.org | https://theecologist.org/rss | ECO | wikipedia | UK | ok |  | aufgenommen |
| TriplePundit | triplepundit.com | https://triplepundit.com/feed/ | ECO | own | US | ok |  | aufgenommen |
| Wuppertal Institut | wupperinst.org | http://wupperinst.org/rss_news_en.php | ECO | own | DE | ok |  | aufgenommen |
| Yale Environment 360 | e360.yale.edu | https://e360.yale.edu/feed.xml | ECO | own | US | ok |  | aufgenommen |
| Agora Energiewende | agora-energiewende.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BAFU | bafu.admin.ch |  | ECO | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BDEW | bdew.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BEE Erneuerbare Energie | bee-ev.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BMWE | bmwe.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BMWK | bmwk.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BWE Windenergie | wind-energie.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| CSIRO | csiro.au |  | ECO | wikipedia | AU | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| dena | dena.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Deutsche Bundesstiftung Umwelt | dbu.de | https://dbu.de/feed | ECO | idw | DE | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2022-07-04) |
| Deutsche Umwelthilfe | duh.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Down To Earth | downtoearth.org.in | https://downtoearth.org.in/feed | ECO | wikipedia | IN | ok |  | nicht aufgenommen: Indien-Umweltmagazin |
| edie | edie.net |  | ECO | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| EEA Featured Articles | eea.europa.eu | https://www.eea.europa.eu/en/newsroom/rss-feeds/featured-articles-rss//rss.xml | ECO | own | EU | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| electrive | electrive.net |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Ellen MacArthur Foundation | ellenmacarthurfoundation.org |  | ECO | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Empa | empa.ch |  | ECO | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| ENDS Report | endsreport.com |  | ECO | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| energate messenger | energate-messenger.de | https://content.energate.de/rss/energate-messenger-plus.xml | ECO | own | DE | reserved |  | nicht aufgenommen: reserved (tdmrep.json location='/') |
| Energie & Management | energie-und-management.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| EPA News Releases | epa.gov | https://www.epa.gov/newsreleases/search/rss | ECO | own | US | feed_error |  | nicht aufgenommen: feed_error (feed HTTP 405) |
| erneuerbareenergien.de | erneuerbareenergien.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| European Environment Agency | eea.europa.eu | https://www.eea.europa.eu/en/newsroom/rss-feeds/eeas-press-releases-rss/rss.xml | ECO | own | EU | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| EUWID Recycling | euwid-recycling.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Forschungszentrum Jülich | fz-juelich.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (26 URLs tried)) |
| Green Car Journal | greencar.com |  | ECO | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| H2 View | h2-view.com |  | ECO | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Hereon | hereon.de | https://www.techfacts.de/feed/ | ECO | own | DE | ok |  | nicht aufgenommen: Feed auf fremder Domain (techfacts.de) – Autodiscovery-Fehltreffer |
| High Country News | hcn.org | https://www.hcn.org/feed/ | ECO | wikipedia | US | ok | CC BY-NC-ND 4.0 | nicht aufgenommen: US-Regionalmagazin |
| HNEE Eberswalde | hnee.de |  | ECO | idw | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Hydrogen Insight | hydrogeninsight.com |  | ECO | own | NO | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| IEA | iea.org | https://www.iea.org/news.rss | ECO | own | INT | feed_error |  | nicht aufgenommen: feed_error (feed HTTP 404) |
| IISD | iisd.org |  | ECO | wikipedia | CA | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| IRENA | irena.org |  | ECO | own | INT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| JRC Joint Research Centre | joint-research-centre.ec.europa.eu |  | ECO | own | EU | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| KIT | kit.edu | https://www.kit.edu/pi.rss | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (article HTTP 404 (unverified)) |
| Klima- und Energiefonds | klimafonds.gv.at | https://klimafonds.gv.at/feed | ECO | own | AT | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2024-09-18) |
| Kunststoffe | kunststoffe.de |  | ECO | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| natur | natur.de | https://natur.de/feed.xml | ECO | wikipedia | DE | ok |  | nicht aufgenommen: Consumer-Naturmagazin |
| neue verpackung | neue-verpackung.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| NOAA News Releases | noaa.gov | https://www.noaa.gov/news-release/rss | ECO | own | US | blocked |  | nicht aufgenommen: blocked (feed HTTP 403 for the bot UA) |
| NREL News | nrel.gov | https://www.nrel.gov/news/rss.xml | ECO | own | US | feed_error |  | nicht aufgenommen: feed_error (feed unreachable (ConnectError)) |
| OilPrice | oilprice.com | https://feeds.feedburner.com/oilpricecom | ECO | hn | US | ok |  | nicht aufgenommen: Rohstoffnachrichten, HN-Einzeltreffer |
| Orion Magazine | orionmagazine.org |  | ECO | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Rat für Nachhaltige Entwicklung | nachhaltigkeitsrat.de |  | ECO | feedspot | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (24 URLs tried)) |
| Recycling International | recyclinginternational.com |  | ECO | own | NL | feed_error |  | nicht aufgenommen: feed_error (no feed found (22 URLs tried)) |
| Recyclingmagazin | recyclingmagazin.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| reNews | renews.biz |  | ECO | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Resource | resource.co |  | ECO | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Resurgence & Ecologist | resurgence.org |  | ECO | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| RIFS Potsdam | rifs-potsdam.de |  | ECO | feedspot | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (23 URLs tried)) |
| SDSN Germany | sdsngermany.de | https://sdsngermany.de/feed | ECO | feedspot | DE | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2025-08-28) |
| Sierra Club | sierraclub.org |  | ECO | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| TMG Think Tank | tmg-thinktank.com |  | ECO | feedspot | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Umweltbundesamt | umweltbundesamt.de | https://www.umweltbundesamt.de/presse/rss | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (feed HTTP 404) |
| Umweltbundesamt Österreich | umweltbundesamt.at |  | ECO | own | AT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| UNEP | unep.org | https://unep.org/rss.xml | ECO | own | INT | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| US Department of Energy | energy.gov | https://www.energy.gov/rss.xml | ECO | own | US | ok | Public Domain (US federal) | nicht aufgenommen: veraltet (jüngster Eintrag 2020-06-10) |
| USGS | usgs.gov | https://www.usgs.gov/news/rss | ECO | own | US | feed_error |  | nicht aufgenommen: feed_error (feed HTTP 404) |
| VKU | vku.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (25 URLs tried)) |
| Windpower Monthly | windpowermonthly.com |  | ECO | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| World Resources Institute | wri.org |  | ECO | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| WWF Deutschland | wwf.de |  | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Zeitschrift für Umweltrecht | zeitschrift-fuer-umweltrecht.de |  | ECO | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Öko-Institut | oeko.de | https://www.oeko.de/rss-feed | ECO | own | DE | feed_error |  | nicht aufgenommen: feed_error (feed HTTP 404) |

### TECH (127 Kandidaten, 37 aufgenommen)

| Name | Domain | Feed | Vertikale | Herkunft | Land | Status | Lizenz | Entscheidung |
|---|---|---|---|---|---|---|---|---|
| AI News | artificialintelligence-news.com | https://www.artificialintelligence-news.com/feed/ | TECH | own | UK | ok |  | aufgenommen |
| Bitkom | bitkom.org | https://bitkom.org/feed | TECH | own | DE | ok |  | aufgenommen |
| CERN | home.cern | https://home.cern/feed/ | TECH | own | INT | ok |  | aufgenommen |
| DARPA | darpa.mil | https://www.darpa.mil/rss.xml | TECH | own | US | ok | Public Domain (US federal) | aufgenommen (fulltext, Public Domain (US federal)) |
| DIN | din.de | https://www.din.de/service/rss/din-de/64514/feed.rss | TECH | own | DE | ok |  | aufgenommen |
| DPMA | dpma.de | https://www.dpma.de/rss.xml | TECH | own | DE | ok |  | aufgenommen |
| EE Journal | eejournal.com | https://www.eejournal.com/feed/ | TECH | own | US | ok |  | aufgenommen |
| Electronics Weekly | electronicsweekly.com | https://www.electronicsweekly.com/feed/ | TECH | own | UK | ok |  | aufgenommen |
| Elektronik Praxis | elektronikpraxis.de | https://www.elektronikpraxis.de/rss/news.xml | TECH | own | DE | ok |  | aufgenommen |
| elektroniknet | elektroniknet.de | https://elektroniknet.de/feed | TECH | own | DE | ok |  | aufgenommen |
| EPO European Patent Office | epo.org | https://epo.org/rss.xml | TECH | own | EU | ok |  | aufgenommen |
| ETH Zürich | ethz.ch | https://www.ethz.ch/en/news-und-veranstaltungen/eth-news/news/_jcr_content.feed.html | TECH | own | CH | ok |  | aufgenommen |
| European Spaceflight | europeanspaceflight.com | https://europeanspaceflight.com/feed/ | TECH | own | EU | ok |  | aufgenommen |
| Fraunhofer IAO | iao.fraunhofer.de | https://www.iao.fraunhofer.de/de/presseservice/rss-feed/iao-news.rss | TECH | own | DE | ok |  | aufgenommen |
| Fraunhofer IIS | iis.fraunhofer.de | https://www.iis.fraunhofer.de/de/rss/presse.rss | TECH | own | DE | ok |  | aufgenommen |
| Fraunhofer IPA | ipa.fraunhofer.de | https://www.ipa.fraunhofer.de/de/presse/rss-feeds.rss | TECH | own | DE | ok |  | aufgenommen |
| futurezone | futurezone.at | https://futurezone.at/xml/rss | TECH | own | AT | ok |  | aufgenommen |
| GitHub Blog | github.blog | https://github.blog/feed/ | TECH | own | US | ok |  | aufgenommen |
| Google DeepMind | deepmind.google | https://deepmind.google/blog/feed | TECH | hn | US | ok |  | aufgenommen |
| inside-it | inside-it.ch | https://inside-it.ch/rss.xml | TECH | own | CH | ok |  | aufgenommen |
| ISTA Austria | ista.ac.at | https://ista.ac.at/?feed=rss2 | TECH | idw | AT | ok |  | aufgenommen |
| Laboratory News | labnews.co.uk | https://labnews.co.uk/feed/ | TECH | wikipedia | UK | ok |  | aufgenommen |
| Leibniz-Gemeinschaft | leibniz-gemeinschaft.de | https://leibniz-gemeinschaft.de/rss.xml | TECH | own | DE | ok |  | aufgenommen |
| Light Reading | lightreading.com | https://lightreading.com/rss.xml | TECH | own | US | ok |  | aufgenommen |
| Max-Planck-Gesellschaft | mpg.de | https://www.mpg.de/en/research.rss | TECH | own | DE | ok |  | aufgenommen |
| Netzwoche | netzwoche.ch | https://netzwoche.ch/rss.xml | TECH | own | CH | ok |  | aufgenommen |
| NIST News | nist.gov | https://www.nist.gov/news-events/news/rss.xml | TECH | own | US | ok | Public Domain (US federal) | aufgenommen (fulltext, Public Domain (US federal)) |
| Physics Today | physicstoday.org | https://physicstoday.aip.org/index.rss | TECH | wikipedia | US | ok |  | aufgenommen |
| Physics World | physicsworld.com | https://physicsworld.com/feed | TECH | wikipedia | UK | ok |  | aufgenommen |
| Quantum Computing Report | quantumcomputingreport.com | https://quantumcomputingreport.com/feed/ | TECH | own | US | ok |  | aufgenommen |
| SciDev.Net | scidev.net | https://www.scidev.net/global/global_rss.xml | TECH | own | UK | ok | CC BY 4.0 | aufgenommen (fulltext, CC BY 4.0) |
| Scientific American | scientificamerican.com | https://www.scientificamerican.com/platform/syndication/rss/ | TECH | wikipedia | US | ok |  | aufgenommen |
| Semiconductor Digest | semiconductor-digest.com | https://www.semiconductor-digest.com/feed/ | TECH | own | US | ok |  | aufgenommen |
| Swiss IT Magazine | itmagazine.ch | https://www.itmagazine.ch/rss/news.xml | TECH | own | CH | ok |  | aufgenommen |
| The PLOS Blog | theplosblog.plos.org | https://theplosblog.plos.org/feed/ | TECH | own | US | ok |  | aufgenommen |
| TUM | tum.de | https://tum.de/news.rss | TECH | own | DE | ok |  | aufgenommen |
| ZVEI | zvei.org | https://www.zvei.org/themen/rss-themen-industrie | TECH | own | DE | ok |  | aufgenommen |
| 404 Media | 404media.co | https://www.404media.co/rss/ | TECH | hn | US | ok |  | nicht aufgenommen: Tech-Newsletter (TECH-Balance) |
| ACM Queue | queue.acm.org |  | TECH | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| AiF | aif.de | https://www.aif.de/feed/ | TECH | idw | DE | ok |  | nicht aufgenommen: Förderverband, läuft über idw |
| All About Circuits | allaboutcircuits.com | https://allaboutcircuits.com/rss/ | TECH | own | US | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| American Scientist | americanscientist.org | https://americanscientist.org/rss.xml | TECH | wikipedia | US | ok |  | nicht aufgenommen: Mitgliedermagazin |
| Automation | automationnet.de |  | TECH | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Aviation Week | aviationweek.com | https://aviationweek.com/rss.xml | TECH | wikipedia | US | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| BBC Science Focus | sciencefocus.com | https://feeds.purplemanager.com/193c804a-a673-47bd-b09b-11baf4822a17/complete-rss-feed-for-science-focus | TECH | wikipedia | UK | ok |  | nicht aufgenommen: Consumer-Wissenschaft |
| bild der wissenschaft | wissenschaft.de | https://wissenschaft.de/feed.xml | TECH | wikipedia | DE | ok |  | nicht aufgenommen: Consumer-Wissenschaft |
| BleepingComputer | bleepingcomputer.com | https://www.bleepingcomputer.com/feed/ | TECH | own | US | ok |  | nicht aufgenommen: Security-News (breit) |
| BMFTR | bmftr.bund.de |  | TECH | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Chemical & Engineering News | cen.acs.org |  | TECH | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Cloudflare Blog | blog.cloudflare.com | https://blog.cloudflare.com/rss/ | TECH | hn | US | ok |  | nicht aufgenommen: Konzern-Blog (TECH-Balance) |
| Communications of the ACM | cacm.acm.org |  | TECH | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Computer & Automation | computer-automation.de |  | TECH | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Computer Weekly | computerweekly.com | https://www.computerweekly.com/rss/RSS-Feed.xml | TECH | wikipedia | UK | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| ComputerBase | computerbase.de | https://www.computerbase.de/rss/news.xml | TECH | own | DE | ok |  | nicht aufgenommen: Consumer-Hardware |
| Computerwelt | computerwelt.at |  | TECH | wikipedia | AT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Computerwoche | computerwoche.de | https://www.computerwoche.de/feed/ | TECH | own | DE | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| Computing | computing.co.uk |  | TECH | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| CORDIS | cordis.europa.eu | https://cordis.europa.eu/news/en?format=rss | TECH | own | EU | feed_error |  | nicht aufgenommen: feed_error (HTML page, no feed found (27 URLs tried)) |
| Cosmos | cosmosmagazine.com |  | TECH | wikipedia | AU | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Dark Reading | darkreading.com | https://darkreading.com/rss.xml | TECH | own | US | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| Datamation | datamation.com | https://www.datamation.com/feed/ | TECH | wikipedia | US | ok |  | nicht aufgenommen: US-Enterprise-IT (TECH-Balance) |
| DFKI | dfki.de | https://www.dfki.de/web/news-media/ | TECH | own | DE | blocked |  | nicht aufgenommen: blocked (feed HTTP 403 for the bot UA) |
| Discover | discovermagazine.com |  | TECH | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| DLR | dlr.de | https://www.dlr.de/en/rss | TECH | own | DE | feed_error |  | nicht aufgenommen: feed_error (HTML page, no feed found (23 URLs tried)) |
| dotnetpro | dotnetpro.de | https://www.developer-world.de/feed/rss | TECH | wikipedia | DE | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| EDN | edn.com |  | TECH | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Embedded | embedded.com |  | TECH | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| ENISA | enisa.europa.eu |  | TECH | own | EU | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| EPFL | epfl.ch |  | TECH | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (23 URLs tried)) |
| EU Science | science.europa.eu | https://science.europa.eu/rss? | TECH | own | EU | feed_error |  | nicht aufgenommen: feed_error (feed unreachable (ConnectError)) |
| EuroScience | euroscience.org |  | TECH | wikipedia | EU | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| eWeek | eweek.com | https://eweek.com/feed | TECH | wikipedia | US | ok |  | nicht aufgenommen: US-Enterprise-IT (TECH-Balance) |
| Falling Walls | falling-walls.com |  | TECH | idw | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| GeekWire | geekwire.com | https://www.geekwire.com/feed/ | TECH | hn | US | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| Google Keyword Blog | blog.google | https://blog.google/rss/ | TECH | hn | US | ok |  | nicht aufgenommen: Konzern-Blog (breit; Google Research reicht nicht) |
| Google Research Blog | research.google |  | TECH | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Hackaday | hackaday.com | https://hackaday.com/feed/ | TECH | own | US | ok |  | nicht aufgenommen: Maker-Blog |
| HPCwire | hpcwire.com |  | TECH | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Hugging Face Blog | huggingface.co | https://huggingface.co/blog | TECH | own | US | feed_error |  | nicht aufgenommen: feed_error (no entries (SAXParseException)) |
| IEEE Computer Society | computer.org | https://computer.org/feed | TECH | wikipedia | US | ok |  | nicht aufgenommen: Verbandsfeed (TECH-Balance) |
| InfoQ | infoq.com | https://infoq.com/feed | TECH | own | US | ok |  | nicht aufgenommen: Entwicklermedium (TECH-Balance) |
| InformationWeek | informationweek.com | https://www.informationweek.com/rss.xml | TECH | wikipedia | US | ok |  | nicht aufgenommen: US-Enterprise-IT (TECH-Balance) |
| InfoWorld | infoworld.com | https://www.infoworld.com/feed/ | TECH | wikipedia | US | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| International Railway Journal | railjournal.com |  | TECH | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Knowable Magazine | knowablemagazine.org | https://knowablemagazine.org/rss | TECH | wikipedia | US | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| Krebs on Security | krebsonsecurity.com | https://krebsonsecurity.com/feed/ | TECH | own | US | ok |  | nicht aufgenommen: Security-Blog (Einzelautor) |
| Linux Journal | linuxjournal.com | https://www.linuxjournal.com/node/feed | TECH | wikipedia | US | ok |  | nicht aufgenommen: Entwicklermagazin |
| Linux-Magazin | linux-magazin.de | https://www.linux-magazin.de/feed/ | TECH | wikipedia | DE | ok |  | nicht aufgenommen: Entwicklermagazin |
| LWN | lwn.net | https://lwn.net/headlines/rss | TECH | hn | US | reserved |  | nicht aufgenommen: reserved (header x-robots-tag: noai) |
| MacRumors | macrumors.com | https://feeds.macrumors.com/MacRumors-All | TECH | hn | US | ok |  | nicht aufgenommen: Consumer-Apple-News |
| Make: | makezine.com | https://makezine.com/feed/ | TECH | wikipedia | US | ok |  | nicht aufgenommen: Maker-Magazin |
| Microsoft Research | microsoft.com | https://microsoft.com/en-us/research | TECH | own | US | feed_error |  | nicht aufgenommen: feed_error (no entries (SAXParseException)) |
| Mozilla Blog | blog.mozilla.org | https://blog.mozilla.org/en/feed/ | TECH | hn | US | ok |  | nicht aufgenommen: Konzern-Blog (TECH-Balance) |
| OpenAI | openai.com |  | TECH | hn | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| PCtipp | pctipp.ch | https://www.pctipp.ch/feed/rss | TECH | wikipedia | CH | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| Phoronix | phoronix.com |  | TECH | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Popular Mechanics | popularmechanics.com | https://popularmechanics.com/rss | TECH | wikipedia | US | ok |  | nicht aufgenommen: Consumer-Wissenschaft |
| Popular Science | popsci.com | https://www.popsci.com/feed/ | TECH | wikipedia | US | ok |  | nicht aufgenommen: Consumer-Wissenschaft |
| RFID im Blick | rfid-im-blick.de |  | TECH | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| RWTH Aachen | rwth-aachen.de | https://www.rwth-aachen.de/cms/root/Die-RWTH/Aktuell/~uma/Pressemitteilungen/lidx/1/?rss=1&amp;dateid=1 | TECH | own | DE | ok |  | nicht aufgenommen: Hochschul-Presse läuft über idw |
| ScienceAlert | sciencealert.com | https://www.sciencealert.com/feed/gn/ | TECH | hn | AU | ok |  | nicht aufgenommen: Wissenschafts-Aggregator (Pressemeldungen) |
| SD Times | sdtimes.com | https://sdtimes.com/feed/ | TECH | own | US | ok |  | nicht aufgenommen: Entwicklermedium (TECH-Balance) |
| SecurityWeek | securityweek.com |  | TECH | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| ServeTheHome | servethehome.com | https://www.servethehome.com/feed/ | TECH | hn | US | ok |  | nicht aufgenommen: Hardware-Reviews (TECH-Balance) |
| SiliconANGLE | siliconangle.com | https://siliconangle.com/feed | TECH | own | US | ok |  | nicht aufgenommen: US-Enterprise-IT (TECH-Balance) |
| Spektrum der Wissenschaft | spektrum.de |  | TECH | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Techdirt | techdirt.com | https://www.techdirt.com/feed/ | TECH | hn | US | ok |  | nicht aufgenommen: Tech-Policy-Blog (TECH-Balance) |
| Technologist | technologist.eu | https://technologist.eu/feed/ | TECH | wikipedia | EU | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2019-04-23) |
| The New Stack | thenewstack.io | https://thenewstack.io/feed | TECH | own | US | ok |  | nicht aufgenommen: Entwicklermedium (TECH-Balance) |
| The Next Platform | nextplatform.com | https://nextplatform.com/feed | TECH | own | US | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| The Planetary Society | planetary.org | https://www.planetary.org/rss/articles | TECH | wikipedia | US | ok |  | nicht aufgenommen: Mitgliederorganisation |
| The Robot Report | therobotreport.com |  | TECH | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| The Scientist | the-scientist.com |  | TECH | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Tom's Hardware | tomshardware.com | https://www.tomshardware.com/feeds.xml | TECH | own | US | ok |  | nicht aufgenommen: Consumer-Hardware |
| TU Berlin | tu.berlin | https://tu.berlin/feed.xml | TECH | idw | DE | ok |  | nicht aufgenommen: Hochschul-Presse läuft über idw |
| TU Dresden | tu-dresden.de |  | TECH | idw | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (24 URLs tried)) |
| TU Wien | tuwien.at |  | TECH | own | AT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Understanding AI | understandingai.org |  | TECH | hn | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Uni Bremen | uni-bremen.de | https://www.uni-bremen.de/rss.xml | TECH | idw | DE | ok |  | nicht aufgenommen: Hochschul-Presse läuft über idw |
| Universität Stuttgart | uni-stuttgart.de | https://uni-stuttgart.de/rss.xml | TECH | idw | DE | ok |  | nicht aufgenommen: Hochschul-Presse läuft über idw |
| USPTO News | uspto.gov | https://www.uspto.gov/rss/uspto-news | TECH | own | US | feed_error |  | nicht aufgenommen: feed_error (feed HTTP 404) |
| VDE | vde.com |  | TECH | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| VDI | vdi.de |  | TECH | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| VDMA | vdma.org |  | TECH | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Weizenbaum-Institut | weizenbaum-institut.de |  | TECH | idw | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Works in Progress | worksinprogress.co | https://worksinprogress.co/rss.xml | TECH | hn | UK | ok |  | nicht aufgenommen: Essay-Magazin |
| ZHAW | zhaw.ch |  | TECH | idw | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |

### HEALTH (72 Kandidaten, 23 aufgenommen)

| Name | Domain | Feed | Vertikale | Herkunft | Land | Status | Lizenz | Entscheidung |
|---|---|---|---|---|---|---|---|---|
| apotheke adhoc | apotheke-adhoc.de | https://apotheke-adhoc.de/rss.xml | HEALTH | own | DE | ok |  | aufgenommen |
| BioPharma Dive | biopharmadive.com | https://www.biopharmadive.com/feeds/news/ | HEALTH | own | US | ok |  | aufgenommen |
| BioSpace | biospace.com | https://www.biospace.com/index.rss | HEALTH | own | US | ok |  | aufgenommen |
| CDC | cdc.gov | https://tools.cdc.gov/api/v2/resources/media/132608.rss | HEALTH | own | US | ok | Public Domain (US federal) | aufgenommen (fulltext, Public Domain (US federal)) |
| DDZ Diabetes-Zentrum | ddz.de | https://ddz.de/feed/ | HEALTH | idw | DE | ok |  | aufgenommen |
| Devicemed | devicemed.de | https://www.devicemed.de/rss/news.xml | HEALTH | own | DE | ok |  | aufgenommen |
| DZNE | dzne.de | https://www.dzne.de/index.php?id=1026&type=100 | HEALTH | own | DE | ok |  | aufgenommen |
| E-Health-Com | e-health-com.de | https://e-health-com.de/rss | HEALTH | own | DE | ok |  | aufgenommen |
| ECDC | ecdc.europa.eu | https://www.ecdc.europa.eu/en/taxonomy/term/323//feed | HEALTH | own | EU | ok | CC BY 4.0 | aufgenommen (fulltext, CC BY 4.0) |
| eLife | elifesciences.org | https://elifesciences.org/rss/recent.xml | HEALTH | own | UK | ok | CC BY 4.0 | aufgenommen (fulltext, CC BY 4.0) |
| European Biotechnology | european-biotechnology.com | https://european-biotechnology.com/feed/ | HEALTH | own | DE | ok |  | aufgenommen |
| FDA | fda.gov | https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml | HEALTH | own | US | ok | Public Domain (US federal) | aufgenommen (fulltext, Public Domain (US federal)) |
| Helmholtz Munich | helmholtz-munich.de | https://www.helmholtz-munich.de/feed.xml | HEALTH | own | DE | ok |  | aufgenommen |
| HIT Consultant | hitconsultant.net | https://hitconsultant.net/feed/ | HEALTH | own | US | ok |  | aufgenommen |
| Imaging Technology News | itnonline.com | https://itnonline.com/rss.xml | HEALTH | wikipedia | US | ok |  | aufgenommen |
| kma Online | kma-online.de | https://www.kma-online.de/dienste/feeds/aktuelles.xml | HEALTH | own | DE | ok |  | aufgenommen |
| Lifespan.io | lifespan.io | https://lifespan.io/feed/ | HEALTH | own | US | ok |  | aufgenommen |
| Longevity.Technology | longevity.technology | https://longevity.technology/feed/ | HEALTH | own | UK | ok |  | aufgenommen |
| Medical Design & Outsourcing | medicaldesignandoutsourcing.com | https://www.medicaldesignandoutsourcing.com/feed/ | HEALTH | own | US | ok |  | aufgenommen |
| Natural Products Insider | naturalproductsinsider.com | https://naturalproductsinsider.com/rss.xml | HEALTH | own | US | ok |  | aufgenommen |
| pharmaphorum | pharmaphorum.com | https://pharmaphorum.com/rss.xml | HEALTH | own | UK | ok |  | aufgenommen |
| PharmaTimes | pharmatimes.com | https://pharmatimes.com/feed/ | HEALTH | own | UK | ok |  | aufgenommen |
| Vitafoods Insights | vitafoodsinsights.com | https://vitafoodsinsights.com/rss.xml | HEALTH | own | UK | ok |  | aufgenommen |
| Apotheken Umschau | apotheken-umschau.de | https://www.apotheken-umschau.de/rss/topthemen.xml | HEALTH | wikipedia | DE | reserved |  | nicht aufgenommen: reserved (feed header tdm-reservation: 1) |
| BAG Bundesamt für Gesundheit | bag.admin.ch |  | HEALTH | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Becker's Hospital Review | beckershospitalreview.com | https://beckershospitalreview.com/feed/ | HEALTH | wikipedia | US | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| BfArM | bfarm.de |  | HEALTH | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Bibliomed Pflege | bibliomed.de | https://bibliomed.de/feed/ | HEALTH | wikipedia | DE | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2021-09-29) |
| BioTechniques | future-science.com |  | HEALTH | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BPI | bpi.de |  | HEALTH | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (22 URLs tried)) |
| BVMed | bvmed.de |  | HEALTH | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (33 URLs tried)) |
| Charité | charite.de | https://www.charite.de/service/veranstaltung?type=105 | HEALTH | own | DE | ok |  | nicht aufgenommen: Feed ist Stellen-/Veranstaltungsfeed |
| DAZ | deutsche-apotheker-zeitung.de | https://feeds.purplemanager.com/63cea2f6-fc14-445a-b7b3-4e7f2eafeff5/newsletter-news-neu | HEALTH | own | DE | reserved |  | nicht aufgenommen: reserved (header tdm-reservation: 1) |
| Diabetes Ratgeber | diabetes-ratgeber.net | https://www.apotheken-umschau.de/rss/topthemen.xml | HEALTH | wikipedia | DE | reserved |  | nicht aufgenommen: reserved (feed header tdm-reservation: 1) |
| Digital Health | digitalhealth.net |  | HEALTH | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| DKFZ | dkfz.de |  | HEALTH | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| EMA | ema.europa.eu | https://www.ema.europa.eu/en/rss/news.xml | HEALTH | own | EU | feed_error |  | nicht aufgenommen: feed_error (feed HTTP 404) |
| European Pharmaceutical Review | europeanpharmaceuticalreview.com |  | HEALTH | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Fit for Fun | fitforfun.de | https://www.fitforfun.de/rss | HEALTH | wikipedia | DE | ok |  | nicht aufgenommen: Consumer-Magazin ohne Trendwert |
| Fitt Insider | insider.fitt.co |  | HEALTH | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| GEN Genetic Engineering News | genengnews.com | https://www.genengnews.com/feed/ | HEALTH | own | US | reserved |  | nicht aufgenommen: reserved (tdmrep.json location='/') |
| Journal für die Apotheke | journalfuerdieapotheke.de |  | HEALTH | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (20 URLs tried)) |
| Labiotech | labiotech.eu |  | HEALTH | own | FR | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| LISAvienna | lisavienna.at |  | HEALTH | own | AT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| MassDevice | massdevice.com |  | HEALTH | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Max Delbrück Center | mdc-berlin.de |  | HEALTH | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| MD+DI | mddionline.com |  | HEALTH | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Medizin & Technik | medizin-und-technik.industrie.de |  | HEALTH | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| MedUni Wien | meduniwien.ac.at |  | HEALTH | own | AT | feed_error |  | nicht aufgenommen: feed_error (no feed found (22 URLs tried)) |
| MHH Hannover | mhh.de |  | HEALTH | idw | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| NICE | nice.org.uk |  | HEALTH | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| NIH | nih.gov | https://www.nih.gov/news-events/news-releases | HEALTH | own | US | blocked |  | nicht aufgenommen: blocked (feed HTTP 403 for the bot UA) |
| Nursing in Practice | nursinginpractice.com | https://www.nursinginpractice.com/feed/ | HEALTH | wikipedia | UK | ok |  | nicht aufgenommen: Pflege UK |
| Nutrition Insight | nutritioninsight.com | https://resource-cns.cnsmedia.com/rss/ninews.xml | HEALTH | own | NL | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| Paul-Ehrlich-Institut | pei.de | https://www.pei.de/SiteGlobals/Functions/RSSFeed/RSSGenerator_Aktuell.xml?nn=165890 | HEALTH | own | DE | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| Pharmakon | pharmakon.info |  | HEALTH | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Pharmazeutische Zeitung | pharmazeutische-zeitung.de |  | HEALTH | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Psychiatric Times | psychiatrictimes.com |  | HEALTH | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Psychologie Heute | psychologie-heute.de | https://www.psychologie-heute.de/feed.rss | HEALTH | wikipedia | DE | ok |  | nicht aufgenommen: Consumer-Magazin |
| Robert Koch-Institut | rki.de | https://www.rki.de/SiteGlobals/Functions/RSS/RSS-neue-Dokumente.xml | HEALTH | own | DE | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| StudyFinds | studyfinds.com | https://studyfinds.com/feed/ | HEALTH | hn | US | ok |  | nicht aufgenommen: Studien-Aggregator (umgeschriebene PR) |
| Swiss Biotech | swissbiotech.org |  | HEALTH | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Swiss Medtech | swiss-medtech.ch |  | HEALTH | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (25 URLs tried)) |
| Swissmedic | swissmedic.ch | http://fetchrss.com/rss/5fe092c0fd80be0c580365425fe0ba17754a0371247c2342.xml | HEALTH | own | CH | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| U.S. Pharmacist | uspharmacist.com |  | HEALTH | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| UMG Göttingen | umg.eu |  | HEALTH | idw | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Universitätsklinikum Bonn | ukbonn.de |  | HEALTH | idw | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Universitätsklinikum Heidelberg | klinikum.uni-heidelberg.de |  | HEALTH | idw | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Universitätsklinikum Würzburg | ukw.de |  | HEALTH | idw | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| vfa | vfa.de |  | HEALTH | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (25 URLs tried)) |
| Well+Good | wellandgood.com | https://www.theskimm.com/rss/feed.xml | HEALTH | own | US | ok |  | nicht aufgenommen: Consumer-Wellness |
| Ärzte Zeitung | aerztezeitung.de | https://aerztezeitung.de/news.rss | HEALTH | own | DE | reserved |  | nicht aufgenommen: reserved (tdmrep.json location='/') |

### BIZ (104 Kandidaten, 26 aufgenommen)

| Name | Domain | Feed | Vertikale | Herkunft | Land | Status | Lizenz | Entscheidung |
|---|---|---|---|---|---|---|---|---|
| BLS Latest | bls.gov | https://www.bls.gov/feed/bls_latest.rss | BIZ | own | US | ok | Public Domain (US federal) | aufgenommen (fulltext, Public Domain (US federal)) |
| Crunchbase News | news.crunchbase.com | https://news.crunchbase.com/feed/ | BIZ | own | US | ok |  | aufgenommen |
| Destatis | destatis.de | https://www.destatis.de/SiteGlobals/Functions/RSSFeed/DE/RSSNewsfeed/Aktuell.xml?nn=241288 | BIZ | own | DE | ok |  | aufgenommen |
| Deutsche Bundesbank | bundesbank.de | https://www.bundesbank.de/service/rss/en/633292/feed.rss | BIZ | own | DE | ok |  | aufgenommen |
| deutsche-startups.de | deutsche-startups.de | https://deutsche-startups.de/feed | BIZ | own | DE | ok |  | aufgenommen |
| Digiday | digiday.com | https://digiday.com/feed/ | BIZ | wikipedia | US | ok |  | aufgenommen |
| Digital Commerce 360 | digitalcommerce360.com | https://digitalcommerce360.com/feed | BIZ | own | US | ok |  | aufgenommen |
| E+Z Entwicklung und Zusammenarbeit | dandc.eu | https://dandc.eu/feed | BIZ | wikipedia | DE | ok |  | aufgenommen |
| EHI Retail Institute | ehi.org | https://www.ehi.org/feed/ | BIZ | own | DE | ok |  | aufgenommen |
| etailment | etailment.de | https://etailment.de/feed.xml | BIZ | own | DE | ok |  | aufgenommen |
| EU Commission Press Corner | ec.europa.eu | https://ec.europa.eu/commission/presscorner/api/rss?language=en | BIZ | own | EU | ok | CC BY 4.0 | aufgenommen (fulltext, CC BY 4.0) |
| Federal Reserve Press Releases | federalreserve.gov | https://www.federalreserve.gov/feeds/press_all.xml | BIZ | own | US | ok | Public Domain (US federal) | aufgenommen (fulltext, Public Domain (US federal)) |
| FTC Press Releases | ftc.gov | https://www.ftc.gov/feeds/press-release.xml | BIZ | own | US | ok | Public Domain (US federal) | aufgenommen (fulltext, Public Domain (US federal)) |
| GOV.UK News and communications | gov.uk | https://www.gov.uk/search/news-and-communications.atom | BIZ | own | UK | ok | OGL v3.0 | aufgenommen (fulltext, OGL v3.0) |
| HDE Handelsverband | einzelhandel.de | https://einzelhandel.de/?format=feed&amp;type=rss | BIZ | own | DE | ok |  | aufgenommen |
| IFH Köln | ifhkoeln.de | https://ifhkoeln.de/feed | BIZ | own | DE | ok |  | aufgenommen |
| IT Finanzmagazin | it-finanzmagazin.de | https://www.it-finanzmagazin.de/feed/ | BIZ | own | DE | ok |  | aufgenommen |
| manager magazin | manager-magazin.de | https://www.manager-magazin.de/news/index.rss | BIZ | own | DE | ok |  | aufgenommen |
| Modern Retail | modernretail.co | https://modernretail.co/feed | BIZ | own | US | ok |  | aufgenommen |
| Payment and Banking | paymentandbanking.com | https://paymentandbanking.com/payment/rss/ | BIZ | own | DE | ok |  | aufgenommen |
| Retail Gazette | retailgazette.co.uk | https://www.retailgazette.co.uk/feed/ | BIZ | own | UK | ok |  | aufgenommen |
| SEC Press Releases | sec.gov | https://www.sec.gov/news/pressreleases.rss | BIZ | own | US | ok | Public Domain (US federal) | aufgenommen (fulltext, Public Domain (US federal)) |
| Startbase | startbase.de | https://www.startbase.de/feed/ | BIZ | own | DE | ok |  | aufgenommen |
| Tech.eu | tech.eu | https://tech.eu/feed | BIZ | own | EU | ok |  | aufgenommen |
| Trending Topics | trendingtopics.eu | https://trendingtopics.eu/feed | BIZ | own | AT | ok |  | aufgenommen |
| WZB | wzb.eu | https://wzb.eu/rss.xml | BIZ | idw | DE | ok |  | aufgenommen |
| absatzwirtschaft | absatzwirtschaft.de | https://www.absatzwirtschaft.de/feed/ | BIZ | own | DE | ok |  | nicht aufgenommen: verify_feeds fehlgeschlagen (/feed/ leitet auf marken-award.de um) |
| AlphaGalileo | alphagalileo.org |  | BIZ | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (23 URLs tried)) |
| APA-OTS | ots.at |  | BIZ | own | AT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| aws Austria Wirtschaftsservice | aws.at |  | BIZ | own | AT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Bain | bain.com |  | BIZ | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Bank of Canada | bankofcanada.ca | https://www.bankofcanada.ca/feed/?content_type=sparks-at-bank-article&post_type[0]=post&post_type[1]=page | BIZ | hn | CA | ok |  | nicht aufgenommen: HN-Einzeltreffer |
| BCG | bcg.com |  | BIZ | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BDI | bdi.eu |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BFS Bundesamt für Statistik | bfs.admin.ch |  | BIZ | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| brand eins | brandeins.de |  | BIZ | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| BusinessWire | businesswire.com |  | BIZ | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Börse Online | boerse-online.de |  | BIZ | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Campaign | campaignlive.co.uk |  | BIZ | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Capital | capital.de | https://www.capital.de/feed/standard/ | BIZ | own | DE | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| Census Bureau | census.gov | https://www.census.gov/newsroom/press-releases.xml | BIZ | own | US | feed_error |  | nicht aufgenommen: feed_error (feed entries carry no link) |
| Chain Store Age | chainstoreage.com |  | BIZ | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Citywire | citywire.co.uk |  | BIZ | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Der Standard | derstandard.at | https://www.derstandard.at/rss | BIZ | own | AT | ok |  | nicht aufgenommen: Tageszeitung (breit) – Owner-Entscheid |
| Die Presse | diepresse.com | https://diepresse.com/rss | BIZ | own | AT | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| DIHK | dihk.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| DIW Berlin | diw.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| EIB | eib.org | https://www.eib.org/about/jobs/index.rss | BIZ | own | EU | ok |  | nicht aufgenommen: Feed ist Stellen-/Veranstaltungsfeed |
| EIT | eit.europa.eu | https://www.eit.europa.eu/rss | BIZ | own | EU | blocked |  | nicht aufgenommen: blocked (feed HTTP 403 for the bot UA) |
| Entrepreneur | entrepreneur.com | https://www.entrepreneur.com/latest.rss | BIZ | own | US | ok |  | nicht aufgenommen: US-Gründermagazin (breit) |
| EurekAlert | eurekalert.org |  | BIZ | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Eurostat | ec.europa.eu | https://ec.europa.eu/eurostat | BIZ | own | EU | feed_error |  | nicht aufgenommen: feed_error (no entries (SAXParseException)) |
| EZB | ecb.europa.eu |  | BIZ | own | EU | feed_error |  | nicht aufgenommen: feed_error (no feed found (34 URLs tried)) |
| FAZ | faz.net | https://www.faz.net/rss/aktuell/ | BIZ | own | DE | reserved |  | nicht aufgenommen: reserved (meta tdm-reservation: 1) |
| FFG | ffg.at | https://ffg.at/rss.xml | BIZ | own | AT | ok |  | nicht aufgenommen: verify_feeds fehlgeschlagen (Redirect-Schleife der Feed-URL) |
| Finance Forward | financefwd.com | https://financefwd.com/feed | BIZ | own | DE | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| FinTech Futures | fintechfutures.com |  | BIZ | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Format trend | format.at |  | BIZ | wikipedia | AT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Forrester Blogs | forrester.com | https://forrester.com/blogs | BIZ | own | US | feed_error |  | nicht aufgenommen: feed_error (no entries (SAXParseException)) |
| Fortune | fortune.com | https://fortune.com/feed | BIZ | own | US | ok |  | nicht aufgenommen: US-Wirtschaftsmagazin (breit, Paywall-Teaser) |
| Gartner Newsroom | gartner.com | https://gartner.com/en/newsroom | BIZ | own | US | blocked |  | nicht aufgenommen: blocked (feed HTTP 403 for the bot UA) |
| Gewinn | gewinn.com | https://gewinn.com/rss | BIZ | wikipedia | AT | ok |  | nicht aufgenommen: Consumer-Finanzmagazin |
| Handelszeitung | handelszeitung.ch |  | BIZ | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| IB.SH | ib-sh.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| IBB Berlin | ibb.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| ifo Institut | ifo.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| IfW Kiel | ifw-kiel.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| ILO | ilo.org | https://www.ilo.org/rss | BIZ | own | INT | blocked |  | nicht aufgenommen: blocked (feed HTTP 403 for the bot UA) |
| IMF | imf.org |  | BIZ | own | INT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Inc. | inc.com | https://inc.com/rss | BIZ | own | US | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| Innosuisse | innosuisse.admin.ch |  | BIZ | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Internet World | internetworld.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Investment Week | investmentweek.co.uk |  | BIZ | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| IW Köln | iwkoeln.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (22 URLs tried)) |
| KfW | kfw.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| L-Bank | l-bank.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| LfA Förderbank Bayern | lfa.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Marketing Week | marketingweek.co.uk |  | BIZ | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Mining Weekly | miningweekly.com |  | BIZ | wikipedia | ZA | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| MIT Sloan Management Review | sloanreview.mit.edu | http://feeds.feedburner.com/mitsmr | BIZ | own | US | ok |  | nicht aufgenommen: Dublette (Domain schon aktiv) |
| NordHandwerk | nord-handwerk.de | https://www.nord-handwerk.de/feed | BIZ | wikipedia | DE | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2019-07-08) |
| NRF | nrf.com |  | BIZ | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| NRW.BANK | nrwbank.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| NZZ | nzz.ch | https://www.nzz.ch/recent.rss | BIZ | own | CH | ok |  | nicht aufgenommen: Tageszeitung (breit) – Owner-Entscheid |
| OECD | oecd.org | https://www.oecd.org/en/about/news.rss | BIZ | own | INT | blocked |  | nicht aufgenommen: blocked (feed HTTP 403 for the bot UA) |
| Packaging Digest | packagingdigest.com |  | BIZ | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Packaging World | packworld.com |  | BIZ | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Practical Ecommerce | practicalecommerce.com | https://www.practicalecommerce.com/feed | BIZ | own | US | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| presseportal | presseportal.de | https://www.presseportal.de/rss/presseportal.rss2?langid=1 | BIZ | own | DE | ok |  | nicht aufgenommen: Presseverteiler-Index laut ToS-Regel: Owner-Entscheid (wie PR Newswire?) |
| Quartz | qz.com | https://qz.com/feed | BIZ | own | US | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| Startup-Verband | startupverband.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| startupticker | startupticker.ch |  | BIZ | own | CH | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Statistik Austria | statistik.at |  | BIZ | own | AT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Stiftung Warentest | test.de | https://www.test.de/rss/alles/ | BIZ | wikipedia | DE | ok |  | nicht aufgenommen: Verbrauchertests – Owner-Entscheid (Warentest-Signale?) |
| strategy+business | strategy-business.com |  | BIZ | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (22 URLs tried)) |
| Süddeutsche Zeitung | sueddeutsche.de | https://rss.sueddeutsche.de/rss/Topthemen | BIZ | own | DE | ok |  | nicht aufgenommen: Tageszeitung (breit) – Owner-Entscheid |
| The Paypers | thepaypers.com |  | BIZ | own | NL | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Universität Hohenheim | uni-hohenheim.de |  | BIZ | idw | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (25 URLs tried)) |
| Unternehmermagazin | unternehmermagazin.de | https://unternehmermedien.de/feed/ | BIZ | wikipedia | DE | ok |  | nicht aufgenommen: veraltet (jüngster Eintrag 2023-07-13) |
| W&V | wuv.de | https://www.wuv.de/feed/rss | BIZ | own | DE | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| WIBank | wibank.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| World Bank | worldbank.org | https://www.worldbank.org/en/news/all | BIZ | own | INT | feed_error |  | nicht aufgenommen: feed_error (HTML page, no feed found (21 URLs tried)) |
| World Economic Forum | weforum.org |  | BIZ | own | INT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| ZEW | zew.de |  | BIZ | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (22 URLs tried)) |

### LIFESTYLE (86 Kandidaten, 31 aufgenommen)

| Name | Domain | Feed | Vertikale | Herkunft | Land | Status | Lizenz | Entscheidung |
|---|---|---|---|---|---|---|---|---|
| 80.lv | 80.lv | https://80.lv/feed | LIFESTYLE | own | US | ok |  | aufgenommen |
| ARTnews | artnews.com | https://artnews.com/feed | LIFESTYLE | own | US | ok |  | aufgenommen |
| bildungsklick | bildungsklick.de | https://bildungsklick.de/feed.rss | LIFESTYLE | own | DE | ok |  | aufgenommen |
| Börsenblatt | boersenblatt.net | https://boersenblatt.net/feed | LIFESTYLE | own | DE | ok |  | aufgenommen |
| Deutscher Kulturrat | kulturrat.de | https://www.kulturrat.de/feed/ | LIFESTYLE | own | DE | ok |  | aufgenommen |
| DFG | dfg.de | https://www.dfg.de/service/rss/de/323556/feed.rss | LIFESTYLE | own | DE | ok |  | aufgenommen |
| Digital Music News | digitalmusicnews.com | https://www.digitalmusicnews.com/feed/ | LIFESTYLE | own | US | ok |  | aufgenommen |
| DOSB | dosb.de | https://www.dosb.de/aktuelles/rss/feed.xml | LIFESTYLE | own | DE | ok |  | aufgenommen |
| DWDL | dwdl.de | https://www.dwdl.de/rss/allethemen.xml | LIFESTYLE | own | DE | ok |  | aufgenommen |
| Game Developer | gamedeveloper.com | https://gamedeveloper.com/rss.xml | LIFESTYLE | own | US | ok |  | aufgenommen |
| game Verband | game.de | https://www.game.de/feed/ | LIFESTYLE | own | DE | ok |  | aufgenommen |
| GamesMarkt | gamesmarkt.de | https://www.gamesmarket.global/rss/ | LIFESTYLE | own | DE | ok |  | aufgenommen |
| GamesWirtschaft | gameswirtschaft.de | https://www.gameswirtschaft.de/feed/ | LIFESTYLE | own | DE | ok |  | aufgenommen |
| Global Voices | globalvoices.org | https://globalvoices.org/feed/ | LIFESTYLE | own | INT | ok | CC BY 3.0 | aufgenommen (fulltext, CC BY 3.0) |
| Hochschulforum Digitalisierung | hochschulforumdigitalisierung.de | https://hochschulforumdigitalisierung.de/feed/ | LIFESTYLE | own | DE | ok | CC BY-SA 4.0 | aufgenommen (fulltext, CC BY-SA 4.0) |
| HRK | hrk.de | https://www.hrk.de/rss-feed/rss.xml | LIFESTYLE | own | DE | ok |  | aufgenommen |
| Human Resources Manager | humanresourcesmanager.de | https://humanresourcesmanager.de/rss.xml | LIFESTYLE | own | DE | ok |  | aufgenommen |
| Hyperallergic | hyperallergic.com | https://hyperallergic.com/rss/ | LIFESTYLE | own | US | ok |  | aufgenommen |
| IAB | iab.de | https://iab.de/feed/ | LIFESTYLE | own | DE | ok |  | aufgenommen |
| Inside Higher Ed | insidehighered.com | https://www.insidehighered.com/rss.xml | LIFESTYLE | own | US | ok |  | aufgenommen |
| Monopol | monopol-magazin.de | https://www.monopol-magazin.de/rss.xml | LIFESTYLE | own | DE | ok |  | aufgenommen |
| Music Ally | musically.com | https://musically.com/feed/ | LIFESTYLE | own | UK | ok |  | aufgenommen |
| Musikwoche | musikwoche.de | https://musikwoche.de/feed | LIFESTYLE | own | DE | ok |  | aufgenommen |
| News4teachers | news4teachers.de | https://www.news4teachers.de/feed/ | LIFESTYLE | own | DE | ok |  | aufgenommen |
| Personalwirtschaft | personalwirtschaft.de | https://www.personalwirtschaft.de/feed/ | LIFESTYLE | own | DE | ok |  | aufgenommen |
| Social Media Today | socialmediatoday.com | https://www.socialmediatoday.com/feeds/news/ | LIFESTYLE | own | US | ok |  | aufgenommen |
| Sportico | sportico.com | https://www.sportico.com/feed/rss/ | LIFESTYLE | own | US | ok |  | aufgenommen |
| The Art Newspaper | theartnewspaper.com | https://www.theartnewspaper.com/rss.xml | LIFESTYLE | own | UK | ok |  | aufgenommen |
| touristik aktuell | touristik-aktuell.de | https://www.touristik-aktuell.de/feed/ | LIFESTYLE | own | DE | ok |  | aufgenommen |
| TTG Media | ttgmedia.com | https://ttgmedia.com/feed.xml | LIFESTYLE | own | UK | ok |  | aufgenommen |
| turi2 | turi2.de | https://www.turi2.de/feed/ | LIFESTYLE | own | DE | ok |  | aufgenommen |
| 11 Freunde | 11freunde.de | https://www.11freunde.de/aktuelles/index.rss | LIFESTYLE | wikipedia | DE | ok |  | nicht aufgenommen: Fanmagazin |
| Aeon | aeon.co | https://aeon.co/feed.rss | LIFESTYLE | hn | UK | ok |  | nicht aufgenommen: Essay-Magazin |
| Amusement Today | amusementtoday.com | https://amusementtoday.com/feed/ | LIFESTYLE | wikipedia | US | ok |  | nicht aufgenommen: Freizeitpark-Fachblatt |
| Artnet News | news.artnet.com | https://news.artnet.com/feed | LIFESTYLE | own | US | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| Billboard | billboard.com | https://billboard.com/feed | LIFESTYLE | own | US | ok |  | nicht aufgenommen: Charts/Consumer |
| Blickpunkt:Film | blickpunktfilm.de |  | LIFESTYLE | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| buchreport | buchreport.de |  | LIFESTYLE | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Cicero | cicero.de | https://cicero.de/rss.xml | LIFESTYLE | wikipedia | DE | ok |  | nicht aufgenommen: Politikmagazin, kein Vertikalen-Bezug |
| Cineuropa | cineuropa.org | https://cineuropa.org/rss | LIFESTYLE | wikipedia | EU | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| Creative COW | creativecow.net |  | LIFESTYLE | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| DAAD | daad.de |  | LIFESTYLE | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (23 URLs tried)) |
| Deadline | deadline.com | https://deadline.com/feed | LIFESTYLE | own | US | ok |  | nicht aufgenommen: Hollywood-Branchendienst (Variety-Nähe, Paywall-Teaser) |
| eLearning Industry | elearningindustry.com | https://feeds.feedburner.com/elearningindustry | LIFESTYLE | own | US | ok |  | nicht aufgenommen: Dublette (Domain schon aktiv) |
| Esports Insider | esportsinsider.com | https://esportsinsider.com/feed | LIFESTYLE | own | UK | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| Eurogamer | eurogamer.net | https://www.eurogamer.net/feed | LIFESTYLE | own | UK | ok |  | nicht aufgenommen: Consumer-Spielemagazin |
| Funworld IAAPA | iaapa.org | https://iaapa.org/rss.xml | LIFESTYLE | wikipedia | US | ok |  | nicht aufgenommen: Freizeitpark-Verband |
| fvw | fvw.de | https://www.fvw.de/news/feed/ | LIFESTYLE | own | DE | reserved |  | nicht aufgenommen: reserved (meta tdm-reservation: 1) |
| GameStar | gamestar.de | https://www.gamestar.de/news/rss/news.rss | LIFESTYLE | wikipedia | DE | ok |  | nicht aufgenommen: Consumer-Spielemagazin |
| Goethe-Institut | goethe.de |  | LIFESTYLE | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Haufe | haufe.de | https://www.haufe.de/xml/rss_129150.xml | LIFESTYLE | own | DE | ok |  | nicht aufgenommen: unklarer Themenfeed eines breiten Verlags |
| Hospitality Net | hospitalitynet.org | https://www.hospitalitynet.org/rss/news.xml | LIFESTYLE | own | NL | blocked |  | nicht aufgenommen: blocked (article HTTP 403 for the bot UA) |
| IGN | ign.com | https://de.ign.com/feed.xml | LIFESTYLE | hn | US | ok |  | nicht aufgenommen: Consumer-Spielemagazin |
| IndieWire | indiewire.com | https://www.indiewire.com/feed/rss/ | LIFESTYLE | wikipedia | US | reserved |  | nicht aufgenommen: reserved (meta robots: noai, noimageai) |
| Kindergarten heute | kindergarten-heute.de |  | LIFESTYLE | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Kotaku | kotaku.com | https://kotaku.com/feed | LIFESTYLE | own | US | ok |  | nicht aufgenommen: Consumer-Spielemagazin |
| kress | kress.de |  | LIFESTYLE | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Kulturmanagement Network | kulturmanagement.net |  | LIFESTYLE | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Kulturnews | kulturnews.de | https://kulturnews.de/feed | LIFESTYLE | wikipedia | DE | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| Library Journal | libraryjournal.com |  | LIFESTYLE | wikipedia | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Literary Hub | lithub.com | https://lithub.com/home-page-rigel-two-up-2/feed/ | LIFESTYLE | hn | US | ok |  | nicht aufgenommen: Literaturmagazin |
| M Menschen Machen Medien | mmm.verdi.de | https://mmm.verdi.de/feed/ | LIFESTYLE | wikipedia | DE | ok |  | nicht aufgenommen: Gewerkschaftsmagazin |
| Medium Magazin | mediummagazin.de |  | LIFESTYLE | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Meedia | meedia.de |  | LIFESTYLE | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Music Week | musicweek.com |  | LIFESTYLE | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Musikexpress | musikexpress.de | https://www.musikexpress.de/feed/ | LIFESTYLE | wikipedia | DE | ok |  | nicht aufgenommen: Consumer-Magazin |
| Nexus Mods | nexusmods.com |  | LIFESTYLE | hn | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Outdoor Magazin | outdoor-magazin.com | https://www.outdoor-magazin.com/rss/alle/ | LIFESTYLE | wikipedia | DE | ok |  | nicht aufgenommen: Consumer-Magazin |
| PC Games | pcgames.de | https://www.pcgames.de/feed.cfm?menu_alias=home/ | LIFESTYLE | wikipedia | DE | ok |  | nicht aufgenommen: Consumer-Spielemagazin |
| PhocusWire | phocuswire.com |  | LIFESTYLE | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Polygon | polygon.com | https://polygon.com/feed | LIFESTYLE | own | US | ok |  | nicht aufgenommen: Consumer-Spielemagazin |
| Press Gazette | pressgazette.co.uk |  | LIFESTYLE | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (23 URLs tried)) |
| Publishers Weekly | publishersweekly.com | https://www.publishersweekly.com/pw/feeds/recent/index.xml | LIFESTYLE | own | US | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
| Simple Flying | simpleflying.com | https://simpleflying.com/feed/ | LIFESTYLE | hn | US | ok |  | nicht aufgenommen: Consumer-Luftfahrt |
| Smithsonian Magazine | smithsonianmag.com |  | LIFESTYLE | hn | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| SPONSORs | sponsors.de |  | LIFESTYLE | own | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| SportsPro | sportspromedia.com |  | LIFESTYLE | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Stifterverband | stifterverband.org | https://stifterverband.org/rss.xml | LIFESTYLE | own | DE | ok | CC BY-SA 4.0 | nicht aufgenommen: veraltet (jüngster Eintrag 2025-03-02) |
| Tes | tes.com |  | LIFESTYLE | wikipedia | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| The Bookseller | thebookseller.com |  | LIFESTYLE | own | UK | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| The Red Bulletin | redbulletin.com |  | LIFESTYLE | wikipedia | AT | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Travel Weekly | travelweekly.com |  | LIFESTYLE | own | US | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Twice | twice.com | https://www.twice.com/feed | LIFESTYLE | wikipedia | US | ok |  | nicht aufgenommen: US-Consumer-Electronics-Handel |
| UNESCO | unesco.org | https://www.unesco.org/en/rss | LIFESTYLE | own | INT | blocked |  | nicht aufgenommen: blocked (feed HTTP 403 for the bot UA) |
| Working@office | workingoffice.de |  | LIFESTYLE | wikipedia | DE | feed_error |  | nicht aufgenommen: feed_error (no feed found (21 URLs tried)) |
| Übermedien | uebermedien.de | https://uebermedien.de/feed/ | LIFESTYLE | own | DE | blocked |  | nicht aufgenommen: blocked (robots.txt disallows the feed URL) |
