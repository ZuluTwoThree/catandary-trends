# Catandary Trends – Lokale Cross-Industry Trend Intelligence Pipeline

## Architekturübersicht

Catandary Trends ist eine branchenübergreifende Trend-Intelligence-Plattform, die auf lokalen LLMs (Ollama) läuft und als öffentlicher Free-Content-Bereich auf der Catandary-Website dient. Sie deckt alle relevanten Industrie-Vertikale ab und fungiert als Lead-Generator für die kostenpflichtigen Catandary-Services, insbesondere Catandary Foresight.

**Kernprinzipien:**
- Branchenübergreifend mit eigenständiger Catandary-Taxonomie (Vertikale + PESTEL + Mega/Macro/Micro)
- Nur legale Primärquellen (RSS-Feeds von Fachmedien, Presseverteilern, Marken-Newsrooms)
- Keine Aggregator-Seiten scrapen (Trendhunter etc.) — Aggregatoren dürfen aber als **Entdeckungs-Index** dienen, um die dort verlinkten Primärquellen zu finden und einzeln zu prüfen (Owner 2026-09-03, #97)
- Alle LLM-Verarbeitung lokal auf der **RTX 3090 (24 GB)** (produktive Linux-Workstation; VRAM per `nvidia-smi` verifizieren). Stage 6 (Content-Gen) auf llama.cpp **Gemma-4-26B-A4B** (aktuell seit #11 / 2026-07-14; revertierbar nur noch aufs 35B — das 30B-GGUF+Startskript fielen dem llama.cpp-Umbau 2026-08-29 zum Opfer).
- Cloud-APIs nur als Fallback für komplexe Synthese-Aufgaben
- Modularer Aufbau: Neue Vertikale können ohne Architekturänderung hinzugefügt werden

---

## Catandary Trend-Taxonomie

### Industrie-Vertikale (eigenständige Catandary-Struktur)

| Vertikale | Kürzel | Abdeckung | Beispiel-Signale |
|---|---|---|---|
| **Food & Beverage** | FOOD | Lebensmittel, Getränke, Gastronomie, AgriTech | Plant-Based, Fermentation, Functional Foods |
| **Technology & AI** | TECH | Software, Hardware, AI, Robotik, IoT | GenAI-Tools, Wearables, Edge Computing |
| **Health & Wellness** | HEALTH | Medizin, klinische Wellness, Mental Health, Pharma, Supplements, körperphysiologische Fitness | Digital Health, Longevity, Microbiome |
| **Sustainability & Eco** | ECO | Energie, Kreislaufwirtschaft, Klima, Mobilität | Carbon Capture, Circular Packaging, EV |
| **Design & Architecture** | DESIGN | Produktdesign, Architektur, Interiors, UX | Biophilic Design, Modular Housing |
| **Fashion & Beauty** | FASHION | Mode, Kosmetik, Textil, Schmuck | Slow Fashion, Biotech Materials, Clean Beauty |
| **Business & Retail** | BIZ | Strategie, Startups, Handel, E-Commerce, Fintech | D2C, Recommerce, Embedded Finance |
| **Lifestyle** | LIFESTYLE | Kultur, Entertainment, Social Media, Gaming, Kunst, Bildung, Inklusion, Luxury, Travel, Sport (Athleten/Events/Communities/Studios) | Creator Economy, Spatial Computing, Experiential Luxury, EdTech, Hyrox |

### PESTEL-Klassifizierung (quer zu den Vertikalen)

Jeder Trend wird zusätzlich einer oder mehreren PESTEL-Dimensionen zugeordnet:

| Dimension | Kürzel | Farbe (UI) | Beispiele |
|---|---|---|---|
| **Political** | P | Rot | Regulierung, Trade Policy, Subventionen |
| **Economic** | E | Blau | Preisdruck, Funding, Marktkonsolidierung |
| **Social** | S | Grün | Verbraucherverhalten, Demografie, Werte |
| **Technological** | T | Violett | Neue Technologien, Patente, F&E |
| **Environmental** | En | Türkis | Nachhaltigkeit, Klima, Ressourcen |
| **Legal** | L | Orange | Gesetze, Compliance, IP-Schutz |

### Mega/Macro/Micro-Ebenen (Catandary Foresight Taxonomie)

| Ebene | Zeithorizont | Beispiel |
|---|---|---|
| **Mega-Trend** | 10-25 Jahre | "Personalisierte Ernährung" |
| **Macro-Trend** | 3-10 Jahre | "Functional Foods mit Darm-Hirn-Achse-Fokus" |
| **Micro-Trend** | 6 Monate - 3 Jahre | "Postbiotische Snack-Bars mit Mood-Claims" |

Die Mega/Macro-Einordnung wird auf der Free-Seite nur angeteasert – die vollständige Prognose ist Catandary-Foresight-Content.

---

## Hardware-Basis

- **GPU:** NVIDIA RTX 3090 (24 GB GDDR6X) — die produktive lokale Karte (per `nvidia-smi` bestätigt). Vor jeder VRAM-/Koexistenz-Entscheidung trotzdem `nvidia-smi` prüfen (llama-server hält ~22 GB im Ruhezustand). *(Frühere Doku nannte alternativ eine 16-GB-Karte; produktiv ist es die 3090.)*
- **Modelle laufen sequentiell** (nicht parallel) – VRAM wird zwischen Schritten freigegeben
- **Peak-VRAM Ollama-Pfad:** ~10.7 GB (Qwen3 14B Q4_K_M) — passt auf der 24-GB-Karte mit Headroom
- **llama.cpp-Pfad für Stage 6 (Content-Gen), aktuell:** **Gemma-4-26B-A4B-it-qat-UD-Q4_K_XL** (`start-gemma4-26b.sh`) — Umstellung von Qwen3-30B via #11 (2026-07-14) nach einem kontrollierten A/B: das 30B erfand in 32,9 % der Bodies erfundene Spezifika (fake Gesetze/Städte), das Gemma-26B nur 8,6 %. *(Die frühere Zusatzbehauptung, Gemma treffe das 150–250-Wörter-Ziel, ist durch den Dauerbetrieb widerlegt: der Median fiel am Umstiegstag von 131 auf 105 und liegt seither bei ~109. Owner hat ~100 am 2026-08-19 als Länge akzeptiert.)* Qwen3.6-35B-A3B (~24 GB) bleibt installiert und per `STAGE5_MODEL`/`STAGE5_START` **revertierbar**; das 30B wurde beim llama.cpp-Umbau 2026-08-29 entfernt (GGUF + start-qwen3-30b.sh). Mid-Pipeline-GPU-Handover (siehe `pipeline/gpu_handover.py`). Default-Backend (ohne `scheduled_cycle.sh`) bleibt Ollama.
- **Ollama-Konfiguration:** `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_KEEP_ALIVE=5m`

---

## Datenbeschaffung: Legale Quellenstrategie

### Schicht 1: Direkte Primärquellen via RSS (nach Vertikale)

Quellen werden pro Vertikale organisiert. Neue Vertikale starten mit 3-5 Kernquellen und wachsen organisch. Feed-URLs sind zu verifizieren.

**FOOD & BEVERAGE:**
| Quelle | Typ | Fokus |
|---|---|---|
| FoodNavigator | Fachpresse | Ingredients, Regulation, Innovation |
| Food Dive | Fachpresse | Business, Supply Chain, M&A |
| The Spoon | FoodTech | Technology, AgriTech, Delivery |
| FoodBev Media | Fachpresse | Product Launches, Packaging |
| New Food Magazine | Fachpresse | Processing, Safety, Science |

**TECHNOLOGY & AI:**
| Quelle | Typ | Fokus |
|---|---|---|
| TechCrunch | Tech-Presse | Startups, Funding, Product Launches |
| The Verge | Tech-Presse | Consumer Tech, Culture, Policy |
| Ars Technica | Tech-Presse | Deep Tech, Science, Policy |
| MIT Technology Review | Forschung | Emerging Tech, AI, Biotech |
| VentureBeat (AI) | Tech-Presse | AI/ML, Enterprise, Startups |

**HEALTH & WELLNESS:**
| Quelle | Typ | Fokus |
|---|---|---|
| STAT News | Fachpresse | Pharma, Biotech, Health Policy |
| Mobihealthnews | Fachpresse | Digital Health, Wearables |
| Nutraingredients | Fachpresse | Supplements, Functional, Nutrition |
| Fierce Healthcare | Fachpresse | Health Systems, Insurance, AI |

**SUSTAINABILITY & ECO:**
| Quelle | Typ | Fokus |
|---|---|---|
| GreenBiz | Fachpresse | Corporate Sustainability, Circular |
| CleanTechnica | Fachpresse | Renewable Energy, EV, Storage |
| Packaging Dive | Fachpresse | Sustainable Packaging, Materials |
| Carbon Brief | Forschung | Climate Science, Policy |

**DESIGN & ARCHITECTURE:**
| Quelle | Typ | Fokus |
|---|---|---|
| Dezeen | Fachpresse | Architecture, Product Design |
| ArchDaily | Fachpresse | Architecture, Urban Planning |
| Core77 | Fachpresse | Industrial Design, UX |
| Designboom | Fachpresse | Art, Design, Technology |

**FASHION & BEAUTY:**
| Quelle | Typ | Fokus |
|---|---|---|
| Business of Fashion | Fachpresse | Fashion Business, Strategy |
| Cosmetics Design | Fachpresse | Beauty, Ingredients, Innovation |
| Vogue Business | Fachpresse | Luxury, Retail, Consumer |
| Sourcing Journal | Fachpresse | Supply Chain, Textiles |

**BUSINESS & RETAIL:**
| Quelle | Typ | Fokus |
|---|---|---|
| Retail Dive | Fachpresse | Retail, E-Commerce, DTC |
| Fast Company | Business-Presse | Innovation, Leadership |
| Finextra | Fachpresse | Fintech, Banking, Payments |
| CB Insights (Blog) | Research | Startups, Markets, VC |

**LIFESTYLE (Kultur, Entertainment, Social Impact, Luxury):**
| Quelle | Typ | Fokus |
|---|---|---|
| Nieman Lab | Fachpresse | Media, Journalism, Platforms |
| The Creator Economy | Fachpresse | Creators, Social Media |
| Game Industry.biz | Fachpresse | Gaming, Interactive Media |

**Cross-Industry Presseverteiler:**
| Quelle | Typ | Nutzung |
|---|---|---|
| PR Newswire | Pressemitteilungen | Alle Kategorien, Filter nach Branche |
| BusinessWire | Pressemitteilungen | Alle Kategorien, Filter nach Branche |
| GlobeNewswire | Pressemitteilungen | Alle Kategorien, Filter nach Branche |

**Ergänzende Datenquellen:**
| Quelle | Zugang | Typ |
|---|---|---|
| Exploding Topics API | API, $249/Monat | Cross-Industry Trend-Daten |
| Google Trends | pytrends (kostenlos) | Validierung aller Vertikalen |
| Reddit (diverse Subreddits) | Offizielle API | Community-Signale |
| Hacker News | RSS/API | Tech-Signale |

*(Stand 2026-09-02: davon ist nur Hacker News produktiv — `scripts/ingest_hn_launches.py` im Samstagslauf. Exploding Topics, Google Trends/pytrends und Reddit sind **nicht implementiert**; die Tabelle ist eine Ideenliste, keine Quellenliste. Vereinzelte Erwähnungen in `pipeline/crs.py`/`radar_discovery.py` sind Radar-Altcode.)*

### Quellenwachstum

Neue Quellen werden manuell kuratiert und in `sources.yaml` eingetragen. Kein automatisches Scraping, keine Aggregator-Quellen. **Seit 2026-09-03 (#97):** neue Quellen nur mit maschinell geprüftem Status (`tdm_status: ok` — robots, Bot-UA 200, kein TDM-Vorbehalt); **Volltext für alle `ok`-Quellen (Owner 2026-09-11, Option A — bis dahin nur bei offener Lizenz)**; Aggregatoren dienen nur als Entdeckungs-Index für die dort verlinkten Primärquellen. Trendhunter und Brave Search Radar wurden 2026-04-12 entfernt.

**Ist-Stand 2026-09-09 (gemessen, nicht fortgeschrieben):**

| | |
|---|---|
| `sources.yaml`, aktiv | **560** RSS-Quellen (559 eindeutige Feeds — Nation's Restaurant News steht unter zwei Vertikalen) |
| davon Signalbetrieb (`llm_pipeline: false`) | 33 — liefern Embeddings/Foresight, nie Artikel |
| **liefern Artikelmaterial** | **527** |
| mit `fulltext: true` | **480** (seit 2026-09-11; 178 davor) |
| DB `sources` | 616 gesamt, **601 aktiv** = 506 aus der YAML + 95 Nicht-RSS-Pseudoquellen (EPO/Google Patents, OpenAlex, CORDIS, Funding, SEC Form D) |
| noch ohne DB-Zeile | 53 YAML-Quellen — die legt der nächste 04:00-Poll an (`upsert_source`), dann 654 aktiv |

Alle 8 Vertikale sind abgedeckt. Die DB-Zählung zieht immer erst mit dem nächsten Poll nach; **Flag-Änderungen in der YAML erreichen die DB nie von selbst** (`upsert_source` schreibt nur beim INSERT) — nach jeder Änderung an `active` oder `llm_pipeline` gehört `scripts/apply_source_hygiene.py --apply` dazu.

**Wie es dahin kam (Chronik #97):**

- **2026-09-04, WP2/WP3:** 708 Kandidaten geprüft (ok 352, feed_error 294, blocked 50, reserved 12), **217 aufgenommen** — 226 → 443 aktive Quellen; davon 108 DE/AT/CH und 16 mit offener Lizenz + `fulltext`. Je Vertikale: FOOD 30, DESIGN 24, FASHION 14, ECO 32, TECH 37, HEALTH 23, BIZ 26, LIFESTYLE 31. Regeln, Lizenzbelege, Kandidatentabelle: `docs/compliance/source_candidates_2026-09-04.md`.
- **2026-09-04, WP2b:** Triage der 294 `feed_error`-Kandidaten + benannte internationale Tech-Liste → **56 weitere Quellen** (Feeds an nicht-standardisierten CMS-Pfaden: UBA, KIT, Jülich, JRC, USPTO, EMA, DIW, Fraunhofer IVV, EZB, Census, WRI, Google/Microsoft Research, Hugging Face … plus TechNode, DigiTimes, TNW, UKTN, ITU/W3C/IETF/ETSI, Siemens/Arm/AMD/Meta/Mistral). Bot-Walls und leere Feeds je Kandidat: `docs/compliance/source_triage_2026-09-04.md`.
- **2026-09-04, Vorbehalts-Welle:** die 33 Quellen mit maschinenlesbarem TDM-Vorbehalt deaktiviert (22 × `tdmrep.json` bei Springer Nature/Wiley/SAGE/T&F/AAAS, 8 × `TDM-Reservation`-Header auf dem Feed bei Elsevier/Cell/Lancet, 3 vom 03.09.), Ersatz: 4 Frontiers-Open-Access-Journale. → 414.
- **2026-09-09, Owner-Domainliste:** 181 Domains abgeglichen (`docs/compliance/source_domain_check_2026-09-09.md`), die 111 inhaltlich möglichen geprobt — ok 57, feed_error 47, blocked 7, **reserved 0** (1.306 Requests). **39 aufgenommen** (40 empfohlen; Farmers Review Africa fiel im Nachlauf mit `verify_feed` durch: 403 rund 25 min nach der Probe, mit beiden UAs). Kein `fulltext` — keine strukturiert belegte offene Lizenz. 17 ok-Kandidaten bewusst abgelehnt (8× Regel 6 Tageszeitungen mit breitem Gesamtfeed, 4× Autodiscovery-Fehltreffer, 2× verwaist, Firmenblog, Dublette, keine Primärquelle). 474 → 513. Bericht: `docs/compliance/source_probe_2026-09-09.md`.
- **2026-09-09, Weg D — Open-Access-Ersatz:** 43 OA-Kandidaten geprobt (ok 22, blocked 11, feed_error 8, reserved 2), **14 aufgenommen, 13 mit `fulltext: true`** — eine CC-BY-Lizenz macht die TDM-Schranke entbehrlich, ein Vorbehalt nach §44b Abs. 3 geht dann ins Leere (kein Lizenzantrag nötig). PLOS Medicine/Global Public Health/Digital Health/Climate/Sustainability, Frontiers Food Science/Aging/Robotics and AI/Artificial Intelligence/Psychology, Atmospheric Chemistry and Physics, JAIR, F1000Research, Open Research Europe. 513 → 527, `fulltext` 168 → 181. **Lücken:** DESIGN (Materialforschung) und FASHION (Textilforschung) — MDPI sperrt **alle** acht geprüften Journalfeeds mit 403 für den Bot-UA, ebenso Royal Society Open Science und PeerJ; BMC und SpringerOpen bieten keine Artikelfeeds mehr. Bericht: `docs/compliance/oa_replacement_2026-09-09.md`.
- **2026-09-09, Weg A — Signalbetrieb:** die 33 Vorbehalts-Quellen laufen wieder (`active: true`), liefern aber nie Artikelmaterial (`llm_pipeline: false`) und ihr Teaser wird gar nicht erst gespeichert (`store_excerpt: false`, neues Feld — der Poller schreibt nur Titel, URL und Datum). Bibliografische Metadaten sind nicht geschützt, das Abstract im Teaser sehr wohl; §44b Abs. 3 sperrt TDM, nicht die Kenntnisnahme einer Tatsache. Damit kommt der analytische Wert zurück, ohne ein Wort geschützten Textes zu speichern. Der Samstagslauf verarbeitet sie über `signal_batch_embedded.py --signal-only` (30 der 33 sind `source_type=research` und liefen ohnehin mit; die drei `trade_media` — Lebensmittelzeitung, Horizont, Robb Report — fänden sonst keinen Lauf). 527 → 560.
- **2026-09-09, Wege B+C — Lizenz je Artikel schlägt Host-Vorbehalt:** ein Verlag kann site-weit TDM vorbehalten und denselben Artikel unter CC BY veröffentlichen; die Lizenz ist eine Erlaubnis, der Vorbehalt sperrt nur die Schranke, die ein lizenzierter Zugriff nicht braucht. `pipeline/open_license.py` löst gegen OpenAlex auf (DOI aus der URL, sonst Titelsuche mit Titelabgleich), prüft `best_oa_location.license` (offen: cc-by/cc-by-sa/cc0/public domain; **nie** `-nc`, **nie** `-nd`) und rankt die offenen Fundstellen (Datenrepositorien zuletzt). `scripts/resolve_open_licence.py` (Default Dry-Run, `--apply`, Cron 03:45) holt den Volltext von dort — **vom Vorbehalts-Host wird nichts geholt, der Feed ist nur Entdeckungs-Index** (Weg C, dieselbe Regel wie für Aggregatoren seit 03.09.) — und schreibt `raw_content` + `open_licence` + `oa_url` (additive Migration `_migrate_open_licence`, **in `init_db` verdrahtet**, Live-DB 09.09.). `open_licence` ist zugleich die Eintrittskarte in den Cycle: `get_unprocessed_entries` lässt solche Einträge zu, obwohl ihre Quelle im Signalbetrieb läuft (`active` bleibt das härtere Gate). Jeder Eintrag wird mit `--apply` **genau einmal** geprüft: `raw_entries.licence_checked_at` wird bei jedem Ausgang gestempelt, auch bei „nicht offen" (additive Migration `_migrate_licence_checked`, in `init_db` verdrahtet, Live-DB 09.09.). Ohne diese Marke fragte der nächtliche Lauf dieselben ~85 % Nicht-Offenen jede Nacht neu ab — die Zeilen bleiben ja unverarbeitet, bis der Samstagslauf sie einzieht — und bei ~254 Einträgen/Tag gegen `--limit 300` käme der ältere Teil des Pools nie an die Reihe. Ausbeute an 60 echten Einträgen: 10 offen lizenziert (17 %), davon **7 mit Volltext (12 %)** — bei ~500 Einträgen/Woche aus diesen Quellen rund 58 Artikel/Woche. Nature Communications und Scientific Reports (zusammen 12.380 Werke seit 07/2026, 100 % OA, 4.089 CC BY) sind über diesen Weg erreichbar, über Weg D nicht: `nature.com` liefert eine site-weite `tdmrep.json`.
  **Compliance-Fix im selben Zug:** `article_fetcher.fetch_fulltext_result` prüfte robots und TDM nur gegen die ANGEFRAGTE URL. Ein DOI-Link (`doi.org/10.1038/…` → `nature.com/articles/…`) umging damit die site-weite `tdmrep.json` von nature.com — 12.000 Zeichen wurden gespeichert. Die Ziel-URL nach Weiterleitungen wird jetzt erneut geprüft. Der Parameter `open_licence=` hebt **nur** den TDM-Vorbehalt auf, nie robots.txt (Zugriffspolitik der Seite, kein Rechtevorbehalt).
- **2026-09-11, Option A — Volltext für alle `ok`-Quellen (Owner):** Messung der letzten 14 Tage: die 305 Quellen mit `tdm_status: ok` aber `fulltext: false` lieferten 10.500 Einträge und **19** Volltexte; die 165 Opt-in-Quellen 9.098 Einträge mit 69 % Text (seit dem Fix vom 08.09. 73–100 % je Quelle; Rest = Bezahlartikel wie heise+, gelöschte Seiten, bildlastige Beiträge). Die Regel „Volltext nur bei offener Lizenz" war strenger als §44b: geprüft sind bei allen `ok`-Quellen robots, Bot-Zugang und Vorbehalt, und der Fetcher prüft jeden Artikel erneut. **302 Quellen auf `fulltext: true`** → 480 von 560; erwartet rund +7.000 Volltexte je 14 Tage. `fetch_batch` dafür parallelisiert (`FETCH_WORKERS=8`, Host-Drossel 1 Anfrage/s bleibt; seit 2026-09-17 mit Ausnahmetabelle `article_fetcher.HOST_DELAYS` — Project Syndicate 2 s; gemessen ist die Sperre dort ein Kontingent je Zeitfenster mit langer Strafzeit, kein Intervall: nach 10 min Pause mit 10 s Abstand 30/30 × 429). Zugleich **User-Agent V2:** `CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology)` — die Mailadresse steht auf der Methodik-Seite (Abschnitt „Our AI agent", bis 20.09. „Our crawler"), nicht mehr in jedem Log. Anlass: `docs/embedding_eval_2026-09-11.md` (der Hebel für Inhaltsanalyse ist Text, nicht ein zweiter Vektor).
- **2026-09-17, Nachhollauf + Sperren:** `refetch_fulltext.py --since 2026-09-03 --min-age-days 0 --apply` holte 12.176 von 14.471 Volltexten (84 %) nach — die Einträge waren nie geholt worden. Sieben Quellen sperren Artikelseiten trotz `tdm_status: ok` per 403 (DigiTimes 74/389 erreichbar, Retail Gazette 10/52, Mongabay/Tech Funding News/Apparel Resources/HPCwire 0) → `fulltext: false`, `tdm_status: blocked` (Owner); pv magazine International schon am 16.09.
- **Offen:** die 17 Quellen, deren robots.txt nur die Feed-URL sperrt (Owner-Entscheid seit 04.09.); DESIGN/FASHION ohne OA-Ersatz; die juristische Bestätigung von „Lizenz sticht Vorbehalt".

2026-08-07 kamen 15 verifizierte Feeds für die Taxonomie-Erweiterung dazu (Quantum/Semis/Space/Digital Health/Future of Work/Education — u. a. The Quantum Insider, NVIDIA/Intel/IBM Newsroom, SpaceNews, NASA/ESA, Rock Health, HR Dive, EdSurge). Ausbau auf nicht-RSS-Quellentypen siehe `pipeline_expansion_prompt.md` und Goal Contract unter `goals/`.
*(Quellenzahl 2026-09-02: `scripts/apply_source_hygiene.py --apply` ist ausgeführt — die 6 in #81 (28.08.) als tot befundenen Feeds (Euractiv, Rock Health Blog, WorkLife, Shopify News, Förderinfo Bund – Mobilität, Environmental Leader) und die 3 schon vorher nur in `sources.yaml` deaktivierten (MobiHealthNews, Healthcare IT News, BMJ) stehen jetzt auch in der DB auf `active=false` (per SELECT verifiziert). DB-Ist 02.09.: **323 aktiv / 16 inaktiv / 339 gesamt**; die Differenz zur alten Rechnung 328−9=319 sind die vier am 29.08. angelegten OpenAlex-Fresh-Pseudoquellen (ids 347–350). Strukturbefund bleibt gültig: `sources.yaml` `active: false` synct nie automatisch in die DB (`upsert_source` überschreibt `active` auf einer bestehenden Zeile nie, und der Poller überspringt inaktive Quellen VOR dem Upsert-Call) — Deaktivierungen daher immer mit `apply_source_hygiene.py --apply` nachziehen.)*

**Nutzungsbedingungen maschinell geprüft (seit 2026-09-04, #97 WP1):** Jede aktive RSS-Quelle trägt in `sources.yaml` die Protokollfelder `tdm_checked`/`tdm_status` (`ok|reserved|blocked|feed_error`) und ggf. `license`/`discovered_via` (Kriterien + Feldsemantik im Kopfkommentar der Datei). Werkzeuge: `scripts/probe_source_compliance.py` (je Kandidat oder `--all-active`: Feed, robots.txt für `CatandaryTrendsBot` RFC-9309-konform, Bot-Status, TDM-Signale über die Fetcher-Funktionen, Lizenzhinweise, Conditional-GET; `--yaml`/`--write`; Aggregator-Blockliste) und `scripts/discover_from_aggregators.py` (nur HN-API, Wikipedia-API→Wikidata P856, idw-RSS, Reddit-API mit registrierter App → Domain-Kandidaten → Feed-Autodiscovery → `--probe`). **Aggregatoren nie als Quelle, aber als Entdeckungs-Index erlaubt (Owner 03.09.).** Die Monatsprüfung (`monthly_source_check.py`, Abschnitt 8, `--no-tdm` überspringt) prüft alle aktiven Quellen erneut, schreibt die Felder zurück, meldet Wechsel nach/aus `reserved|blocked` und schaltet `fulltext: true` bei Vorbehalt/Sperre auf Artikel-Ebene ab (nie automatisch wieder ein). Erstlauf 04.09. über 226 aktive RSS-Quellen in `sources.yaml` (die 323 der DB-Zählung enthalten Pseudoquellen ohne Feed): ok 142, reserved 33 (22 Wissenschaftsverlage per `tdmrep.json`, 8 Elsevier-Feeds mit `TDM-Reservation`-Header, 3 vom 03.09.), blocked 46 (22 Artikel-403, 5 Feed-Sperren, 17 robots-Regeln nur auf der Feed-URL — Owner-Entscheid offen —, Wired/Vogue UK robots auf Artikelseiten → `fulltext` aus), feed_error 5 — `docs/compliance/source_probe_2026-09-04.md`. Nebenbefund: `urllib.robotparser` liest `*` wörtlich; der Fetcher wertet robots.txt seit 04.09. selbst RFC-9309-konform aus (`article_fetcher.robots_allows`).

---

## LLM-Pipeline: Modellarchitektur

### Modell-Zuordnung pro Pipeline-Schritt

| Schritt | Modell | VRAM | Speed (Referenz) | Backend |
|---|---|---|---|---|
| 1. Relevanz-Filter | Qwen3 8B Q4_K_M | ~6.5 GB | ~129 t/s | Ollama (`ollama pull qwen3:8b`) |
| 2. Strukturierte Extraktion | NuExtract 3.8B | ~4 GB | ~200+ t/s | Ollama (`ollama pull nuextract`) — derzeit Fallback auf qwen3:8b |
| 3. NER (Markennamen) | Qwen3 8B Q4_K_M | ~6.5 GB | ~129 t/s | Ollama |
| 4. Klassifizierung | Qwen3 8B Q4_K_M | ~6.5 GB | ~129 t/s | Ollama |
| 5. Content-Generierung (EN) | Qwen3 14B Q4_K_M (Ollama-Fallback) **oder** Gemma-4-26B-A4B (llama.cpp, aktuell; 30B/35B revertierbar) | ~10.7 GB / ~16 GB | ~80 t/s / ~110 t/s | Ollama (Default) **oder** llama.cpp (`STAGE5_BACKEND=llamacpp`, nur 24-GB-Karte, mit GPU-Handover) |
| 6. Embeddings | Qwen3-Embedding 8B | ~5–6 GB | Batch | Ollama (`ollama pull qwen3-embedding`) |

> **⚠️ Backend-Realität (Stand 2026-07-01):** Die „Backend"-Spalte zeigt den **Config-Default** (`ollama` — Modell-Refs oben). **Produktiv läuft der ganze Cycle aber auf llama.cpp:** `scheduled_cycle.sh` setzt `STAGE_8B_BACKEND`/`EMBED_BACKEND`/`STAGE5_BACKEND=llamacpp`, sodass **alle** LLM-Stages (Relevanz/Extraktion/Klassifizierung/Reclassify auf dem 208K-8B, Embeddings, Content-Gen auf dem Gemma-4-26B) über den **llama-server (:8090)** laufen — Beleg: ein realer Cycle machte 3.922 `/v1/chat/completions` + 60 `/v1/embeddings` auf :8090 und **0** Inferenz-Calls auf Ollama. Ollama bleibt der **Default/Fallback** (greift nur, wenn `STAGE*_BACKEND=ollama`), plus optional `CLASSIFY_BACKEND=anthropic` für Stages 2/3/4/8 off-GPU.
>
> **Kein Ollama-Zwang mehr im Full Cycle:** `run_full_cycle` erkennt seit 2026-07-01 die aktiven GPU-Backends. Läuft alles auf llama.cpp, wird der frühere Ollama-Preflight (`check_ollama` + `check_gpu` lädt qwen3:14b als CPU-Offload-Canary) **übersprungen** und stattdessen `check_gpu_nvidia_smi()` genutzt (nur `nvidia-smi`, kein Modell-Load). → **Ein llama.cpp-Cycle braucht Ollama nicht** (nicht mal laufend). Nur wenn ein GPU-Stage auf `ollama` steht, wird Ollama geprüft/benötigt.
>
> **Hybrid-Klassifikation ist Default im RSS-Cycle (seit 2026-07-11, #41, `7d03d14`):** `RSS_CLASSIFY_MODE=hybrid` — embed-first, dann **Distill-Embedding-Heads** für Vertical/Mega/PESTEL (GPU-frei, Sekunden statt Minuten). Relevanz als **Hybrid-Gate**: Distill entscheidet die sicheren Ränder (≥0.7 behalten, <0.3 verwerfen), nur das unsichere Band geht ans 8B (~21 % real). Extraktion (Markennamen) + Content-Gen bleiben LLM. Embeddings werden persistiert (auch für Gefilterte — Trend-Drift-Hedge), Stage 5 macht nur noch Dedup. Fallback: `RSS_CLASSIFY_MODE=llm` = alter Voll-8B-Pfad; lädt der Head nicht, fällt der Cycle automatisch zurück. Referenzwerte Prod-Cycle 2026-07-12: 0 Fehler, Stage-8-Korrekturquote ~3,5 % (Drift-Wächter: Retrain bei dauerhaft >30 % oder 8B-Band >35 %).
>
> **Signaltyp auf dem Distill-Pfad (#110, seit 2026-09-25 auf `dev`, Default AUS):** die vier Heads geben keinen `trend_signal_type` aus; `llm_processor._distill_signal_type` (auch von `scripts/signal_batch.py` genutzt) leitete ihn seit dem 14.07. allein aus der Quellenart ab — Patentnummer → `patent`, Forschungsquelle → `research`, NSF/NIH/UKRI/Form D → `funding`, **alles andere → `market_shift`**. Folge: seit dem 14.07. bekam jeder Presse-Artikel `market_shift` (product_launch 10, regulation 27, partnership 2, consumer_behavior 2 gegen 89 k / 76 k / 13 k / 10 k davor), die acht Schreibanweisungen in `SIGNAL_TYPE_FRAMING` kollabierten für Presse auf eine, der Richter beanstandete Partnerschaftsmeldungen als „kein Signal", und der Signaltyp-Filter war blind. Abhilfe: ein **fünfter Head** `models/distill/signal_type.joblib` (`scripts/train_signal_type_head.py`, eigenes Skript, fasst die vier anderen nicht an; Teacher = die 553 k vom LLM-Pfad gelabelten Presse-Zeilen vor dem 14.07.; SGD log-loss, `class_weight='balanced'`; Holdout: market_shift P 0,92 / R 0,81, product_launch F1 0,72, regulation 0,68, partnership 0,59, consumer_behavior 0,51; Genauigkeit 0,88 ab Konfidenz 0,6, 0,92 ab 0,7). `DistillClassifier` lädt ihn, wenn die Datei existiert, und liefert `signal_type` + `signal_type_confidence`; die Regel bleibt für patent/research/funding maßgeblich, der Head entscheidet nur die fünf Presse-Klassen und **nur** mit `DISTILL_SIGNAL_TYPE=1` und Konfidenz ≥ `DISTILL_SIGNAL_TYPE_MIN_CONF` (Default 0,6 — dort trifft die Verteilung auf den 48 k Presse-Zeilen seit dem 14.07. die historische: market_shift 64 %, regulation 18 %, product_launch 13 %, partnership 3,6 %, consumer_behavior 1,8 %; vorher 71 / 12 / 13 / 2,4 / 1,6), sonst `market_shift`. Bericht `docs/signal_type_head_2026-09-25.md`, Rohdaten `data/signal_type_head_report.{json,md}`. Der Bestand seit dem 14.07. ist NICHT nachgezogen (Stufe 2, Owner-Entscheid); das Modell liegt je Worktree (`models/` ist gitignored — beim Merge nach `main` kopieren, wie bei den anderen Heads). Frontend (Stufe 3, `dev`): Signaltyp-Label auf der Trendkarte neben der Quelle, Feld `signal` in `trends/index.json`, Chip-Gruppe „Signal" in der Export-Suche (`#signal=`).

**Alternative Modelle zum Testen:**
- Relevanz-Filter: Gemma 3 4B (`ollama pull gemma3:4b`, ~3.5 GB) – noch schneller
- Extraktion: Qwen3 8B mit Structured Output als Alternative zu NuExtract
- Content-Gen: Qwen3.5 9B (`ollama pull qwen3.5:9b`, ~6.6 GB) – neuer, kompakter
- Content-Gen: Mistral Small 3.2 24B – beste Sprachqualität, braucht aber CPU-Offloading
- Embeddings: jina-embeddings-v2-base-de (~323 MB) – speziell Deutsch+Englisch, minimaler VRAM

### Pipeline-Ablauf pro RSS-Eintrag

```
RSS-Eintrag (Titel + Teaser + URL + Datum)
    │
    ▼
[Schritt 1] RELEVANZ-FILTER (Qwen3 8B)
    "Ist das ein relevantes Trend-Signal?"
    → ja/nein/grenzwertig + confidence score
    → Vertikale zuordnen: FOOD/TECH/HEALTH/ECO/DESIGN/FASHION/BIZ/LIFESTYLE
    → Wenn nein: archivieren als "gefiltert", Ende
    │
    ▼
[Schritt 2] STRUKTURIERTE EXTRAKTION (Qwen3 8B; NuExtract-Fallback deaktiviert)
    Template: {brand_name, product_name, source_type, key_claims,
               key_figures, dates, quotes, geography}  (Listen gedeckelt)
    → Rein extraktiv, nur Text der im Original steht; Temperatur: 0
    → Volltext-Grundlage (seit 2026-09-03, Compliance-Welle): der Fetcher
      (pipeline/article_fetcher.py) meldet sich als CatandaryTrendsBot/1.0
      (+https://catandary.de/trends/methodology — V2 seit 2026-09-11: Kontakt
      auf der Seite, nicht mehr in jedem Log), respektiert robots.txt UND maschinenlesbare TDM-Vorbehalte
      (TDM-Reservation-Header, meta tdm-reservation, robots noai, tdmrep.json;
      TDM_RESPECT=1) — bei Vorbehalt nur Titel/Teaser. 147 Quellen sind
      fulltext:true (3 Vorbehalts-Quellen + 10 Bot-Sperren am 03.09. auf
      false gesetzt, docs/compliance/tdm_probe_2026-09-03.md). raw_content
      wird 14 Tage nach Abruf genullt (Cron 03:30, §44b Abs. 2 S. 2 UrhG).
      Die Anreicherung (article_fetcher.fetch_batch) läuft seit 2026-09-08
      unmittelbar vor JEDEM LLM-Lauf des Cycles, also auch vor Phase 1
      (Backlog). Vorher stand sie nur zwischen Poll und Phase 3 — jeder
      Backlog-Eintrag, auch „Write again" aus dem Review-Desk, lief textlos
      (Teaser statt Artikel) in die Content-Generierung. Stage 1 (Titel-
      Dedup, get_recent_titles) ignoriert seither wie der Embedding-Dedup
      per Hand verworfene Zeilen (rejected + reviewed_at), sonst würde der
      zurückgezogene Vorgänger die Neufassung als Duplikat töten. „Write
      again" löscht außerdem den Stage-6-Content-Cache
      (raw_entries.content_en_json) — ohne das fügte der Cycle den
      verworfenen Text wortgleich wieder ein (564 von 813 am 08.09.) und
      scheiterte am eigenen Slug; eine Slug-Kollision bekommt seither ein
      -r2/-r3-Suffix (llm_processor.unique_slug) statt den Eintrag als
      „processed" zu verlieren.
      **Der geholte Volltext erreichte den Produktionspfad bis 2026-09-09
      gar nicht:** `run_pipeline_batch` (der Pfad, den der Cycle nutzt) las
      ausschließlich `entry["excerpt"]`, während `fetch_batch` in
      `raw_content` schreibt — nur der Einzel-Pfad `process_entry` griff
      seit #11 auf `raw_content` zu. Gemessener Unterschied bei Opt-in-
      Quellen: excerpt 124–456 Zeichen gegen raw_content 2.442–6.331
      (The Conversation 124 : 6.025). Der Batch-Pfad normalisiert jetzt
      einmalig nach dem Laden (`raw_content`, wenn länger als der Teaser).
    → **Mindest-Textbasis (Stage 0b, seit 2026-09-09, #97):** ein Eintrag
      mit weniger als `MIN_SOURCE_TEXT_CHARS` (Env, Default 80) Zeichen
      Quelltext wird VOR jedem LLM-Aufruf verworfen
      (`mark_filtered(… "insufficient_source_text")`, in beiden Pfaden).
      Grund: das Grounding-Gate prüft Zahlen/Namen GEGEN die Quelle — steht
      dort nichts, gibt es nichts zu prüfen und jede Modell-Erfindung
      rutscht mit 0 Flags durch. Genau so entstanden am 08.09. 187
      published Artikel aus den am 04.09. deaktivierten Vorbehalts-Quellen,
      deren excerpt der Purge geleert hatte (flüssig formulierte, frei
      erfundene Studieninhalte; alle 278 am 09.09. auf `rejected` +
      `review_reason='titleonly:tdm-reserved-source'` zurückgezogen).
      Schwellen-Herleitung an der Kohorte vom 08.09. (2.714 Trends):
      0 Zeichen 216, <80 247 (9,1 %), <200 770 (28 %) — 80 trifft das Loch,
      nicht den Normalbetrieb (Median 508 Zeichen).
    → **Deaktivierte Quellen liefern seit 2026-09-09 auch keinen Backlog
      mehr:** `get_unprocessed_entries` filtert zusätzlich auf
      `COALESCE(s.active, TRUE) = TRUE`. Vorher stoppte `active: false` nur
      das Polling — die schon geholten Einträge liefen weiter in die
      Content-Generierung, weshalb die am 04.09. abgeschalteten 33 Journale
      am 08.09. noch einmal 187 Artikel erzeugten.
    → EXTRACTION_STRICT=1 (Default seit 2026-08-21): alle Felder Pflicht,
      quotes/geography werden auf Wörtlichkeit gefiltert (~5,3 s/Artikel)
    → key_figures kommen NICHT vom Modell: deterministisch per Regex aus der
      Quelle, jeder Eintrag mit wörtlichem Satzkontext (figures_with_context)
    → Alle Felder gehen in den Content-Prompt von Schritt 5 (seit 2026-08-21;
      vorher nur brand/product/claims — Artikel dadurch ~170 statt ~110 Wörter)
    │
    ▼
[Schritt 3] NER + KLASSIFIZIERUNG (Qwen3 8B)
    Structured Output mit Pydantic-Schema:
    {
        verticals: ["FOOD", "HEALTH", ...],  // Kann cross-vertical sein
        pestel: ["T", "S", "En"],  // PESTEL-Dimensionen
        tags: ["protein", "ai-powered", "circular", ...],
        trend_signal_type: "product_launch" | "research" | "market_shift" |
                           "consumer_behavior" | "regulation" | "funding" |
                           "partnership" | "patent",
        regions: ["US", "EU", "APAC", "Global", ...],
        mega_trend: "Personalized Nutrition" | "Generative AI" | "Circular Economy" | ...
    }
    → Temperatur: 0
    │
    ▼
[Schritt 4] DUPLIKAT-CHECK (Qwen3-Embedding)
    → EIN Vektorraum: `embedding`/`embedding_1024` = title + excerpt[:500]
      (Median 588 Zeichen). Für den Dedup richtig gewählt; NICHT verbreitern
      (1,7 Mio. Zeilen, geänderte Semantik).
      *(Der zweite Raum `embedding_full_1024` über den vollen Quelltext, #102,
      lief vom 10.–11.09.2026 und wurde vom Owner zurückgebaut: Messung über
      95.023 Zeilen ohne Gewinn gegenüber dem Dedup-Vektor, weil 95 % der
      Zeilen gar keinen längeren Text haben — docs/embedding_eval_2026-09-11.md.
      Spalten bleiben additiv stehen, nichts liest sie; Cron/Skripte entfernt.)*
    → Embedding generieren
    → Cosine-Similarity gegen letzte 30 Tage prüfen
    → Wenn >0.92 Similarity: als Duplikat markieren, Ende
    │
    ▼
[Schritt 5] CONTENT-GENERIERUNG EN (llama.cpp Gemma-4-26B / Ollama 14B)
    → Eigener Trend-Artikel (~100 Wörter; Owner-Festlegung 2026-08-19.
      Der Prompt fragt weiterhin 150-250 — hoch fragen ist das, was ~100
      erzeugt. Guard-Untergrenze STAGE5_TARGET_BODY_WORDS=100.)
    → Analytischer, professioneller Ton
    → Quellennennung + Backlink Pflicht
    → MUSS sich substanziell vom Original unterscheiden
    → HARD RULE Sprache: title + body IMMER Englisch, auch bei
      nicht-englischer (z. B. deutscher) Quelle → übersetzen, nie echoen
    → Temperatur: 0.6-0.8
    → Identitäts-Check (#98): vor jedem Request/Retry muss /v1/models das
      erwartete GGUF nennen, sonst Stage-Abbruch (Einträge bleiben unprocessed)
    → Quelltext im Prompt: nur der ANFANG, STAGE6_SOURCE_MAX_CHARS (Env,
      Default 4000 = die bisherige Kappe; die Extraktion liest 12.000 und
      liefert Zahlen/Daten/Zitate der hinteren Hälfte). Bewusst nicht
      angehoben: die 22 Garbage-Bodies vom 05.09. entstanden ausschließlich
      bei Prompts an dieser Kappe (User-Prompt ≈ 5k Zeichen ≈ 2k Tokens =
      -ub-Grenze des Gemma-Starts). Repro: scripts/repro_stage6_garbage.py
      (GPU, on demand, drei Arme: Produktion / cache_prompt=false / 2000 Zeichen).
    → Schlusssatz ist OPTIONAL (Owner 2026-09-24). Bis dahin verlangte der
      Prompt "Close with a concrete, falsifiable consequence" — ein Pflicht-
      Ausblick, den der Draft-Richter anschließend als quellenfremd
      beanstandete (2 von 25 Stichprobenfällen waren quellentreue Artikel,
      deren einziger Einwand dieser erzwungene Schluss war). Jetzt: nur
      schreiben, wenn die Quelle ihn trägt, sonst mit der letzten Tatsache
      enden.
    → Prompt-Regel (seit 2026-09-05): "Never add first names, titles,
      affiliations, dates or figures that are not in the source; refer to
      people exactly as the source does."
    → Wort-Untergrenze (STAGE5_TARGET_BODY_WORDS=100) wird seit 2026-09-24 nur
      noch eingefordert, wenn die Quelle mindestens
      STAGE5_BREVITY_MIN_SOURCE_CHARS=1000 Zeichen hergibt. Darunter ist sie ein
      Dünne-Quelle-Melder: das Modell kann keine Wörter schreiben, die in der
      Quelle nicht stehen, liefert dreimal dieselbe kurze Antwort und die wird
      nach aufgebrauchtem Budget ohnehin genommen. Gemessen an 5.355 Artikeln
      (22.–24.09.): 242 der 250 Dauer-Fehlschläge kamen aus Quellen unter 1.000
      Zeichen, darüber 0,2 % (8 von 4.352). In der Nacht auf den 24.09. kostete
      das 86 × 2 volle Generierungen auf dem 26B. Stub-Grenze
      (STAGE5_MIN_BODY_WORDS=25), Truncation, Klischee, Obergrenze und
      Grounding gelten unverändert bei jeder Quellenlänge.
    → HARTER Garbage-Guard (#11, 2026-09-05; pipeline/content_guard.py):
      Nicht-Latein-Anteil > 0,5 %, Wort ≥ 4× in Folge / "URLURLURL",
      Unikat-Anteil < 35 %, < 60 Wörter, Nicht-Wort-Zeichen > 25 %,
      Leerraum-Runs, Script-Leak gegen die Quelle → frischer Request OHNE
      Prompt-Cache (cache_prompt=false); nach 3 Versuchen GarbledOutputError:
      NICHTS wird gespeichert, der Eintrag bleibt unprocessed (kein
      mark_filtered). Vorher gab chat_structured nach dem Soft-Guard-Budget
      das letzte Ergebnis trotzdem zurück — so wurden am 05.09. 22 Token-
      Suppen mit Confidence bis 0,93 zu Drafts. Der Soft-Guard (Cliché,
      Länge, Grounding) behält seine "nach Budget akzeptieren"-Semantik.
    │
    ▼
[Schritt 6] ÜBERSETZUNG DE — ENTFÄLLT (seit ~2026-06)
    → DE-Content wurde geskippt: `title_de`/`summary_de`/`body_de` bleiben NULL.
      Pipeline erzeugt nur EN-Content (`title_en`/`body_en`). Die DE-Spalten im
      Datenmodell bleiben für evtl. spätere Reaktivierung erhalten, werden aber
      nicht mehr befüllt.
    │
    ▼
[Schritt 7] INSERT (trends Tabelle, Status: "draft")
    │
    ▼
[Schritt 8] RECLASSIFY (Qwen3 8B)
    → Vertikale per LLM-Semantic-Check korrigieren
    → Fängt Fehlklassifizierungen aus Schritt 3 ab
    → Nur Drafts mit `reclassified_at IS NULL` (seit 2026-09-24): ein schon
      eingeordneter Draft bekommt bei Temperatur 0 dieselbe Antwort noch
      einmal. Belegt über vier Nächte: 0 Änderungen an ~9.600 alten Drafts
      je Pass, alle 380 Änderungen vom 24.09. in der ID-Spanne derselben
      Nacht. 63 → ~6 Minuten je Lauf.
    │
    ▼
[Schritt 9] AUTO-PUBLISH
    → Status: "draft" → "published" wenn confidence >= 0.85
    → Niedrigere Confidence bleibt als Draft für manuelles Review
    → Gates (Reihenfolge, jedes hält den Draft für /trends/review):
      garbled (content_guard, Body gegen Quelle) → truncated (#18) →
      ungrounded specifics (Zahl/Jahr/Prozent/Geld nicht in der Quelle, #11)
      → ungrounded person names (grounding.ungrounded_names, #11 seit
      2026-09-05: "Henkel-Chef Knobel" darf nicht als "Henkel CEO Markus
      Knobel" live gehen — Vorname aus pipeline/first_names.py oder Titel
      davor, jedes Wort muss in Titel+Teaser+Volltext+Extraktion stehen).
      Zähler: held_garbled / held_truncated / held_fabricated / held_names.
    │
    ▼
[Schritt 10] DRAFT-RICHTER (Qwen3.8-27B lokal; seit 2026-08-22, DRAFT_JUDGE=0 schaltet ab)
    → Beurteilt die frischen Drafts UNTER der Schwelle redaktionell
      (Kriterien der Haiku-Volldurchsicht: 71,6 % davon sind publizierbar,
      Confidence trennt kaum — docs/confidence_threshold_entscheidung_2026-08-21.md)
    → publish nur bei signal=true UND Kategorie ok; sonst ZURÜCKHALTEN, nie verwerfen
    → Jede Freigabe durch dieselben Gates wie Auto-Publish: Garbage,
      Truncation, Grounding (Zahlen + Personennamen), pgvector-Dedup gegen
      Published (pipeline/draft_judge.py). Garbage-Kandidaten gehen VOR dem
      Richter nach status='review' + review_reason='garbled:…' (divert_garbled,
      judged_at gestempelt) — Token-Suppe ist keine Ermessensfrage.
    → **Textbasis des Richters (seit 2026-09-24):** 12.000 Zeichen Quelle
      (`JUDGE_SOURCE_MAX_CHARS`) **plus die Extraktionsfelder**
      (`JUDGE_EXTRACTION_MAX_CHARS=1500`) — also dieselbe Grundlage, aus der
      Stage 6 geschrieben hat. Vorher sah er fest 4.000 Zeichen und damit
      WENIGER als der Schreiber: die Extraktion liest 12.000 und reicht Zahlen,
      Namen, Daten und Zitate aus dem hinteren Teil in den Content-Prompt. Der
      Artikel trug dadurch zu Recht Angaben, die der Richter nicht finden
      konnte — und er nannte sie erfunden. Stichprobe 24.09. (25 gehaltene
      Drafts, neu beurteilt und von Hand gegen die Quelle gelesen): **5 der 10
      `source_mismatch`-Urteile falsch**, die beanstandete Angabe stand bei
      Position 4.005 („invents African ancestry"), 4.012 (Anmeldefrist), 4.033
      (Ökonomenname), 5.111 (Augustiner) und 7.021 (carbon fibre). Gegenprobe
      an 8 Drafts mit langer Quelle: 4 `source_mismatch` bei 4.000 Zeichen,
      1 bei 12.000 + Extraktion. Preis: 2,2 → 3,2 s je Artikel, Stage 10 also
      ~22 → ~32 min. Richtig lag er bei 3 von 10 (115-Zeichen-Bildunterschrift,
      261-Zeichen-Teaser, ein echter Zahlendreher in einer ungarischen Quelle:
      2,8 % Fettgehalt als Preisänderung gelesen).
    → Jeder beurteilte Draft wird judged_at-gestempelt und nie erneut
      beurteilt (seit 2026-08-25 — vorher richtete der Judge dieselbe
      gehaltene Kohorte jede Nacht neu und die frischen Drafts verhungerten
      am 600er-Limit); Kandidaten holen sich vorher fehlenden Volltext
      (nur Opt-in-Quellen, fulltext_filled in der JSON)
    → GPU-Handover mit zwei Guards (seit 2026-08-26): VRAM-Vorab-Check
      (27B lässt nur ~1.1 GB Reserve — Fremdbelegung → SKIP mit klarer
      Diagnose statt 240s-Timeout) + Modell-Identitäts-Check gegen
      /v1/models (llama-server ignoriert den model-Namen im Request —
      ohne Check würde ein geplatzter Symlink-Swap den Richter still
      aufs 8B schicken). E2E-getestet 2026-08-26.
    → auto_published=true; Zahlen → data/draft_judge_last.json → Morgen-Mail
```

**Ein Publish von Hand ist endgültig (Owner-Regel 2026-09-22).** Drückt der
Owner auf `/trends/review` *Publish*, ist die Sache entschieden — auch gegen
einen weiter widersprechenden Prüfer und auch ohne einen Agent-Vorschlag
anzuwenden. Anlass: das Namens-Gate beanstandete „Per Second" aus „Tokens Per
Second (TPS)" — kein Personenname, nichts zu reparieren. Marke ist `reviewed_at`
(jede Handentscheidung setzt es); `scripts/recheck_published_grounding.py`
überspringt solche Zeilen in der Auswahl UND im UPDATE (`--include-reviewed`
hebt es für einen bewussten Audit auf), der Review-Agent nimmt nur
`reviewed_at IS NULL`, Stage 9 nur Drafts. Test:
`tests/test_human_publish_is_final.py`.

**Stage 11: Review-Agent (seit 2026-09-22, `REVIEW_AGENT=0` schaltet ab).**
Nach dem Richter prüft `scripts/review_agent.py --handover --apply` die Drafts,
die ein Gate zurückhält, auf **Äquivalenz statt Wortgleichheit**: ist die
beanstandete Zahl dieselbe Angabe in anderer Form („1 000"/„1,000",
„Seventy percent"/„70 %", 6,100万人/61 million, „23 heures"/„11:00 PM",
„2015-25"/2025) und nennt die Quelle die Person wirklich? Jede Bestätigung
braucht ein **wörtliches Quellzitat**, das gegen den Quelltext geprüft wird —
das Modell kann nur bestätigen, was dasteht. Namen entscheidet eine
deterministische Regel (Titel zählen nicht zur Identität, Nachname wortweise,
Tippfehler-Toleranz bei Vornamen), andere Schriften ein **zweiter, blinder
Durchgang**, der nur die Quellform romanisiert. Ergänzte Vornamen werden
korrigiert und das Ergebnis durch dieselben Gates geschickt wie Auto-Publish.
Beim Menschen bleiben: Rollen-Halluzinationen („the Foreign Secretary" → ein
Name aus dem Modellwissen), fehlende Personen, abweichende Schreibweisen,
ungeklärte Transliterationen — mit Klasse, Beleg und Ein-Klick-Vorschlag auf
`/trends/review`. Eigener Kollisionswächter (`scheduled_cycle-agent`), eigener
GPU-Handover auf das Content-Gen-Modell, Ruhezustand danach wiederhergestellt;
Zahlen → `data/review_agent_last.json` → Morgen-Mail. Erste Messung 22.09.:
von 183 Holds 100 äquivalent, danach 15 weitere repariert.
`REVIEW_AGENT_APPLY=0` lässt ihn nur prüfen.

**KI-Kennzeichnung je Artikel (#99, seit 2026-09-06, EU AI Act Art. 50 Abs. 4).**
Alles oben ab Schritt 5 ist Maschinenarbeit, und die Schritte 9/10 sind
ausschließlich automatische Gates — auch der Draft-Richter ist ein Modell. Ein
veröffentlichter Feed-Artikel wird also **von keinem Menschen gelesen, bevor er
erscheint**; damit greift die Kennzeichnungspflicht aus Art. 50 Abs. 4
unabhängig vom laufenden Anwaltsergebnis (die von der Kommission angebotenen
EU-Icons sind fakultativ und werden nicht verwendet). Jede Seite `/trends/<slug>`
trägt deshalb **direkt unter Titel/Meta-Block** — nicht im Fuß — ein
aufklappbares Kennzeichen (`frontend/src/components/AiArticleDisclosure.tsx`,
natives `<details>`, ohne JS bedienbar): sichtbar „AI-generated / not reviewed
by a person", darin der volle Satz `ARTICLE_DISCLOSURE_EN` aus
`frontend/src/lib/aiDisclosure.ts`:

> This article was generated by a local language model from the single source
> linked below, checked automatically against that source, and published
> without a person reading it beforehand.

Jede Teilaussage ist an eine reale Pipeline-Eigenschaft gebunden (lokales Modell
= Stage 6 auf der Workstation-GPU; *single source* = ein `raw_entry`/eine
`source_url`; *checked automatically* = Grounding + `content_guard` + Dedup;
*without a person* = Auto-Publish/Draft-Richter). Wird der Pfad je um eine
menschliche Durchsicht ergänzt, ist der letzte Halbsatz falsch und muss weg.
Maschinenlesbar zusätzlich (es gibt dafür **keinen** verbindlichen Standard):
`<meta name="generator">` auf der Artikelseite und im Article-JSON-LD
`creator` = `SoftwareApplication` (mit demselben Satz als `description`) neben
`author` = Organization Catandary sowie `isBasedOn` = Quell-URL.

**Abgrenzung zum Newsletter:** dort greift seit 2026-09-06 die Freigabepflicht
(ein Mensch liest und verantwortet), deshalb sagt `AI_DISCLOSURE_EN` das
Gegenteil über den Menschen und ist die richtige Konstante für Mail und
Website-Edition. Auf `/analysis` schreibt der Owner selbst — dort steht
bewusst keine Kennzeichnung.

### Structured Output: Produktionsreife Absicherung

```python
from pydantic import BaseModel
from ollama import chat
from typing import Literal
import time

class TrendSignal(BaseModel):
    is_relevant: bool
    confidence: float
    primary_vertical: Literal["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]
    brand_name: str | None
    categories: list[str]
    tags: list[str]
    trend_signal_type: Literal[
        "product_launch", "research", "market_shift",
        "consumer_behavior", "regulation", "funding"
    ]

def extract_with_retry(model: str, prompt: str, schema, max_retries: int = 3):
    """Structured extraction mit Retry-Loop und Fallback."""
    for attempt in range(max_retries):
        try:
            response = chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                format=schema.model_json_schema(),
                options={"temperature": 0}
            )
            result = schema.model_validate_json(response["message"]["content"])
            return result
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            # Fallback auf anderes Modell
            try:
                response = chat(
                    model="qwen3:8b" if model != "qwen3:8b" else "nuextract",
                    messages=[{"role": "user", "content": prompt}],
                    format=schema.model_json_schema(),
                    options={"temperature": 0}
                )
                return schema.model_validate_json(response["message"]["content"])
            except:
                return None  # Log als Fehler, manuell reviewen
```

---

## Datenmodell

```sql
-- Quellen-Registry
CREATE TABLE sources (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    feed_url TEXT NOT NULL,
    source_type TEXT CHECK (source_type IN ('trade_media', 'press_wire', 'brand', 'api', 'radar')),
    vertical TEXT CHECK (vertical IN ('FOOD','TECH','HEALTH','ECO','DESIGN','FASHION','BIZ','LIFESTYLE','CROSS')),
    sub_categories JSONB DEFAULT '[]',
    active BOOLEAN DEFAULT true,
    auto_discovered BOOLEAN DEFAULT false,
    discovery_count INTEGER DEFAULT 0,
    last_fetched TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rohdaten aus Feeds
CREATE TABLE raw_entries (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id),
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    excerpt TEXT,
    raw_content TEXT,
    published_date TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT false,
    filtered_out BOOLEAN DEFAULT false,
    filter_reason TEXT
);

-- Kuratierte Trend-Artikel
CREATE TABLE trends (
    id SERIAL PRIMARY KEY,
    raw_entry_id INTEGER REFERENCES raw_entries(id),
    title_en TEXT NOT NULL,
    title_de TEXT,                     -- *_de-Spalten bleiben NULL (DE-Content seit ~2026-06 geskippt, Spalten für spätere Reaktivierung erhalten)
    slug TEXT UNIQUE NOT NULL,
    summary_en TEXT,
    summary_de TEXT,
    body_en TEXT,
    body_de TEXT,
    -- Catandary-Taxonomie
    verticals JSONB DEFAULT '[]',     -- ["FOOD", "HEALTH"] (cross-vertical möglich)
    primary_vertical TEXT,             -- Haupt-Vertikale für Routing
    pestel JSONB DEFAULT '[]',        -- ["T", "S", "En"]
    tags JSONB DEFAULT '[]',
    trend_signal_type TEXT,
    -- Mega/Macro/Micro (Foresight-Teaser)
    mega_trend TEXT,
    macro_trend TEXT,                  -- Nur auf Foresight voll sichtbar
    trend_level TEXT CHECK (trend_level IN ('mega', 'macro', 'micro')),
    -- Entitäten
    brands JSONB DEFAULT '[]',
    companies JSONB DEFAULT '[]',
    -- people: gibt es in der Live-DB NICHT (Schema-Check 2026-09-02); brands/companies = Organisationen
    regions JSONB DEFAULT '[]',
    -- Scoring
    trend_score REAL,
    confidence REAL,
    -- Quelle
    source_url TEXT NOT NULL,
    source_name TEXT,
    -- Embeddings (qwen3-embedding = 4096-dim; pgvector ANN-Index cappt bei 2000 → für indizierte Suche truncaten)
    embedding VECTOR(4096),
    -- Status
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'published', 'rejected', 'signal')),
    auto_published BOOLEAN DEFAULT false,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    -- seit dem Ursprungs-Schema dazugekommen (Live-DB 2026-09-02): sort_date, embedding_1024
    -- (pgvector-ANN auf dem 1024er-Matryoshka-Präfix), grounding_flags, grounding_checked_at,
    -- reviewed_at, judged_at (Draft-Richter), reclassified_at (Stage-8-Stempel, 24.09.)
);

-- Engagement-Tracking (für späteres Foresight-Feedback)
CREATE TABLE trend_metrics (
    id SERIAL PRIMARY KEY,
    trend_id INTEGER REFERENCES trends(id),
    page_views INTEGER DEFAULT 0,
    unique_visitors INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    newsletter_clicks INTEGER DEFAULT 0,
    avg_time_on_page REAL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cross-Vertical Trend-Cluster (für Foresight)
CREATE TABLE trend_clusters (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    verticals JSONB DEFAULT '[]',
    pestel JSONB DEFAULT '[]',
    mega_trend TEXT,
    trend_ids JSONB DEFAULT '[]',     -- Array von trend.id
    cluster_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Automatisierung & Scheduling

### Cron-Jobs (realer Stand 2026-09-22 = `crontab -l`; Deploy-Template `deploy/crontab.txt` ist damit synchron)

**Zeitplan-Änderung 2026-09-22 (Owner):** die gesamte Wochentags-Kette startet **1 h 15 min früher** — der Quellenausbau auf 560 Feeds hat den Nachtlauf von knapp 3 h auf gemessene 3:48–5:26 verlängert, er endete zuletzt erst 08:44–09:24 und blockierte das Review beim Frühstück. Neu: 01:30 Backup · 02:00 Static Export · 02:15 Retention · 02:30 Lizenz-Auflösung · 02:45 Full Cycle · Di 03:45 Patent-Sweep · Di 06:45 Patent-Rechnungen · Di 07:45 Newsletter-Edition. **Nicht verschoben:** der Wächter (07:45, s. u.) und alle Wochenend-/Monatsjobs.

```
# Env-Zeilen sind Pflicht: cron hat keine systemd-User-Session — ohne
# XDG_RUNTIME_DIR schlagen die GPU-Handover (`systemctl --user`) still fehl.
XDG_RUNTIME_DIR=/run/user/1000
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

# Full Cycle Mo–Fr 02:45 (bis 2026-09-22: 04:00 — der Owner hat die ganze
# Wochentags-Kette um 1 h 15 min vorgezogen, damit der Lauf beim Frühstück
# fertig ist; nach dem Quellenausbau auf 560 Feeds dauert er 3:48–5:26 statt
# knapp 3 h und endete zuletzt erst 08:44–09:24.)
# (Feed-Polling + LLM-Pipeline + Auto-Publish in einem
# Lauf via scheduled_cycle.sh; Wrapper räumt vorher ALLES VRAM frei, auch
# manuell gestartete llama-server). Log: ~/logs/catandary-full-cycle-*.log
# VRAM-Freiräumen tötet seit 2026-09-10 nur noch Prozesse, die laut nvidia-smi
# wirklich VRAM halten (--query-compute-apps). Das frühere pauschale
# `pkill -f build/bin/llama-server` erwischte auch den CPU-Embedder auf :8091
# (0 MiB VRAM), der Vektorsuchen abseits der GPU bedient — er lag nach dem
# ersten Nachtlauf tot da. Die Unit hat jetzt zusätzlich Restart=always.
# Kollisionswächter (#98, seit 2026-09-05, scripts/lib/gpu_guard.sh): Wrapper
# UND scheduled_cycle.sh warten vor dem VRAM-Freiräumen, bis kein fremder
# GPU-Job läuft (Ingester, Pulse, Deep Dive, zweiter Cycle;
# max GPU_GUARD_MAX_MIN=90 min), sonst Abbruch mit rc=75 ohne etwas anzufassen
# (end-Zeile → Wächter-Mail). Vor Stage 10 dasselbe (30 min → Richter-Skip);
# der Ruhezustand wird am Ende nicht hergestellt, wenn inzwischen ein fremder
# Job die Unit hält (er stellt ihn selbst her).
# Stage 8 fragt seit 2026-09-24 nur noch die Drafts, die er noch nicht
# eingeordnet hat (`trends.reclassified_at IS NULL`, additive Migration
# `_migrate_reclassified_at`, in `init_db`; der Bestand wurde beim Anlegen der
# Spalte einmalig gestempelt). Vorher lief JEDER Pass über ALLE Drafts — bei
# Temperatur 0 und unverändertem Titel+Summary kommt dabei dieselbe Antwort
# heraus wie in der Nacht der Anlage: der Pass über den stehenden Bestand
# meldete vier Nächte in Folge 0 Änderungen (0/9.353, 0/9.397, 0/9.624), und
# alle 380 Änderungen vom 24.09. lagen im ID-Bereich derselben Nacht. Kosten
# waren 63 von 273 Minuten je Lauf plus ~21.000 UPDATEs/Nacht auf eine Tabelle
# mit HNSW-Indizes. Jetzt ~6 min. Ein Draft mit Klassifikationsfehler bleibt
# ungestempelt und kommt wieder; `reclassify_drafts(force=True)` nimmt bewusst
# den ganzen Bestand (nach Taxonomie- oder Prompt-Änderungen).
# Leerlauf-Schutz (seit 2026-09-09): Stage 8 + Stage 9 laufen nur, wenn die Phase Trends angelegt hat;
# Phase 3 und run 2 entfallen, wenn im Backlog nur Einträge stehen, die
# Stage 6 im selben Lauf garbled liegen ließ (`garbled_ids` in
# data/cycle_log.jsonl, `run_full_cycle.remaining_backlog`). Anlass 09.09.:
# ein einziger Garbage-Eintrag (ArchDaily 827670, danach per mark_filtered
# stillgelegt) kostete vier Reclassify-Pässe = 1,5 h. Solche Dauer-Garbled
# bleiben absichtlich unprocessed und kommen im NÄCHSTEN Cycle noch einmal
# dran — wiederholt sich das über mehrere Nächte, per Hand filtern.
# Batch 3000 (seit 2026-09-10; vorher 600). So bemessen, dass ein normaler Tag in
# EINEM Lauf durchgeht: mit 600 sprang run 2 an jedem Tag an und kostete jedes Mal
# einen zweiten kompletten Stage-8-Pass (damals Reclassify über ALLE Drafts,
# ~28 min; seit 24.09. kostet ein zweiter Pass fast nichts mehr).
# Gemessener Anfall: 1.509–1.619/Tag mit 474 Quellen, stationär ~2.460 mit 560.
# Zu hoch kostet nichts — min(batch, vorhandene); gegen Massen-Ingest schützen
# CYCLE_MAX_PER_SOURCE und die 50k-Sanity-Zählung. CYCLE_BATCH=N hebt ihn für
# eine einzelne Nacht weiter an.
45 2 * * 1-5  scripts/full_cycle_cron.sh

# Waechter 07:45 — liest seit 23.09. auch die Stage-Bilanz des Cycles
# (scheduled_cycle.sh end … rc1/rc2/rc3/agent): ein Wert != 0 ist eine Mail wert,
# auch wenn der Wrapper mit rc=0 endete. Anlass: Stage 11 stuerzte am 23.09. ab
# und niemand erfuhr es. `agent=-` = Stage abgeschaltet, kein Defekt.
# BEWUSST NICHT mitverschoben (22.09.): er meldete bis dahin
# jeden Werktag faelschlich "still running", weil der Cycle um 07:45 noch lief;
# mit dem frueheren Start findet er einen fertigen Lauf vor.
# (seit 2026-08-17): meldet per Mail, wenn der Nachtlauf keine
# end-Zeile mit Exit-Code geschrieben hat. Der Wrapper schreibt sie als letzte
# Handlung — stirbt er vorher (Stromausfall 17.08.), fehlt sie einfach und
# niemand merkt es. Schweigen = alles in Ordnung. Wochenenden sind ausgenommen.
# Seit 2026-08-24 prüft er zusätzlich das heutige Backup-ARTEFAKT (existiert
# catandary-pg-<Datum>.dumpdir, toc.dat da, ≥1 GB?) — Log-Zeilen zählen nicht.
45 7 * * *   cd <repo> && .venv/bin/python -m scripts.cycle_watchdog

# DB-Backup (täglich 01:30, bis 22.09. 02:45). Seit 2026-08-24: pg_dump -Fd -j4 + zstd:3 →
# catandary-pg-<Datum>.dumpdir (~113 GB, ~18 min), verifiziert per
# pg_restore --list gegen die Live-Tabellenzahl, Fehler FATAL. Der alte
# -Fc/-Z6-Dump lief ab 13.07. jede Nacht in den 1-h-Timeout, wurde als
# "non-fatal" verschluckt und meldete trotzdem "backup OK" — 42 Nächte ohne
# restaurierbares Postgres-Backup. Restore: docs/restore_runbook.md.
# keep-days 4 = Owner-Entscheidung 2026-08-24 (~480 GB Steady-State).
30 1 * * *   .venv/bin/python scripts/backup_db.py --dest /mnt/data-hdd/backups/catandary --skip-sqlite --keep-days 4

# Newsletter-Website-Edition (Di 07:45, bis 22.09. 09:00; seit 2026-08-29; von Mo auf Di verlegt am
# 2026-09-11, Owner — die Wochenrechnung 'vor 7 Tagen' trifft an beiden Tagen
# dieselbe abgeschlossene ISO-Woche, geprueft): generiert die
# Vorwoche (deterministisch) nach newsletter_editions — /trends/newsletter
# zeigt sie sofort. KEIN Versand (der wartet auf #16/Launch).
# Optional (#96, NICHT gesetzt): NEWSLETTER_DEEP_DIVE=dry-run hängt nach der
# Edition den „Deep Dive of the Week"-Schritt an — seit 2026-09-19 schreibt der
# nur noch status "disabled" (Rechercheur = Scouting-Dossiers entfernt), kein
# Modell. Default off. docs/newsletter_deep_dive.md.
45 7 * * 2   scripts/weekly_newsletter_publish.sh

# Research Pulse (#73, INSTALLIERT 2026-09-18 — Owner; bis dahin nur Vorschlag, die Seite
# stand deshalb vom 05.09. bis 18.09. auf W35): Samstag 12:00 nach weekly_ingesters.sh;
# rechnet die Vorwoche für alle 28 Themes (Stats + KMeans ~15 s, Gemma-Absätze via
# GPU-Handover; gemessen 54–58 s je Woche, 19/28 Themes mit Text — unter 5 Papers kein Text).
# Idempotent (≥20 Themes gerechnet = no-op). Wächter-Notiz data/weekly_research_pulse_last.json →
# Montags-Morgen-Mail (review_notify.py); der „Recompute"-Knopf bleibt für Einzel-Themes.
0 12 * * 6   scripts/weekly_research_pulse.sh

# Field Watch (Pivot 2026-09-20, VORSCHLAG — scharf erst mit dem Merge nach main):
# Samstag 12:30 nach dem Pulse; Wochenblätter aller fields/<kunde>.yaml
# (scripts/field_watch.py --all), reine SQL-Messung ohne GPU (~40 s je Kunde),
# ohne Kundendateien no-op. Notiz data/weekly_field_watch_last.json → Montags-Mail.
# Die Kundenseite (trends/clients/<kunde>/, htpasswd) lädt der Owner von Hand hoch.
30 12 * * 6  scripts/weekly_field_watch.sh

# Statischer Export → Webspace (täglich 02:00, bis 22.09. 03:15; INSTALLIERT 2026-09-05): nach dem
# Review-Tag und ~45 min vor dem 02:45-Cycle — veröffentlicht wird der freigegebene Stand.
# build_public_static.sh + publish_static_site.py --apply, Log ~/logs/catandary-publish-*.log
0 2 * * *    scripts/publish_static_site.sh

# Volltext-Retention (täglich 02:15, bis 22.09. 03:30; INSTALLIERT 2026-09-03, Owner-Auftrag „100 % konform"):
# raw_content verarbeiteter raw_entries älter als 60 MONATE → NULL (§44b Abs. 2 S. 2 UrhG).
# Frist am 2026-09-10 von 14 Tagen auf 1825 Tage erweitert (Owner). Die Norm nennt keine
# Frist, sie bindet sie an den Zweck — dokumentierter Zweck ist die längsschnittliche
# Trendanalyse (Lead-Time Forschung→Patent→Funding→Markt läuft über Jahre). Der Kreis der
# Quellen wird NICHT erweitert: Vorbehalts-Quellen speichern weiterhin gar keinen Volltext.
# Vorbehalts-Quellen: purge_raw_content.py --source … --ignore-state --also-extraction
15 2 * * *   .venv/bin/python scripts/purge_raw_content.py --days 1825 --apply

# Volltext-Vektoren (#102, 09:00): am 2026-09-11 vom Owner ZURUECKGEBAUT — der
# zweite Vektorraum brachte keinen messbaren Gewinn (docs/embedding_eval_2026-09-11.md).
# Cron-Zeile, Wrapper und Skripte entfernt; kein Backfill, kein Lauf auf bequiet.

# Volltext-Nachhollauf (#102, on demand — KEIN Cron): die 14-Tage-Regel hat bis
# zum 10.09. 17.665 Volltexte geloescht (Purge-Log). Die Quell-URL steht noch in
# jeder Zeile, der erneute Abruf ist nach §44b zulaessig und seit der 60-Monats-
# Frist auch haltbar. Wiederbeschaffungsquote gemessen: 90 % (54 von 60).
#   scripts/refetch_fulltext.py --since 2026-07-12 --limit 0 --apply
# Der Altersfilter (--min-age-days, Default 15) ist der Kern: im 0-14-Tage-Band
# haben 70 % ihren Text noch, und die uebrigen 30 % sind die, bei denen der Abruf
# schon damals scheiterte — ein Lauf ohne Filter zieht gezielt die Fehlschlaege
# (gemessen 3 von 60 = 5 % gegen 54 von 60 = 90 %).

# Offen lizenzierte Artikel der Vorbehalts-Quellen freischalten (02:30, bis 22.09. 03:45,
# INSTALLIERT 2026-09-09, #97 Wege B+C): OpenAlex-Auflösung → Lizenzprüfung →
# Volltext von der OFFENEN Fundstelle (nie vom Vorbehalts-Host) → raw_content +
# open_licence. Ausbeute 12 % der Einträge, ~58 Artikel/Woche.
30 2 * * *   .venv/bin/python scripts/resolve_open_licence.py --limit 300 --apply
# --also-excerpt (nur mit --ignore-state) setzt die geleerten Zeilen seit
# 2026-09-09 im selben Zug auf processed + filtered_out +
# filter_reason='source_text_purged' — ein Eintrag ohne Quelltext ist nie
# wieder Artikelmaterial (Anlass: die 04.09.-Leerung liess die Zeilen im Pool).

# Source-Discovery-Loop (Sonntag 06:00)
0 6 * * 0    .venv/bin/python scripts/discovery_loop.py

# Monatlicher Quellen-Check mit Issue-Post (1. des Monats, 08:00)
0 8 1 * *    .venv/bin/python scripts/monthly_source_check.py --post-issue

# Wöchentlicher Patent-Sweep (Dienstag 03:45, bis 22.09. 05:00; --kind both = Cr-Del + Amend,
# Amend trägt CPC-Codes + Zitationskanten nach — hält den SPNP/TIR-Graph aktuell)
45 3 * * 2   scripts/weekly_patents.sh

# Patentbasierte Rechnungen nach dem Sweep (Dienstag 06:45, bis 22.09. 08:00; seit 2026-08-09):
# build_cpc_tier_series + build_cpc_insights + assign_cpc (alles CPU/SQL).
# Radare + TIR-/SPNP-Forschungsläufe bewusst NICHT im Cron (Owner: on-demand).
45 6 * * 2   scripts/weekly_patent_analytics.sh

# OpenAlex-Monats-Sync (5. des Monats 02:00, seit 2026-08-15, #80; 07:00→02:00 am 2026-08-29 entzerrt — Erstlauf 05.09. fällt auf einen Ingester-Samstag): neue
# Snapshot-Partitionen → research_corpus (45M-Suchschicht) + Journal-/
# Autoren-Nebentabellen + Statistik-Refresh (Amend-Analog, CPU/Netz)
0 2 5 * *    scripts/sync_openalex_monthly.sh

# Nicht-RSS-Ingester wöchentlich (Samstag 06:00, seit 2026-08-09; 05:00→06:00 am 2026-08-29 entzerrt): Preprints
# (arXiv/bioRxiv/medRxiv, 14-Tage-Fenster) + Funding (NSF/NIH/OpenAIRE/UKRI,
# 45 Tage) + SEC Form D (Vorquartal, nur im 1. Quartalsmonat) + sofortige
# Distill-Verarbeitung der Neuzugänge via signal_batch_embedded (GPU-Handover).
# Seit 2026-08-23 (#87) zusätzlich die Startup-Explorer-Signale: Presse-Regex,
# HN-Launches (30-Tage-Fenster), ClinicalTrials-Sweep, FDA-510(k)-Bulk.
# Seit 2026-08-28 (Owner) außerdem in den Signalraum: OpenAlex-Fresh-Sweep
# (zitationsfrei, 14-Tage-Fenster, Cap 1500/Konzept — läuft über den
# research-Distill-Schritt mit; seit 2026-09-05 (#73) mit Werk-Typ-Gate: nur
# article/preprint/review/book-chapter, Repository-Hosts Zenodo/figshare/
# GitHub … gesperrt, Typ → openalex_meta → research_signals.kind) + Patent-Signale (--patents-only: nur mit
# Abstract, rollendes 60-Tage-Publikationsfenster, Limit 60k/Lauf; der
# 19,6M-BDDS-Backlog bleibt bewusst außen vor).
# Signalbetriebs-Quellen (#97, seit 2026-09-09): eigener Schritt
# `signal_batch_embedded.py --signal-only --limit 20000` für alle Quellen mit
# `llm_pipeline = FALSE`. BEWUSST OHNE `--min-id`: der Wasserstand wird Samstag früh
# genommen, die Einträge dieser Quellen entstehen aber beim Poll Mo–Fr und liegen
# darunter — mit `--min-id` fände der Schritt konsequent 0 Zeilen (Befund 09.09., vor
# dem ersten Lauf). 30 der 33 sind `source_type=research` und liefen ohnehin mit; die
# drei `trade_media` und der stehende SEC-Form-D-Rest (1.584 Zeilen) fänden sonst keinen Lauf.
# Kollisionswächter (#98, seit 2026-09-05): jeder der drei GPU-Schritte
# (signal_batch_embedded) wartet per scripts/lib/gpu_guard.sh auf eine freie
# GPU (max 90 min), sonst SKIP — Ingests und CPU-Schritte laufen trotzdem; das
# min_id-Fenster wird in data/weekly_ingesters_pending_min_id gemerkt und beim
# nächsten Lauf nachgeholt; Status → data/weekly_ingesters_last.json →
# Montags-Morgen-Mail (review_notify.py, 60 h Frische). rc=75 bei Skip.
# Embedding-Fehlerpfad (#98 d): Server-/Verbindungsfehler (Connection refused,
# 5xx/429, Timeout) markieren in signal_batch NICHTS mehr — derselbe Chunk
# wird nach EMBED_ERROR_SLEEP=5 s erneut versucht, nach
# EMBED_MAX_CONSECUTIVE_ERRORS=20 Fehlern in Folge bricht der Lauf mit Exit 3
# ab (Wrapper-rc), alles Unverarbeitete bleibt unprocessed.
# filter_reason='embedding_error' nur noch für inhaltliche Fehler (der Server
# lehnt genau diesen Text ab). Reparatur älterer Läufe:
# scripts/reset_embedding_errors.py [--since D|--min-id N|--source-type T] --apply
0 6 * * 6    scripts/weekly_ingesters.sh

# Startup-Explorer-Quellen monatlich (6. 12:00, seit 2026-08-23, #87): CORDIS +
# SBIR (--refresh) + GLEIF + Companies House + GLEIF/CH-Enrichment + Distill
# der Neuzugänge + HDD-Download-Cleanup. Firmenstamm-Rebuild, Wikidata und
# Brücken bewusst NICHT im Cron (Rebuild würde Enrichment verwerfen) — on-demand.
# Distill-Schritt hinter dem Kollisionswächter (#98) wie weekly_ingesters
# (Pending-Datei data/monthly_startup_sources_pending_min_id, Note-JSON).
0 12 6 * *   scripts/monthly_startup_sources.sh

# Source-Link-Integrität monatlich (2. des Monats 07:00, Issue #48 — in der echten
# crontab installiert; Cron-Lauf 02.09. 07:03 im Log, 12 bestätigt tot): Stichprobe published
# Backlinks (HEAD/GET, ein Worker pro Host), --mark upsertet bestätigt tote Links
# (404/410/ConnErr, erst nach 2 aufeinanderfolgenden Fehl-Checks) in die Tabelle
# dead_links; 403/429 (Bot-Block) wird nie markiert. Die additive Migration
# scripts/migrate_dead_links.py ist auf der Live-DB ausgeführt (dead_links: 124
# Zeilen am 02.09.); sie läuft NICHT in init_db — auf einer frischen DB einmalig
# von Hand nachziehen (bekannte Migrationslücke, s. docs/issue_status.md).
0 7 2 * *    scripts/check_source_links.py --per-source 12 --mark
```

**Ops-Sampler (systemd-Timer, kein Cron; #104 Stufe 1, seit 2026-09-11):**
`catandary-ops-sampler.timer` ruft minütlich `scripts/ops_sampler.py` aus dem
main-Worktree auf und schreibt eine Zeile nach `ops_samples` — GPU lokal
(nvidia-smi, `/v1/models`, haltender Job aus den Besitzvermerken), bequiet
(nur Modell-API, backend-neutral: llama.cpp `/health` oder Ollama `/api/ps`),
CPU/RAM, **alle vier Platten** (Füllstand, I/O-Delta, hwmon-Temperatur, SMART
sobald `deploy/sudoers/catandary-smart` eingespielt ist), Postgres (Größe,
Verbindungen, lange Abfragen). Jede zehnte Minute ist eine volle Messung
(`is_full`: Backlog, Review-Queue, Tabellengrößen,
SMART) und löscht Zeilen älter als 7 Tage. Tabellen `ops_samples`/`ops_events`/
`ops_alerts` (additive Migration `_migrate_ops`, in `init_db`, Live-DB 11.09.).
Deltas über `data/ops_sampler_state.json`. Units: `deploy/systemd/catandary-ops-sampler.{service,timer}`.
Anzeige: `/trends/ops` (Stufe 3, s. Routing; `frontend/src/lib/ops.ts` Helfer, `opsDb.ts` Queries,
`components/ops/Chart.tsx` SVG ohne Chart-Bibliothek; Sperre wie `/trends/review`: `BLOCKED_PREFIXES`,
Proxy-Matcher, `static-export.exclude`, `canOps()`).

**Laufprotokoll `ops_events` (#104 Stufe 2, seit 2026-09-11):** jeder Job-Lauf
ist eine Zeile (Job, Start, Ende, rc, Notiz). Schreiber: die neun Shell-Wrapper
über `scripts/lib/ops_events.sh` (`ops_event_start <job>` nach dem `cd`,
`ops_event_end <rc> [Notiz]` vor jeder end-Zeile — auch auf den Abbruchpfaden
blocked/exists/skipped/locked) und die neun Python-Crons/Worker über
`pipeline.ops_events.record("<job>")` um `main()` (backup_db, purge_raw_content,
resolve_open_licence, discovery_loop, monthly_source_check, check_source_links,
research_pulse; `dossier_worker` bis 2026-09-19). `OPS_EVENT_ID` wird exportiert:
ein Python-Skript unter einem Wrapper übernimmt dessen Zeile statt eine zweite
anzulegen (Notizen wie `gpu=remote …` landen dann dort). Das Protokoll
darf einen Lauf nie verhindern — DB weg → Warnung im Log, Job läuft weiter. **Auch der Import ist optional** (seit 2026-09-12): die Crontab startet
`backup_db.py` ohne `cd`, und ein harter `from pipeline.ops_events import record`
warf dort einen ModuleNotFoundError — das Backup der Nacht auf den 12.09. fiel
aus (Wächter meldete, von Hand nachgeholt). Jetzt: `ImportError → nullcontext`,
`backup_db` setzt den Repo-Root selbst in den Pfad; Test
`tests/test_cron_scripts_start_anywhere.py` startet jeden Python-Cron mit `--help`
aus einem fremden Verzeichnis. Ein
Lauf ohne `ended_at` ist die Information „abgebrochen, Ende unbekannt" — **aber
kein Dauerzustand mehr (seit 2026-09-12):** jede Zeile trägt die `pid` des
Prozesses, dessen Leben den Lauf bedeutet (Python: der Interpreter; Wrapper:
`$$` der Bash via `--pid`), und der Sampler ruft jede Minute vor den Alarmregeln
`ops_events.close_orphans()` auf: offene Zeilen dieses Hosts, deren Prozess
nicht mehr existiert oder deren pid inzwischen ein *jüngerer* Prozess trägt
(Startzeit aus `/proc/<pid>/stat` gegen `started_at`), werden geschlossen —
`ended_at` = jetzt, `rc` NULL, Notiz `process N gone — closed by ops_sampler`
(Seite: „aborted"). Zeilen ohne pid (Altbestand) und fremde Hosts bleiben
unangetastet. Zusätzlich fängt `record()` SIGTERM (nur wenn das Skript keinen
eigenen Handler hat): `SystemExit(143)` → Ende gestempelt, `subprocess.run`-Kinder
beendet. Anlass: der um 07:49 von Hand gestartete Backup-Nachholer wurde nach dem
2-min-Tool-Timeout hart gekillt, die Zeile blieb offen, und um 13:50 kam die Mail
„backup_db running for 6.0 h" — es lief längst nichts mehr (das Backup selbst war
um 08:19 als zweiter Lauf sauber durch). Von Hand: `python -m pipeline.ops_events
close-orphans`.

**Alarme (#104 Stufe 5, seit 2026-09-11):** `pipeline/ops_alerts.py` läuft im
Sampler nach jeder Messung; Schwellen in `ops_alerts.yaml` (Repo-Root, ohne Code
änderbar). Regeln: Platte frei < 10 % (unter `/` = System + Postgres schon < 20 %),
Platten-Temperatur (HDD > 50 °C, SSD > 65 °C), SMART FAILED / NVMe critical
warning / Verschleiß ≥ 90 % / Reserve < 10 % / Sektor- und Medienfehler-Zähler
**steigen** (gegen die vorige volle Messung, ein stabiler Wert ist kein Alarm),
GPU > 88 °C, Fremdbelegung (> 1,5 GB VRAM, aber kein llama-server antwortet und
kein Job hält die Karte — der Ruhezustand mit 8B ist keiner), DB-Verbindungen
> 80 %, Job läuft > 2 × seinen Median (28 d, ≥ 3 Läufe), Job läuft > 6 h
(„läuft" = Zeile offen **und** Prozess lebt — tote Läufe schließt der Sampler
vorher, s. Laufprotokoll; Startzeit in der Mail seit 12.09. lokal mit Zone, nicht
mehr fälschlich „UTC"),
Backlog-Tagesmaximum steigt 3 Tage in Folge. Zustand in `ops_alerts`: **eine
Mail beim Auslösen, eine bei der Entwarnung** (Resend, derselbe Weg wie der
Wächter); eine Regel, die in dieser Minute nichts prüfen konnte (SMART/Backlog
nur alle 10 min), lässt ihre offenen Alarme stehen — sonst flatterte die
Entwarnung im Minutentakt. Der Alarmpfad fängt alles, die Messung ist vorher
geschrieben. **Sampler tot** meldet der Morgen-Wächter (`cycle_watchdog.py`
`inspect_sampler`: letzte Messung > 5 min alt). Offene Alarme stehen als Banner
oben auf `/trends/ops`.

**Mengenbremse statt Quellen-Verbot (Owner-Präzisierung 2026-08-20):** Funding-News
dürfen über den regulären Cycle zu Artikeln werden. Verhindert wird nur, dass ein
Massen-Ingest en masse in die Content-Generierung läuft (235k SBIR/CORDIS-Zeilen
brachen den Nachtlauf an der 50k-Grenze ab): `get_unprocessed_entries` nimmt pro
Quelle und Lauf höchstens `CYCLE_MAX_PER_SOURCE` (Default 200; RSS-Normalbetrieb
liegt bei p95 ≈ 70/Tag) — der Rest bleibt liegen und gehört dem Distill-Pfad
(`signal_batch`). Die 50k-Sanity-Zählung in `scheduled_cycle.sh` zählt denselben
gebremsten Intake. Zusätzlich existiert `sources.llm_pipeline` als manueller
Notschalter (FALSE = Quelle liefert nie Artikelmaterial). **Gesetzt für „SEC
Form D" (id 260, Owner 2026-08-24):** die Reg-D-Stubs fluteten den Draft-Richter
(248 von 546 Gehaltenen am 24.08.) und sind als Drei-Datenpunkte-Meldungen kein
Artikelmaterial — sie bleiben Signale über den Distill-Pfad. Redaktionelle
Funding-News aus Fachmedien dürfen weiterhin Artikel werden (Präzisierung
2026-08-20 bleibt gültig).

Auto-Publish ist in die LLM-Pipeline integriert (Stage 8+9: Reclassify → Auto-Publish);
Standalone-Lauf nur als Fallback: `python pipeline/auto_publisher.py`
(nutzt `AUTO_PUBLISH_CONFIDENCE=0.85` aus config.py). Newsletter: die **Website-
Edition** läuft seit 2026-08-29 per Cron (**Di** 09:00, von Mo verlegt am 2026-09-11, `weekly_newsletter_publish.sh`
— generiert die Vorwoche nach `newsletter_editions`, mit Full-Cycle-Kollisions-
wächter und Gemma-Swap); der E-Mail-**Versand** bleibt manuell/gegated bis zur
Launch-Kette (#16, `NEWSLETTER_GOLIVE.md`). **Human-in-the-loop vor jedem Versand
(Owner 2026-09-06):** keine Ausgabe geht raus, die nicht ein Mensch gelesen und
freigegeben hat. `newsletter_editions` trägt dafür `approved_at`/`approved_by`/
`approval_note` (additive Migration `scripts/migrate_newsletter_approval.py`,
Live-DB 2026-09-06); `pipeline/newsletter_sender.py` bricht ohne `approved_at`
mit **Exit 2** ab (auch bei `--latest`; `--force` öffnet das Gate nicht, einen
Abschalter gibt es bewusst nicht), `--dry-run` bleibt erlaubt und warnt, dass die
Freigabe fehlt. Freigegeben wird auf **`/trends/newsletter/review`**: Editionsliste
mit Status (Entwurf/freigegeben/versendet), Vorschau **der echten Mail** (die Seite
ruft `python -m pipeline.newsletter_preview` und zeigt das gelieferte HTML — ein
Renderer für Mail und Vorschau, `render_email_html()`), Freigabe mit optionaler
Notiz, Zurückziehen solange `sent_at` leer ist. **KI-Kennzeichnung** (#99, EU AI
Act Art. 50 — Anwaltstext offen, intern ab jetzt gesetzt): je Block ein Badge
(Editorial/Vertical-Summaries/Deep-Dive = *AI-generated*, Signal-Themes-Radar =
*Computed* (SQL, kein Modell), Trend-Links = *Curated*, verlinkte Artikel selbst
modellgeschrieben); ein Hinweissatz (`AI_DISCLOSURE_EN`, Python + TS-Mirror in
`frontend/src/lib/aiDisclosure.ts`, per pytest gegen Drift gepinnt) steht im
Mail-Fuß **und** in der Website-Edition. **Deep Dive of the Week (#96):** seit 2026-09-19
stillgelegt — `scripts/newsletter_deep_dive.py` schreibt nur noch `status:
"disabled"` (der Rechercheur dahinter, die Scouting-Dossiers, ist entfernt);
der gespeicherte Dry-Run (W35, `gate_failed`) rendert weiter, öffentlich nie. Abschnitt
„Newsletter Deep Dive" unten, Historie `docs/newsletter_deep_dive.md`.

### Feed-Poller Architektur

```python
# sources.yaml – Konfigurationsdatei für Quellen (pro Vertikale)
verticals:
  FOOD:
    sources:
      - name: FoodNavigator
        feed_url: https://www.foodnavigator.com/rss/...
        type: trade_media
      - name: Food Dive
        feed_url: https://www.fooddive.com/feeds/...
        type: trade_media

  TECH:
    sources:
      - name: TechCrunch
        feed_url: https://techcrunch.com/feed/
        type: trade_media
      - name: Ars Technica
        feed_url: https://feeds.arstechnica.com/arstechnica/index
        type: trade_media

  # ... weitere Vertikale nach gleichem Schema

cross_industry:
  press_wires:
    - name: PR Newswire
      feed_url: https://www.prnewswire.com/rss/...
      type: press_wire
    - name: BusinessWire
      feed_url: https://www.businesswire.com/rss/...
      type: press_wire
```

---

## Frontend: Catandary Trends Website

### Tech-Stack (Ist-Stand 2026-07-23)

- **Framework:** Next.js 16 (App Router, Turbopack-Dev) + TypeScript + React 19
- **Styling:** Tailwind CSS v4 (`@theme`-Tokens in `frontend/src/app/globals.css` — Designsystem „Editorial Intelligence": IBM Plex Serif/Mono/Sans, Ink `#0a0c0a`, Akzent Chartreuse `#d4ff3a`, scharfe Kanten)
- **DB-Anbindung:** eigener `pg`-Layer (`frontend/src/lib/pg.ts` + `db.ts`) auf PostgreSQL/pgvector, Socket-Default (kein Drizzle); teure Aggregat-Queries laufen über einen In-Process-TTL-Cache in `db.ts`
- **Auth/Paywall:** **entfernt 2026-09-03 (#93, kein SaaS — Owner 26.08.)**. Magic-Link-Auth, Tier-Entitlements, `TierGate`, Stripe-Checkout/Webhook, `/account*`, `/trends/pricing`, `/api/auth*`, `/api/stripe*` sowie `scripts/migrate_accounts.py`/`set_user_tier.py` sind physisch aus dem Code; die DB-Tabellen `app_users`/`magic_tokens`/`research_live_usage` bleiben ungenutzt stehen (kein DROP). Es gibt keine Accounts: die Owner-Instanz sieht alles, der Review-Guard (`lib/review-access.ts`) ist nur noch „lokal ja, `PUBLIC_MODE`/Export nie" (`REVIEW_ENABLED` entfällt). `AUTH_SECRET` bleibt — er signiert die Newsletter-Abmelde-HMAC (`lib/unsubscribe.ts`). `PUBLIC_MODE=1` (`frontend/src/proxy.ts`, Blockliste `lib/publicMode.ts`) blendet nur noch `/trends/foresight*`, `/trends/review*`, `/api/foresight*` als 404 aus und fenstert den Feed auf `PUBLIC_WINDOW_DAYS` (`lib/archiveWindow.ts`, `archiveWindowDays()`); das frühere 28-Tage-Paywall-Fenster (#70) ist weg
- **Zweite GPU im Tailnet — RTX 5080 auf `bequiet` (seit 2026-09-10):** Windows-Arbeitsplatz,
  Tailnet `100.119.239.40`, 1 ms über LAN (kein Relay). Ollama 0.33.3 auf `:11434` ohne
  Authentifizierung, elf Modelle vorhanden (u. a. `qwen3:8b`, `qwen3:14b`, `qwen3-embedding`,
  `nuextract`), SSH mit Schlüssel. 16 GB VRAM, davon am Sperrbildschirm **13,9 GB frei** —
  bei angemeldetem Benutzer deutlich weniger, also für verlässlichen Betrieb mit ~10–11 GB
  rechnen. Reicht für 8B/14B und den Embedder, **nicht** für Gemma-4-26B oder den 27B.
  **Owner-Regel: 01:00–17:00 frei nutzbar, 17:00–01:00 gehört die Karte dem Owner**
  (`pipeline/remote_gpu.py`, `REMOTE_GPU_WINDOW`). Gemessen 10.09., warm, Ø 2.013 Zeichen:
  **12,4 Texte/s gegen 6,6/s auf der lokalen 3090** — und derselbe Text ergibt hier wie dort
  **cos 0,9995**, die Vektorräume sind also austauschbar. Kaltstart ~35 s (Modellladen).
  Der Rechner ist ein Arbeitsplatz, kein Server (Laufzeit beim ersten Blick 2 h): jeder
  Aufrufer prüft Fenster **und** Erreichbarkeit und fällt sonst auf die lokale Karte zurück.
- **Embedding-Server auf der CPU (`:8091`, seit 2026-09-09, #97):** systemd user unit
  `catandary-embed-cpu.service` (`~/llama.cpp/start-qwen3-emb-cpu.sh`, dasselbe
  Qwen3-Embedding-8B wie Stage 5, aber `CUDA_VISIBLE_DEVICES=""` und `-ngl 0`). Er existiert für
  **Vektorsuchen, während `:8090` ein Chatmodell hält** — ein Embedding-Request dorthin würde
  vom Chatmodell beantwortet, und die ANN-Suche liefe gegen einen Vektor aus einem anderen Raum.
  Erster Nutzer war der Korpus-Rechercheur der Scouting-Dossiers (entfernt 2026-09-19); heute
  u. a. `scripts/validate_emerging.py` (`RESEARCH_EMBED_HOST`). Kostet ~5 GB RAM, **0 MiB VRAM**,
  ~0,3 s je Anfrage.
  `-ngl 0` allein genügt nicht: llama.cpp legt den Compute-Buffer trotzdem auf CUDA0 (bei
  `-ub 8192` sind das 5,4 GB) und stirbt neben dem GPU-Server an OOM — daher der harte
  Device-Ausschluss und der kleine Batch.
- **Zugriff auf die Owner-Instanzen (seit 2026-09-05, Security E-1/E-2/E-4 behoben):** `:3001` (main, systemd), `:3004` (dev), `:3999` (dev, PUBLIC_MODE) und der llama-server `:8090` binden nur noch auf **127.0.0.1** (`-H 127.0.0.1` in `deploy/systemd/catandary-frontend.service`, `--host 127.0.0.1` in allen `~/llama.cpp/start-*.sh`). Vom MacBook geht es über **Tailscale Serve** (tailnet-only, HTTPS, Serve + HTTPS-Zertifikate im Tailnet aktiviert, Funnel bewusst aus): `https://kiworkstation.tail678c6e.ts.net` → :3001, `…:3004` → :3004, `…:3999` → :3999 (`tailscale serve status`). Direkt über die Tailnet-IP sind die Ports zu.
- **Hosting (Ist 2026-09-02):** **Es gibt keinen VPS.** `catandary.de` = statische Landing (`docs/launch/preview.html`) auf dem bestehenden Hetzner-**Webhosting** (Shared Webspace, kein Node); die Next-App läuft nur lokal auf der Workstation, Port 3001 via systemd user unit `catandary-frontend` — `/trends` & Co. sind öffentlich 404. **Owner-Entscheid 02.09.: öffentliche Website = statischer Export (`next build` mit `output: 'export'`) aufs Webhosting** — Design `docs/audits/2026-09-02_static_export_design.md`, Plan `docs/launch/09_launch_plan_2026-09-02.md` (#82-Neuschnitt, Welle 2). Der VPS-Pfad (`docs/launch/HOSTING_PUBLIC_VPS.md`) ist damit verworfen.
- **Reverse Proxy:** keiner im Einsatz — `deploy/Caddyfile` ist ein Relikt der verworfenen VPS-Planung (s. „Deployment" unten)
- **Laufende Instanzen (Workstation, 02.09.):** `:3001` = `next start` aus `~/projects/catandary-trends` (main, systemd, ohne `PUBLIC_MODE`); `:3004` = `next dev` aus `~/projects/ct-dev` (dev, **ohne** `PUBLIC_MODE`); `:3999` = `next dev` aus `ct-dev` mit `PUBLIC_MODE=1 NEXT_DIST_DIR=.next-public` = **die PUBLIC_MODE-Vorschau** (nicht :3004). Start (in tmux, keine systemd-Unit dafür): `cd ~/projects/ct-dev/frontend && PUBLIC_MODE=1 NEXT_DIST_DIR=.next-public npx next dev --turbopack -p 3999` — `NEXT_DIST_DIR` ist seit `21b3059` nötig, weil Next 16 `.next/dev` pro Verzeichnis lockt (zweiter Dev-Server aus demselben Worktree)
- **Domain:** catandary.de (Landing `/` statisch live; `/trends` erst nach dem Export)
- **Newsletter:** Resend (Domain send.catandary.de)
- **Tests:** Vitest (`frontend/src/lib/*.test.ts`)

### Deployment

> **Historisch (verworfen 02.09.2026):** Der Caddy-Block darunter stammt aus der VPS-Planung (Hetzner Cloud + Caddy vor der Next-App, `docs/launch/HOSTING_PUBLIC_VPS.md`). Ein VPS wurde nie bestellt, Caddy läuft nirgends. Bleibt als Referenz stehen, falls der Pfad je wieder aufgemacht wird — **aktuell gilt der statische Export** (s. Hosting oben). Der Workflow-Block danach beschreibt weiterhin die **lokale** :3001-Instanz und ist aktuell.

```
# [HISTORISCH] Caddy-Konfiguration (Caddyfile) — App läuft lokal auf :3001
catandary.de {
    # Next.js App
    reverse_proxy localhost:3001

    # Statische Assets cachen
    @static path /trends/_next/static/*
    header @static Cache-Control "public, max-age=31536000, immutable"
}

# Oder als Subdomain falls bestehende Seite nicht stören:
# trends.catandary.de { reverse_proxy localhost:3001 }
```

```bash
# Deployment-Workflow der lokalen :3001-Instanz (main-Worktree ~/projects/catandary-trends) — systemd statt PM2 (seit #38)
git pull origin main
cd frontend && npm run build
systemctl --user restart catandary-frontend
# Unit: deploy/systemd/catandary-frontend.service (Socket-Default, Autostart via Linger)

# PostgreSQL + pgvector
sudo apt install postgresql postgresql-contrib
# pgvector Extension installieren
CREATE EXTENSION vector;
```

### Statischer Export (Betrieb, Stand 2026-09-03 — Welle 2)

Der öffentliche Auftritt unter `catandary.de/trends` ist ein **statischer Export** der Next-App, gebaut auf der Workstation und per SFTP/rsync aufs Hetzner-Webhosting gelegt. Vollständige Betriebsdoku: `docs/launch/HOSTING_HETZNER.md` (Abschnitte „Statischer Export — Build / Publish / Suche im Export").

- **Build:** `scripts/build_public_static.sh [OUT_DIR]` → Staging-Baum `frontend/.export/site` (Exclusion-Liste `frontend/static-export.exclude` = alles, was `BLOCKED_PREFIXES` in `src/proxy.ts` sperrt, plus Proxy/API/Unsubscribe; Vitest-Drift-Wächter), `STATIC_EXPORT=1 PUBLIC_MODE=1 next build` mit `output: 'export'`, Ergebnis `frontend/.export/out` + `out.manifest.tsv` (sha256/size/path) + `out.build_info.json`. ~15k Artikel (Fenster `PUBLIC_WINDOW_DAYS`, Default 30, Tagesgrenze via `lib/archiveWindow.ts`), ~30k Dateien / ~1 GB, ~60 s. Segment-Prefetch-Dateien werden entfernt, Link-Prefetch ist im Export aus.
- **Methodik-Statistik:** der Build schreibt vorab `frontend/.export/methodology_stats.json` (`scripts/methodology_stats.py`, ohne statement_timeout) und reicht sie per `METHODOLOGY_STATS_FILE` an `next build` — die Live-Aggregate liefen unter 6 Build-Workern in den 20-s-Timeout (erster Produktions-Export 05.09.).
- **Determinismus ist Pflicht:** zwei aufeinanderfolgende Builds müssen `diff -rq`-leer sein (konstante Build-ID, keine `new Date()` im Render, `sort_date DESC, id DESC`-Tiebreaker, Related = 3 Vorgänger derselben Vertikale, `source_date = LEAST(published, created_at)`). Während des Nachtlaufs (02:45) ist das nicht gegeben (DB ändert sich) — Publish läuft deshalb davor, 02:00.
- **Render-Weichen:** `lib/renderMode.ts` (`isStaticExport()`) und `lib/publicMode.ts`; `generateStaticParams` nur im Export (Workstation-Build lieferte sonst 500 auf Artikel-/Mega-/Listing-Seiten, Fix `dd4490b`). Lokale Owner-Instanz (`npm run build` ohne Flags) verhält sich unverändert.
- **URL-Schema Export:** `/trends` (= `trends/index.html`), `/trends/page/<n>`, `/trends/v/<vertical>[/page/<n>]`, `/trends/<slug>` (Apache-Rewrite auf `.html`, abgelaufene Slugs → **410** via Muster in `trends/.htaccess`), `/trends/mega[/<m>]`, `/trends/methodology`, `/trends/newsletter` (Signup + neueste Edition + Archivliste), `/trends/newsletter/<jahr>-w<kw>` (letzte 12 Editionen, `PUBLIC_NEWSLETTER_EDITIONS`; Artikel-Links außerhalb des Fensters → `source_url`), `/trends/newsletter/unsubscribed` (303-Ziel von `unsubscribe.php`, noindex), `/trends/imprint|privacy|enquiry`, `/trends/index.json` (Suchindex, ~2 MB gz, clientseitige Suche/Filter `components/StaticSearch.tsx`), `/trends/sitemap.xml`. `.htaccess` liegen verzeichnisweise in `trends/` und `_next/` — der **Webroot bleibt owner-verwaltet** (`index.html` = Landing `docs/launch/preview.html`, `robots.txt`, `newsletter/**` PHP-DOI); das Export-Root-`index.html` wird nicht hochgeladen.
- **Publish:** `scripts/publish_static_site.py` (Default `--dry-run`, `--apply` schreibt) — Manifest-Delta gegen `trends/.publish-manifest.tsv` auf dem Webspace, verwaltet NUR `trends/**`, `_next/**` und die Root-Allowlist `trends.html`/`trends.txt`; Reihenfolge Assets → Artikel → Listing → Löschen; Gates: Build ≤ 12 h alt, ≥ 1000 Artikel, ≤ 60 % Löschungen. Backends `MODE=sftp|rsync|local` aus `~/.config/catandary/webspace.env` (0600; **fehlt noch — Owner-Aktion**). Summary `data/publish_last.json`, Wächter-Check in `cycle_watchdog.py` (nur aktiv, wenn die Config existiert).
- **Cron (installiert 2026-09-05):** `15 3 * * *  scripts/publish_static_site.sh` (Lock, Cycle-Kollisionswächter, Build → Publish). `PUBLIC_NOINDEX=1` hält den Export bis zum Launch 01.10. auf `noindex`.
- **TDM-Vorbehalt + KI-Crawler-Sperre (Owner 2026-09-03):** jede exportierte Seite trägt `<meta name="tdm-reservation" content="1">` + `tdm-policy` + `robots: noai, noimageai` (`layout.tsx`), `trends/.htaccess` und `_next/.htaccess` setzen `TDM-Reservation: 1` und liefern den KI-Crawlern aus `frontend/src/lib/aiCrawlers.ts` (36 UAs: GPTBot, ClaudeBot, CCBot, Bytespider, …) ein **403**; `robots.ts` sperrt dieselbe Liste per `Disallow: /`; der Build schreibt `/.well-known/tdmrep.json`; Klartext unter `/trends/tdm-policy`. `robots.txt` und `tdmrep.json` sind seit 03.09. **export-verwaltet** (`ROOT_ALLOWLIST`), Suchmaschinen bleiben erlaubt. Root-`.htaccess` des Webroots: Owner fügt `docs/launch/root-htaccess.snippet` ein. Details `docs/launch/HOSTING_HETZNER.md`.
- **Lokaler Apache-Test:** `scripts/htaccess_test_server.sh` (Docker `httpd:2.4`, Port 8098, Bind per `HTACCESS_TEST_BIND`) prüft die `.htaccess`-Regeln; die Playwright-Suche-Prüfung ist in der Hosting-Doku beschrieben.

### Routing (Ist-Stand 2026-07-23)

```
/                                → Weiterleitung auf /trends (seit 2026-09-05; die frühere App-Landing war eine zweite, driftende Kopie — Countdown 01.09. statt 01.10., tote Links. Gepflegt ist nur `docs/launch/preview.html` auf catandary.de; der Export lädt `/` nicht hoch)
/trends                          → Hauptfeed (Card-Grid, Filter-Bar inkl. Suche ?q= — es gibt KEINE separate /trends/search-Route)
/trends/[slug]                   → Einzelner Trend-Artikel (trägt die KI-Kennzeichnung nach Art. 50 Abs. 4 direkt unter dem Titel, s. o.)
/trends/vertical/[v]             → Redirect auf /trends?v=<VERTICAL> (im statischen Export nicht gebaut; Apache-301 auf /trends/v/<v>)
/trends/page/[n], /trends/v/[vertical], /trends/v/[vertical]/page/[n]
                                 → statische Listing-Routen des Exports (24/Seite, lib/staticListing.ts); lokal per Request rendernd, nichts verlinkt sie dort
/trends/imprint|privacy|enquiry  → nur im statischen Export (Export-Adressen der Root-Seiten, lib/sitePaths.ts); lokal 404
/trends/mega, /trends/mega/[m]   → „Mega Signal Themes"-Übersicht (28 kuratierte Themes; „Megatrend" ist verdientes, gemessenes Badge — 12 Keys, Regel in scripts/measure_mega_axes.py) + Detail
                                   Bottom-up-Entdeckung neuer Themen: scripts/propose_mega_trends.py (Cluster im Signalraum → NEW/SPLIT/MERGE, read-only,
                                   schreibt nur eine Kandidatendatei; measure_mega_axes --write-yaml bleibt die einzige Schreibquelle der Badge-Felder).
                                   Der SQLite-Prototyp discover_mega_trends.py wurde 2026-09-09 entfernt (zeigte auf die vor-Postgres-DB, abgelöst).
/trends/foresight                → Foresight-Cockpit (Hub) + Unterseiten:
  /clusters /clusters/<id> /emerging /technology /lead-time /evolution
    (Cluster-Schicht seit 2026-09-15: Snapshot ueber die letzten 24 Monate statt des
     ganzen Archivs (`--window-months`), Momentum als Anteil am Gehoer auf einem FESTEN
     QUELLENPANEL (nur Quellen, die in beiden Vergleichsfenstern geliefert haben) mit
     Daempfung von Mengenausschlaegen je Quelle auf deren Median, laufender Monat raus,
     rohe Mengenaenderung als zweite Zahl, groesste Einzelquelle mit Anteil statt
     "confirmed by N sources", Belege = neueste zentrumsnahe Signale (eines je Quelle),
     Titel innerhalb eines Laufs eindeutig, Mega-Zuordnung erst ab 50 % Reinheit.
     Der Schwerpunktvektor wird jetzt persistiert und traegt die Detailseite
     /clusters/<id>: pgvector-Nachbarschaft im selben Scope/Fenster, 12 zentrumsnaechste
     + 12 neueste Signale, Messblock. Anlass + Messungen: docs/cluster_layer_audit_2026-09-15.md)
    (/emerging = ZWEITE Signalraum-Schicht seit 2026-09-15, neben den Clustern, nicht
     statt ihnen — Owner-Frage „was muesste man tun, dass wirklich Trends entdeckt
     werden?". k-Means teilt den Bestand restlos auf, also ist jede Zelle ein
     Themengebiet; ein Trend ist die umgekehrte Form. pipeline/emerging.py +
     emerging_snapshot.py: frischer 90-Tage-Schnitt fein zerlegt (Zellzahl ist ein
     RECHENBUDGET, nicht Prinzip: global 400 Dok/Zelle, kleine Bereiche 40), nur
     Zellen mit Kohaesion >= 0,75 bleiben (global 83 Nester aus 784 Zellen = 12 %
     des Schnitts, Rest ist ausdruecklich Rauschen), deckungsgleiche Zentren wieder
     vereint. Danach laeuft der GANZE Bestand am Zentrum vorbei und wird je Monat
     gezaehlt (1,75M Dokumente / 449 Monate / 212 s, Speicher = ein Block) ->
     erster Monat, Alter, Neuheits-Hebel (korpus-normiert, saettigt bei ~4,5),
     Beschleunigung, neues Vokabular gegen den Stand vor 24-36 Monaten. Karte zeigt
     als Kopfzeile das ALTER und immer die Schwaechen (Quellenzahl, groesste Quelle,
     Anteil klassifizierter Dokumente) — die Schicht ist ein Sucher, kein Urteil:
     im ersten Lauf stand ganz oben ein dichtes, brandneues Nest mit 647 Dokumenten
     Pseudowissenschaft aus einem Massen-Ingest. Tabellen emerging_runs/
     emerging_nests, additiv, Live-DB 15.09. Kein Cron, Knopf „Recompute pockets".
     NAMEN (seit 2026-09-15 abends, pipeline/nest_naming.py): das lokale Modell
     liest die zentrumsnaechsten Titel und benennt das Nest; jedes bedeutungs-
     tragende Wort muss im Nest vorkommen, sonst faellt der Name durch und das
     Schlagwort-Label bleibt (Karte zeigt beides). 311 von 328 benannt; einziger
     GPU-Schritt der Schicht, --no-llm-names schaltet ihn ab.
     PRUEFUNG (scripts/validate_emerging.py + known_trends.yaml): Ruecktest auf
     21 Stichtagen gegen 20 datierbare Trends. 9 von 20 gefunden, 5 vor dem
     Mainstream, Median-Vorlauf 6 Monate, Gegenproben nie ueber 0,62. Ein
     Treffer zaehlt nur, wenn das getroffene Nest ein Kennwort des Trends auch
     WIRKLICH enthaelt — ohne diese Regel meldete der Test 15 von 20 und 23
     Monate, weil ein einziges Nest "Machine Learning · Neural Networks" gleich
     drei KI-Trends traf. Bei 5 Trends fand der Test nicht einmal das Feld:
     Quellenproblem, kein Erkennungsproblem.
     EBENEN (Owner 2026-09-15: "ein science trend ist nicht das selbe wie ein
     markttrend, selbst wenn thematisch deckungsgleich"): pipeline/tiers.py ordnet
     jede Zeile einer Lead-Time-Ebene zu (Zwilling der SQL-TIER_FILTERS); der
     Archiv-Scan zaehlt je Monat UND Ebene, also traegt jedes Nest vier
     Erstauftritte, die Reihenfolge und den Abstand Wissenschaft->Markt. Dazu
     Akteure: verschiedene Firmen/Marken in den Markt-Aehnlichen, frueh gegen
     spaet — Untergrenze, weil nur 13 % der Fachpresse-Zeilen einen extrahierten
     Namen tragen (Forschung 1 %, Patente 0 %: Extraktion laeuft nur im
     Artikel-Pfad). WICHTIG: die Ebene laesst sich NICHT nachtraeglich aus einem
     gemeinsamen Nest loesen, weil die Einbettung den Sprachstil mitkodiert —
     "perovskite tandem solar cells" trifft in 400.000 Dokumenten 146
     Forschungs- und 2 Marktzeilen. Deshalb eigener Scope `tier:<t>`
     (`--all-tiers`), der jede Ebene fuer sich clustert; die Marktebene bekommt
     automatisch feinere Zellen (bei 207 Dok/Zelle 5 Nester, bei 69 dann 46).
     Offen: Extraktion auf den Signalpfad ausweiten, damit Akteure zaehlbar
     werden. docs/emerging_nests_2026-09-15.md)
    (das druckbare Foresight-Dossier /dossier samt CSV-Export
     wurde am 2026-09-15 entfernt: es las nur den ungeeichten Cluster-Snapshot vom 03.08. — Owner-Entscheid)
    (Technologie-Suche: Query-Quality-Gate #67 seit 2026-09-04, `pipeline/query_gate.py` — eine Anfrage
     bekommt nur dann eine Zahl, wenn ihre 20 nächsten CPC-Klassen alle unter d20 ≤ 0,36 liegen UND
     mindestens ein Patenttitel alle Terme enthält; weicht das Wort-Feld der Titeltreffer (≥ 40 %) vom
     Embedding-Feld ab → Feldwahl statt stiller Zuordnung, sonst → „keine Technologie-Signatur" mit
     2–3 nächsten echten Feldern; breite echte Begriffe wie „blockchain" mit vielen Titeltreffern werden nicht gesperrt, sondern zur Feldwahl zurückgefragt. Herleitung + Messtabelle: `docs/tech_query_gate_2026-09-04.md`)
  /research /patents               (Research-/Patent-Explorer; Explorer-Facetten ?src/?range/?sort/?concept/?layer=signals seit #73;
                                    ?artifacts=1 blendet Repository-Einträge/Nicht-Paper ein — Default aus, seit 2026-09-05)
  /research/pulse, /research/pulse/[theme] → Research Pulse (#73, seit 2026-09-04): Wochen-Synthese je Theme,
                                   Tabelle research_pulse, „Recompute"-Knopf (Owner-App); Cron Sa 12:00 seit 2026-09-18
  /pitch                           → Kunden-Briefing (seit 2026-09-13): Präsentation im Browser nach dem
                                     McKinsey-SCR-Q-Rahmen (Situation, Complication, Resolution, Question), sieben
                                     Folien, Pfeiltasten/Rail, Zahlen live aus dem Korpus (`getBriefingStats`,
                                     billige Zählungen + Planer-Schätzung für research_corpus — die
                                     Methodik-Aggregate liefen in den 20-s-Timeout). Owner-only wie das
                                     ganze Cockpit; Ehrlichkeitsregeln der Launch-Site gelten (kein Methoden-USP,
                                     keine Kundenlogos, TIR = relative Entwicklung).
  /ventures, /ventures/company/[id] → Startup Explorer (#87, seit 2026-08-23):
                                     Firmen-Korpus mit Evidenz-Timeline + Brücken
                                   (ungegated — Owner-Werkzeug; im PUBLIC_MODE/Export 404.
                                    Tier-Gates + Free-Teaser entfernt 2026-09-03, #93)
/trends/methodology              → Methodik-/Trust-Seite
/trends/newsletter (+/unsubscribe) → Newsletter-Signup/-Abmeldung (lokal Client-Seite mit ?year=&week=)
/trends/newsletter/<jahr>-w<kw>, /trends/newsletter/unsubscribed
                                 → nur im statischen Export: Editions-Archiv (letzte 12) + Abmelde-Bestätigung (lib/newsletterEditions.ts); lokal 404 bzw. unverlinkt
/trends/newsletter/review        → Freigabe-Desk (Owner, seit 2026-09-06): Editionsliste + Vorschau der echten Mail
                                   + Freigabe/Zurückziehen + KI-Kennzeichnung je Block; im PUBLIC_MODE 404 und aus dem
                                   statischen Export ausgeschlossen (BLOCKED_PREFIXES + static-export.exclude + canReview())
/trends/ops                      → Ops-Dashboard (#104, seit 2026-09-11; Owner, im PUBLIC_MODE 404, nicht im Export): Jetzt-Kacheln (GPU lokal + bequiet, CPU/RAM, Postgres, Queues, Sampler), alle vier Platten (Füllstand, I/O, Temperatur, SMART-Ampel, „voll in N Tagen"), 24-h/7-d-Diagramme als server-gerendertes SVG mit Job-Bändern aus ops_events, Job-Statistik (28 Tage, Median-Dauer) und die letzten 40 Läufe; ?range=24h|7d, Auto-Refresh 60 s. **Wochenplan** (Stufe 4): die INSTALLIERTE Crontab (`crontab -l`, Fallback `deploy/crontab.txt`) als Wochenraster, Blockbreite = gemessene Median-Dauer, Überschneidungen aufgelistet; **Logbuch** `docs/ops/logbook.md` (versioniert, `## <Datum> · change|plan|decision|idea · <Titel>`, optional `duration:`/`gpu:`-Zeilen) gerendert, `plan`-Einträge mit Tag erscheinen im Wochenplan. **Alarme** (Stufe 5) als Banner oben (offen) + zuletzt entwarnt; Regeln/Schwellen s. Cron-Block.
/trends/ops/prompts              → Prompt-Katalog (seit 2026-09-18; Owner, wie /trends/ops gesperrt): jede Systemanweisung, die ein Sprachmodell in diesem System bekommt, LIVE aus dem Code gelesen (`pipeline/prompt_catalog.py --json`, 60-s-Cache im Frontend) — je Eintrag: was die umgebende Funktion tut und wann sie läuft, welches Modell antwortet, Datei:Zeile, der Prompt selbst aufklappbar, bei Stage 6 und dem Dossier-Schreiber zusätzlich der User-Prompt-Bauer. 28 Einträge in 7 Gruppen (Feed-Pipeline, Richter, Foresight, Newsletter, Dossiers, Advisor, On-demand). Nicht drin: Embeddings, Distill-Heads, A/B-/Eval-Skripte. Nebenfund beim Bau: `corpus_research.PROFILE_SYSTEM` war doppelt definiert (Firmenprofil überschrieb die Suchrichtungen) → `COMPANY_PROFILE_SYSTEM`.
/trends/dossiers, /trends/dossiers/[slug] → ENTFERNT 2026-09-19 (Owner-Dossier-Desk #95, „Das Feature trägt nicht"; s. Abschnitt „Scouting-Dossiers — entfernt"; Rückweg Tag `archive/dossiers-2026-09-19`). Lokal wie im Export 404.
/imprint, /privacy, /enquiry     → Rechtstexte + Anfrage (mailto); im Export unter /trends/… (s. o.), da der Publisher den Webroot nie schreibt
```

Hinweis: Ein DE/EN-Switcher existiert nicht mehr — die Produktsprache ist durchgehend Englisch (DE-Content-Spalten bleiben NULL, s.o.).

### Design-Richtung

- Dark-Mode Card-Grid UI
- **Vertikale-Tabs** oder Filter-Bar oben (FOOD / TECH / HEALTH / ECO / DESIGN / FASHION / BIZ / LIFESTYLE)
- **PESTEL-farbcodierte Badges** auf jeder Karte
- **Vertikale-Icons** für schnelle visuelle Orientierung
- Trend-Score-Visualisierung pro Karte
- Cross-Vertical-Trends hervorgehoben ("Trends die mehrere Branchen betreffen")
- Prominente Quellennennung (Trust-Signal)
- "Powered by Catandary Foresight" CTA
- Newsletter-Signup (primärer Lead-Magnet)

### Lead-Capture-Strategie

- **Free Layer (Trends):** Kuratierte Artikel, Kategorisierung, Trend-Score
- **Teaser Layer:** Mega/Macro/Micro-Einordnung andeuten, aber nicht voll zeigen
- **Premium CTA:** "Vollständige Trend-Prognose → Catandary Foresight"
- **Gated Content:** Tiefere Analysen hinter Email-Gate
- **Newsletter:** Wöchentliche Top-Trends + Foresight-Teaser

---

## Sprint-Plan (alle Sprints abgeschlossen)

### Sprint 1 ✓ — Pipeline-MVP (FOOD + TECH)
- [x] Ollama-Setup, Feed-Poller, LLM-Pipeline, Pydantic-Schemas, Review-CLI

### Sprint 2 ✓ — Content-Generierung + DB
- [x] Content-Generierung DE+EN, Duplikat-Erkennung, PostgreSQL-Support, Radar-Pipeline

### Sprint 3 ✓ — Frontend-MVP
- [x] Next.js mit Dark-Mode Card-Grid, Vertical-Filter, PESTEL-Badges, DE/EN-Switcher

### Sprint 4 ✓ — Launch + HEALTH/ECO
- [x] HEALTH + ECO Vertikale, Newsletter, SEO, Deployment-Config

### Sprint 5 ✓ — DESIGN/FASHION/BIZ + Polish
- [x] Weitere Vertikale, Cross-Vertical Clustering, Mega-Trend-Seiten, Auto-Publish

### Sprint 6 ✓ — Vollausbau + Overhaul
- [x] Alle Vertikale live (8 Vertikale nach Konsolidierung)
- [x] CULTURE+SOCIAL+LUXURY → LIFESTYLE zusammengelegt
- [x] Trendhunter komplett ersetzt durch 43 Primärquellen + Brave Search Radar
- [x] Semantische Reklassifizierung aller 1226 Trends
- [x] CRS-Scoring, kanonische Mega-Trends-Taxonomie
- [x] Engagement-Tracking, Newsletter, Cluster-Dashboard

---

## Technische Randbedingungen

- **Domain:** catandary.de – alle URLs müssen dazu passen (catandary.de/trends/...)
- **Hosting:** Hetzner-Webhosting (statisch) — öffentlich nur der statische Export; die volle App bleibt lokal auf der Workstation (Owner-Entscheid 02.09.2026; kein VPS, kein Caddy)
- **Kein Scraping von Aggregator-Seiten** – nur Primärquellen über RSS/API; Aggregatoren nur als Entdeckungs-Index für neue Primärquellen (#97), jede neue Quelle muss die TDM-/Bot-/Lizenz-Kriterien selbst erfüllen
- **Quellennennung ist Pflicht** – jeder Artikel verlinkt zur Originalquelle
- **Content muss eigenständig sein** – LLM-Texte substanziell anders als Original
- **API-Kosten minimieren** – lokale Modelle (Ollama) für alles außer komplexe Synthese
- **Konfigurierbar** – neue Quellen ohne Code-Änderung via sources.yaml
- **Testbar** – Unit-Tests für Deduplizierung, Schema-Validierung, LLM-Output-Qualität
- **Modular** – Feed-Poller, LLM-Processor, Frontend sind unabhängige Komponenten

---

## Anweisungen für Claude Code (Autonomer Arbeitsmodus)

### ⚖️ Konstitutionelle Bedingung: Doku spiegelt immer die Realität

**Verbindlich bei jeder Arbeit in diesem Repo:** Die Repo-Dokumentation (`CLAUDE.md`, `README.md`, `docs/`) muss stets die **tatsächlichen aktuellen Bedingungen** des Repos widerspiegeln.

- **Ändert eine Arbeit reale Bedingungen** (Modelle, Backends, Defaults, Konfiguration, DB-Schema, Branch-Zustand, Pipeline-Verhalten, Cron/Deploy), wird die betroffene Doku **im selben Zug** mitgezogen — niemals stale Doku hinterlassen.
- **Gegen die Realität verifizieren, nicht die alte Doku fortschreiben:** aktive Start-Skripte/GGUFs/Env in `scheduled_cycle.sh`, `config.py`-Defaults, Schema in `pipeline/db.py` etc. tatsächlich prüfen statt annehmen.
- **README und Bedienungsanleitung gehören dazu (Owner-Vorgabe 2026-09-05):** `README.md` (Karte der Owner-Funktionen, Setup, Betrieb, Launch-Checkliste) und `docs/owner_manual.md` (Schritt-für-Schritt-Anleitung je Funktion) sind Teil der Doku-Pflicht. Wer eine Owner-Funktion, Route, ein Skript, Flag, einen Cron oder ein Ergebnisformat ändert, zieht **im selben Commit** den betreffenden Abschnitt in README und Handbuch nach (neue Funktion → neues Kapitel; entfernte Funktion → Kapitel raus, nicht „veraltet" stehen lassen). Vor dem Commit gegen die laufende Instanz prüfen (URL, Kommando, Flag), nicht aus dem Kopf schreiben.
### ⚖️ Konstitutionelle Bedingung: was nachts läuft, läuft aus `main`

**Verbindlich seit 2026-09-11 (Owner).** Alle Cron-Jobs starten aus dem Worktree
`~/projects/catandary-trends` = **`main`**. Entwickelt und getestet wird in
`~/projects/ct-dev` = **`dev`**. Zwischen „bei mir grün" und „läuft nachts"
liegt daher ein Merge — und der ist keine Formalie, sondern Teil der Arbeit.

- **Ändert eine Arbeit etwas, das ein Cron ausführt** (Skript unter `scripts/`,
  ein Default darin, `pipeline/`-Code auf dem Cron-Pfad, `deploy/crontab.txt`),
  dann ist die Änderung **erst mit dem Merge nach `main` in Betrieb**. „Auf
  `dev` committet" heißt bei diesen Dateien: *noch nicht scharf.*
- **Der Merge wird dem Owner vorgelegt, nicht stillschweigend gemacht.**
  Vor dem Merge: kurz auflisten, **was dadurch scharf geht** — je Punkt eine
  Zeile, in der Sprache der Wirkung („der Nachtlauf nimmt ab jetzt 3000 statt
  600 Einträge"), nicht in Commit-Titeln. Erst nach der Zustimmung mergen.
  Grund (Owner 2026-09-11): der Owner will jede Änderung, die in den
  Produktivbetrieb geht, **einzeln im Gedächtnis haben** — nicht als Sammelposten.
  Das präzisiert die Freigabe vom 2026-09-02 („dev→main-Merge freigegeben"):
  sie gilt weiter für den Merge als *Vorgang*, aber der Zeitpunkt und der Umfang
  werden vorher benannt.
- **Nicht mergen, während ein Cron läuft**, wenn der Merge ein gerade
  ausgeführtes **Shell-Skript** anfasst: Bash liest Skripte während der
  Ausführung nach, ein Überschreiben mitten im Lauf kann den Prozess zerreißen.
  Auf das Ende warten (`pgrep -f "scheduled_cycle.sh|full_cycle_cron.sh"`).
- **Datenbank-Migrationen** sind davon unberührt: beide Worktrees teilen dieselbe
  Live-DB. Wird eine additive Migration beim Bauen auf `dev` ausgeführt, ist die
  Spalte für `main` schon da — der Merge bringt nur den Code, der sie kennt.

Anlass: zweimal derselbe Fehler (2026-09-10 und 2026-09-11). Am 11.09. lief der
Nachtlauf mit Batch 600 statt 3000 und der 09:00-Lauf fiel ganz aus, weil beides
nur auf `dev` stand — während Retention und Lizenz-Auflösung funktionierten,
weil deren Parameter in der Crontab-Zeile selbst stehen und nicht im Skript.

- **Doku-Stand auf `dev` und `main` konsistent halten** (`dev` sofort mitziehen; `main` erhält den Stand beim bewussten Release-Merge). *(Der frühere Parallel-Zweig `epic/alpha` wurde am 2026-07-19 gelöscht — es gibt keinen zweiten Doku-Branch mehr zu pflegen.)*
- Ursprung dieser Regel (2026-07-18): Content-Gen lief real längst auf Gemma-4-26B, während CLAUDE.md/README noch 30B/35B nannten — solche Drift ist ab jetzt konstitutionell auszuschließen.

### Arbeitsweise

Claude Code soll **möglichst autonom** arbeiten. Das bedeutet:

- **Triff eigene Entscheidungen** bei Implementierungsdetails (Library-Wahl, Dateistruktur, Naming Conventions, Error-Handling-Patterns). Frage nicht nach Präferenzen – wähle die beste Option und baue weiter.
- **Implementiere vollständig.** Keine Platzhalter, keine TODOs, keine "hier musst du noch..."-Kommentare. Jede Datei soll lauffähig sein.
- **Teste während du baust.** Schreibe Unit-Tests für kritische Logik (Deduplizierung, Schema-Validierung, Feed-Parsing). Führe sie aus bevor du weitergehst.
- **Verifiziere RSS-Feeds.** Bevor du einen Feed in die sources.yaml einträgst, prüfe ob die URL tatsächlich erreichbar ist und valides RSS/Atom liefert.
- **Erstelle eine funktionierende .env.example** mit allen benötigten Umgebungsvariablen.
- **Schreibe ein README.md** mit Setup-Anweisungen (Ollama-Modelle, DB-Setup, Abhängigkeiten, Start-Befehle).
- **Git-Commits** nach jedem abgeschlossenen Feature-Block mit aussagekräftiger Commit-Message.
- **Git-Branches** für jeden Sprint, Merge via Pull Request in `main`.
- **Push regelmäßig** auf GitHub – nach jedem Feature-Block, mindestens am Ende jeder Arbeitssession.

### Git & GitHub Workflow

**Repository:** GitHub, Organisation/User: `ZuluTwoThree`, Repo-Name: `catandary-trends`

**Initialisierung (einmalig):**
```bash
git init
git remote add origin git@github.com:ZuluTwoThree/catandary-trends.git
```

**Branch-Strategie (seit 2026-07-08 — dev/main statt Sprint-Branches):**
- `main` – stabiler, deployter Prototyp (**"save"**). Prod-Server 3001 läuft von hier. Nur bewusst per Merge aus `dev` aktualisieren.
- `dev` – Integrations-Branch für laufende Arbeit. Hierhin committen; nach Stabilisierung → `main` mergen + 3001 neu bauen.
- Feature-Branches optional bei komplexen Features (von `dev` abzweigen, in `dev` zurück).
- `product/trend-radar` – **Branch am 2026-07-19 gelöscht, als Tag `archive/product-trend-radar-2026-06-11` (57eecaf) archiviert.** War die divergente Produkt-Variante (Sales-Kit/Pricing/Kunden-Portal, Stand 2026-06-11, 338 hinter main). **Nicht in main/dev mergen** (reaktiviert das entfernte Brave-Search-Radar + Aggregator-Sourcing, gegen das Legal-Primärquellen-Prinzip). Bergbar aus dem Tag (extrahieren, nicht mergen): das Sales-/Business-Material unter `docs/sales/`, `docs/BUSINESS_PLAN.md`, `docs/SETUP_VERKAUF.md` — nutzt aber die **alte** 4-Tier-Preisstruktur (basic/team/pro/agency), abgelöst durch Starter/Pro/Super Pro+ + Hypercare.
- **Gelöschte Branches** (alle vollständig in `main` bzw. als Tag gesichert): `sprint/*` (2026-07-08), sowie `hardening/release-candidate` + `epic/alpha` (2026-07-19, nach dem Release-Merge `dev`→`main` PR #62). `epic/alpha` war die Alpha-Epic-Arbeit (Foresight/Monetarisierung/UX/Newsletter); ihre 2 Restcommits waren inhaltsgleiche Doku-Syncs, deren Endzustand in `main` steht. Offener Alpha-Rest = Owner-Gates (Stripe/Resend/UX/Labels), kein Code-Blocker (siehe `docs/issue_status.md`).
- `feature/foresight-radar` – **die gesamte Radar-/Foresight-Instrument-Arbeit, geparkt am 2026-08-07** (38 Commits, Basis `main` @ `146d522`). Enthält: Horizont-Radar (H1/H2/H3, kalibriert über 52 Felder), Cluster- und Mega-Trend-Radare, Signalwolke, Blechschmidt-Portfolio, und „Der Messtisch" (`pipeline/instrument.py`, `scripts/instrument.py`, `/trends/foresight/instrument`) inkl. Suchfeld-Einstieg, Korpus-Projektion und Automatisierung der Relevanzbewertung. Doku dazu: `docs/radar_*.md`, `docs/instrument_learning_curve.md`.
  - **Warum getrennt:** `dev` sollte für andere Entwicklung frei werden, ohne dass ein `dev`→`main`-Merge das unfertige Radar mitveröffentlicht (Owner 2026-08-07).
  - **Zustand bei Parkzeit:** lauffähig, 271 pytest / 142 vitest / tsc grün; läuft im Worktree `/home/dirk/projects/ct-dev` auf Port 3004.
  - **Wiederaufnahme:** auf dieser Branch weiterarbeiten, vorher `git rebase main` (die Nicht-Radar-Arbeit steckt bereits in `main`, es gab beim Parken keine Divergenz außerhalb der Radar-Dateien).
- **Stand 2026-09-01:** `feature/foresight-radar` wurde gelöscht und als Tag `archive/foresight-radar-2026-08-07` gesichert; der Rückweg fürs Radar ist `feature/radar-rebase` (Worktree `/home/dirk/projects/ct-radar`, Plan #92). Der Absatz oben beschreibt den Parkzustand vom 07.08. (damals :3004 in `ct-dev`; heute läuft dort `dev`).
- **Aktiv sind `main`, `dev` und `feature/radar-rebase`.** Archiv-Referenzen liegen als `archive/*`-Tags (nicht als Branches). Worktrees: `~/projects/catandary-trends`=main (:3001), `~/projects/ct-dev`=dev (:3004, :3999), `~/projects/ct-radar`=radar-rebase.

**Commit-Konventionen:**
```
feat: add RSS feed poller with sources.yaml config
fix: handle malformed RSS entries gracefully
refactor: extract Ollama retry logic into shared client
test: add unit tests for deduplication
docs: update README with setup instructions
chore: add .gitignore, .env.example
```

**Workflow (dev → main):**
```bash
# Laufende Arbeit auf dev
git checkout dev
git pull

# Während der Arbeit: regelmäßig committen und pushen
git add -A
git commit -m "feat: implement feed poller for FOOD + TECH verticals"
git push origin dev

# Stabilen Stand nach main übernehmen (bewusster Schritt)
git checkout main
git merge dev
git push origin main
# danach 3001 neu bauen + Neustart über systemd (seit 2026-07-13, #38):
# cd frontend && npm run build && systemctl --user restart catandary-frontend
# (Unit: deploy/systemd/catandary-frontend.service — ohne DATABASE_URL, Socket-Default; Autostart via Linger)
```

**Claude Code soll autonom:**
- Auf `dev` committen und pushen; `main` nur per bewusstem Merge aktualisieren (main bleibt der deploybare "save")
- Nach jedem abgeschlossenen Feature committen und pushen
- Keine manuellen Merge-Konflikte hinterlassen

**Tags/Releases:**
- `v0.1.0` – Sprint 1 (Pipeline MVP)
- `v0.2.0` – Sprint 2 (Content Gen + DB)
- `v0.3.0` – Sprint 3 (Frontend MVP)
- `v0.4.0` – Sprint 4 (Launch)
- `v1.0.0` – Alle Vertikale live

### Entscheidungsprinzipien

Bei Unsicherheit, folge diesen Prinzipien:
1. **Einfachheit über Komplexität** – die einfachere Lösung ist fast immer besser
2. **Lauffähig über perfekt** – ein funktionierendes MVP schlägt eine halbe Idealarchitektur
3. **SQLite zuerst** – starte mit SQLite, PostgreSQL-Migration kommt in Sprint 2
4. **Weniger Quellen, dafür verifiziert** – lieber 3 funktionierende RSS-Feeds als 15 kaputte URLs
5. **Structured Output mit Retry** – immer Pydantic-Validierung + 3 Retries implementieren
6. **Logging überall** – jeder Pipeline-Schritt loggt Input, Output, Dauer, Fehler

### Projektstruktur (Empfohlen)

```
catandary-trends/
├── CLAUDE.md                    # Diese Datei
├── README.md                    # Setup & Usage (von Claude Code generiert)
├── .gitignore                   # Python, Node, .env, DB-Dateien
├── .env.example                 # Umgebungsvariablen (ohne Secrets)
├── sources.yaml                 # Quellen-Konfiguration
├── pipeline/
│   ├── __init__.py
│   ├── feed_poller.py           # RSS-Feed-Aggregation
│   ├── llm_processor.py         # LLM-Pipeline (Filter → Extract → Classify → Generate)
│   ├── auto_publisher.py        # Auto-Publish high-confidence Drafts
│   ├── newsletter_generator.py  # Wöchentlicher Newsletter
│   ├── source_report.py         # Neue-Quellen-Report
│   ├── models.py                # Pydantic-Schemas für LLM-Outputs
│   ├── db.py                    # Datenbank-Layer (SQLite → PostgreSQL)
│   ├── ollama_client.py         # Ollama-Wrapper mit Retry-Logic
│   └── config.py                # sources.yaml Loader + Settings
├── frontend/                    # Next.js App (ab Sprint 3)
│   ├── app/
│   │   ├── trends/
│   │   │   ├── page.tsx         # Hauptseite
│   │   │   ├── [slug]/page.tsx  # Einzelartikel
│   │   │   ├── vertical/[v]/page.tsx
│   │   │   └── ...
│   │   └── layout.tsx
│   ├── components/
│   ├── lib/
│   ├── tailwind.config.ts
│   └── package.json
├── tests/
│   ├── test_feed_poller.py
│   ├── test_llm_processor.py
│   ├── test_models.py
│   └── test_deduplication.py
├── scripts/
│   ├── setup_db.py              # DB-Initialisierung
│   ├── verify_feeds.py          # RSS-Feed-Validierung
│   └── review_cli.py            # Manueller Review-Client
└── requirements.txt
```

### Weiterentwicklung

**Das Backlog lebt seit 2026-07-02 in den [GitHub Issues](https://github.com/ZuluTwoThree/catandary-trends/issues)** (Labels: `foresight`, `acquisition`, `pipeline`, `frontend`, `content-quality`, `ops`, `prio-high`). Vor jeder neuen Feature-Planung **immer zuerst `gh issue list` prüfen** — die Issues enthalten den Kontext zu Ideen, die schon durchdacht oder angetestet wurden (Dry-Runs, Methodik-Notizen, Wiedervorlage-Kriterien). Neue Ideen, die nicht sofort umgesetzt werden, als Issue anlegen statt im Code oder Chat verloren gehen zu lassen. `BACKLOG.md` im Repo-Root ist nur noch die Issue-Übersicht + Meilenstein-Historie (Volltexte der alten Items: Git-Historie, Stand `1fd18e5`).

Alle 6 Sprints sind abgeschlossen. Neue Features und Verbesserungen werden direkt auf `main` oder in Feature-Branches entwickelt. Aktuelle Prioritäten:

1. **Statischer Export** der öffentlichen Seiten aufs Hetzner-Webhosting (#82/#93, Welle 2 in `docs/launch/09_launch_plan_2026-09-02.md`; Design `docs/audits/2026-09-02_static_export_design.md`)
2. **Launch-Rest** — `unsubscribe.php` + Sender-Umbau (#16), Auth/Stripe-Rückbau + Landing-Copy (#93), Compliance-Punkte aus `docs/audits/2026-09-02_compliance_review.md`
3. **Owner-App** — Query-Quality-Gate (#67), Research Pulse (#73); Field Watch als Nachfolge-Idee der entfernten Scouting-Dossiers (#108). *(Korpus-Rechercheur-Frontend #95 und Newsletter-Deep-Dive #96 sind seit 2026-09-19 entfernt bzw. stillgelegt.)*

*(Die früheren drei Punkte — Cron-Orchestrierung, Newsletter-Generator, „Hetzner Caddy + PM2" — sind erledigt bzw. überholt: alle Crons laufen (s. Cron-Block oben), die Newsletter-Website-Edition läuft per Cron seit 29.08., PM2 ist seit #38 durch systemd ersetzt, der VPS-Pfad ist verworfen.)*

**Hinweis zur Vertical-Balance:** LIFESTYLE, DESIGN und FASHION sind die *Now*-Trendsignale im Foresight-Modell (kurze Lead-Zeit). Ihr kombinierter Anteil (~18 %) ist gesund — keine aktive Quellenausweitung nötig.

---

## Quellenbalance & Pipeline-Optimierung

### Ist-Zustand (Stand 2026-08-07, Quellenzahl aktualisiert 2026-09-02)

**601 aktive Quellen in der DB / 560 aktive RSS-Quellen in `sources.yaml`** (Ist 2026-09-09, Aufschlüsselung s. „Quellenwachstum" oben; war 257 am 2026-08-07, 323 am 2026-09-02). 21,6 Mio. Raw Entries, 1.134.488 Trends (67.035 published), **28 kanonische Mega-Trends** (22 + 6 neue Keys aus der Taxonomie-Erweiterung 2026-08-07: Quantum Information Science, Next-Gen Semiconductors, Orbital Economy, Evolution of Work Models, Education & Lifelong Learning, Digital Healthcare Integration — siehe `docs/mega_taxonomy_decision_2026-08-07.md`). Die übrigen Zahlen dieser Zeile (Raw Entries, Trends, Mega-Trends) sind weiterhin der 2026-08-07-Snapshot, nicht neu gemessen.

*(Die folgende Tabelle ist der historische Snapshot 2026-05-29 — nur published Trends der Frühphase; der heutige Korpus ist backfill-dominiert.)*

| Vertical | Trends | Anteil | Bewertung |
|----------|--------|--------|-----------|
| TECH | 9.623 | 36% | TECH-Dominanz hat zugenommen (vorher 32%) — Quellenvielfalt rechtfertigt das weiterhin |
| BIZ | 4.699 | 18% | Stabil hoch |
| HEALTH | 3.812 | 14% | Weiter gewachsen, Endpoints/Healthcare IT News tragen |
| ECO | 2.388 | 9% | Stabil |
| FOOD | 1.691 | 6% | Anteil **gesunken** (vorher 12%), aber 8 neue FOOD-Quellen seit 2026-05-24 noch in Catch-up — Effekt schlägt erst über Wochen voll durch |
| LIFESTYLE | 1.594 | 6% | Stabil |
| DESIGN | 1.343 | 5% | Stabil |
| FASHION | 1.224 | 5% | Stabil |
| **TOTAL** | **26.374** | **100%** | |

### Balance-Prinzip für die Datenpipeline

1. **TECH-Dominanz beobachten** — bei 36% durch Quellenvielfalt (VC/Startup + Deep Tech + Halbleiter + Quantum) erklärt, aber Trend zur weiteren Konzentration im Auge behalten
2. **Regelmäßiger Balance-Check** (monatlich): bei >3× Abweichung vom Median Quellen und Schwellenwerte anpassen
3. **FOOD-Catch-up** beobachten — die 8 Quellen aus dem 2026-05-24-Commit (`a561b74`) füttern erst seit dem 2026-05-25-Lauf. Anteil sollte sich über 4–6 Wochen Richtung historischer ~10–12% normalisieren.

### Geplante Quellen-Ergänzungen

Keine offenen Ergänzungen. Lebensmittelzeitung wurde in `sources.yaml` eingebunden.

---

## Stage-6 auf llama.cpp (Content-Gen; Gemma-4-26B aktuell seit #11 / 2026-07-14; 30B/35B revertierbar)

Auf der 24-GB-Karte kann Stage 6 (Content-Generierung) auf ein deutlich größeres Modell umgeleitet werden:

- **Modell (aktuell):** **Gemma-4-26B-A4B-it-qat-UD-Q4_K_XL** (~16 GB), Start-Skript `start-gemma4-26b.sh`. Umstellung von Qwen3-30B via **#11 (2026-07-14)** nach kontrolliertem A/B (n=70, Fisher p=0.013): 30B erfand in **32,9 %** der Bodies fake Spezifika (z. B. „Ordinance 2023-47"), Gemma-26B nur **8,6 %**. *(Die Wortziel-Behauptung ist widerlegt — Median am Umstiegstag 14.07. von 131 auf 105 gefallen, seither ~109. ~100 Wörter sind seit 2026-08-19 die akzeptierte Länge; siehe `docs/confidence_threshold_eval_2026-08-18.md`.)* Qwen3.6-35B (`start-qwen3.6-35b.sh`) bleibt installiert und revertierbar; das 30B (GGUF + Startskript) wurde beim llama.cpp-Umbau 2026-08-29 entfernt. Geladen via `llama-server` (systemd user unit `llama-server.service`, Port 8090).
- **Routing:** `STAGE5_BACKEND=llamacpp` in `scheduled_cycle.sh` aktiviert den Pfad — gegated nur darauf, dass das in `STAGE5_MODEL` gesetzte **Start-Skript** (aktuell `start-gemma4-26b.sh`) existiert und das erwartete GGUF referenziert, **nicht** darauf, worauf `start-active.sh` beim Start zeigt. Content-Gen versucht damit **immer** das gesetzte Modell, egal welches Modell (oder keines) bei Pipeline-Start geladen war.
- **GPU-Handover:** `pipeline/gpu_handover.py` (`content_gen_on_llamacpp`) **hängt vor Stage 6 den Symlink `start-active.sh` selbst auf das Content-Gen-Start-Skript um** (speichert das vorherige Ziel), entlädt die Ollama-Modelle, startet llama-server, und stoppt es nach Stage 6 wieder + **stellt den Symlink zurück** (wie die 8B-/Embedding-Handover). Der Pre-Flight prüft danach konsistent das nun gesetzte Modell — OOM-Schutz bleibt. Stages 7–9 nutzen Ollama wieder (Qwen3 8B für Reclassify on-demand). MODEL_START_SCRIPTS mappt die Content-Gen-GGUFs (Gemma-26B + 30B + 35B) auf ihre Start-Skripte.
- **Besitz der Unit — Cleanup nur eigene Server (#98, seit 2026-09-05):** `llama_server_start` vermerkt nach dem Ready-Check `MAINPID OWNERPID` in `data/llama-server.<job>.pid` (`<job>` = `GPU_JOB_NAME` oder Stem des Einstiegsskripts: `run_full_cycle`, `signal_batch_embedded`, `research_pulse` …; gleiches Format wie `llama_unit_record_owner` in `scripts/lib/gpu_guard.sh`, der Richter-Block nutzt `scheduled_cycle-judge`). `llama_server_stop` stoppt die Unit nur, wenn ihre MainPID noch die vermerkte ist — hat ein anderer Job sie inzwischen neu gestartet, bleibt sie stehen (Warnung `is not the one this job started … leaving it running`) und der Symlink wird ebenfalls nicht angefasst (der andere Job stellt den Ruhezustand bei seinem Exit her). Umgekehrt verweigert `llama_server_start` die Übernahme eines Servers, den ein noch **lebender** anderer Job vermerkt hat (`RuntimeError: … belongs to running job <job> (pid N)`); Vermerke toter Jobs werden dabei gelöscht. Ohne Vermerk (MainPID beim Start unlesbar) gilt der alte Stop-Pfad. Die Ausnahme „VRAM freiräumen vor dem Cycle" (`full_cycle_cron.sh` killt ALLE manuellen `build/bin/llama-server`) bleibt, läuft aber nur noch, wenn der Kollisionswächter keinen fremden GPU-Job sieht — sonst Abbruch rc=75.
- **Content-Guard:** Wortzahl-Validator retryt bis zu 3× bei vorzeitig terminierten Body-Strings (Grammar-Artefakt bei temp 0.7). In den ersten vier Nachtläufen war die "alle 3 Versuche failed"-Rate <0,25 %.
- **Modell-Identitäts-Check je Request (#98, seit 2026-09-05):** llama-server ignoriert das `model`-Feld und antwortet mit dem geladenen GGUF. `llamacpp_client.chat_structured(verify_model=True)` — gesetzt in allen llama.cpp-Pfaden der Stages 2/3/4/6/8 — prüft vor dem ersten Request (TTL-gecacht, `LLAMACPP_MODEL_CHECK_TTL=30` s je erwartetem Modell) und vor **jedem Retry** `GET /v1/models`; weicht das geladene Modell ab, fliegt `ModelMismatchError` (nie retryt, nie zu `None` verschluckt). Stage 6 bricht dann ab: der getroffene und alle folgenden Einträge bleiben **unprocessed** (nicht gefiltert), die schon generierten laufen in Stage 7 weiter, `errors` zählt die Reste → `run_full_cycle` endet mit Exit 2. In den 8B-Stages propagiert der Fehler aus `_concurrent`/`reclassify_drafts` und beendet den Lauf; der Hybrid-Pfad fällt bei Mismatch bewusst NICHT auf den Voll-8B-Pfad zurück. Ein unerreichbarer Server ist kein Urteil (der Request selbst entscheidet). Vorfall: 05.09. antwortete der Embedding-Server auf die Content-Requests mit 200 OK, der Cliché-Guard verwarf jeden Body und Stage 6 re-rollte stundenlang.
- **Rückbau:** `STAGE5_BACKEND=ollama` (Env-Override) erzwingt den Ollama-14B-Pfad. Alternativ das Content-Gen-Start-Skript entfernen/umbenennen → `scheduled_cycle.sh` fällt automatisch auf Ollama zurück. **Zurück auf 30B/35B:** in `scheduled_cycle.sh` `STAGE5_MODEL`/`STAGE5_START` auf `start-qwen3-30b.sh` bzw. `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` + `start-qwen3.6-35b.sh` zeigen lassen. (Das bloße Umhängen von `start-active.sh` deaktiviert den Pfad **nicht** — der Handover hängt selbst um.)
- **Zugehörige Goals:** offene Erweiterung der Quellen-Architektur, siehe `goals/` und `pipeline_expansion_prompt.md`.

## Scouting-Dossiers — entfernt 2026-09-19 (Owner: „Das Feature trägt nicht")

**Was es war (#95, 2026-09-01 bis 2026-09-19, 30 Runden):** ein agentischer
Korpus-Rechercheur (`scripts/corpus_research.py`, Qwen3.8-27B lokal) als
Owner-Werkzeug mit Desk `/trends/dossiers` — Auftragszettel, Worker auf
Knopfdruck, Messkette (CPC → TIR → Lead-Time), DR-Vorlauf, Leser,
abschnittsweises Schreiben, Endkontrolle, Korpus-Evidenz-Block, Advisor mit
Freigabe durch einen Menschen, plus der „Deep Dive of the Week" des
Newsletters über denselben Auftragspfad.

**Warum entfernt:** sieben Dossierversionen zum selben Thema und 48 Läufe
insgesamt zeigten ein stabiles Muster — alles, was die Plattform *misst*,
hält; alles, was das Modell *schreiben* muss (Beschaffung fremder
Primärquellen, Verdichtung, Urteil), wackelt; der Leser war nie zufrieden,
auch nicht bei v9 mit dem besten Nutzenwert von 50 Läufen (U 0,56). Messungen,
Runden und Befunde: `docs/agentic_dossiers.md` (Runden 1–30),
`docs/dossier_vs_deep_research_2026-09-07.md`, `docs/dossier_manual_run_2026-09-19.md`,
`docs/plan_dossier_agent_2026-09-18.md` — bleiben als Historie stehen, je mit
Banner.

**Was bleibt (generisch, ohne Dossier-Abhängigkeit):** `pipeline/web_search.py`
(Brave → SearXNG-Fallback), `pipeline/web_cache.py` (`data/web_cache.sqlite`),
`pipeline/legal_text.py` (Rechtstexte artikelweise schneiden),
`article_fetcher.pdf_text` + `max_chars` (PDF-Abruf, große Kappe für
Rechtstexte), `pipeline/prompt_catalog.py` + `/trends/ops/prompts` (ohne die
Gruppen `dossier`/`advisor`), der CPU-Embedder `:8091`
(`catandary-embed-cpu.service`, `RESEARCH_EMBED_HOST` — heute u. a. für
`scripts/validate_emerging.py`), `frontend/src/lib/detachedSpawn.ts` (Pulse,
Snapshot), `pipeline/gpu_handover.model_on_llamacpp` (Draft-Richter) und die
Modellregistrierung Qwen3.8-Flash-Next. **DB-Tabellen bleiben stehen, kein
DROP** (wie bei früheren Rückbauten): `dossier_orders`, `dossiers`,
`dossier_run_outcomes`, `dossier_source_priors`, `dossier_query_stats`,
`advisory_notes`; nichts liest oder schreibt sie mehr.

**Entfernt:** `pipeline/{advisory,advisory_store,dossier_*}.py`,
`scripts/{advisory,corpus_research,dossier_*,rescore_must_answer,migrate_dossier_*}.py`,
`tests/test_{advisory,dossier_*}.py`, `frontend/src/app/trends/dossiers/**`,
`frontend/src/lib/{dossiers,dossierWorker,dossier-access,dossierIntake,advisory,advisoryWorker}.ts`,
`DossierQuestionField.tsx`, Nav-Eintrag „Scouting Desk", Cockpit-Karte,
`/trends/dossiers` aus `BLOCKED_PREFIXES`/`proxy.ts`/`static-export.exclude`,
`DOSSIERS_ENABLED`/`DOSSIER_*`-Env, die Muster `dossier_worker|corpus_research`
aus `gpu_guard.sh`/`ops_probe.py`. Die Owner-Guards der Pulse-/Snapshot-Actions
nutzen jetzt `canReview()` (`lib/review-access.ts`); `repoRoot()` lebt in
`lib/researchPulseWorker.ts` (`WORKER_ROOT`, früher `DOSSIER_WORKER_ROOT`).

**Rückweg:** Git-Tag `archive/dossiers-2026-09-19` (dev-HEAD `177c34f` vor dem
Rückbau, Runden 1–30). **Nachfolge-Idee:** „Field Watch" — die Plattform als
Messinstrument, nicht als Autor: `docs/value_proposition_field_watch_2026-09-19.md`
und Issue #108.

## Research Pulse (#73 Teil 1, seit 2026-09-04)

Wöchentliche Synthese je Mega-Signal-Theme aus dem frischen Forschungskorpus
(`research_signals`, Embeddings `trends.embedding_1024` — der Fresh-Korpus ist vollständig
embedded). Je Theme und ISO-Woche: Volumen vs. Median der vier Vorwochen, KMeans-Cluster
(k ≤ 5, fester Seed) mit c-TF-IDF-Labels, Vorwochen-Zuordnung per pgvector-Nächster-Zentroid
(→ Wachstum/„emerging"), 4 zentroid-nächste Papers je Cluster (OA-Badge nur für Preprint-Server),
100–150-Wörter-Absatz auf Gemma-4-26B (T=0.2, Seed 73, nur Zahlen aus dem Messblock, keine
Prognosen). Versioniert in `research_pulse` (additive Migration `scripts/migrate_research_pulse.py`).

- **Paper-Basis (seit 2026-09-05, #73):** `research_signals.kind` (`article|preprint|review|
  chapter|artifact|unknown`, Regelquelle `pipeline/research_kinds.py`, Migration + Backfill
  `scripts/migrate_research_signals_kind.py`, Rebuild klassifiziert mit). Pulse und Explorer
  zählen `kind <> 'artifact'` — OpenAlex indexiert Zenodo-/figshare-/GitHub-Deposits als Works,
  im Fresh-Sweep waren das 20,6 % der letzten 14 Tage (AI-Theme W35: 1.083 von 4.919). Der
  Ingest (`ingest_openalex.py`, Concept-Sweeps) nimmt seit 05.09. nur noch article/preprint/
  review/book-chapter und sperrt Repository-Hosts. Deep-Dive-Themenwahl zählt published
  Artikel (nicht research_signals) — Artefakte sind dort strukturell nicht drin.

- **Rechnen:** `.venv/bin/python scripts/research_pulse.py [--week 2026-W35] [--themes a,b]
  [--no-llm] [--limit N]` — ein GPU-Handover für alle Texte, Ruhezustand wird wiederhergestellt.
  Referenz 2026-09-04: 28 Themes ohne LLM 14 s; 5 Themes mit Gemma 28 s; 2026-09-05: 28 Themes
  ohne LLM 15 s, 1 Theme mit Gemma 19 s.
- **Frontend:** `/trends/foresight/research/pulse` (Übersicht + Wochen-Wechsler),
  `/pulse/[theme]` (Herkunftskopf, Messblock, Text, Cluster, „Recompute"-Knopf = Server Action mit
  Owner-Modus `canReview()` + Origin-Check, spawnt das Skript detached via `detachedSpawn.ts`). Einstiege: Research
  Explorer, Foresight-Cockpit, `/trends/mega/[m]` (nur Owner-Modus — Foresight ist nicht im Export).
- **Betrieb:** Cron **installiert 2026-09-18** (Owner-Entscheid; `deploy/crontab.txt`, Wrapper
  `scripts/weekly_research_pulse.sh`, Sa 12:00, Status-Notiz in die Montags-Mail). Bis dahin
  nur Vorschlag: W36/W37 fehlten und wurden am 18.09. von Hand nachgerechnet (je ~55 s,
  19/28 Themes mit Text). Der Knopf bleibt für einzelne Themes/Wochen.
- Methode/Datenlage: `docs/research_pulse.md`.

## Field Watch / Trajectory Sheet / Feldprobe (Produkt, seit 2026-09-20)

Der Pivot vom 19./20.09. (`docs/business_model_2026-09-19.md`,
`docs/commercialization_plan_2026-09-20.md`, Owner-Freigabe der Namen und Preise
20.09.): **das Messen ist das Produkt, Prosa kommt vom Owner.** Drei Angebote,
Preise sichtbar auf der Landing (`docs/launch/preview.html`, FAQ, Muster-PDFs
unter `/trends/samples/` aus `frontend/public`): Trajectory Sheet 1.490 € je
Feld, Field Watch 390 €/Monat für drei Felder (Setup 900 €, +90 €/Feld, Pilot
290 €), Analyst Day 1.200 €, Feldprobe frei. Kein Checkout, keine Konten —
Rechnung.

- **Code:** `pipeline/field_watch.py` (Messung: `measure_week`, `measure_sheet`,
  `probe`, `quant_block`; `TIER_SQL` = SQL-Zwilling von `tiers.tier_of`, per Test
  gegen dessen Marker gepinnt), `pipeline/field_watch_render.py` (HTML/SVG/PDF,
  Chromium der Playwright-Installation, `FIELD_WATCH_CHROME`), CLI
  `scripts/field_watch.py` (`<kunde>` Wochenblatt · `--sheet <feld>` ·
  `--probe "<phrase>"` · `--export` Kundenseite · `--all` Cron · `--sample`).
- **Feld** = `fields/<kunde>.yaml` (Vorlage `fields/example.yaml`, echte Kunden
  gitignored): Suchphrasen (`phraseto_tsquery` gegen `idx_trends_fts` bzw.
  `patent_search.tsv`) + CPC-Anker für den Reifegradblock (`tir_trajectory` über
  die Anker, Zykluszeit, Zentralitäts-Peak — kein Embedding, keine GPU). Ohne
  `--cpc` holt nur die Feldprobe Kandidatenklassen aus der Technologie-Suche
  (GPU-Handover). Das Mapping ist der Owner-Checkpoint und steht auf jedem Blatt.
- **Regeln, die auf jedem Blatt stehen** (und öffentlich auf
  `/trends/methodology#field-method`): Ebene nach Quellentyp; Anteil je 10.000
  Signale der Ebene; Quartale auf **festem Quellenpanel** (Quelle in den ersten
  UND letzten vier Quartalen des Fensters aktiv — Milchalternativen roh 65 → 16
  je 10k, Panel 66 → 59: die Sammelrampe 2026, nicht das Feld); Take-off =
  Ramp-Regel (≥ 15 % des Peaks, ≥ 3), am Fensterrand als Rand berichtet;
  Wissenschaft aus `research_corpus` ab 2010, Markt ab 2020 in Breite;
  Akteure = Extraktion (13 % der Presse-Zeilen, Untergrenze); dünne Zellen als
  Tabelle. **Kein Modelltext im Produktpfad** — der Kennzeichnungsfuß
  („deterministische Abfragen, kein Sprachmodell") bleibt nur so wahr; die
  einzige Prosa ist `reading:` aus der Kundendatei, als vom Analysten gekennzeichnet.
- **Ausgabe:** `data/field_watch/<kunde>/` (`<woche>.{pdf,html,json}`,
  `sheet-<feld>-<datum>.*`, `site/` für den Kundenbereich), Feldproben unter
  `probes/`; Protokoll `field_watch_runs` (additive Migration
  `_migrate_field_watch`, in `init_db`, Live-DB 20.09.).
- **Kundenbereich:** `trends/clients/<kunde>/` auf dem Webspace, Upload von Hand
  (SFTP), Basic Auth per `.htaccess`-Vorlagen in `deploy/webspace/`. Der Publisher
  schützt den Teilbaum (`publish_static_site.OWNER_SUBTREES`: nie schreiben,
  listen, löschen — sftp-Plan, `--full`, rsync-Exclude; Test).
- **Cron:** `scripts/weekly_field_watch.sh`, Zeile Sa 12:30 in `deploy/crontab.txt`
  — Vorschlag, scharf erst mit dem Merge nach `main`; ohne Kundendateien no-op;
  Notiz in der Montags-Mail (`review_notify.GPU_JOB_NOTES`).
- **Muster:** `docs/samples/` (LFP-Sheet, FOOD-Wochenblatt W38), erzeugt mit
  `--sample` aus `fields/example*.yaml`; Kopien auf der Website.

## Newsletter Deep Dive (#96 — seit 2026-09-19 stillgelegt)

Die rechercheur-gestützte Sektion „Deep Dive of the Week" lief vom 2026-09-04
bis 2026-09-19 als Dry-Run über den Auftragspfad der Scouting-Dossiers. Mit
deren Rückbau gibt es den Rechercheur nicht mehr; Historie, Gates und
Kalibrier-Protokoll: `docs/newsletter_deep_dive.md`.

- **Heute:** `scripts/newsletter_deep_dive.py --year J --week KW` macht nur noch die
  deterministische Themenwahl (Ranking gespeichert) und schreibt dann hart
  `status: "disabled"`, `error: "dossier feature removed 2026-09-19"` nach
  `newsletter_editions.deep_dive` — derselbe Pfad wie `no_theme`: Edition
  unverändert, kein Modell, keine GPU, rc 2 (`dd=2` in der end-Zeile des Wrappers,
  nie ein Blocker). `data/newsletter_deep_dive_last.json` + Morgen-Mail-Zeile
  (`review_notify._deep_dive_line`) nennen den Grund. Der Wrapper-Schalter
  `NEWSLETTER_DEEP_DIVE=dry-run` bleibt Default off.
- **Gespeicherte Editionen** (ein Dry-Run: W35 2026, `gate_failed`) rendern weiter: Gate-, Kondensat-
  und Speicher-Funktionen bleiben im Skript, `DeepDive.tsx`/`newsletterEditions.ts`
  zeigen den Datensatz ohne Desk-Link (den Desk gibt es nicht mehr;
  `dossier_slug`/`dossier_version` sind reine Anzeigefelder). Öffentlich
  weiterhin nur `gate_passed && !dry_run` — also nie.
- Prompt `newsletter-deepdive` bleibt im Katalog (Gruppe `newsletter`) mit dem
  Vermerk, dass er nicht mehr aufgerufen wird.

## Technische Hinweise

- **Aktuell (Linux-Workstation, Stand 2026-09-02):** Python = `.venv/bin/python` im Repo. Ollama ist installiert (`~/.local/bin/ollama`), aber **kein systemd-Dienst und produktiv nicht aktiv** (Port 11434 am 02.09. leer) — der ganze Cycle läuft über den llama-server auf :8090 (s. „Backend-Realität" oben). Ollama nur manuell starten, wenn ein Stage auf `STAGE*_BACKEND=ollama` steht; Client-Adresse dann `OLLAMA_CLIENT_HOST` (Default `http://127.0.0.1:11434`, `pipeline/config.py`; `.env.example` setzt `OLLAMA_HOST` für den Server-Bind).
- *(Historisch, Windows-Ära bis ~06/2026: Ollama als Windows-Exe, Python unter `C:\Users\Dirk\...\Python313`. Nicht mehr gültig.)*
- **Poller-Dry-Run** (seit 2026-09-09): `python -m pipeline.feed_poller [VERTICAL …] --dry-run` holt die
  Feeds und zählt, wie viele Einträge neu wären — aufgeteilt in Artikelmaterial und „nur Signal" (die 33
  Vorbehalts-Quellen), plus die ergiebigsten Quellen. Schreibt nichts: keine Quellen-Zeile, keinen Eintrag,
  kein `last_fetched` (`db.known_entry_urls` schaut nur nach). Vor Nächten gedacht, in denen viele neue
  Quellen zum ersten Mal ziehen.
- LLM-Processor Default-Batch ist 10, für große Batches: `python -m pipeline.llm_processor 200`
- Pipeline-Output in Datei umleiten (nicht pipen!): `python -m pipeline.llm_processor 200 > data/llm_processor.log 2>&1`
- Frontend-Ports: `:3001` = Prod-Instanz (systemd, main-Worktree), `:3004` = Dev-Server aus `ct-dev`, `:3999` = PUBLIC_MODE-Vorschau aus `ct-dev` (Details im Frontend-Abschnitt). `npm run dev` ohne Argument nimmt 3001 — im Dev-Worktree immer `-p 3004` mitgeben. Port 3000 war für Open WebUI reserviert (am 02.09. lauscht dort nichts).
- Qwen3 braucht `think=False` in Ollama-Calls (oder `enable_thinking=false` in llama.cpp) um Chain-of-Thought-Bloat zu vermeiden
