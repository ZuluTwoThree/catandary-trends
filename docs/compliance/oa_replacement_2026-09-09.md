# Open-Access-Ersatz für die 33 TDM-Vorbehalts-Journale (2026-09-09, #97)

Weg **D** aus dem Brainstorming vom 09.09.: die am 04.09. deaktivierten Vorbehalts-Titel nicht zurückholen,
sondern ihre **Fachabdeckung** über Quellen wiederherstellen, deren Artikel selbst offen lizenziert sind.
Eine CC-BY-Lizenz macht die TDM-Schranke aus §44b UrhG entbehrlich — wer erlaubt hat, braucht keinen
Schrankentatbestand, und ein Vorbehalt nach Abs. 3 geht damit ins Leere. Kein Lizenzantrag, keine Anfrage
beim Verlag.

Werkzeug: `scripts/probe_source_compliance.py --file … --discovered-via oa-ersatz-2026-09-09`,
zwei Runden über 43 Kandidaten, 188 Requests, 58 s.

## Ergebnis

| Status | Kandidaten |
|---|---|
| ok | 22 |
| blocked | 11 |
| feed_error | 8 |
| reserved | 2 |

**Aufgenommen: 14.** Alle als `type: research` in den `science`-Listen, `tdm_checked: "2026-09-09"`,
`tdm_status: ok`, `discovered_via: oa-ersatz-2026-09-09`. **13 davon mit `fulltext: true`** — der erste
nennenswerte Volltext-Zuwachs aus offenen Lizenzen seit dem 04.09. (damals 16 von 217).
Aktive RSS-Quellen 513 → **527**; Einträge mit `fulltext: true` 168 → 181 (davon aktiv 178).

| Ersetzt | Neue Quelle | Vertikale | Lizenz |
|---|---|---|---|
| Trends in Food Science & Technology, Comprehensive Reviews in Food Science | Frontiers in Food Science and Technology | FOOD | CC BY 4.0 |
| The Lancet | PLOS Medicine | HEALTH | CC BY 4.0 |
| The Lancet, Lancet Planetary Health | PLOS Global Public Health | HEALTH | CC BY 4.0 |
| Lancet Digital Health | PLOS Digital Health | HEALTH | CC BY 4.0 |
| Nature Aging | Frontiers in Aging | HEALTH | CC BY 4.0 |
| Nature Climate Change, Lancet Planetary Health | PLOS Climate | ECO | CC BY 4.0 |
| Nature Sustainability, One Earth | PLOS Sustainability and Transformation | ECO | CC BY 4.0 |
| Nature Climate Change (Klimaforschung) | Atmospheric Chemistry and Physics | ECO | CC BY 4.0 |
| Science Robotics | Frontiers in Robotics and AI | TECH | CC BY 4.0 |
| Nature Machine Intelligence | Frontiers in Artificial Intelligence | TECH | CC BY 4.0 |
| Nature Machine Intelligence | Journal of Artificial Intelligence Research | TECH | — (kein Volltext) |
| Psychological Science, Nature Human Behaviour | Frontiers in Psychology | LIFESTYLE | CC BY 4.0 |
| Nature (main), Science Magazine News | F1000Research | CROSS | CC BY 4.0 |
| Nature (main) | Open Research Europe | CROSS | CC BY 2.5 |

`relevance_min` gesetzt bei den breiten/volumenstarken Feeds: Frontiers in Psychology 0.7,
Atmospheric Chemistry and Physics / F1000Research / Open Research Europe 0.6.

`verify_feed` 14/14 grün, pytest 1.470 passed.

## Zwei Lücken bleiben offen

**DESIGN / Materialforschung** (Ersatz für Matter, Nature Materials, Nature Reviews Materials): kein
verwendbarer Kandidat. MDPI *Materials*, Royal Society Open Science und PeerJ antworten dem ehrlichen
Bot-UA auf dem Feed mit **403**; `Frontiers in Materials` ist seit 04.09. bereits aktiv. Die Vertikale
hat damit weiterhin nur eine Wissenschaftsquelle.

**FASHION / Textilforschung** (Ersatz für Intl Journal of Fashion Design, Textile Research Journal):
ebenfalls keiner. *Textiles* (MDPI) ist bot-gesperrt, *Fashion and Textiles* (SpringerOpen) bietet keinen
Feed an. `Frontiers in Bioengineering and Biotechnology` deckt den Trends-in-Biotechnology-Teil ab und ist
seit 04.09. aktiv.

## Der Sonderfall, der Weg B begründet

**Nature Communications** (2.576 Werke seit 07/2026, 100 % Open Access, 1.069 CC BY) und
**Scientific Reports** (9.804 / 100 % / 3.020) sind die volumenstärksten OA-Journale überhaupt — und
kommen trotzdem als `reserved` zurück, weil `nature.com` eine `tdmrep.json` mit `location: "/"` ausliefert.
Der Artikel ist frei lizenziert, der Host verbietet TDM. Genau diese Konstellation ist der Grund für Weg B
(Lizenzprüfung je Artikel schlägt Vorbehalt je Host); über Weg D sind sie nicht erreichbar.

## Nicht aufgenommen (ok geprüft)

- **PLOS ONE, PLOS Biology, PLOS Computational Biology** — Mega- bzw. Spezialjournale ohne redaktionelle
  Auswahl; PLOS ONE veröffentlicht ein Vielfaches dessen, was ein 30-Einträge-Feed abbilden kann.
  Der Fachbereich ist über eLife (aktiv) und die Preprint-Ingester abgedeckt.
