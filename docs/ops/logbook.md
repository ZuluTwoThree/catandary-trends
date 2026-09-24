# Ops-Logbuch

Protokoll und Planung von Läufen und Hardware — angezeigt auf `/trends/ops`
(#104). Ein Eintrag = eine `##`-Überschrift mit festem Kopf:

    ## <Datum> · <Art> · <Titel>

Datum `YYYY-MM-DD`, optional mit Uhrzeit `YYYY-MM-DD HH:MM`; für Ideen ohne
Termin reicht `YYYY-MM`. Arten: **change** (ist passiert), **plan** (mit Datum —
erscheint im Wochenplan der Seite), **decision**, **idea**. Direkt unter der
Überschrift dürfen `schlüssel: wert`-Zeilen stehen, die der Wochenplan liest:
`duration: 3h` (auch `45m`, `2h30m`, `1d`) und `gpu: local|bequiet`. Danach
Freitext in Markdown. Neueste Einträge oben ist Konvention, die Seite sortiert
selbst. Bearbeiten im Editor, committen — keine zweite Wahrheit in der DB.

## 2026-09-24 · change · Vier Issues geschlossen, Pulse W35 nachgerechnet
duration: 1h
gpu: local
Issue-Audit über die 27 offenen Issues: fünf waren ohne Owner-, Anwalts- oder
Mehrtages-Gate abschließbar. Geschlossen: #95 und #96 (mit dem Dossier-Rückbau
vom 19.09. gegenstandslos), #67 (Query-Quality-Gate, 18 Tests grün, Rest ist ein
Betriebshinweis in der Doku), #73 (Research Pulse: Merge da, `kind` ohne NULL,
Cron seit 18.09.). Für #73 die Woche W35 komplett nachgerechnet — bis heute hatte
nur das AI-Theme einen Text: 28 Themes, 18 mit Text, 10 unter 5 Papers, 0 Fehler,
62 s, ein Handover, Ruhezustand danach verifiziert. #79: die 4.421.765
JP-F-Term-Zeilen (`patent_cpc.subclass IS NULL`, 235.898 Patente, alle mit
CPC daneben) hat der Owner von Hand gelöscht — der Befehl war in der
Agent-Sitzung als Massenlöschung blockiert; Issue geschlossen. Wirkung: die
Pseudo-Klassen wie `5C15` verschwinden beim nächsten Rebuild aus
`cpc_cooccurrence` (397.128 von 1,52 M Paaren) und aus der SPNP-Sektionswahl.
Im selben Zug (Owner-Freigabe) die 1.490.819 japanischen FI-Zeilen bereinigt,
die seit dem Backfill vom 02.09. zwar eine Subclass hatten, im Feld `cpc` aber
noch die Editionsziffer trugen (`4H04N19/463`): 1.197.137 per UPDATE auf den
Code ohne Ziffer (1 min 46 s), 293.682 gelöscht, weil dasselbe Patent den Code
schon als CPC-Zeile hatte (20 %, Unique-Index). Kein Code in `patent_cpc`
beginnt mehr mit einer Ziffer. Wirksam wird das in Kookkurrenz, SPNP-Sektion
und `assign_cpc` beim nächsten Rebuild; `cpc LIKE 'H04N19/%'`-Suchen finden
diese JP-Patente ab sofort (FI-Gruppe als CPC-Gruppe, auf Subclass-Ebene exakt).
Kein Cron-Pfad berührt, kein Merge nötig.

## 2026-09-25 · change · Signaltyp-Head gebaut (#110), Karte + Export-Filter auf dev
duration: 2h
gpu: nein
Block 2 der Nacht (Owner-Go 24.09. 23:50). Fünfter Distill-Head für den Signaltyp
von Presse-Signalen: `scripts/train_signal_type_head.py`, Teacher 552.964
LLM-gelabelte Presse-Zeilen vor dem 14.07., Laden 288 s, Training 2 × ~95 s,
CPU, 9 GB RAM, kein Cron berührt. Holdout balanced: Genauigkeit 0,80 gesamt,
0,88 ab Konfidenz 0,6 (76 % der Zeilen), 0,92 ab 0,7; Makro-F1 0,67 (plain 0,62,
findet aber nur ein Viertel der seltenen Klassen). Auf den 48.217 Presse-Zeilen
seit dem 14.07. (heute alle market_shift) vergäbe der Head bei Boden 0,6:
market_shift 64 %, regulation 18 %, product_launch 13 %, partnership 3,6 %,
consumer_behavior 1,8 % — historisch 71/12/13/2,4/1,6. Verdrahtet hinter
`DISTILL_SIGNAL_TYPE=1` (Default AUS, Boden 0,6), Regel bleibt für
patent/research/funding; `signal_batch` nutzt dieselbe Funktion statt einer
Kopie. Frontend auf dev: Label auf der Karte, `signal` im Suchindex, Chip-Gruppe
in der Export-Suche. Gates: pytest 1.272 + 3 neue, vitest 485, tsc 0. Bericht
`docs/signal_type_head_2026-09-25.md`. Offen (Owner): einschalten (Cron-Env →
main-Merge, Head kopieren), Bestand seit 14.07. nachziehen (Stufe 2).

