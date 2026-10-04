# GPT Researcher — Einsatzprüfung für Trajectory Sheet und Field Watch (2026-10-04)

> Owner-Frage 04.10.: Wie lässt sich <https://github.com/assafelovic/gpt-researcher>
> mit unserem Code, unseren Daten und APIs für die Produkte nutzen? Welche APIs,
> MCPs oder Skills fehlen? Geprüft am Quellcode (Stand `0957c30`, 26.09.2026,
> v0.16.0), **nicht installiert, nicht ausgeführt.**
> Hinweis: ein Produkt „Trajectory Shield" gibt es im Repo nicht; gemeint ist das
> **Trajectory Sheet** (Landing, Methodik-Seite, `pipeline/field_watch.py --sheet`).

## 1. Was das Werkzeug ist

Ein Recherche-Agent (Planer → parallele Sucher → Schreiber), Apache 2.0, Python ≥ 3.12.
Er formuliert Teilfragen, sucht, kratzt Seiten, filtert Passagen und schreibt einen
Bericht mit Zitaten (1.200 Wörter Default, `deep_research` rekursiv).

| Baustein | Was es gibt | Bezug zu uns |
|---|---|---|
| LLM | 27 Provider, u. a. `anthropic`, `ollama`, `openai` mit `OPENAI_BASE_URL` | llama-server :8090 ist OpenAI-kompatibel; Anthropic-Key ist in `.env` gesetzt |
| Embeddings | `custom`/`openai` mit Base-URL | CPU-Embedder :8091 (Qwen3-Embedding-8B) passt |
| Retriever | Tavily (Default), Brave, **SearXNG**, OpenAlex, Semantic Scholar, arXiv, PMC, **MCP**, **custom** | Brave-Key gesetzt, SearXNG läuft auf 127.0.0.1:8888 |
| `custom`-Retriever | GET auf `RETRIEVER_ENDPOINT?query=…` → `[{url, raw_content}]`, `requires_scraping=False` | der saubere Andockpunkt für unseren Korpus **und** unseren konformen Fetcher |
| Vektorspeicher | jeder LangChain-VectorStore mit `asimilarity_search` (`report_source="langchain_vectorstore"`) | unsere Vektoren liegen in `trends.embedding_1024`, nicht im `langchain_postgres`-Schema → Adapter nötig |
| MCP | als Client (Retriever `mcp`) und als Server (`gptr-mcp`: `deep_research`, `quick_search`, `write_report`, `get_research_sources`) | |

## 2. Harte Befunde gegen den Einsatz „wie geliefert"

