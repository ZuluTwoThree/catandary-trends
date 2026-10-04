# Owner-Handbuch — Bedienung der Catandary-Trends-App

Stand 2026-09-05, verifiziert gegen Code, `crontab -l` und die laufenden
Instanzen (`:3001`, `:3004`, `:3999`, `:8090`, `:8098`). Kurzfassung und
Setup: [`README.md`](../README.md). Architektur-Vertrag: [`CLAUDE.md`](../CLAUDE.md).

**Lesehinweise.** „Owner-Instanz" = `http://localhost:3001` (main) bzw.
`:3004` (dev). Alle `python`-Aufrufe meinen `.venv/bin/python` im Repo-Root;
Cron und Wächter laufen aus dem **main-Worktree** `~/projects/catandary-trends`
(dort liegen auch `data/*_last.json` und die Logs zeigen dorthin). GPU-Regel für
alles, was ein Modell braucht: **nicht parallel** zum 02:45-Full-Cycle, zum
Samstags-Ingester oder zu einem laufenden Research-Pulse-Lauf —
jedes Werkzeug übernimmt `:8090` exklusiv und stellt danach den Ruhezustand
wieder her.

## Inhalt

1. [Morgenroutine](#1-morgenroutine--was-nachts-passiert-und-was-morgens-zu-tun-ist)
2. [Trend-Feed, Artikelseite, Suche und Filter](#2-trend-feed-artikelseite-suche-und-filter)
3. [Review-Seite](#3-review-seite-trendsreview)
4. [Mega Signal Themes und Methodik-Seite](#4-mega-signal-themes-und-methodik-seite)
5. [Foresight-Cockpit](#5-foresight-cockpit-trendsforesight)
6. [Dossier-Desk — entfernt 2026-09-19](#6-dossier-desk--entfernt-2026-09-19)
7. [Newsletter](#7-newsletter)
8. [Analysen](#8-analysen-analysis)
9. [Statischer Export](#9-statischer-export--die-öffentliche-website)
10. [Quellen verwalten](#10-quellen-verwalten)
11. [Betrieb](#11-betrieb-cron-wächter-backup-gpu-logs)
12. [Sicherheit und Recht](#12-sicherheit-und-recht-kurz)

---

## 1. Morgenroutine — was nachts passiert und was morgens zu tun ist

**Nachts (Mo–Fr, automatisch; seit 22.09. 1 h 15 min früher, damit der Lauf beim Frühstück fertig ist).** 01:30 Postgres-Backup · 02:15 Volltext-Retention
(`raw_content` älter 60 Monate → NULL) · **02:45 Full Cycle** (`scripts/full_cycle_cron.sh`
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

Der Sonntagslauf hat zwei Schritte: Mega-Kandidaten suchen (schreibt
`mega_discovery.candidate.yaml`, macht den Arbeitsbaum also „dirty" — das ist
normal) und, wenn `mega_trends.yaml` neuer ist als `models/distill/meta.json`,
die Distill-Heads neu trainieren. Ob beides durchlief, steht in
`~/logs/catandary-discovery-loop.log` (`discovery rc=…`, `retrain rc=…`) und als
Lauf-Zeile auf `/trends/ops`. **Endet der Lauf mit `rc != 0`, kommt seit dem
26.09. eine Alarm-Mail** (Regel `job_failed`, §11.9) — vorher fiel das drei
Sonntage lang nicht auf: der Retrain wurde bei 56 GB Speicher abgeschossen und
die Heads blieben auf dem Stand vom 07.08. Retrain von Hand, wenn nötig:

```bash
cd ~/projects/catandary-trends
.venv/bin/python scripts/train_distill_heads.py          # alle Zeilen, 1024 Dim
.venv/bin/python scripts/train_distill_heads.py --sample 250000   # schnell
```

Der Mega-Kopf wird dabei mit `class_weight='balanced'` trainiert (Entscheidung vom
26.09.): kleine Themen werden dadurch überhaupt erst zugewiesen — `virtual_worlds_
consolidation` ging von Recall 0,000 auf 0,793, `evolution_of_work_models` von 0,014
auf 0,928 —, dafür sinkt die Gesamtgenauigkeit um 3,6 Punkte, vor allem in den
größten Klassen. `--mega-class-weight none` stellt das alte Verhalten her. Die
Abstain-Schwelle (wann ein Signal *keinen* Mega-Trend bekommt) rechnet der Lauf
selbst aus und legt sie zum Modell; sie darf nicht von Hand in
`pipeline/distill.py` gesetzt werden, weil sie an Dimension und Gewichtung hängt.

Der Lauf sagt vorher, wieviel Speicher er schätzt, und bricht ab, statt sich
abschießen zu lassen. `--dim 4096` trainiert auf dem vollen Vektor — das passt
auf dieser Maschine nur mit `--sample`. Die Modelle liegen in `models/`, das
**pro Worktree** existiert und nicht in git ist: nach einem Retrain in `ct-dev`
gehören sie nach `~/projects/catandary-trends/models/distill/` kopiert, sonst
arbeitet der Nachtlauf mit den alten.

---

## 2. Trend-Feed, Artikelseite, Suche und Filter

**Wozu.** Der Feed ist das redaktionelle Produkt: die publizierten Artikel
(`trends.status = 'published'`), je ~100 Wörter Englisch, mit Quellennennung
und Backlink. Lokal sieht der Owner den gesamten Korpus (Zehntausende Artikel),
öffentlich nur die letzten 14 Tage (bis 02.10.2026: 30).

**Wo.** `/trends` (Feed), `/trends/<slug>` (Artikel), `/trends?q=<Suche>`,
`/trends?v=<VERTIKALE>`. `/trends/vertical/<v>` leitet auf `/trends?v=` um.

**Bedienung.**
- Filter-Bar über dem Grid: Suchfeld (`?q=`; Postgres-Volltextsuche mit
  `websearch_to_tsquery`-Semantik — Phrasen in Anführungszeichen, `OR`,
  `-ausschluss`), Vertikale (Mehrfachauswahl), PESTEL, Mega-Theme-Chips,
  Zeitraum, Score-Regler, Signaltyp, Sortierung, Quellen-Ausschluss,
  Listen-/Karten-Ansicht; aktive Filter erscheinen als Chips und lassen sich
  einzeln entfernen.
- Signaltyp (seit 2026-09-25 auch auf der Karte, links neben der Quelle, und
  als Chip-Gruppe „Signal" in der Suche des statischen Exports, Hash
  `#signal=regulation,partnership`): Product launch / Partnership / Regulation /
  Consumer behavior / Market shift / Funding / Research / Patent. **Achtung:**
  Artikel vom 14.07. bis 25.09. trugen für Presse durchweg `market_shift`;
  am 25.09. per Head nachgelabelt (§11.11), 31.684 blieben market_shift, weil
  der Head dort unter der Konfidenz-Schwelle lag.
- Die Hybrid-Suche (FTS + pgvector-ANN, RRF-Fusion) steht zusätzlich als API
  bereit: `/api/search?q=…&vertical=FOOD&limit=20`. Sie trägt auch das Suchfeld
  des Foresight-Cockpits. **Den Suchvektor rechnet der CPU-Embedder auf `:8091`**
  (`catandary-embed-cpu`, dasselbe Qwen3-Embedding-8B wie die Pipeline; Adresse
  über `RESEARCH_EMBED_HOST`). Bis zum 28.09.2026 fragte die Route Ollama auf
  `:11434` — dort läuft seit der Umstellung auf llama.cpp nichts, die Semantik fiel
  still weg und das Cockpit zeigte „(text match only)". Steht das wieder da: ist
  `catandary-embed-cpu` aktiv (`systemctl --user status catandary-embed-cpu`)?
  Die Antwort nennt es in `meta.embedding_available`; gemessen 28.09.:
  `solar panel` 60 Text- + 60 Vektortreffer in 0,6 s, `Pflanzenkäse aus Cashew`
  0 Text-, 18 reine Vektortreffer.
- Artikelseite: Titel, Body, Vertikal- und PESTEL-Badges, Mega-Theme, Score,
  Quelle mit Backlink, verwandte Artikel. Ist die Quell-URL nachweislich tot
  (`dead_links`, monatlicher Link-Check), zeigt die Seite einen Hinweis und den
  Archiv-Link statt des toten Backlinks.
- „Also reported by" (#109, seit 2026-09-25): berichten mehrere Quellen
  dieselbe Meldung (gleiche Marke, 48 h, Kosinus ≥ 0,80), listet die
  Artikelseite die anderen Berichte mit Quelle und Link; der älteste ist als
  „first report" markiert. Gruppen rechnet `scripts/group_stories.py`
  (§11.12); ohne Lauf fehlt der Abschnitt einfach.
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
  scripts/scheduled_cycle.sh 1500` (nur mit ≥ 6 h Luft zum 02:45-Lauf,
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

**Was er liest (seit 24.09.2026).** 12.000 Zeichen Quelle plus die
Extraktionsfelder — dieselbe Grundlage, aus der Stage 6 geschrieben hat. Bis
dahin sah er nur die ersten 4.000 Zeichen und damit weniger als der Schreiber,
weshalb Zahlen und Namen aus dem hinteren Teil langer Artikel als erfunden
galten („source_mismatch"). An einer Stichprobe von 25 gehaltenen Entwürfen
waren 5 von 10 solchen Urteilen aus genau diesem Grund falsch.

**Eine Kohorte noch einmal beurteilen lassen.** Normalerweise wird jeder
Entwurf genau einmal beurteilt. Nach einer Änderung daran, *was* der Richter
liest, lohnt ein Nachlauf — der muss ausdrücklich angefordert werden:

```bash
.venv/bin/python -m pipeline.draft_judge \
    --since-hours 720 --limit 2000 --rejudge --min-source-chars 4000 [--dry-run]
```

`--rejudge` nimmt auch schon gestempelte Zeilen, `--min-source-chars` grenzt auf
die ein, die eine solche Änderung überhaupt bewegen kann. Die Zahlen landen in
`data/draft_judge_rejudge.json`, nicht in der Datei der Morgen-Mail. Rechnen Sie
mit gut 3 Sekunden je Entwurf. Vorher prüfen, dass kein Nachtlauf aktiv ist
(`pgrep -f scheduled_cycle.sh`) — der Richter braucht die GPU allein.

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

### 3.x Review-Agent: Äquivalenz-Prüfung der Zahlen-Holds (Test, seit 2026-09-22)

**Befund (Owner 22.09.):** die meisten Holds „Zahl nicht in der Quelle" sind keine
Erfindungen, sondern andere Ausdrucksformen — „1 000 kilometres" gegen „1,000",
„23 heures" gegen „11:00 PM", „31.12.2025" gegen „December 31, 2025", „Seventy percent"
gegen „70%", „6,100万人" gegen „61 million". Das Gate vergleicht Token, ein Mensch
vergleicht Bedeutung.

`scripts/review_agent.py` macht den Bedeutungsvergleich mit dem geladenen Modell auf
`:8090`, aber mit **Beleg-Zwang**: für jede beanstandete Zahl muss das Modell ein
wörtliches Zitat aus der Quelle liefern; das Zitat wird gegen den Quelltext geprüft
(Whitespace/Anführungszeichen/Groß-Klein normalisiert). Fehlt es dort, gilt die Zahl
als nicht belegt — egal, was das Modell behauptet. Personennamen-Holds entscheidet
der Agent nie (Formregel „refer to people exactly as the source does"), Garbage und
abgeschnittene Bodies auch nicht; die bleiben bei dir.

```bash
.venv/bin/python scripts/review_agent.py            # Dry-Run über die ganze Warteschlange (~2,5 min für 180)
.venv/bin/python scripts/review_agent.py --limit 20 # nur die jüngsten 20
.venv/bin/python scripts/review_agent.py --ids 1794582,1794534
.venv/bin/python scripts/review_agent.py --apply    # äquivalente Drafts veröffentlichen
```

Ausgabe: Tabelle (Entscheid `equivalent` / `human` mit Begründung und Beleg) und
`data/review_agent_last.json` (je Draft jede Zahl mit Satz, Beleg, Form, Grund).
`--apply` setzt äquivalente Drafts auf `published` mit `review_reason =
'agent:equivalent: <Zahl> = "<Beleg>" (<Form>) …'` — nachvollziehbar in der DB; kein
Reject, nichts wird verworfen. Braucht den llama-server auf `:8090` (nimmt das
geladene Modell; nicht während des Nachtlaufs starten).

**Namens-Holds (seit 22.09. abends).** Derselbe Beleg-Zwang, aber die Entscheidung
fällt deterministisch an den Namensteilen; das Modell liefert Beleg, Quellform und
ein Veto. Titel gehören nicht zur Identität („Chinese Vice Premier He Lifeng" =
Quelle „Vize-Ministerpräsident He Lifeng"), der Nachname muss als eigenes Wort in
der Quelle stehen, Vorname und Titel dürfen einen Tippfehler Abstand haben (Quelle
„Urlula", Artikel „Ursula"). Andere Schriften klärt ein **zweiter, blinder
Durchgang**: das Modell romanisiert nur die Quellform, ohne den Artikelnamen zu
sehen — trifft die Romanisierung den Nachnamen, ist es dieselbe Person.

| Klasse | Bedeutung | Folge |
|---|---|---|
| `named` | alle Namensteile stehen in der Quelle (Gate stolperte über Tippfehler/Kompositum) | veröffentlicht |
| `translit_confirmed` | andere Schrift, Romanisierung passt (加藤 久明 → „Katō Hisaaki") | veröffentlicht |
| `surname_only` | Quelle nennt nur den Nachnamen, der Artikel ergänzt den Vornamen | bleibt — „Write again" |
| `role_only` | Quelle nennt nur eine Rolle, der Name kommt aus dem Modellwissen | bleibt — **der gefährliche Fall** |
| `absent` | Person kommt in der Quelle nicht vor | bleibt |
| `misspelled` | Nachname weicht von der Quelle ab (Artikel-Defekt) | bleibt |
| `translit` | Romanisierung passt nicht zum Artikelnamen | bleibt |

Gemessen am Bestand 22.09. (65 Namen in 83 Drafts): 16 nur andere Schrift, 17
ergänzter Vorname, 16 gar nicht in der Quelle, 6 falsch geschrieben, 4 aus der
Rolle erfunden — darunter „the Foreign Secretary" → David Lammy und ein Artikel,
der den Nestlé-Chef „Mark Schneider" nannte, während die (ukrainische) Quelle
Філіп Навратіль nennt. Genau diese Fälle bleiben bei dir.

**Reparatur (Stufe 1, seit 22.09. abends).** Einen Befund korrigiert der Agent
selbst: den **ergänzten Vornamen**. Er setzt die Quellform im ganzen Body ein
(„Kemi Badenoch stated" → „Badenoch stated", „Satella Nadella" → „Satya Nadella")
und lässt danach **dieselben Gates** laufen wie das Auto-Publish — nur wenn alle
grün sind, wird veröffentlicht (`review_reason = 'agent:repair: Kemi Badenoch →
Badenoch (surname_only)'`). Zwei Schutzregeln aus der Messung: die Quellform muss
namensförmig sein (ein Repo-Handle „arnegiacomo" wird abgelehnt) und den Nachnamen
behalten („Dario Amodei" → „Dario" wäre kein Name mehr). `--no-repair` schaltet
die Stufe ab.

**Bewusst nicht automatisch:** abweichende **Schreibweisen**. Gemessen an vier
echten Fällen wäre der Tausch zweimal richtig gewesen (Papfuss → Papenfuss,
Kokotjalo → Kokotajlo) und zweimal falsch — einmal hätte er einen Tippfehler der
Quelle übernommen („Xi Jinping" → „Xi Jiping"). Welche Seite richtig schreibt,
ist ohne Weltwissen nicht zu entscheiden, und Weltwissen soll hier nicht
entscheiden. Diese Fälle und die Satzstreichungen (Zahl/Person nicht gedeckt)
stehen als **Vorschläge** unter der Tabelle und im Bericht (`proposals`).

**Wenn Stage 11 ausfällt, sagt es der Wächter (seit 23.09.).** Der Wrapper meldet
nur seinen eigenen Exit-Code; die Bilanz der einzelnen Stages steht in der
end-Zeile des inneren Logs (`scheduled_cycle.sh end … (rc1=0 rc2=0 rc3=0
agent=0)`). Der Morgen-Wächter liest sie jetzt und schickt eine Mail, sobald ein
Wert ≠ 0 ist — mit den letzten Logzeilen, also z. B. dem Traceback. `agent=-`
(Stage abgeschaltet oder übersprungen) ist kein Defekt. Anlass: am 23.09. stürzte
Stage 11 in der ersten Zeile ab, der Cycle endete trotzdem mit rc=0 und der
Ausfall fiel erst beim Nachfragen auf.

**Im Nachtlauf (Stage 11, seit 22.09.).** Der Agent läuft automatisch nach dem
Draft-Richter: `scripts/review_agent.py --handover --apply`. Er hängt sich den
llama-server selbst auf das Content-Gen-Modell um und stellt den Ruhezustand
danach wieder her; ein eigener Kollisionswächter lässt ihn aus, wenn ein fremder
GPU-Job läuft. Die Zahlen stehen am Morgen in der Mail („Review agent (stage 11):
65 held drafts checked, 0 equivalent, 15 repaired, 50 left for you — 15
published. Names left for you: role_only=4, surname_only=17, …"). Abschalten:
`REVIEW_AGENT=0`; nur prüfen ohne zu schreiben: `REVIEW_AGENT_APPLY=0`.

**Im Review-Desk sichtbar (seit 22.09. abends).** `/trends/review` zeigt unter
jeder Karte einen Block **„Agent check"** mit dem, was der letzte Lauf gefunden
hat: je Name die Klasse im Klartext („source gives only a role — the name comes
from the model, not the source"), die Schreibweise der Quelle, bei anderen
Schriften die Romanisierung; je Zahl der wörtliche Quellbeleg oder der Grund,
warum sie nicht gedeckt ist. Darüber steht, wie alt der Bericht ist („Agent check
from 3 h ago") und wie man ihn erneuert. Läuft der Agent nie, fehlt der Block —
die Seite funktioniert wie zuvor.

**Ein-Klick-Vorschläge.** Wo der Agent etwas vorschlägt, steht ein Knopf:
*Use the source's spelling: Kerstin Papfuss → Kerstin Papenfuss* oder *Drop that
sentence: David Lammy*. Ein Klick wendet die Änderung an und lässt **dieselben
Gates** laufen wie das Auto-Publish; nur wenn alle grün sind, wird der Artikel
mit dem korrigierten Text veröffentlicht (`review_reason = 'desk:agent-proposal'`).
Objektiert ein Gate, bleibt der Artikel unverändert stehen und die Karte bleibt.

Sicherheit: der Browser schickt nur die Trend-ID und den **Index** des
Vorschlags; welchen Text der Knopf einsetzt, liest die Server-Action frisch aus
`data/review_agent_last.json`. Ein veralteter Tab oder ein gefälschter POST kann
damit keinen beliebigen Text in einen Artikel schreiben. Ist der Bericht
inzwischen ein anderer, passiert nichts.

**Ein Publish von Hand ist endgültig (Owner-Regel 22.09.).** Drückst du
*Publish*, ist der Artikel veröffentlicht — auch wenn ein Prüfer weiter
widerspricht und auch wenn du einen Agent-Vorschlag NICHT angewendet hast. Der
Einwand kann schlicht falsch sein: das Namens-Gate beanstandete „Per Second",
herausgeschnitten aus „Tokens Per Second (TPS)"; im Kontext war nichts zu
reparieren. Technisch: jede Handentscheidung stempelt `reviewed_at` — und nur
sie: der Draft-Richter setzt die Marke seit 25.09. nicht mehr (bis dahin galten
seine Freigaben als Handentscheidung und wurden nie nachgeprüft; Bestand mit
`scripts/reset_judge_reviewed_at.py` bereinigt), und
`scripts/recheck_published_grounding.py` überspringt solche Zeilen (zweifach —
in der Auswahl und im UPDATE). `--include-reviewed` öffnet sie wieder, wenn du
bewusst einen Altbestand prüfen willst. Auch der Review-Agent und Stage 9 fassen
sie nicht an. Gepinnt in `tests/test_human_publish_is_final.py`.

**Erstlauf 22.09. (Dry-Run, 183 Holds, Gemma-4-26B):** 100 äquivalent, 83 bleiben —
davon 62 Namens-Holds, 20 Zahlen ohne Beleg, 1 garbled. Von den 120 Drafts mit
reinen Zahlen-Holds waren 100 (83 %) vollständig belegt; Formen: 41 gleicher Wert
(Gate-Tokenisierung), 24 Zahlwort, 12 Übersetzung, 12 Spanne, 11 Datum, 11 Rundung.
Noch kein Cron — Owner-Entscheid nach Sichtung des Berichts.

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
*Cockpit · Clusters · Emerging · Technology · Lead Time · Evolution*;
Research Explorer, Research Pulse, Patent Explorer und Startup Explorer
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
hing. Seither laufen alle Desk-Jobs (Pulse, Snapshot) in einem
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

Dieselben Nester räumlich und über die Zeit: §5.12 (`/trends/foresight/map`) — sie liest genau diesen Schnappschuss.

### 5.4a Frei wählbare Domänen (`/trends/foresight/emerging?domain=<k>`)

Nester nicht nur je Vertikale oder Ebene, sondern in einer **selbst definierten Domäne** —
Wireless, Robotics, Elektromobilität, oder was immer du in `domains.yaml` einträgst. Ein
Signal gehört zur Domäne, wenn **sein Embedding** es sagt, nicht das Vertikal-Etikett der
Pipeline: eine kleine Sonde, trainiert auf Saat, die nicht von unseren Klassifikatoren stammt.

**Neue Domäne anlegen** (Eintrag in `domains.yaml`, Repo-Wurzel):

```yaml
wireless:
  name: Wireless communication
  seeds:
    cpc: [H04W, H04B7, H01Q]                 # Präfixe der Prüfer-CPC
    openalex_topics: [Advanced MIMO Systems Optimization]
    openalex_subfields: []
    phrases: ['"5G"', '"6G"', '"Open RAN"']  # Volltext, "…" = Phrase
  target_recall: 0.7                         # Anteil der Saat, den die Schwelle je Ebene behält
```

Je mehr Ebenen die Saat erreicht, desto besser überträgt die Sonde: CPC erreicht Patente,
OpenAlex die Forschung, Phrasen auch die Presse.

```bash
.venv/bin/python -m pipeline.domains train wireless --measure    # ~1 min: Sonde, Schwellen je Ebene, Mitglieder in 90 Tagen, Stichproben
.venv/bin/python -m pipeline.emerging_snapshot --scope domain:wireless   # Nester in der Domäne (~7 min, Benennung auf der GPU)
.venv/bin/python -m pipeline.domains list
```

**Lesen:** `train --measure` nennt je Ebene Schwelle, Saat-Recall und die Fehltreffer-Rate
auf dem Zufallshintergrund (eine Obergrenze — der Hintergrund ist unbeschriftet) und zeigt
Stichproben „in" und „knapp darunter". Stimmen die Stichproben nicht, die Saat schärfen
(engere CPC-Präfixe, eindeutigere Phrasen) und neu trainieren. Auf der Seite erscheint die
Domäne als Reiter unter „by domain"; der Knopf *Recompute pockets* rechnet alle trainierten
Domänen mit. **Vorsicht beim Alter:** Patent-Nester wirken jung, weil Patente im Signalraum
erst seit August 2026 (und für Food seit #114) vorliegen. Details und erste Messung:
`docs/domains_framework_2026-09-30.md`.

### 5.4b Live: Nester für einen freien Begriff (`/trends/foresight/discover`)

Für Begriffe, die du nicht vorher in `domains.yaml` anlegen willst oder kannst. Im
Foresight-Menü *Discover*, oder auf Emerging in der Zeile „by domain" *+ discover a term*.

1. **Begriff** eingeben, optional **andere Schreibweisen** (Komma-getrennt, z. B.
   `all-solid-state battery, SSB`), Fenster 6/12/24 Monate (Standard 12). *Select signals*.
2. Nach ~10 s steht die **Auswahl**: wie viele Signale in den letzten 12 Monaten und im
   ganzen Archiv, je Ebene, wie viel Prozent den Begriff wörtlich tragen, 14 Stichproben
   „Inside the selection" und 8 „Just outside". Passen die Stichproben nicht (zu breit,
   mehrdeutig), *Discard* und mit engerem Begriff oder anderen Schreibweisen neu.
3. *Find pockets*: nach einigen Sekunden die Nester, in Untergruppen, mit Namen vom
   ruhenden 8B (läuft gerade ein GPU-Job, bleiben die Schlagwort-Etiketten — einfach später
   *run again*). *Open the pockets →* zeigt sie auf Emerging wie jede andere Domäne.
4. Unten **Discovered domains**: jede gespeicherte freie Domäne mit *run again* und *delete*
   (löscht Sonde und Nester-Lauf).

**Kalender:** wenige Sekunden nach den Nestern kommt die Datierung gegen echte
Kalenderdaten dazu (Ergebnis-Box: „Dating them against research and patents …"). Jede
Karte zeigt dann oben **„on record since <Jahr>"** und den Block *On the record*:
Forschung (OpenAlex, ab 2010) und Patente (ab 1990) mit erstem Jahr, Take-off, Wachstum
der letzten drei Jahre und einer Kurve je Million Dokumente, darunter die gezählte Abfrage
im Wortlaut. „2010 oder früher" heißt: dort beginnt unser Forschungsbestand.

**Lesen:** ein Nest ist ein **Trend-Kandidat**, kein Urteil. Die Dichteprüfung ist relativ
zur Domäne (dichteste 40 % ihrer Zellen, je Ebene), der wörtliche Anteil sagt, wie sehr die
Auswahl am Begriff klebt (precision fermentation 19 %, digital twin 85 %). Das **Alter**
im Signalraum misst unsere Abdeckung (viele Nester „2026-07"); maßgeblich ist deshalb der
Kalender oben auf der Karte. Er ist eine Wortzählung — die Abfrage steht dabei.

**Dienst:** `pipeline/domain_service.py`, systemd-Unit `catandary-domain-service`
(127.0.0.1:8093, ~4 GB RAM, keine GPU). **Schalter oben auf der Seite** („Discovery
service"): *aus* stoppt den Dienst und gibt den Speicher frei, er bleibt auch nach einem
Neustart der Maschine aus (`disable --now`); *an* startet ihn (`enable --now`), nach
~6–10 s ist er bereit. Solange er aus ist, ist *Select signals* gesperrt; die
gespeicherten Domänen bleiben sichtbar.

```bash
systemctl --user status catandary-domain-service
journalctl --user -u catandary-domain-service -n 50
.venv/bin/python -m pipeline.domain_service --rebuild          # Vektor-Kopie neu aufbauen (~6 min)
.venv/bin/python -m pipeline.domain_service --once "batteries"  # ein Auftrag ohne Seite
```

Messungen, Stellschrauben und Grenzen: `docs/domains_framework_2026-09-30.md`, Abschnitt
„Live-Dienst".

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

**Cron (installiert 2026-09-18):** `0 12 * * 6 scripts/weekly_research_pulse.sh` rechnet
jeden Samstag die Vorwoche für alle 28 Themes (idempotent, Kollisionswächter; ~1 min).
Der Lauf meldet sich in der Montags-Morgen-Mail (Zeile „GPU cron weekly_research_pulse",
mit Woche, Themes, Texten); blocked oder failed erzwingt die Mail. Fehlt eine Woche
trotzdem (Rechner aus, Cron blockiert), von Hand nachholen:
`python scripts/research_pulse.py --week 2026-W36`. Vor dem 18.09. war die Zeile nur
ein Vorschlag — deshalb stand die Seite zwei Wochen auf W35.

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

### 5.11 Field Watch, Trajectory Sheet, Feldprobe (`scripts/field_watch.py`)

Die drei Produkte des Pivots vom 20.09.2026 (`docs/commercialization_plan_2026-09-20.md`):
**Trajectory Sheet** (ein Feld, 6 Seiten, 1.490 €), **Field Watch** (drei Felder,
Wochenblatt, 390 €/Monat) und die kostenlose **Feldprobe** (Seite 1 des Sheets).
Alles ist deterministische SQL-Messung — kein Sprachmodell schreibt ein Wort;
der einzige Prosa-Abschnitt (`reading:`) kommt von dir.

**Kundendatei anlegen** — `fields/<kunde>.yaml` (Vorlage `fields/example.yaml`;
echte Kunden sind per `.gitignore` vom Repo ausgenommen):

```yaml
customer: "Firma GmbH"
slug: firma
fields:
  - name: Präzisionsfermentation
    terms: [precision fermentation, recombinant whey, animal-free dairy]
    cpc: [C12P21/02, A23J3/08]      # Anker für den Reifegradblock (K(t), Zykluszeit)
    reading: ""                     # Einordnung im Sheet — nur wenn du sie schreibst
```

Feld = Suchphrasen (Titel/Teaser/Tags des Signalkorpus, Titel+Abstract des
Patentindex) + CPC-Anker. Das Mapping ist dein Checkpoint: Feldprobe rechnen,
Kandidatenklassen ansehen, Anker eintragen, Kunde gibt frei; es steht auf jedem Blatt.

**Kommandos** (alle aus dem Repo-Root, `.venv/bin/python`):

| Was | Kommando | Dauer |
|---|---|---|
| Feldprobe (Seite 1 + Anker-Vorschlag) | `scripts/field_watch.py --probe "precision fermentation" [--terms a,b] [--cpc C12P21/02] [--requester "Name"]` | ~10 s mit `--cpc`; ohne Anker fragt die Technologie-Suche nach Klassen (GPU-Handover, ~1 min) |
| Wochenblatt (Vorwoche) | `scripts/field_watch.py <kunde>` — `--week 2026-09-14` für eine bestimmte Woche | ~40 s je drei Felder |
| Trajectory Sheet eines Feldes | `scripts/field_watch.py <kunde> --sheet <feld-slug>` | ~20–40 s |
| Kundenseite bauen | `scripts/field_watch.py <kunde> --export` → `data/field_watch/<kunde>/site/` (index.html + PDFs) | Sekunden |
| alle Kunden (Cron) | `scripts/field_watch.py --all` | — |

Ausgabe: `data/field_watch/<kunde>/<woche>.{pdf,html,json}` bzw.
`sheet-<feld>-<datum>.*`; Feldproben unter `data/field_watch/probes/`. Jede
Erzeugung eine Zeile in `field_watch_runs` (Kunde, Art, Woche, Feld, Messung als
JSON, PDF-Pfad). `--sample` stempelt „Beispiel zur Demonstration" (die Muster in
`docs/samples/` und auf der Website unter `/trends/samples/` sind so entstanden:
`fields/example.yaml` Woche 38, `fields/example-lfp.yaml --sheet lfp`). `--no-pdf`
lässt das PDF weg; das PDF kommt aus dem Playwright-Chromium der Frontend-Tests
(`FIELD_WATCH_CHROME` überschreibt den Pfad).

**Lesen:** Wochenblatt = je Feld und Ebene diese Woche gegen den Median der vier
Vorwochen (grün ≥ +25 %, rot ≤ −25 %), 12 Quartale auf festem Quellenpanel,
Signale der Woche mit Quelle, neue Akteure, Nester, „Wo die Evidenz dünn ist".
Sheet = Auf einen Blick, Reifegrad-Karte (K(t) aus dem Patentgraph der Anker,
Zykluszeit, Zentralitäts-Peak), vier Ebenen 1990–heute (Wissenschaft ab 2010,
Markt ab 2020 in Breite), Quartale, Anmelder/CPC-Subklassen, meistzitierte
Werke/Patente, Nester, Einordnung (nur wenn `reading:` gesetzt), dünne Zellen,
Methodik. Die Regeln stehen öffentlich auf `/trends/methodology#field-method`.

**Kundenbereich:** `trends/clients/<kunde>/` auf dem Webspace, von Hand per SFTP
(Inhalt = `--export`-Ordner), `.htaccess`-Vorlagen in `deploy/webspace/`
(Basic Auth, `htpasswd -B` außerhalb des Webroots, noindex). Der Publisher fasst
`trends/clients/` nie an (`OWNER_SUBTREES`) — weder Upload noch Löschen, auch nicht
mit `--full` oder rsync.

**Cron (Vorschlag, scharf erst mit dem Merge nach `main`):** `30 12 * * 6
scripts/weekly_field_watch.sh` — Wochenblätter aller Kunden nach dem Research
Pulse; keine GPU, kein Kollisionswächter; ohne Kundendateien no-op; Notiz
`data/weekly_field_watch_last.json` in der Montags-Mail. Die Kundenseite wird
bewusst nicht automatisch hochgeladen — du sichtest das Blatt zuerst.

### 5.12 Signalraum in 3D (`/trends/foresight/map`)

Dieselben Nester wie §5.4, aber mit Koordinaten und einer Uhr. Erreichbar über das
**Foresight-Menü** in der Kopfzeile (Eintrag *Signal Space*, zwischen Emerging und
Technology) — also von jeder Cockpit-Seite aus, auch von Clusters und Emerging; auf
dem Handy in derselben Gruppe der Schublade. Die Seite rechnet **nichts** nach: sie liest den Emerging-Schnappschuss (Zentroid je Nest, dazu die
Treffer je Monat aus dem Archiv-Scan) und ergänzt nur das, was dort fehlte — drei
Achsen und einen Zeitregler. Gibt es für einen Bereich keinen Lauf, steht das da,
mit Verweis auf den Recompute-Knopf der Emerging-Seite.

**Zwei Ansichten, ein Umschalter oben links.**

*Messachsen* (Default) ist die ehrliche: waagerecht das **Alter** des Nests
(logarithmisch, Ticks bei 1/2/5/10/20 Jahren), senkrecht der **Anteil je 10.000
Signalen desselben Monats** über zwölf rollende Monate (logarithmisch), in die
Tiefe das **Wachstum** gegen die zwölf Monate davor (×0,25 bis ×4, Mitte „flat").
Die Punkte *bewegen* sich: ein Monatsschritt ist ein Schritt auf der Bahn, und die
Spur hinter jedem Nest zeigt das letzte Jahr. Die Kugelgröße ist der Anteil, mit
**einer** Skala für den ganzen Durchlauf — eine Skala je Bild ließe jeden Monat
gleich voll aussehen.

*Karte* ist die Orientierungshilfe: die 1024-dimensionalen Zentroide per
klassischem MDS auf drei Achsen gepresst. Hier steht die Position fest und nur die
Größe atmet. Die Achsen sind **absichtlich unbeschriftet** — sie haben keine
Einheit. Was die Projektion kostet, steht daneben: Shepard r, gehaltene Varianz und
wie viele der fünf nächsten Nachbarn Nachbarn bleiben. Gemessen am 27.09.: global
r 0,47 / 24 % / 47 %, `tier:science` r 0,73, `tier:market` r 0,64. Lies die Karte
danach: unter 0,6 ist nur die *Gruppierung* ablesbar, keine Abstände und erst recht
keine Richtungen. Eine lokale Nachoptimierung (Sammon) wurde gemessen und nicht
eingebaut — sie hob r auf 0,71–0,73, verschlechterte aber die Nachbarschaftstreue
bei einem von zwei Läufen (`docs/signal_space_2026-09-27.md`).

**Bedienung.** Ziehen dreht den Raum, `+`/`−` zoomen, *Reset view* stellt den
Blick zurück. *Spin* dreht langsam von selbst (das ist es, was die Tiefe überhaupt
sichtbar macht) und hält an, sobald du ziehst. *Play* läuft durch die Monate,
Pfeiltasten links/rechts gehen einen Monat weiter, der Regler springt direkt.
*Trails* schaltet die Spuren ab. Zeigen auf einen Punkt blendet seine Zahlen
rechts ein, Klicken hält sie fest.

**Was rechts steht** — und warum: Monat, Anteil (mit der rohen Trefferzahl
dahinter), Wachstum, Alter mit erstem Monat, Größe und Kohäsion des Nests,
Quellenzahl **mit der größten Quelle und ihrem Anteil**, wie viel des Nests je
eine Klassifizierungsstufe gesehen hat, und der Anteil etablierter Quellen. Liegt
letzterer unter 50 %, sagt ein Satz darunter, dass das Alter dieses Nests eher
etwas über unsere Abonnements aussagt als über die Welt. Darunter drei Belege mit
Quelle und Datum. Ein dichtes, brandneues Nest kann ein einzelner Massen-Ingest
sein — die Seite versteckt das nicht, sie zeigt es.

**Normalisierung.** Der Korpus wird für den Stand **des Laufs** rekonstruiert
(`trends.created_at <= Laufzeitpunkt`), nicht für heute: sonst sänke jedes Nest,
weil die jüngsten Monate seit dem Schnappschuss um Zehntausende Zeilen gewachsen
sind, die Nest-Treffer aber eingefroren sind. Der Rest (~0,02 %) sind Zeilen, deren
Publikationsdatum am Lauftag noch in der Zukunft lag; die Seite nennt ihn.

**Dritte Ansicht: *Signal cloud*** (seit 27.09.) zeigt nicht die Nester, sondern die
**Signale selbst**: 600 aus jedem der letzten 180 Monate, zusammen 108.000, per UMAP
in drei Dimensionen.

*Layout* (seit 28.09.) wählt zwischen zwei Anordnungen derselben Punkte:
**Topic** (Standard) rechnet vor der Projektion den typischen Schreibstil jeder Ebene
heraus (ihren Mittelvektor) — ein Thema aus Forschung, Patenten, Förderung und
Fachpresse liegt dann in einer Region; **Style** ist die Anordnung vom 27.09., in der
die Ebenen eigene Kontinente bilden. Gemessen (`docs/space_eval_2026-09-28.md`): die
Treffer eines Suchbegriffs sind in *Topic* zu 34 % statt 21 % untereinander nächste
Nachbarn, Forschung und Markt zum selben Thema liegen weniger als halb so weit
auseinander. Suche, *All signals*, Taschen und Filter funktionieren in beiden; beim
Umschalten wird eine laufende Suche in der neuen Anordnung neu platziert. Rechts
unten stehen die Treuewerte der gewählten Anordnung. Ein Lauf rechnet beide
(zuletzt 20 min, Spitze 4 GB); nur die alte: `python -m pipeline.signal_space
--layouts style`. Die Nester sitzen als Ringe in derselben Wolke; ein Klick auf
einen Ring lässt seine Mitglieder aufleuchten. Ein Klick auf einen Punkt öffnet rechts
Titel, Quelle, Datum, Ebene, Vertikale, Signaltyp und Nest — veröffentlichte Artikel
verlinken auf die Artikelseite, alle anderen auf die Quelle.

*Bedienung:* **Colour** färbt nach Ebene, Vertikale oder Nest. **Window** wählt, welche
Monate hell leuchten (3 Monate, 12 Monate, alle); der Regler schiebt das Fenster, *Play*
lässt es laufen. **Context** zeigt den Rest des Archivs als schwachen Schatten, damit die
Form lesbar bleibt. **Nests** blendet die Ringe aus und ein (Ausblenden hebt auch eine
gewählte Tasche auf, sonst bliebe ein Filter stehen, den man im Bild nicht mehr lösen
kann); zum Anwählen einer Tasche genügt ein Klick auf die Ringlinie; ein Zug, der auf
einem Ring beginnt, dreht oder verschiebt trotzdem. Die Chips unter *show* blenden Ebenen und Vertikalen ganz aus —
gefiltert wird, nicht neu projiziert, deshalb bleiben die Positionen vergleichbar. Die
Wolke ist immer global; auf einem anderen Tab steht ein Hinweis dazu.

*Navigation:* Ziehen dreht. **Shift-Ziehen oder rechte Maustaste** verschiebt das
Bild. Das **Mausrad** zoomt zum Cursor hin — der Punkt unter dem Cursor bleibt stehen.
**Doppelklick** auf ein Signal oder einen Ring macht ihn zur Bildmitte; Drehen und
Zoomen beziehen sich danach auf ihn. `+`/`−` zoomen um die Mitte, die Anzeige daneben
nennt den Faktor (×0,15 bis ×50 — die Grenze setzt die 16-Bit-Speicherung der
Koordinaten, darüber rasteten die Punkte sichtbar ein). *Reset view* stellt Blick,
Zoom und Mitte zurück. Punkte, die beim Verschieben hinter die Kamera geraten, werden
ausgeblendet statt gespiegelt gezeichnet.

*All signals* (seit 28.09., **Standard beim Öffnen** — abschalten zeigt die Stichprobe)
zeichnet statt der Stichprobe **alle 1,52 Mio. eingeordneten Signale** des Fensters (die Spalte `all_points` des Laufs, ~24 MB, einmal
geladen, danach schaltet der Knopf sofort hin und her). Die Form bleibt dieselbe — die
Stichprobe hat sie festgelegt —, aber die **Helligkeit ist jetzt Menge**: die Monate seit
dem Quellenausbau 2025/26 überstrahlen die frühen Jahre. Für „woraus bestand ein Monat"
zurück auf die Stichprobe. Punkte werden kleiner und blasser gezeichnet, Hover, Klick,
Tooltip, Nest-Filter und Suche funktionieren gleich (gemessen: 504.228 Punkte im
12-Monats-Fenster; ein Treffertest über alle 1,52 Mio. ~18 ms). Der Knopf ist grau, wenn ein Lauf nicht alle
Signale eingeordnet hat (Läufe vor dem 27.09. abends) — dann *Recompute cloud*.

*Tooltip:* Bleibt der Cursor etwa **eine Sekunde** auf einem Signal, erscheint sein
Titel mit Quelle und Datum; auf einer Ringlinie Name und Größe der Tasche. Solange der
Cursor über der Wolke ist, pausiert das Drehen — ein bewegtes Ziel ließe sich weder
lesen noch treffen.

*Suche:* Das Feld am Ende der Filterleiste durchsucht **den ganzen Bestand**, nicht
nur die 108.000 Punkte der Stichprobe — drei Quellen parallel: Titel, Zusammenfassung
und Tags (dieselbe Volltextsuche wie `?q=` im Feed), die **Abstracts der
Forschungssignale** und die **Abstracts der Patente**. Syntax überall gleich: `solar
panel` verlangt beide Wörter, `"solar panel"` die Phrase, `-wort` schließt aus. Jeder
Treffer erscheint als eigener Punkt, weil der Wolkenlauf seit dem 27.09. **alle
1,52 Mio. Signale des 15-Jahres-Fensters** in dieselbe Wolke einordnet (die Stichprobe
bestimmt die Form, der Rest wird per `umap.transform` eingesetzt; ein Stichprobenpunkt
behält dabei seine Position). Neben dem Feld steht die Trefferzahl, dahinter, wie viele
Treffer vor dem Fenster liegen (älter als 15 Jahre oder undatiert) — beim Zeigen auf
die Zahl die Aufteilung nach Quelle. Scheitert eine Quelle (Zeitlimit), steht
„partial — … timed out" daneben. Gemessen am 27.09.: `solar panel` 2.288 Treffer (vorher
nur die 112 der Stichprobe), `perovskite` 2.946, `battery` 19.214, `AI` 88.698 — 0,2 bis
1,1 s; auch bei 88.698 Treffern läuft die Animation mit 60 Bildern/s. Treffer werden
größer und kräftiger gezeichnet, je weniger es sind; die Stichprobe tritt als Schatten
zurück. Abstract-Treffer heißen „der Begriff kommt vor", nicht „darum geht es" — bei
Forschung oft als Methode oder Nebensatz. Eine **neue** Suche öffnet das Fenster auf
alle Monate; danach eingrenzen und mit *Play* zusehen, wann die Treffer auftauchen.
Leeren beendet die Suche.

*Suche nach Bedeutung* (seit 28.09.): der Schalter vor dem Feld wählt **Text** (die
Stichwortsuche oben), **Meaning** (Vektorsuche) oder **Both** (Standard). *Meaning* bettet
die Anfrage auf dem CPU-Embedder `:8091` ein und holt die **N nächsten Signale** über den
HNSW-Index auf `embedding_1024` (N = 250 / 500 / 1.000 — pgvector 0.6 liefert je Anfrage
höchstens 1.000; mehr ginge erst mit pgvector 0.8). Findet auch ohne gemeinsames Wort und
in jeder Sprache: `Pflanzenkäse aus Cashew` → 971 Signale in der Wolke (Text: 0),
`PV module recycling` → Recycling-Arbeiten, in denen „solar panel" nicht vorkommt.
**Wichtig:** die Vektorsuche liefert eine *Rangfolge*, keine Treffermenge — irgendetwas ist
immer „am nächsten", auch bei Unsinn. Deshalb stehen neben dem Feld die
Ähnlichkeitsspanne (z. B. `similarity 0.84–0.63`, nächster bis letzter Treffer; die Skala
schwankt von Anfrage zu Anfrage, also als Spanne lesen, nicht als Note), und die Treffer
verblassen mit ihrem Rang (der nächste voll, der letzte auf 20 %). In *Both* sind die
Treffer nach Herkunft gefärbt — **gelbgrün** = Text und Bedeutung, **weiß** = nur Text,
**cyan** = nur Bedeutung — mit den drei Zahlen daneben; in *Text* und *Meaning* bleibt die
Färbung nach Ebene/Vertikale. Tooltip und Detailfeld nennen je Punkt `match: text`,
`meaning 0.72` oder `text + meaning 0.72`. Gemessen 28.09.: `solar panel` in *Both* 106
beides / 2.186 nur Text / 825 nur Bedeutung; Antwort 0,3–1,3 s. Ist der Embedder weg,
steht „partial — meaning (embedder :8091 unreachable) failed" daneben und die Textsuche
läuft weiter.

*Lesart* (steht auch auf der Seite): jeder Monat hat gleich viele Punkte — **Helligkeit
zeigt, woraus ein Monat bestand, nie wie viel es gab**; Menge gehört auf die Messachsen.
UMAP hält Nachbarschaften, keine Abstände: gemessen am 27.09. ist die Trustworthiness
0,938 (was nah aussieht, ist nah), aber nur 24 % der zehn nächsten Nachbarn eines Signals
bleiben seine Nachbarn — für Regionen und Dichte taugt die Wolke, für „was liegt direkt
neben diesem Signal" nicht. Leere Flächen und Abstände zwischen fernen Regionen bedeuten
nichts. Sofort sichtbar ist, dass die Einbettung nach **Schreibstil** trennt: Fachpresse,
Forschung, Patente und Förderung liegen als eigene Kontinente, auch beim selben Thema.
Nur 2,2 % der Punkte liegen in einem Nest — die Nester sind dichte Ecken der letzten 90
Tage, die Wolke umfasst 15 Jahre.

*Neu rechnen:* Knopf **Recompute cloud** oben auf der Seite (kein Cron) oder
`.venv/bin/python -m pipeline.signal_space` (`--dry-run` zählt nur die Stichprobe,
`--per-month`, `--months`, `--sample-only` ohne das Einordnen aller Signale, `--layouts
style` nur die alte Anordnung). CPU, mit beiden Anordnungen rund 20 Minuten, Spitze ~4 GB
(das Einordnen der 1,4 Mio. übrigen Signale in beide sind ~17 davon; nur *Style* ~10 min,
2,8 GB). Die letzten zwei Läufe bleiben
in `signal_space_runs`. Die Nester kommen aus dem jüngsten *globalen* Emerging-Lauf — wer
die Nester neu rechnet, sollte danach auch die Wolke neu rechnen.

**Vergangenheit und Zitationsflüsse (seit 03.10.).** Liegt die Stichprobe der
Vergangenheit vor (§11.3b, `history_vectors`), nimmt die Wolke sie mit:
- **Stichprobe je Monat:** Die 600 Punkte je Monat werden aus `trends` **und** der
  Zufallsschicht gezogen. Vor 2023 stammen Patente und Forschung damit überwiegend aus
  der Stichprobe.
- **All signals:** Auch alle Vergangenheits-Dokumente des Fensters werden eingeordnet,
  einschließlich der zitierten Patente.
- **Schalter *Past sample*:** blendet diese Punkte aus und ein; die Anordnung bleibt
  dieselbe.
- **Klick auf einen Vergangenheitspunkt:** zeigt Titel, Datum und Link (Patent bzw.
  DOI), dazu die Schicht. Bei der Stichprobe steht dort, für wie viele Dokumente ihres
  Monats der Punkt steht; bei den zitierten Patenten „cited by a patent in the signal
  space".
- **Schalter *Citation flows*:** zieht Bögen von einem Nest zu dem Nest, dessen Patente
  es zitiert. Das neuere baut auf dem älteren auf; die Breite wächst mit der Wurzel der
  Zahl. Zitate innerhalb eines Nests werden nicht gezeichnet. Klick auf einen Ring
  zeigt nur seine Flüsse.
- **Woher die Zählung kommt:** jedes Patent, das in einem Nest liegt, ob aus `trends`
  oder aus der Stichprobe, nachgeschlagen in `patent_links`.
- **Aus der Vergangenheit lassen:** `--no-history`.
- **Reihenfolge nach neuen Vektoren:** erst *Recompute pockets*, denn der Archiv-Scan
  datiert die Nester dann auch gegen die Vergangenheit (Patente ab 1990, Forschung ab
  2010; `emerging_snapshot --no-history` schaltet das ab). Danach *Recompute cloud*.
- **Lesart:** Ein Vergangenheitspunkt steht für viele Dokumente seines Monats; Dichte
  vor 2023 heißt also Zusammensetzung, nicht Menge.

**Grenzen.** Gezeigt werden die letzten 180 Monate (15 Jahre); 24 weitere werden
nur geladen, um die rollenden Fenster zu füllen. Ältere Monate stehen im
Schnappschuss, ergeben aber bei wenigen hundert Signalen je Monat kein Bild. Die
Seite ist wie das ganze Cockpit Owner-only (im `PUBLIC_MODE` 404, nie im Export) —
deshalb darf sie interaktiv sein, wo die öffentlichen Seiten deterministisch sein
müssen.

## 6. Dossier-Desk — entfernt 2026-09-19

Der Scouting-Dossier-Desk `/trends/dossiers` (Korpus-Rechercheur, Messkette,
Checkpoint, Leser, Advisor) wurde am 2026-09-19 entfernt — Owner: „Das Feature
trägt nicht" (7 Versionen zu einem Thema, 48 Läufe, Leser nie zufrieden).
Historie und Messungen: `docs/agentic_dossiers.md`; Rückweg: Git-Tag
`archive/dossiers-2026-09-19`; Nachfolge-Idee „Field Watch":
`docs/value_proposition_field_watch_2026-09-19.md`, Issue #108. DB-Tabellen
bleiben stehen (kein DROP); die Route ist lokal wie im Export 404.

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
des 14-Tage-Fensters zeigen auf die Primärquelle), `/trends/newsletter/unsubscribed`.
Editions-URLs sind lokal 404 (dort gilt die Client-Seite).

### 7.3 Deep Dive of the Week — stillgelegt seit 2026-09-19 (#96)

**Was es war.** Rechercheur-gestützte Sektion zum stärksten Wochenthema, als
Dry-Run über den Auftragspfad der Scouting-Dossiers (27B-Rechercheur → Gate →
Gemma-Kondensat). Mit dem Rückbau der Dossiers (§6) gibt es den Rechercheur
nicht mehr.

**Was heute passiert.** Ist `NEWSLETTER_DEEP_DIVE=dry-run` in der Crontab gesetzt
(Default `off` — heute nicht gesetzt), läuft nach der Edition
`scripts/newsletter_deep_dive.py`: Themenwahl (SQL, deterministisch, Ranking
gespeichert) und dann hart `status: "disabled"`, `error: "dossier feature removed
2026-09-19"` in `newsletter_editions.deep_dive` — Edition unverändert, kein
Modell, keine GPU, Exit-Code 2 (`dd=2` in der end-Zeile, nie ein Blocker). Die
Dienstag-Morgen-Mail zeigt „disabled — researcher removed 2026-09-19".

**Wo der Owner es sieht.** Der gespeicherte Dry-Run W35 2026 (`gate_failed`)
rendert weiter als Block „Deep-Dive Dry-Run — not public" (Thema, Gate-Chips,
Audit, Kondensat-Vorschau; ohne Desk-Link). Öffentlich nur `gate_passed &&
!dry_run` — also nie.

**Terminal.**
```bash
python -m scripts.newsletter_deep_dive --year 2026 --week 35 --theme-only   # Ranking, kein Modell
python -m scripts.newsletter_deep_dive --year 2026 --week 35                # schreibt status "disabled"
```

Historie (Gates, Kalibrierung, drei Dry-Runs W35): `docs/newsletter_deep_dive.md`.

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
über git, kein Admin-UI). *(Bis 2026-09-19 landeten hier auch die
Deep-Dive-Drafts aus Abschnitt 7.3; der Schritt ist stillgelegt.)*

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

Env: `PUBLIC_WINDOW_DAYS` (14, bis 02.10.2026: 30), `PUBLIC_NOINDEX` (**1** bis zum Launch),
`PUBLIC_SITE_URL` (`https://catandary.de`), `KEEP_STAGING=1` (Debug). Das Skript
kopiert `frontend/` per rsync in `frontend/.export/site/` ohne alles aus
`frontend/static-export.exclude` (Foresight, Review, Ops, API, Proxy),
baut mit `STATIC_EXPORT=1 PUBLIC_MODE=1`, verifiziert (404/Index/Feed/Expired/
Sitemap, Artikel > 0, **kein** `"status":"draft"` im Payload, `index.json`
valide), kopiert die `.htaccess` aus `frontend/public-export/` hinein und
schreibt Manifest + `build_info.json`. Referenz 04.09.: 15 178 Artikel,
28 Mega-Seiten, 12 Editionen, 33 089 Dateien, 1,31 GB, 55 s Build. Zwei Läufe
nacheinander müssen `diff -rq`-leer sein (Determinismus-Gate) — während des
Nachtlaufs nicht gegeben; ein Build unter DB-Last kann am 20-s-Statement-Timeout
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
# PUBLIC_WINDOW_DAYS=14
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

**Cron (installiert 05.09.2026, Zeit 22.09.):** `0 2 * * *  scripts/publish_static_site.sh` — täglich nach dem Review-Tag, rund 45 min vor dem 04:00-Cycle
— Lock, Kollisionswächter (wartet bis 90 min auf den Cycle), Build, `--apply`;
ohne `webspace.env` stiller Skip; Log `~/logs/catandary-publish-<Datum>.log`.
Wächter 07:45 prüft die Summary, sobald die Config existiert.

### 9.4 Was owner-verwaltet bleibt (Webroot)

`index.html` (= `docs/launch/preview.html`, die Landing), `mark.svg`,
`favicon.ico`, `assets/signal-cloud.bin` (die Signalwolke im Hero, seit 29.09.;
neu erzeugen mit `.venv/bin/python scripts/export_landing_cloud.py` nach einem
neuen Wolkenlauf — 20.000 Punkte, nur Geometrie, keine Titel; ohne die Datei zeigt
der Hero die alte 2D-Animation), `newsletter/**` (PHP-DOI), die Root-`.htaccess`. Der Publisher
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
Gemma-4-26B der Artikelerzeugung oder den 27B-Richter.

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
| 01:30 täglich | Postgres-Backup (dumpdir, zstd, keep 4 Tage) | `scripts/backup_db.py --dest /mnt/data-hdd/backups/catandary --skip-sqlite --keep-days 4` | installiert |
| 01:55 täglich | Story-Gruppierung (#109) | `scripts/group_stories.py --days 3 --apply` | installiert (25.09.) |
| 02:15 täglich | Volltext-Retention 60 Monate | `scripts/purge_raw_content.py --days 1825 --apply` | installiert (03.09., Frist 10.09. erweitert) |
| 02:30 täglich | Offen lizenzierte Artikel der Vorbehalts-Quellen freischalten | `scripts/resolve_open_licence.py --limit 300 --apply` | installiert (09.09.) |
| 02:45 Mo–Fr | Full Cycle + Draft-Richter + **Review-Agent (Stage 11)** + Morgen-Mail | `scripts/full_cycle_cron.sh` (Batch **3000** — so bemessen, dass ein normaler Tag in einem Lauf durchgeht; `CYCLE_BATCH=N` in der Crontab-Zeile hebt ihn für eine Nacht an) | installiert |
| 07:45 täglich | Wächter (bewusst NICHT mitverschoben 22.09.) | `python -m scripts.cycle_watchdog` | installiert |
| 07:45 **Di** | Newsletter-Website-Edition (von Mo verlegt 11.09., Zeit 22.09.) | `scripts/weekly_newsletter_publish.sh` | installiert (ohne `NEWSLETTER_DEEP_DIVE`) |
| 03:45 Di | Patent-Ingest BDDS (Cr-Del + Amend) | `scripts/weekly_patents.sh` | installiert |
| 06:45 Di | Patent-Rechnungen (assign_cpc, Tier-Serien, Insights) | `scripts/weekly_patent_analytics.sh` | installiert |
| 06:00 Sa | Nicht-RSS-Ingester + Distill + Research-Index (Relevanz: Presse/Forschung per Head, Patente/Förderung per Regel seit 02.10.) | `scripts/weekly_ingesters.sh` | installiert |
| 06:00 So | Discovery-Loop (Mega-Kandidaten, Head-Retrain auf dem 1024er-Präfix seit 26.09.) | `scripts/discovery_loop.py` | installiert |
| 1. 08:00 | Monats-Quellencheck (+ TDM-Re-Probe) → Issue #13 | `scripts/monthly_source_check.py --post-issue` | installiert |
| 2. 07:00 | Backlink-Check → `dead_links` | `scripts/check_source_links.py --per-source 12 --mark` | installiert |
| 5. 02:00 | OpenAlex-Monats-Sync (45M-Korpus) | `scripts/sync_openalex_monthly.sh` | installiert |
| 6. 12:00 | Startup-Register (CORDIS/SBIR/GLEIF/CH) | `scripts/monthly_startup_sources.sh` | installiert |
| 02:00 täglich | **Statischer Export → Webspace** | `scripts/publish_static_site.sh` | **installiert in `deploy/crontab.txt`, nicht installiert** (kein `webspace.env`) |
| 08:30 Sa | Research Pulse (Vorwoche, 28 Themes) | `scripts/weekly_research_pulse.sh` | installiert (2026-09-18; Zeit ab 26.09., vorher 12:00) |
| 08:45 Sa | Field Watch (Wochenblätter aller Kundenfelder) | `scripts/weekly_field_watch.sh` | installiert (2026-09-26; ohne Kundendateien no-op) |
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

### 11.3a Kalte Tabellen auf die HDD (`scripts/move_cold_tables_to_hdd.sh`, 2026-10-03)

Verschiebt die drei `*_old`-Tabellen (36 GB, liest nur noch der Dump) samt Indizes in den
Postgres-Tablespace `hdd` unter `/mnt/data-hdd/pg_tablespace`. Nichts wird gelöscht.
Ohne Argument ist es ein Probelauf, der nur zeigt, was passieren würde; `--apply` führt aus.
Beim ersten Mal fragt `sudo` nach dem Passwort, weil der Tablespace einmalig als
Superuser angelegt wird. Nicht während Backup (01:30) oder Cycle (02:45) starten, das
Skript bricht dann mit rc 75 ab. Andere Tabellen: `TABLES="a b" scripts/…`.
Restore danach: `docs/restore_runbook.md`, Abschnitt Tablespace. **Ausgeführt 03.10.:** die drei
`*_old`-Tabellen und `history_vectors` liegen im Tablespace `hdd`.

### 11.3b Vergangenheit des Signalraums planen (`scripts/history_plan.py`, 2026-10-03)

Probelauf, schreibt nichts. Zählt je Monat und Ebene, was eingebettet werden müsste, damit
Wolke, Nester und Zitationsgraph eine Vergangenheit haben:
- Patente 1990–2022, eine je Familie;
- Forschung 2010–2022;
- Quote je Monat `--quota` (Default 2.000) plus alle zitierten Patentfamilien.

Ausgabe:
- Tabelle je Jahr;
- GPU-Stunden mit 3090 + 5080 parallel;
- Größe der Nebentabelle;
- `data/history_plan.json`.

~2,5 min. Plan und Ergebnis vom 03.10.: `docs/history_backfill_plan_2026-10-03.md`.

**Einbetten** (`scripts/history_embed.py`, gebaut 03.10.):

- `select`: füllt die Warteschlange `history_items` je Ebene und Zeitfenster einmalig (~7,5 min).
  Hat eine Ebene im Fenster schon Einträge, wird sie übersprungen; ein abgebrochener Lauf holt die
  fehlende Ebene beim nächsten Aufruf nach. Default seit 03.10.: bis 2026-06. Ein neues Zeitfenster
  hängst du mit eigenem `--…-from`/`--until` an; `--force` füllt ein schon belegtes Fenster auf.
- `scripts/run_history_embed.sh`: bettet auf 3090 + 5080 parallel ein (~6 h).
  - Die 5080 nur mit deinem Wort, denn Nemotron wird solange angehalten und am Ende
    wieder gestartet.
  - `NO_REMOTE=1` nimmt nur die 3090.
  - Ein zweiter Aufruf macht dort weiter, wo der erste aufgehört hat.
- `status`: Fortschritt je Ebene und Schicht.
- `scripts/history_redate.py [--apply]`: Datiert Forschungsarbeiten, die OpenAlex auf den
  1. Januar setzt (nur Jahr bekannt), per Crossref auf ihren Monat. Ohne Monat fallen sie
  aus der Zählung. `--refill-january --apply` füllt den Januar wieder auf, danach
  `history_embed.py work`. Ergebnis 03.10.: 59 % datiert.
  Ist neue Forschung in die Stichprobe gekommen, beide Schritte noch einmal laufen lassen.
- `check --host URL`: Stimmt der Vektorraum mit `trends` überein? Gut ist ein Kosinus
  um 0,998.

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

### 11.4a Kontext, Parallelität, VRAM messen (`scripts/ctx_eval/`, 2026-09-25)

Werkzeugkasten, um für jedes Modell zu messen, wie viel Kontext es wirklich braucht, ab wie
vielen gleichzeitigen Anfragen der Durchsatz nicht mehr steigt und wie viel VRAM eine kleinere
Konfiguration spart. Bericht der ersten Messung: `docs/context_parallel_eval_2026-09-25.md`.
**Alle Läufe brauchen ein Fenster ohne GPU-Cronjobs und stoppen den Produktivserver.**

```bash
gpu-mode status --hours 12                  # Fenster prüfen (GPU-Crons: Sa 06:00, Sa 08:30, Mo-Fr 02:45)
systemctl --user stop llama-server.service

.venv/bin/python scripts/ctx_eval/llama_log_stats.py /tmp/llama-server.log
#   → je Modell: Prompt-/Ausgabelängen (Median/p99/Max), truncated, gleichzeitig belegte Slots

.venv/bin/python scripts/ctx_eval/build_prompts.py 1000        # echte Prompts aus der Live-DB
.venv/bin/python scripts/ctx_eval/build_quality_sets.py 75     # Handentscheidungen für den Qualitätsvergleich
.venv/bin/python scripts/ctx_eval/build_probes.py              # längste erlaubte Anfrage (CJK-Quelle)

scripts/ctx_eval/run_server.sh start start-gemma4-26b.sh test -c 16384 --parallel 1
#   Testserver auf :8190 — NIE über start-*.sh (die killen den Produktivserver und binden :8090)
.venv/bin/python scripts/ctx_eval/bench_parallel.py \
    --prompts data/ctx_eval/prompts/gemma_stage6.jsonl \
    --concurrency 1,2,4,8 --duration 120 --ramp 30 --label test --out data/ctx_eval/results.jsonl
scripts/ctx_eval/run_server.sh stop

scripts/ctx_eval/matrix.sh gemma            # fertige Messblöcke: gemma | 27b | emb
scripts/ctx_eval/block_8b.sh                # 8B-Varianten (Server muss laufen)
.venv/bin/python scripts/ctx_eval/summarize_results.py        # Markdown-Tabelle aller Stufen
.venv/bin/python scripts/ctx_eval/quality_eval.py --kind judge \
    a=data/ctx_eval/q_judge_q4.jsonl b=data/ctx_eval/q_judge_q8.jsonl

gpu-mode catandary                          # IMMER am Ende, auch nach Abbruch
readlink ~/llama.cpp/start-active.sh        # muss start-qwen3-8b-208k.sh sein
```

Ergebnisse liegen in `data/ctx_eval/` (`results.jsonl`, `results_table.md`, `dump_*.jsonl`,
`server-*.log`, Testläufe unter `testrun/`). Startskript-Varianten aus der Messung vom
25.09.2026, jede mit gemessenem VRAM-Budget im Kopfkommentar:

| Skript | Status | Wirkung |
|---|---|---|
| `start-gemma4-26b-ctx16k.sh` | **in Betrieb** (main-Merge 26.09.) | Kontext 16 384 statt 262 144; 15 072 statt 19 782 MiB; Durchsatz gleich |
| `start-qwen3.8-27b-ctx16k.sh` | **in Betrieb** (main-Merge 26.09.) | Kontext 16 384/q8_0 statt 262 144/q4_0; 17 610 statt 23 094 MiB; Reserve ~6,7 statt ~1,2 GB |
| `start-qwen3-8b-208k-ctx16.sh` | vorbereitet, **nicht** aktiv | 16 statt 24 Slots; 16 506 statt 22 000 MiB, aber −3 % Durchsatz — nicht empfohlen, solange die GB nicht gebraucht werden |
| `start-qwen3-emb-16slots.sh` | vorbereitet, **nicht** aktiv | 8 552 statt 11 096 MiB bei gleichem Durchsatz; betrifft eine Phase von 1–2 min je Nacht |

Die beiden aktiven sind in `pipeline/gpu_handover.py` (`MODEL_START_SCRIPTS`),
`pipeline/draft_judge.py` (`JUDGE_START_SCRIPT`), `scripts/scheduled_cycle.sh` und den beiden
Newsletter-Wrappern eingetragen. **Rückweg:** dort wieder auf `start-gemma4-26b.sh` bzw.
`start-qwen3.8-27b.sh` zeigen lassen — die alten Skripte liegen unverändert in `~/llama.cpp`.
Testlauf der Umstellung: `scripts/ctx_eval/testrun_batch.sh 100` (echter Pipeline-Batch mit
VRAM-Protokoll) und `scripts/ctx_eval/testrun_judge.sh 40` (Stufe 10 einzeln, stellt den
Ruhezustand per `trap` auch bei Abbruch wieder her).

### 11.4b Der Wächter prüft den llama-server mit (seit 2026-09-26)

Der Morgen-Wächter (07:45) meldet jetzt auch, wenn `:8090` nicht antwortet oder ein
anderes Modell als den Ruhezustand serviert. Läuft gerade ein GPU-Job, gibt es keinen
Alarm — dann gehört die Karte ihm.

Anlass: `weekly_ingesters.sh` stellte den Ruhezustand nicht her. Der GPU-Handover stoppt
den Server nach dem letzten Schritt und setzt nur den Symlink zurück; das abschließende
`systemctl start` wie im Cycle fehlte. Gemessen über `ops_samples` lag die Karte danach
jeden Samstag leer da (19.09.: 129 von 169 Messungen zwischen 07:30 und 12:00 ohne
geladenes Modell; 26.09.: 106 von 109). Die Owner-Instanz auf :3001 hatte in dieser Zeit
kein Modell. Beides ist behoben: der Wrapper stellt den Ruhezustand her (sichtbar als
`rest=…` in seiner end-Zeile), der Wächter prüft ihn.

Prüfen von Hand:

```bash
.venv/bin/python -m scripts.cycle_watchdog --dry-run --force   # zeigt alle Checks
curl -s localhost:8090/v1/models | python -m json.tool | grep '"id"'
gpu-mode catandary                                             # zurück in den Ruhezustand
```

### 11.4c Schlagworte messen (`scripts/tag_eval/`, 2026-09-27)

Zwei Piloten zur Frage, ob Forschungs- und Patentsignale billig Schlagworte bekommen
können (seit dem 03.07. haben sie keine). Ergebnis und Zahlen:
`docs/tag_eval_2026-09-27.md` — kurz: der Reranker hilft nur bei Patenten (Platz 1
36 → 43 %) und schafft in llama.cpp nur 17–25 Paare/s; kleine LLMs (Gemma 4 E4B,
Qwen3.5-4B) sind weder schneller als das 8B noch nah an dessen Tags.

Wiederholen (braucht die ganze GPU, ~35 min; nur in einem Fenster ohne GPU-Crons):

```bash
scripts/tag_eval/run_pilots.sh          # hält :8090 an, stellt den vorherigen Zustand per trap wieder her
.venv/bin/python scripts/tag_eval/pilot_small_llm_tags.py --compare   # Vergleichstabelle neu
```

Einzeln: `pilot_vocab_rerank.py --rerank-host … --embed-host … [--only patent|research]`
und `LLAMACPP_HOST=… pilot_small_llm_tags.py --label <modell>`. Das Treiberskript
startet Testserver auf 8093/8094/8095 per PID — nicht über `~/llama.cpp/start-*.sh`,
deren `pkill` auch den CPU-Embedder :8091 träfe — und meldet sich über den
Besitzvermerk `data/llama-server.tag_eval.pid` und `ops_events` an, damit der
Fremdbelegungs-Alarm schweigt. Ergebnisse unter `data/tag_eval/` (nicht versioniert).

### 11.4d Projektion der Signalwolke messen (`scripts/space_eval/`, 2026-09-28)

Frage: ordnet eine andere Projektion die Themen in der Signalwolke besser an? Die
Messlatte lernt jede Variante auf 36.000 Signalen (200 je Monat), setzt die Treffer von
28 festen Suchbegriffen per `transform` ein und misst Treue zum Originalraum,
Reinheit gegen Prüfer-CPC und OpenAlex-Themen, den Zusammenhalt der Treffer eines
Begriffs und den Abstand der Ebenen (Forschung/Patente/Förderung/Markt) zum selben
Thema. Ergebnis: `docs/space_eval_2026-09-28.md` — kurz: **Ebenen-Mittel abziehen +
UMAP-Kosinus auf 1024** ist in allen Themenmaßen am besten (bei allen 28 Begriffen),
kostet ~4 min mehr je Wolkenlauf und ist **nicht** umgestellt.

```bash
.venv/bin/python scripts/space_eval/eval_projection.py                 # 7 Varianten, ~5 min, CPU
.venv/bin/python scripts/space_eval/eval_projection.py --seed 7 --out eval_projection_seed7.json
```

Nur lesend, keine GPU; Ergebnisse unter `data/space_eval/` (nicht versioniert).

**Einbett-Rezept für Abstracts** (#114, 28.09.): `scripts/space_eval/run_abstract_eval.sh`
bettet 2.000 Food-Arbeiten dreimal ein (heute roh + 500 Zeichen · aufgeräumt + 500 ·
aufgeräumt + ganzer Abstract) und misst Themen-Reinheit, Suche und die Mehr-Ähnlichkeit
strukturierter Abstracts. Braucht die GPU: hält den llama-server (:8090) ~11 min an, startet
das Embedding-Modell auf :8095 per PID, meldet sich über
`data/llama-server.space_eval.pid` und `ops_events` an und stellt :8090 per `trap` wieder
her; bricht mit rc 75 ab, wenn ein GPU-Cron läuft. Dieselbe Messung auf der RTX 5080:
`scripts/space_eval/run_abstract_eval_bqu.sh` — hält auf bequietUbuntu Nemotron an
(`systemctl --user` per SSH `bqu`, nur mit Owner-Wort), startet dort das Embedding-Modell auf
:8095, misst von der Workstation aus, prüft mit 200 Texten auf :8091, ob beide Maschinen
denselben Vektorraum liefern, und startet Nemotron per `trap` neu; danach prüfen, ob :8090
dort wirklich wieder antwortet. Ergebnis: aufgeräumt + 500 Zeichen
(`pipeline/text_clean.embed_text`), der ganze Abstract bringt nichts und kostet 2,5×.

### 11.4e Food-Pilot (Issue #114, `scripts/food_pilot.py`)

Holt die Food-Domäne der letzten drei Jahre vollständig in den Signalraum (bis dahin
fehlten Patente 2019–2025 fast ganz): **Patente** aus `EPO DOCDB (FOOD)` — eine
Veröffentlichung je DOCDB-Familie (die früheste mit Abstract), ohne Gebrauchsmuster,
Familien mit schon vorhandenem Signal übersprungen — und **Forschung** aus
`research_corpus`: Subfelder Food Science (inkl. Culinary Culture and Tourism) und
Nutrition and Dietetics, dazu alternative Proteine per Phrase in Titel/Abstract
(Liste im Skript). Ohne Ersatzdatum 1. Januar, ohne Repository-Einträge, ohne schon
vorhandene Forschungssignale.

```bash
.venv/bin/python scripts/food_pilot.py select              # zählt, schreibt data/food_pilot/ (nur lesend, ~1 min)
.venv/bin/python scripts/food_pilot.py takeover --limit 500 # Trockenlauf; --apply schreibt raw_entries
scripts/run_food_pilot.sh                                  # Volllauf: Übernahme, Einbetten, Ruhezustand, research_signals
.venv/bin/python scripts/food_pilot.py status              # Ergebnis je Gruppe
```

Die Arbeiten kommen unter drei Pseudo-Quellen `OpenAlex corpus: Food Science | Nutrition
and Dietetics | Alternative proteins` mit **`llm_pipeline = FALSE`** — der Nachtlauf
schreibt daraus nie Artikel. Eingebettet wird über den regulären Signalpfad
(`signal_batch_embedded.py --ids-file … --clean-text`): Relevanz-Head (Schwelle 0,5; seit
02.10. für Patente und Förderung stattdessen Regeln, `pipeline/signal_rules.py`),
Embedding-Dedup, Status `signal`; `--clean-text` nimmt Ebenen-Tag, Überschriften, HTML und
Copyright vor dem 500-Zeichen-Schnitt heraus (`pipeline/text_clean.py`). Der Volllauf
stellt danach den 8B-Ruhezustand her — der Einbett-Handover allein setzt nur den Symlink
zurück und lässt die Unit gestoppt — und baut `research_signals` neu. Er muss **vor 02:45**
fertig sein (der Nachtlauf wartet sonst bis 90 min auf die GPU und bricht ab).
Auswahl 29.09.: 76.433 Patente, 129.788 Arbeiten (Food Science 75.494, Nutrition 49.484,
alternative Proteine 4.810); Test mit 500 + 500: 839 Signale, Patente 79 % / Forschung 88 %
übernommen, der Rest nicht relevant oder Duplikat. Danach die Wolke neu rechnen
(*Recompute cloud*).

### 11.4f Nester nachbenennen (`scripts/rename_nests.py`)

Die Nester der Emerging-Schicht bekommen ihren Namen vom lokalen Modell (Gemma, ein
GPU-Handover je Lauf). Scheitert dieser Handover, behalten sie ihre Schlagwort-Etiketten,
und `llm_label_note` sagt „handover failed". Nachbenennen, ohne den Lauf neu zu rechnen:

```bash
.venv/bin/python scripts/rename_nests.py --runs 60,61,66            # zeigt, was es benennen würde
.venv/bin/python scripts/rename_nests.py --runs 60,61,66 --apply    # benennt (GPU, ~1 min + Modellwechsel)
.venv/bin/python scripts/rename_nests.py --runs 66 --redo --apply   # alle Nester eines Laufs neu
```

Gleiche Prüfung wie im Lauf (jedes tragende Wort muss im Nest vorkommen, Namen eindeutig
je Lauf); Nester, die die Prüfung schon einmal verworfen hat, bleiben ohne `--all-unnamed`
unangetastet. Danach startet das Skript das 8B wieder, falls es vorher lief (#116).
30.09.: 41 von 49 nachbenannt (ECO, DESIGN, Ebene Patente), die 16 Patent-Nester danach mit
`--redo` noch einmal, weil die Großbuchstaben der Patenttitel in die Namen durchschlugen.

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
   Seit 24.09.2026 nimmt Stage 8 nur die Drafts, die noch nicht eingeordnet
   sind (`trends.reclassified_at IS NULL`) — bei einem abgebrochenen Lauf
   also genau die schuldig gebliebenen. Soll der **ganze** Draft-Bestand neu
   eingeordnet werden (nach einer Änderung an der Vertikalen-Taxonomie oder
   an `CLASSIFY_SYSTEM`), braucht es den bewussten Vollauf — er dauert rund
   eine Stunde:
   ```bash
   .venv/bin/python -c "from pipeline.reclassify import reclassify_drafts; \
       print(reclassify_drafts(force=True))"
   ```
   (Nur mit laufendem 8B auf `:8090`, also nicht während des Nachtlaufs.)
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
   `data/research_pulse/`), dann §11.8 — der Wächter sollte das verhindert haben.
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
`data/research_pulse/`, `data/foresight_snapshot/`.

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
(`scheduled_cycle.sh`, `run_full_cycle`, `signal_batch*`,
`research_pulse`, `newsletter_deep_dive`, `newsletter_generator`,
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
`research_pulse`, `newsletter_deep_dive` …) ebenso wie der
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
Platte unter 10 % frei (`/` mit Postgres schon unter 20 %), HDD über 55 °C /
SSD über 68 °C (aus den Datenblättern der verbauten Laufwerke, 16.09.), SMART FAILED, NVMe-Verschleiß ≥ 90 % oder Reserve < 10 %,
Sektor-/Medienfehler-Zähler, die gegenüber der vorigen Messung **steigen**,
GPU über 88 °C, Grafikspeicher belegt ohne antwortenden llama-server und ohne
bekannten Job, mehr als 80 % der DB-Verbindungen, ein Job, der länger als das
Doppelte seines Medians läuft, ein Job über 6 h (gezählt wird nur ein Lauf,
dessen Prozess noch lebt — eine Zeile, deren Prozess ohne Ende-Eintrag starb,
schließt der Sampler binnen einer Minute selbst und die Seite zeigt sie als
„aborted"), **ein Job, dessen letzter abgeschlossener Lauf mit `rc != 0`
endete** (seit 26.09.; bleibt gemeldet, bis derselbe Job wieder mit 0 endet —
`rc = 75` ist der Skip des GPU-Kollisionswächters und kein Defekt,
`job_failed_ignore_rc` in der yaml nimmt weitere auf), ein Backlog, dessen
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

### 11.10 Prompt-Katalog (`/trends/ops/prompts`)

**Wozu.** Nachlesen, was die Sprachmodelle in diesem System als Systemanweisung
bekommen — ohne im Code zu suchen. Ein Eintrag je LLM-Funktion: kurz, was die
Funktion tut und wann sie läuft (Cron, Desk-Knopf, nur auf Zuruf), welches
Modell antwortet, wo der Prompt steht (Datei:Zeile) und der Prompt selbst zum
Aufklappen. Bei Stage 6 (Artikel) steht darunter zusätzlich der Bauer des
User-Prompts (Quelltext).

**Wo.** `/trends/ops/prompts`, verlinkt oben rechts auf `/trends/ops`
(„Prompts →"). Owner-Seite: im PUBLIC_MODE 404, im statischen Export nie
gebaut (dieselben drei Schlösser wie das Ops-Dashboard).

**Woher die Texte kommen.** Die Seite ruft `python -m pipeline.prompt_catalog
--json` auf und liest die Prompts aus den Modulen — sie zeigt also immer den
Stand des Codes, aus dem die Instanz läuft (`:3001` = main, `:3004` = dev).
60 Sekunden Cache. Ein Eintrag, der nicht lädt (Umbenennung, Importfehler),
erscheint rot mit der Fehlermeldung statt zu verschwinden.

```bash
.venv/bin/python -m pipeline.prompt_catalog --list    # eine Zeile je Eintrag, mit Zeichenzahl
```

**Was nicht drin ist.** Embedding-Aufrufe (keine Anweisung), die
Distill-Klassifikationsköpfe (kein Modell), die A/B-, Benchmark- und
Eval-Skripte unter `scripts/`. Neue LLM-Funktion → neuer Eintrag in
`build_catalog()` (Test `tests/test_prompt_catalog.py` prüft, dass jeder Eintrag
lädt und auf eine echte Datei zeigt).

### 11.11 Signaltyp-Head (#110)

**Wozu.** Seit der Hybrid-Klassifikation (14.07.2026) kam der Signaltyp allein
aus der Quellenart — jede Presse-Meldung wurde `market_shift`. Der fünfte
Distill-Head entscheidet für Presse zwischen product_launch, regulation,
partnership, consumer_behavior und market_shift; patent/research/funding
bleiben bei der Quellenart-Regel.

**Trainieren** (CPU, kein GPU, ~8 min; fasst die vier anderen Heads nicht an):

```bash
.venv/bin/python scripts/train_signal_type_head.py            # voll: 553 k Teacher-Zeilen
.venv/bin/python scripts/train_signal_type_head.py --no-write # nur Kennzahlen
```

Schreibt `models/distill/signal_type.joblib` + `signal_type_meta.json` und den
Bericht `data/signal_type_head_report.{json,md}` (Holdout je Klasse, Genauigkeit
je Konfidenz-Band, und was der Head auf den Presse-Zeilen seit dem 14.07.
vergeben würde, mit Titel-Stichproben je Klasse). `models/` ist gitignored und
liegt je Worktree — nach dem Merge nach `main` die Datei dorthin kopieren.

**Einschalten.** Seit 25.09. aktiv: `DISTILL_SIGNAL_TYPE=1` steht in
`scheduled_cycle.sh` und `weekly_ingesters.sh` (Zeile entfernen oder `=0` schaltet ab); `DISTILL_SIGNAL_TYPE_MIN_CONF`
(Default 0,6) ist der Konfidenz-Boden, darunter bleibt es bei `market_shift`.
Ohne Schalter oder ohne Datei verhält sich alles wie bisher. Gemessen (Holdout,
25.09.): Genauigkeit 0,83 ab 0,5, 0,88 ab 0,6, 0,92 ab 0,7 — bei 92 / 76 / 61 %
der Zeilen über der Schwelle; 0,6 trifft auf den Presse-Zeilen seit dem 14.07.
die historische Klassenverteilung am besten.

**Bestand nachziehen** (Stufe 2, erledigt 25.09.): `scripts/relabel_signal_types.py`
(Dry-Run; `--apply` schreibt gebatcht 1.000 Zeilen je Commit, nur
`trend_signal_type` + `trend_score`). Lauf 25.09.: 49.681 Presse-Zeilen seit dem
14.07. geprüft, 17.997 umgelabelt (regulation 8.888, product_launch 6.422,
partnership 1.792, consumer_behavior 895). Nach einem Retrain des Heads erneut
laufen lassen, wenn sich die Schwelle ändert.

### 11.12 Story-Gruppierung (#109)

**Wozu.** Eine Meldung, drei Artikel: der Dedup (Kosinus ≥ 0,92) misst
Textähnlichkeit, drei Blickwinkel auf dieselbe Meldung liegen darunter. Statt
die Schwelle zu senken (kostet ~9 % aller Artikel, löst den Fall nicht)
gruppiert ein Nachlauf: gleiche extrahierte Marke · 48 h · Kosinus ≥ 0,80,
transitiv. Der älteste Artikel führt. Nichts wird gefiltert oder
entpubliziert — Stufe 1 misst und zeigt.

```bash
.venv/bin/python scripts/group_stories.py                 # Dry-Run, letzte 3 Tage, Kennzahlen + 5 größte Gruppen
.venv/bin/python scripts/group_stories.py --days 30       # einen Monat messen
.venv/bin/python scripts/group_stories.py --days 3 --apply   # trend_stories schreiben (Cron-Zeile)
```

Ausgabe: Zeile mit `groups`, `articles_in_groups`, `followers`,
`follower_share`, Größenhistogramm; danach die größten Gruppen mit Quelle,
Zeit, Kosinus zum Leitartikel und Titel. `data/story_groups_last.json` hält
den letzten Lauf. `--apply` ist idempotent (story_id = id des Leitartikels);
das Fenster wird jedes Mal neu gerechnet, Artikel, die aus einer Gruppe
fallen, verlieren ihre Zeile. Stand 25.09. (26.08.–25.09.): 23.342 Artikel,
1.085 Gruppen, 1.895 Folgeberichte (8,1 %).

Cron seit 25.09. installiert (01:55). **Nächste Entscheidung (Owner, ab
02.10.):** Folgeberichte weiter veröffentlichen und nur anzeigen (heute) oder in
Stage 5 gar nicht erst veröffentlichen (`mark_filtered`).

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
  steht auf der Methodik-Seite unter „Our AI agent" (bis 20.09. „Our crawler"), nicht mehr in jedem Log),
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
