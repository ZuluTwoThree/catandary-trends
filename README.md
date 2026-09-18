# Catandary Trends

**English summary.** Catandary Trends is an owner-operated trend-scouting and
foresight application that runs entirely on local models (llama.cpp on one
RTX 3090). It polls curated primary sources (RSS, preprints, patents, funding,
company registers), classifies the signals, writes short English trend articles,
and offers a set of analyst tools on top of the corpus: technology trajectories
from the patent citation graph, cross-tier lead time, cluster momentum, a
research explorer with weekly "pulse" syntheses, and agentic scouting dossiers.
The public website (`catandary.de/trends`) is a **static export** of a 30-day
article window uploaded to shared web hosting; there is no SaaS, no login, no
payment — the business is sales-led (individual analyses, "Super Pro+"). This
README is the owner's manual; it is written in German.

---

## Was das ist

Catandary Trends ist die **Owner-App** eines Einzelunternehmers: ein lokal
laufendes Trend-Scouting- und Foresight-Werkzeug, das jede Nacht Fachquellen
liest, Signale klassifiziert, kurze englische Trend-Artikel schreibt und darauf
Analysewerkzeuge anbietet. Alles — Klassifikation, Texte, Recherche-Dossiers —
läuft auf lokalen Modellen (llama.cpp, Port 8090, eine RTX 3090 mit 24 GB).
Cloud-APIs sind Opt-in-Fallbacks.

Nach außen gibt es genau zwei Dinge:

- **Das Schaufenster:** `catandary.de` = statische Landing (owner-verwaltet) +
  `catandary.de/trends` = **statischer Export** der letzten 30 Tage Artikel,
  Mega-Themen, Methodik und Newsletter-Archiv, per SFTP auf das bestehende
  Hetzner-Webhosting gelegt. Kein Server, keine Suche auf dem Server, keine
  Foresight-Werkzeuge. Countdown auf der Landing: **01.10.2026**.
