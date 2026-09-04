# Erstlauf Quellen-Compliance-Prüfung (2026-09-04, #97 WP1)

Werkzeug: `scripts/probe_source_compliance.py --all-active` — je Quelle Feed-Validität, robots.txt für `CatandaryTrendsBot` (RFC 9309: Wildcards, `$`, längste Regel, exakter Produkt-Token), Bot-Status des jüngsten Artikels mit dem Produktions-UA, TDM-Signale über die Fetcher-Funktionen (Header, Meta, `noai`, `/.well-known/tdmrep.json`), Lizenzhinweise, Conditional-GET. Etikette: 1 Request/s/Host, 15 s Timeout, 8 Worker; robots.txt einmal je Host, tdmrep.json aus dem 24-h-Host-Cache. Drei Läufe zwischen 09:45 und 10:35 Uhr (415–454 Requests, 67–76 s je Lauf); der dritte Lauf ist der Seeding-Stand in `sources.yaml` (Protokollfelder `tdm_checked: "2026-09-04"`, `tdm_status`, `license`).

**Umfang:** 226 aktive RSS-Quellen in `sources.yaml` (225 eindeutige Feed-URLs — Nation's Restaurant News steht unter zwei Vertikalen; 8 Quellen `active: false` ausgelassen). Die „323 aktiven Quellen" aus #97 sind die DB-Zählung inkl. OpenAlex-/Patent-/Funding-Pseudoquellen ohne Feed.

## Ergebnis je Status (Lauf 3, Seeding)

| Status | Quellen | Bedeutung |
|---|---|---|
| ok | 142 | Feed valide, robots erlaubt Feed + Artikel, Artikel 200, kein TDM-Signal |
| reserved | 33 | maschinenlesbarer TDM-Vorbehalt (Artikel oder Feed) |
| blocked | 46 | Bot-Sperre (401/403/429) oder robots-Verbot für Feed-URL/Artikel |
| feed_error | 5 | nicht verifizierbar (Feed defekt/Bot-Wall, Artikel Timeout) |

Stabilität über die drei Läufe: 219 von 225 Feeds mit identischem Status; Wechsel nur bei Samsung Newsroom (Timeout → ok), HBR (relativer Artikel-Link, Werkzeugfehler behoben), Hacker News Best (aggregierender Feed, jetzt ohne Artikel-Urteil), Variety (Feed 200 → 403 im dritten Lauf), PR Newswire (Feed 200 → 404 im dritten Lauf), Social Enterprise UK (Timeout → ok).

**Die 13 Quellen vom 03.09.:** die 3 Vorbehalte (Horizont, Lebensmittelzeitung: `meta tdm-reservation=1`; Robb Report: `noai,noimageai`) reproduzieren in allen drei Läufen. Von den 10 Bot-Sperren reproduzieren 5 (Business of Fashion — jetzt schon der Feed 403 —, Class Central, InsideEVs, Luxury Daily, Sifted); **5 antworten dem Bot-UA heute dreimal mit 200** (CleanTechnica, ESG Today, Nonprofit Quarterly, Norwegian SciTech News, pv magazine Deutschland). Die 403 vom 03.09. betrafen dort ältere, aus der DB gezogene Artikel-URLs und waren offenbar URL- oder zeitabhängig. `fulltext` bleibt aus (kein Auto-On) — Kandidaten für manuelle Wiederfreigabe nach zwei Wochen Beobachtung (WP3-Regel).

## reserved (33) — alle bereits `fulltext: false`

- **22 × `tdmrep.json` mit `location: "/"`** (site-weiter Vorbehalt), sämtlich Wissenschaftsverlage: Springer Nature (14 Nature-Feeds inkl. Nature main), Wiley (EFSA Journal, EFSA News, Comprehensive Reviews in Food Science), SAGE (Textile Research Journal, Psychological Science), Taylor & Francis (Intl Journal of Fashion Design), AAAS (Science Magazine News, Science Robotics). Die Sondierung vom 03.09. sah nur Volltext-Quellen — daher damals „keine gültige tdmrep.json".
- **8 × `TDM-Reservation: 1` als HTTP-Header auf der Feed-Antwort selbst** — Elsevier: Trends in Food Science & Technology, Food Policy, Trends in Biotechnology (sciencedirect.com), The Lancet, Lancet Digital Health, Lancet Planetary Health (thelancet.com), One Earth, Matter (cell.com). Das ist ein expliziter Vorbehalt auf dem Feed, nicht nur auf Artikelseiten.
- 3 × wie am 03.09. (Horizont, Lebensmittelzeitung, Robb Report).

Folge: kein Volltext (war schon so). Offene Owner-Frage (nicht Teil von WP1): ob Titel/Teaser aus einem Feed mit Vorbehalts-Header weiterhin klassifiziert und als Signal gezeigt werden dürfen. Die bisherige Linie (03.09.): der Feed ist vom Verlag zur Weiterverbreitung angeboten, die generierten Artikel sind eigenständige Berichterstattung mit Backlink. Für die 8 Elsevier-Feeds ist diese Begründung schwächer als für die 22 tdmrep-Hosts, weil der Vorbehalt auf der Feed-Antwort steht.

## blocked (46)

- **22 × Artikel 403 für den Bot-UA** (Feed liefert): NYT Technology/Health/Climate/Business/Science, Fierce Healthcare/Biotech/Pharma, Nutritional Outlook, Inside Climate News, InsideEVs, Dezeen, Fashionista, Ecotextile News, Fast Company, Finextra, Retail Insider, Sifted, Nieman Lab, Luxury Daily, Class Central Report, PNAS. Alle bereits `fulltext: false`. Teaser-Betrieb läuft; WP4-Kontaktliste.
- **5 × Feed selbst gesperrt**: Business of Fashion, EE Times, Endpoints News, Variety (403; Variety erst im dritten Lauf — möglicherweise Ratenlimit durch die Wiederholung), VentureBeat (429). Der Poller bekommt dort nichts (Retry mit kurzem UA-Token half im Probe-Lauf bei keiner Quelle). WP4-Kontaktliste, sonst `active: false`.
- **17 × robots.txt verbietet die Feed-URL** (Artikelseiten teils erlaubt): 10 Förderinfo-Bund-Feeds (`Disallow: /foerderinfo/de/services/`), idw Pressemitteilungen (`Disallow: /*pressreleasesrss`), Netzpolitik.org (`Disallow: /feed/`), Spotify Newsroom (`Disallow: */feed/`), The Register (`Disallow: /` für `*`), SAP News (`Disallow: /`), NEJM (`/action`, `/rss`), Axios (`api.axios.com`: `Disallow: /`). **Owner-Entscheidung nötig:** gilt robots.txt für das Abonnieren eines angebotenen RSS-Feeds? Üblich ist, dass `Disallow: /feed/` Suchmaschinen vom Indexieren des Feeds abhalten soll, nicht Feedreader vom Lesen; The Register, SAP und Axios sperren dagegen alles für nicht namentlich genannte Bots. Das Werkzeug wertet Feed-URL-Regeln als `blocked`, lässt `fulltext` aber unangetastet, solange die Artikelseite erlaubt ist (idw, Förderinfo, Netzpolitik, Spotify, Register-Artikel sind erlaubt).
- **2 × robots.txt verbietet die Artikelseite**: Wired und Vogue UK (Condé Nast: `Disallow: /*` für `*`, nur `/*rss` u. ä. erlaubt). Beide hatten `fulltext: true` — **der Fetcher hat dort bis heute Volltext gegen robots.txt geholt**, weil `urllib.robotparser` `*` wörtlich liest (siehe Befund unten). Jetzt `fulltext: false`. Bereits gespeicherter Volltext (`raw_entries.raw_content`, max. 14 Tage alt) — Löschung analog 03.09. ist Owner-Entscheid (`purge_raw_content.py --source`).
- SAP News (`Disallow: /` deckt auch Artikel): `fulltext: false` gesetzt.

## feed_error (5)

Intel Newsroom (Feed-URL liefert HTML — Feed tot), IFPRI Blog (Incapsula-Bot-Wall, HTML statt XML), EU Parliament Press (HTTP 202 mit leerem Body — Bot-Challenge), McKinsey Insights (Artikel-Timeout), PR Newswire (Feed 404 nur im dritten Lauf, vorher 200 — Monatsprüfung klärt). Die ersten drei gehören in die Feed-Health-Pflege (#13/#81).

## Lizenzen

Strukturiert erkannt (7): Frontiers in Sustainable Food Systems **CC BY 4.0**, CleanTechnica **CC BY 2.0**, Higher Ed Dive **CC BY-SA 4.0**, Netzpolitik.org CC BY-NC-SA 4.0, MIT News CC BY-NC-ND 3.0, Carbon Brief CC BY-NC-ND 4.0, Modern Farmer CC BY-ND 4.0. Nur die ersten drei zählen als „offen" im Sinne von Kriterium 4; NC/ND-Lizenzen sind kein Plus für `fulltext`. Hinweise ohne Lizenzwert: `rel="license"` der Förderinfo-Feeds zeigt aufs BMFTR-Impressum, Hypebeast auf ein proprietäres `license.xml`.

Conditional GET (Lauf 2): 90 Feeds ETag+Last-Modified, 59 nur Last-Modified, 30 nur ETag, 47 keines — 179 von 226 Feeds könnten per `If-None-Match`/`If-Modified-Since` gepollt werden (Poller macht das heute nicht; Folgeidee für #13).

## Befunde am Werkzeugbestand

1. **`urllib.robotparser` ist kein RFC-9309-Parser:** `*` in Pfaden wird wörtlich gelesen, `$` nicht verstanden, User-Agent-Gruppen per Teilstring gewählt (`User-agent: bot` träfe uns). Betroffen im Produktions-Fetcher: Condé Nast (`Disallow: /*`) und idw (`/*pressreleasesrss`). Behoben (Commit 29b8b83): `pipeline.article_fetcher.robots_allows()` wertet die geparsten Regeln selbst aus; `_robots_ok` nutzt es; das Probe-Werkzeug importiert dieselbe Funktion. 8 Tests.
2. Aggregierende Feeds (`type: api`, Hacker News Best via hnrss.org): ein Artikel-Urteil sagt nichts über die Quelle — das Werkzeug prüft dort nur den Feed; robots/TDM prüft der Fetcher je Artikel. HN steht auf der Aggregator-Blockliste für Kandidaten, bleibt aber als vom Owner kuratierte Quelle bestehen — Owner-Frage, ob das zur „nur Primärquellen"-Linie passt.
3. Ein Feed-403 oder Timeout schaltet `fulltext` nicht ab (Artikel ungeprüft); nur Artikel-Evidenz (Vorbehalt, robots-Verbot auf der Artikelseite, 401/403/429 dort) tut das. Variety hätte sonst durch das Ratenlimit des dritten Laufs seinen Volltext verloren.

## Owner-Entscheidungen (offen)

- Feed-URL-robots-Regeln (17 Quellen, darunter 10 Förderinfo Bund + idw): weiterpollen (RSS als Abo-Angebot) oder deaktivieren? Bis zur Entscheidung meldet die Monatsprüfung sie nicht erneut (Status ist protokolliert), Polling läuft unverändert.
- Elsevier-Feeds mit `TDM-Reservation`-Header (8): Teaser-Betrieb fortführen oder deaktivieren?
- Wired/Vogue UK: gespeicherten Volltext löschen (wie am 03.09.)?
- Hacker News Best als Quelle behalten?
- Fünf nicht reproduzierte 403-Quellen: `fulltext` nach zwei Wochen Beobachtung wieder einschalten?

## Weiterer Betrieb

Monatsprüfung: `scripts/monthly_source_check.py` Abschnitt 8 (Cron 1. des Monats 08:00) prüft alle aktiven Quellen erneut, schreibt die Protokollfelder zurück, meldet Wechsel nach/aus `reserved|blocked` und schaltet `fulltext` bei Artikel-Vorbehalt/-Sperre ab (nie automatisch wieder ein). Kandidatenrecherche (WP2): `scripts/discover_from_aggregators.py --probe --yaml` (HN-API, Wikipedia-Listen → Wikidata P856, idw-Institutionen, Reddit nur mit registrierter App).
