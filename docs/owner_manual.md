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
≥ 0,85 — **außer** ein Gate schlägt an: (1) das Grounding-Gate findet im Body
eine Zahl, ein Jahr, einen Prozent- oder Geldbetrag, der in der Quelle nicht
vorkommt (Modell hat etwas erfunden); (2) seit 05.09.2026 (#11) auch einen
**Personennamen**, den die Quelle nicht wörtlich nennt („Henkel-Chef Knobel"
→ „Henkel CEO **Markus** Knobel", real Carsten — Vorname/Titel dazuerfunden);
(3) der Body ist **garbled** (Token-Suppe wie „M M M M M 仪器(", eingestreute
CJK-Zeichen, Wortwiederholungen, < 60 Wörter — `pipeline/content_guard.py`);
(4) der Text bricht mitten im Satz ab. Solche Artikel bleiben `draft` und
landen hier. Ohne Entscheidung bleiben sie liegen.

**Wo.** `http://localhost:3001/trends/review` — nicht im Menü verlinkt,
`PUBLIC_MODE`/Export: 404. Kein Login (Owner-Instanz).

**Bedienung.**
- Drei Ansichten: **Today** (Drafts der letzten 30 h), **Backlog** (alle,
  max. 100) und **Re-check (n)** — die Warteschlange der **Bestandsprüfung
  05.09.2026**: Artikel mit `status='review'`, die
  `scripts/recheck_published_grounding.py` (oder der Draft-Richter) aus
  `published`/`draft` herausgenommen hat; jede Karte nennt in der Zeile
  `reason:` den Grund (`recheck_2026-09-05:name:Markus Knobel`,
  `…:garbled:script_leak:续约`). Nichts in `review` ist öffentlich. Kopfzeile:
  Anzahl heute, gesamt, ältestes Datum, Anzahl im Re-check.
- Jede Karte zeigt links den generierten Artikel, rechts „What the source
  actually said" (Feed-Teaser bzw. Volltext). Beanstandete Token — Zahlen
  **und Personennamen** — sind im Body markiert und in Warnzeilen aufgeführt
  („Not supported by the source: …", „Person named differently than in the
  source: …", „Garbled text: …"); Kopfzeilen-Flags: `cut off mid-sentence`,
  `garbled`, `ungrounded name`, `in review`.
- **Publish** — Artikel geht live; `auto_published=false`, `reviewed_at` gesetzt
  („human-reviewed"), `review_reason` gelöscht. **Reject** — Status `rejected`,
  `reviewed_at` gesetzt. **Write again** — bei abgeschnittenem oder garbled
  Text: der Rohdaten-Eintrag wird für den nächsten Cycle neu eingereiht, der
  aktuelle Draft wird verworfen (die Quelle geht nicht verloren). Der Cycle
  holt für Opt-in-Quellen (`fulltext: true`) den Volltext vorher neu (seit
  08.09.2026 auch für Backlog-Einträge); bei Vorbehalts-Quellen schreibt das
  Modell aus Titel + Teaser + gecachter Extraktion. Alle drei
  Aktionen gelten für beide Warteschlangen (`draft` und `review`).
- **Viele Karten auf einmal** (z. B. die ganze Re-check-Queue): dieselben zwei
  SQL-Schritte wie *Write again* in einer Transaktion — alte Zeilen
  `status='rejected', reviewed_at=NOW()` (Grund bleibt als Audit-Spur), dann
  `raw_entries SET processed=FALSE, filtered_out=FALSE, filter_reason=NULL,
  content_en_json=NULL` (der Stage-6-Cache muss weg, sonst kommt der alte Text
  wortgleich zurück) für ihre `raw_entry_id`s — und danach den Cycle von Hand starten:
  `tmux new -s rewrite` → `cd ~/projects/catandary-trends && bash
  scripts/scheduled_cycle.sh 1500` (nur mit ≥ 6 h Luft zum 04:00-Lauf,
  Kollisionswächter greift). Vorlage: 08.09.2026, 813 Zeilen,
  `docs/compliance/grounding_recheck_2026-09-05.md` (Nachtrag).
- Ein Namens-Treffer ist ein **Hold, kein Urteil**: „Donald Trump" bei Quelle
  „Trump" ist korrekt ergänzt, „Simona Reiche" bei Quelle „Reiche" erfunden
  (real Katherina) — das entscheidet der Mensch. Geprüft wird gegen das, was
  die DB **heute** hält; nach `purge_raw_content.py` gelöschte Volltexte
  können Namen „ungrounded" erscheinen lassen, die das Modell damals gelesen hat.
- Bestandsprüfung wiederholen (CPU, ~2 min für 89k):
  `python scripts/recheck_published_grounding.py --names --garbage --dry-run`
  (Zahlen + Report nach `docs/compliance/grounding_recheck_<Datum>.md`), dann
  `--apply` (Treffer → `status='review'`, `review_reason` gestempelt;
  `reviewed_at` bleibt leer). `--status draft --garbage` fängt Suppe unter
  den Drafts, `--status review` stempelt Gründe auf von Hand verschobene Zeilen.
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

**Grenzen.** Today/Backlog zeigen nur Gate-Holds (Confidence ≥ 0,85). Vom
Richter *gehaltene* Sub-Schwellen-Drafts erscheinen hier nicht; sie bleiben
`draft` und sind über die CLI (`list draft`) erreichbar — außer der Richter
hat sie als garbled nach `review` umgeleitet, dann stehen sie im Re-check-Tab.
Die Grounding-Gates arbeiten fail-open: ohne gespeicherten Quelltext wird
nicht geprüft; der Garbage-Guard prüft den Body auch ohne Quelle.

**Stage-6-Schutz (seit 05.09.2026).** Token-Suppe wird gar nicht erst
gespeichert: der harte Guard würfelt mit frischem Request ohne Prompt-Cache
neu und lässt den Eintrag nach drei Fehlversuchen unverarbeitet
(`GarbledOutputError`, Zähler „garbled → left unprocessed" in der
Stage-6-Zeile des Cycle-Logs). Der Vorfall vom 05.09. (22 Suppen in Folge,
alle Volltext-Prompts an der 4000-Zeichen-Kappe) ist mit
`scripts/repro_stage6_garbage.py` nachspielbar — GPU frei halten, Kopf lesen.

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

**Neue Themen finden (Bottom-up).** `scripts/propose_mega_trends.py` clustert den
Signalraum auf Mega-Trend-Höhe und schlägt gegen die kanonische Taxonomie
**NEW / SPLIT / MERGE / COVERED** vor — read-only, es fasst `mega_trends.yaml`
nie an, sondern schreibt eine Kandidatendatei:

```bash
python scripts/propose_mega_trends.py --limit 60000 --no-label \
    --out mega_trends.candidate.yaml          # ohne LLM-Benennung, rein lokal
python scripts/propose_mega_trends.py --limit 60000 --label-backend local
```

`--status` (Default `signal,published`), `--k-range` (Default `16,30`,
Silhouette-Suche), `--vertical` und `--exclude-source-types` (Default `api`)
schneiden den Raum zu. Der Ausschluss ist wichtig: Förderbescheide und Patente
sind formelhaft, und da nur `title + excerpt[:500]` eingebettet wird, clustert
das Verfahren dann die Satzform statt des Themas (Beleg:
`docs/mega_discovery_2026-09-09.md`). Der Vorschlag wird von
Hand in `mega_trends.yaml` kuratiert — bewusst, denn die Taxonomie ist eine
redaktionelle Entscheidung. *(Der alte SQLite-Prototyp `discover_mega_trends.py`
ist am 09.09.2026 entfernt worden: er zeigte auf die vor-Postgres-Datei
`data/catandary.db` und war durch dieses Werkzeug abgelöst.)*

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

### 5.0 Archiv einer Quelle nachladen (`scripts/ingest_sitemap_archive.py`)

Ein RSS-Feed zeigt die letzten zehn Einträge. Alles davor sieht der Korpus nie —
und genau dort liegt die Frühphase eines Trends. Eine Sitemap listet dagegen das
ganze Archiv, und robots.txt nennt sie meist selbst.

    .venv/bin/python scripts/ingest_sitemap_archive.py sciencealert.com --dry-run
    .venv/bin/python scripts/ingest_sitemap_archive.py sciencealert.com \
        --source "ScienceAlert Health" --since 2014-01 --until 2020-01 --apply
    .venv/bin/python scripts/ingest_sitemap_archive.py --check-blocked

**Was es nicht tut.** Es fasst nichts an, was robots sperrt: die Sitemap-URL und
jede Artikel-URL werden einzeln mit demselben Matcher geprüft wie im Fetcher.
Es holt keine Volltexte, sondern legt nur `raw_entries` an; den Text holt später
`article_fetcher`, der jeden Artikel erneut auf robots und TDM-Vorbehalt prüft.
Und es löscht nichts — doppelte URLs werden übersprungen, Bestehendes bleibt.
Eine Quelle legt es auch nicht an: ein Archiv gehört zu einer Quelle, die schon
in `sources.yaml` geprüft steht.

**`--check-blocked`** beantwortet die Frage, ob der Weg auch für Quellen trägt,
die wir nicht pollen dürfen. Bei vielen Häusern trifft die robots-Regel nur den
Feed-Pfad, während Sitemap und Artikel erlaubt sind — dann ist das Archiv keine
Umgehung, sondern die offene Tür des Hauses. Lauf vom 2026-09-16 über 34
gesperrte Quellen: **2 Treffer** (Netzpolitik.org, Finextra).

Drossel eine Anfrage pro Sekunde, `SITEMAP_DELAY` und `SITEMAP_MAX` stellen um.

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

„What's moving now": datengetriebene Cluster aus dem Signalraum der **letzten
24 Monate** (`--window-months`, 0 = ganzes Archiv), sortiert nach steigendem
Anteil, mit Momentum-Badge, Quellenkonzentration und Evidenzlinks; Rechenstand
und Messgrundlage stehen im Kopf. Die Seite liest **persistierte Snapshots**
(`foresight_runs`/`foresight_clusters`).

**Was auf einer Karte steht (Überarbeitung 2026-09-15).** Der Momentum-Wert ist
der Anteil am Gehör, gemessen auf einem **festen Quellenpanel**: nur Quellen,
die im frühen *und* im späten Vergleichsfenster geliefert haben, zählen mit.
Vorher verglich die Rechnung eine Fachpresse-Ära mit einer Forschungs-Ära und
maß damit unseren eigenen Quellenausbau (226 → 560 Quellen); AI- und
Patent-Cluster stiegen, Fachpresse-Themen fielen. Zusätzlich wird ein Monat,
in dem eine Quelle weit über ihrem eigenen Median liefert, auf diesen Median
gedämpft — ein Nachtrags-Ingest sieht sonst aus wie Momentum (FASHION-Lauf
15.09.: eine Quelle sprang von ~50 auf ~350 Beiträge/Monat und erzeugte allein
den einzigen Aufsteiger, +18,4 pp → +4,2 pp nach Dämpfung). Der **laufende
Monat** fällt ganz heraus. Weil Anteil am Gehör ein Nullsummenmaß ist, steht
die **rohe Mengenänderung** als zweite Zahl daneben. Die Karte nennt außerdem
die **größte Einzelquelle** mit ihrem Anteil (Quellenzahl ist Breite, keine
Bestätigung — der frühere Satz „confirmed by N independent sources" ist weg),
die **Kohäsion** in Worten und den Mega-Trend nur ab 50 % Reinheit. Belege sind
die **neuesten** Signale nahe am Clusterzentrum, höchstens eines je Quelle
(vorher die zentrumsnächsten, also die durchschnittlichsten und oft Jahre alten).
Titel sind innerhalb eines Laufs eindeutig.

**Klick auf den Titel oder „Open cluster"** öffnet `/trends/foresight/clusters/<id>`:
Messwerte, großer Anteilsverlauf, die 12 zentrumsnächsten und die 12 neuesten
Signale der Nachbarschaft (pgvector gegen den gespeicherten Schwerpunkt, im selben
Scope und Zeitfenster), alle Tags und ein Absatz, wie gemessen wurde. Neu rechnen — bewusst nur
auf Knopfdruck, kein Cron (Radar-Regel; Owner 2026-09-15: die Cluster-Schicht
bleibt als Owner-Instrument mit sichtbarem Rechenstand): Knopf **Recompute
snapshot** im Kopf der Seite (startet `python -m pipeline.foresight_snapshot
--all-verticals --dim1024` detached, CPU-only, 10–20 min, Log
`data/foresight_snapshot/<stamp>-clusters.log`, Lock `data/foresight_snapshot.lock`)
oder dasselbe im Terminal. **`--dim1024` ist Pflicht** über 1 Mio. Signale: der
erste Desk-Lauf am 15.09. nahm die 4096er-Spalte, wuchs auf 56 GB und wurde vom
Kernel abgeschossen — samt `:3001`, weil der Prozess im Cgroup des Frontend-Dienstes
hing. Seither laufen alle Desk-Jobs (Dossier, Advisor, Pulse, Snapshot) in einem
eigenen systemd-Scope mit `MemoryMax` (Default 40 GB, `WORKER_MEMORY_MAX` in
`frontend/.env.local`), und der Lader liest die Vektoren seitenweise (20.000 Zeilen).
Derselbe Snapshot speist die Kacheln „Moving right now" im Cockpit und den
Streifen „What's moving" über dem Feed — beide zeigen sein Datum.
Validierung: `scripts/foresight_validation.py` (Known-Trend-Recovery 23/24).

### 5.4 Emerging (`/trends/foresight/emerging?vertical=<V>`)

Die zweite Signalraum-Schicht, **neben** den Clustern (Owner 2026-09-15, auf die
Frage „was müsste man tun, dass wirklich Trends entdeckt werden?"). Cluster
beantworten „worüber wird am meisten geredet", diese Seite „was ist neu".

**Verfahren.** Ein frischer Zeitschnitt (90 Tage; ein zu dünner Bereich bekommt
einmalig 180) wird fein zerlegt, es bleiben nur die wirklich dichten Zellen
(global 83 Nester aus 784 Zellen, also 12 % des Schnitts — der Rest ist
ausdrücklich Rauschen), und fast deckungsgleiche Zellen werden wieder vereint.
Danach läuft der **gesamte Bestand** am Zentrum jedes Nests vorbei und wird je
Monat gezählt. Das ergibt: erster Monat mit mindestens drei Ähnlichen, Alter,
Neuheits-Hebel (Anteil der Treffer in den letzten sechs Monaten gegen den
Anteil, den der Korpus dort hat — 1,0 heißt „verteilt wie das Archiv", 4,5 ist
die Sättigung), Beschleunigung und neues Vokabular gegen den Stand von vor 24
bis 36 Monaten.

**Auf der Karte** steht als Kopfzeile das **Alter**, nicht die Größe. Darunter
der Neuheits-Satz, neue Begriffe, der Monatsverlauf der Ähnlichen über fünf
Jahre, die drei neuesten Belege und — immer — die Schwächen: Quellenzahl, Anteil
der größten Quelle und wie viel des Nests je eine Klassifizierungsstufe gesehen
hat. Ein Nest mit 0 % ist reines Massen-Ingest-Material, das kein Pipeline-Schritt
je gelesen hat. Filter „show only pockets under 18 months" oben.

**Das ist ein Sucher, kein Urteil.** Die Sortierung nach Aktualität hebt
zwangsläufig auch Tagesnachrichten und Massenquellen. Im ersten Lauf stand ganz
oben ein Nest mit 647 Dokumenten Pseudowissenschaft aus einem Forschungs-Sweep —
tatsächlich dicht, tatsächlich neu, inhaltlich wertlos. Deshalb die Schwächen
auf jeder Karte statt stiller Filter.

**Die vier Ebenen.** Ein Wissenschaftstrend ist nicht dasselbe wie ein
Markttrend, auch bei gleichem Thema (Owner 2026-09-15). Jedes Nest wird deshalb
**getrennt je Ebene datiert** — Forschung, Patente, Förderung, Markt —, und die
Karte zeigt, welches Gespräch es hauptsächlich ist, wann die anderen begannen und
wie viele Monate zwischen Forschung und Markt liegen. Dazu die Zahl der
**verschiedenen genannten Firmen** früh gegen spät; weil nur 13 % der
Fachpresse-Zeilen einen extrahierten Namen tragen, ist das eine Untergrenze und
sagt das auch.

Die Reiter **by conversation** über dem Raster öffnen Läufe, die **nur** eine
Ebene geclustert haben. Das ist nötig, nicht Kosmetik: die Einbettung kodiert den
Sprachstil mit, eine wissenschaftlich formulierte Anfrage findet fast nur
Wissenschaft (gemessen: „perovskite tandem solar cells" trifft in 400.000
Dokumenten 146 Forschungs- und 2 Marktzeilen). Ein Marktgespräch wird nur
gefunden, wenn man die Fachpresse für sich clustert. Die Marktebene bekommt dabei
automatisch feinere Zellen — Fachpresse schreibt über alles, ihre Nester sind
klein.

**Namen.** Der Titel einer Karte kommt vom lokalen Modell: es liest die
zentrumsnächsten Titel des Nests und benennt sie. Jedes bedeutungstragende Wort
muss im Nest wirklich vorkommen, sonst wird der Name verworfen und das
Schlagwort-Label bleibt stehen; unter dem Namen steht klein „tags say: …", damit
man beides sieht. 311 von 328 Nestern bekamen am 15.09. einen Namen, aus
„World · Action" wurde „World-Action Models". Abschaltbar mit `--no-llm-names`.

**Prüfung gegen bekannte Trends.** `.venv/bin/python scripts/validate_emerging.py`
lässt die Erkennung auf 21 historischen Stichtagen laufen und hält 20 datierbare
Trends aus `known_trends.yaml` dagegen. Ergebnis 15.09.: 9 von 20 gefunden, 5 vor
dem Mainstream, Median-Vorlauf 6 Monate, Gegenproben nie über 0,62. Die
Mainstream-Daten in der Datei sind eine Einschätzung, keine Messung — korrigiere
sie, und die Vorlaufzeiten ändern sich mit. Lies das Ergebnis zusammen mit dem
Abschnitt „Ehrliche Lesart" in `docs/emerging_nests_2026-09-15.md`.

**Neu rechnen** (kein Cron, Radar-Regel): Knopf **Recompute pockets** im Kopf
der Seite oder im Terminal `python -m pipeline.emerging_snapshot --all-verticals --all-tiers`
(CPU für Erkennung und Datierung, eine GPU-Übergabe für die Namen; global ~6 min,
je Ebene ~5 min, kleine Vertikale Sekunden). Einzelne Bereiche mit
`--scope tier:market` oder `--scope vertical:FOOD`.
Tabellen `emerging_runs`/`emerging_nests`, je Bereich bleibt ein Lauf stehen.
Methode, Messungen und die offenen Punkte: `docs/emerging_nests_2026-09-15.md`.

### 5.5 Evolution (`/trends/foresight/evolution?vertical=<V>`)

Cluster-Abstammung über Zeitfenster: Fäden mit *New* / *Fading*, rising /
steady / cooling und „shifting in meaning" bei starker Drift. Liest die
persistierte Lineage; rechnen mit dem Knopf **Recompute lineage** im Kopf
(`python -m pipeline.foresight_snapshot --lineage`, detached, CPU-only) oder im
Terminal mit Fensterparametern `[--since … --until … --step … --span …]`.

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


### 5.10 Kunden-Briefing (`/trends/foresight/pitch`)

**Wozu.** Catandary Foresight einem Interessenten vorstellen — im Browser, im
Design der Seite, statt als PDF oder Folien. Aufgebaut nach dem
McKinsey-Rahmen **Situation → Complication → Resolution → Question**: was
Strategieteams heute lesen (Fachpresse), warum das zu spät und zu unsicher ist
(Volumen, Versprechen gegen Realität, kein Belegpfad), was Foresight anders
macht (Korpus in vier Ebenen → Messung der Innovationskette → datiertes,
belegtes Dossier → deterministische Prüfung + Mensch), wie ein Dossier geprüft
wird (mit echtem Kalenderblock aus dem LFP-Dossier), welche Frage der Kunde
mitbringt (Timing, Skepsis, Exposure) und die zwei Angebotsformen; zum Schluss
„What we do not claim" und der Kontakt.

**Bedienung.** Öffnen über das Foresight-Cockpit („Briefing deck for prospects
→") oder direkt `/trends/foresight/pitch`. **← → / Bild↑↓ / Pos1 / Ende**
blättern, die Rail rechts zeigt die Folie und springt per Klick; die URL trägt
die Folie (`#s3`), ein geteilter Link landet also auf derselben Stelle. Am
besten im Vollbild des Browsers (F11) über Tailscale Serve vom MacBook.

**Zahlen.** Die vier Kacheln der Titelfolie kommen live aus der Datenbank
(aktive Quellen, analysierte Signale, Forschungswerke ≈ Planer-Schätzung,
Patente mit Zitationsgraph), 1 h gecacht; fällt eine Zählung aus, steht „—",
die Seite bleibt. Die Methodik-Aggregate wurden bewusst *nicht* verwendet
(20-s-Timeout auf kaltem Cache).

**Regeln.** Dieselben wie für die Launch-Site: kein Methoden-USP („nur wir"),
keine Kundenlogos oder Zertifikate, die Verbesserungsrate als *relative
Entwicklung* und nicht als Frühwarnung, KI-Erzeugung und menschliche Abnahme
offen benannt. Die Seite ist Owner-only (PUBLIC_MODE 404, nicht im statischen
Export) — sie zitiert Arbeit im Review-Status.

### 5.11 Themensuche (`/trends/foresight/topic`)

Ein Begriff rein, die Datenlage raus — je Konversation (Forschung, Patente,
Förderung, Markt) getrennt gesucht und getrennt datiert. *Stand 17.09.2026:
auf `dev` (:3004), noch nicht auf `main`.*

**Seite.** Begriff ins Feld, Häkchen bei den Ebenen, *Search*. Die URL ist die
Anfrage (`?q=…&tiers=market,patent`), ein Lesezeichen ist eine gespeicherte
Suche; `&fresh=1` (Link „recompute" unten) rechnet neu statt aus dem Cache.
Von oben nach unten:

1. **Belege je Ebene** mit `head` (Ø der fünf besten Ähnlichkeiten) und `cut`
   (angewandte Schwelle = max(head − 0,08, 0,62)). „—" = nichts Nahes (Kopf
   unter dem Minimum der Ebene), „thin" = unter 5 Treffer, „+" = das
   1.000er-Fenster ist voll, die Zahl ist ein Boden.
2. **What it was called, and when** — frühere Wortpaare aus den ältesten
   Treffern (nur wenn sie nah an der Anfrage bleiben, ≥ 0,72; anklickbar als
   neue Suche) und die ältesten Volltext-Belege, die der Vektor akzeptiert.
3. **When each conversation began** — je Ebene der erste *tragende* Monat
   (≥ 3 Treffer in einem Monat), daneben der erste Einzeltreffer und der
   Abstand zur vorigen Konversation; darunter Forschung → Markt in Monaten,
   Neuheits-Hebel, Beschleunigung, Anteil etablierter Quellen, Marktakteure.
4. **Last 60 months** — Kurve je Ebene, die neuesten Belege (einer je Quelle,
   verlinkt), und die **Schwächen** des Blocks (⚠): zu dünn, Fenster voll,
   nur 1–2 Quellen, größte Quelle ≥ 50 %, gedämpfte Ausschläge einer Quelle,
   wenige klassifizierte Zeilen, junge Quellen, fehlender Index.
5. **Rückfrage** statt Bericht bei Kurzanfragen (≤ 2 Wörter), die sich über
   Vertikale verteilen oder deren bester Kopf unter 0,75 liegt („rag" wird als
   Lappen eingebettet): drei Felder mit Beispieltiteln — Anfrage präzisieren.

**Vorschläge unter dem Suchfeld:** Namen der Nester (letzter Lauf global +
Ebenen, Etikett Ebene · Alter · Zeilen), neues Vokabular, gestellte Fragen mit
Ergebnis. Auf jeder Nest-Karte unter `/emerging` steht „search →".

**Anfragen formulieren.** In der Sprache der Quellen (Englisch), so wie die
gesuchte Ebene spricht — eine fachsprachliche Anfrage findet Forschung, eine
Produktsprache den Markt. Für die Volltext-Spur gelten `websearch`-Regeln
(`"phrase"`, `OR`, `-wort`).

**CLI (dasselbe Ergebnis als Text oder JSON):**

```bash
cd ~/projects/ct-dev
.venv/bin/python -m pipeline.topic_report "precision fermentation of dairy proteins"
.venv/bin/python -m pipeline.topic_report "glp-1 weight loss" --tiers market,patent --json
```

**Rücktest** gegen `known_trends.yaml` (Marktebene; Forschung nur mit
`research_institutional`): `.venv/bin/python scripts/validate_topic_search.py`
→ `data/topic_validation.json`, ~10 s. Stand 17.09.: Markt 18/18, Gegenproben
0/3; tragender Marktmonat im Median 23 Monate nach dem Marktdatum (Korpus vor
2024 dünn), erster Einzeltreffer 72 Monate davor.

**Cache.** Gleiche Anfrage + gleiche Ebenen = sofort aus `topic_reports`
(7 Tage); Korpus-Monatszahlen 24 h in `topic_cache`.

**Suchtabelle.** `topic_vectors` (Ebene + Vektorkopie je Trend, vier HNSW-
Teilindizes, 23 GB) wird von jeder Anfrage um neue Zeilen ergänzt. Einmalig
bzw. nach einem Restore: `.venv/bin/python scripts/migrate_topic_vectors.py
--indexes` (~2 min füllen, ~8 min Indizes); `--status` zählt, `--reconcile`
sammelt Nachzügler ein.

**Voraussetzung.** Der CPU-Embedder `catandary-embed-cpu` (`:8091`) muss laufen
— ohne ihn zeigt die Seite die Fehlermeldung der Maschine.

**Emerging seit Stufe 5:** der Knopf *Recompute pockets* rechnet nur noch
global + vier Ebenen (`--scope global --all-tiers`); die Vertikal-Reiter sind
weg, eine Vertikal-Frage ist eine Themensuche.

## 6. Dossier-Desk (`/trends/dossiers`)

**Wozu.** Scouting-Dossiers zu Technologiefeldern bestellen: der agentische
Rechercheur (`scripts/corpus_research.py`) durchsucht die eigenen Korpora
(Artikel, Signale, Paper, Patente), optional das Web, **misst und zählt** vorher
die Innovationskette (CPC → TIR-Trajektorie, Lead-Time, Zykluszeit,
Zentralitäts-Peak, Leitpatente; dazu die Korpus-Zählung je Jahr) und liefert
einen zitierten Bericht mit maschineller Endkontrolle. Proprietäre
Owner-Dokumente: streng lokal (Qwen3.8-27B), kein Kundenpfad, kein Cron.

**Wo.** `/trends/dossiers` (Desk), `/trends/dossiers/<slug>?v=<n>` (Leseansicht).
Lokal standardmäßig an; `DOSSIERS_ENABLED=0` = Not-Aus; im Export nie gebaut.

**Wie der Rechercheur sucht (seit 09.09.2026).** Standard ist jetzt die
**Vektorsuche** über `trends.embedding_1024`, sobald `RESEARCH_EMBED_HOST`
gesetzt ist (`.env`: `http://127.0.0.1:8091`) und der CPU-Embedder läuft:

```bash
systemctl --user status catandary-embed-cpu       # muss active sein
curl -s http://127.0.0.1:8091/v1/models | head -c 80
```

Der eigene Server ist nötig, weil `:8090` während des Laufs den 27B hält — ein
Embedding-Request dorthin käme vom Chatmodell. Er läuft auf der CPU
(~5 GB RAM, **kein VRAM**), eine Anfrage dauert ~0,3 s. Ist er aus, sucht der
Rechercheur per Volltext wie vorher; fällt er mitten im Lauf aus, schaltet er
selbst zurück und schreibt den Grund in die Notizen (sichtbar im
Herkunftskopf). Erzwingen lässt sich beides je Auftrag über
`params = {"retrieval": "fts"}` bzw. `"vector"`.

**Auftrag anlegen (Desk).** Formular „New order slip":
- **Technology field** (Pflicht, ≤ 500 Zeichen) — die Phrase, die auch gemessen wird;
- **Series slug** (optional) — gleicher Slug = nächste Version derselben Serie;
- **Custom question** (optional) — ersetzt die Foresight-Standardfrage; ändert
  die Recherche, nicht die Messung;
- **CPC anchor** (optional, seit 2026-09-13, z. B. `H01M4/5825`) — die
  Patentklasse, in der gemessen werden soll. Normalerweise nicht nötig: die
  Kaskade misst die Kernphrase ohne Anwendungs-Anhängsel und wählt bei einer
  breiten Klasse die dichtere Titelklasse derselben Familie (für LFP findet sie
  `H01M4/5825` selbst). Der Anker ist der Override, wenn du die Klasse besser
  kennst als der Entdecker. Codes ohne Leerzeichen; findet der Anker keine
  Trajektorie, läuft die Kaskade wie bisher und der Messanhang nennt beides;
- Checkbox *measure the innovation chain first* (Quant-Vorstufe: CPC → TIR →
  Lead-Time → Hub-Patente als zitierbare Quelle „Q1");
- Checkbox *start the worker right away*.
„Place order" legt den Auftragszettel (`dossier_orders`, Status `queued`) an.
Jeder Auftrag läuft seit 2026-09-13 mit **DR-Vorlauf** (Primärquellen zuerst
lesen, Faktenzettel mit festen Plätzen für Paper und Förderung, Kalender-
Kandidaten — dann erst schreiben; ~12 min mehr); abschalten nur per CLI
`--no-dr` bzw. `params {"dr": false}`. Der Erstentwurf wird zweimal geschrieben
und der faktendichtere genommen; danach ein Neuwurf plus höchstens ein Nachzug
für Strukturbefunde. Hergang: `docs/agentic_dossiers.md`, Runde 15.

**Breites Feld statt einer Technologie (Landschafts-Modus, seit 2026-09-13,
nur CLI):** `python -m scripts.dossier_worker --order-new "batteries" --mode
landscape --run`. Vor dem Plan schlägt das Modell 8–14 Teilfelder vor (aus
Feld + 60 Korpus-Schlagzeilen), der Korpus zählt jedes nach (Trend-Signale und
Patente mit Text, UND aller Begriffe); Teilfelder unter 5 Signalen fallen weg.
Der Plan bekommt je Teilfeld einen Suchschritt, die Frage ist die
Landkarten-Frage (was gibt es, was bewegt sich, was ist Hype, was beobachten),
die Themenbegriffe für Actor-Tabelle/Kalender/Kurzfassung umfassen alle
Teilfelder, und das Dossier trägt den Anhang „Landscape map“ mit den Zahlen.
Die Struktur- und Belegregeln bleiben dieselben.

**Web-Suche mit Fallback (seit 2026-09-13):** Brave zuerst; antwortet Brave mit
402 (Kontingent), 429, 5xx oder gar nicht, übernimmt die lokale SearXNG-Instanz
(Metasuche über Brave/Google u. a.). Container: `docker run -d --name searxng
--restart unless-stopped -p 127.0.0.1:8888:8080 -v <repo>/data/searxng:/etc/searxng
searxng/searxng:latest` mit `deploy/searxng/settings.yml` (JSON-Format an,
Limiter aus). Prüfen: `curl 'http://127.0.0.1:8888/search?q=test&format=json'`;
`docker restart searxng`, wenn er nicht antwortet. `WEB_SEARCH_BACKEND=searxng`
erzwingt ihn, `result.web.cache.searxng_api` zählt je Lauf.

**Warum ein v1 jetzt eher trägt (Runde 16, 13.09.):** Neuwurf-Aufträge nennen
das Thema und verbieten Fremdfakten; die Kurzfassung muss das Thema nennen; das
Kalender-Soll folgt den belegten Kandidaten (mind. 3 statt starr 5); ein zweiter
Neuwurf, der nichts bessert, wird verworfen. Details `docs/agentic_dossiers.md`.

**Der Leser (seit 2026-09-13):** Vor dem Neuwurf liest dasselbe Modell den
Entwurf noch einmal — als fordernder Vorstand, nicht als Autor: Beantwortet
das Dossier die Frage? Ist jede Sektion beim Thema? Sind die Optionen
entscheidungsfähig? Fehlt ein Teilfeld der Landkarte? Seine Einwände (höchstens
acht, mit Zitatstelle und konkreter Änderung; er darf keine Zahlen oder Namen
hinzufügen) gehen in denselben Neuwurf-Auftrag wie die Code-Befunde. Nach der
Endfassung liest er ein zweites Mal; was dann bleibt, steht im Prüfnachweis als
„Leser (nicht sperrend)" und in der Review-Ansicht — als Lesehilfe für deinen
Sign-off, nie als Sperre. Ausschalten: `DOSSIER_READER=0`.
Seit 14.09. löst der Leser auch den zweiten Neuwurf aus, wenn nach dem ersten
schwere Einwände bleiben; Liste und Dossieransicht zeigen beide Ampeln
(„end-control clean" / „reader objects"). Der Bericht entsteht seit 14.09.
**Sektion für Sektion** (sieben Aufrufe, Kurzfassung zuletzt) statt in einem
Zug — `DOSSIER_WRITE=single` stellt den alten Pfad her.

**Die Messkette (seit 2026-09-07, Default AN).** Ein Dossier trägt jetzt zwei
codegenerierte Anhänge, die nicht das Modell schreibt, sondern der Code:

- **„Measured development"** — Jahres-Zeitreihe je Reifegrad
  (Forschung/Patente/Förderung/Markt), Take-off-Jahre, Patent→Markt-Vorlauf,
  Verbesserungsrate K(t) mit n je Fenster, Zykluszeit und Zentralitäts-Peak.
- **„What the corpus counts"** — wie viele Treffer der eigene Korpus zum Thema
  überhaupt hat, je Jahr, Vertikale, Signaltyp, Quelle, plus Top-Geldgeber der
  Forschung.

Findet die Messung das Feld nicht, **steht der Fehlschlag mit jedem Versuch im
Dossier** (vorher verschwand er stumm). Die Endkontrolle meldet zusätzlich
„Messung ausgefallen" bzw. „gemessen, aber im Text nicht verwendet".
Zitiert wird über Katalog-IDs statt URL-Freitext, der Paper-/Patent-Sweep läuft
auch ohne Audit-Befund (Kappen 24 Paper / 16 Patente) und bekommt nach dem
Re-Audit genau eine Nachrunde.

Abschalten (alter Pfad, reproduzierbar): `DOSSIER_MEASURE=0` in der Umgebung
des Workers, `--no-measure` bei `scripts/corpus_research.py`, oder
`params = {"measure": false}` am Auftragszettel.

**DR-Modus (seit 2026-09-07, Default AUS — Feature in Development; das
Ziel „besser als Sonnet Deep Research" ist offen, Stand in
`docs/dossier_vs_deep_research_2026-09-07.md`, Issue #100).** Die Arbeitsweise eines
Deep-Research-Agenten: der Lauf liest vor dem Schreiben bis zu 28 ungelesene
Treffer **nach Rang** (Behörde/Register/Journal zuerst, Presse gar nicht),
zieht daraus **Notizen** — datierte Einzelaussagen, jede maschinell gegen ihren
Quelltext geprüft — und schreibt den Bericht aus diesem Faktenbuch statt aus
dem Rohmaterial; gesampelt wird nach Modellkarte (temp 0.7, top_p 0.80,
top_k 20, presence_penalty 0.5 — die 1.5 der Karte bestrafen genau die
Wiederholung, von der eine Faktentabelle lebt) statt nur über die Temperatur.
Seit Runde 13 legt der Lauf dem Bericht außerdem zwei fertige Listen vor:
**Kalender-Kandidaten** (datierte Zukunftstermine, aus jeder gelesenen Seite
maschinell gezogen und gegen sie geprüft) und **Aufwands-Anker** (Förderbeträge,
Programmbudgets, Verfahrensdauern aus Förder-/Rechtsseiten). Seit Runde 14
kommt eine **Akteur-Landkarte** dazu (je Akteur die jüngste belegte Aussage
mit Zahl oder Datum; „Was sich bewegt" beginnt mit einer Pflichttabelle), die
Streichung arbeitet auf Absatzebene und repariert Sätze mit ungestützter Zahl
erst per Modell, und die Suchrichtungen sind **themenneutral**: Kern +
kuratiertes Rückgrat je Vertikale + Modellprofil. Welche Anfragen ein Thema
auslöst, zeigt ohne Lauf:

```bash
.venv/bin/python scripts/dossier_topic_probe.py "solid-state batteries"
.venv/bin/python scripts/dossier_topic_probe.py "vertical farming" --brave --read 5
```

(rechnet das Profil gegen den gerade laufenden llama-server — im Ruhezustand
das 8B, aussagekräftig erst mit dem 27B). Einschalten:

```bash
DOSSIER_DR=1 .venv/bin/python -m scripts.dossier_worker --order N
python scripts/corpus_research.py --foresight "solid-state batteries" --dr --quant
# oder am Auftragszettel: params = {"dr": true}
```

Der Modus kostet Laufzeit (ein Modellaufruf je Primärquelle) und macht den
Bericht faktendichter, aber strenger: Aussagen ohne Primärquelle werden in der
Kurzfassung gestrichen.

**Denken einschalten (optional, seit 2026-09-07).** Der 27B kann mit Reasoning
laufen. Dafür eine Datei `~/.config/catandary/llama-server.env` anlegen —
die Unit `llama-server.service` liest sie, wenn sie existiert:

```
LLAMA_REASONING=on
LLAMA_REASONING_EFFORT=medium     # low | medium | high | xhigh
```

Dazu den Lauf mit `DOSSIER_DR_THINK=1` starten (dann gilt der denkende
Sampling-Satz der Modellkarte und ein Client-Zeitlimit von 2.400 s statt 600).
**Kein `LLAMA_ARG_THINK_BUDGET` setzen:** läuft die Denkspur ins Budget,
schließt llama.cpp die Denkmarke selbst und das Modell überlegt im Antwortfeld
weiter — am 2026-09-07 standen so 51 Zeilen Überlegung vor der ersten
Überschrift. **Datei nach dem Lauf wieder löschen** — sonst denkt auch der
nächtliche Draft-Richter, und der Cycle wird deutlich langsamer. Der
Berichts- und der Revisionsaufruf des Dossiers denken seit Runde 13 in keinem
Fall (`enable_thinking: false` je Anfrage) — geschrieben wird nach dem
nicht-denkenden Satz der Modellkarte, egal wie der Server gestartet wurde. Ein Vergleichslauf gegen die Runden davor steht in
`docs/agentic_dossiers.md` (Abschnitt „Die DR-Runde").

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

Ablauf je Lauf: Phase 1 Embedding-Handover + Quant-Messblock → Phase 1b
Korpus-Zählung (CPU/SQL, kein Modell) → Phase 2 27B-Handover (VRAM-Vorab-Check
< 1,1 GB Fremdbelegung, Identitäts-Check `/v1/models`) → Plan → Korpus-Suche →
Audit → Paper-/Patent-Sweep (auch ohne Audit-Befund) → Web → Re-Audit → eine
Sweep-Nachrunde → Bericht → **Zitat-Kanonisierung** (Katalog-IDs; jede URL muss
im gesammelten Katalog stehen, sonst gestrichen) → Mess- und Korpus-Anhang →
Endkontrolle → Status **`review`**. Danach Ruhezustand (Symlink 8B-208k,
llama-server wieder aktiv, falls er lief).

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


### 6.5 Advisor — Beratungsnotiz je Kunde

**Wozu.** Das Dossier kennt seinen Leser nicht; deshalb trägt es seit dem
14.09. keine Optionen mehr, sondern „Decision points and watch items". Die
Beratung entsteht später, wenn Kunde und Auftrag bekannt sind — als eigene,
versionierte Notiz zu **einer** Dossier-Version.

**Bedienung.** Auf der Dossierseite unter „Advisory notes for this dossier" →
„New advisory note": Kundenprofil (Branche, Größe, Position in der
Wertschöpfung, Fähigkeiten, Geografie, Horizont, Risikoappetit, Notizen) und
der **Auftragsumfang** (Pflicht: die anstehende Entscheidung, was drin und
draußen ist, Budget/Zeit). „Create note" legt die Notiz an und startet den
Advisor (Haken „start right away"; ~10–20 min: 27B mit eingeschaltetem Denken,
Symlink auf `start-qwen3.8-27b-thinking.sh`, Ruhezustand danach). Die Ansicht
`/trends/dossiers/<slug>/advisory/<id>` zeigt Profil, Auftrag, Prüfung
(„check clean/objects" · „reader ok/objects") und die Notiz: Situation für
diesen Kunden, Optionen inkl. Null-Option — je Option Trigger, Horizont,
Aufwand **aus einem Vergleichsfall des Dossiers** (Fördergrenzen sind
verboten), Wer zahlt, Risiko, Abbruchkriterium, Gegenargument —, Empfehlung
mit Konfidenz und „was meine Meinung ändern würde", benutzte Belege.

**Regeln.** Geschlossener Katalog: jede externe Zahl/Aussage muss aus dem
Dossier stammen und trägt dessen Zitat; Kundenfakten kommen aus dem Profil
(„(client profile)"). Deterministisch geprüft: gestrichene Marker,
Platzhalter in Pflichtfeldern, Zahlen, die weder im Dossier noch im Profil
stehen; danach liest der Leser. **Nichts geht raus ohne deine Freigabe**
(„Approve for delivery" → `approved_at/approved_by`; „Withdraw approval"
nimmt sie zurück) — dieselbe Regel wie beim Newsletter.

**CLI.** `python -m scripts.advisory --new --dossier <slug>[@v] --profile-file
p.json --scope "…" --run`, `--note <id>`, `--list [--dossier <slug>]`,
`--approve <id> [--approval-note "…"]`, `--withdraw <id>`. Log
`data/advisory/<stamp>.log`, Lock `data/advisory.lock`; läuft ein
Dossier-Worker, verweigert der Desk den Start („busy").

## 7. Newsletter

### 7.1 Website-Edition (automatisch, Di 09:00)

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

**Erster Schritt jedes Versands ist die Freigabe (§ 7.5).** Ohne sie bricht der
Sender ab — auch der Wrapper unten.

`scripts/newsletter_tonight.sh` (Generierung + Versand via Resend) ist **kein
Cron** und darf es erst werden, wenn: (1) das PHP-Abmeldepaket auf dem Webspace
liegt (`unsubscribe.php`, `_lib.php`, `nl_config.php` Block 5 = `NEWSLETTER_UNSUB_SECRET`),
(2) `export.php` deployed ist und `sync_subscribers.py` (liegt in
`docs/launch/newsletter-doi-php/`, vor Aktivierung nach `scripts/` kopieren;
Cron 08:30 vorbereitet) die bestätigten Adressen aus dem Hetzner-MySQL in
`newsletter_subscribers` zieht, (3) die Links in den Mails auf `catandary.de` zeigen. Restliste:
`docs/launch/newsletter-doi-php/NEWSLETTER_GOLIVE.md`. Sender testen:
`python -m pipeline.newsletter_sender --latest --dry-run` (rendert, zählt
Empfänger, sendet nicht). Der Wrapper erzeugt eine **frische** Edition — die ist
naturgemäß noch nicht freigegeben, sein Versandschritt endet also mit `send=2`
und einem Hinweis im Log. Das ist die vorgesehene Reihenfolge (erzeugen → lesen
→ freigeben → senden), kein Fehler.

### 7.5 Ausgabe freigeben (`/trends/newsletter/review`)

**Wozu.** Human-in-the-loop (Owner-Entscheidung 2026-09-06): jede Ausgabe wird
gelesen und freigegeben, bevor sie an die Liste geht. Ohne Freigabe verschickt
der Sender nichts — er bricht mit einer Meldung und **Exit 2** ab. Einen Schalter
zum Abstellen gibt es bewusst nicht.

**Wo.** `http://localhost:3001/trends/newsletter/review` (Owner-Instanz). Die
Seite ist im PUBLIC_MODE 404 und im statischen Export gar nicht enthalten.

**Schritte.**
1. Links die Edition wählen (neueste zuerst; Status **draft / released / sent**).
2. Rechts die **Vorschau** lesen — das ist die Mail selbst, gerendert vom Template
   des Senders (`pipeline/newsletter_preview.py`), nicht eine nachgebaute Ansicht.
   Nur der persönliche Abmelde-Link ist ein Platzhalter, und die Links im
   Vorschau-Rahmen sind bewusst tot (Sandbox).
3. Stimmt sie: optional eine Notiz eintippen (was geprüft/geändert wurde) und
   **Release for sending** drücken. Das setzt `approved_at`, `approved_by`
   (`NEWSLETTER_APPROVER`, Default `owner`) und `approval_note`.
4. Erst danach senden:
   `python -m pipeline.newsletter_sender --year <J> --week <KW>`
   (Probe ohne Versand: `--dry-run`; sie funktioniert auch ohne Freigabe und
   sagt an, dass die Freigabe fehlt).
5. **Withdraw release** nimmt die Freigabe zurück — solange die Ausgabe noch
   nicht versendet ist. Nach dem Versand ist sie unveränderlich (`sent_at`).

**Was die Badges bedeuten** (KI-Kennzeichnung, #99):

| Badge | Bedeutung | Betrifft |
|---|---|---|
| `AI-generated` | Text, den das lokale Sprachmodell geschrieben hat | Weekly Overview (Editorial), Vertical Signals, Deep Dive |
| `Computed` | reine Rechnung über den Korpus, **kein** Sprachmodell | Signal Themes Radar (Signalzahlen je Thema, SQL) |
| `Curated` | Auswahl bestehender Artikel — die verlinkten Artikel sind ihrerseits modellgeschrieben und verlinken ihre Quelle | Cited signals (Trend-Links) |

Unter den Badges steht der Satz, den **jede** Ausgabe trägt — im Mail-Fuß und in
der Website-Edition:

> Sections of this briefing are generated from our corpus by a local language
> model and checked automatically; the selection and this edition were reviewed
> and released by a person.

Er ist die öffentliche Form genau dieses Gates: solange die Freigabe Pflicht ist,
stimmt der Satz. (Anwaltsprüfung zur ausdrücklichen Kennzeichnung nach EU AI Act
Art. 50 läuft — Issue #99; die interne Umsetzung steht bereits.) **Die
Feed-Artikel tragen seit 06.09. einen anderen Satz**, weil dort niemand
freigibt — siehe §12, „KI-Kennzeichnung der Artikel".

**Wenn die Vorschau nicht erscheint.** Der Kasten zeigt die Fehlermeldung des
Renderers. Häufigste Ursache: `.venv` fehlt oder die DB ist nicht erreichbar —
`python -m pipeline.newsletter_preview --year <J> --week <KW> | head` im Terminal
zeigt dasselbe.

**Spalten.** `newsletter_editions.approved_at / approved_by / approval_note`
(additive Migration `scripts/migrate_newsletter_approval.py`, auf der Live-DB am
2026-09-06 ausgeführt). `sent_at`/`recipients_count` bleiben, was sie waren.

### 7.6 Anmeldung und Abmeldung (PHP auf dem Webspace)

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
`frontend/public/analyses/<image>`. `draft: true` = öffentlich nie gelistet, im Export und
unter PUBLIC_MODE 404 — **auf der Owner-Instanz (:3001/:3004) aber sichtbar** (seit 2026-09-14:
„Draft“-Marke in der Liste, Hinweisbanner auf der Seite), damit ein Stück an seiner
endgültigen URL gelesen werden kann, bevor es live geht. Veröffentlichen = `draft: false` setzen, Bild ablegen, committen (Versionierung
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
   Vorab rechnet `scripts/methodology_stats.py` die Korpuszahlen der Methodik-Seite in `frontend/.export/methodology_stats.json` (ca. 1–2 min); ohne diese Datei würde die Seite im Export in den DB-Timeout laufen.
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

**Cron (installiert 05.09.2026):** `15 3 * * *  scripts/publish_static_site.sh` — täglich nach dem Review-Tag, rund 45 min vor dem 04:00-Cycle
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
(Header, Meta, `noai`, `tdmrep.json`). `fulltext: true` seit 11.09.2026 bei allen
`tdm_status: ok`-Quellen (Option A, Owner; vorher nur bei offener Lizenz) — nur ohne
Vorbehalt/Sperre, bevorzugt bei offener Lizenz.

**Felder je Quelle in `sources.yaml`.** `name`, `feed_url`, `type`
(trade_media/press_wire/brand/api), `lead_time_tier` (future/market/now …),
`fulltext: true|false`, `active: false` (Deaktivierung), `relevance_min`
(breite Feeds), `wp_categories`/`ingest_cap` (WordPress-Backfill), und die
**Protokollfelder** `tdm_checked: "YYYY-MM-DD"`, `tdm_status: ok|reserved|blocked|feed_error`,
`license` (nur strukturiert erkannt), `discovered_via` (own/hn/wikipedia/idw/
feedspot/triage/owner-domainliste-<Datum>/oa-ersatz-<Datum>), sowie
`llm_pipeline: false` + `store_excerpt: false` für den Signalbetrieb (s. u.).
Stand 09.09.: 568 Feed-Einträge, 8 inaktiv, **560 aktiv** (davon 33 im
Signalbetrieb, 178 mit Volltext); DB `sources`: 601 aktiv / 616 gesamt, darin
95 Nicht-RSS-Pseudoquellen (Patente, OpenAlex, Funding). 53 YAML-Quellen haben
noch keine DB-Zeile — die legt der Poller beim nächsten 04:00-Lauf an
(`upsert_source`), dann sind es 654.

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

**Volltext-Retention.** Cron `30 3 * * *`: `purge_raw_content.py --days 1825 --apply`
(verarbeitete Einträge, **60 Monate** nach Abruf — Frist am 10.09.2026 von 14 Tagen
erweitert; §44b Abs. 2 S. 2 UrhG nennt keine Frist, sondern bindet sie an den Zweck,
und der dokumentierte Zweck ist die längsschnittliche Trendanalyse). Für Vorbehalts-Quellen gezielt:
`python scripts/purge_raw_content.py --source "Horizont" --ignore-state --also-extraction --apply`
(ohne `--apply` = Dry-Run mit Zeilen/Bytes; `--by-source` listet die größten).
`--also-excerpt` löscht zusätzlich den Feed-Teaser und **stillt die Zeilen im
selben Zug** (`processed`, `filtered_out`, `filter_reason='source_text_purged'`,
seit 09.09.2026) — ohne das blieben sie im unverarbeiteten Pool und der Cycle
schrieb später Artikel aus dem nackten Titel.

**Signalbetrieb statt Abschalten (seit 09.09.2026).** Eine Quelle mit
maschinenlesbarem TDM-Vorbehalt muss nicht ganz weg: `llm_pipeline: false`
(nie Artikelmaterial) + `store_excerpt: false` (der Poller speichert nur Titel,
URL und Datum, kein Abstract) lassen sie weiterlaufen und in Embeddings,
Mega-Themes und Research Pulse einfließen. So laufen die 33 Vorbehalts-Quellen
seit dem 09.09. Wichtig: `upsert_source` schreibt Flags nie auf eine bestehende
Zeile — nach jeder Flag-Änderung in `sources.yaml`
`python scripts/apply_source_hygiene.py --apply` laufen lassen (synct `active`
in beide Richtungen und `llm_pipeline`; ohne `--apply` Dry-Run mit Plan).
Der Samstagslauf verarbeitet sie über
`scripts/signal_batch_embedded.py --signal-only`.

**Gelöschte Volltexte zurückholen (#102, seit 10.09.2026).** Die alte
14-Tage-Regel hat 17.665 Artikeltexte gelöscht. Verloren ist davon nichts
Grundsätzliches — gelöscht wurde die Kopie, nicht die Quell-URL:

```bash
python scripts/refetch_fulltext.py --limit 200                      # Dry-Run
python scripts/refetch_fulltext.py --since 2026-07-12 --limit 0 --apply
```

Gemessene Quote: **90 %** (54 von 60), Ø 5.564 Zeichen, rund ein Eintrag pro
Sekunde bei 8 Threads. Kein Cron — das ist ein Aufräumlauf, kein Dauerbetrieb.

`--min-age-days` (Default 15) ist dabei nicht Kosmetik: jüngere Einträge hat der
Purge nie angefasst, 70 % von ihnen haben ihren Text noch, und die übrigen 30 %
sind genau die, bei denen der Abruf schon damals scheiterte. Ohne den Filter
zieht der Lauf also gezielt die Fehlschläge — gemessen 5 % Quote statt 90 %.

**Reihenfolge:** erst nachholen, dann einbetten. Sonst entstehen Vektoren auf
775-Zeichen-Anrissen, die man danach noch einmal rechnen müsste.

**Die zweite GPU im Tailnet (seit 10.09.2026).** Auf `bequiet` steckt eine
RTX 5080. Vereinbart ist: **01:00–17:00 nutzen wir sie, 17:00–01:00 gehört sie
Ihnen.** Der Volltext-Embedder greift von selbst danach — er prüft vor jedem
Block Fenster *und* Erreichbarkeit und rechnet sonst auf der lokalen 3090
weiter. Läuft das Fenster mitten im Lauf ab, hört er auf; der nächste Lauf setzt
fort.

```bash
tailscale ping bequiet                                   # erreichbar?
curl -s http://100.119.239.40:11434/api/version          # Ollama wach?
```

Sie ist rund doppelt so schnell wie die lokale Karte (12,4 gegen 6,6 Texte/s),
und die Vektoren sind austauschbar (cos 0,9995 für denselben Text). Eingestellt
wird das in `.env`: `REMOTE_EMBED_HOST`, `REMOTE_GPU_WINDOW`,
`REMOTE_EMBED_MODEL`. Leerer Host = nur die lokale Karte.

Grenze: 16 GB, davon am Sperrbildschirm 13,9 GB frei — bei angemeldetem
Benutzer weniger. Das reicht für 8B, 14B und den Embedder, nicht für das
Gemma-4-26B der Artikelerzeugung oder den 27B-Rechercheur.

**Zweiter Vektorraum über den Quelltext (#102) — zurückgebaut am 11.09.2026.**
Die Messung über 95.023 Zeilen (`docs/embedding_eval_2026-09-11.md`) zeigte
keinen Gewinn gegenüber dem Dedup-Vektor: 95 % der Zeilen haben gar keinen
längeren Text als den Anriss. Owner-Entscheid: kein Backfill, kein 09:00-Lauf,
kein Betrieb auf bequiet. Die Spalten bleiben stehen (nichts liest sie), die
Skripte sind entfernt. Der Hebel für Inhaltsanalyse ist Textabdeckung (§10,
Option A: Volltext für alle 480 tdm-ok-Quellen).

**Ob der zweite Raum wirklich besser ist, wird gemessen, nicht behauptet:**

```bash
python scripts/compare_vector_spaces.py --kind patent -n 3
```

Der Test legt die nächsten Nachbarn aus beiden Räumen nebeneinander und zeigt
die Überlappung. Patente sind der harte Fall: ihre Abstracts beginnen fast alle
mit derselben Formel, und der alte Vektor sieht davon nur die ersten
500 Zeichen — bei einem 1.603-Zeichen-Abstract also 31 %, abgeschnitten mitten
in der Eröffnungsformel.

**Vorher sehen, was kommt (Dry-Run, seit 09.09.2026).** Der Poller zählt auf
Wunsch nur, statt zu schreiben — nützlich vor einer Nacht, in der viele neue
Quellen zum ersten Mal ziehen:

```bash
python -m pipeline.feed_poller --dry-run          # alle Quellen
python -m pipeline.feed_poller FOOD TECH --dry-run
```

Ausgegeben werden Einträge in den Feeds, davon neu, aufgeteilt in
**Artikelmaterial** und **nur Signal** (die Vorbehalts-Quellen), sowie die 15
ergiebigsten Quellen. Es wird nichts geschrieben: keine Quellen-Zeile
(`upsert_source`), kein Eintrag, kein `last_fetched`. Die Feeds werden dabei
wirklich abgerufen — ein Request je Quelle, wie bei einem echten Poll.

**Offen lizenzierte Artikel aus Vorbehalts-Quellen freischalten (seit
09.09.2026).** Ein Verlag kann site-weit TDM vorbehalten und denselben Artikel
unter CC BY veröffentlichen. Die Lizenz ist eine Erlaubnis, der Vorbehalt sperrt
nur die Schranke — für diesen Artikel geht er also ins Leere. Der Cron
`45 3 * * *` erledigt das täglich; von Hand:

```bash
python scripts/resolve_open_licence.py --limit 50                 # Dry-Run mit Statistik
python scripts/resolve_open_licence.py --limit 50 --apply         # wirklich freischalten
python scripts/resolve_open_licence.py --source "Nature (main)" --apply
```

Je Eintrag: OpenAlex-Auflösung (DOI aus der URL, sonst Titelsuche),
Lizenzprüfung (`cc-by`, `cc-by-sa`, `cc0`, Public Domain — nie `-nc`, nie
`-nd`), Volltext von der **offenen Fundstelle**; vom Vorbehalts-Host wird nichts
geholt. Erfolgreiche Einträge bekommen `raw_content`, `open_licence` und
`oa_url` und dürfen damit in den Content-Cycle, obwohl ihre Quelle im
Signalbetrieb läuft. Gemessene Ausbeute (09.09., 60 Einträge): 10 offen
lizenziert, 7 davon mit Volltext. Jeder Eintrag wird genau einmal geprüft
(`licence_checked_at`), auch wenn er nicht offen ist — sonst liefe jede Nacht
dieselbe Abfrage gegen eine kostenpflichtige API. Log:
`~/logs/catandary-open-licence.log`. Verarbeitet werden die Zeilen der
Vorbehalts-Quellen samstags über `signal_batch_embedded.py --signal-only`.

**Quelle deaktivieren stoppt seit 09.09.2026 auch den Backlog.** `active: false`
in `sources.yaml` + `apply_source_hygiene.py --apply` hielt vorher nur den
Poller an; die bereits geholten Einträge liefen weiter in die
Content-Generierung. `get_unprocessed_entries` filtert jetzt zusätzlich auf
`active`. Zusätzlicher Schutz: Einträge mit weniger als
`MIN_SOURCE_TEXT_CHARS` (Default 80) Zeichen Quelltext werden vor jedem
LLM-Aufruf als `insufficient_source_text` verworfen — aus einem bloßen Titel
entsteht nie ein Artikel.

**Takedown.** `python scripts/takedown.py --url <Artikel-oder-Quell-URL> | --trend-id N | --source "<Name>" [--keep-raw] [--purge-raw] [--deactivate] [--reject-all] [--note "Ticket"] --apply`
— Default Dry-Run. Artikel-Modus: Trend auf `rejected`, gespeicherten Volltext
löschen (außer `--keep-raw`); Quell-Modus: alle Volltexte der Quelle löschen,
Quelle deaktivieren, alle Drafts/Artikel der Quelle rejecten. Prozess und
Antwortfrist (72 h, Entwurf): `docs/compliance/takedown_notice.md`.

**Tote Backlinks.** Monatlich am 2. 07:00 `check_source_links.py --per-source 12 --mark`
(2-Strike, 403/429 nie markiert) → `dead_links` → Artikelseite zeigt Archiv-Link.

---

## 11. Betrieb (Cron, Wächter, Backup, GPU, Logs)

> **Was nachts läuft, läuft aus `main`.** Alle Crons starten aus
> `~/projects/catandary-trends`; entwickelt wird in `~/projects/ct-dev`. Eine
> Änderung an einem Cron-Skript, einem Default darin oder an
> `deploy/crontab.txt` ist **erst nach dem Merge nach `main` in Betrieb** — auf
> `dev` committet heißt: noch nicht scharf. Der Merge wird Ihnen vorher
> vorgelegt, mit einer Zeile je Punkt in der Sprache der Wirkung, damit Sie
> wissen, was ab der nächsten Nacht anders ist (Owner-Regel 11.09.2026).
> Ausnahme ohne Merge: Parameter, die in der Crontab-Zeile selbst stehen
> (z. B. `--days 1825`) — die wirken sofort.


> **Zugriff seit 05.09.2026:** Alle Instanzen und der llama-server hören nur auf `127.0.0.1`. Vom MacBook: `https://kiworkstation.tail678c6e.ts.net` (Owner-App :3001; `/` leitet auf `/trends`, es gibt keine App-Landing mehr). **Launch-Tag (01.10.):** `scripts/go_live.sh --dry-run`, dann `--apply` — setzt `PUBLIC_NOINDEX=0`, baut und lädt den Export, entfernt das `noindex` der Landing, lädt sie hoch und prüft alles nach. **Landing-Vorschau vor dem Upload:** `scripts/landing_preview.sh` → `https://kiworkstation.tail678c6e.ts.net:3997/preview.html` (Countdown, Animationen, Formular; das Formular postet an den ECHTEN DOI-Endpunkt), `https://kiworkstation.tail678c6e.ts.net:3004` (dev), `…:3999` (PUBLIC_MODE-Vorschau) — Tailscale Serve, nur im Tailnet, HTTPS. Auf der Workstation selbst weiterhin `http://127.0.0.1:3001`. Die alten Adressen `100.115.179.37:3001` funktionieren absichtlich nicht mehr. Serve-Konfiguration: `tailscale serve status`; ändern: `tailscale serve --bg --https=443 http://127.0.0.1:3001`.

### 11.1 Cron — realer Stand `crontab -l` (05.09.2026)

Alle Pfade zeigen auf den main-Worktree; die Env-Zeilen `XDG_RUNTIME_DIR=/run/user/1000`
und `DBUS_SESSION_BUS_ADDRESS=…` sind Pflicht (sonst scheitert `systemctl --user`
im Handover still).

| Zeit | Job | Skript | Status |
|---|---|---|---|
| 02:45 täglich | Postgres-Backup (dumpdir, zstd, keep 4 Tage) | `scripts/backup_db.py --dest /mnt/data-hdd/backups/catandary --skip-sqlite --keep-days 4` | installiert |
| 03:30 täglich | Volltext-Retention 60 Monate | `scripts/purge_raw_content.py --days 1825 --apply` | installiert (03.09., Frist 10.09. erweitert) |
| 03:45 täglich | Offen lizenzierte Artikel der Vorbehalts-Quellen freischalten | `scripts/resolve_open_licence.py --limit 300 --apply` | installiert (09.09.) |
| 04:00 Mo–Fr | Full Cycle + Draft-Richter + Morgen-Mail | `scripts/full_cycle_cron.sh` (Batch **3000** — so bemessen, dass ein normaler Tag in einem Lauf durchgeht; `CYCLE_BATCH=N` in der Crontab-Zeile hebt ihn für eine Nacht an) | installiert |
| 07:45 Mo–Fr | Wächter | `python -m scripts.cycle_watchdog` | installiert |
| 09:00 **Di** | Newsletter-Website-Edition (von Mo verlegt 11.09.) | `scripts/weekly_newsletter_publish.sh` | installiert (ohne `NEWSLETTER_DEEP_DIVE`) |
| 05:00 Di | Patent-Ingest BDDS (Cr-Del + Amend) | `scripts/weekly_patents.sh` | installiert |
| 08:00 Di | Patent-Rechnungen (assign_cpc, Tier-Serien, Insights) | `scripts/weekly_patent_analytics.sh` | installiert |
| 06:00 Sa | Nicht-RSS-Ingester + Distill + Research-Index | `scripts/weekly_ingesters.sh` | installiert |
| 06:00 So | Discovery-Loop (Mega-Kandidaten, Head-Retrain) | `scripts/discovery_loop.py` | installiert |
| 1. 08:00 | Monats-Quellencheck (+ TDM-Re-Probe) → Issue #13 | `scripts/monthly_source_check.py --post-issue` | installiert |
| 2. 07:00 | Backlink-Check → `dead_links` | `scripts/check_source_links.py --per-source 12 --mark` | installiert |
| 5. 02:00 | OpenAlex-Monats-Sync (45M-Korpus) | `scripts/sync_openalex_monthly.sh` | installiert |
| 6. 12:00 | Startup-Register (CORDIS/SBIR/GLEIF/CH) | `scripts/monthly_startup_sources.sh` | installiert |
| 03:15 täglich | **Statischer Export → Webspace** | `scripts/publish_static_site.sh` | **installiert in `deploy/crontab.txt`, nicht installiert** (kein `webspace.env`) |
| 12:00 Sa | Research Pulse | `scripts/weekly_research_pulse.sh` | **Vorschlag, auskommentiert** |
| 09:00 **Di** | Newsletter-Versand | `scripts/newsletter_tonight.sh` | **gegated, auskommentiert** (#16) |
| 08:30 täglich | Subscriber-Sync MySQL → Postgres | `python -m scripts.sync_subscribers` (Datei liegt noch unter `docs/launch/newsletter-doi-php/`) | **auskommentiert** (#16) |

`deploy/crontab.txt` ist das Template; die drei Wochen-/Monats-Wrapper tragen
einen Existenz-Guard (`[ -x … ] && … || echo skip`), weil sie nach einem
`dev`-Feature erst mit dem Merge auf `main` erscheinen. Alle GPU-Wrapper
(Cycle, Ingester, Startup-Register, Newsletter-Edition, Pulse) teilen sich
seit 05.09. den Kollisionswächter aus §11.8 — zwei GPU-Jobs laufen nie mehr
gleichzeitig gegen `:8090`.

### 11.2 Wächter-Mails

*(Seit 11.09.2026 prüft der Wächter zusätzlich den Ops-Sampler — §11.9.)*

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
   fährt nur Stage 8/9 + Morgen-Mail nach, ohne neu zu generieren. (Seit
   09.09.2026 überspringt der Cycle Stage 8/9 selbst, wenn eine Phase keinen
   Trend angelegt hat — Drafts eines abgebrochenen Laufs holt der nächste
   Lauf mit Neuzugängen oder eben `resume_cycle.sh` nach.)
5b. Steht im Cycle-Log mehrere Nächte hintereinander derselbe Eintrag mit
   `content generation GARBLED, entry left unprocessed`: der Eintrag bleibt
   bewusst offen und wird jede Nacht erneut versucht (im selben Lauf seit
   09.09. nur einmal, nicht mehr in Phase 3/run 2). Dauerfälle per Hand
   stilllegen: `mark_filtered(<raw_entry_id>, "content_generation_error: …")`
   aus `pipeline.db` (Vorlage 09.09.2026, ArchDaily 827670).
6. `cron` braucht `XDG_RUNTIME_DIR` — fehlt die Zeile, scheitern alle Handover
   mit „Failed to connect to bus" und der Lauf macht 0 LLM-Calls.
7. Steht im Cycle-Log `Stage 6 ABORTED at n/m: GeneratedContent: llama-server at
   … serves '…', expected '…'` (oder ein `ModelMismatchError`-Traceback aus den
   8B-Stages), hat ein anderer Job den Server unter der Stage getauscht (#98).
   Nichts ist verloren: die betroffenen Einträge sind weder verarbeitet noch
   gefiltert und laufen beim nächsten Cycle erneut (Stage-Zwischenergebnisse sind
   gecacht). Prüfen, welcher Job es war (`~/logs/catandary-ingesters-*.log`,
   `data/dossier_worker/`), dann §11.8 — der Wächter sollte das verhindert haben.
8. Endet ein `signal_batch`-/Ingester-Lauf mit `ABORT distill: 20 embedding
   backend failures in a row … Exit 3` (Wrapper-rc 3), war der Embedding-Server
   weg. Nichts markiert: Server prüfen (Punkte 1–4), dann den Schritt wiederholen
   — `python scripts/signal_batch_embedded.py --source-type research --min-id <N>`
   (N aus dem Log, „min_id (Wasserstand vor Ingest)"). Stehen aus älteren
   Läufen Einträge mit `filter_reason='embedding_error'` in der DB, obwohl nur
   der Server ausgefallen war (bis 05.09. das Verhalten):
   `python scripts/reset_embedding_errors.py` zeigt die Zahl je Quelle (Dry-Run),
   `--apply` setzt sie zurück (`--since 2026-09-01`, `--min-id N`, `--source-type
   research` grenzen ein); der nächste Lauf embeddet sie neu. Echte inhaltliche
   Fehler (ein Text, den der Server ablehnt) tragen weiterhin `embedding_error`
   und sollen so bleiben.

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
`llama-server.<job>.pid` (Besitzvermerk der Unit, §11.8),
`ops_sampler_state.json` (Zählerstände des Ops-Samplers für CPU-/I/O-Deltas, §11.9); Worker-Logs
`data/dossier_worker/`, `data/research_pulse/`.

### 11.7 Pipeline von Hand

```bash
scripts/scheduled_cycle.sh 600                       # Referenzlauf mit GPU-/Service-Wrapper (wie der Cron, ohne VRAM-Räumung)
python -m pipeline.run_full_cycle --dry-run           # nur Zähler, kein Modell
python -m pipeline.run_full_cycle --skip-poll --batch 600 [--min-id N]
python -m pipeline.llm_processor 200                  # Stages auf 200 Einträge (Output in Datei umleiten, nicht pipen)
python scripts/generate_content.py --vertical FOOD --limit 200   # Artikel für Signale nachziehen
python -m pipeline.auto_publisher                     # Stage 9 standalone
python scripts/reset_embedding_errors.py [--apply]     # als embedding_error aussortierte Einträge zurückholen (§11.5 Punkt 8)
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

**Besitz der Unit.** Wer `llama-server.service` startet, vermerkt `MAINPID OWNERPID`
in `data/llama-server.<job>.pid` und stoppt beim Aufräumen nur noch einen Server
mit **dieser** MainPID — die Python-Handover in `pipeline/gpu_handover.py`
(`<job>` = Einstiegsskript: `run_full_cycle`, `signal_batch_embedded`,
`dossier_worker`, `research_pulse`, `newsletter_deep_dive` …) ebenso wie der
Richter-Block in `scheduled_cycle.sh` (`scheduled_cycle-judge`,
`llama_unit_record_owner` / `llama_unit_stop_owned`). Hat inzwischen ein anderer
Job die Unit neu gestartet, bleibt sie stehen und auch der Symlink wird nicht
angefasst — Logzeilen `… is not the one this job started (PID …) — leaving it
running` bzw. `[gpu_guard/…] WARN: llama-server PID … gehört nicht diesem Job
(unsere war …) — bleibt stehen`. Umgekehrt weigert sich ein Handover, einen
Server zu übernehmen, den ein noch lebender anderer Job vermerkt hat
(`RuntimeError: … belongs to running job <job> (pid N) — refusing to take over`);
der abgewiesene Lauf lässt seine Einträge unberührt. Vermerke toter Jobs
räumt der nächste Start weg; `rm data/llama-server.*.pid` ist jederzeit
ungefährlich.

---

### 11.9 Ops-Dashboard (`/trends/ops`, #104)

**Die Seite** (Owner-Instanz, Link im Foresight-Cockpit unter „Ops"; im
`PUBLIC_MODE` 404, im Export nie gebaut): oben **Jetzt** — sechs Kacheln
(GPU 3090: Speicher, Last, Temperatur, Watt, geladenes Modell, haltender Job ·
GPU 5080 auf bequiet: Backend llamacpp/ollama/down, Fenster, Modell · CPU/RAM ·
Postgres: Größe, Verbindungen, lange Abfragen, die vier größten Tabellen ·
Queues: Backlog, Review-Queue · Sampler: Alter der
letzten Messung, Zeilen/24 h, laufende Jobs). Dann **Platten** — je Gerät
Füllstand je Mount (System-/DB-Platte warnt schon bei 80 %), Lese-/Schreibrate,
Beschäftigung, Temperatur, SMART-Ampel mit Grund (PASSED / „3 reallocated" /
„92 % worn" / FAILED), Betriebsstunden und „voll in ~N Tagen" (lineare
Steigung der letzten 7 Tage; braucht ein paar Stunden Daten). Dann
**Diagramme** über 24 h oder 7 d (`?range=7d`): GPU-Speicher, GPU-Last,
GPU-Temperatur (Linie bei 88 °C), CPU, Platten-Beschäftigung (System + HDD),
RAM, DB-Größe, Backlog/Review-Queue — die farbigen Bänder dahinter sind die
Job-Läufe aus `ops_events`, Legende darüber. Zuletzt **Jobs** (28 Tage: Läufe,
Median-Dauer, letzter Lauf, Ergebnis) und **Runs** (letzte 40: Start, Dauer,
Ergebnis ok/blocked/rc N/running/aborted, Notiz — „aborted" = der Prozess
starb ohne Ende-Eintrag, das wahre Ende ist unbekannt). Die Seite lädt sich alle 60 s neu.

**Wochenplan:** die *installierte* Crontab (`crontab -l`; fällt auf
`deploy/crontab.txt` zurück und sagt es dazu) als Raster Mo–So × 0–24 h. Jeder
Block ist ein geplanter Start, seine Breite die gemessene Median-Dauer der
letzten 28 Tage (10 min, solange nichts gemessen ist), Vergangenes blasser, die
rote Linie ist jetzt. Darunter eine Liste der Überschneidungen dieser Woche —
zwischen gemessenen Cron-Jobs und geplanten Läufen. Der GPU-Wächter serialisiert
GPU-Jobs ohnehin: eine Überschneidung heißt Warten, nicht Bruch.

**Logbuch (`docs/ops/logbook.md`):** Ihr Protokoll- und Planungsheft,
versioniert im Repo, von der Seite gerendert. Ein Eintrag = eine Überschrift
`## <Datum> · <Art> · <Titel>` — Datum `YYYY-MM-DD` (optional `HH:MM`), für
Ideen ohne Termin `YYYY-MM`; Arten `change` (passiert), `plan` (mit Tag →
erscheint als gestrichelter Block im Wochenplan), `decision`, `idea`. Direkt
unter der Überschrift optional `duration: 3h` (`45m`, `2h30m`, `1d`) und
`gpu: local|bequiet`, dann Markdown. Im Editor schreiben, committen — die Seite
liest die Datei beim Aufruf; Reihenfolge sortiert sie selbst (neueste oben).

**Alarme:** der Sampler prüft nach jeder Messung die Regeln aus
`pipeline/ops_alerts.py`; die Schwellen stehen in **`ops_alerts.yaml`** im
Repo-Root und wirken ohne Code beim nächsten Minutentakt. Was gemeldet wird:
Platte unter 10 % frei (`/` mit Postgres schon unter 20 %), HDD über 50 °C /
SSD über 65 °C, SMART FAILED, NVMe-Verschleiß ≥ 90 % oder Reserve < 10 %,
Sektor-/Medienfehler-Zähler, die gegenüber der vorigen Messung **steigen**,
GPU über 88 °C, Grafikspeicher belegt ohne antwortenden llama-server und ohne
bekannten Job, mehr als 80 % der DB-Verbindungen, ein Job, der länger als das
Doppelte seines Medians läuft, ein Job über 6 h (gezählt wird nur ein Lauf,
dessen Prozess noch lebt — eine Zeile, deren Prozess ohne Ende-Eintrag starb,
schließt der Sampler binnen einer Minute selbst und die Seite zeigt sie als
„aborted"), ein Backlog, dessen
Tagesmaximum drei Tage in Folge steigt. **Eine Mail beim Auslösen, eine bei der
Entwarnung** (gleiche Adresse wie der Wächter), dazwischen Ruhe; offene Alarme
stehen als Banner oben auf `/trends/ops`, darunter aufklappbar die zuletzt
entwarnten. Ist der Sampler selbst tot, meldet das der Morgen-Wächter um 07:45
(„The ops sampler has stopped writing", mit den Kommandos zum Wiederbeleben).
Regeln von Hand prüfen, ohne zu schreiben:

```bash
.venv/bin/python -c "from pipeline import ops_alerts as a, ops_probe as p; s=p.take_sample(full=True); print([(f.kind,f.message) for r in a.evaluate(s, a._db_context(), a.load_thresholds()) for f in r.findings] or 'keine Befunde')"
psql catandary -c "select kind, key, message, raised_at, resolved_at from ops_alerts order by raised_at desc limit 20"
```

**Darunter: Sampler und Laufprotokoll.**

Grundlage des kommenden Ops-Dashboards `/trends/ops`: ein systemd-User-Timer
misst **jede Minute** und schreibt eine Zeile nach `ops_samples`. Läuft aus dem
main-Worktree wie alle Crons.

| Was | Woher |
|---|---|
| GPU lokal: Speicher, Last, Temperatur, Watt, geladenes Modell, haltender Job | `nvidia-smi`, `GET :8090/v1/models`, `data/llama-server.<job>.pid`, sonst `pgrep` gegen die Muster des Kollisionswächters |
| bequiet: erreichbar, im Fenster, Backend, geladenes Modell | nur die Modell-API (`REMOTE_EMBED_HOST`): llama.cpp `/health` + `/v1/models` **oder** Ollama `/api/ps` — der Wechsel auf llama.cpp ändert an der Messung nichts |
| CPU %, load1, RAM | `/proc/stat` (Delta zur Vorminute), `/proc/meminfo` |
| **alle Platten** (`nvme1n1` Lexar = System + Postgres, `sda` HDD = Backups, `sdb`, `nvme0n1` NTFS): Füllstand je Mount, Lese-/Schreib-Bytes/s, Beschäftigung %, Temperatur, SMART | `/sys/block`, `statvfs`, hwmon (NVMe ohne Root); SMART nur mit sudoers-Zeile (unten) |
| Postgres: Größe, Verbindungen/`max_connections`, Abfragen > 60 s | Systemkatalog |
| **nur alle 10 min** (`is_full = true`): Backlog, Review-Queue (Drafts ≥ 0,85), 8 größte Tabellen, SMART | `get_unprocessed_entries` (~2 s) u. a.; dieselbe Messung löscht Zeilen älter als 7 Tage |

```bash
systemctl --user status catandary-ops-sampler.timer      # läuft er?
journalctl --user -u catandary-ops-sampler -n 20          # letzte Läufe
.venv/bin/python -m scripts.ops_sampler --print           # eine Messung ansehen (schreibt nichts)
.venv/bin/python -m scripts.ops_sampler --print --full    # inkl. teurer Zählungen + SMART
psql catandary -c "select ts, gpu_mem_used_mib, gpu_job, cpu_pct, db_size_bytes from ops_samples order by ts desc limit 5"
```

**Installieren / nach Änderung neu laden** (Units liegen in `deploy/systemd/`):

```bash
ln -sf ~/projects/catandary-trends/deploy/systemd/catandary-ops-sampler.service ~/.config/systemd/user/
ln -sf ~/projects/catandary-trends/deploy/systemd/catandary-ops-sampler.timer   ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now catandary-ops-sampler.timer
```

**SMART freischalten (einzige Root-Aktion, optional):** `sudo apt install
smartmontools`, dann `sudo install -m 0440 deploy/sudoers/catandary-smart
/etc/sudoers.d/catandary-smart && sudo visudo -c`. Erlaubt genau einen
Lesebefehl (`smartctl -j -n standby -A -H /dev/*`, weckt schlafende Platten
nicht). Bis dahin bleibt `smart` in der Zeile leer, alles andere läuft.

Kosten: ~2 s je Messung (davon 2 s Timeout, wenn bequiet aus ist), ~4 s bei
einer vollen; Tabelle ~10.000 Zeilen Bestand.

**Laufprotokoll `ops_events` (Stufe 2):** jeder Lauf eines Cron-Wrappers oder
Workers ist eine Zeile — Job, Start, Ende, Exit-Code, Notiz (z. B.
`batch=3000`, `gpu_done=3 gpu_skipped=0`, `gpu=remote http://…`, `blocked:
fremder GPU-Job`). Das ist das Langzeit-Gedächtnis für „wie lang dauert der
Samstag wirklich" — es wird nicht gelöscht.

```bash
.venv/bin/python -m pipeline.ops_events open                 # was läuft gerade (Start ohne Ende)?
psql catandary -c "select job, started_at, ended_at - started_at as dauer, rc, note from ops_events order by started_at desc limit 20"
```

Ein Lauf **ohne** `ended_at` und ohne laufenden Prozess ist abgebrochen (kill,
Stromausfall) — genau diese Information soll stehen bleiben. Schreiber sind
die zehn Shell-Wrapper (`scripts/lib/ops_events.sh`, zwei Zeilen je Wrapper)
und die Python-Crons/Worker (`with record("<job>")` um `main()`); ein von Hand
gestarteter Wrapper zählt genauso. Das Protokoll verhindert nie einen Lauf:
ist die DB nicht erreichbar, steht `[ops_events] WARN` im Log und der Job
läuft weiter. Die Seite `/trends/ops`, das Logbuch `docs/ops/logbook.md` und
die Alarme (`ops_alerts`) sind seit 2026-09-11 live — Details in §11.9.

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
  `CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology)` (V2 seit 11.09.: die Mailadresse
  steht auf der Methodik-Seite unter „Our crawler", nicht mehr in jedem Log),
  ≤ 1 Request/s/Host, Volltext nur bei `fulltext: true`, Aufbewahrung 60 Monate)
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
  (0600) — nie committen. Der Firecrawl-Key aus der Git-Historie (`4c0b116`) ist am **2026-09-06 widerrufen** — nicht rotiert: der Firecrawl-Backfill ist seit 2026-06 durch WP-API/OpenAlex abgelöst, es gibt keinen Cron und keinen Aufrufer im Betrieb. `FIRECRAWL_API_KEY` ist aus `.env` entfernt; `scripts/backfill_sources.py --mode deep` und `scripts/deep_uncapped_measure.py` tragen den Hinweis im Kopf und brechen mit klarer Meldung ab. Der Brave-Key bleibt: ihn braucht der Korpus-Rechercheur (`scripts/corpus_research.py`).

### KI-Kennzeichnung der Artikel (#99)

**Was steht wo.** Jede Artikelseite `/trends/<slug>` trägt seit 06.09. direkt
unter Titel und Meta-Zeile — noch über dem Anriss, nicht im Fuß — ein kleines
Kennzeichen:

> **AI-GENERATED / NOT REVIEWED BY A PERSON** ▸

Aufgeklappt (ein Klick, funktioniert auch ohne JavaScript und im statischen
Export) steht darin der volle Satz:

> This article was generated by a local language model from the single source
> linked below, checked automatically against that source, and published
> without a person reading it beforehand.

**Warum beim Feed nötig.** Art. 50 Abs. 4 EU AI Act verlangt die Kennzeichnung
für KI-erzeugte Texte zu Angelegenheiten von öffentlichem Interesse, wenn sie
**ohne menschliche Kontrolle** veröffentlicht werden. Genau das ist der Feed:
Der Artikel entsteht in Stufe 6 aus einer Quelle, und was danach über die
Veröffentlichung entscheidet, sind Maschinen — Grounding-Gate, Garbage-/
Truncation-Prüfung, Dedup, Auto-Publish ab Confidence 0,85 und der Draft-
Richter, der selbst ein Modell ist. Niemand liest die Artikel vorher. Die
Kennzeichnung steht deshalb unabhängig vom noch laufenden Anwaltsergebnis; die
von der EU-Kommission angebotenen Icons sind ausdrücklich fakultativ und werden
nicht verwendet (nachrüstbar, ohne dass sich sonst etwas ändert).

**Warum beim Newsletter nicht dieselbe.** Dort greift seit 06.09. die
Freigabepflicht (§7.5): keine Ausgabe geht raus, die nicht ein Mensch gelesen
und verantwortet hat. Der Hinweissatz der Ausgabe endet folgerichtig auf
„reviewed and released by a person" — die Aussage, die der Artikel gerade nicht
treffen darf. Zwei Produkte, zwei Sätze; sie stehen zusammen in
`frontend/src/lib/aiDisclosure.ts` und werden von Tests gegeneinander gehalten.

**Auf `/analysis` steht keine Kennzeichnung** — die Analysen schreibt der Owner
selbst.

**Wenn sich der Ablauf ändert.** Der Satz ist wörtlich an den Ablauf gebunden.
Käme je eine menschliche Durchsicht vor die Veröffentlichung, wäre der letzte
Halbsatz falsch und müsste weg; entfielen die automatischen Gates, der mittlere.
Formulierung nur zusammen mit dem, was sie beschreibt, ändern.

**Maschinenlesbar.** Einen verbindlichen Standard für „dieser Text ist
KI-erzeugt" gibt es nicht (`<meta name="ai-generated">` ist ein Vorschlag,
schema.org kennt keine KI-Provenienz, C2PA signiert Mediendateien). Gesetzt ist
deshalb pragmatisch: `<meta name="generator">` mit der Pipeline, und im
Article-JSON-LD `creator` = `SoftwareApplication` (mit demselben Satz als
Beschreibung) neben `author` = Organisation Catandary — verantwortlich bleibt
der Herausgeber — sowie `isBasedOn` = die Quell-URL.

**Selbst prüfen.**
```bash
curl -s http://localhost:3001/trends/<slug> | grep -c 'This article was generated'   # → 1
curl -s http://localhost:3001/trends/<slug> | grep -o '<meta name="generator"[^>]*>'
```
Im Export gilt: so viele Artikelseiten mit dem Satz wie `articles` in
`out.build_info.json` (zuletzt 16.925 von 16.925).