- **Das Geschäft:** sales-led. Verkauft werden Individualanalysen und
  „Super Pro+"-Zugang; die Anfrage läuft über eine `mailto:`-Seite
  (`/enquiry`). Es gibt keine Tarife, keine Accounts, keine Zahlungsstrecke
  (Rückbau 03.09.2026, Issue #93).

Alles andere — Review-Queue, Foresight-Cockpit, Dossier-Desk, Research Pulse —
ist **nur auf der Workstation** erreichbar (`:3001` main, `:3004` dev) und im
Export gar nicht enthalten.

Ehrlichkeitsregeln, die für jeden Text im Repo und auf der Website gelten: kein
Methoden-USP (die TIR-Methode ist publizierte MIT-Forschung, andere nutzen sie
auch), keine Kunden- oder Zertifikatsbehauptungen, keine „erkennt Trends
früh"-Versprechen — die Werkzeuge messen relative Entwicklung, und wo der Korpus
nichts belegen kann, sagen sie das.

Architektur- und Taxonomie-Vertrag: [`CLAUDE.md`](CLAUDE.md). Backlog: die
[GitHub-Issues](https://github.com/ZuluTwoThree/catandary-trends/issues);
Stand je Issue in [`docs/issue_status.md`](docs/issue_status.md).

---

## Inhalt

1. [Instanzen und Einstieg](#1-instanzen-und-einstieg)
2. [Bedienungsanleitung Owner-Funktionen](#2-bedienungsanleitung-owner-funktionen)
   - [2.1 Karte der Owner-Funktionen](#21-karte-der-owner-funktionen)
   - [2.2 Routine: Morgen nach dem Nachtlauf](#22-routine-morgen-nach-dem-nachtlauf)
   - [2.3 Routine: Öffentliche Website aktualisieren](#23-routine-öffentliche-website-aktualisieren-bis-der-cron-läuft)
   - [2.4 Routine: Scouting-Dossier bestellen](#24-routine-scouting-dossier-bestellen)
   - ausführlich je Funktion: [`docs/owner_manual.md`](docs/owner_manual.md)
3. [Setup](#3-setup)
4. [Architektur in einer Seite](#4-architektur-in-einer-seite)
5. [Tests und Konventionen](#5-tests-und-konventionen)
6. [Launch-Checkliste Owner](#6-launch-checkliste-owner)

---

## 1. Instanzen und Einstieg

> **Zugriff seit 05.09.2026:** Alle Instanzen und der llama-server hören nur auf `127.0.0.1`. Vom MacBook: `https://kiworkstation.tail678c6e.ts.net` (Owner-App :3001; `/` leitet auf `/trends`, es gibt keine App-Landing mehr). **Landing-Vorschau vor dem Upload:** `scripts/landing_preview.sh` → `https://kiworkstation.tail678c6e.ts.net:3997/preview.html` (Countdown, Animationen, Formular; das Formular postet an den ECHTEN DOI-Endpunkt), `https://kiworkstation.tail678c6e.ts.net:3004` (dev), `…:3999` (PUBLIC_MODE-Vorschau) — Tailscale Serve, nur im Tailnet, HTTPS. Auf der Workstation selbst weiterhin `http://127.0.0.1:3001`. Die alten Adressen `100.115.179.37:3001` funktionieren absichtlich nicht mehr. Serve-Konfiguration: `tailscale serve status`; ändern: `tailscale serve --bg --https=443 http://127.0.0.1:3001`.

| Wo | Was | Start |
|---|---|---|
| `http://localhost:3001` | **Produktive Owner-Instanz** aus dem `main`-Worktree `~/projects/catandary-trends` (`next start`, systemd user unit `catandary-frontend`) | läuft dauerhaft; nach einem `main`-Update: `cd frontend && npm run build && systemctl --user restart catandary-frontend` |
| `http://localhost:3004` | Dev-Server aus dem `dev`-Worktree `~/projects/ct-dev` | `cd ~/projects/ct-dev/frontend && npx next dev --turbopack -p 3004` (in tmux, Session `ct`) |
| `http://localhost:3999` | **PUBLIC_MODE-Vorschau** = so sieht die öffentliche Seite aus (Foresight/Review/Dossiers → 404, Feed auf 30 Tage gefenstert) | `cd ~/projects/ct-dev/frontend && PUBLIC_MODE=1 NEXT_DIST_DIR=.next-public npx next dev --turbopack -p 3999` |
| `http://localhost:8098` | Lokaler Apache (Docker) mit dem **fertigen statischen Export** und den echten `.htaccess`-Regeln | `scripts/htaccess_test_server.sh` (Handbuch §9) |
| `:8090` | `llama-server` (systemd user unit `llama-server.service`), Ruhezustand = Qwen3-8B | läuft dauerhaft; Handbuch §11 |

`npm run dev` ohne Argument nimmt Port **3001** — im Dev-Worktree immer `-p 3004`
mitgeben. Alle drei Next-Instanzen und der llama-server lauschen derzeit auf
**allen Interfaces** (LAN/Tailnet erreichbar, ohne Login) — siehe Handbuch §12.

Die Owner-Navigation (Header): *Trends · Mega Trends · Analyses* und der
Foresight-Block *Cockpit · Clusters · Technology · Lead Time · Evolution ·
Scouting Desk*. Die Review-Queue (`/trends/review`) ist bewusst nicht
verlinkt.

---

## 2. Bedienungsanleitung Owner-Funktionen

Die ausführliche Anleitung — je Funktion *Wozu · Wo · Schritt für Schritt · Was
das Ergebnis bedeutet · Grenzen* — steht im
**[Owner-Handbuch `docs/owner_manual.md`](docs/owner_manual.md)**. Hier die
Karte und die drei Routinen, die man auswendig kennen sollte.

### 2.1 Karte der Owner-Funktionen

| Funktion | Wo | Kernaktion | Handbuch |
|---|---|---|---|
| Trend-Feed, Artikel, Suche/Filter | `/trends`, `/trends/<slug>`, `?q=` `?v=` | lesen, filtern; Hybrid-Suche auch als `/api/search` | [§2](docs/owner_manual.md#2-trend-feed-artikelseite-suche-und-filter) |
| **Review-Queue** (Holds: Zahlen/Jahre, **Personennamen**, **garbled**, abgeschnitten; Tab *Re-check* = Bestandsprüfung 05.09.) | `/trends/review` (unverlinkt) | *Publish · Reject · Write again*; CLI `scripts/review_cli.py`; Bestandsprüfung `scripts/recheck_published_grounding.py --names --garbage --dry-run/--apply` | [§3](docs/owner_manual.md#3-review-seite-trendsreview) |
| Mega Signal Themes, Methodik | `/trends/mega`, `/trends/methodology` | Badges lesen (Megatrend/Domain/Faded Hype/Momentum); Messung `scripts/measure_mega_axes.py --write-yaml` | [§4](docs/owner_manual.md#4-mega-signal-themes-und-methodik-seite) |
| Technologie-Suche (Quality-Gate ok/ambiguous/off_topic) | `/trends/foresight/technology` | Phrase → Feldwahl oder Rückfrage → K(t), Lead-Time, Leitpatente; CLI `scripts/tech_analyze.py --query` | [§5.1](docs/owner_manual.md#51-technologie-suche-trendsforesighttechnology) |
| Lead Time, Cluster, Evolution | `/trends/foresight/lead-time` `/clusters` `/clusters/<id>` `/evolution` | lesen; Snapshots neu rechnen (Knopf oder `python -m pipeline.foresight_snapshot --all-verticals --dim1024 [--window-months N] [--lineage]`) | [§5.2, 5.3, 5.5](docs/owner_manual.md#52-lead-time-trendsforesightlead-timecpcsubklasse) |
| **Emerging** (was ist neu) | `/trends/foresight/emerging` `?tier=market` | dichte junge Nester, je Ebene datiert (Forschung/Patente/Förderung/Markt); Knopf *Recompute pockets* oder `python -m pipeline.emerging_snapshot --all-verticals --all-tiers` | [§5.4](docs/owner_manual.md#54-emerging-trendsforesightemergingverticalv) |
| Archiv einer Quelle nachladen | — | `python scripts/ingest_sitemap_archive.py <host> --dry-run` (Sitemaps statt Feed; `--check-blocked` listet gesperrte Quellen, die über Sitemaps erreichbar wären) | [§5.0](docs/owner_manual.md#50-archiv-einer-quelle-nachladen-scriptsingest_sitemap_archivepy) |
| Emerging: Rücktest gegen bekannte Trends | — | `python scripts/validate_emerging.py`; Prüfmenge `known_trends.yaml`, Bericht `data/emerging_validation.json` | [§5.4](docs/owner_manual.md#54-emerging-trendsforesightemergingverticalv) |
| Research Explorer | `/trends/foresight/research` | `?q= ?layer=signals ?src= ?range= ?sort= ?concept= ?theme=` | [§5.6](docs/owner_manual.md#56-research-explorer-trendsforesightresearch) |
| **Research Pulse** | `/trends/foresight/research/pulse[/<theme>]` | Cron Sa 12:00 (`weekly_research_pulse.sh`, seit 2026-09-18); *Recompute*-Knopf je Theme oder `scripts/research_pulse.py` | [§5.7](docs/owner_manual.md#57-research-pulse-trendsforesightresearchpulse-pulsetheme) |
| Patent Explorer | `/trends/foresight/patents` | Nummer/CPC/Jahr automatisch, `company:"…"`, `"phrase"` `OR` `-x` | [§5.8](docs/owner_manual.md#58-patent-explorer-trendsforesightpatents) |
| Startup Explorer | `/trends/foresight/ventures` | Firmen mit Evidenz-Timeline | [§5.9](docs/owner_manual.md#59-startup-explorer-trendsforesightventures-companyid) |
| **Dossier-Desk** | `/trends/dossiers` | Auftrag → *Run now* → `review` → *Sign off*; *Recompute · v(n+1)*; Firma/Fokus/Sprache nur CLI `scripts/corpus_research.py` | [§6](docs/owner_manual.md#6-dossier-desk-trendsdossiers) |
| Newsletter (Edition, Archiv, Deep-Dive Dry-Run, Versand, Abmeldung) | `/trends/newsletter` | Edition Mo 09:00 automatisch; `NEWSLETTER_DEEP_DIVE=dry-run` in der Crontab; Versand gegated (#16) | [§7](docs/owner_manual.md#7-newsletter) |
| **Newsletter freigeben** (Pflicht vor jedem Versand) | `/trends/newsletter/review` | Ausgabe als Mail lesen → *Release for sending*; ohne Freigabe bricht der Sender mit Exit 2 ab | [§7.5](docs/owner_manual.md#75-ausgabe-freigeben-trendsnewsletterreview) |
| Analysen | `/analysis` | Markdown in `frontend/content/analyses/`, `draft: false` = live; Drafts nur auf der Owner-Instanz sichtbar | [§8](docs/owner_manual.md#8-analysen-analysis) |
| **Statischer Export** | `scripts/build_public_static.sh` → `htaccess_test_server.sh` → `publish_static_site.py --apply` | täglich 06:30 (Cron vorbereitet); `PUBLIC_NOINDEX=0` zum Launch | [§9](docs/owner_manual.md#9-statischer-export--die-öffentliche-website) |
| Quellen | `sources.yaml` | `probe_source_compliance.py --yaml` → eintragen → `verify_feeds.py`; `apply_source_hygiene.py --apply` nach jeder Flag-Änderung (synct `active` + `llm_pipeline`); Signalbetrieb statt Abschalten (`llm_pipeline: false` + `store_excerpt: false`); `resolve_open_licence.py --apply` schaltet CC-BY-Artikel aus Vorbehalts-Quellen frei; `python -m pipeline.feed_poller --dry-run` zeigt vorab, wie viel Neues die Feeds bringen; `takedown.py`, `purge_raw_content.py` | [§10](docs/owner_manual.md#10-quellen-verwalten) |
| Betrieb | `crontab -l`, `~/logs/`, `data/*_last.json` | Wächter-Mails, Backup/Restore, GPU-Ruhezustand, llama-server-Reparatur; Kollisionswächter der GPU-Crons (`scripts/lib/gpu_guard.sh`, wartet 90 min, dann Skip + Pending-Datei); `scripts/reset_embedding_errors.py --apply` holt als `embedding_error` aussortierte Einträge zurück | [§11](docs/owner_manual.md#11-betrieb-cron-wächter-backup-gpu-logs), [§11.8](docs/owner_manual.md#118-kollisionswächter-und-besitz-des-llama-servers-98) |
| Korpus-Rechercheur: Vektorsuche | `systemctl --user status catandary-embed-cpu` | CPU-Embedder auf `:8091` (kein VRAM); `RESEARCH_EMBED_HOST` in `.env` schaltet den Dossier-Worker auf Vektorsuche | [§6](docs/owner_manual.md#6-dossier-desk-trendsdossiers) |
| **Advisor — Beratungsnotiz je Kunde** (seit 2026-09-14) | Dossierseite `/trends/dossiers/<slug>` → „New advisory note" (Kundenprofil + Auftragsumfang); Ansicht `/trends/dossiers/<slug>/advisory/<id>` mit Freigabe; CLI `python -m scripts.advisory --new --dossier <slug> --profile-file p.json --scope "…" --run`, `--approve <id>` | Optionen entstehen nicht mehr im Dossier: ein Modell in der Beraterrolle (27B, Denken an) schreibt aus Dossier + Profil + Auftrag Situation, Optionen inkl. Null-Option (Trigger, Horizont, Aufwand aus Vergleichsfall, Wer zahlt, Risiko, Abbruchkriterium), Empfehlung mit Konfidenz; geschlossener Katalog, Zahlen gegen Dossier/Profil, Leser; **Freigabe nur durch dich** (`approved_at`) | [§6.5](docs/owner_manual.md#65-advisor--beratungsnotiz-je-kunde) |
| **Dossier: Landschafts-Modus** | `python -m scripts.dossier_worker --order-new "batteries" --mode landscape --run` (params `{"mode": "landscape"}`) | breites Feld → Teilfeld-Karte (Modell schlägt vor, Korpus zählt nach), ein Suchschritt je Teilfeld, Landkarten-Frage, Anhang „Landscape map“ im Dossier | [§6](docs/owner_manual.md#6-dossier-desk-trendsdossiers) |
| **Kunden-Briefing** | `/trends/foresight/pitch` (Foresight-Cockpit → „Briefing deck for prospects") | SCR-Q-Präsentation im Browser (7 Folien, ← → / Rail, `#s3`-Links), Korpuszahlen live; nur Owner-Instanz (PUBLIC_MODE 404, nicht im Export) | [§5.10](docs/owner_manual.md#510-kunden-briefing-trendsforesightpitch) |
| **Ops-Dashboard** (#104) | `/trends/ops` (Foresight-Cockpit → „Ops"); Logbuch `docs/ops/logbook.md`; Alarm-Schwellen `ops_alerts.yaml`; `systemctl --user status catandary-ops-sampler.timer`; `python -m pipeline.ops_events open` (offene Läufe) / `close-orphans` (tote Läufe schließen — macht der Sampler minütlich selbst) | minütlich eine Messzeile nach `ops_samples` (GPU lokal + bequiet, CPU/RAM, alle Platten, Postgres); jeder Cron-/Worker-Lauf eine Zeile in `ops_events` (Start, Ende, rc, Notiz); `python -m scripts.ops_sampler --print [--full]` zeigt eine Messung; SMART nach `deploy/sudoers/catandary-smart` | [§11.9](docs/owner_manual.md#119-ops-dashboard-trendsops-104) |
| Sicherheit & Recht | — | Binding aller Interfaces (Entscheid offen), TDM-Regime, Takedown | [§12](docs/owner_manual.md#12-sicherheit-und-recht-kurz) |

### 2.2 Routine: Morgen nach dem Nachtlauf

1. Postfach: **Wächter-Mail** nur bei Befund (fehlende Cycle-end-Zeile,
   fehlendes Backup-Artefakt, künftig fehlgeschlagener Publish) — Schweigen ist
   gesund. **Review-Mail** nur, wenn die Nacht Artikel zurückgehalten hat (mit
   Draft-Richter-Zahlen, ggf. Deep-Dive-Zeile und — montags — der Zeile zum
   Samstags-Ingester: `ok`/`blocked`/`failed`; `blocked` heißt, ein anderer
   GPU-Job hielt `:8090`, der nächste Lauf holt die Signale nach).
2. `http://localhost:3001/trends/review` → jede Karte: *Publish* / *Reject* /
   bei abgeschnittenem Text *Write again*. Backlog-Tab nicht wachsen lassen.
3. `/trends` sichten; bei Verdacht `~/logs/catandary-full-cycle-<Datum>.log`
   (letzte Zeile `… end … rc=0`).

### 2.3 Routine: Öffentliche Website aktualisieren (bis der Cron läuft)

```bash
cd ~/projects/catandary-trends            # main-Worktree — nicht während des 04:00-Cycles
scripts/build_public_static.sh            # ~60 s → frontend/.export/out (+ Manifest, build_info.json)
scripts/htaccess_test_server.sh           # optional: Apache-Test auf :8098, nach jedem Build neu starten
.venv/bin/python scripts/publish_static_site.py          # Dry-Run: Plan je Phase
.venv/bin/python scripts/publish_static_site.py --apply  # Upload (Manifest-Delta, nur trends/** + _next/** + 4 Root-Dateien)
```

Voraussetzung: `~/.config/catandary/webspace.env` (chmod 600) — existiert noch
nicht (Owner-Aktion, Abschnitt 6). Build ≤ 12 h alt, ≥ 1000 Artikel, ≤ 60 %
Löschungen, sonst Exit 2.

### 2.4 Routine: Scouting-Dossier bestellen

`http://localhost:3001/trends/dossiers` → *New order slip*: Technology field,
optional Series slug und eigene Frage, Häkchen „measure the innovation chain
first" und „start the worker right away" → *Place order*. Worker läuft 10–20 min
(GPU exklusiv, nicht parallel zum Cycle), Ergebnis steht in `review`; in der
Leseansicht Herkunftskopf, Endkontrolle, Bericht, Coverage-Anhang lesen → *Sign
off*. Gleicher Slug später erneut = nächste Version (*Recompute · v(n+1)*).
Terminal: `.venv/bin/python -m scripts.dossier_worker --order-new "solid-state batteries" --run`.

Seit 2026-09-07 trägt jedes Dossier zwei codegenerierte Mess-Anhänge
(„Measured development" = Zeitreihe je Reifegrad, Take-offs, Vorlaufzeit,
K(t), Zykluszeit, Zentralitäts-Peak; „What the corpus counts" = Korpus-Zählung
je Jahr/Vertikale/Quelle) — und meldet es sichtbar, wenn die Messung ausfällt.
Alter Pfad: `DOSSIER_MEASURE=0` bzw. `--no-measure`
([`docs/agentic_dossiers.md`](docs/agentic_dossiers.md#die-messkette-2026-09-07)).

Ebenfalls seit 2026-09-07 ist der Bericht **entscheidungsorientiert**: sieben
Pflichtabschnitte (Decision summary ≤ 200 Wörter · What is moving · Regulatory
and IP status · What happens next · What the evidence does not support ·
Options · Open questions), Längenband 2.200–2.800 Wörter Fließtext (beide
Grenzen lösen den Neuwurf aus), je Option ein Go/No-Go-Gerüst
(Trigger/Time horizon/Effort/Risk/Against it). „What happens next" ist ein
Kalender datierter, belegter Termine (mindestens fünf Zeilen), und jede der
vier Ebenen der Innovationskette — Wissenschaft, Patente, Förderung, Markt —
braucht im Fließtext eine datierte und belegte Aussage. Der Rechts- und
Zulassungsstatus kommt aus einem eigenen Sweep mit festen Suchmustern
(SPC/Patentablauf Europa, EMA, FDA, anstehende Entscheidungstermine,
Gerichtsentscheidungen, EFSA-Health-Claims) und eigenem Budget; jede im
Fließtext zitierte Web-Zahl wird gegen den Volltext genau der zitierten Seite
geprüft — was dort nicht steht, fliegt raus. Kernzahlen in Kurzfassung,
Optionen und Kalender brauchen zusätzlich eine Quelle vom Rang 0/1 (Behörde,
Register, Gericht, Firmen-IR/SEC, Fachjournal), sonst werden sie als „nur
sekundär belegt" gekennzeichnet oder gestrichen. Ein gezielter Neuwurf plus
höchstens ein Nachzug für Strukturbefunde (`DOSSIER_REWRITES`), Best-of-2 im
Erstentwurf (`DOSSIER_DRAFTS`), kein Kritiker-Modell
([`docs/agentic_dossiers.md`](docs/agentic_dossiers.md#die-entscheidungsebene-2026-09-07)).

**DR-Vorlauf — Default seit 2026-09-13** (`DOSSIER_DR=0`, `--no-dr` oder
`params = {"dr": false}` schalten ab; das Ziel „besser als Sonnet Deep
Research" für die *Schreibweise* bleibt offen, Stand und Wiederaufnahme in
[`docs/dossier_vs_deep_research_2026-09-07.md`](docs/dossier_vs_deep_research_2026-09-07.md),
Issue #100):
Arbeitsweise eines Deep-Research-Agenten — Primärquellen werden vor dem
Schreiben **nach Rang** gelesen, daraus entsteht ein **Faktenbuch** aus
datierten Einzelaussagen (jede maschinell gegen ihren Quelltext geprüft), und
der Bericht wird aus diesem Faktenbuch geschrieben; gesampelt wird nach
Modellkarte statt nur über die Temperatur. Seit Runde 13 bekommt der Bericht
zusätzlich **Kalender-Kandidaten** (datierte Zukunftstermine aus den gelesenen
Seiten) und **Aufwands-Anker** (Förderbeträge, Programmbudgets,
Verfahrensdauern) als fertige Listen vorgelegt, und eine dritte Sweep-Welle
fragt je Akteur nur nach Terminen. Seit Runde 14 außerdem eine
**Akteur-Landkarte** (Pflichttabelle in „Was sich bewegt"), Streichung auf
Absatzebene mit Reparatur je Satz, und **themenneutrale Suchrichtungen**:
themenunabhängiger Kern + kuratiertes Rückgrat je Vertikale (Vertikale aus den
Korpus-Nachbarn) + Modellprofil (Regulatoren, Ereignistypen, Akteur-Saatgut,
Perspektiven). Probe ohne Lauf: `scripts/dossier_topic_probe.py "<Thema>"`.
Kostet Laufzeit, hebt die
Faktenquote (erster Lauf: 0,94 gegen 0,25 der Runde davor)
([`docs/agentic_dossiers.md`](docs/agentic_dossiers.md#die-dr-runde-2026-09-07--arbeitsweise-statt-regelwerk)).

---

## 3. Setup

Geprüft auf der Linux-Workstation (Ubuntu 24.04, Python 3.12.3, Node 24.15,
PostgreSQL 16.15). Ein Laptop-Pfad ohne GPU steht in
[`MACBOOK_SETUP.md`](MACBOOK_SETUP.md).

### 3.1 Voraussetzungen

| Komponente | Anmerkung |
|---|---|
| Python 3.12 | virtualenv `.venv/` im Repo; **alle** Python-Aufrufe in dieser README meinen `.venv/bin/python` |
| PostgreSQL 16 + `pgvector` | Datenbank `catandary`, Peer-Auth über den lokalen Socket. Die Extension muss ein Superuser anlegen |
| Node 24 | nur Frontend |
| NVIDIA-GPU, 24 GB | RTX 3090; Modelle laufen **nacheinander**, nie parallel |
| [llama.cpp](https://github.com/ggerganov/llama.cpp) | Checkout + Build unter `~/llama.cpp` (`build/bin/llama-server`), Start-Skripte `~/llama.cpp/start-*.sh`, Modelle in `~/llama.cpp/models/` |
| Docker | nur für den lokalen Apache-Test des Exports (`httpd:2.4`) |
| Ollama | installiert, **nicht** aktiv — Fallback, wenn ein Stage auf `STAGE*_BACKEND=ollama` steht |

### 3.2 Repo, Python, Datenbank

```bash
git clone git@github.com:ZuluTwoThree/catandary-trends.git
cd catandary-trends
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                      # Werte eintragen, s. 3.5

createdb catandary
sudo -u postgres psql -d catandary -c 'CREATE EXTENSION vector'
.venv/bin/python scripts/setup_db.py      # Kern-Schema (init_db, idempotent)
```

**Additive Migrationen laufen nicht automatisch** (bekannte Repo-Falle). Auf
einer frischen DB einmalig von Hand, jede idempotent:

```bash
.venv/bin/python scripts/migrate_dead_links.py           # dead_links (Link-Check --mark)
.venv/bin/python scripts/migrate_dossier_orders.py       # dossier_orders + dossiers
.venv/bin/python scripts/migrate_research_pulse.py       # research_pulse
.venv/bin/python scripts/migrate_newsletter_deep_dive.py # newsletter_editions.deep_dive
.venv/bin/python scripts/migrate_newsletter_approval.py  # newsletter_editions.approved_at/_by/_note
# weitere migrate_*.py in scripts/ (reviewed_at, status_signal, mega_trends,
# startup_explorer, research_live, press_investor_enrichment) je nach Bedarf
```

Auf der Live-DB sind alle genannten ausgeführt (Stand 04.09.2026).

### 3.3 Modelle und Start-Skripte (llama.cpp)

| Rolle | GGUF in `~/llama.cpp/models/` | Start-Skript | Kontext |
|---|---|---|---|
| Ruhezustand, Relevanz/Extraktion/Klassifikation/Reclassify | `Qwen3-8B-UD-Q4_K_XL.gguf` | `start-qwen3-8b-208k.sh` | 212 992 |
| Embeddings | `Qwen3-Embedding-8B-Q4_K_M.gguf` | `start-qwen3-emb.sh` | 8 192 |
| Content-Generierung, Newsletter, Research-Pulse-Texte | `gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf` (+ mmproj, mtp) | `start-gemma4-26b.sh` | 262 144 |
| Draft-Richter, Dossier-Rechercheur | `Qwen3.8-27B-UD-Q4_K_XL.gguf` | `start-qwen3.8-27b.sh` | bis 262 144 |
| Revert-Option Content-Gen | `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` | `start-qwen3.6-35b.sh` | 131 072 |

Die systemd-Unit `~/.config/systemd/user/llama-server.service` startet
`~/llama.cpp/start-active.sh` — einen **Symlink**, den die GPU-Handover
(`pipeline/gpu_handover.py`) für die Dauer eines Stages auf das passende
Start-Skript umhängen und danach auf `start-qwen3-8b-208k.sh` zurückstellen.
Log: `/tmp/llama-server.log` (unrotiert). Kein `--alias` in den Start-Skripten:
der Handover prüft die Modell-Identität über `/v1/models` gegen den
GGUF-Dateinamen. Wer die Unit startet, vermerkt ihre MainPID in
`data/llama-server.<job>.pid` und stoppt beim Aufräumen nur noch diesen Server;
einen Server, den ein anderer laufender Job vermerkt hat, übernimmt kein
Handover (#98, Handbuch §11.8).

```bash
systemctl --user enable --now llama-server     # Autostart via Linger
loginctl enable-linger dirk                    # einmalig, damit cron systemctl --user erreicht
```

### 3.4 Frontend

```bash
cd frontend && npm install
npx next dev --turbopack -p 3004               # Dev (ct-dev)
npm run build && npm run start                 # Prod-Build, next start -p 3001
systemctl --user enable --now catandary-frontend   # Unit: deploy/systemd/catandary-frontend.service
```

Die Unit setzt **kein** `DATABASE_URL` — das Frontend verbindet über den
Postgres-Socket (`frontend/src/lib/pg.ts`); eine TCP-URL bricht die Peer-Auth.
`frontend/.env.local` wird beim Start in den Prozess geladen (nicht in
`/proc/*/environ` sichtbar).

### 3.5 Umgebungsvariablen

`.env` (Repo-Root, Pipeline) — die Schalter, die im Betrieb zählen:

| Variable | Bedeutung |
|---|---|
| `DATABASE_URL=postgresql:///catandary` | Postgres für die Pipeline. Leer = SQLite-Fallback (nur Tests) |
| `STAGE_8B_BACKEND`, `EMBED_BACKEND`, `STAGE5_BACKEND` | `ollama` \| `llamacpp` je Stage-Gruppe; `scripts/scheduled_cycle.sh` setzt alle drei auf `llamacpp`, sobald die Start-Skripte existieren |
| `CLASSIFY_BACKEND` | `ollama` \| `llamacpp` \| `anthropic` (Stages 2/3/4/8 off-GPU, kostet API) |
| `RSS_CLASSIFY_MODE=hybrid` | Distill-Heads entscheiden Relevanz/Vertikale/Mega/PESTEL, nur das unsichere Band geht ans 8B; `llm` = alter Vollpfad |
| `CYCLE_MAX_PER_SOURCE=200` | Mengenbremse je Quelle und Lauf |
| `EXTRACTION_STRICT=1` | Extraktion mit Wörtlichkeitsfilter |
| `AUTO_PUBLISH_GROUNDING_GATE=1` | Grounding-Gate vor Auto-Publish (Handbuch §3) |
| `DRAFT_JUDGE=1` | Stage 10 Draft-Richter (0 = aus; nur in `scheduled_cycle.sh` gelesen) |
| `TDM_RESPECT=1` | Fetcher beachtet maschinenlesbare TDM-Vorbehalte |
| `DOSSIER_MEASURE=0` | Dossier ohne Messkette (alter Pfad, reproduzierbar) |
| `DOSSIER_DR=0` | Dossier OHNE DR-Vorlauf (Primärquellen zuerst, Faktenzettel, Kalender-Kandidaten — Default AN seit 2026-09-13) |
| `DOSSIER_WRITER_MODEL`, `DOSSIER_WRITER_TIMEOUT` | Schreibphase (Sektionen, Leser, Neuwurf) auf einem anderen Modell — GGUF-Name aus `gpu_handover.MODEL_START_SCRIPTS`, z. B. `Qwen3.8-Flash-Next-UD-Q2_K_XL-00001-of-00003.gguf` (125B/6B MoE, Test seit 2026-09-14); Client-Timeout dafür 1800 s |
| `DOSSIER_WRITE=single` | Dossier in EINEM Schreibaufruf (Best-of-2) statt Sektion für Sektion (Default `sections` seit 2026-09-14) |
| `DOSSIER_READER=0` | Dossier ohne den Leser (zweiter Blick desselben Modells mit eigener Anweisung: Einwände in den Neuwurf, Resthinweise in den Prüfnachweis; Default an seit 2026-09-13) |
| `DOSSIER_DRAFTS`, `DOSSIER_REWRITES` | Best-of-N im Erstentwurf (Default 2) und Zahl der gezielten Neuwürfe (Default 2 = ein Nachzug für Strukturbefunde) |
| `NEWSLETTER_DEEP_DIVE` | `dry-run` aktiviert den Deep-Dive-Schritt im Montagslauf (nur in der Crontab setzen, s. Handbuch §7.3) |
| `RESEND_API_KEY`, `NEWSLETTER_FROM`, `NEWSLETTER_UNSUB_SECRET`, `NEWSLETTER_PUBLIC_BASE`, `NL_EXPORT_URL`, `NL_EXPORT_TOKEN` | Newsletter-Versandkette (#16) |
| `NEWSLETTER_APPROVER` | Name, der als Freigebender in `approved_by` landet (Default `owner`); Frontend-Env |
| `REVIEW_NOTIFY_TO`, `REVIEW_URL` | Empfänger und Link der Morgen-Mail |
| `BRAVE_SEARCH_API_KEY`, `FIRECRAWL_API_KEY` | Web-Stufe des Rechercheurs bzw. Backfill |
| `WEB_SEARCH_BACKEND`, `SEARXNG_URL` | Web-Suche des Rechercheurs (seit 2026-09-13): `auto` = Brave zuerst, bei 402/429/5xx/Netzfehler oder ohne Schlüssel SearXNG (Docker `searxng`, 127.0.0.1:8888, `deploy/searxng/settings.yml`); `brave`/`searxng` erzwingen |
| `WEB_CACHE`, `WEB_CACHE_SEARCH_TTL_HOURS`, `WEB_CACHE_PAGE_TTL_HOURS`, `WEB_CACHE_PATH` | Cache der Web-Stufe (seit 2026-09-12): Brave-Treffer 72 h, Seitentexte 7 Tage in `data/web_cache.sqlite`; `python -m pipeline.web_cache stats\|purge\|clear` |
| `OPENALEX_API_KEY`, `EPO_OPS_*`, `EPO_LOGIN`/`EPO_PASSWORD` | Akquise-APIs |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL_CLASSIFY` | nur für `CLASSIFY_BACKEND=anthropic` |
| `PUBLISH_CONFIG` | Pfad der Webspace-Config (Default `~/.config/catandary/webspace.env`) |

`frontend/.env.local` (Frontend):

| Variable | Bedeutung |
|---|---|
| `PUBLIC_MODE=1` | Instanz verhält sich wie die öffentliche Seite (Blockliste `lib/publicMode.ts`, Fenster `PUBLIC_WINDOW_DAYS`) — nur für die :3999-Vorschau |
| `DOSSIERS_ENABLED=0` | Not-Aus für den Dossier-Desk (Default an) |
| `AUTH_SECRET` | signiert die Newsletter-Abmelde-Tokens (≥ 16 Zeichen) |
| `PUBLIC_BASE_URL` | App-Origin für den Same-Origin-Check der POST-Routen |
| `CONTACT_EMAIL` | Adresse hinter `/enquiry` (Default `trends@catandary.de`) |
| `OPENALEX_API_KEY` | Live-Suche im Research Explorer (25 Live-Treffer/Tag, serverseitig) |
| `TRUST_PROXY` | nur hinter einem eigenen Proxy auf 1 — hier 0 |

Build-Variablen des Exports (`STATIC_EXPORT`, `PUBLIC_NOINDEX`,
`PUBLIC_WINDOW_DAYS`, `PUBLIC_SITE_URL`, `PUBLIC_NEWSLETTER_EDITIONS`) setzt
`scripts/build_public_static.sh` bzw. die Webspace-Config — Handbuch §9.

---

## 4. Architektur in einer Seite

```
   AKQUISE (Lead-Time-Tiers)              VERARBEITUNG                          PRODUKT
┌────────────────────────────────┐  ┌──────────────────────────────┐  ┌──────────────────────────────┐
│ science  OpenAlex (45M Werke,  │  │ Full Cycle Mo–Fr 04:00       │  │ Owner-App :3001 (Next.js 16) │
│          Fresh-Sweep), arXiv/  │  │  Poll → Titel-Dedup →        │  │  Feed · Review · Mega ·      │
│          bioRxiv/medRxiv       │  │  Relevanz/Extraktion/        │  │  Foresight-Cockpit ·         │
│ patent   EPO DOCDB Back-File   │─▶│  Klassifikation (Distill +   │─▶│  Dossier-Desk · Newsletter   │
│          (18,7M, 112M Zitate)  │  │  8B) → Embedding-Dedup →     │  │                              │
│ funding  NSF/NIH/OpenAIRE/UKRI │  │  Content EN (Gemma-26B) →    │  │ Statischer Export → Hetzner  │
│          SEC Form D, SBIR,     │  │  Reclassify → Auto-Publish   │  │  Webspace: /trends (30 Tage) │
│          CORDIS                │  │  (≥ 0,85 + Grounding-Gate) → │  │  + Mega + Newsletter-Archiv  │
│ market   ~560 RSS-Quellen,     │  │  Draft-Richter (27B)         │  └──────────────────────────────┘
│          Presseverteiler,      │  │ Wochen-Ingester Sa 06:00     │
│          Newsrooms             │  │  (Distill-Pfad, GPU-frei)    │
└────────────────────────────────┘  └──────────────────────────────┘
        alles in PostgreSQL 16 + pgvector · alle Modelle lokal auf llama-server :8090
```

**Taxonomie.** Acht Vertikale (`FOOD TECH HEALTH ECO DESIGN FASHION BIZ
LIFESTYLE`), PESTEL-Dimensionen quer dazu, 28 kuratierte Mega-Signal-Themes
(`mega_trends.yaml`), und je Signal ein **Lead-Time-Tier** (science → patent →
funding → market). Die CPC-Patentklassifikation ist die gemeinsame
Technologie-Achse: jedes Signal jeder Ebene wird per Embedding auf CPC
projiziert, dadurch sind Forschung, Patente, Funding und Markt für eine
Technologie übereinanderlegbar.

**Pipeline-Stufen** (`pipeline/llm_processor.py`, Orchestrator
`pipeline/run_full_cycle.py`, Cron-Wrapper `scripts/full_cycle_cron.sh` →
`scripts/scheduled_cycle.sh`): 1 Titel-Dedup (rapidfuzz) · 2 Relevanz-Gate
(Distill-Head, Band 0,3–0,7 ans 8B) · 3 strukturierte Extraktion (8B,
Zahlen deterministisch per Regex aus der Quelle) · 4 Klassifikation
(Distill-Heads) · 5 Embedding + Dedup (Cosine > 0,92) · 6 Artikel EN
(Gemma-4-26B, ~100 Wörter, immer Englisch) · 7 Insert `draft` · 8 Reclassify
(8B) · 9 Auto-Publish (Confidence ≥ 0,85, **Grounding-Gate**: erfundene Zahlen
oder Jahre → Hold) · 10 Draft-Richter (Qwen3.8-27B beurteilt die Drafts unter
der Schwelle, gibt frei oder hält, verwirft nie). Zwischen den Stufen wechselt
`pipeline/gpu_handover.py` das Modell auf `:8090` (Symlink + VRAM-Check +
Identitäts-Check); die Stages 2/3/4/6/8 prüfen zusätzlich vor jedem Request
und Retry, dass `:8090` noch ihr Modell serviert, und brechen sonst ab, ohne
Einträge zu verlieren (#98, Handbuch §11.5 Punkt 7).

**KI-Kennzeichnung (#99, EU AI Act Art. 50 Abs. 4).** Die Stufen 9/10 sind
reine Maschinen-Gates — auch der Draft-Richter ist ein Modell —, ein Feed-Artikel
wird also von keinem Menschen gelesen, bevor er erscheint. Jede Seite
`/trends/<slug>` trägt deshalb direkt unter dem Titel ein aufklappbares
Kennzeichen (`frontend/src/components/AiArticleDisclosure.tsx`, natives
`<details>`, funktioniert ohne JS): sichtbar „AI-generated / not reviewed by a
person", darin der volle Satz `ARTICLE_DISCLOSURE_EN`
(`frontend/src/lib/aiDisclosure.ts`). Maschinenlesbar dazu — mangels Standard
pragmatisch gewählt — `<meta name="generator">` und im Article-JSON-LD
`creator` = `SoftwareApplication` neben `author` = Organization plus `isBasedOn`
= Quell-URL. **Nicht** betroffen: der Newsletter (dort greift die Freigabe durch
einen Menschen, `AI_DISCLOSURE_EN`) und `/analysis` (schreibt der Owner selbst).
Handbuch: [§12, KI-Kennzeichnung](docs/owner_manual.md#ki-kennzeichnung-der-artikel-99).

**Distill-Pfad** (`pipeline/distill.py`, `scripts/signal_batch*.py`): lineare
Heads auf den 4096-dim-Embeddings ersetzen die LLM-Klassifikation für den
Massen-Ingest; Ergebnis sind `status='signal'`-Zeilen ohne Artikel — der
Rohstoff der Foresight-Werkzeuge. Fällt der Embedding-Server aus, bleibt der
Rest des Laufs unverarbeitet (Retry desselben Chunks, nach 20 Fehlern in Folge
Exit 3) statt als `embedding_error` aussortiert zu werden (#98). Retrain: `scripts/train_distill_heads.py`
(auch automatisch im Sonntag-Discovery-Loop, wenn `mega_trends.yaml` geändert
wurde).

**Datenmodell-Kern** (`pipeline/db.py`): `sources` (Registry, gespiegelt aus
`sources.yaml`), `raw_entries` (21,6 Mio.; `raw_content` nach 14 Tagen
geleert), `trends` (Artikel und Signale; `status` draft/published/rejected/
signal, `embedding` 4096 + `embedding_1024` HNSW, `auto_published`,
`reviewed_at`, `judged_at`), `newsletter_editions` (+ `deep_dive` JSONB,
+ `approved_at`/`approved_by`/`approval_note` = Freigabe-Gate des Versands),
`dossier_orders` + `dossiers` (slug + version), `research_pulse`,
`research_signals`/`research_corpus`, Patent-Graph (`patent_links`,
`patent_cpc_full`, `patent_search`), `foresight_runs`/`foresight_clusters`,
`cpc_tier_series`, `dead_links`, `startup_companies`.

**Backends.** Produktiv läuft der gesamte Cycle auf llama.cpp (`:8090`); Ollama
(`:11434`) ist Default in `config.py`, aber nicht gestartet. `CLASSIFY_BACKEND=
anthropic` kann Stages 2/3/4/8 off-GPU schicken (historischer Backfill).
Details, Referenzwerte und Entscheidungshistorie: `CLAUDE.md`.

---

## 5. Tests und Konventionen

```bash
.venv/bin/python -m pytest tests/           # 742 Tests (05.09.2026); conftest erzwingt SQLite — kein Postgres nötig
.venv/bin/python -m pyflakes pipeline/ scripts/
cd frontend && npx vitest run               # 386 Tests in 37 Dateien
cd frontend && npx tsc --noEmit             # 0 Fehler
cd frontend && npm run lint
```

Vitest-Wächter, die man kennen sollte: `staticExport.test.ts` (Blockliste
`publicMode.ts` ↔ `static-export.exclude`), `aiCrawlers.test.ts` (Crawler-Liste
↔ `.htaccess`-Regex), `dossier-access.test.ts`, `newsletterEditions.test.ts`
(Render-Regel Deep Dive). Python: `tests/test_query_gate.py` (Fixture mit
Live-Vektoren; nach einem Embedding-Modellwechsel neu messen mit
`scripts/measure_query_gate.py`), `tests/test_publish_static_site.py`
(75 Tests inkl. SFTP-E2E gegen einen lokalen sshd).

**Branches.** `main` = die deployte :3001-Instanz („save"), `dev` =
Integrationsbranch (Worktree `~/projects/ct-dev`). Auf `dev` committen und
pushen; `main` nur bewusst per Merge aktualisieren und danach :3001 neu bauen.
Vor Commits im jeweiligen Worktree `git branch --show-current` prüfen — ein
Build im falschen Worktree ist grün, wirkt aber nicht. Radar-Arbeit liegt
geparkt auf `feature/radar-rebase`.

**Commits.** `feat: / fix: / refactor: / test: / docs: / chore:`, Scope in
Klammern (`feat(frontend): …`). Nie `git add -A` — im Repo liegen bewusst
untracked Arbeitsstände (z. B. Deep-Dive-Drafts unter
`frontend/content/analyses/`).

**Doku-Regel (konstitutionell).** `CLAUDE.md`, diese README und `docs/`
spiegeln die **tatsächlichen** Bedingungen. Wer Modelle, Defaults, Cron,
Schema oder Pipeline-Verhalten ändert, zieht die Doku im selben Commit mit —
und verifiziert gegen Code/Cron/Instanz statt alte Doku fortzuschreiben.

**Engineering-Regeln.** Batch-Inserts für alles im Backfill-Maßstab; den
112M-Kanten-Zitationsgraph nie in den RAM laden (SQL-scoped); PG-Wrapper-Zeilen
sind Dicts (`r["col"]`); literales `%` in parametrisiertem SQL als `%%`; NUL
aus Fremdtext strippen; Pydantic + 3 Retries um jeden LLM-Call; Qwen3 mit
`enable_thinking=false`.

---

## 6. Launch-Checkliste Owner

Aus `docs/launch/09_launch_plan_2026-09-02.md`; Reihenfolge = Abhängigkeit.

1. **Webspace-Zugang anlegen:** `~/.config/catandary/webspace.env` (chmod 600;
   Vorlage in 2.9) mit SFTP-Host/User/Passwort aus konsoleH. Klären: hat das
   Paket SSH/rsync? Speicher-/Inode-Quota (Export ≈ 33 000 Dateien, 1,3 GB)?
2. **Erstupload:** `scripts/build_public_static.sh` → `publish_static_site.py`
   (Dry-Run) → `--apply` (Stunden über SFTP). Danach die `.htaccess`-Checks aus
   `frontend/public-export/trends/.htaccess` (Kommentarblock am Ende) und die
   TDM-Checks aus Handbuch §12 gegen `https://catandary.de/trends/` abarbeiten.
3. **Root-`.htaccess` ergänzen:** Inhalt von `docs/launch/root-htaccess.snippet`
   in die owner-verwaltete Root-Datei (TDM-Header + Bot-Sperre für Landing und
   `/newsletter/`).
4. **Cron installiert (05.09.2026):** `15 3 * * *  scripts/publish_static_site.sh` — täglich nach dem Review-Tag, rund 45 min vor dem 04:00-Cycle
   aus `deploy/crontab.txt` in `crontab -e` übernehmen. Der Wächter (07:45)
   prüft ab dann `data/publish_last.json`.
5. **Newsletter-PHP nachziehen:** `_lib.php`, `unsubscribe.php`, `nl_config.php`
   (Block 5 `unsub_secret` = `NEWSLETTER_UNSUB_SECRET` in `.env`), `export.php`
   — Reihenfolge und Prüfungen in
   `docs/launch/newsletter-doi-php/NEWSLETTER_GOLIVE.md`. Erst Export
   publizieren, dann das PHP hochladen (Redirect-Ziel
   `/trends/newsletter/unsubscribed`).
6. **Landing:** `docs/launch/preview.html` als `index.html` hochladen; die
   SaaS-Preistabelle und der „Explore the live engine"-CTA darin sind noch
   nicht auf „Analysen statt Plattform" umgeschrieben (#93, Owner-Stimme).
   Countdown-Datum steht an **zwei** Stellen in der Datei.
7. **Indexierung zum 01.10.:** `PUBLIC_NOINDEX=0` in `webspace.env`, nächster
   06:30-Export liefert `robots.txt` ohne Disallow-all und Seiten ohne
   `noindex`; `noindex`-Meta aus der Landing entfernen.
8. **Owner-Entscheide, die noch offen sind:** Owner-Instanz auf Loopback binden
   (Handbuch §12); Firecrawl-Key rotieren (stand in der Git-Historie); 30 vs. 60/90 Tage
   Fenster; Tracking (Empfehlung: keins); Verbleib der ~4,4 Mio. F-Term-Altzeilen
   (#79); `/analysis` auf der Live-Site (Root-Datei wird nicht hochgeladen —
   entweder von Hand mit der Landing oder Route nach `/trends/analysis`
   verschieben).
9. **Rechtstexte:** `/imprint`, `/privacy` (Export: `/trends/imprint`,
   `/trends/privacy`) sind Entwürfe ohne anwaltliche Prüfung
   (`docs/legal/README.md`); Impressums-Adressblock ist Owner-Gate.