## 2026-09-25 07:00 · plan · Nach dem Nachtlauf entscheiden: vier offene Punkte

Erster Lauf mit den drei Änderungen vom 24.09. Zuerst die Zahlen ansehen:
`~/logs/catandary-full-cycle-20260925-0245.log` (Endzeit, erwartet ~06:55 statt
07:42), `data/draft_judge_last.json` (Kategorien — `source_mismatch` sollte
deutlich unter den 103 von 600 der Vornacht liegen) und die Stage-Dauern im
`catandary-scheduled-`-Log (Stage 8 erwartet ~6 statt 63 min, Stage 10 ~32
statt 22 min, Stage 6 rund 14 min kürzer).

**1. Signaltyp-Regression vom 14.07. — der eigentliche Fund.**
`llm_processor._distill_signal_type` leitet den Signaltyp seit der Umstellung auf
die Distill-Heads allein aus der Quellenart ab: Patentnummer → `patent`,
Forschungsquelle → `research`, NSF/NIH/UKRI → `funding`, **alles andere →
`market_shift`**. Seit dem 14.07. bekommt damit jeder Fachpresse-Artikel
`market_shift`; `product_launch`, `partnership`, `regulation` und
`consumer_behavior` wurden seither nie wieder vergeben (Bestand davor: 89.337 /
13.447 / 76.262 / 9.786). Folge: die acht per A/B-Test eingeführten
Schreibanweisungen in `SIGNAL_TYPE_FRAMING` kollabieren auf eine einzige — eine
Partnerschaftsmeldung wird als Marktverschiebung geschrieben, und der
Draft-Richter beanstandet sie folgerichtig als „kein Signal" (3 von 10
`no_signal`-Fällen der Stichprobe vom 24.09.). Betrifft außerdem jede Auswertung,
die nach Signaltyp filtert. Beispiele: #1799132 Laifen Swift 04 (Fashionista),
#1766361 WestJet × Tim Hortons (Retail Insider), #1766817 Bluegrass Ingredients
(Prepared Foods). Offen: Signaltyp wieder aus dem Inhalt bestimmen — eigener
Distill-Head, Regelwerk auf der Extraktion oder zurück ans 8B.

**2. Restliche Entwürfe im Fenster.** 3.048 mit kurzer Quelle. Empfehlung:
liegenlassen — bei Quellen unter 4.000 Zeichen konnte die Kappe gar nicht
irreführen.

**3. Die 4.113 Alten außerhalb des 30-Tage-Fensters.** Liegenlassen, prüfen
oder auf `rejected` abräumen. Sie kosten seit dem 24.09. keine Rechenzeit mehr
und sind öffentlich unsichtbar (das Fenster filtert auf `sort_date`).

**4. Ergebnis des Nachlaufs vom 24.09. abnehmen.** 1.942 Entwürfe mit Quelle
> 4.000 Zeichen wurden mit der neuen Textbasis neu beurteilt,
`data/draft_judge_rejudge.json`.

Erledigt am 24.09. und ab dieser Nacht scharf: Stage 8 nur noch für neue
Entwürfe · Wort-Untergrenze nur ab 1.000 Zeichen Quelle · Richter liest 12.000
Zeichen + Extraktion · kein Pflicht-Ausblick am Artikelende mehr.

## 2026-09-22 · change · Wochentags-Kette startet 1 h 15 min früher

Owner: der Nachtlauf war beim Frühstück noch nicht fertig, das Review musste warten.
Ursache ist der Quellenausbau auf 560 Feeds — gemessen (ops_events, 30 Tage) dauert
der Full Cycle jetzt 3:48–5:26 statt knapp 3 h und endete zuletzt 08:44–09:24.
Verschoben: 02:45→01:30 Backup, 03:15→02:00 Static Export, 03:30→02:15 Retention,
03:45→02:30 Lizenz-Auflösung, 04:00→02:45 Full Cycle, Di 05:00→03:45 Patent-Sweep,
Di 08:00→06:45 Patent-Rechnungen, Di 09:00→07:45 Newsletter-Edition. Reihenfolge und
Abstände bleiben, der Export veröffentlicht weiter den am Vortag freigegebenen Stand.
Nicht verschoben: der Wächter (07:45) — er meldete bisher jeden Werktag fälschlich
"still running" (Log 21./22.09.), weil der Cycle um 07:45 noch lief; mit dem früheren
Start findet er einen fertigen Lauf vor. Wochenend- und Monatsjobs unberührt.
duration: Full Cycle 228–326 min (Median 299)

## 2026-09-19 · decision · Scouting-Dossiers entfernt

