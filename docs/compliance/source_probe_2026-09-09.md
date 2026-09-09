# Compliance-Probe der Owner-Domainliste (2026-09-09, #97)

Fortsetzung von `source_domain_check_2026-09-09.md`. Dort waren von 181 Owner-Domains 147 der Pipeline unbekannt.
Geprobt wurden davon die **111 inhaltlich in Frage kommenden**: 102 Fachmedien/Tageszeitungen/Institutionen und
9 Wissenschaftsverlage/Repositorien. **Nicht geprobt** (bleiben per Quellenregel draußen): 23 Presseverteiler/
Syndikations-/Finanzportale, 12 Marktforschungs-Report-Shops, 1 Aggregator (trendhunter.com, Blockliste).

Werkzeug: `scripts/probe_source_compliance.py --file … --discovered-via owner-domainliste-2026-09-09`.
Je Domain: Feed-Autodiscovery, robots.txt für `CatandaryTrendsBot` (RFC 9309, `pipeline.article_fetcher.robots_allows`),
Bot-Status der jüngsten Artikelseite mit dem Produktions-UA, TDM-Signale (Header, Meta, `noai`, `tdmrep.json`),
Lizenzhinweise, Conditional-GET. Etikette: 1 Request/s/Host, 15 s Timeout, 8 Worker. **1.306 Requests, ~7 min**,
ein Lauf. Rohdaten (JSON) liegen im Scratchpad, nicht im Repo.

## Ergebnis

| Status | Domains | Bedeutung |
|---|---|---|
| ok | 57 | Feed valide, robots erlaubt Feed + Artikel, Artikel 200, kein TDM-Signal |
| feed_error | 47 | nicht verifizierbar — 45× kein Feed gefunden, 2× Feed valide aber Artikel-Ebene unbrauchbar |
| blocked | 7 | Bot-Sperre (403) oder robots-Verbot der Feed-URL |
| reserved | 0 | kein einziger maschinenlesbarer TDM-Vorbehalt in der Liste |

