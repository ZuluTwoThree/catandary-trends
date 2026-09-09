# Domain-Abgleich Owner-Liste vs. Quellen (2026-09-09)

181 Domains aus einer vom Owner per Foto übermittelten Liste (Textdatei, 182 Zeilen, `foodprocessing.com.au` doppelt),
abgeglichen gegen `sources.yaml` (Feed-Hosts, Subdomain-tolerant), die Tabelle `sources` der Live-DB und die
Prüfprotokolle vom 04.09. (`source_candidates`, `source_probe`, `source_triage`). Rohliste: Fotos IMG_7920–7923.

| Status | Domains |
|---|---|
| nicht enthalten, nie geprüft | 147 |
| Quelle (aktiv) | 20 |
| geprüft 04.09., nicht aufgenommen | 10 |
| Quelle (deaktiviert) | 2 |
| Quelle (nur DB) | 1 |
| abgedeckt | 1 |

Von den 147 nie geprüften Domains sind nach Typ (Zuordnung nach Augenschein, nicht geprobt):

- Fachmedien / Tageszeitungen / Institutionen (Kandidaten für die Probe): 102
- Presseverteiler / Syndikation / Finanzportale (keine Primärquelle): 23
- Marktforschungs-Report-Shops (Pressemitteilungen zu Bezahlreports): 12
- Wissenschaftsverlage / Repositorien: 9
- Aggregator (Blockliste): 1

**Ausgeführt am 2026-09-09:** die 111 inhaltlich in Frage kommenden Kandidaten (102 Fachmedien + 9 Wissenschaftsverlage)
sind durch `scripts/probe_source_compliance.py` gelaufen — 57 `ok`, 47 `feed_error`, 7 `blocked`, 0 `reserved`;
Empfehlung 40 aufnehmen. Ergebnis je Domain: `docs/compliance/source_probe_2026-09-09.md`.
Presseverteiler/Report-Shops/Aggregatoren bleiben per Regel draußen und wurden nicht geprobt.

## Vollständige Tabelle