Owner: „Das Feature trägt nicht." Nach 30 Runden, sieben Versionen zu einem Thema und
48 Läufen war das Muster stabil — alles Gemessene hält, alles vom Modell Geschriebene
wackelt, der Leser war nie zufrieden. Desk `/trends/dossiers`, Korpus-Rechercheur, Advisor,
alle `dossier_*`-Module/Skripte/Tests, die Prompt-Gruppen `dossier`/`advisor` und der
Deep-Dive-Rechercheur des Newsletters (schreibt jetzt `status: "disabled"`) sind aus `dev`
und `main`. Bleiben: Web-Suche/-Cache, Rechtstext-Slicer, PDF-Abruf, Prompt-Katalog,
CPU-Embedder `:8091`, `detachedSpawn.ts`; DB-Tabellen stehen (kein DROP). Rückweg: Tag
`archive/dossiers-2026-09-19`. Nachfolge-Idee „Field Watch":
`docs/value_proposition_field_watch_2026-09-19.md`, #108. Keine GPU-Läufe im Rückbau.

## 2026-09-18 · change · Dossier: Einstieg „What this is about" als achte Pflichtsektion

Owner-Wunsch: Hintergrund für Fachfremde am Anfang jedes Dossiers — was die Technologie
ist, warum sie für die Frage zählt. 60–220 Wörter, keine Zahlen/Daten, außerhalb der
Faktenquote, geschrieben nach den Beleg-Sektionen. Workflow-Befund über v1–v4 mit zehn
Punkten in docs/agentic_dossiers.md Runde 21.

## 2026-09-18 · change · Prompt-Katalog /trends/ops/prompts

Owner-Seite neben Ops: alle 28 Systemanweisungen der LLM-Prozesse live aus dem Code,
je mit Funktionsbeschreibung, Modell, Auslöser, Datei:Zeile. Nebenfund und Fix:
`corpus_research.PROFILE_SYSTEM` war doppelt definiert — die Suchrichtungen jedes
Dossiers liefen unter der Firmenprofil-Anweisung (jetzt `COMPANY_PROFILE_SYSTEM`).

## 2026-09-18 · change · Dossier-Rechercheur: PDFs lesbar, Kalender-Auffüller mit Primärlatte

Anlass datacenter-virtualization v1/v2 (Aufträge 39/40, je 33 min). Drei Harness-Fehler
behoben: PDFs kamen als too_short zurück (BSI SYS.1.5 viermal gefunden, nie gelesen — jetzt
pypdf), der Kalender-Auffüller trug Rang-2-Werbetext mit nackter Jahreszahl ein (jetzt Rang
≤ 1 + präziser Termin), Streichung ließ leere „|"-Zeilen (Tabellenzeile = eine Aussage).
Brave: metered, kein Monatsdeckel; 919 Aufrufe im September. Cache too_short geleert.

## 2026-09-18 · change · Research Pulse: Samstags-Cron installiert, W36/W37 nachgerechnet

Die Seite stand seit dem 05.09. auf W35: der Cron `0 12 * * 6 weekly_research_pulse.sh`
war nur ein auskommentierter Vorschlag, der Knopf rechnet ein Theme und wurde nicht
gedrückt. W36 und W37 von Hand nachgerechnet (58 s / 54 s, je 19 von 28 Themes mit Text,
0 Fehler). Cron installiert (Owner); der Wrapper schreibt jetzt auf jedem Ausgang eine
Notiz für die Montags-Morgen-Mail.

## 2026-09-16 · change · robots-Prüfer ignorierte jede Regel mit Fragezeichen

Bei der Quellenprüfung von sciencealert.com meldete unser Prüfer die
WordPress-Schnittstelle `/?rest_route=` als **erlaubt**, obwohl robots.txt sie
ausdrücklich sperrt. Ursache in `article_fetcher._rule_regex`: die Regelseite
kodierte das `?` zu `%3F`, während `robots_allows` den Query der URL roh
anhängt. Die beiden konnten sich nie treffen, also war **jede query-basierte
Regel wirkungslos** — `Disallow: /*?utm_source=`, `/?rest_route=`, `/*?s=`.

Ein Zeichen in der safe-Liste behebt es. Nachgemessen: **117 von 380 aktiven
Quellen-Hosts** führen solche Regeln. Kehrseite geprüft, damit der Fix keine
Abdeckung kostet: von 1.200 Artikel-URLs der letzten 14 Tage mit Query wird
**keine einzige** neu gesperrt — die Regeln zielen auf Such- und
Tracking-Parameter, unsere Feed-Links tragen die nicht.

Zwei Regressionstests in `test_probe_source_compliance.py`.

## 2026-09-16 · change · Plattentemperatur: Grenzwerte aus den Datenblättern, Laufwerk als Kronzeuge

Anlass: wiederholte Mails „nvme0n1: 65.8 °C, limit 65 °C". Nachgeprüft, was
verbaut ist und was die Laufwerke selbst sagen:

| Gerät | Modell | Betrieb laut Datenblatt | jetzt |
|---|---|---|---|
| nvme0n1 | Kingston NV2 500 GB | 0–70 °C | 48 °C |
| nvme1n1 | Lexar NM790 2 TB | 0–70 °C | 42 °C |
| sda | Seagate Barracuda ST2000DM008 | 0–60 °C | 37 °C |
| sdb | Kingston A400 240 GB | 0–70 °C | 35 °C |

Der Alarm lag mit 65 °C **unter** dem, was ein DRAM-loses NVMe unter Dauerlast
normal erreicht. Neue Grenzen: SSD/NVMe **68**, HDD **55** — jeweils knapp unter
dem Datenblatt, nicht darüber.

Der eigentliche Fund steckt aber in den Laufwerken selbst: sie zählen mit, wie
viele Minuten sie über **ihrer eigenen** Warn- und Kritisch-Schwelle lagen.
nvme0n1 meldet dort **0 und 0** — es hat bei 65,8 °C nie gewarnt. nvme1n1 dagegen
meldet **314 Minuten über Warn- und 1 Minute über Kritisch-Schwelle** bei erst
255 Betriebsstunden, und davon hat unser Alarm nie etwas gesagt.

Der Sampler liest diese Zähler jetzt mit (`warning_temp_time`,
`critical_comp_time`), und eine Regel schlägt an, wenn sie **steigen** — dieselbe
Logik wie bei den Sektorfehlern. Damit hängt die Warnung am Urteil des
Herstellers statt an einer Zahl von uns.

## 2026-09-16 · change · Emerging: vier Ebenen statt einer Zeitachse

Owner-Einwand: ein Wissenschaftstrend ist nicht dasselbe wie ein Markttrend,
auch bei gleichem Thema. Perowskit wird erforscht, patentiert, gefördert und
erst dann am Markt diskutiert — vier Gespräche, vier Anfänge. Der Detektor
datierte bisher das früheste und nannte es den Trend; genau das erklärt die
unglaubwürdigen +26 Monate aus dem Rücktest.

- `pipeline/tiers.py` ordnet jede Zeile einer Ebene zu (Zwilling der
  SQL-`TIER_FILTERS`), der Archiv-Scan zählt je Monat **und Ebene**. Jedes Nest
  trägt jetzt vier Erstauftritte, die Reihenfolge und den Abstand
  Wissenschaft → Markt.
- **Befund, der den Rest erklärt:** die Einbettung kodiert den Sprachstil mit.
  „perovskite tandem solar cells" trifft in 400.000 Dokumenten 146 Forschungs-
  und 2 Marktzeilen. Die Ebene lässt sich deshalb nicht nachträglich aus einem
  gemeinsamen Nest lösen.
- Konsequenz: Scope `tier:<t>` (`--all-tiers`), jede Ebene für sich geclustert.
  Die Marktebene liefert dann echte Marktgespräche (Smart Glasses · Privacy
  Concerns, EU Regulations · Regulatory Delay, Sugar Tax · Public Health) und
  braucht feinere Zellen: 5 Nester bei 207 Dok/Zelle, 46 bei 69. Der Lauf merkt
  das selbst und rechnet einmal nach.
- Akteure statt Artikel: verschiedene Firmen in den Markt-Ähnlichen, früh gegen
  spät. Untergrenze, weil nur 13 % der Fachpresse-Zeilen einen extrahierten
  Namen tragen — steht so auf der Karte.

Reiter „by conversation" auf `/trends/foresight/emerging`. Additive Spalten,
Live-DB. Kein Cron. `docs/emerging_nests_2026-09-15.md`.

## 2026-09-15 · change · Emerging: Namen vom Modell und der erste Rücktest

Punkte 5 und 6 der Trendfindungs-Liste, auf Owner-Auftrag.

**Namen.** `pipeline/nest_naming.py` lässt das lokale Modell die
zentrumsnächsten Titel eines Nests lesen und benennen. Jedes bedeutungstragende
Wort muss im Nest vorkommen, sonst fällt der Name durch und das Schlagwort-Label
bleibt — dieselbe Grounding-Regel wie bei den Artikeln. Namen sind je Lauf
eindeutig, Patenttitel schreien nicht mehr. 311 von 328 Nestern benannt; aus
„World · Action" wurde „World-Action Models", aus „Defect Passivation · Electron
Selective Layer" „Self-Assembled Monolayers for Perovskite Solar Cells". Die
Karte zeigt beides. Einziger GPU-Schritt der Schicht, ~0,2 s je Nest.

**Rücktest.** `scripts/validate_emerging.py` + `known_trends.yaml`: 21 Stichtage
2021-07 bis 2026-09, 20 datierbare Trends, drei Gegenproben. **9 von 20
gefunden, 5 vor dem Mainstream, Median-Vorlauf 6 Monate**, Gegenproben nie über
0,62.

