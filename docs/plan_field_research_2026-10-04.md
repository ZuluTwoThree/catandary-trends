# Plan: Korpus-MCP, Recherche-Starter und Entwürfe für Trajectory Sheet / Field Watch (2026-10-04)

> Owner-Auftrag 04.10.: „Baue den MCP-Server für unseren Korpus. Baue den Starter und den
> Rest als Ergänzung und Erweiterung für Trajectory Sheet und Field Watch. Erst einen Plan."
> Grundlage: `docs/gpt_researcher_eval_2026-10-04.md`.
>
> **Owner-Festlegungen 04.10.:**
> 1. Modelltext darf **als Entwurf** ins Blatt. Jedes Entwurfsblatt wird vor der Auslieferung
>    von einem Menschen umgeschrieben.
> 2. Für geholte Texte gilt die **1825-Tage-Regel** (wie `raw_content`).

## 0. Leitplanken

- **Nichts kommt in die gemeinsame venv.** gpt-researcher und das MCP-SDK liegen in einer
  eigenen venv `~/venvs/catandary-research` (uv, Python 3.12, Versionen gepinnt in
  `requirements-research.txt`). Sie liegt außerhalb der Worktrees, damit `dev` und `main`
  dieselbe benutzen, und berührt die Cron-venv nicht.
- **Die Recherche-venv importiert keinen Pipeline-Code.** Sie spricht nur HTTP mit einem
  lokalen Korpus-Dienst (Main-venv) und, bei lokalem Modell, mit dem llama-server.
- **Jeder Seitenabruf läuft über `article_fetcher.fetch_fulltext_result`**
  (`CatandaryTrendsBot/1.0`, robots, TDM nach Weiterleitung, Host-Drossel). gpt-researcher holt
  selbst nichts — fail closed, zusätzlich eine Sperre auf Socket-Ebene.
- **Kein Cron.** Alles läuft auf Knopfdruck. Die GPU-Läufe stehen im Kollisionswächter.
- **Entwürfe sind nie auslieferbar.** Ein Entwurfsblatt trägt ein Wasserzeichen und einen
  eigenen Dateinamen, und der Export der Kundenseite überspringt es. Ausgeliefert wird nur
  Text, den der Owner in die Kundendatei geschrieben hat.

## 1. Architektur

```
Claude Code / Desktop ──stdio──▶ MCP-Server (Recherche-venv, tools/research/mcp_server.py)
                                        │ HTTP + Token, 127.0.0.1
                                        ▼
scripts/field_research.py ──startet──▶ Korpus-Dienst (Main-venv, pipeline/corpus_service.py)
  (Main-venv: GPU-Wächter,              │  pipeline/corpus_api.py: Signale, Forschung, Patente,
   Handover, ops_events,                │  Feldmessung, Reifegrad, Nester, Websuche, konformer
   Entwürfe speichern)                  │  Abruf, Retriever-Format für gpt-researcher
        │ Subprozess                    ▼
        ▼                            PostgreSQL · :8091-Embedder · SearXNG/Brave · Fetcher
gptr-Worker (Recherche-venv, tools/research/gptr_run.py)
  RETRIEVER=custom → Korpus-Dienst; browse_urls → Korpus-Dienst /fetch;
  Socket-Sperre: nur 127.0.0.1 (lokal) bzw. zusätzlich api.anthropic.com
```

Der Korpus-Dienst läuft **nicht dauerhaft**. Der MCP-Server und `field_research.py` starten
ihn jeweils als Kindprozess auf einem freien Port mit Einmal-Token und beenden ihn mit
sich. Damit gibt es keine neue systemd-Unit, und jeder Worktree benutzt seinen eigenen Code.
Das Token schützt gegen Aufrufe aus dem Browser (dieselbe Lücke wie bei den
Foresight-GET-Routen, geschlossen am 04.10.).

## 2. Phasen