1. **Der Scraper verletzt unsere Compliance-Regeln (#97).** Default-User-Agent ist ein
   gefälschter Edge/Chrome-String, kein robots.txt-Check, kein TDM-Vorbehalt-Check
   (kein Treffer für `robots`/`tdm` im Paket), 15 parallele Worker, kein Host-Delay.
   Unser Fetcher meldet sich als `CatandaryTrendsBot/1.0`, prüft robots RFC-9309-konform,
   TDM-Header/-Meta/`tdmrep.json` auch nach Weiterleitungen, drosselt je Host.
   → Einsatz nur, wenn **gpt-researcher selbst nichts holt**: Suche + Abruf über einen
   eigenen `custom`-Retriever, der `pipeline/web_search.py` und
   `article_fetcher.fetch_fulltext_result` benutzt und `raw_content` zurückgibt.
2. **Kein Modelltext im Produktpfad.** Beide Blätter tragen den Fuß „deterministische
   Abfragen, kein Sprachmodell" (`field_watch_render.py`). Ein generierter Absatz im
   Blatt macht diesen Satz falsch. `reading:` schreibt der Owner.
3. **Die Dossier-Erfahrung gilt weiter.** 48 Läufe bis 19.09.: was die Plattform misst,
   hält; was ein Modell schreiben muss, wackelt (`docs/agentic_dossiers.md`,
   `docs/dossier_vs_deep_research_2026-09-07.md`). gpt-researcher ist dieselbe
   Architektur wie der entfernte Rechercheur, nur fremd gepflegt. Er löst das
   Schreibproblem nicht; er spart Bauzeit für die Such-/Abrufkette.
4. **Lokal nur mit Handover.** Der Ruhezustand (8B, 4 × 8.192 Token) ist zu klein für
   `SMART_TOKEN_LIMIT` 12.000 + Kontext. Ein lokaler Lauf braucht Gemma-26B/27B per
   `gpu_handover` und gehört in den Kollisionswächter (`gpu_guard.sh`), sonst kollidiert
   er mit dem 02:45-Cycle.
5. **Nicht in die gemeinsame venv.** `ct-dev/.venv` ist ein Symlink auf die venv von
   `main`; gpt-researcher zieht LangChain & Co. nach. Eine Installation dort wäre sofort
   für alle Crons live. → eigene venv (`~/venvs/gptr`), Aufruf als Subprozess.

## 3. Wo es trotzdem passt

| # | Einsatz | Produkt | Wer sieht es | Bewertung |
|---|---|---|---|---|
| A | **Rechtsrahmen-Anhang** (+390 €, im Plan „nach dem zweiten Kunden", 2 Tage) | Sheet | Kunde, als eigener gekennzeichneter Anhang, vom Owner gelesen | **bester Fit.** Evidenzfrage, nicht Urteilsfrage; `query_domains` auf EUR-Lex/BMJ/EFSA/EMA begrenzen, `legal_text.py` schneidet artikelweise. Spart den Bau der Such-/Zitatkette. Eigene Kennzeichnung nötig (Art. 50 Abs. 4 greift nicht, wenn der Owner liest und verantwortet — wie beim Newsletter). |
| B | **Feld-Einrichtung** (Setup 900 €): Kundenphrase → Fachbegriffe, Synonyme, DE/EN-Schreibweisen, Normbezeichnungen als Kandidaten für `terms:` | Sheet + Field Watch | nur Owner | nützlich, risikoarm. Ergebnis geht nie ins Blatt, sondern durch `field_watch.py --probe` (Treffer zählen) und den Owner-Checkpoint. |
| C | **Vertriebsvorbereitung**: Interessent → welche Felder, welche Wettbewerber, welche Förderprogramme, vor dem 20-min-Gespräch und der Feldprobe | Verkauf | nur Owner | nützlich. Nur Firmendaten, keine Personendaten an Provider. |
| D | **„Warum hat sich das bewegt?"** zu einem Ausschlag im Wochenblatt, recherchiert über **unseren** Korpus (custom-Retriever auf `/api/search`) + Web | Field Watch | nur Owner, als Notiz für den eigenen `reading:`-Absatz | mittel. Hilft beim Schreiben, ersetzt es nicht. |
| — | Text fürs Blatt, `reading:` generieren, Akteurs-Lücke schließen | — | — | **nein.** Bricht die Kennzeichnung; die Akteurs-Lücke ist ein NER-Problem auf dem Signalpfad, kein Rechercheproblem. |

Die OpenAlex-/arXiv-/PMC-Retriever bringen uns nichts Neues: der lokale
`research_corpus` (45,5 M) ist größer und monatlich synchron.

## 4. Was fehlt (APIs, MCPs, Skills)

**Selbst zu bauen — der eigentliche Hebel:**

1. **Konformer Retriever-Endpunkt** (klein, ~1 Tag): HTTP-Dienst auf 127.0.0.1, der
   `web_search.search_raw` + `article_fetcher.fetch_fulltext_result` (+ `web_cache`)
   kapselt und `[{url, raw_content}]` liefert; optional ein zweiter Modus, der unseren
   Korpus durchsucht. Ohne ihn ist gpt-researcher für uns nicht zulässig.
2. **Korpus-MCP-Server** (`catandary-corpus`, ~2 Tage): Werkzeuge `search_signals`
   (FTS + ANN wie `/api/search`), `field_probe`, `measure_sheet`, `tir_trajectory`,
   `get_signal`. Nutzbar von Claude Code, Claude Desktop und gpt-researcher
   (`RETRIEVER=mcp`). Heute kommt an die Daten nur, wer Python im Repo startet.
   Die Next-API-Routen taugen dafür nicht direkt: sie sind Owner-UI, teils mit
   Same-Origin-Pflicht und GPU-Handover.

**Extern, fehlt heute:**

3. **EUR-Lex strukturiert** — für Anhang A. EUR-Lex hat einen Webservice (Registrierung
   nötig) und den offenen Cellar-SPARQL-Endpunkt; ein MCP dafür ist mir nicht bekannt.
   Registrierung erst nach Owner-Freigabe (persönliche Daten).
4. **Tavily** ist der Default-Retriever, aber verzichtbar (Brave + SearXNG vorhanden).
   **Kein OpenAI-Key nötig**, wenn `anthropic` oder der lokale Server gesetzt wird.

**Skills (Claude Code, mit `skill-creator` anzulegen):**

5. **`field-setup`**: Kundenphrase → Begriffs-/CPC-Kandidaten → `--probe` →
   `fields/<kunde>.yaml`-Entwurf → Checkpoint-Liste für den Owner.
6. **`regulatory-annex`**: die Regeln aus dem Handdurchgang vom 19.09.
   (`docs/dossier_manual_run_2026-09-19.md`: Quellklasse vor Suche, Rechtstexte
   artikelweise, zwei unabhängige Seiten je Hersteller-Aussage) als feste Anleitung.
   Damit ginge Anhang A auch **ohne** gpt-researcher mit Claude Code + Brave/SearXNG.

## 5. Empfehlung

Kein Einbau in den Produktpfad. Wenn überhaupt, dann für den Rechtsrahmen-Anhang (A)
und die Feld-Einrichtung (B), in eigener venv, mit dem konformen Retriever (1) als
Pflicht-Vorbau. Vorher lohnt der Vergleich mit Skill 6: wenn Claude Code mit fester
Anleitung den Anhang in gleicher Qualität liefert, ist gpt-researcher eine
Abhängigkeit ohne Gegenwert. Der Korpus-MCP (2) lohnt sich unabhängig davon.

## 6. Nachtrag: konform per Fork? (Owner-Frage 04.10.)

**Ja, technisch geht es — aber ein Fork ist der teurere Weg.** Im Code gibt es genau
zwei Stellen, an denen gpt-researcher selbst Seiten holt:

- `skills/browser.py` `BrowserManager.browse_urls` → `actions/web_scraping.scrape_urls`
  → `scraper/scraper.py` `Scraper` (alle Scraper-Klassen: bs, browser, nodriver, PDF,
  arXiv, Firecrawl, Tavily-Extract). Aufgerufen von der normalen Recherche, Deep Research
  und den Nachlade-Pfaden (`researcher.py` Z. 252/965/1095).
- `document/online_document.py` `OnlineDocumentLoader` (nur bei `document_urls`).

Daneben schicken Retriever Suchanfragen an ihre APIs (Brave, SearXNG …) — das ist kein
Seitenabruf. Wichtig: auch ein Retriever mit `requires_scraping=False` löst Scraping aus,
sobald ein Treffer **ohne** `raw_content` kommt (`researcher.py` Z. 903–916).

**Weg 1 — Fork:** `Scraper.extract_data_from_url` und `OnlineDocumentLoader` auf
`article_fetcher.fetch_fulltext_result` umbiegen. Der Patch ist klein (~50 Zeilen), aber
das Projekt ändert sich wöchentlich (3.200 Commits, letzter 26.09.); jedes Update ist ein
Merge, und der Patch kann still wirkungslos werden, wenn oben ein neuer Abrufpfad dazukommt.

**Weg 2 — ohne Fork, empfohlen:** ein eigener Starter (`scripts/gptr_run.py`, eigene venv):
1. `RETRIEVER=custom` auf unseren Endpunkt (Abschnitt 4, Punkt 1), der nur Treffer **mit**
   konform geholtem `raw_content` zurückgibt — Treffer ohne Text werden verworfen, nicht
   durchgereicht.
2. Vor dem Import `BrowserManager.browse_urls` durch eine Funktion ersetzen, die über
   unseren Fetcher holt (robots, TDM nach Weiterleitung, `CatandaryTrendsBot/1.0`,
   Host-Drossel), und `OnlineDocumentLoader.load` hart scheitern lassen. Fail closed:
   jeder unbekannte Abrufweg endet im Fehler, nicht im Abruf.
3. Konfiguration festnageln: `CONTEXT_FILTER=keyword` (Jev schickt Text an TypeSafe),
   `IMAGE_GENERATION_ENABLED=False`, kein `MCP`, keine `source_urls`/`document_urls`,
   `USER_AGENT` auf unseren Bot.
4. Test, der eine Recherche gegen Attrappen fährt und jeden ausgehenden Request außer
   127.0.0.1 als Fehler wertet — läuft bei jedem Versions-Update von gpt-researcher.

Aufwand Weg 2: ~1,5 Tage inkl. Endpunkt. Er hält Updates aus, solange die zwei
Einstiegspunkte heißen, wie sie heißen — und wenn nicht, scheitert der Test, statt still
zu kratzen.

**Was weder Fork noch Starter lösen:** die Kennzeichnung (kein Modelltext im Blatt),
die Schreibqualität (Dossier-Befund) und die Speicherfrist der geholten Texte (der Starter
muss Arbeitsverzeichnis und Memory nach dem Lauf löschen oder der 1825-Tage-Regel
unterstellen).