| Domain | Status | Detail | Typ |
|---|---|---|---|
| 21jingji.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| agritechtomorrow.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| agro-media.fr | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| agronfoodprocessing.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| alimarket.es | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| allaboutfeed.net | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| alphagalileo.org | geprüft 04.09., nicht aufgenommen | candidates: feed_error | Wissenschaftsverlage / Repositorien |
| aquaculturemag.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| asiafoodjournal.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| au.finance.yahoo.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| bakeryandsnacks.com | Quelle (aktiv) | Bakery and Snacks [FOOD, tdm=ok, fulltext=nein] | Fachmedien / Tageszeitungen / Institutionen |
| bangkokpost.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| bioengineer.org | nicht enthalten, nie geprüft |  | Wissenschaftsverlage / Repositorien |
| biofuelsdigest.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| blogs.sw.siemens.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| boerderij.nl | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| boursier.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| briefingwire.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| business-standard.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| businesswire.com | geprüft 04.09., nicht aufgenommen | triage: blocked; candidates: feed_error | Fachmedien / Tageszeitungen / Institutionen |
| carbonherald.com | Quelle (aktiv) | Carbon Herald [ECO, tdm=ok, fulltext=ja] | Fachmedien / Tageszeitungen / Institutionen |
| cell.com | Quelle (deaktiviert) | One Earth [ECO, tdm=reserved, fulltext=nein, inaktiv]; Matter (Cell Press) [DESIGN, tdm=reserved, fulltext=nein, inaktiv] | Wissenschaftsverlage / Repositorien |
| chaindrugreview.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| cheesereporter.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| chemicalprocessing.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| compuserve.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| cordis.europa.eu | Quelle (nur DB) | CORDIS EU Research Projects (SME Participations) [CROSS, active=True] | Wissenschaftsverlage / Repositorien |
| dairybusiness.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| dairybusinessmea.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| dairyglobal.net | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| dairyreporter.com | Quelle (aktiv) | DairyReporter [FOOD, tdm=ok, fulltext=ja] | Fachmedien / Tageszeitungen / Institutionen |
| databridgemarketresearch.com | nicht enthalten, nie geprüft |  | Marktforschungs-Report-Shops |
| doaj.org | nicht enthalten, nie geprüft |  | Wissenschaftsverlage / Repositorien |
| economictimes.indiatimes.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| eda.euromilk.org | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| edie.net | Quelle (aktiv) | edie [ECO, tdm=ok, fulltext=nein] | Fachmedien / Tageszeitungen / Institutionen |
| einpresswire.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| ekathimerini.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| emsf-lisboa.pt | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| en.edairynews.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| essfeed.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| euobserver.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| express-press-release.net | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| farmersreviewafrica.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| farms.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| feedandgrain.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| fei-online.com | Quelle (aktiv) | Food Engineering & Ingredients [FOOD, tdm=ok, fulltext=nein] | Fachmedien / Tageszeitungen / Institutionen |
| fibre2fashion.com | geprüft 04.09., nicht aufgenommen | candidates: feed_error | Fachmedien / Tageszeitungen / Institutionen |
| finanzen.net | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| firmenpresse.de | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| fishfocus.co.uk | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| fmi.org | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| fnbnews.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| food-safety.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| foodaffairs.it | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| foodandbeverageontario.ca | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| foodbev.com | Quelle (aktiv) | FoodBev Media [FOOD, tdm=ok, fulltext=nein] | Fachmedien / Tageszeitungen / Institutionen |
| foodbusinessmea.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| foodbusinessnews.net | geprüft 04.09., nicht aufgenommen | candidates: feed_error | Fachmedien / Tageszeitungen / Institutionen |
| foodinfotech.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| foodingredientsfirst.com | geprüft 04.09., nicht aufgenommen | candidates: blocked | Fachmedien / Tageszeitungen / Institutionen |
| foodmanufacture.co.uk | Quelle (aktiv) | Food Manufacture [FOOD, tdm=ok, fulltext=ja] | Fachmedien / Tageszeitungen / Institutionen |
| foodnavigator.com | Quelle (aktiv) | FoodNavigator [FOOD, tdm=ok, fulltext=ja] | Fachmedien / Tageszeitungen / Institutionen |
| foodnavigator-asia.com | Quelle (aktiv) | Food Navigator Asia [FOOD, tdm=ok, fulltext=ja] | Fachmedien / Tageszeitungen / Institutionen |
| foodnavigator-usa.com | Quelle (aktiv) | Food Navigator USA [FOOD, tdm=ok, fulltext=ja] | Fachmedien / Tageszeitungen / Institutionen |
| foodonline.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| foodprocessing.com.au | geprüft 04.09., nicht aufgenommen | candidates: ok | Fachmedien / Tageszeitungen / Institutionen |
| foodtank.com | Quelle (aktiv) | Food Tank [FOOD, tdm=ok, fulltext=nein] | Fachmedien / Tageszeitungen / Institutionen |
| foodtechbiz.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| fponthenet.net | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| fr.news.yahoo.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| freshfruitportal.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| freshplaza.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| frontiersin.org | Quelle (aktiv) | Frontiers in Nutrition [FOOD, tdm=ok, fulltext=ja]; Frontiers in Sustainable Food Systems [FOOD, tdm=ok, fulltext=ja]; Frontiers in Materials [TECH, tdm=ok, fulltext=ja]; Frontiers in Bioengineering and Biotechnology [HEALTH, tdm=ok, fulltext=ja]; Frontiers in Energy Research [ECO, tdm=ok, fulltext=ja] | Wissenschaftsverlage / Repositorien |
| futuremarketinsights.com | nicht enthalten, nie geprüft |  | Marktforschungs-Report-Shops |
| geneticliteracyproject.org | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| giiresearch.com | nicht enthalten, nie geprüft |  | Marktforschungs-Report-Shops |
| gminsights.com | nicht enthalten, nie geprüft |  | Marktforschungs-Report-Shops |
| globenewswire.com | Quelle (aktiv) | GlobeNewswire [Presseverteiler, tdm=ok, fulltext=ja] | Fachmedien / Tageszeitungen / Institutionen |
| global-agriculture.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| goodricke.in | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| greenqueen.com.hk | Quelle (aktiv) | Green Queen [FOOD, tdm=ok, fulltext=ja] | Fachmedien / Tageszeitungen / Institutionen |
| greentechlead.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| grontsamhallsbyggande.se | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| hortidaily.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| hongkongnews.net | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| ifdc.org | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| igrownews.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| ieeexplore.ieee.org | nicht enthalten, nie geprüft |  | Wissenschaftsverlage / Repositorien |
| indianexpress.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| industriaalimentaria.org | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| industrie.de | geprüft 04.09., nicht aufgenommen | candidates: ok | Fachmedien / Tageszeitungen / Institutionen |
| industrieanzeiger.industrie.de | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| ingredientsnetwork.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| innovationnewsnetwork.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| innovationsfood.com | Quelle (aktiv) | Innovations in Food Technology [FOOD, tdm=ok, fulltext=nein] | Fachmedien / Tageszeitungen / Institutionen |
| interzero.de | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| itweb.co.za | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| jdsupra.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| journalofdairyscience.org | nicht enthalten, nie geprüft |  | Wissenschaftsverlage / Repositorien |
| lakeshoreadvance.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| lantbruksnytt.se | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| leadertelegram.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| lifepr.de | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| link.springer.com | nicht enthalten, nie geprüft |  | Wissenschaftsverlage / Repositorien |
| lucidityinsights.com | nicht enthalten, nie geprüft |  | Marktforschungs-Report-Shops |
| marketpublishers.com | nicht enthalten, nie geprüft |  | Marktforschungs-Report-Shops |
| marketscreener.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| mdpi.com | nicht enthalten, nie geprüft |  | Wissenschaftsverlage / Repositorien |
| meatthefacts.eu | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| menafn.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| mexiconewsdaily.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| miragenews.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| morganstanley.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| mundoagropecuario.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| nature.com | Quelle (deaktiviert) | Nature Food [FOOD, tdm=reserved, fulltext=nein, inaktiv]; Nature Biotechnology [FOOD, tdm=reserved, fulltext=nein, inaktiv]; Nature Machine Intelligence [TECH, tdm=reserved, fulltext=nein, inaktiv]; Nature Electronics [TECH, tdm=reserved, fulltext=nein, inaktiv]; Nature Medicine [HEALTH, tdm=reserved, fulltext=nein, inaktiv]; Nature Neuroscience [HEALTH, tdm=reserved, fulltext=nein, inaktiv]; Nature Aging [HEALTH, tdm=reserved, fulltext=nein, inaktiv]; Nature Sustainability [ECO, tdm=reserved, fulltext=nein, inaktiv]; Nature Climate Change [ECO, tdm=reserved, fulltext=nein, inaktiv]; Nature Energy [ECO, tdm=reserved, fulltext=nein, inaktiv]; Nature Reviews Materials [DESIGN, tdm=reserved, fulltext=nein, inaktiv]; Nature Materials [DESIGN, tdm=reserved, fulltext=nein, inaktiv]; Nature Human Behaviour [LIFESTYLE, tdm=reserved, fulltext=nein, inaktiv]; Nature (main) [Presseverteiler, tdm=reserved, fulltext=nein, inaktiv] | Wissenschaftsverlage / Repositorien |
| news.tuoitre.vn | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| newhope.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| nielseniq.com | nicht enthalten, nie geprüft |  | Marktforschungs-Report-Shops |
| nieuweoogst.nl | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| nutritioninsight.com | geprüft 04.09., nicht aufgenommen | candidates: blocked | Fachmedien / Tageszeitungen / Institutionen |
| nutraingredients-asia.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| oecd.org | geprüft 04.09., nicht aufgenommen | candidates: blocked | Fachmedien / Tageszeitungen / Institutionen |
| orfonline.org | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| packaging-labelling.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| packagingeurope.com | Quelle (aktiv) | Packaging Europe [ECO, tdm=ok, fulltext=nein] | Fachmedien / Tageszeitungen / Institutionen |
| packaginginsights.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| packagingrevolution.net | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| paperindustryworld.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| penize.cz | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| perishablenews.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| petfoodindustry.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| petfoodprocessing.net | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| pigprogress.net | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| plantbasednews.org | Quelle (aktiv) | Plant Based News [FOOD, tdm=ok, fulltext=ja] | Fachmedien / Tageszeitungen / Institutionen |
| plasticstoday.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| preparedfoods.com | Quelle (aktiv) | Prepared Foods [FOOD, tdm=ok, fulltext=nein] | Fachmedien / Tageszeitungen / Institutionen |
| prnewswire.co.uk | abgedeckt | PR Newswire (prnewswire.com) ist Presseverteiler-Quelle; .co.uk = UK-Ausgabe desselben Wires | Presseverteiler / Syndikation / Finanzportale |
| processingmagazine.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| procurementandsupply.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| prozesstechnik.industrie.de | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| pubs.rsc.org | nicht enthalten, nie geprüft |  | Wissenschaftsverlage / Repositorien |
| publicsectorcatering.co.uk | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| researchandmarkets.com | nicht enthalten, nie geprüft |  | Marktforschungs-Report-Shops |
| repositrak.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| retail.economictimes.indiatimes.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| retailcustomerexperience.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| retailtechinnovationhub.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| sciengine.com | nicht enthalten, nie geprüft |  | Wissenschaftsverlage / Repositorien |
| sdcexec.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| sharesmagazine.co.uk | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| smartbrief.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| smartpackagingeurope.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| spnews.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| springer.com | nicht enthalten, nie geprüft |  | Wissenschaftsverlage / Repositorien |
| supplychaindigital.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| supplychaindive.com | Quelle (aktiv) | Supply Chain Dive [BIZ, tdm=ok, fulltext=ja] | Fachmedien / Tageszeitungen / Institutionen |
| supplysidefbj.com | geprüft 04.09., nicht aufgenommen | candidates: blocked | Fachmedien / Tageszeitungen / Institutionen |
| techsci.com | nicht enthalten, nie geprüft |  | Marktforschungs-Report-Shops |
| textilevaluechain.in | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| thehindubusinessline.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| thehansindia.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| theinsightpartners.com | nicht enthalten, nie geprüft |  | Marktforschungs-Report-Shops |
| thepoultrysite.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| thestpetersburgnews.net | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| thesun.ng | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| timesofmalta.com | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| trademagazin.hu | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| trademaster.ua | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| trendhunter.com | nicht enthalten, nie geprüft |  | Aggregator |
| vakbladvoedingsindustrie.nl | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| valuespectrum.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
| vegconomist.com | Quelle (aktiv) | vegconomist [FOOD, tdm=ok, fulltext=ja] | Fachmedien / Tageszeitungen / Institutionen |
| vegconomist.de | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| verifiedmarketresearch.com | nicht enthalten, nie geprüft |  | Marktforschungs-Report-Shops |
| vietnamnet.vn | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| vietnamplus.vn | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| widya.ai | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| worldbiomarketinsights.com | nicht enthalten, nie geprüft |  | Marktforschungs-Report-Shops |
| yle.fi | nicht enthalten, nie geprüft |  | Fachmedien / Tageszeitungen / Institutionen |
| zeebiz.com | nicht enthalten, nie geprüft |  | Presseverteiler / Syndikation / Finanzportale |