Der Test hat sich dabei selbst korrigiert: in der ersten Fassung meldete er 15
von 20 und 23 Monate Vorlauf, weil ein einziges Nest „Machine Learning · Neural
Networks" nahe genug an drei verschiedenen KI-Trends lag. Seitdem muss das
getroffene Nest ein Kennwort des Trends auch wirklich enthalten. Bei fünf
Trends fand der Test nicht einmal das Feld (Wärmepumpen, Psychedelika, Quiet
Luxury, Hyrox, Inferenz-Effizienz) — das ist ein Quellen-, kein
Erkennungsproblem, dieselbe Lücke wie bei den dünnen Vertikalen.

Ehrliche Lesart im Doku-Abschnitt gleichen Namens: die verfolgenswerte Zahl ist
die Trefferquote, nicht der Vorlauf.

## 2026-09-15 · change · Zweite Schicht: Emerging-Nester (was ist neu statt was ist laut)

Auf die Owner-Frage „was müsste man tun, dass wirklich Trends entdeckt werden?"
gebaut, **neben** der Cluster-Schicht, nicht statt ihr. k-Means teilt den
Bestand restlos auf, also ist jede Zelle ein Themengebiet; ein Trend ist die
umgekehrte Form, eine kleine dichte junge Stelle, zu der der Rest nicht gehört.

- `pipeline/emerging.py` + `pipeline/emerging_snapshot.py`: frischer
  90-Tage-Schnitt fein zerlegt, nur dichte Zellen bleiben (global 83 Nester aus
  784 Zellen, 12 % des Schnitts), Zellen mit fast gleichem Zentrum
  zusammengefügt.
- Danach läuft der **ganze Bestand** am Zentrumsvektor vorbei und wird je Monat
  gezählt: 1.749.202 Dokumente über 449 Monate in 212 s, Speicher bleibt bei
  einem Block. Daraus erster Monat, Alter, Neuheits-Hebel (korpus-normiert),
  Beschleunigung und neues Vokabular gegen den Stand von vor 24 bis 36 Monaten.
- Seite `/trends/foresight/emerging` mit eigenem Knopf „Recompute pockets";
  Tabellen `emerging_runs`/`emerging_nests`, additiv, Live-DB angelegt. Kein Cron.
- Gefunden u. a.: Retrieval Augmented Generation (10 Monate alt), Vision Language
  Models in der Robotik (6), KV-Cache-Kompression (10), Batterie-Ladezustands-
  schätzung (3). Ebenfalls ganz oben: 647 Dokumente Pseudowissenschaft aus einem
  Massen-Ingest — tatsächlich dicht und neu. Jede Karte trägt deshalb ihre
  Schwächen (Quellenzahl, größte Quelle, Anteil je klassifizierter Dokumente).

Offen und dokumentiert: Bestätigung über die vier Lead-Time-Ebenen, Akteure statt
Artikel zählen, Namen vom Modell, Prüfung gegen datierbare bekannte Trends.
Details: `docs/emerging_nests_2026-09-15.md`.

## 2026-09-15 · change · Cluster-Schicht: Momentum maß den eigenen Quellenausbau

Die Karten auf `/trends/foresight/clusters` sortierten nach einem Anteilswert,
der das frühe gegen das späte Drittel der letzten 36 Monate stellte. In diesem
Fenster wuchs der Korpus von rund 10.000 auf 129.124 Signale im Monat und der
Quellenmix drehte von 49 % Fachpresse auf 56 % Forschung. Oben standen deshalb
die Forschungs- und Patent-Cluster, unten die Fachpresse-Themen. Umbau:

- Snapshot clustert die **letzten 24 Monate** (`--window-months`, 0 = Archiv).
  Global 567.911 statt 1.749.201 Signale, neun Scopes in 3,5 statt 10,5 min.
- Momentum auf **festem Quellenpanel** (nur Quellen mit Lieferung in beiden
  Fenstern; global 122 Quellen, 44 % Abdeckung; unter 25 % wird es verworfen
  und als `cohort_applied = 0` vermerkt).
- **Dämpfung** von Mengenausschlägen je Quelle auf deren Median. Eine Quelle
  war im FASHION-Lauf von ~50 auf ~350 Beiträge/Monat gesprungen (Nachtrags-
  Ingest) und erzeugte allein den einzigen Aufsteiger: +18,4 pp → +4,2 pp.
- Laufender Monat fällt aus Achse und Vergleich.
- Karte nennt die beiden Anteile statt einer nackten pp-Zahl, die größte
  Einzelquelle mit Anteil statt „confirmed by N independent sources", Kohäsion
  in Worten, Mega-Trend erst ab 50 % Reinheit. Belege sind die neuesten
  zentrumsnahen Signale, eines je Quelle.
- Neue Detailseite `/trends/foresight/clusters/<id>` auf dem jetzt
  persistierten Schwerpunktvektor (pgvector, 0,09 s).

Additive Spalten auf `foresight_runs`/`foresight_clusters`, Live-DB migriert.
Kein Cron betroffen. Befund und Messungen: `docs/cluster_layer_audit_2026-09-15.md`.

