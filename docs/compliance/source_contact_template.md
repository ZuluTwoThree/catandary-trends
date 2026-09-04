# Kontaktvorlage Quellen-Freischaltung (#97 WP4)

Stand: 2026-09-04. Absender für alle Quellen-Anfragen ist **sources@catandary.de**
(Owner-Festlegung 03.09.2026); Versand und Registrierungen erfolgen durch den
Owner. Diese Datei enthält nur Vorlagen und die abgelesene Kontaktliste —
**es wurde nichts versendet.**

Der Crawler meldet sich als
`CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology; trends@catandary.de)`
(`pipeline/feed_poller.py`, `pipeline/article_fetcher.py`), respektiert
robots.txt (RFC 9309) und maschinenlesbare TDM-Vorbehalte (§44b Abs. 3 UrhG),
holt höchstens einen Artikel pro Sekunde und Host, löscht Volltexte nach 14
Tagen und verlinkt jede Meldung auf die Quelle. Details öffentlich unter
`/trends/tdm-policy` und `/trends/methodology`.

---

## Vorlage DE — Bitte um Freischaltung des Bot-UA (Bot-Sperre 403/429)

**Betreff:** Bitte um Freischaltung von CatandaryTrendsBot für {QUELLE}

Sehr geehrte Damen und Herren,

wir betreiben unter catandary.de/trends einen redaktionellen Trend-Dienst, der
Fachmeldungen aus RSS-Feeds auswertet und daraus eigenständige, kurze
Einordnungen veröffentlicht — jede mit Quellennennung und Link auf den
Originalbeitrag bei {QUELLE}. Wir abonnieren Ihren öffentlich angebotenen
RSS-Feed {FEED_URL}.

Unser Crawler meldet sich ehrlich als
`CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology; trends@catandary.de)`.
Derzeit beantwortet Ihr Server Anfragen dieses User-Agents mit {STATUS}
({FEED_ODER_ARTIKEL}). Wir möchten Ihre Inhalte nicht gegen Ihren Willen
abrufen und bitten daher um eine der folgenden Optionen:

1. Freischaltung des User-Agents `CatandaryTrendsBot` (Feed und Artikelseiten),
   oder
2. Freischaltung nur des Feeds, wenn Sie keinen Artikelabruf wünschen — wir
   verarbeiten dann ausschließlich Titel und Teaser aus dem Feed.

Unsere Regeln: höchstens eine Anfrage pro Sekunde und Host, robots.txt und
TDM-Vorbehalte (TDMRep, `noai`, `tdmrep.json`) werden maschinell beachtet,
Volltexte werden nach 14 Tagen gelöscht, es entstehen keine Kopien Ihrer
Artikel — nur eigenständige Kurztexte mit Backlink. Unsere Richtlinie:
https://catandary.de/trends/tdm-policy

Sollten Sie den Abruf grundsätzlich nicht wünschen, genügt eine kurze Antwort;
wir deaktivieren die Quelle dann.

Mit freundlichen Grüßen
{NAME}
Catandary — sources@catandary.de

---

## Vorlage DE — Bitte um TDM-Lizenz (maschinenlesbarer Vorbehalt)

**Betreff:** Anfrage Text-und-Data-Mining-Lizenz für {QUELLE}

Sehr geehrte Damen und Herren,

Ihre Artikelseiten tragen einen maschinenlesbaren Nutzungsvorbehalt
({SIGNAL}, §44b Abs. 3 UrhG). Wir respektieren diesen Vorbehalt und speichern
deshalb keine Volltexte von {QUELLE}; verarbeitet werden nur Titel und Teaser
aus Ihrem öffentlich angebotenen RSS-Feed {FEED_URL}.

Für unseren redaktionellen Trend-Dienst catandary.de/trends (eigenständige
Kurzeinordnungen, immer mit Quellennennung und Link auf Ihren Beitrag) würden
wir Artikeltexte gern für 14 Tage zur Analyse vorhalten. Wir bitten um
Auskunft, ob Sie dafür eine Lizenz einräumen — kostenfrei gegen Backlink oder
zu Ihren Konditionen — und wie eine solche Vereinbarung aussehen könnte.

