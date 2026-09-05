# Owner-Handbuch — Bedienung der Catandary-Trends-App

Stand 2026-09-05, verifiziert gegen Code, `crontab -l` und die laufenden
Instanzen (`:3001`, `:3004`, `:3999`, `:8090`, `:8098`). Kurzfassung und
Setup: [`README.md`](../README.md). Architektur-Vertrag: [`CLAUDE.md`](../CLAUDE.md).

**Lesehinweise.** „Owner-Instanz" = `http://localhost:3001` (main) bzw.
`:3004` (dev). Alle `python`-Aufrufe meinen `.venv/bin/python` im Repo-Root;
Cron und Wächter laufen aus dem **main-Worktree** `~/projects/catandary-trends`
(dort liegen auch `data/*_last.json` und die Logs zeigen dorthin). GPU-Regel für
alles, was ein Modell braucht: **nicht parallel** zum 04:00-Full-Cycle, zum
Samstags-Ingester, zu einem laufenden Dossier-Worker oder Research-Pulse-Lauf —
jedes Werkzeug übernimmt `:8090` exklusiv und stellt danach den Ruhezustand
wieder her.

## Inhalt

1. [Morgenroutine](#1-morgenroutine--was-nachts-passiert-und-was-morgens-zu-tun-ist)
2. [Trend-Feed, Artikelseite, Suche und Filter](#2-trend-feed-artikelseite-suche-und-filter)
3. [Review-Seite](#3-review-seite-trendsreview)
4. [Mega Signal Themes und Methodik-Seite](#4-mega-signal-themes-und-methodik-seite)
5. [Foresight-Cockpit](#5-foresight-cockpit-trendsforesight)
6. [Dossier-Desk](#6-dossier-desk-trendsdossiers)
7. [Newsletter](#7-newsletter)
8. [Analysen](#8-analysen-analysis)
9. [Statischer Export](#9-statischer-export--die-öffentliche-website)
10. [Quellen verwalten](#10-quellen-verwalten)
11. [Betrieb](#11-betrieb-cron-wächter-backup-gpu-logs)
12. [Sicherheit und Recht](#12-sicherheit-und-recht-kurz)

---

## 1. Morgenroutine — was nachts passiert und was morgens zu tun ist

**Nachts (Mo–Fr, automatisch).** 02:45 Postgres-Backup · 03:30 Volltext-Retention
(`raw_content` älter 14 Tage → NULL) · **04:00 Full Cycle** (`scripts/full_cycle_cron.sh`
→ `scheduled_cycle.sh`): VRAM freiräumen, RSS-Poll, Stages 1–9, Draft-Richter
(Stage 10), Ruhezustand wiederherstellen, Morgen-Mail (`scripts/review_notify.py`)
verschicken · 07:45 Wächter (`scripts/cycle_watchdog.py`). Der Cycle endet
typischerweise 05:55–06:12.

**Morgens (Owner).**

1. **Postfach.** Zwei Absender, beide nur bei Bedarf:
   - *Wächter-Mail* — kommt **nur**, wenn etwas fehlt: keine `end`-Zeile mit
     Exit-Code im Cycle-Log, kein heutiges Backup-Artefakt (`catandary-pg-<Datum>.dumpdir`
     mit `toc.dat`, ≥ 1 GB) oder — sobald `webspace.env` existiert — kein
     fehlerfreies `data/publish_last.json` von heute. **Schweigen = gesund.**
   - *Review-Mail* („grounding-hold review queue") — kommt nur, wenn die Nacht
     Artikel zurückgehalten hat; enthält Anzahl heute/gesamt, ältestes Datum,
     Beispieltitel, eine Zeile mit den Draft-Richter-Zahlen
     (`data/draft_judge_last.json`), — solange die Datei < 36 h alt ist — eine
     Zeile zum Newsletter-Deep-Dive (`data/newsletter_deep_dive_last.json`) und
     — < 60 h alt — je eine Zeile zu den GPU-Crons (`data/weekly_ingesters_last.json`,
     `data/monthly_startup_sources_last.json`: `ok` / `blocked` / `failed`, Zahl der
     gelaufenen und übersprungenen GPU-Schritte, Blockierer; §11.8). Ein
     `blocked`/`failed` erzwingt die Mail auch bei leerer Queue.
     Link: `REVIEW_URL` (Default `http://localhost:3001/trends/review`).
2. **Review-Queue abarbeiten** (Abschnitt 3) — jeder gehaltene Artikel braucht
   eine Entscheidung, sonst wächst der Backlog.
3. **Feed sichten:** `http://localhost:3001/trends` zeigt, was die Nacht
   publiziert hat (Sortierung Datum, neueste zuerst).
4. **Bei Verdacht ins Log:** `~/logs/catandary-full-cycle-<YYYYMMDD-HHMM>.log`
   (Wrapper) und `~/logs/catandary-scheduled-<…>.log` (Stages). Die letzte Zeile
   des Wrappers ist `… end … rc=<Exit-Code>`.

Wochenende: Samstag 06:00 laufen die Nicht-RSS-Ingester (Preprints, Funding,
Startup-Signale, OpenAlex-Fresh, Patent-Signale, Research-Index-Rebuild),
Sonntag 06:00 der Discovery-Loop. Kein Cycle, keine Review-Mail, kein Wächter.

---

## 2. Trend-Feed, Artikelseite, Suche und Filter

**Wozu.** Der Feed ist das redaktionelle Produkt: die publizierten Artikel
(`trends.status = 'published'`), je ~100 Wörter Englisch, mit Quellennennung
und Backlink. Lokal sieht der Owner den gesamten Korpus (Zehntausende Artikel),
öffentlich nur die letzten 30 Tage.

**Wo.** `/trends` (Feed), `/trends/<slug>` (Artikel), `/trends?q=<Suche>`,
`/trends?v=<VERTIKALE>`. `/trends/vertical/<v>` leitet auf `/trends?v=` um.

**Bedienung.**
- Filter-Bar über dem Grid: Suchfeld (`?q=`; Postgres-Volltextsuche mit
  `websearch_to_tsquery`-Semantik — Phrasen in Anführungszeichen, `OR`,
  `-ausschluss`), Vertikale (Mehrfachauswahl), PESTEL, Mega-Theme-Chips,
  Zeitraum, Score-Regler, Signaltyp, Sortierung, Quellen-Ausschluss,
  Listen-/Karten-Ansicht; aktive Filter erscheinen als Chips und lassen sich
  einzeln entfernen.
- Die Hybrid-Suche (FTS + pgvector-ANN, RRF-Fusion) steht zusätzlich als API
  bereit: `/api/search?q=…&vertical=FOOD&limit=20`.
- Artikelseite: Titel, Body, Vertikal- und PESTEL-Badges, Mega-Theme, Score,
  Quelle mit Backlink, verwandte Artikel. Ist die Quell-URL nachweislich tot
  (`dead_links`, monatlicher Link-Check), zeigt die Seite einen Hinweis und den
  Archiv-Link statt des toten Backlinks.
- Seitenaufrufe werden lokal in `trend_metrics` gezählt (`/api/track`; im Export
  abgeschaltet).

**Grenzen.** Artikel sind bewusst kurz (~100 Wörter; der Prompt fragt 150–250,
das erzeugt ~100). Es gibt keinen deutschen Content (`*_de`-Spalten bleiben
NULL). Signale ohne Artikel (`status='signal'`) erscheinen nicht im Feed, nur in
den Foresight-Werkzeugen.

---

## 3. Review-Seite (`/trends/review`)

**Wozu.** Das nächtliche Auto-Publish veröffentlicht Drafts mit Confidence
≥ 0,85 — **außer** das Grounding-Gate findet im Body eine Zahl, ein Jahr, einen
Prozent- oder Geldbetrag, der in der Quelle nicht vorkommt (Modell hat etwas
erfunden), oder der Text bricht mitten im Satz ab. Solche Artikel bleiben
`draft` und landen hier. Ohne Entscheidung bleiben sie liegen.

**Wo.** `http://localhost:3001/trends/review` — nicht im Menü verlinkt,
`PUBLIC_MODE`/Export: 404. Kein Login (Owner-Instanz).

**Bedienung.**
- Zwei Ansichten: **Today** (Drafts der letzten 30 h) und **Backlog** (alle,
  max. 100). Kopfzeile: Anzahl heute, gesamt, ältestes Datum.
- Jede Karte zeigt links den generierten Artikel, rechts „What the source
  actually said" (Feed-Teaser bzw. Volltext). Beanstandete Token sind im Body
  markiert und in der Warnzeile aufgeführt („Not supported by the source: …");
  abgeschnittene Bodies tragen „cut off mid-sentence".
- **Publish** — Artikel geht live; `auto_published=false`, `reviewed_at` gesetzt
  („human-reviewed"). **Reject** — Status `rejected`, `reviewed_at` gesetzt.
  **Write again** — nur bei abgeschnittenem Text: der Rohdaten-Eintrag wird für
  den nächsten Cycle neu eingereiht, der aktuelle Draft wird verworfen (die
  Quelle geht nicht verloren).
- Terminal-Alternative: `python scripts/review_cli.py list | show <id> | publish <id> |
  reject <id> | review | stats`.

**Was nachts sonst noch entscheidet — der Draft-Richter (Stage 10).** Drafts
*unter* der Schwelle bewertet ein lokales Qwen3.8-27B redaktionell (Kriterien
der Haiku-Volldurchsicht vom 21.08.: Confidence trennt kaum, ~72 % der
Sub-Schwellen-Drafts sind publizierbar). Er **gibt frei** (`auto_published=true`,
dieselben Gates wie Auto-Publish: Grounding, Truncation, pgvector-Dedup gegen
Published) oder **hält** — er verwirft nie. Jeder beurteilte Draft bekommt
`judged_at` und wird nicht erneut beurteilt. Zahlen in
`data/draft_judge_last.json` → Morgen-Mail. Abschalten: `DRAFT_JUDGE=0` in der
Cron-Umgebung. Der Richter braucht die GPU exklusiv (27B lässt ~1,1 GB Reserve);
Fremdbelegung → SKIP mit Diagnose statt Timeout.

**Grenzen.** Die Review-Seite zeigt nur Grounding-/Truncation-Holds
(Confidence ≥ 0,85). Vom Richter *gehaltene* Sub-Schwellen-Drafts erscheinen
hier nicht; sie bleiben `draft` und sind über die CLI (`list draft`) erreichbar.
Das Gate arbeitet fail-open: ohne gespeicherten Quelltext wird nicht geprüft.

---

## 4. Mega Signal Themes und Methodik-Seite

**Wozu.** `/trends/mega` ordnet jedes Signal einem der **28 kuratierten
Themes** (`mega_trends.yaml`) zu und zeigt, welche davon *gemessen* Megatrends
sind — statt behauptet.

**Wo.** `/trends/mega`, `/trends/mega/<key>` (Theme-Seite mit Artikeln,
Deep-Links in Research Explorer und Research Pulse — letztere nur lokal).

**Badge-Regeln** (Legende auf der Seite; Messung `scripts/measure_mega_axes.py`):
- **Megatrend** — spannt mehrere Industrien, hat Evidenz über die ganze Kette
  Forschung → Patente → Funding → Markt, und die Forschung war zuerst da.
  Derzeit tragen 12 Keys das Badge.
- **Domain** — ein tiefes Feld, kein Querschnitt: ≥ ⅔ der Signale in einer
  Industrie.
- **Faded Hype** — Abdeckung hatte ihren Gipfel vor Jahren und ist seither
  eingebrochen (Peak-Jahr auf dem Badge).
- **Momentum ↗ → ↘** — Anteil an neuen Signalen der letzten 90 Tage gegen die 90
  davor. Zu wenig Daten → **kein** Badge (keine Vermutung).
- Messzeile je Karte: `reach` (Streuung über die acht Industrien, 0–1), `tiers`
  (belegte Ebenen), `lead` (Monate, die Forschung vor der Marktabdeckung lag).

**Neu messen.** `python scripts/measure_mega_axes.py` (read-only, schreibt
`docs/mega_axes_<Datum>.md`); `--write-yaml` ist die **einzige** Schreibquelle
für die Badge-Felder in `mega_trends.yaml`. Vetos stehen in der YAML. Nach
Änderungen an `mega_trends.yaml`: `npm run gen:mega-trends` läuft automatisch
vor `dev`/`build`.

**Methodik-Seite** `/trends/methodology` („Method & Trust"): Quellenstrategie,
Pipeline, Grenzen, Live-Korpuszahlen (`getMethodologyStats`, 1 h gecacht). Sie
ist Teil des Exports und die Adresse, die der Crawler-UA nennt. Der geplante
Abschnitt „Source Use & Removal Requests" liegt als Entwurf in
`docs/compliance/takedown_notice.md` und ist **noch nicht** eingebaut.

---

## 5. Foresight-Cockpit (`/trends/foresight`)

Hub mit Kennzahlen des Korpus und Einstiegen in die Werkzeuge; Menü:
*Cockpit · Clusters · Technology · Lead Time · Evolution · Dossier · Scouting
Desk*; Research Explorer, Research Pulse, Patent Explorer und Startup Explorer
sind vom Cockpit aus verlinkt. Alles owner-only (`PUBLIC_MODE`/Export: 404).

### 5.1 Technologie-Suche (`/trends/foresight/technology`)

**Wozu.** Freitext → Patentfeld (feine CPC-Codes) → Verbesserungsrate K(t) aus
dem Zitationsgraph + Innovationskette. Beispiel-Chips unter dem Feld.

**Bedienung.** Phrase eingeben („solid-state battery electrolyte"), Enter.
Fortschritt in drei Schritten (Embedding → Feld → Rechnung; große Felder bis
~2 min). Das **Quality-Gate** (`pipeline/query_gate.py`, seit 04.09.) läuft
GPU-frei *vor* jeder Zahl und liefert eines von drei Urteilen:

| Urteil | Was der Nutzer sieht | Regel |
|---|---|---|
| `ok` | die Analyse (Trajektorie, Lead-Time, Leitpatente) | 20 nächste CPC-Klassen alle ≤ 0,36 (d20) **und** ≥ 1 Patenttitel enthält alle Terme |
| `ambiguous` | „Your phrase points to more than one patent field — which one do you mean?" + klickbare Feldwahl | Wort-Feld der Titeltreffer (≥ 20 Treffer, ≥ 40 % eine Subklasse) ≠ Embedding-Feld; oder breiter echter Begriff („blockchain": viele Titeltreffer, d20 knapp drüber) |
| `off_topic` | „We don't see a technology signature for …" + 2–3 nächste **echte** Felder als Vorschlags-Buttons, **keine Zahl** | d20 > 0,36 oder 0 Titeltreffer oder d1 > 0,55 |

Ein Klick in der Feldwahl ruft `?q=…&codes=…` — dieselbe Phrase, exakt diese
Klassen (Vektor aus dem Cache, kein zweiter Handover). Terminal:
`python scripts/tech_analyze.py --query "…" [--codes H01M10/052 …] [--json]`.

**Was das Ergebnis bedeutet.** K(t) = jahresweise Verbesserungsrate der
Technologie (Methode: SPNP-Zentralität + Zitationsmetriken, Singh/Triulzi/Magee
2021; gegen den MIT-1757er-Datensatz validiert). Ehrlichkeitsgrenzen sind
eingebaut: Mindestzahl Patente je Fenster, die letzten ~7 Jahre sind wegen
Zitationsreife ausgegraut, absolute K-Werte nur im kalibrierten Bereich (bis
~2019), Patent ≠ Produkt. Kein „erkennt früh"-Anspruch — die Zahl beschreibt
relative Entwicklung.

**Grenzen.** Schwellen gelten für das aktuelle Embedding-Modell; nach einem
Wechsel `scripts/measure_query_gate.py` laufen lassen und `D20_MAX` gegen die
neue Lücke setzen (Test `test_d20_threshold_sits_in_the_measured_gap`). Breite
Ein-Wort-Begriffe landen in der Feldwahl, nicht in der Analyse.

### 5.2 Lead Time (`/trends/foresight/lead-time?cpc=<Subklasse>`)

Die vier Ebenen (Forschung, Patente, Funding, Markt) einer Technologie als
Share-of-Voice-Kurven über die Zeit, je Ebene auf ihren eigenen Gipfel
normiert. Öffnet ohne Eingabe auf dem klarsten belegten Fall; die Liste rechts
wechselt die Technologie. Die Kopfzahl „N years ahead" erscheint **nur**, wenn
beide Ebenen eine belastbare Emergenz zeigen (`reliable`); sonst nur Kurven.
Daten: `cpc_tier_series`/`cpc_leadtime_summary`, jeden Dienstag 08:00 neu
gerechnet (`scripts/weekly_patent_analytics.sh`).

### 5.3 Cluster (`/trends/foresight/clusters?vertical=<V>`)

„What's moving now": datengetriebene Cluster aus dem vollen Signalraum,
sortiert nach steigendem Anteil, mit Momentum-Badge, Quellenbestätigung und
Evidenzlinks; Datum des Rechenstands im Kopf. Die Seite liest **persistierte
Snapshots** (`foresight_runs`/`foresight_clusters`). Neu rechnen — bewusst nur
auf Knopfdruck im Terminal, kein Cron:
`python -m pipeline.foresight_snapshot --all-verticals [--dim1024]`.
Validierung: `scripts/foresight_validation.py` (Known-Trend-Recovery 23/24).

### 5.4 Evolution (`/trends/foresight/evolution?vertical=<V>`)

Cluster-Abstammung über Zeitfenster: Fäden mit *New* / *Fading*, rising /
steady / cooling und „shifting in meaning" bei starker Drift. Liest die
persistierte Lineage; rechnen mit
`python -m pipeline.foresight_snapshot --lineage [--since … --until … --step … --span …]`.

### 5.5 Foresight-Dossier zum Drucken (`/trends/foresight/dossier?vertical=<V>`)

Ein-Seiten-Zusammenfassung „rising / holding / cooling" aus dem aktuellen
Cluster-Snapshot, druckoptimiert (kein Chrome im Ausdruck). Nicht zu
verwechseln mit dem Dossier-Desk (Abschnitt 6).

### 5.6 Research Explorer (`/trends/foresight/research`)

**Wozu.** Suche über den 45-Mio.-Korpus (`research_corpus`, OpenAlex-Snapshot,
monatlich am 5.) und die kuratierte **Signal-Schicht** (`research_signals`,
wöchentlich Samstag neu gebaut) mit Topic-Trends, Emerging Topics und
Patent-Brücke (Topic → CPC).

**Facetten (URL-Parameter).** `?q=` Text · `?layer=signals` (Suche in der
Signal-Schicht statt im 45M-Korpus) · `?src=arxiv,biorxiv,medrxiv,openalex,journals`
· `?range=7d|30d|90d|1y` · `?sort=relevance|date` (Relevanz nur mit `q`) ·
`?concept=<OpenAlex-Konzept>` (Konzept-Badges an den Treffern sind klickbar) ·
`?theme=<Mega-Key>` (Deep-Link von den Theme-Seiten). Paper-Detail
`/research/paper/<id>`, Export der Trefferliste `/research/export`, Typeahead
`/research/suggest`. OA-Badge nur für Preprint-Server (per Definition offen).

**Live-Suche.** Mit `OPENALEX_API_KEY` in `frontend/.env.local` holt die Seite
bis zu 25 Live-Treffer pro Tag direkt von OpenAlex (serverseitig, Key nie im
Client).

### 5.7 Research Pulse (`/trends/foresight/research/pulse`, `/pulse/<theme>`)

**Wozu.** Wochen-Synthese je Mega-Theme aus den frischen Forschungssignalen:
Volumen der ISO-Woche vs. Median der vier Vorwochen, KMeans-Cluster (k ≤ 5,
fester Seed) mit c-TF-IDF-Labels, Wachstum/„emerging" je Cluster, die vier
zentroid-nächsten Papers, und ein 80–190-Wörter-Absatz von Gemma-4-26B
(T = 0,2, Seed 73, nur Zahlen aus dem Messblock, keine Prognosen).

**Bedienung.** Übersicht mit Wochen-Wechsler; Theme-Seite mit Herkunftskopf,
Messblock, Text und Clustern. **„Recompute"** (Server Action, nur Owner-Modus)
startet `scripts/research_pulse.py --themes <key> --week …` detached — Cluster
in Sekunden, Absatz ~1 min (Modell-Load); Lock `data/research_pulse.lock`, Log
`data/research_pulse/<stamp>.log`, danach Ruhezustand. Terminal:
`python scripts/research_pulse.py [--week 2026-W35] [--themes a,b] [--no-llm] [--limit N] [-v]`
(Default: letzte abgeschlossene Woche, alle 28 Themes; ohne LLM ~14 s).

**Cron-Vorschlag, nicht installiert:** `0 12 * * 6 scripts/weekly_research_pulse.sh`
(auskommentiert in `deploy/crontab.txt`; idempotent, Kollisionswächter). Owner
entscheidet Cron vs. Knopf.

**Grenzen.** Kein Text unter 5 Papers. 6 der 28 Themes sind in der Forschung
praktisch leer. Ein Journal-Batch erscheint als „emerging ×22" — Datenrealität,
im Fußtext erklärt. Jeder Lauf ist eine neue Zeile (`research_pulse`
versioniert); die Seite zeigt je Theme/Woche die jüngste.

### 5.8 Patent Explorer (`/trends/foresight/patents`)

**Wozu.** 19 Mio.+ Patente (EPO-DOCDB-Back-File mit Abstract, CPC, Familien,
Anmeldern), plus Kennzahlen je Technologie-Achse.

**Suche.** Ein Feld, drei Ausbaustufen (#78): der **Smart-Router** erkennt
Publikationsnummern (`US11734097B2`), CPC-Codes (`H01M`) und Jahre im Freitext
und macht Filter daraus; **jede** der ~650 CPC-Subklassen ist browsebar (das
Dropdown zeigt 26 kuratierte Achsen mit Technologie-Panel); Text läuft über den
**materialisierten Volltextindex** `patent_search` (`"exact phrase"`, `OR`,
`-exclude`; Phrasen-Suche ~0,15 s). Anmelder: `company:samsung` oder
`company:"Toyota Motor"`; trifft ein Suchtext einen Anmeldernamen, bietet die
Seite „Looking for the company?" an. Filter `?cpc=`, `?country=` (Ämter mit
≥ 200k Patenten), `?page=`.

**Grenzen.** Der Graph wird jeden Dienstag 05:00 nachgezogen (`weekly_patents.sh`);
Zitationsmetriken der letzten ~7 Jahre sind unreif. Radare und TIR-Forschungsläufe
laufen bewusst nicht per Cron.

### 5.9 Startup Explorer (`/trends/foresight/ventures`, `/company/<id>`)

Firmen-Korpus (~145k Firmen, ~420k datierte Ereignisse aus Primärquellen:
Funding-Regex aus Presse, SEC Form D, SBIR/CORDIS-Grants, HN-Launches,
ClinicalTrials, FDA 510(k), GLEIF/Companies House). Filter: Text, Vertikale,
Land, Ereignistyp. Firmenseite = Evidenz-Timeline mit Quellen und Brücken zu
Artikeln/Patenten; Attributionsblock (OGL, CC BY, Public Domain) am Fuß. Daten:
Signale wöchentlich (Sa), Register monatlich (6. 12:00,
`monthly_startup_sources.sh`). Firmenstamm-Rebuild/Wikidata/Brücken nur
on-demand (Rebuild würde Enrichment verwerfen).

---

## 6. Dossier-Desk (`/trends/dossiers`)

**Wozu.** Scouting-Dossiers zu Technologiefeldern bestellen: der agentische
Rechercheur (`scripts/corpus_research.py`) durchsucht die eigenen Korpora
(Artikel, Signale, Paper, Patente), optional das Web, misst vorher die
Innovationskette (TIR-Trajektorie, Lead-Time, Leitpatente) und liefert einen
zitierten Bericht mit maschineller Endkontrolle. Proprietäre Owner-Dokumente:
streng lokal (Qwen3.8-27B), kein Kundenpfad, kein Cron.

**Wo.** `/trends/dossiers` (Desk), `/trends/dossiers/<slug>?v=<n>` (Leseansicht).
Lokal standardmäßig an; `DOSSIERS_ENABLED=0` = Not-Aus; im Export nie gebaut.

**Auftrag anlegen (Desk).** Formular „New order slip":
- **Technology field** (Pflicht, ≤ 500 Zeichen) — die Phrase, die auch gemessen wird;
- **Series slug** (optional) — gleicher Slug = nächste Version derselben Serie;
- **Custom question** (optional) — ersetzt die Foresight-Standardfrage; ändert
  die Recherche, nicht die Messung;
- Checkbox *measure the innovation chain first* (Quant-Vorstufe: CPC → TIR →
  Lead-Time → Hub-Patente als zitierbare Quelle „Q1");
- Checkbox *start the worker right away*.
„Place order" legt den Auftragszettel (`dossier_orders`, Status `queued`) an.

**Firmen-Dossier, Fokus, Sprache — nur per CLI.** Der Desk kennt nur den
Themen-Modus. Für ein Firmen-Dossier (web-first die eigene Website der Firma,
dann das Trendumfeld aus den Korpora), einen Zusatzschwerpunkt oder deutschen
Bericht:

```bash
python scripts/corpus_research.py --company "Askea Feinmechanik, Amtzell" --lang de \
    --focus "Portfolio Medizintechnik" --slug askea --quant --web-steps 6
python scripts/corpus_research.py --foresight "solid-state batteries" --slug ssb --quant
# --lang de|en (Default: de bei --company, sonst en) · --web-steps 0 = offline
```

Mit `--slug` landet der Lauf als nächste Version in `dossiers` und erscheint im
Desk als Serie.

**Worker starten.** Knöpfe im Desk: **Run now** (ein Auftrag), **Run N queued**
(alle offenen), **Run again** (nach `failed`), **Cancel**, in der Leseansicht
**Recompute · v(n+1)**. Der Desk spawnt `python -m scripts.dossier_worker
[--order N]` detached (Lock `data/dossier_worker.lock`, Log
`data/dossier_worker/<stamp>.log`); „Worker started — 10–20 minutes; reload to
follow." Ein Worker zugleich. Terminal-Äquivalente:

```bash
python -m scripts.dossier_worker --list
python -m scripts.dossier_worker --order-new "solid-state batteries" --run
python -m scripts.dossier_worker                 # alle queued abarbeiten
python -m scripts.dossier_worker --order 7       # nur diesen (failed wird neu eingereiht)
python -m scripts.dossier_worker --assume-model-up   # :8090 serviert schon das 27B
python -m scripts.dossier_worker --skip-quant
```

Ablauf je Lauf: Phase 1 Embedding-Handover + Quant-Messblock → Phase 2
27B-Handover (VRAM-Vorab-Check < 1,1 GB Fremdbelegung, Identitäts-Check
`/v1/models`) → Plan → Korpus-Suche → Audit → Paper-/Patent-Sweep → Web →
Bericht → **Zitat-Kanonisierung** (jede URL muss im gesammelten Katalog
stehen, sonst gestrichen) → Endkontrolle → Status **`review`**. Danach
Ruhezustand (Symlink 8B-208k, llama-server wieder aktiv, falls er lief).

**Leseansicht.** *Herkunftskopf* (Frage, Belegmix Artikel/Signale/Paper/
Patente/Web, zitiert/gestrichen, Messblock-Kurzfassung, Modell, Retrieval,
Dauer, Sprache) → *Endkontroll-Panel* (unbelegte Zahlen, gestrichene Zitate,
Zitatquote, offene Fragen; „end-control clean" oder N findings) → *Bericht*
(Markdown inkl. Tabellen) → *Coverage-Anhang* (Ledger je Lücke: Paper/Patente/
Web-Queries/-Treffer/-Fetches) → *Versionswechsler*. **Sign off (this version)**
setzt `done`; das passiert nie automatisch.

**Abnahmekriterien** (Abnahmelauf 03.09., „perovskite tandem photovoltaics"):
≥ 95 % der Zitate im fertigen Dossier belegt (8/8), 0 erfundene URLs (alle per
HEAD/GET erreichbar), 0 unbelegte Zahlen, wörtliche Zitate im Material, Ledger
vollständig, Dauer 10–15 min (477 s Recherche, 568 s Wandzeit).

**Grenzen.** Vor der Kanonisierung erfindet das Modell plausible Pfade bekannter
Domains — **Streichungsquote 46,7 %** der Zitat-Instanzen im Abnahmelauf (bei
`--lang de` ähnlich); der fertige Text ist sauber, verliert aber Belege. Lücken,
die erst das Re-Audit aufwirft, werden nicht mehr gesweept und fehlen im
Ledger. Kein Versions-Diff (nur Wechsler). Die Quant-Vorstufe misst das
**Thema**, nicht die eigene Frage. Web-Treffer sind ungeranked, der
Patent-Sweep titelbasiert. `--retrieval vector` ist ungetestet (Default FTS).
Nicht parallel zum 04:00-Cycle starten.

Doku: `docs/agentic_dossiers.md`, Skizze `docs/corpus_research_sketch.md`.

---

## 7. Newsletter

### 7.1 Website-Edition (automatisch, Mo 09:00)

`scripts/weekly_newsletter_publish.sh` (Cron `0 9 * * 1`) generiert die
**Vorwoche** (ISO-Woche von „heute − 7 Tage") nach `newsletter_editions`:
Kollisionswächter (wartet auf einen laufenden Cycle) → Idempotenz (Edition
vorhanden = no-op) → Gemma-Swap → `pipeline.newsletter_generator --year --week`.
Kein Versand. Log `~/logs/catandary-newsletter-publish-<Datum>.log`, end-Zeile
`(gen=<rc> dd=<rc>)`. Manuell nachgenerieren:
`python -m pipeline.newsletter_generator --year 2026 --week 35 [--preview] [--skip-llm]`.

### 7.2 Ansehen — lokal und im Export

Lokal: `/trends/newsletter` ist eine Client-Seite mit Wochen-Wechsler
(`?year=&week=`, Daten aus `/api/newsletter`). Im Export: `/trends/newsletter`
(Signup + neueste Edition + Archivliste), `/trends/newsletter/<jahr>-w<kw>`
(die letzten 12 Editionen, `PUBLIC_NEWSLETTER_EDITIONS`; Artikel-Links außerhalb
des 30-Tage-Fensters zeigen auf die Primärquelle), `/trends/newsletter/unsubscribed`.
Editions-URLs sind lokal 404 (dort gilt die Client-Seite).

### 7.3 Deep Dive of the Week — Dry-Run (#96 Phase 1, nicht scharf)

**Wozu.** Rechercheur-gestützte Sektion zum stärksten Wochenthema. Phase 1 baut
die ganze Kette, zeigt das Ergebnis aber nur dem Owner.

**Einschalten.** In `crontab -e` die Montagszeile ergänzen:
`0 9 * * 1  NEWSLETTER_DEEP_DIVE=dry-run /home/dirk/projects/catandary-trends/scripts/weekly_newsletter_publish.sh`
(Default `off` — heute nicht gesetzt). Läuft dann *nach* der Edition; ~4–5 min.

**Was passiert.** Themenwahl (SQL, deterministisch: Anteils-Delta je Mega-Theme
gegen 4 Vorwochen, ≥ 15 Signale, Varianz-Regel über die letzten 4 Editionen)
→ Dossier-Auftrag `newsletter-deepdive-<J>-w<KW>` → Worker (27B, Zeitbudget
20 min, ohne Web-Stufe) → **Gate** → Gemma-Kondensat 300–500 Wörter (nur
belegte Kernaussagen + Zitatkatalog als Kontext) → deterministische Nachprüfung
→ speichern.

**Was das Gate prüft.** `supported_claims` ≥ 8 belegte Kernaussagen ·
`contradictions` < 3 · `citations_canonical` 100 % · `dossier_grounded` 0
unbelegte Zahlen · `condensate`: Wortzahl, alle Links im Katalog, alle Zahlen im
Dossier, ≥ 4 Belege, reine Prosa, keine Meta-Rede über die Beleglage.
`gate_passed` = alle fünf.

**Wo der Owner es sieht.** In der Edition auf der Owner-Instanz als Block
„Deep-Dive Dry-Run — not public" (Thema, Gate-Chips ok/fail, Audit-Zahlen,
Gründe, Kondensat-Vorschau, Link „Open the dossier in the desk →"); das Dossier
selbst im Desk (Status `review`); ein Draft unter
`frontend/content/analyses/newsletter-deepdive-<J>-w<KW>.md` (`draft: true`,
untracked); eine Zeile in der Dienstag-Morgen-Mail. Öffentlich gerendert wird
nur `gate_passed && !dry_run` — im Dry-Run also nie (Export-Nachweis 04.09.:
keine Spur in `out/`).

**Terminal.**
```bash
python -m scripts.newsletter_deep_dive --year 2026 --week 35 --theme-only   # Ranking, kein Modell
python -m scripts.newsletter_deep_dive --year 2026 --week 35                # Dry-Run (Edition muss existieren)
python -m scripts.newsletter_deep_dive --year 2026 --week 35 --theme quantum_information_science
python -m scripts.newsletter_deep_dive --year 2026 --week 35 --from-dossier newsletter-deepdive-2026-w35@3
#   ^ nur Gate + Kondensat auf einem bestehenden Dossier, kein 27B-Lauf
```

**Stand.** Drei Dry-Runs W35 (Thema `digital_trust_and_data_sovereignty`): Gate
verfehlt nur an `supported_claims` (6–7 < 8) — ohne Web-Stufe trägt der Korpus
zu einem News-Thema ~6 belegte Aussagen; Kondensat jeweils sauber. Phase 2
(Owner-Entscheid nach 2–3 Wochen): `--web-steps 6`, Schwellen kalibrieren,
`--apply`, E-Mail-Template. Doku: `docs/newsletter_deep_dive.md`.

### 7.4 Versand-Kette (#16, gegated — läuft nicht)

`scripts/newsletter_tonight.sh` (Generierung + Versand via Resend) ist **kein
Cron** und darf es erst werden, wenn: (1) das PHP-Abmeldepaket auf dem Webspace
liegt (`unsubscribe.php`, `_lib.php`, `nl_config.php` Block 5 = `NEWSLETTER_UNSUB_SECRET`),
(2) `export.php` deployed ist und `sync_subscribers.py` (liegt in
`docs/launch/newsletter-doi-php/`, vor Aktivierung nach `scripts/` kopieren;
Cron 08:30 vorbereitet) die bestätigten Adressen aus dem Hetzner-MySQL in
`newsletter_subscribers` zieht, (3) die Links in den Mails auf `catandary.de` zeigen. Restliste:
`docs/launch/newsletter-doi-php/NEWSLETTER_GOLIVE.md`. Sender testen:
`python -m pipeline.newsletter_sender --latest --dry-run` (rendert, zählt
Empfänger, sendet nicht).

### 7.5 Anmeldung und Abmeldung (PHP auf dem Webspace)

Anmeldung = Double-Opt-in über `/newsletter/subscribe.php` (+ `confirm.php`,
`cron.php`; Paket `docs/launch/newsletter-doi-php/`, Einbau `EINBAU.md`;
System of Record ist das MySQL auf dem Webspace). Abmeldung = `unsubscribe.php`
(GET Button, POST Abmeldung, RFC-8058-One-Click), antwortet mit 303 auf
`/trends/newsletter/unsubscribed`. Die Next-Route `/trends/newsletter/unsubscribe`
existiert nur lokal und wird in keiner Mail verlinkt.

---

## 8. Analysen (`/analysis`)

**Wozu.** Handgeschriebene, datierte, signierte Analysen als Serie —
LinkedIn-Teaser und Kontinuitätsnachweis für Interessenten (#93 Etappe 2).

**Bedienung.** Eine Analyse ist eine Markdown-Datei
`frontend/content/analyses/<slug>.md` mit Frontmatter `slug, title, date, teaser,
image, corpus_asof, author, draft` (Vorlage `_template.md`); das Bild liegt unter
`frontend/public/analyses/<image>`. `draft: true` = nie gelistet, `/analysis/<slug>`
404. Veröffentlichen = `draft: false` setzen, Bild ablegen, committen (Versionierung
über git, kein Admin-UI). Deep-Dive-Drafts (Abschnitt 7.3) landen hier zum
Redigieren: Kopf mit Gate/Audit, Kondensat, darunter das volle Dossier;
Autor-Zeile umschreiben, kürzen, `draft: false`.

**Grenzen.** Im Export wird `/analysis/<slug>` nur gebaut, wenn mindestens eine
Analyse `draft: false` hat. Die Root-Seite `/analysis` gehört zu den Root-Dateien,
die der Publisher **nicht** hochlädt — auf der Live-Site ist sie 404, bis der
Owner sie von Hand mit der Landing hochlädt oder die Route nach `/trends/analysis`
verschoben wird (offene Entscheidung).

---

## 9. Statischer Export — die öffentliche Website

**Wozu.** Der Webspace kann kein Node. Also wird die Next-App mit `output: "export"`
in einen Ordner gebaut und per SFTP als Manifest-Delta hochgeladen. Verwaltet
werden **nur** `trends/**`, `_next/**` und vier Root-Dateien
(`ROOT_ALLOWLIST`: `trends.html`, `trends.txt`, `robots.txt`,
`.well-known/tdmrep.json`); der Webroot bleibt Owner-Sache. Vollständige Betriebsdoku: `docs/launch/HOSTING_HETZNER.md`.

### 9.1 Bauen

```bash
scripts/build_public_static.sh                      # → frontend/.export/out (+ out.manifest.tsv, out.build_info.json)
PUBLIC_WINDOW_DAYS=3 scripts/build_public_static.sh /pfad/zum/out    # Schnelltest
```

Env: `PUBLIC_WINDOW_DAYS` (30), `PUBLIC_NOINDEX` (**1** bis zum Launch),
`PUBLIC_SITE_URL` (`https://catandary.de`), `KEEP_STAGING=1` (Debug). Das Skript
kopiert `frontend/` per rsync in `frontend/.export/site/` ohne alles aus
`frontend/static-export.exclude` (Foresight, Review, Dossiers, API, Proxy),
baut mit `STATIC_EXPORT=1 PUBLIC_MODE=1`, verifiziert (404/Index/Feed/Expired/
Sitemap, Artikel > 0, **kein** `"status":"draft"` im Payload, `index.json`
valide), kopiert die `.htaccess` aus `frontend/public-export/` hinein und
schreibt Manifest + `build_info.json`. Referenz 04.09.: 15 178 Artikel,
28 Mega-Seiten, 12 Editionen, 33 089 Dateien, 1,31 GB, 55 s Build. Zwei Läufe
nacheinander müssen `diff -rq`-leer sein (Determinismus-Gate) — während des
04:00-Cycles nicht gegeben; ein Build unter DB-Last kann am 20-s-Statement-Timeout
scheitern. Lock `frontend/.export/.lock` (gemeinsam mit dem Publisher).

### 9.2 Lokal prüfen (Apache im Docker)

```bash
scripts/htaccess_test_server.sh            # httpd:2.4, AllowOverride All, out/ read-only auf :8098
HTACCESS_TEST_BIND=100.115.179.37 scripts/htaccess_test_server.sh   # Tailnet-Vorschau vom MacBook
scripts/htaccess_test_server.sh --stop
```

Nach **jedem** Build neu starten (der Build ersetzt `out/`, der Bind-Mount wäre
stale). Der Testplan steht als Kommentarblock am Ende von
`frontend/public-export/trends/.htaccess`; 500er auf dem echten Webspace heißen:
`AllowOverride` dort ist enger (zuerst `Options -Indexes` entfernen, dann
`DirectorySlash`/`RewriteOptions`). Die PUBLIC_MODE-Vorschau `:3999` zeigt
dagegen den *Server*-Modus der öffentlichen Seite (kein `.htaccess`, keine
Client-Suche).

### 9.3 Publizieren

Config einmalig, `~/.config/catandary/webspace.env`, **chmod 600** (fehlt noch —
Owner-Aktion):

```bash
MODE=sftp                  # sftp | rsync | local
HOST=wpXXX.webspace-host.de
PORT=22
USER=login
PASSWORD='geheim'          # oder KEY_FILE=~/.ssh/id_ed25519
REMOTE_ROOT=/public_html   # Docroot prüfen (EINBAU.md nennt /usr/www/users/<login>/)
CONNECTIONS=3
HOST_KEY_POLICY=strict     # erster Lauf accept-new, dann strict
KNOWN_HOSTS=~/.ssh/known_hosts
PUBLIC_NOINDEX=1           # zum Launch auf 0
# PUBLIC_WINDOW_DAYS=30
```

```bash
python scripts/publish_static_site.py                # Dry-Run (Default): Plan je Phase, schreibt nichts
python scripts/publish_static_site.py --apply        # Upload/Löschen; Erstupload Stunden über SFTP
python scripts/publish_static_site.py --apply --full # Reparatur: Remote-Listing statt Manifest
# Flags: --config, --out, --connections 1..4, --min-articles, --max-build-age-hours,
#        --max-delete-pct, --force, --max-errors, --log-file, -v
```

Reihenfolge = Konsistenz (kein atomarer Swap): `_next/**` → Artikelseiten →
Listing/Index/Sitemap, `.htaccess` zuletzt → Löschen. Checkpoint alle 2000
Operationen; ein Abbruch setzt beim nächsten Lauf dort fort. **Sicherheitsnetze
(Exit 2):** Config fehlt/nicht 0600; Build älter 12 h; < 1000 Artikel; > 60 %
Löschungen (nur mit `--force`); 0 verwaltete Dateien; Pfad außerhalb der
Teilbäume. Exit 1 = Übertragungsfehler (erneut starten). Summary
`data/publish_last.json` (nur bei `--apply`). `MODE=local` + `LOCAL_DEST=`
= Vorschau in einen Ordner.

**Cron (vorbereitet, nicht installiert):** `30 6 * * *  scripts/publish_static_site.sh`
— Lock, Kollisionswächter (wartet bis 90 min auf den Cycle), Build, `--apply`;
ohne `webspace.env` stiller Skip; Log `~/logs/catandary-publish-<Datum>.log`.
Wächter 07:45 prüft die Summary, sobald die Config existiert.

### 9.4 Was owner-verwaltet bleibt (Webroot)

`index.html` (= `docs/launch/preview.html`, die Landing), `mark.svg`,
`favicon.ico`, `newsletter/**` (PHP-DOI), die Root-`.htaccess`. Der Publisher
schreibt und löscht dort nie; alle anderen Root-Dateien des Exports
(`404.html`, `imprint.html`, `analysis.html`, …) gelten als „outside scope".
Rechtstexte und Anfrage haben deshalb Export-Adressen unter `/trends/imprint`,
`/trends/privacy`, `/trends/enquiry` (lokal 404). **Einmalig einfügen:**
`docs/launch/root-htaccess.snippet` in die Root-`.htaccess` (TDM-Header +
KI-Crawler-403 für Landing und `/newsletter/`). `robots.txt` und
`/.well-known/tdmrep.json` entstehen beim Build und werden vom Publisher
verwaltet — die handgeschriebene `robots.txt` wird ersetzt.

### 9.5 `PUBLIC_NOINDEX`

Default 1: `robots.txt` = Disallow all, jede Seite `noindex, nofollow`. Zum
Launch **`PUBLIC_NOINDEX=0`** in `webspace.env` (oder als Env vor dem Build);
der nächste Export liefert indexierbare Seiten. Die Landing trägt ihr eigenes
`noindex`-Meta in `preview.html`.

### 9.6 URL-Schema (Apache mappt `.html`)

`/trends` · `/trends/page/<n>` · `/trends/v/<vertical>[/page/<n>]` ·
`/trends/<slug>-<id>` (fehlt die Datei → **410** über `trends/expired.html`) ·
`/trends/mega[/<key>]` · `/trends/methodology` · `/trends/newsletter[/<jahr>-w<kw>|/unsubscribed]`
· `/trends/imprint|privacy|enquiry|tdm-policy` · `/trends/index.json` (Suchindex
~2 MB gzip, Client-Suche: Substring über Titel + Summary, Chips, Zustand im
URL-Hash) · `/trends/sitemap.xml`. Legacy `/trends/vertical/<v>` → 301.

---

## 10. Quellen verwalten

**Regeln seit 03.09. (#97).** Nur Primärquellen mit validem RSS/Atom;
Aggregatoren nur als Entdeckungs-Index. Aufnahme nur bei `tdm_status: ok`:
robots.txt erlaubt `CatandaryTrendsBot` Feed und Artikel, Artikelseite
antwortet dem ehrlichen Bot-UA mit 200, kein maschinenlesbarer TDM-Vorbehalt
(Header, Meta, `noai`, `tdmrep.json`). `fulltext: true` nur ohne
Vorbehalt/Sperre, bevorzugt bei offener Lizenz.

**Felder je Quelle in `sources.yaml`.** `name`, `feed_url`, `type`
(trade_media/press_wire/brand/api), `lead_time_tier` (future/market/now …),
`fulltext: true|false`, `active: false` (Deaktivierung), `relevance_min`
(breite Feeds), `wp_categories`/`ingest_cap` (WordPress-Backfill), und die
**Protokollfelder** `tdm_checked: "YYYY-MM-DD"`, `tdm_status: ok|reserved|blocked|feed_error`,
`license` (nur strukturiert erkannt), `discovered_via` (own/hn/wikipedia/idw/
feedspot/triage). Stand 05.09.: ~515 Feed-Einträge, 41 inaktiv, 170 mit
Volltext; DB `sources`: 290 aktiv / 339 gesamt — neue YAML-Quellen legt der
Poller beim nächsten 04:00-Lauf an (`upsert_source`).

**Neue Quelle aufnehmen.**
```bash
python scripts/probe_source_compliance.py https://example.org/feed --yaml      # Snippet mit Protokollfeldern
python scripts/probe_source_compliance.py --file kandidaten.txt --json out.json --yaml
python scripts/discover_from_aggregators.py --index hn,wikipedia,idw,reddit --probe --yaml   # Kandidaten aus Indizes
```
Snippet in die passende Vertikale von `sources.yaml` einfügen (ggf.
`relevance_min`), dann `python scripts/verify_feeds.py` (prüft **alle** Feeds,
keine Argumente) — oder gezielt pollen: `python -m pipeline.feed_poller FOOD`.

**Bestand prüfen.** `python scripts/probe_source_compliance.py --all-active [--write]`
(schreibt `tdm_checked/tdm_status/license` zurück); monatlich automatisch am 1.
08:00 durch `scripts/monthly_source_check.py --post-issue` (Pass-Rate, Balance,
Feed-Health, WP-Yield, OpenAlex-Dichte, TIP-Erinnerung, Brand-Balance,
**Abschnitt 8 = TDM-Re-Probe** aller aktiven Quellen, ~10 min, `--no-tdm`
überspringt). Statuswechsel melden sich im Issue-#13-Kommentar.

**Deaktivieren.** `active: false` in der YAML **plus**
`python scripts/apply_source_hygiene.py --apply` — die YAML-Flagge synct nie
automatisch in die DB (Dry-Run ohne `--apply`).

**Kontakt mit Verlagen (WP4).** Vorlagen (DE/EN, Bot-Freischaltung, TDM-Lizenz)
und die abgelesene Kontaktliste: `docs/compliance/source_contact_template.md`.
Absender **sources@catandary.de**; Versand ist Owner-Sache, nichts wurde
versendet. Offene Owner-Entscheide (17 Feed-robots-Quellen, 8 Elsevier-Feeds
mit Vorbehalts-Header, Hacker News als Quelle): `docs/compliance/source_probe_2026-09-04.md`.

**Volltext-Retention.** Cron `30 3 * * *`: `purge_raw_content.py --days 14 --apply`
(verarbeitete Einträge, 14 Tage nach Abruf). Für Vorbehalts-Quellen gezielt:
`python scripts/purge_raw_content.py --source "Horizont" --ignore-state --also-extraction --apply`
(ohne `--apply` = Dry-Run mit Zeilen/Bytes; `--by-source` listet die größten).

**Takedown.** `python scripts/takedown.py --url <Artikel-oder-Quell-URL> | --trend-id N | --source "<Name>" [--keep-raw] [--purge-raw] [--deactivate] [--reject-all] [--note "Ticket"] --apply`
— Default Dry-Run. Artikel-Modus: Trend auf `rejected`, gespeicherten Volltext
löschen (außer `--keep-raw`); Quell-Modus: alle Volltexte der Quelle löschen,
Quelle deaktivieren, alle Drafts/Artikel der Quelle rejecten. Prozess und
Antwortfrist (72 h, Entwurf): `docs/compliance/takedown_notice.md`.

**Tote Backlinks.** Monatlich am 2. 07:00 `check_source_links.py --per-source 12 --mark`
(2-Strike, 403/429 nie markiert) → `dead_links` → Artikelseite zeigt Archiv-Link.

---

## 11. Betrieb (Cron, Wächter, Backup, GPU, Logs)

### 11.1 Cron — realer Stand `crontab -l` (05.09.2026)

Alle Pfade zeigen auf den main-Worktree; die Env-Zeilen `XDG_RUNTIME_DIR=/run/user/1000`
und `DBUS_SESSION_BUS_ADDRESS=…` sind Pflicht (sonst scheitert `systemctl --user`
im Handover still).

| Zeit | Job | Skript | Status |
|---|---|---|---|
| 02:45 täglich | Postgres-Backup (dumpdir, zstd, keep 4 Tage) | `scripts/backup_db.py --dest /mnt/data-hdd/backups/catandary --skip-sqlite --keep-days 4` | installiert |
| 03:30 täglich | Volltext-Retention 14 Tage | `scripts/purge_raw_content.py --days 14 --apply` | installiert (03.09.) |
| 04:00 Mo–Fr | Full Cycle + Draft-Richter + Morgen-Mail | `scripts/full_cycle_cron.sh` | installiert |
| 07:45 Mo–Fr | Wächter | `python -m scripts.cycle_watchdog` | installiert |
| 09:00 Mo | Newsletter-Website-Edition | `scripts/weekly_newsletter_publish.sh` | installiert (ohne `NEWSLETTER_DEEP_DIVE`) |
| 05:00 Di | Patent-Ingest BDDS (Cr-Del + Amend) | `scripts/weekly_patents.sh` | installiert |
| 08:00 Di | Patent-Rechnungen (assign_cpc, Tier-Serien, Insights) | `scripts/weekly_patent_analytics.sh` | installiert |
| 06:00 Sa | Nicht-RSS-Ingester + Distill + Research-Index | `scripts/weekly_ingesters.sh` | installiert |
| 06:00 So | Discovery-Loop (Mega-Kandidaten, Head-Retrain) | `scripts/discovery_loop.py` | installiert |
| 1. 08:00 | Monats-Quellencheck (+ TDM-Re-Probe) → Issue #13 | `scripts/monthly_source_check.py --post-issue` | installiert |
| 2. 07:00 | Backlink-Check → `dead_links` | `scripts/check_source_links.py --per-source 12 --mark` | installiert |
| 5. 02:00 | OpenAlex-Monats-Sync (45M-Korpus) | `scripts/sync_openalex_monthly.sh` | installiert |
| 6. 12:00 | Startup-Register (CORDIS/SBIR/GLEIF/CH) | `scripts/monthly_startup_sources.sh` | installiert |
| 06:30 täglich | **Statischer Export → Webspace** | `scripts/publish_static_site.sh` | **vorbereitet in `deploy/crontab.txt`, nicht installiert** (kein `webspace.env`) |
| 12:00 Sa | Research Pulse | `scripts/weekly_research_pulse.sh` | **Vorschlag, auskommentiert** |
| 09:00 Mo | Newsletter-Versand | `scripts/newsletter_tonight.sh` | **gegated, auskommentiert** (#16) |
| 08:30 täglich | Subscriber-Sync MySQL → Postgres | `python -m scripts.sync_subscribers` (Datei liegt noch unter `docs/launch/newsletter-doi-php/`) | **auskommentiert** (#16) |

`deploy/crontab.txt` ist das Template; die drei Wochen-/Monats-Wrapper tragen
einen Existenz-Guard (`[ -x … ] && … || echo skip`), weil sie nach einem
`dev`-Feature erst mit dem Merge auf `main` erscheinen. Alle GPU-Wrapper
(Cycle, Ingester, Startup-Register, Newsletter-Edition, Pulse) teilen sich
seit 05.09. den Kollisionswächter aus §11.8 — zwei GPU-Jobs laufen nie mehr
gleichzeitig gegen `:8090`.

### 11.2 Wächter-Mails

`scripts/cycle_watchdog.py` (07:45 Mo–Fr): Cycle-`end`-Zeile mit rc, heutiges
Backup-Artefakt, Publish-Summary (schlafend ohne `webspace.env`). Mail nur bei
Befund. Manuell: `python -m scripts.cycle_watchdog --dry-run [--date 20260817]`.
Transport: Resend (`RESEND_API_KEY`, `NEWSLETTER_FROM`), Empfänger
`REVIEW_NOTIFY_TO`. Die Review-Mail (`review_notify.py`) läuft am Ende des
Cycle-Wrappers; `--dry-run` druckt, `--force` sendet auch bei leerer Queue.

### 11.3 Backup und Restore

`pg_dump -Fd -j4 --compress=zstd:3` → `/mnt/data-hdd/backups/catandary/catandary-pg-<Datum>.dumpdir`
(~113 GB, ~18 min), verifiziert per `pg_restore --list` gegen die
Live-Tabellenzahl; Fehler sind fatal; `.env` wird mitkopiert; 4 Tage Retention
(Owner 24.08., ~480 GB Steady-State). **Restore:** `docs/restore_runbook.md` —
der eine Stolperstein: `CREATE EXTENSION vector` muss **vor** `pg_restore` als
Superuser in die Zieldatenbank, sonst fehlen still alle Vektor-Tabellen. Der
alte SQLite-Stand liegt einmalig unter `backups/catandary/frozen/`.

### 11.4 GPU-Ruhezustand

Normalzustand: `llama-server.service` aktiv, `~/llama.cpp/start-active.sh →
start-qwen3-8b-208k.sh`, `/v1/models` meldet `Qwen3-8B-UD-Q4_K_XL`, `nvidia-smi`
zeigt ~22 GB belegt (das 8B mit 208k Kontext). Jedes Werkzeug (Cycle, Richter,
Worker, Pulse, Deep Dive, Newsletter) hängt den Symlink um, startet die Unit
neu und stellt den Zustand danach wieder her; `scheduled_cycle.sh` setzt den
Symlink am Ende **immer** zurück.

```bash
systemctl --user status llama-server
readlink ~/llama.cpp/start-active.sh
curl -s localhost:8090/v1/models | python -m json.tool | grep '"id"'
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

### 11.5 Wenn der llama-server tot ist oder das falsche Modell serviert

1. `systemctl --user status llama-server`, `tail -50 /tmp/llama-server.log`.
2. Symlink prüfen — zeigt er auf ein 27B-/Gemma-Skript, ist ein Handover
   abgebrochen: `ln -sf start-qwen3-8b-208k.sh ~/llama.cpp/start-active.sh`.
3. `nvidia-smi`: hält ein fremder Prozess VRAM (manuell gestarteter
   `llama-server`, Unsloth, Open WebUI), beenden. Der Cron-Wrapper räumt nur
   `systemctl --user stop llama-server` und `pkill -f build/bin/llama-server` —
   ein Server aus einem anderen Pfad überlebt das und der 04:00-Lauf OOMt
   (Exit 137).
4. `systemctl --user restart llama-server`, dann `curl -s localhost:8090/v1/models`.
5. Ist ein Cycle mittendrin gestorben (z. B. Stromausfall): `scripts/resume_cycle.sh`
   fährt nur Stage 8/9 + Morgen-Mail nach, ohne neu zu generieren.
6. `cron` braucht `XDG_RUNTIME_DIR` — fehlt die Zeile, scheitern alle Handover
   mit „Failed to connect to bus" und der Lauf macht 0 LLM-Calls.
7. Steht im Cycle-Log `Stage 6 ABORTED at n/m: GeneratedContent: llama-server at
   … serves '…', expected '…'` (oder ein `ModelMismatchError`-Traceback aus den
   8B-Stages), hat ein anderer Job den Server unter der Stage getauscht (#98).
   Nichts ist verloren: die betroffenen Einträge sind weder verarbeitet noch
   gefiltert und laufen beim nächsten Cycle erneut (Stage-Zwischenergebnisse sind
   gecacht). Prüfen, welcher Job es war (`~/logs/catandary-ingesters-*.log`,
   `data/dossier_worker/`), dann §11.8 — der Wächter sollte das verhindert haben.

### 11.6 Logs und Statusdateien

`~/logs/catandary-full-cycle-<Datum-Zeit>.log` (Wrapper, end-Zeile mit rc) ·
`catandary-scheduled-<…>.log` (Stages) · `catandary-watchdog.log` ·
`catandary-backup.log` · `catandary-purge-raw.log` · `catandary-ingesters-<Datum>.log`
· `catandary-patent-analytics-<…>.log` · `catandary-openalex-sync-<…>.log` ·
`catandary-newsletter-publish-<Datum>.log` · `catandary-source-check.log` ·
`catandary-source-links.log` · `catandary-discovery-loop.log` · künftig
`catandary-publish-<Datum>.log`. `/tmp/llama-server.log` wächst unrotiert (64 MB
am 05.09.; war schon 6,9 GB — gelegentlich leeren).
Statusdateien im main-Worktree `data/`: `draft_judge_last.json`,
`research_pulse_last.json`, `newsletter_deep_dive_last.json`,
`publish_last.json` (ab erstem `--apply`), `weekly_ingesters_last.json` und
`monthly_startup_sources_last.json` (Kollisionswächter, §11.8),
`weekly_ingesters_pending_min_id` / `monthly_startup_sources_pending_min_id`
(nur vorhanden, solange ein übersprungener GPU-Schritt nachzuholen ist),
`llama-server.<job>.pid` (Besitzvermerk der Unit, §11.8); Worker-Logs
`data/dossier_worker/`, `data/research_pulse/`.

### 11.7 Pipeline von Hand

```bash
scripts/scheduled_cycle.sh 600                       # Referenzlauf mit GPU-/Service-Wrapper (wie der Cron, ohne VRAM-Räumung)
python -m pipeline.run_full_cycle --dry-run           # nur Zähler, kein Modell
python -m pipeline.run_full_cycle --skip-poll --batch 600 [--min-id N]
python -m pipeline.llm_processor 200                  # Stages auf 200 Einträge (Output in Datei umleiten, nicht pipen)
python scripts/generate_content.py --vertical FOOD --limit 200   # Artikel für Signale nachziehen
python -m pipeline.auto_publisher                     # Stage 9 standalone
```
Vorher `nvidia-smi` prüfen; die Skripte übernehmen `:8090` selbst.

### 11.8 Kollisionswächter und Besitz des llama-servers (#98)

**Warum.** `:8090` gehört immer genau einem Job. Am 05.09. lief ein von Hand
gestarteter Full Cycle bis in den Samstags-Ingester: dessen Handover ersetzte
den Gemma-Server des Cycles durch den Embedding-Server, Stage 6 generierte
gegen das Embedding-Modell, und beim Abbruch stoppte der Cycle den
Embedding-Server der Ingester (2.275 Distill-Aufrufe „Connection refused").

**Wächter (`scripts/lib/gpu_guard.sh`).** Jeder GPU-Wrapper (`full_cycle_cron.sh`,
`scheduled_cycle.sh`, `weekly_ingesters.sh`, `monthly_startup_sources.sh`,
`weekly_newsletter_publish.sh`, `weekly_research_pulse.sh`) ruft vor seinem
GPU-Schritt `gpu_guard_wait <job>` auf: läuft ein anderer bekannter GPU-Job
(`scheduled_cycle.sh`, `run_full_cycle`, `signal_batch*`, `dossier_worker`,
`corpus_research`, `research_pulse`, `newsletter_deep_dive`, `newsletter_generator`,
die Wrapper selbst), wartet er — Default 90 min (`GPU_GUARD_MAX_MIN`), Poll 60 s
— und gibt danach auf. Logzeilen: `[gpu_guard/<job>] fremder GPU-Job aktiv —
warte (max 90 min):` mit PID + Kommandozeile, `… frei nach ~N min — weiter`
oder `… SKIP: nach 90 min immer noch belegt durch:`. Was dann passiert:

| Wrapper | bei Skip |
|---|---|
| `full_cycle_cron.sh` / `scheduled_cycle.sh` | Abbruch **vor** dem VRAM-Räumen, `rc=75` in der end-Zeile → Wächter-Mail; nichts angefasst |
| `weekly_ingesters.sh` / `monthly_startup_sources.sh` | Ingests und CPU-Schritte laufen, nur die `signal_batch_embedded`-Schritte werden übersprungen; `min_id` landet in `data/<job>_pending_min_id` und der nächste Lauf holt das Fenster nach; `rc=75`; Notiz `data/<job>_last.json` (`status: blocked`) → Montags-Mail |
| `weekly_newsletter_publish.sh` / `weekly_research_pulse.sh` | `gen=blocked`, beim nächsten Lauf nachholen |
| Stage 10 im Cycle | wartet 30 min, dann „draft judge SKIPPED: fremder GPU-Job aktiv" |

Von Hand nachholen, wenn ein Ingester-Lauf übersprungen wurde (GPU muss frei sein):

```bash
cat data/weekly_ingesters_pending_min_id                       # gemerkter Wasserstand
python scripts/signal_batch_embedded.py --source-type research --min-id <N>
python scripts/signal_batch_embedded.py --source-type api --no-patents --min-id <N>
rm data/weekly_ingesters_pending_min_id                        # oder den Samstag abwarten
```

**Besitz der Unit (Richter-Block).** Der Stage-10-Block in `scheduled_cycle.sh`
vermerkt nach dem Start `MAINPID OWNERPID` in `data/llama-server.scheduled_cycle-judge.pid`
(`llama_unit_record_owner`) und stoppt danach nur noch einen Server mit
**dieser** MainPID (`llama_unit_stop_owned`). Hat inzwischen ein anderer Job
die Unit neu gestartet, bleibt sie stehen — Logzeile `[gpu_guard/…] WARN:
llama-server PID … gehört nicht diesem Job (unsere war …) — bleibt stehen`.
`rm data/llama-server.*.pid` ist jederzeit ungefährlich (nächster Start
vermerkt neu).

---

## 12. Sicherheit und Recht (kurz)

- **Erreichbarkeit.** `:3001`, `:3004`, `:3999` und der `llama-server :8090`
  lauschen auf allen Interfaces; Review-, Desk- und Recompute-Aktionen sind im
  LAN/Tailnet ohne Login erreichbar (Same-Origin-Check ist die einzige Hürde).
  Empfehlung aus dem Security-Review: `next start -H 127.0.0.1` in der Unit +
  `tailscale serve` für den MacBook-Zugriff — **Owner-Entscheid offen**, weil
  sich der Zugriffsweg ändert. Rate-Limiter lesen `X-Forwarded-For` nur mit
  `TRUST_PROXY=1` (hier 0).
- **Eigenes TDM-Regime (Owner 03.09.).** Wir beachten fremde Vorbehalte
  (`TDM_RESPECT=1`, robots.txt RFC 9309, ehrlicher UA
  `CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology; trends@catandary.de)`,
  ≤ 1 Request/s/Host, Volltext nur bei `fulltext: true`, Löschung nach 14 Tagen)
  — und erklären selbst einen: `TDM-Reservation: 1`-Header auf `/trends/**` und
  `/_next/**`, `tdm-reservation`/`tdm-policy`-Meta + `robots: noai, noimageai`
  auf jeder Exportseite, `/.well-known/tdmrep.json`, Klartext `/trends/tdm-policy`
  (nur im Export), `robots.txt` und `.htaccess`-403 für 36 KI-Crawler
  (`frontend/src/lib/aiCrawlers.ts`; Vitest hält die drei Stellen synchron).
  Suchmaschinen und Link-Vorschauen bleiben erlaubt. Prüfen nach dem Upload:
  ```bash
  curl -sI https://catandary.de/trends/ | grep -i tdm-reservation   # → 1
  curl -s  https://catandary.de/.well-known/tdmrep.json            # → JSON
  curl -sI -A "GPTBot/1.0"    https://catandary.de/trends/         # → 403
  curl -sI -A "Googlebot/2.1" https://catandary.de/trends/         # → 200
  ```
- **Takedown-Prozess.** Anfragen an trends@catandary.de → `scripts/takedown.py`
  (Abschnitt 10); Entwurf des öffentlichen Textes und der internen Frist in
  `docs/compliance/takedown_notice.md`. Attributionspflichten je Quelle
  (OpenAIRE CC BY, CORDIS, UKRI OGL): `docs/compliance/attribution_matrix.md` —
  die Footer-Zeile im Frontend ist noch offen.
- **Rechtstexte** sind Entwürfe ohne anwaltliche Prüfung (`docs/legal/README.md`).
- **Secrets.** `.env`, `frontend/.env.local`, `~/.config/catandary/webspace.env`
  (0600) — nie committen. Der Firecrawl-Key aus der Git-Historie (`4c0b116`)
  ist zu rotieren (Repo privat, Risiko gering).
- **Persönliche Daten** gehen nie ungefragt an Dritte (Registrierungen, Header,
  Signups immer vorher ankündigen).