**Kein `fulltext: true` für irgendeinen Kandidaten.** Strukturiert erkannte offene Lizenz: keine. Vier reine
Text-Treffer ohne Lizenzwert (aquaculturemag „CC BY-NC-ND", eDairy News „public domain", iGrow News und
Innovation News Network „Creative Commons") — nach der WP3-Regel vom 04.09. zählt nur ein struktureller Beleg
(`link rel=license`, CC-URL, Feed-Element). Alle 57 laufen also im Titel-/Teaser-Betrieb.

Conditional GET: 51 der 57 ok-Feeds liefern ETag und/oder Last-Modified.

**Empfehlung: 40 aufnehmen, 17 nicht.** Die 17 fallen unter die redaktionellen Regeln vom 04.09.
(`source_candidates_2026-09-04.md`, Abschnitt „Redaktionelle Regeln"): 8× Regel 6 (Tageszeitungen mit breitem
Gesamtfeed), 4× Regel 4 (Autodiscovery-Fehltreffer), 2× Regel 3 (verwaist), 1× Regel 1 (Firmenblog),
1× Dublette, 1× keine Primärquelle. Je Vertikale neu: **FOOD 25, BIZ 8, ECO 5, TECH 2.**
Der Schwerpunkt der Owner-Liste ist eindeutig Food/Agrar/Dairy/Packaging — das trifft genau die Vertikale,
deren Anteil laut CLAUDE.md-Balance-Prinzip beobachtet wird (FOOD auf 6 % gefallen).

**Eingetragen am 2026-09-09: 39 der 40.** Farmers Review Africa fiel im Nachlauf mit `scripts.verify_feeds.verify_feed` durch — der Feed antwortete rund 25 Minuten nach der Probe mit **403**, und zwar sowohl dem Produktions-UA `CatandaryTrendsBot/1.0` als auch dem Reader-UA von `verify_feeds`; gleiche Behandlung wie FFG und absatzwirtschaft am 04.09. (ok geprobt, im Nachlauf entfernt). Die übrigen 39 sind mit `tdm_checked: "2026-09-09"`, `tdm_status: ok` und `discovered_via: owner-domainliste-2026-09-09` in `sources.yaml`; IFDC steht als Forschungseinrichtung in der `science`-Liste von FOOD, die anderen 38 in den `sources`-Listen. Aktive RSS-Quellen 474 → **513**. 39/39 `verify_feed` grün, 1.459 pytest grün.

## ok (57) — mit Empfehlung

| Domain | Feed-URL | Einträge | jüngster | Empfehlung |
|---|---|---|---|---|
| agro-media.fr | `https://www.agro-media.fr/feed` | 20 | 2026-09-09 | **aufnehmen** als „Agro Media“ (FOOD) |
| agronfoodprocessing.com | `https://agronfoodprocessing.com/feed/` | 10 | 2026-09-09 | **aufnehmen** als „AgronFood Processing“ (FOOD) |
| alimarket.es | `https://www.alimarket.es/media/rss/alimentacion.xml` | 1 | 2026-09-09 | **aufnehmen** als „Alimarket Alimentación“ (FOOD) |
| aquaculturemag.com | `https://aquaculturemag.com/feed/` | 10 | 2026-09-07 | **aufnehmen** als „Aquaculture Magazine“ (FOOD) |
| chaindrugreview.com | `https://chaindrugreview.com/latest/rss/` | 15 | 2026-09-09 | **aufnehmen** als „Chain Drug Review“ (BIZ) |
| chemicalprocessing.com | `https://www.chemicalprocessing.com/__rss/website-scheduled-content.xml?input=%7B%22sectionAlias%22%3A%22home%22%7D` | 25 | 2026-09-04 | **aufnehmen** als „Chemical Processing“ (ECO) |
| dairybusinessmea.com | `https://dairybusinessmea.com/feed/` | 10 | 2026-09-09 | **aufnehmen** als „Dairy Business MEA“ (FOOD) |
| en.edairynews.com | `https://en.edairynews.com/feed/` | 10 | 2026-09-09 | **aufnehmen** als „eDairy News“ (FOOD) |
| euobserver.com | `https://euobserver.com/feed/` | 20 | 2026-09-09 | **aufnehmen** als „EUobserver“ (BIZ) |
| farmersreviewafrica.com | `https://farmersreviewafrica.com/feed/` | 10 | 2026-09-09 | ~~aufnehmen~~ — **im Nachlauf verworfen**: `verify_feed` bekam 403 (beide UAs), ~25 min nach der Probe |
| fishfocus.co.uk | `https://fishfocus.co.uk/feed/` | 17 | 2026-09-09 | **aufnehmen** als „Fish Focus“ (FOOD) |
| fmi.org | `http://feeds.feedburner.com/FMI-News` | 25 | 2026-09-09 | **aufnehmen** als „FMI – The Food Industry Association“ (BIZ) |
| fnbnews.com | `https://fnbnews.com/xml/Top-NewsRSS.XML` | 6 | — | **aufnehmen** als „FnB News“ (FOOD) |
| foodaffairs.it | `https://www.foodaffairs.it/feed/` | 25 | 2026-09-09 | **aufnehmen** als „Food Affairs“ (FOOD) |
| foodbusinessmea.com | `https://www.foodbusinessmea.com/feed/` | 10 | 2026-09-09 | **aufnehmen** als „Food Business MEA“ (FOOD) |
| foodinfotech.com | `https://www.foodinfotech.com/feed/` | 10 | 2026-09-09 | **aufnehmen** als „FoodInfoTech“ (FOOD) |
| freshfruitportal.com | `https://www.freshfruitportal.com/feed/` | 10 | 2026-09-09 | **aufnehmen** als „FreshFruitPortal“ (FOOD) |
| freshplaza.com | `https://www.freshplaza.com/europe/rss.xml/` | 48 | 2026-09-09 | **aufnehmen** als „FreshPlaza“ (FOOD) |
| geneticliteracyproject.org | `https://geneticliteracyproject.org/feed/` | 19 | 2026-09-09 | **aufnehmen** als „Genetic Literacy Project“ (FOOD) |
| greentechlead.com | `https://greentechlead.com/feed` | 10 | 2026-09-09 | **aufnehmen** als „Greentech Lead“ (ECO) |
| grontsamhallsbyggande.se | `https://www.grontsamhallsbyggande.se/feed/` | 16 | 2026-09-09 | **aufnehmen** als „Grönt Samhällsbyggande“ (ECO) |
| hortidaily.com | `https://www.hortidaily.com/rss.xml/` | 28 | 2026-09-09 | **aufnehmen** als „HortiDaily“ (FOOD) |
| ifdc.org | `https://ifdc.org/feed/` | 10 | 2026-09-08 | **aufnehmen** als „IFDC“ (FOOD) |
| igrownews.com | `https://igrownews.com/feed/` | 10 | 2026-09-09 | **aufnehmen** als „iGrow News“ (FOOD) |
| innovationnewsnetwork.com | `https://www.innovationnewsnetwork.com/feed/` | 20 | 2026-09-09 | **aufnehmen** als „Innovation News Network“ (TECH) |
| itweb.co.za | `https://www.itweb.co.za/rss` | 29 | 2026-09-09 | **aufnehmen** als „ITWeb“ (TECH) |
| lantbruksnytt.se | `https://lantbruksnytt.se/feed/` | 20 | 2026-09-09 | **aufnehmen** als „Lantbruksnytt“ (FOOD) |
| mundoagropecuario.com | `https://mundoagropecuario.com/feed/` | 20 | 2026-09-09 | **aufnehmen** als „Mundo Agropecuario“ (FOOD) |
| newhope.com | `https://newhope.com/rss.xml` | 50 | 2026-09-09 | **aufnehmen** als „New Hope Network“ (FOOD) |
| paperindustryworld.com | `https://www.paperindustryworld.com/feed/` | 10 | 2026-09-04 | **aufnehmen** als „Paper Industry World“ (ECO) |
| perishablenews.com | `https://perishablenews.com/feed/` | 10 | 2026-09-09 | **aufnehmen** als „Perishable News“ (FOOD) |
| processingmagazine.com | `https://www.processingmagazine.com/__rss/website-scheduled-content.xml?input=%7B%22sectionAlias%22%3A%22home%22%7D` | 25 | 2026-09-08 | **aufnehmen** als „Processing Magazine“ (ECO) |
| publicsectorcatering.co.uk | `https://www.publicsectorcatering.co.uk/rss/costsectorcatering/rss.xml` | 10 | 2026-09-09 | **aufnehmen** als „Public Sector Catering“ (FOOD) |
| repositrak.com | `https://repositrak.com/feed/` | 10 | 2026-09-03 | **aufnehmen** als „ReposiTrak“ (BIZ) |
| retail.economictimes.indiatimes.com | `https://retail.economictimes.indiatimes.com/rss/topstories` | 10 | 2026-09-09 | **aufnehmen** als „ET Retail“ (BIZ) |
| retailcustomerexperience.com | `https://www.retailcustomerexperience.com/rss/` | 85 | 2026-09-09 | **aufnehmen** als „Retail Customer Experience“ (BIZ) |
| retailtechinnovationhub.com | `https://retailtechinnovationhub.com/home?format=rss` | 20 | 2026-09-09 | **aufnehmen** als „Retail Technology Innovation Hub“ (BIZ) |
| spnews.com | `https://spnews.com/api/rss/content.rss` | 30 | 2026-09-09 | **aufnehmen** als „Supermarket Perimeter“ (BIZ) |
| trademagazin.hu | `https://trademagazin.hu/hu/feed/` | 30 | 2026-09-09 | **aufnehmen** als „Trade Magazin“ (FOOD) |
| trademaster.ua | `https://trademaster.ua/rss.php?id=1` | 30 | — | **aufnehmen** als „TradeMaster“ (FOOD) |
| bangkokpost.com | `https://www.bangkokpost.com/rss/data/most-recent.xml` | 10 | 2026-09-09 | nicht aufnehmen: Regel 6 – Tageszeitung, breiter Gesamtfeed |
| bioengineer.org | `https://bioengineer.org/feed/` | 20 | 2026-09-09 | nicht aufnehmen: keine Primärquelle – republiziert fremde Pressemitteilungen |
| blogs.sw.siemens.com | `https://blogs.sw.siemens.com/news/rss` | 10 | 2026-06-03 | nicht aufnehmen: Regel 3 – Produktblog, jüngster Eintrag 2026-06-03; Siemens Press ist bereits Quelle |
| economictimes.indiatimes.com | `https://economictimes.indiatimes.com/rssfeedsdefault.cms` | 76 | 2026-09-09 | nicht aufnehmen: Regel 6 – Tageszeitung, breiter Gesamtfeed (der ET-Retail-Sektionsfeed ist empfohlen) |
| food-safety.com | `https://www.food-safety.com/rss/topic/158-food-safety-summit-press-releases` | 30 | 2026-05-20 | nicht aufnehmen: Regel 3/4 – Autodiscovery traf einen Messe-Presseinfo-Feed, jüngster Eintrag 2026-05-20 |
| indianexpress.com | `https://indianexpress.com/section/opinion/40-years-ago/feed/` | 200 | 2026-09-09 | nicht aufnehmen: Regel 4 – Autodiscovery traf /section/opinion/40-years-ago/feed/ |
| meatthefacts.eu | `https://meatthefacts.eu/feed` | 1 | 2019-09-05 | nicht aufnehmen: Regel 3 – verwaist (jüngster Eintrag 2019-09-05) |
| news.tuoitre.vn | `https://news.tuoitre.vn/home.rss` | 50 | — | nicht aufnehmen: Regel 6 – Tageszeitung, Gesamtfeed |
| nieuweoogst.nl | `https://www.nieuweoogst.nu/sector/algemeen-nieuws/multifunctionele-landbouw/feed.xml` | 20 | 2026-06-11 | nicht aufnehmen: Regel 4 – Autodiscovery traf die Unterrubrik „multifunctionele landbouw“, jüngster Eintrag 2026-06-11 |
| nutraingredients-asia.com | `https://www.nutraingredients.com/arc/outboundfeeds/rss/` | 20 | 2026-09-09 | nicht aufnehmen: Regel 4 – Autodiscovery traf den globalen NutraIngredients-Feed (bereits aktive Quelle) |
| thehindubusinessline.com | `https://www.thehindubusinessline.com/feeder/default.rss` | 60 | 2026-09-09 | nicht aufnehmen: Regel 6 – Wirtschaftstageszeitung, breiter Gesamtfeed |
| thesun.ng | `https://thesun.ng/feed` | 10 | 2026-09-09 | nicht aufnehmen: Regel 6 – Tageszeitung, breiter Gesamtfeed |
| vegconomist.de | `https://vegconomist.de/feed/` | 20 | 2026-09-09 | nicht aufnehmen: Dublette – vegconomist (.com) ist bereits aktive Quelle |
| vietnamnet.vn | `https://vietnamnet.vn/home.rss` | 1000 | 2026-09-09 | nicht aufnehmen: Regel 6 – Tageszeitung, Gesamtfeed (1.000 Einträge) |
| vietnamplus.vn | `https://www.vietnamplus.vn/rss/home.rss` | 50 | 2026-09-09 | nicht aufnehmen: Regel 6 – Nachrichtenagentur, Gesamtfeed |
| widya.ai | `https://widya.ai/feed/` | 10 | 2026-09-09 | nicht aufnehmen: Regel 1 – Firmenblog eines AI-Anbieters, kein Fachmedium |
| yle.fi | `https://yle.fi/rss/uutiset/paauutiset` | 10 | 2026-09-09 | nicht aufnehmen: Regel 6 – öffentlich-rechtliche Hauptnachrichten, Gesamtfeed |


## blocked (7)

Alle sieben liefern den Feed, sperren aber die Artikelseite (403 für den ehrlichen Bot-UA) bzw. den Feed-Pfad per
robots.txt. Nach der Linie vom 04.09. heißt das: nicht aufnehmen, Kandidaten für die WP4-Kontaktliste.

| Domain | Feed | Befund |
|---|---|---|
| biofuelsdigest.com | `https://biofuelsdigest.com/feed` | article HTTP 403 for the bot UA |
| doaj.org | `https://doaj.org/feed` | article HTTP 403 for the bot UA |
| mexiconewsdaily.com | `https://mexiconewsdaily.com/feed` | article HTTP 403 for the bot UA |
| packaginginsights.com | `https://resource-cns.cnsmedia.com/rss/pinews.xml` | robots.txt disallows the feed URL |
| plasticstoday.com | `https://plasticstoday.com/rss.xml` | article HTTP 403 for the bot UA |
| thehansindia.com | `https://www.thehansindia.com/google_feeds.xml` | article HTTP 403 for the bot UA |
| timesofmalta.com | `https://timesofmalta.com/?feed=rss2` | article HTTP 403 for the bot UA |

## feed_error (47)

**Kein Feed gefunden (45)** — Autodiscovery über Homepage, 21–40 Kandidatenpfade und verlinkte RSS-Übersichten:

- 21jingji.com
- agritechtomorrow.com
- allaboutfeed.net
- asiafoodjournal.com
- boerderij.nl
- business-standard.com
- cheesereporter.com
- dairyglobal.net
- eda.euromilk.org
- ekathimerini.com
- emsf-lisboa.pt
- farms.com
- feedandgrain.com
- foodandbeverageontario.ca
- foodonline.com
- foodtechbiz.com
- fponthenet.net
- global-agriculture.com
- goodricke.in
- ieeexplore.ieee.org
- industriaalimentaria.org
- industrieanzeiger.industrie.de
- ingredientsnetwork.com
- interzero.de
- jdsupra.com
- journalofdairyscience.org
- link.springer.com
- mdpi.com
- morganstanley.com
- orfonline.org
- packaging-labelling.com
- packagingrevolution.net
- petfoodindustry.com
- petfoodprocessing.net
- pigprogress.net
- procurementandsupply.com
- prozesstechnik.industrie.de
- pubs.rsc.org
- sciengine.com
- sdcexec.com
- smartpackagingeurope.com
- springer.com
- supplychaindigital.com
- textilevaluechain.in
- vakbladvoedingsindustrie.nl

Darunter sieben der neun Wissenschaftsverlage/Repositorien der Liste (`mdpi.com`, `springer.com`,
`link.springer.com`, `pubs.rsc.org`, `ieeexplore.ieee.org`, `journalofdairyscience.org`, `sciengine.com`;
DOAJ ist `blocked`, bioengineer.org `ok`) — sie bieten pro Journal
Feeds an, nicht auf Domain-Ebene; die TDM-Frage stellt sich damit gar nicht erst. Bei Springer und MDPI wäre
ohnehin mit `tdmrep.json` zu rechnen (wie bei den 22 Verlagen am 04.09.). Ebenfalls hier: `industrie.de`-
Subdomains (Industrieanzeiger, Prozesstechnik) — die Wurzeldomain `industrie.de` war am 04.09. mit Status `ok`
geprüft, die Subdomains haben keinen eigenen Feed.

**Feed valide, Artikel-Ebene unbrauchbar (2):**

| Domain | Feed | Befund |
|---|---|---|
| dairybusiness.com | `https://dairybusiness.com/feed` | 10 Einträge, tagesaktuell; die Artikel-Links im Feed sind fehlerhaft (307-Redirect, URL abgeschnitten: `…/ollege-awarded-usda-grant-…`). Erneut prüfen, wenn der Feed repariert ist. |
| thepoultrysite.com | `https://www.thepoultrysite.com/all.rss` | 500 Einträge, tagesaktuell, aber **die Einträge tragen kein `<link>`** — ohne Quell-URL kein Backlink und damit keine verwendbare Quelle. |

## Offene Punkte

- Aufnehmen der 40 empfohlenen Quellen in `sources.yaml` (mit `tdm_checked: "2026-09-09"`, `tdm_status: ok`,
  `discovered_via: owner-domainliste-2026-09-09`) — Owner-Freigabe steht aus.
- Regel-6-Gruppe (8 Tageszeitungen/Agenturen: Bangkok Post, Business Line, Economic Times, The Sun NG,
  VietnamNet, VietnamPlus, Tuoi Tre, Yle): dieselbe offene Frage wie am 04.09. bei Süddeutsche/NZZ/Standard und
  Nikkei Asia/Japan Times/Korea Herald — breite Gesamtfeeds ohne Fachsektion. Owner-Entscheid.
- `packaginginsights.com`: robots.txt sperrt nur die Feed-URL, die Artikelseiten sind erlaubt — dieselbe offene
  Owner-Frage wie bei den 17 Quellen vom 04.09. (gilt robots.txt für das Abonnieren eines angebotenen Feeds?).