## 2026-09 · plan · bequiet von Ollama auf llama.cpp umstellen
gpu: bequiet

Drei Punkte, die dann anstehen: (1) `pipeline/remote_gpu.embed_batch_remote`
von `/api/embed` auf `/v1/embeddings` — llama.cpp holt kein Modell bei Bedarf,
das Embedding-Modell muss dort VORHER geladen sein; (2) den llama-server auf
bequiet mit `--host` an die Tailnet-Adresse binden; (3) die
Modell-Identitätsprüfung (`/v1/models`, wie lokal seit #98) auch für bequiet
aktivieren — sonst dasselbe Loch wie am 05.09.: ein Server, der auf alles mit
200 OK antwortet. Der Ops-Sampler ist schon backend-neutral (`/health` oder
`/api/ps`), an der Seite ändert sich nichts.

## 2026-09-12 14:55 · change · Fehlalarm „backup_db running for 6 h" — verwaiste Laufzeile, Sampler schließt tote Läufe jetzt selbst
Der Nachhol-Lauf des Backups um 07:49 lief im Vordergrund eines Tool-Aufrufs und
wurde nach dessen 2-min-Timeout hart gekillt — `ops_events` #9 blieb ohne Ende.
Der zweite Start um 08:00 (detached) lief sauber durch (#14, rc 0, 126,5 GB,
18,6 min). Um 13:50 meldete die Regel `job_hang` trotzdem „running for 6.0 h" —
sie sah nur die offene Zeile, nicht den toten Prozess; und nannte 07:49 lokal
fälschlich „UTC". Behoben: #9 von Hand geschlossen (Entwarnung 14:56); jede
Zeile trägt jetzt die pid ihres Prozesses (Wrapper: `$$`), der Sampler schließt
minütlich Zeilen toter oder wiederverwendeter pids (`close_orphans`), `record()`
stempelt bei SIGTERM das Ende (rc 143), Uhrzeit in der Mail lokal mit Zone,
Seite zeigt solche Läufe als „aborted". Scharf mit dem Merge nach main (Sampler +
Wrapper laufen dort); Spalte `pid` liegt schon in der Live-DB.

## 2026-09-12 · change · Backup 02:45 ausgefallen — Laufprotokoll-Hook zerbrach den Standalone-Start
Die Crontab startet `backup_db.py` ohne `cd`; der Hook `from pipeline.ops_events
import record` (Stufe 2, 11.09.) fand das Paket nicht → ModuleNotFoundError, kein
Backup. Wächter meldete um 07:45, Backup um 07:52 von Hand nachgeholt. Fix: Import
optional (ImportError → nullcontext), Repo-Root im Pfad, Regressionstest aus fremdem
Verzeichnis für alle acht Python-Crons. Lehre: ein Protokoll darf den Job nie
verhindern — das galt für die DB, musste aber auch für den Import gelten.

## 2026-09-11 · decision · Volltext für alle 480 tdm-ok-Quellen, User-Agent ohne Mailadresse
Option A: 302 Quellen von `fulltext: false` auf `true` (Messung: 10.500 Einträge in
14 Tagen, 19 mit Text). Erwartung ~+7.000 Volltexte je 14 Tage; `fetch_batch` jetzt
mit 8 Threads (Host-Drossel bleibt). Option B: nach dem Fix vom 08.09. kommen
73–100 % an, Rest sind heise+, gelöschte Seiten, bildlastige ArchDaily-Beiträge.
User-Agent V2 `CatandaryTrendsBot/1.0 (+https://catandary.de/trends/methodology)`,
Kontakt im neuen Abschnitt „Our crawler" der Methodik-Seite. Scharf mit Merge.

## 2026-09-11 · decision · Zweiter Vektorraum zurückgebaut — entbehrlich
Zwei Handläufe auf bequiet (20:50–21:35, 21:39–22:21, Owner-Freigabe außerhalb
des Fensters): 75.696 Vektoren, jetzt 95.023 mit beiden Räumen. Der erste Lauf
brach an einem einzelnen 400 ab (Fix `2394bba`: 4xx ≠ Host weg). Messung
`docs/embedding_eval_2026-09-11.md`: kein messbarer Vorteil auf Label-Ebene,
weil 95 % der Zeilen gar keinen längeren Text haben (Median Textgewinn 1,1×).
Von den 1,6 Mio offenen Zeilen tragen nur 17.877 einen Volltext ≥ 3× Anriss.
Owner-Entscheid: kein Backfill, kein 09:00-Lauf, kein Betrieb auf bequiet — der
zweite Vektor ist entbehrlich. Cron-Zeile, Wrapper, Skripte und Tests entfernt;
die Spalten mit den 95.023 gerechneten Vektoren bleiben stehen (additiv, nichts
liest sie). Kein Abstempeln der 1,6 Mio offenen Zeilen: das wäre ein Rewrite
von ~30 GB Tabellenmasse für eine Markierung, die niemand mehr abfragt.