Technische Eckdaten: User-Agent
`CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology; trends@catandary.de)`,
höchstens eine Anfrage pro Sekunde und Host, robots.txt-Treue, Löschung nach
14 Tagen, keine Weitergabe der Texte. Richtlinie:
https://catandary.de/trends/tdm-policy

Mit freundlichen Grüßen
{NAME}
Catandary — sources@catandary.de

---

## Template EN — Request to allow the bot user agent (403/429 block)

**Subject:** Request to allow CatandaryTrendsBot for {SOURCE}

Dear {SOURCE} team,

We run an editorial trend service at catandary.de/trends that reads trade-press
RSS feeds and publishes short, independently written assessments — each one
credits the source and links back to the original article on {SOURCE}. We
subscribe to your publicly offered RSS feed {FEED_URL}.

Our crawler identifies itself honestly as
`CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology; trends@catandary.de)`.
Your server currently answers this user agent with {STATUS} ({FEED_OR_ARTICLE}).
We do not want to access your content against your wishes and would therefore
appreciate one of the following:

1. allow-listing the user agent `CatandaryTrendsBot` (feed and article pages), or
2. allow-listing the feed only, if you prefer no article fetches — we then
   process nothing but the titles and teasers you publish in the feed.

Our rules: at most one request per second per host, robots.txt and
machine-readable TDM reservations (TDMRep, `noai`, `tdmrep.json`) are honoured
automatically, full texts are deleted after 14 days, and nothing is copied —
only original short write-ups with a backlink. Policy:
https://catandary.de/trends/tdm-policy

If you would rather not be accessed at all, a one-line reply is enough and we
will deactivate the source.

Kind regards
{NAME}
Catandary — sources@catandary.de

---

## Template EN — Request for a text-and-data-mining licence (machine-readable reservation)

**Subject:** Text and data mining licence enquiry for {SOURCE}

Dear {SOURCE} team,

Your article pages carry a machine-readable rights reservation ({SIGNAL};
Art. 4 DSM Directive / §44b German Copyright Act). We honour it and therefore
store no full text from {SOURCE}; we only process titles and teasers from your
publicly offered RSS feed {FEED_URL}.

For our editorial trend service catandary.de/trends (independent short
assessments, always credited and linked to your article) we would like to hold
article text for analysis for 14 days. Could you let us know whether you grant
such a licence — free of charge against a backlink, or on your terms — and
what an agreement would look like?

Technical details: user agent
`CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology; trends@catandary.de)`,
at most one request per second per host, robots.txt compliance, deletion after
14 days, no redistribution of the text. Policy:
https://catandary.de/trends/tdm-policy

Kind regards
{NAME}
Catandary — sources@catandary.de

---

## Kontaktliste (nur abgelesen — nichts gesendet)

Grundlage: `docs/compliance/source_probe_2026-09-04.md` (Erstlauf). Die
Kontaktseiten der meisten dieser Verlage beantworten auch den Abruf durch das
Lesewerkzeug mit 403 — deshalb steht bei diesen Quellen der Kontaktweg so, wie
er in den Suchtreffern der Website-eigenen Kontakt-/Impressumsseiten sichtbar
ist (abgelesen am 04.09.2026), plus die URL der Kontaktseite zum manuellen
Gegenlesen. Zwei Adressen (Fierce, Nutritional Outlook) sind nur als Formular
auffindbar.

### A. Feed selbst gesperrt (5) — Vorlage „Bot-UA"

| Quelle | Feed-Status | Kontaktweg (Website) | Kontaktseite |
|---|---|---|---|
| Business of Fashion | 403 | support@businessoffashion.com (Shop-/Support-Seite); Kontaktformular | https://www.businessoffashion.com/contact-us/ (403 für Bots) |
| EE Times (AspenCore) | 403 | Managing Editor stefani.munoz@aspencore.com; Publisher cyrus.krohn@arrow.com; Formular https://aspencore.com/contact/ | https://www.eetimes.com/about-us/ |
| Endpoints News | 403 | help@endpointsnews.com (Subscriptions), corrections@endpointsnews.com (Redaktion) | https://endpoints.news/contact/ (403 für Bots) |
| Variety (Penske Media) | 403 (TollBit-Gateway `tollbit.variety.com`, HTTP 402) | Lizenzen/Reprints über Wright's Media: https://info.wrightsmedia.com/licensing-reprints-penske-media; PMC-Kontaktseite | https://variety.com/static-pages/contact-us/ |
| VentureBeat | 429 | tips@venturebeat.com (Redaktion), sales@venturebeat.com | https://venturebeat.com/contact/ |