| # | Inhalt | Dateien | Prüfung |
|---|---|---|---|
| P0 | Recherche-venv | `requirements-research.txt`, `scripts/setup_research_venv.sh` | Import von `gpt_researcher` und `mcp` |
| P1 | Korpus-API + Dienst | `pipeline/corpus_api.py`, `pipeline/corpus_service.py` | pytest (reine Logik, Token, URL-Prüfung), Live-Abfragen gegen die DB |
| P2 | MCP-Server | `tools/research/mcp_server.py`, `.mcp.json` | MCP-Handshake + jedes Werkzeug einmal per SDK-Client |
| P3 | gptr-Worker | `tools/research/gptr_run.py` | Tests in der Recherche-venv: Socket-Sperre, umgeleiteter Abruf, Retriever ohne Text verworfen, Konfiguration festgenagelt |
| P4 | Orchestrator + Entwürfe | `scripts/field_research.py`, `pipeline/field_drafts.py` | pytest (Ablage, Quellenliste), ein echter Lauf |
| P5 | Blätter | `pipeline/field_watch.py` (Schema), `pipeline/field_watch_render.py`, `scripts/field_watch.py --draft` | pytest: Wasserzeichen, Export-Sperre, Fußtext |
| P6 | Skills | `.claude/skills/field-setup/`, `.claude/skills/regulatory-annex/` | Durchlauf an einem Beispiel |
| P7 | EUR-Lex | Cellar-SPARQL-Suche im Korpus-Dienst (ohne Registrierung) | Live-Abfrage; entfällt, wenn der Endpunkt nicht antwortet |
| P8 | Doku | CLAUDE.md, README, `docs/owner_manual.md`, Prompt-Katalog, Eval-Doku | — |

### P1 · Korpus-API (Werkzeuge)

| Werkzeug | Inhalt | Quelle |
|---|---|---|
| `search_signals` | Text, Bedeutung oder beides (RRF), Filter Ebene/Vertikale/Zeitraum, Status published+signal | `idx_trends_fts`, `embedding_1024` (HNSW), Embedder :8091 |
| `get_signal` | Titel, Zusammenfassung, Quelle, Link, Datum, Ebene, Taxonomie, Auszug | `trends`, `raw_entries`, `sources` |
| `search_research` | Werke ab 2010 mit Jahr, DOI, Zitationen | `research_corpus.tsv` |
| `search_patents` | Patente mit Datum, Titel, Anmelder | `patent_search.tsv`, `patent_assignee_raw` |
| `term_counts` | Treffer je Ebene und Jahr für eine Begriffsliste (Feld-Einrichtung) | wie `measure_sheet`, nur Zählung |
| `field_list` / `field_week` / `field_sheet` | Kundenfelder und ihre Messung | `pipeline/field_watch.py` |
| `field_probe` | Feldprobe; ohne CPC-Anker nur mit `allow_gpu=true` | `field_watch.probe` |
| `tir_block` | Reifegradblock zu CPC-Ankern | `field_watch.quant_block`, `cycle_time` |
| `emerging_nests` | Nester des jüngsten Laufs je Scope | `emerging_runs`, `emerging_nests` |
| `web_search` | Brave → SearXNG | `pipeline/web_search.py` |
| `fetch_url` | konformer Abruf, Rechtstexte artikelweise | `article_fetcher`, `legal_text` |
| `eurlex_search` | Rechtsakte per Stichwort (P7) | Cellar SPARQL |

Lesend, `statement_timeout` je Werkzeug, Ergebnisgrößen gedeckelt. Volltexte über MCP nur
gekürzt (Default 4.000 Zeichen).

### P3 · gptr-Worker

- **Retriever** `custom` → `/gptr/retrieve` des Dienstes. Der Dienst sucht (Korpus, Web oder
  beides, je nach Auftrag), holt jeden Treffer konform und gibt **nur** Treffer mit Text zurück.
- `BrowserManager.browse_urls` → `/gptr/fetch`; `OnlineDocumentLoader.load` → Fehler.
- **Socket-Sperre** vor dem Import: Verbindungen nur zu 127.0.0.1/::1, bei `--llm anthropic`
  zusätzlich `api.anthropic.com`. Alles andere wirft einen Fehler.
- **Festgenagelt:** `CONTEXT_FILTER=keyword`, keine Bilder, kein MCP-Retriever, keine
  `source_urls`/`document_urls`, `USER_AGENT` = unser Bot, `LANGUAGE=german` bzw. `english`.