## 2026-09-11 · change · Ops-Dashboard: Sampler, Laufprotokoll, Seite
Stufen 1–3 von #104. Timer misst minütlich (`ops_samples`), alle Wrapper und
Python-Crons protokollieren ihre Läufe (`ops_events`), `/trends/ops` zeigt es.
SMART freigeschaltet: alle vier Platten PASSED. Die Lexar NM790 meldet „240
Betriebsstunden" — das ist KEINE Stundenzahl: sie steckt seit der
Ubuntu-Installation am 13.05.2026 im Rechner (120 Tage, Uptime allein > 600 h).
Der Maxio-Controller zählt in einer anderen Einheit; für die Beurteilung dieser
Platte gelten Verschleiß (1 %), Reserve (100 %) und Medienfehler (0), nicht die
Betriebsstunden.

## 2026-09-11 · change · Cycle-Batch 600 → 3000, Embedding-Tageslimit 30.000
Nachtlauf soll einen normalen Tag in EINEM Durchgang schaffen (vorher jede
Nacht ein zweiter Lauf mit einem kompletten Stage-8-Pass, ~28 min). Embedding
09:00 auf 30.000, damit der Samstag (Wochen-Ingester) in einem Lauf durchgeht.
Erste Nacht mit beidem: 12.09.

## 2026-09-15 · change · Desk-Jobs in eigenem systemd-Scope, Snapshot-Lader seitenweise
Erster Recompute-Klick 13:07: `foresight_snapshot --all-verticals` ohne `--dim1024`
las 1,75 Mio. Vektoren als Text in einem fetchall, 56 GB RSS, OOM-Kill 13:15 — und
weil der Prozess im Cgroup von `catandary-frontend.service` hing, fiel :3001 mit
(systemd-Neustart nach 5 s, Log leer, Lock verwaist). Fix: `lib/detachedSpawn.ts`
wickelt jeden vom Frontend gestarteten Job in `systemd-run --user --scope -p
MemoryMax=40G`; `load_signals` liest per Keyset-Pagination (20k Zeilen) und hält nur
die float32-Bytes; der Knopf setzt `--dim1024`.

## 2026-09-15 · change · Seiten ohne Kundennutzen bereinigt (Owner-Liste)
Cluster/Evolution bleiben als Owner-Instrument nach der Radar-Regel: Rechenstand
sichtbar + „Recompute"-Knopf (CPU-only, detached, `data/foresight_snapshot.lock`);
Cockpit-Kacheln und Feed-Streifen tragen das Snapshot-Datum. `/trends/quality-preview`
(A/B-Vorschau vom Juli) gelöscht, `ab_test_prompt.py --preview` entfernt. Technology-
Kopf ohne Testvermerk/Gating-Rest. Ventures/Research/Pulse/Patents unverändert.

## 2026-09-15 · decision · Druckbares Foresight-Dossier aus dem Produkt genommen
`/trends/foresight/dossier` + CSV-Export (`/api/foresight/export`) entfernt: las nur den
Cluster-Snapshot vom 03.08. (kein Cron, kein Knopf), Cluster-Labels aus Top-Termen,
Anteils-Deltas ohne Kalibrierung — dieselbe Klasse wie das am 25.08. entfernte Radar.
Cluster/Evolution/MovingNow lesen denselben Snapshot; Liste weiterer Kandidaten liegt
dem Owner vor.

## 2026-09-10 · change · RTX 5080 auf bequiet als zweite GPU
Tailnet 100.119.239.40, Ollama auf :11434, 16 GB (13,9 frei am Sperrbildschirm).
Owner-Fenster 01:00–17:00. Gemessen: 12,4 Texte/s gegen 6,6/s lokal, cos 0,9995
zwischen beiden — Vektorräume austauschbar. Der 09:00-Lauf am 11.09. lief komplett
dort: 19.294 Vektoren in 29 min, die 3090 blieb unberührt.

## 2026-09-10 · decision · Volltext-Aufbewahrung 14 Tage → 60 Monate
§44b Abs. 2 S. 2 UrhG nennt keine Frist, sondern bindet sie an den Zweck;
dokumentierter Zweck ist die längsschnittliche Trendanalyse. Nachhollauf holte
32.234 von 34.484 gelöschten Volltexten zurück.

## 2026-09-17 · change · Volltext-Nachhollauf über die letzten 14 Tage
duration: 2 h 31 min
Zufallsstichprobe zeigte: die Einträge ohne Text im 14-Tage-Fenster waren nie
geholt worden (83 % sofort verfügbar), während die 400 neuesten — die
Fehlschläge der letzten Nacht — nur 9 % ergaben. Lauf
`refetch_fulltext.py --min-age-days 0 --since 2026-09-03 --limit 0 --apply`:
14.471 geprüft, **12.176 Volltexte** (84 %), Ø 4.051 Zeichen, 49 MB. Reste:
too_short 1.231, 403 757 (DigiTimes 314, Mongabay 85, Tech Funding News 69,
Apparel Resources 58, HPCwire 45, Retail Gazette 42), 429 45 (Project Syndicate
37, ECDC 7), Timeouts 105. Kein Embedding berührt (Vektor = Titel+Teaser),
nichts gelöscht. Nutzen: Dossiers lesen für diese Einträge den Artikel statt
des Teasers.