### B. Artikelseite 403 für den Bot-UA (22 Feeds, 16 Häuser) — Vorlage „Bot-UA"

| Quelle (Feeds) | Kontaktweg (Website) | Kontaktseite |
|---|---|---|
| New York Times — Technology, Health, Climate, Business, Science (5) | Lizenz-/Permissions-Portal https://nytimes.wrightsmedia.com/ (Formular); keine Redaktions-Mail ablesbar | https://www.nytimes.com/content/help/contact/directory.html (nicht abrufbar) |
| Fierce Healthcare, Fierce Biotech, Fierce Pharma (3, Questex) | Formular https://questex.com/fierce-life-sciences-contact/ ; https://healthcarelifesciences.questex.com/lets-connect/ | https://www.fiercehealthcare.com/contact-us (403 für Bots) |
| Nutritional Outlook (MJH Life Sciences) | nur Kontaktformular auffindbar | https://www.nutritionaloutlook.com/contact-us (403 für Bots) |
| Inside Climate News | Republishing unter CC-Lizenz angeboten (https://insideclimatenews.org/republishing-guidelines/) — Anfrage sollte auf die Republishing-Mail der Guidelines gehen; Kontaktformular | https://insideclimatenews.org/contact/ |
| InsideEVs (Motorsport Network) | team@insideevs.com, tips@insideevs.com | https://insideevs.com/info/contact/ |
| Dezeen | firstname@dezeen.com (Redaktion, Masthead), sales@dezeen.com; Syndication laut Legal-Seite auf Anfrage | https://www.dezeen.com/contact/ , https://www.dezeen.com/legal/ |
| Fashionista (Breaking Media) | tips@fashionista.com; Lizenzen/Permissions breakingmedia@theygsgroup.com | https://fashionista.com/page/contact |
| Ecotextile News (MCL News & Media) | info@mclnews.com | https://www.ecotextile.com/about-us/ |
| Fast Company (Mansueto) | permissions@fastcompany.com (Permissions), mvlicensing@fastcompany.com (Lizenzen), editor@fastcompany.com | https://fastcompany.zendesk.com/hc/en-us/articles/360025831711-Reprints-and-Licensing |
| Finextra | contact@finextra.com (allgemein), news@finextra.com (Redaktion) | https://www.finextra.com/about/finextra.aspx |
| Retail Insider (Kanada) | insider@retail-insider.com | https://www.retail-insider.com/contact |
| Sifted | hello@sifted.eu (allgemein), news@sifted.eu (Redaktion), press@sifted.eu | https://sifted.eu/contact-us |
| Nieman Lab (Harvard) | Kontaktformular; Editor Laura Hazard Owen (Nieman Foundation Contacts) | https://www.niemanlab.org/contact/ |
| Luxury Daily (Napean) | news@napean.com (Redaktion), ads@napean.com | https://www.luxurydaily.com/contact-us/ |
| Class Central (The Report) | contact@classcentral.com | https://www.classcentral.com/contact |
| PNAS | PNASpermissions@pnas.nas.edu (TDM/Permissions laut Rights-Seite; TDM sonst nur für Site-Lizenz-Institutionen) | https://www.pnas.org/about/rights-permissions |

Hinweise für den Versand: Bei PNAS, Variety und NYT ist der Bot-UA-Weg
aussichtslos (Lizenzportale, TollBit-Bezahlschranke) — dort ist die
TDM-Lizenz-Vorlage die richtige, realistisch bleibt Teaser-Betrieb. Bei Inside
Climate News lohnt die Anfrage besonders: die Republishing-Policy ist bereits
CC-lizenziert, nur die Bot-Sperre steht im Weg. Antworten werden im Issue #97
protokolliert; ohne Antwort bleiben die Quellen `fulltext: false`.