- **Earth System Science Data, The Cryosphere, Biogeosciences** (Copernicus, CC BY 4.0) — zu enge
  Fachfeeds (Datensatzpapiere, Glaziologie) für eine Trendplattform; ACP steht stellvertretend für den
  Copernicus-Bestand und kann jederzeit erweitert werden.
- **Journal of Machine Learning Research** — Regel 3: jüngster Feed-Eintrag 2026-01-01 (Bandausgaben).

## Bot-Sperren und fehlende Feeds

MDPI sperrt **alle** geprüften Journalfeeds (Foods, Agriculture, Nutrients, Sustainability, Materials,
Sensors, Electronics, Textiles) mit HTTP 403 für den Produktions-UA — das ist der größte einzelne Verlust,
weil MDPI durchgehend CC BY publiziert. Kandidat für die WP4-Kontaktliste. Ebenso Royal Society Open
Science und PeerJ (403) sowie Environmental Research Letters (IOP: robots.txt sperrt den Feed-Pfad, gleiche
offene Owner-Frage wie bei den 17 Quellen vom 04.09.). Ohne Feed: BMC Medicine, Fashion and Textiles,
Agriculture and Food Security (BioMed Central/SpringerOpen bieten keine Artikelfeeds mehr an),
Collabra: Psychology (404). JMIR antwortet auf der Artikelseite mit HTTP 202 (Bot-Challenge).

## Vollständige Kandidatentabelle

| Kandidat | Status | Feed | jüngster | Lizenz | Befund |
|---|---|---|---|---|---|
| Agriculture (MDPI) | blocked | — | — |  | feed HTTP 403 for the bot UA |
| Electronics (MDPI) | blocked | — | — |  | feed HTTP 403 for the bot UA |
| Environmental Research Letters | blocked | 16 | 2026-09-08 |  | robots.txt disallows the feed URL |
| Foods (MDPI) | blocked | — | — |  | feed HTTP 403 for the bot UA |
| Materials (MDPI) | blocked | — | — |  | feed HTTP 403 for the bot UA |
| Nutrients (MDPI) | blocked | — | — |  | feed HTTP 403 for the bot UA |
| PeerJ | blocked | — | — |  | feed HTTP 403 for the bot UA |
| Royal Society Open Science | blocked | — | — |  | feed HTTP 403 for the bot UA |
| Sensors (MDPI) | blocked | — | — |  | feed HTTP 403 for the bot UA |
| Sustainability (MDPI) | blocked | — | — |  | feed HTTP 403 for the bot UA |
| Textiles (MDPI) | blocked | — | — |  | feed HTTP 403 for the bot UA |
| Agriculture and Food Security | feed_error | — | — |  | no feed found (21 URLs tried) |
| BMC Medicine | feed_error | — | — |  | HTML page, no feed found (21 URLs tried) |
| BMC Medicine | feed_error | — | — |  | no feed found (21 URLs tried) |
| Collabra Psychology | feed_error | — | — |  | feed HTTP 404 |
| Fashion and Textiles | feed_error | — | — |  | HTML page, no feed found (21 URLs tried) |
| Fashion and Textiles | feed_error | — | — |  | no feed found (21 URLs tried) |
| Journal of Medical Internet Research | feed_error | — | — |  | feed unreachable (ReadTimeout) |
| Journal of Medical Internet Research | feed_error | 10 | 2026-09-09 |  | article HTTP 202 (unverified) |
| Atmospheric Chemistry and Physics | ok | 20 | 2026-09-09 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| Biogeosciences | ok | 20 | 2026-09-07 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| Earth System Science Data | ok | 20 | 2026-09-09 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| F1000Research | ok | 72 | 2026-09-08 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| Frontiers in Aging | ok | 20 | 2026-09-08 |  | feed valid, robots allow, article 200, no TDM signal |
| Frontiers in Artificial Intelligence | ok | 20 | 2026-09-09 |  | feed valid, robots allow, article 200, no TDM signal |
| Frontiers in Bioengineering and Biotechnology | ok | 20 | 2026-09-09 |  | feed valid, robots allow, article 200, no TDM signal |
| Frontiers in Food Science and Technology | ok | 20 | 2026-09-09 |  | feed valid, robots allow, article 200, no TDM signal |
| Frontiers in Psychology | ok | 20 | 2026-09-09 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| Frontiers in Robotics and AI | ok | 20 | 2026-09-09 |  | feed valid, robots allow, article 200, no TDM signal |
| Journal of Artificial Intelligence Research | ok | 10 | 2026-08-25 |  | feed valid, robots allow, article 200, no TDM signal |
| Journal of Machine Learning Research | ok | 205 | 2026-01-01 |  | feed valid, robots allow, article 200, no TDM signal |
| Open Research Europe | ok | 29 | 2026-09-01 | CC BY 2.5 | feed valid, robots allow, article 200, no TDM signal |
| PLOS Biology | ok | 30 | 2026-09-08 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| PLOS Climate | ok | 30 | 2026-09-08 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| PLOS Computational Biology | ok | 30 | 2026-09-08 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| PLOS Digital Health | ok | 30 | 2026-09-08 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| PLOS Global Public Health | ok | 30 | 2026-09-08 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| PLOS Medicine | ok | 30 | 2026-09-08 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| PLOS ONE | ok | 30 | 2026-09-08 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| PLOS Sustainability and Transformation | ok | 30 | 2026-08-24 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| The Cryosphere | ok | 20 | 2026-09-09 | CC BY 4.0 | feed valid, robots allow, article 200, no TDM signal |
| Nature Communications | reserved | 8 | 2026-09-09 |  | tdmrep.json location='/' |
| Scientific Reports | reserved | 8 | 2026-09-09 |  | tdmrep.json location='/' |