## 2026-09-17 · change · Sechs 403-Quellen ohne Volltext, Project Syndicate auf 10 s
Aus dem Nachhollauf (Owner): DigiTimes, Mongabay, Tech Funding News, Apparel
Resources, HPCwire, Retail Gazette auf `fulltext: false` / `tdm_status: blocked`
(Artikelseiten 403, Feeds laufen weiter). Project Syndicate bekommt als erster
Host eine eigene Rate (`article_fetcher.HOST_DELAYS`): 37 von 52 Anfragen
kamen mit 429 zurück. Erst 10 s, am Abend auf 2 s gesetzt (Owner) — Messung:
1,5 s: 9 ok, dann 429; 3 s direkt danach 20/20 × 429; nach 10 min Pause mit
10 s Abstand 30/30 × 429. Kontingent je Zeitfenster mit langer Strafzeit, kein
Intervall; der Nachtlauf (5–10 Artikel) bleibt darunter. Netzpolitik-Archiv
nicht abgerufen (30.573 URLs, 400 neu, alles Menüseiten).

## 2026-09-17 · change · Themensuche Stufe 1: Anfrage-Maschine + Suchtabelle topic_vectors
duration: 6 h
gpu: nein (CPU-Embedder :8091)
`pipeline/topic_report.py` (Modul + CLI): ein Begriff rein, je Ebene
(Forschung/Patente/Förderung/Markt) Kopf, Cut, Treffer roh/gedämpft, erster
und erster tragender Monat, Reihenfolge der Ebenen, Abstand Forschung→Markt,
Volltext-Älteste, frühere Vokabeln, Rückfrage bei Kurzanfragen. Unterbau:
Nebentabelle `topic_vectors` (Ebene + Vektorkopie je Trend, 1,76 Mio. Zeilen in
127 s, 7,2 GB) mit vier HNSW-Teilindizes (Forschung 154 s, Patente 32 s,
Förderung 98 s, Markt 174 s) — der Teilindex findet auf Patenten 14–58 Zeilen,
wo der globale Index nach dem Filtern 0–8 ließ. Abgebrochener erster Weg:
Spalte `trends.tier` per UPDATE — Non-HOT-Updates schreiben in den 14-GB-HNSW-
Index, 5 min je 50k-Batch, 285k tote Tupel hinterlassen (Autovacuum räumt).
Kalibrierung: Kopf − 0,08 datiert Präzisionsfermentation auf 2020-01
(Forschung tragend) / 2020-05 (erster Markttreffer) — deckungsgleich mit den
unabhängig notierten Daten. Warm 2,6 s je Anfrage, Cache 0,9 s. Tabellen
`topic_reports`/`topic_cache` (init_db). Keine Cron-Änderung.

## 2026-09-17 · change · Themensuche Stufen 2–5 auf dev (Owner testet vor dem Merge)
duration: 3 h
Seite `/trends/foresight/topic` (GET-Formular, Häkchen je Ebene, Bericht mit
Wortgenerationen, Ebenen-Streifen, 60-Monats-Kurven, neueste Belege je Quelle,
Schwächen je Block, Rückfrage bei Kurzanfragen), Vorschläge unter dem Suchfeld
(Nest-Namen, neues Vokabular, gestellte Fragen), Rücktest
`scripts/validate_topic_search.py`: Markt 18/18 gezählte Trends gefunden,
Gegenproben 0/3, tragender Marktmonat im Median 23 Monate nach dem Marktdatum
(Korpus vor 2024 dünn), erster Einzeltreffer 72 Monate davor. Rückbau: Desk-
Knopf rechnet Nester nur noch global + 4 Ebenen, Vertikal-Reiter weg. Nichts
auf main, kein Cron berührt.

## 2026-09-17 · decision · Themensuche zurückgebaut, Redesign als Issue #106
Owner nach dem Test der Seite: „zu überladen mit all den Beispielen und zu
verwirrend. Sprache ist nicht klar. Inhalt nicht nachvollziehbar." Stufen 1–5
auf `feature/topic-search` (e2907f4) geparkt, auf `dev` zurückgenommen
(Revert von 546f0d4 und 432fc2d), kein Merge nach `main`. Die drei Tabellen
`topic_vectors` (23 GB), `topic_reports`, `topic_cache` aus der Live-DB
gelöscht — Neuaufbau in ~10 min per `scripts/migrate_topic_vectors.py
--indexes` auf dem Branch. Die Messungen (Rücktest Markt 18/18, Ebenen-Index
gegen globalen Index, Kalibrierung) stehen im Plan und im Issue.