- **Modell:** Default **lokal** (Gemma-4-26B über den Handover, `-c 16384`, ein Slot),
  Token-Grenzen passend gesetzt. `--llm anthropic` als Option. Begründung: CLAUDE.md
  „alle LLM-Verarbeitung lokal", die Kundenfelder verlassen den Rechner nicht.
- Ausgabe JSON: Bericht (Markdown), Quellen (URL, Titel, Abrufzeit), Kosten/Dauer, Modell.

### P4 · Orchestrator `scripts/field_research.py`

| Modus | Ergebnis | Wohin |
|---|---|---|
| `regulatory <kunde> <feld>` | Entwurf Rechtsrahmen, Suche auf EUR-Lex/Gesetze/Behörden begrenzt | Sheet Abschnitt 8 |
| `context <kunde> <feld>` | Entwurf Einordnung aus der Messung des Sheets (+ Korpus, Web) | Sheet Abschnitt 7 |
| `movers <kunde> [--week]` | je Feld mit deutlicher Bewegung ein Entwurf „was dahinter steckt" | Wochenblatt |
| `setup "<phrase>"` | Begriffs-Kandidaten, jeder deterministisch gezählt, YAML-Entwurf | nur Owner |
| `prospect "<firma>"` | interner Kurzbericht vor dem Erstgespräch | nur Owner |

GPU-Wächter (`gpu_guard.sh`-Muster um `field_research` erweitert), `model_on_llamacpp`,
Ruhezustand danach, `ops_events.record("field_research")`. Ablage:
`data/field_watch/<kunde>/drafts/<feld>/<modus>-<datum>.{md,json}` (bzw. `drafts/_owner/`).
Die geholten Texte stehen im JSON und fallen unter die 1825-Tage-Regel;
`field_drafts.purge()` räumt danach auf.

### P5 · Blätter

- Kundendatei je Feld neu: `regulatory:` (Text des Owners, Markdown) neben `reading:`.
- `scripts/field_watch.py <kunde> --sheet <feld> --draft` (bzw. Wochenblatt `--draft`): nimmt
  für leere Abschnitte den neuesten Entwurf. Badge „Entwurf · maschinell · vor Auslieferung
  umschreiben", Wasserzeichen auf jeder Seite, Datei `…-ENTWURF.pdf`, Quellenliste der
  Entwürfe als Anhang.
- Ohne `--draft` wie heute, nur Owner-Text. Fußtext wahr halten: liegt zu einem Abschnitt ein
  Entwurf vor, heißt es „vom Analysten geschrieben und verantwortet, auf Grundlage eines
  maschinellen Rechercheentwurfs".
- `--export` überspringt `*-ENTWURF.*` hart (Test).

### P6 · Skills

- **field-setup:** Phrase → `setup`-Modus oder MCP `term_counts` → Kandidaten mit Zählung →
  YAML-Entwurf → Checkliste für den Owner (Freigabe durch den Kunden).
- **regulatory-annex:** die Regeln aus `docs/dossier_manual_run_2026-09-19.md` (Quellklasse vor
  Suche, Rechtstexte artikelweise, zwei unabhängige Seiten je Herstelleraussage), über die
  MCP-Werkzeuge `eurlex_search`, `fetch_url`, `web_search`. Auch ohne gpt-researcher nutzbar.

## 3. Was scharf geht und was nicht

- Kein Cron, keine neue Unit, keine Migration (Entwürfe sind Dateien).
- `pipeline/field_watch*.py` und `scripts/field_watch.py` laufen samstags per Cron aus `main`.
  Die Änderungen sind additiv; ohne `--draft` bleibt die Ausgabe gleich (Test). Sie werden
  erst mit einem Merge scharf, der dem Owner vorher vorgelegt wird.
- `gpu_guard.sh` bekommt ein zusätzliches Muster — ebenfalls erst mit dem Merge.

## 4. Offene Owner-Punkte (Default gesetzt, umstellbar)

- **Modell der Entwürfe:** lokal (Default) oder Claude über die API (`--llm anthropic`).
- **Fußtext** bei umgeschriebenen Abschnitten (Formulierung oben).
