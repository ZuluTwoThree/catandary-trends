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

## 2026-10-10 · change · Förderung: Sperrseiten-Fix, Titel-only als Signal, Testlauf Artikelpfad

- Fetcher erkennt Bot-Sperrseiten (`bot_wall`); 51 gespeicherte Radware/DigiTimes-Seiten geleert, 2 „Bot Detection"-Entwürfe verworfen.
- Förder-Einträge ohne Text werden Signal statt `insufficient_source_text`.
- Testlauf (140 Einträge, 9 min): 77 Entwürfe, 50 Signale, 3 published (alle Nicht-Förderung); Richter 71/74 gehalten (64 `no_signal`) — Entscheid offen.
- Nationale Förderaufruf-Feeds geprüft: UKRI Opportunities, ANR, DFG ok; SNF robots-gesperrt; Eureka ohne Links; FFG/Innosuisse/Vinnova/NWO/Forskningsrådet ohne Feed.

## 2026-10-09 · change · Nacht-8B mit 16 statt 24 Fächern — Mitschrift bleibt nachts an

- Messung Nachtlauf 09.10.: 24 Fächer à 8.960 im Mittel zu 22,8 belegt, aber je Anfrage nur 13 % gefüllt
  (Median 1.138 Token), KV ~14 % genutzt, GPU 69 %, 365 Token/s.
- Test (600 bzw. 200 echte Extraktionen, 24 parallel): gemeinsamer Cache 32k/64k mit Abbrüchen, 128k ohne,
  aber nur 208 Token/s (halbes Tempo); feste Fächer 16 und 20 je ~322 Token/s, 16,2 bzw. 19,0 GB;
  Ergebnisse in allen Fällen im Rauschen gleich.
- Owner: Default 16 Fächer (`start-qwen3-8b-16slot.sh`, `CLASSIFY_WORKERS=16`), NeMo/Whisper bleiben an
  (`GPU_EVICT_DAY_APPS=0`), Richter-Vorab-Check 3500 MiB. Probe-Handover: 18,9 GB mit Mitschrift.

## 2026-10-07 · change · Nachtlauf-Ausfall, Container-Fix, Router-Neuverbindung, Schriften lokal

- **Nachtlauf 07.10. fiel aus** (0 Trends): `kill` auf NeMo/Whisper (root, Docker) scheiterte still,
  3 GB blieben belegt, das 24-Slot-8B startete nicht. Fix `586daac`: `docker stop` vor, `docker start`
  nach dem Lauf. Nachgeholt 12:37–17:50, rc=0, 1.989 + 292 Trends, Container automatisch zurück.
- **Publish 02:00 brach ab:** nächtliche Router-Neuverbindung mit neuem IPv6-Präfix (02:31) traf den
  Upload (lief über IPv6, ENETUNREACH 02:46); der Upload war lang, weil Google Fonts einen
  unicode-range geändert hatte (neue CSS → 28.206 geänderte Dateien) und der Download die Leitung teilte.
  Nachgeholt 12:27–12:37, 24.667 Dateien, 0 Fehler. Owner: Neuverbindung jetzt fest 01:00–02:00;
  Schriften lokal (`frontend/src/fonts`, Googles Versionen, pixelgleich geprüft).
- **OpenAlex-Nachholen abgeschlossen** (Download 06:40, Verarbeitung 12:17); Nachhol-Env aus der Crontab.

## 2026-09-29 · change · Distill-Relevanz-Head zurück auf 26.07. (#115)

Der Retrain vom 27.09. lieferte einen Relevanz-Head, der auf denselben Presse-Einträgen
40,6 % statt 35,0 % verwarf; die Nachtläufe 28. und 29.09. verloren dadurch zusammen 265
Einträge, die der alte Head nicht verworfen hätte. 08:02: `models/distill/relevance.joblib`
in main und dev durch den 4096er-Head vom 26.07. ersetzt (98 % gleiche Entscheidungen wie
der bis 26.09. produktive), neuer als `relevance.joblib.2026-09-27` aufgehoben. Wirksam ab
dem nächsten Lauf. Dauerhafte Lösung: #115.

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

## 2026-10-01 · plan · Nach dem Monats-Check: zwölf stille Quellen reparieren, #81 schließen
Der Monats-Check (01.10. 08:00) probt alle 560 Feeds. Danach die Befunde vom
25.09. (#81-Kommentar) umsetzen: 9 Förderinfo-Themenfeeds (blocked, von
„Bekanntmachungen (alle)" geshadowt), EE Times (403), ZVEI, IFPRI (leer)
deaktivieren; WHO News und Civil Eats auf die aktuellen Feed-URLs umstellen;
Modern Farmer prüfen; DB-Orphans Sourcing Journal + zweite Science-News-Zeile
per SQL inaktiv; Confectionery News / Food Navigator Asia: Dublette zum
FoodNavigator-Sammelfeed entscheiden. Danach `apply_source_hygiene.py --apply`,
Merge, #81 schließen (Reste stehen in #97).

## 2026-09-25 13:30 · change · Richter setzt kein `reviewed_at` mehr, 7.765 Freigaben entstempelt
duration: 30m
gpu: nein
Owner-Go. `draft_judge.publish_draft(auto=True)` stempelte `reviewed_at`, die
Marke einer Handentscheidung (Regel 22.09.). Folge: alle Richter-Freigaben
(~400 je Nacht) galten als „von Hand entschieden" und wurden vom Grounding-
Nachlauf, vom Review-Agent und von Owner-Korrekturen mit `reviewed_at IS NULL`
übersprungen — so kamen die Casino-Artikel am ersten Bereinigungs-UPDATE
vorbei. Fix: der Richter lässt `reviewed_at` unberührt, `auto_published=true`
bleibt seine Marke; Owner-entschiedene Freigaben (`auto=False`) stempeln
weiter. Bestand: `scripts/reset_judge_reviewed_at.py --apply` — 7.765 Zeilen
(auto_published, published, reviewed_at gesetzt; hand-verworfene und Desk-
Freigaben unberührt), gebatcht 1.000/Commit. Frontend liest `reviewed_at`
nirgends, nur die Schreibpfade der Review-Seite setzen es. Tests 1.299 grün.
Scharf mit dem Merge: ab dann werden Richter-Freigaben von den Nachprüfungen
erfasst.

## 2026-09-25 12:30 · change · Food+Tech Connect: Quelle abgeschaltet, Spam-Bestand gelöscht
duration: 45m
gpu: nein
Owner nach Sichtprüfung: „die Quelle ist Schrott, alle Artikel auf der Seite
sind Spam, nur lange zurückliegende sind legit." Audit (lesend): Archiv 2010-07
bis 2025-02 = 1.662 Einträge ohne Spam-Treffer, daraus 1.193 Signale (Juli-
Backfill) — bleiben. Ab dem 06.07.2026 (erste Spam-ID 21601364) ausschließlich
Casino-, Wett- und Adult-SEO in zehn Sprachen: 517 raw_entries, 103 Trends
(9 published, 16 Drafts, 78 vom Richter verworfen). Der Owner hat beides von
Hand gelöscht (`DELETE 103`, `DELETE 517`; Story-Zeilen per Cascade, Metriken
gab es keine), Quelle 228 in DB und `sources.yaml` (dev, `bdf5cc7`) inaktiv. Die
sechs noch veröffentlichten Spam-Seiten verschwinden mit dem Export 02:00.
Nebenbefund: `draft_judge.publish_draft` setzt `reviewed_at` auch bei
automatischen Freigaben — dadurch gelten Richter-Freigaben als Handentscheidung
und werden vom Grounding-Nachlauf, vom Review-Agent und von Owner-Korrekturen
mit `reviewed_at IS NULL` übersprungen. Fix vorgeschlagen (#111).

## 2026-09-25 11:00 · change · Abnahme des Richter-Nachlaufs vom 24.09., alte Entwürfe abgeräumt, Spam-Feed entdeckt
duration: 1h30m
gpu: nein
Owner-Go für die vier offenen Punkte des 07:00-Plans. **Nachtlauf 25.09.:** 3:45 h
statt 4:57–5:26, Stage 8 5,6 min statt 63, Richter 534 beurteilt / 404 frei /
118 gehalten, `source_mismatch` 14 statt 103 — die Änderungen vom 24.09. wirken.
**Kurze Quellen** (3.365 Entwürfe im Fenster): liegen gelassen. **Alte Entwürfe:**
`scripts/expire_old_drafts.py --apply` — 4.760 Entwürfe außerhalb des 30-Tage-
Fensters (ältester 2024-05-16) auf `rejected`, `review_reason='expired:window'`,
gebatcht, `reviewed_at` bleibt NULL. **Abnahme Nachlauf 24.09.** (1.942 neu
beurteilt, 595 frei / 1.292 gehalten): je 10 Zufallsstichproben gegen die Quelle
gelesen. Freigegeben: **10 von 10 quellentreu**, alle Zahlen und Namen belegt,
zweimal ein optionaler Ausblick am Ende, ein Titel leicht überzeichnet („halts"
statt reduziert). Gehalten: **10 von 10 zu Recht** — 2 mit echtem Fehler (heise
„KI und Autismus": Rahmen erfunden, die Quelle ist ein Tagungsbericht; ZEW-China-
Studie: „ifo Institute" statt DIW), 1 Casino-Werbung, 7 dünn oder ohne Signal
(Ticker-Sammelmeldungen, Podcast-Transkript, Konferenzbericht ohne die Fakten
der Quelle; einmal Extraktion komplett leer). Urteil: der Nachlauf ist abgenommen.
**Nebenfund:** der Feed von **Food+Tech Connect** (Quelle 228) ist seit August
kompromittiert — 217 von 363 Einträgen mehrsprachige Casino-SEO-Werbung
(nvvcasino, gangstasino, betspino …); daraus wurden **5 Artikel automatisch
veröffentlicht** (u. a. #1719217 Oscar Spin Casino, #1679578 Winshark Casino,
#1759912 Pragmatic Play, #1719216 Betify), 38 als Drafts gehalten, 22 vom
Richter verworfen. `is_advertorial` und Relevanz-Head haben das nicht gefangen.
Abhilfe (Owner-Hand, Massenänderung vom Sitzungsfilter blockiert): Spam-Trends
auf `rejected`, Quelle 228 in DB und `sources.yaml` deaktivieren, Merge; danach
Export 02:00 nimmt die fünf Seiten vom Netz (410). Offen: ein Sprach-/Spam-Gate
im Poller (Titel nicht in Quellensprache, Casino-Vokabular) — Issue anlegen.

## 2026-09-25 09:30 · change · Owner-Go für die Nachtarbeit: Signaltyp-Head scharf, Bestand nachgelabelt, Story-Cron installiert
duration: 1h
gpu: nein
Owner um 09:20: „ja für 1 bis 4". Umgesetzt: `DISTILL_SIGNAL_TYPE=1` in
`scheduled_cycle.sh` und `weekly_ingesters.sh`, `signal_type.joblib` nach
`catandary-trends/models/distill/` kopiert; Bestand mit
`scripts/relabel_signal_types.py --apply` nachgezogen — 49.681 Presse-Zeilen seit
dem 14.07., **17.997 umgelabelt** (regulation 8.888, product_launch 6.422,
partnership 1.792, consumer_behavior 895), 31.684 bleiben market_shift
(Head unter 0,6), gebatcht 1.000 je Commit, nur Label + CRS-Score; Cron
`55 1 * * * group_stories.py --days 3 --apply` installiert; Merge dev → main,
:3001 neu gebaut. #81: Reparaturen nach dem Monats-Check am 01.10. (Plan-Eintrag),
Reste nach #97.

## 2026-09-25 · change · Story-Gruppierung (#109, Stufe 1) auf dev
duration: 1h30m
gpu: nein
Block 3 der Nacht. Nachlauf statt schärferer Dedup-Schwelle: gleiche
extrahierte Marke (Schlüssel ≤ 4 Wörter) · 48 h · Kosinus ≥ 0,80 auf
embedding_1024 · transitiv, ältester Artikel führt. `pipeline/stories.py`,
`scripts/group_stories.py` (Dry-Run/`--apply`, 3,5 s je 30 Tage), Tabelle
`trend_stories` (additive Migration, Live-DB 25.09., 30 Tage geschrieben:
2.980 Zeilen in 1.085 Gruppen). Gemessen 26.08.–25.09. über 23.342 Artikel:
1.895 Folgeberichte (8,1 %; #109 hatte 7,2 % für den September), 776 Zweier-,
165 Dreiergruppen; größte Apple-Keynote 50, Meta 42, OpenAI 32, Meta Muse 21 —
Ketten über Folgemeldungen, wie erwartet. Artikelseite „Also reported by" mit
Quelle, Link, „first report" (`getStorySiblings`, fensterbegrenzt), auf :3004
gesehen. Cron-Zeile 01:55 als Vorschlag in `deploy/crontab.txt`, nicht
installiert. Tests: 7 neue pytest, tsc 0, vitest 485.

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

## 2026-09-25 · change · Modell-Messplatz: Kontext, Parallelität, VRAM gemessen (nichts umgestellt)

duration: 14:17–16:26 (Owner-Fenster „ab jetzt bis längstens 17 Uhr")
gpu: Produktivserver gestoppt, Testserver auf :8190, danach `gpu-mode catandary` (verifiziert:
start-active.sh → start-qwen3-8b-208k.sh, :8090 serviert Qwen3-8B)

66 Laststufen über 8B, Gemma-26B, Qwen3.8-27B und den Embedder, mit echten Prompts aus der
Live-DB. Werkzeuge unter `scripts/ctx_eval/`, Rohdaten `data/ctx_eval/`, Bericht
`docs/context_parallel_eval_2026-09-25.md`. **Produktiv ist nichts geändert**; vier
Startskript-Varianten liegen als neue Dateien in `~/llama.cpp` und sind nicht in
`gpu_handover.MODEL_START_SCRIPTS` eingetragen.

Kernbefunde: Kontext bei Gemma (262 144 → 16 384: −4,6 GB) und 27B (−5,4 GB) massiv
überdimensioniert, Durchsatz identisch. Beim 8B umgekehrt: der 8 960-Token-Slot reicht für eine
Extraktion aus einer CJK-Quelle nicht (12 000 Zeichen ≈ 8 300 Token) — Sonde verlor 24 von 24
Antworten an `finish_reason=length`, der Eintrag endet als `extraction_error`. `--kv-unified`
spart beim 8B 9 GB, kostet aber 36 % Durchsatz. KV-Quantisierung ist kein Qualitätshebel
(Richter q4_0 vs. q8_0 an 150 Handentscheidungen: McNemar p = 0,29). Größter ungenutzter Hebel:
Stufe 6 sequentiell 20,3 Anfragen/min gegen 30,0/min mit 4 Slots ohne unified = −35 min Nachtlauf,
aber Umbau der Schleife.

## 2026-09-25 · change · Gemma und Draft-Richter auf 16K-Kontext umgestellt (dev, main-Merge offen)

gpu: Testlauf mit echtem Pipeline-Batch, Ruhezustand danach wiederhergestellt

Nach dem Messbericht (`docs/context_parallel_eval_2026-09-25.md`) zeigen sechs Stellen jetzt auf
`start-gemma4-26b-ctx16k.sh` und `start-qwen3.8-27b-ctx16k.sh`: die Registry in `gpu_handover`,
`draft_judge.JUDGE_START_SCRIPT`, `scheduled_cycle.sh` (Stage-5-Start und der Stage-10-Symlink)
und die beiden Newsletter-Wrapper. Das 8B (Ruhezustand) und der Embedder bleiben unverändert.

Wirkung: Gemma 15 072 statt 19 782 MiB, Richter 17 610 statt 23 094 MiB. Kein Tempo-Effekt —
gepaart gemessen liegt der Unterschied unter 5 % und kippt je nach Messreihe die Richtung.
Beim Richter ist die Reserve der Punkt — vorher ~1,2 GB, jetzt ~6,7 GB; der VRAM-Vorabcheck vor
Stufe 10 fängt seitdem einen Fall ab, der praktisch nicht mehr eintreten kann.

Nebenbefund aus dem neuen Test `tests/test_start_scripts_match_registry.py`: Die Registry führte
noch `Qwen3-30B-A3B-Q4_K_M.gguf` → `start-qwen3-30b.sh`, obwohl GGUF und Skript beim
llama.cpp-Umbau am 29.08. gelöscht wurden. Tote Zeile entfernt. Der Test prüft ab jetzt, dass
jedes registrierte Skript existiert, das passende Modell lädt und dass die Shell-Wrapper dasselbe
Skript meinen wie die Registry.

## 2026-09-25 · change · 500 Backlog-Einträge mit den 16K-Skripten verarbeitet; Volltext-Befund

duration: 23:17–23:45 (1 669 s)
gpu: Gemma-Spitze 15 056 MiB, 8B 22 000 MiB; Ruhezustand danach hergestellt

Owner-Auftrag „250 aus dem Backlog". `run_full_cycle` arbeitet zwei Runden ab (Phase 1 Backlog,
Phase 3 „neue"), jede bis BATCH — es wurden 500 Einträge verarbeitet, 264 Artikel erzeugt,
150 auto-publiziert. Die umgestellten Skripte liefen fehlerfrei: beide Handover in beide
Richtungen, kein ModelMismatchError, 2,7 s je Artikel.

**Befund (unabhängig von der Umstellung, betrifft `main`):** 27 Artikel (9 %) hielt der
Garbage-Guard mit `too_short` zurück, weil nur 13 von 331 verarbeiteten Einträgen Volltext
hatten — obwohl alle Quellen auf `fulltext: true` stehen und `article_fetcher` 226 Volltexte
geholt hat. Ursache: die beiden Auswahlen ziehen in entgegengesetzter Richtung.

| Komponente | Auswahl | ID-Spanne im Lauf |
|---|---|---|
| `article_fetcher.fetch_batch` | `ORDER BY re.id DESC LIMIT n` — die NEUESTEN | 25 494 906 – 25 509 134 |
| `db.get_unprocessed_entries` | nach `fetched_at, id` aufsteigend — die ÄLTESTEN | 25 494 865 – 25 496 136 |

Im Nachtlauf fällt das nicht auf: dort ist `CYCLE_BATCH=3000` grösser als der Tagesanfall
(~2 460), also sind beide Mengen praktisch deckungsgleich. Sobald der Rückstand grösser ist als
der Batch — nach einem Ausfall, einem Feiertag, einem Teillauf wie hier — verarbeitet der Cycle
genau die Einträge, für die kein Volltext geholt wurde. Wirkung: dünne Artikel, mehr
Guard-Ausfälle, schwächeres Grounding. Nicht angefasst (Cron-Pfad, Owner-Entscheidung).

Eigene Mängel behoben: `scripts/ctx_eval/testrun_batch.sh` stellt den Ruhezustand jetzt per
`trap` wieder her (der Server lag nach dem ersten Testlauf 10 min tot) und respektiert den
Kollisionswächter; der Kopfkommentar warnt vor der Zwei-Runden-Semantik.

## 2026-09-26 · change · Volltext-Anreicherung trifft jetzt die verarbeiteten Einträge

Fix zum Befund vom 25.09.: `enrich_fulltext` fragt `get_unprocessed_entries(limit, min_id)` —
denselben Aufruf, den `run_pipeline_batch` gleich danach macht — und gibt die ID-Liste an
`fetch_batch(ids=…)`. Vorher wählte der Fetcher `ORDER BY re.id DESC` (die neuesten), der Cycle
nimmt die ältesten; bei Rückstand > Batch überlappten die Mengen mit **0 von 250**.

Gemessen an denselben Einträgen (233 zurückgeholte plus frische, 26.09. 00:12–00:54):

| | ohne Fix | mit Fix |
|---|---|---|
| Textbasis der Auswahl (Median) | 305 Zeichen | 2 527 Zeichen |
| Median Wörter je Artikel | 75 | **158** |
| vom Garbage-Guard verworfen | 10 % | **1,6 %** |
| als irrelevant verworfen (frische Kohorte) | 38 % | **16 %** |

**Historische Einordnung:** In den 14 Nachtläufen vom 08.–24.09. war der Fehler NICHT wirksam —
Rückstand 0–1, Batch 3 000 über dem Tagesanfall (~2 450), also nahmen beide Schritte alles; 3–6 %
ohne Volltext sind gescheiterte Abrufe (der Fetcher protokolliert `enriched 2332/2445`). Auch die
Nacht zum 11.09. mit Batch 600 endete bei 5 %, weil der Folgelauf nachholte. Der Fehler verzögert
in diesem Muster, er verliert nicht.

Datenkorrektur: `scripts/requeue_thin_decisions.py --apply` hat 233 Einträge zurückgeholt, deren
`not_relevant`/`insufficient_source_text`-Entscheidung auf 259 Zeichen Median gefallen war
(Duplikate bewusst nicht). Regressionstest `tests/test_enrichment_matches_selection.py`.

Offen als eigenes Thema: 41–83 Einträge je Tag werden ohne Volltext als irrelevant verworfen, weil
der Abruf scheitert (403, Timeout) — über zwei Wochen ~800.

## 2026-09-26 · idea · Samstags bleibt der llama-server nach dem Ingester-Lauf aus

Befund (gemessen, nicht vermutet): `scripts/weekly_ingesters.sh` stellt den Ruhezustand NICHT her.
Der GPU-Handover stoppt den Server nach dem letzten Distill-Schritt und stellt nur den Symlink
zurück; ein `systemctl --user start llama-server.service` wie am Ende von `scheduled_cycle.sh`
(dort rc3) fehlt. Folge: ab Ende des Ingester-Laufs steht die Owner-Instanz ohne Modell da, bis
der Montags-Cycle läuft.

Belegt über `ops_samples` (07:30–12:00, samstags):

| Samstag | Messungen | davon ohne geladenes Modell |
|---|---|---|
| 2026-09-19 | 169 | 129 |
| 2026-09-26 | 109 | 106 |

Am 26.09. lückenlos von 07:12 (Ende des Embedding-Schritts) bis 09:15, als der Server von Hand
gestartet wurde. **Zweite Lücke:** `cycle_watchdog.py` prüft den llama-server gar nicht — er liest
nur die Stage-Bilanz des Cycles (rc3), und am Wochenende gibt es keinen Cycle. Der Wächter meldete
um 07:45 „alles in Ordnung", während kein Modell geladen war.

Vorschlag (Cron-Pfad, also `main`-Merge nötig, dem Owner vorzulegen): am Ende von
`weekly_ingesters.sh` denselben Block wie in `scheduled_cycle.sh` (Symlink auf den 208K-Klassifizierer
+ Unit starten, übersprungen wenn ein fremder GPU-Job die Unit hält), und im Wächter eine Prüfung
„antwortet `:8090` mit dem Ruhezustands-Modell?" — sonst fällt das nächste Mal wieder niemandem auf.

## 2026-09-26 · change · Extraktions-Kappe in Token, Ruhezustand im Ingester, Wächter prüft :8090

Owner-Freigabe der Punkte 1–3 vom 26.09. Umgesetzt auf `dev`:

**Extraktion (Punkt 2):** `llm_processor.clip_to_token_budget` kappt den Quelltext auf
`EXTRACT_TOKEN_BUDGET` (Default 6.000) geschätzte Token, bevor die Zeichen-Kappe von 12.000
greift. Schätzer konservativ: CJK ~1 Token je Zeichen, alles andere 3,4 Zeichen je Token
(gemessen an 60 Volltexten: Median 4,89, dichtester Fall 3,43). Ernstfall geprüft gegen den
echten Tokenizer: 12.000 Zeichen / 8.302 Token → 6.826 Zeichen / 4.652 Token; die fünf
längsten lateinischen Volltexte bleiben unverändert (2.063–3.469 Token).

**Ingester (Punkt 3a):** `weekly_ingesters.sh` stellt den Ruhezustand her (Symlink + Unit +
Warten auf `/v1/models`), übersprungen wenn ein fremder GPU-Job die Unit hält. Sichtbar als
`rest=…` in der end-Zeile und in der ops_events-Notiz.

**Wächter (Punkt 3b):** `cycle_watchdog.inspect_llama_server` — antwortet `:8090`, und
serviert er `Qwen3-8B-UD-Q4_K_XL`? Drei Ausgänge: ok, `llama-down`, `llama-wrong-model`;
kein Alarm während eines GPU-Jobs. Live geprüft, Tests in
`tests/test_watchdog_llama_server.py` und `tests/test_extraction_token_budget.py`.

1.332 pytest grün. Alles auf dem Cron-Pfad, also erst mit dem `main`-Merge scharf.

## 2026-09-26 · change · Samstags-Mittagsjobs auf vor 9 Uhr vorgezogen (Owner)

`weekly_research_pulse.sh` 12:00 → **08:30**, `weekly_field_watch.sh` 12:30 → **08:45**.
In der installierten Crontab geändert, `deploy/crontab.txt` und die Doku nachgezogen;
Sicherung der alten Crontab in `data/ctx_eval/crontab.backup-20260926`.

Zeitwahl nach den gemessenen Ingester-Enden der letzten sechs Samstage: 05:17, 07:20, 07:20,
07:31, 07:36 und **08:13** (29.08.). 08:30 lässt im spätesten Fall 17 min Puffer; überschneidet
sich der Ingester doch, wartet der Kollisionswächter (max 90 min) statt zu scheitern — der Pulse
würde dann einfach etwas später laufen, immer noch vor 9 Uhr.

Wirksam ab Samstag 03.10.; der Lauf von heute war schon durch (auf Owner-Wunsch auf 11:00
vorgezogen, s. nächster Eintrag). Field Watch läuft ohne Kundendateien als no-op.

## 2026-09-26 · change · Erster Produktivlauf des 16K-Gemma (Research Pulse, vorgezogen auf 11:00)

gpu: Gemma-Spitze 15 038 MiB, Ruhezustand danach automatisch wieder 8B (21 986 MiB)
duration: 64 s (11:00:03 – 11:01:08)

Owner wollte den 12:00-Lauf vorgezogen und beobachtet. Ergebnis: **28 Themes, 20 mit Text,
0 Fehler**, Woche 2026-W38 in `research_pulse`. Server lief mit `n_slots = 1,
n_ctx_slot = 16384` — die Umstellung aus dem `main`-Merge greift also im Produktivbetrieb.

| Zeit | VRAM | Modell |
|---|---|---|
| 11:00:03 | 21 986 MiB | 8B (Ruhezustand) |
| 11:00:34 | 14 010 MiB | Wechsel, Gemma lädt |
| 11:00:49 | 15 038 MiB | Gemma |
| 11:01:19 | 21 986 MiB | 8B (Ruhezustand zurück) |

15 038 MiB liegt innerhalb der Prüfstandsmessung (15 048–15 060) und **4,7 GB unter der alten
Konfiguration** (19 782). Laufzeit 64 s gegen 54–58 s am 18.09. — andere Woche, andere
Datenmenge (grösstes Theme 6 617 Papers), kein Konfigurationsvergleich. Der 12:00-Cron fand die
Woche gerechnet und übersprang mit `exists`.

## 2026-09-26 · idea · Discovery-Loop: das Retrain der Distill-Heads stirbt seit Wochen am Speicher

Aufgefallen, weil `mega_discovery.candidate.yaml` im main-Arbeitsbaum verändert war. Die Datei
ist die Ausgabe des Sonntagslaufs (`discovery_loop.py`, 06:00) und versioniert — jeder Lauf macht
den Arbeitsbaum damit „dirty". Das ist die harmlose Hälfte des Befunds.

**Die andere Hälfte:** Der Loop endet seit mindestens drei Sonntagen mit Fehlern. Aus
`~/logs/catandary-discovery-loop.log`:

| Sonntag | discovery | retrain |
|---|---|---|
| 06.09. | — | `rc=-9` |
| 13.09. | `rc=0` | `rc=-9` |
| 20.09. | `rc=0` | `rc=-9` |

`rc=-9` ist SIGKILL. Der Kernel bestätigt den Grund (`journalctl -k`, 20.09. 06:15:45):
`Out of memory: Killed process 368337 (python) total-vm:60407508kB, anon-rss:56628700kB` —
**56,6 GB**.

Rechnung dahinter: `discovery_loop.retrain()` ruft `scripts/train_distill_heads.py` **ohne
`--sample`**, der Trainer lädt `trends.embedding` (4096-dim) für alle gelabelten Zeilen. Das sind
heute **1.827.351 Zeilen × 4096 × 4 Byte = 29,9 GB** als Matrix, plus der Text-Parse-Zwischen-
schritt (`embedding::text` → `np.array`) und Kopien — 56 GB sind damit erklärt. Dasselbe Muster
wie beim Snapshot-OOM vom 15.09., der :3001 mitriss.

Wirkung: Die Discovery selbst läuft (die Kandidaten werden geschrieben, zuletzt 9 Themen,
Rausch-Anteil 0,81, Stabilität 0,82). Nur die Heads werden nicht neu trainiert, obwohl
`mega_trends.yaml` neuer ist — sie arbeiten weiter mit dem alten Stand. Gemerkt hat es niemand:
der Wächter prüft den Discovery-Loop nicht, und `loop finished WITH ERRORS` steht nur im Log.

**Die Lösung existiert schon — sie wurde nur nicht übertragen** (Owner-Hinweis 26.09.: „ich habe
da etwas in der Art in Erinnerung"). Am 15.09. traf denselben Fehler `foresight_snapshot`: ohne
`--dim1024` las er 1,75 Mio. Vektoren als Text in einem `fetchall`, **56 GB RSS, OOM-Kill** — dieselbe
Zahl wie hier. Behoben wurde er dreifach: seitenweiser Lader (Keyset, 20 k Zeilen, hält nur die
float32-Bytes), `--dim1024` für das Matryoshka-Präfix (`emb_field = "embedding_1024" if dim1024`,
`pipeline/foresight.py:148`, ebenso `discovery.py:103/247`) und ein systemd-Scope mit
`MemoryMax=40G` für vom Frontend gestartete Jobs (`lib/detachedSpawn.ts`).

`train_distill_heads.py` hat von den drei Teilen nur den Server-Cursor. Es lädt hart `embedding`
(4096), kennt kein `--dim1024`, sammelt `chunks` und macht am Ende `np.vstack` — also doch die
Vollmatrix. Und es läuft im Cron **ohne** MemoryMax, weil der Scope nur für Frontend-Jobs gilt.

Prüfung, wo das Muster sonst noch steckt (Skripte, die `embedding` statt `embedding_1024` laden):

| Skript | Matrix heute | mit 1024er | läuft unbeaufsichtigt? |
|---|---|---|---|
| `train_distill_heads.py` | 1 827 351 × 4096 = **29,9 GB** | 7,5 GB | **ja**, über `discovery_loop` (So 06:00) |
| `train_signal_type_head.py` | 708 998 × 4096 = 11,6 GB | 2,9 GB | nein, on demand |
| `propose_mega_trends.py`, `reclassify_mega.py`, `tir_metrics.py`, `mega_trend_reviewer.py`, `fix_mega_abstain.py`, `validate_distill_patents.py`, `distill_prototype.py`, `reclassify_concept_sources.py` | — | — | nein, on demand |

Nur der Trainer läuft also unbeaufsichtigt — und genau er ist der einzige, der stirbt. Bei den
übrigen sitzt jemand davor, wenn es knallt.

Vorschlag (Cron-Pfad → Owner-Entscheid + `main`-Merge): **die Lösung vom 15.09. übertragen**, nicht
neu erfinden — `--dim1024` plus seitenweises Laden nach dem Muster von `pipeline/foresight.py`.
Vorher zu messen: was das 1024er-Präfix mit der Head-Güte macht (Holdout-Vergleich, der Trainer
gibt ihn schon aus). `--sample` bleibt der billige Notausgang, falls die Güte leidet. Unabhängig
davon fehlt die Sichtbarkeit: `loop finished WITH ERRORS` steht nur im Log, der Wächter prüft den
Discovery-Loop nicht — drei Sonntage sind darum unbemerkt geblieben.

Der nächste Lauf ist Sonntag 27.09. 06:00 und würde erneut scheitern.

## 2026-09-26 · change · Retrain der Distill-Heads läuft wieder — auf dem 1024er-Präfix

Umsetzung des Befunds von heute früh (Eintrag oben). Zwei Ursachen, beide behoben.

**Erstens hielt der Lader die Matrix zweimal.** `_stream_trends` sammelte Häppchen in
einer Liste und schloss mit `np.vstack(chunks)` — in dem Moment liegen Häppchen und
Ergebnis nebeneinander, also 2 × 29,9 GB. Das allein erklärt die 56,6 GB, noch vor
jeder sklearn-Kopie. Jetzt wird erst gezählt, dann keyset-paginiert in EINE vorbelegte
Matrix geschrieben (Muster `pipeline/foresight.py`); der Server-Cursor entfällt.

**Zweitens sind 4096 Dimensionen die Matrix.** `--dim` (Default **1024**) trainiert auf
dem Matryoshka-Präfix, also auf `trends.embedding_1024` — das per Definition
`embedding[:1024]` ist (`db.insert_trend`), weshalb es kein Abschneiden ins Blaue,
sondern derselbe Vektorraum ist. Unter Postgres kommt damit auch ein Viertel des
Textes über die Leitung.

**Die Inferenz bleibt unangetastet.** Alle Aufrufer (`llm_processor`, `signal_batch`,
`reclassify`, `mega_trend_reviewer`, die vier On-demand-Skripte) übergeben weiter den
vollen 4096er-Vektor; `pipeline/distill._HeadInput` schneidet je Head auf dessen
`n_features_in_` und normalisiert DANACH — bitgleich zu dem, was der Trainer geladen
hat. Das ist die Voraussetzung dafür, dass die vier neuen 1024er neben dem 4096er
`signal_type`-Head (#110) laufen; beide Breiten gleichzeitig sind heute auf der Platte
geprüft, nicht nur im Unittest.

Dazu zwei Kleinigkeiten, die beide aus dem Vorfall selbst folgen: ein **Preflight**
rechnet `n × dim × 4 × 2,5` gegen `MemAvailable` und bricht mit lesbarer Meldung ab
(der Faktor ist gemessen, nicht hergeleitet — das Laden ist mit 2,2–2,5 × Matrix die
Spitze, nicht die spätere Kopie mit 1,9 ×), und **alle Ausgaben sind ungepuffert**: bei
SIGKILL war der Puffer verloren, genau deshalb stand in den drei OOM-Logs so wenig.

### A/B über die Dimension, identische Zeilen (205.567 Train / 22.840 Holdout)

| | 1024 | 4096 | Δ |
|---|---|---|---|
| Vertical Top-1 | 0,9118 | 0,9297 | −1,79 pp |
| Mega Top-1 | 0,8539 | 0,8673 | −1,34 pp |
| Mega Top-3 | 0,9819 | 0,9849 | −0,30 pp |
| PESTEL micro-F1 | 0,9169 | 0,9323 | −1,54 pp |
| Laufzeit | 237 s | 886 s | 3,7 × |
| Spitze RSS | 2,4 GB | 8,7 GB | 3,6 × |

Das Präfix kostet also gut anderthalb Punkte je Head — bei gleicher Zeilenzahl.

### Volllauf gegen den produktiven Stand

Der Vergleich, der zählt: nicht 1024 gegen 4096, sondern **was heute nachts arbeitet
gegen das, was installiert würde.** 2.648 s, Spitze 16,9 GB, rc 0.

| | produktiv (4096, 1,02 Mio., 07.08.) | neu (1024, 1,83 Mio.) |
|---|---|---|
| Vertical Top-1 | 0,9099 | 0,9092 |
| Mega Top-1 / Top-3 | 0,8429 / 0,9764 | **0,8525 / 0,9803** |
| PESTEL micro-F1 | 0,9091 | **0,9170** |
| Relevanz P / R / Acc | 0,8821 / 0,9030 / 0,8826 | 0,8818 / **0,8774** / 0,8839 |

Die vierfache Zeilenzahl holt den Präfix-Verlust also auf und überholt ihn in der
Summe — Vertical gleich, Mega und PESTEL besser.

### Was schlechter wird, und es ist nicht nichts

Die Summe verdeckt eine Umverteilung. Nach Mega-Klasse (Top-1-Recall im Holdout):

| Klasse | alt | neu | n |
|---|---|---|---|
| quantum_information_science | 0,361 | **0,752** | 2.380 |
| digital_healthcare_integration | 0,292 | **0,572** | 3.740 |
| education_and_lifelong_learning | 0,191 | **0,569** | 1.525 |
| clean_energy_transition | 0,873 | **0,907** | 18.218 |
| circular_economy_and_zero_waste | 0,693 | 0,620 | 819 |
| experience_economy_and_immersive_design | 0,401 | 0,326 | 599 |
| next_generation_semiconductors | 0,329 | 0,168 | 452 |
| connected_living_and_smart_spaces | 0,242 | 0,141 | 645 |
| cultural_heritage_and_identity | 0,099 | 0,030 | 169 |
| evolution_of_work_models | 0,094 | 0,014 | 138 |
| **virtual_worlds_consolidation** | 0,047 | **0,000** | 300 |

Das Muster ist eindeutig: es gewinnen die grossen Klassen, es verlieren die kleinen,
und **eine Klasse wird unerreichbar** (`virtual_worlds_consolidation`) — in der
produktiven Fassung war keine tot. Der Code nennt so eine Klasse an anderer Stelle
zu Recht „dead weight in the yaml": sie steht in `mega_trends.yaml`, aber kein Signal
bekommt sie mehr. Dass das nicht nur an der Datenmenge liegt, zeigt das A/B: bei
gleichen Zeilen hatte 1024 zwei tote Klassen, 4096 eine.

Naheliegende Kur, bewusst NICHT in denselben Lauf gepackt: `class_weight='balanced'`
für den Mega-Head — genau das, was der Signaltyp-Head (#110) für seine kleinen Klassen
schon tut. Das ist ein eigener Messlauf, keine Beifuhr.

Zweiter Posten: die **Relevanz-Trefferquote fällt um 2,6 Punkte** (0,9030 → 0,8774) bei
gleicher Präzision. Ein Teil ist die Datenlage, nicht die Dimension — es gibt jetzt
322.824 Negativbeispiele gegen 256.575 im August, bei unverändert 300.000 Positiven.
Das Hybrid-Tor mildert es (verworfen wird unter 0,3, behalten über 0,7, dazwischen
entscheidet das 8B), ein schwächerer Recall schiebt also eher ins Zweifelsband als in
den Müll — er kostet Rechenzeit, nicht Inhalt. Nach der ersten Nacht mit neuen Heads
gehört `filtered/processed` in `data/cycle_log.jsonl` angesehen (zuletzt 65/300 = 22 %).

### Sichtbarkeit

Neue Alarmregel `job_failed`: endet der letzte abgeschlossene Lauf eines Jobs mit
`rc != 0`, gibt es eine Mail, und der Alarm bleibt, bis derselbe Job wieder mit 0
endet. Rauschprobe über 14 Tage `ops_events`: vier Zeilen mit `rc != 0` — zwei der
echte Defekt, eine ein fehlgeschlagener `publish_static_site` (auch meldenswert), eine
aus dem entfernten Dossier-Feature. `rc=75` (Skip des GPU-Kollisionswächters) ist über
`job_failed_ignore_rc` in der yaml ausgeklammert.

Der Sonntagslauf morgen 06:00 stösst den Retrain an (`mega_trends.yaml` vom 08.08. ist
neuer als `meta.json` vom 07.08.) — **mit dem Merge nach `main` gelingt er, und die
neuen Heads gehen in Betrieb.** Danach stellt sich der Schritt von selbst ab, bis die
Taxonomie wieder geändert wird.

## 2026-09-26 · change · Mega-Head mit Klassengewichtung — und die Abstain-Schwelle gehört zum Modell

Owner-Entscheid nach Messung. Der Mega-Head trainiert ab jetzt mit
`class_weight='balanced'` (Default in `train_distill_heads.py`, der Sonntagslauf ruft
ohne Flags auf). Anlass war der Befund aus dem Umstieg auf 1024 Dimensionen: die
Summe sah besser aus als der produktive Stand, aber `virtual_worlds_consolidation`
war unerreichbar geworden.

### Drei Stände, Recall je Klasse (Auszug, nach Klassengröße)

| Klasse | n | produktiv 07.08. | neu ungew. | neu balanced |
|---|---|---|---|---|
| virtual_worlds_consolidation | 58 | 0,019 | **0,000** | **0,793** |
| evolution_of_work_models | 138 | 0,094 | 0,014 | **0,928** |
| cultural_heritage_and_identity | 169 | 0,099 | 0,030 | 0,722 |
| platformization_of_culture | 298 | 0,265 | 0,268 | 0,896 |
| next_generation_semiconductors | 452 | 0,329 | 0,168 | 0,838 |
| orbital_economy_expansion | 739 | 0,068 | 0,055 | 0,796 |
| connected_living_and_smart_spaces | 645 | 0,242 | 0,141 | 0,651 |
| inclusive_and_human_centric_design | 2.961 | 0,457 | 0,427 | 0,481 |
| clean_energy_transition | 18.218 | 0,873 | 0,907 | 0,849 |
| artificial_intelligence_and_automation | 32.850 | 0,896 | 0,923 | **0,740** |
| personalized_health_and_longevity | 50.185 | 0,958 | 0,956 | 0,862 |

| | Top-1 | Top-3 | macro-Recall | tote Klassen |
|---|---|---|---|---|
| produktiv 07.08. (4096, ungew.) | 0,8429 | 0,9764 | 0,5417 | 0 |
| neu (1024, ungew.) | 0,8525 | 0,9803 | 0,5487 | 1 |
| **neu (1024, balanced)** | 0,8165 | 0,9670 | **0,8106** | **0** |

22 von 28 Klassen werden besser. Der Preis in Zeilen statt in Prozent: **7.163
Holdout-Zeilen werden richtig statt falsch, 13.509 falsch statt richtig, Saldo
−6.346** (−3,61 pp). 79 % der Verluste liegen in zwei Klassen (AI 6.012 Zeilen,
personalized_health 4.717). Die Klassen unter 1.000 Zeilen, um die es geht, sind
zusammen 3,0 % des Holdouts.

Die Entscheidung ist also eine **Umverteilung, kein Gewinn**, und sie folgt dem Zweck
des Labels: der Mega-Trend füllt `/trends/mega/<m>`, die Newsletter-Themenwahl und die
28 Themes des Research Pulse. Ein Thema, das nie zugewiesen wird, hat eine leere Seite
und zeichnet ein falsches Bild seines Feldes — das ist schlimmer als eine gelegentlich
falsche Zuweisung. Für die Gesamtgenauigkeit wäre die andere Wahl richtig gewesen;
`--mega-class-weight none` stellt sie her.

`inclusive_and_human_centric_design` bewegt sich mit 2.961 Zeilen kaum (0,427 →
0,481). Das ist kein Gewichtungsproblem, sondern ein Hinweis, dass die Klasse
inhaltlich unscharf ist — Wiedervorlage bei der nächsten Taxonomie-Runde.

### Der Nebenfund, der wichtiger war als die Gewichtung

Beim Prüfen der Wechselwirkung mit `MEGA_ABSTAIN_THRESHOLD = -1.0` (ab wann ein Signal
`mega_trend = NULL` bekommt) kam heraus: **die Schwelle war nie eine Naturkonstante,
sondern an die 4096er-Skala geeicht.** Gemessen an 20.000 Zeilen quer durch den
Bestand:

| Mega-Head | Abstain bei −1,0 | Top-Score Median | p10 |
|---|---|---|---|
| produktiv (4096, ungewichtet) | **7,2 %** | +1,47 | −0,77 |
| neu (1024, balanced) | **12,9 %** | +0,86 | −1,21 |

Weniger Dimensionen liefern kleinere Entscheidungswerte, Klassengewichte verschieben
sie zusätzlich. Mit dem unveränderten Wert hätte der Umstieg die Abstain-Quote fast
verdoppelt — also mehr `mega_trend = NULL` und leerere Themenseiten, das genaue
Gegenteil dessen, was die Gewichtung kaufen soll. Das hätte beim Merge am Nachmittag
auffallen müssen und fiel erst beim zweiten Hinsehen auf.

Behoben nicht durch eine neue Zahl, sondern durch Zuständigkeit: der Trainer nimmt das
Quantil zur Zielquote `--mega-abstain-rate` (Default 0,072 = das produktive Verhalten)
**auf dem ganzen Holdout** — nicht nur auf mega-gelabelten Zeilen, denn der
Produktivstrom enthält Signale, denen kein Mega-Trend passt, und genau für die ist das
Abstain da — und schreibt sie nach `models/distill/meta.json`. `DistillClassifier`
benutzt die Schwelle des geladenen Modells; die Konstante in `pipeline/distill.py` ist
nur noch der Rückfall für Heads von vor heute. Damit kann kein künftiger Wechsel von
Dimension oder Gewichtung dieselbe stille Verschiebung mehr auslösen. Quantil-gleich
wären auf dem Volllauf-Head −1,418 gewesen; der Trainer rechnet es je Lauf neu (beim
40k-Probelauf −1,605 — dass die Zahl mitwandert, ist der Beweis, dass sie nicht
konstant ist).

Gepinnt sind jetzt auch die Cron-Defaults (`tests/test_distill_dim.py`): Dimension
1024, `balanced`, Abstain-Zielquote 0,072, kein `--sample`. Der Sonntagslauf ruft ohne
Argumente auf — diese vier Werte SIND das Produktivverhalten.

## 2026-09-27 · change · Der Sonntagslauf ist durchgelaufen — erstmals seit dem 07.08.

`discovery_loop` 06:00–06:51, `retrain rc=0`, `loop done.` — **2.968 s, Spitze 17,0 GB**
gegen 56,6 GB und SIGKILL an den drei Sonntagen davor. Die produktiven Heads tragen
jetzt `trained: 2026-09-27`, 1.644.616 Trainingszeilen, 182.735 Holdout.

| | Wert | gestern gemessen |
|---|---|---|
| Vertical Top-1 | 0,9092 | 0,9092 |
| Mega (balanced) Top-1 / Top-3 | 0,8165 / 0,9670 | 0,8165 / 0,9670 |
| Mega macro-Recall | 0,8106 | 0,8106 |
| tote Klassen | **keine** | keine |
| PESTEL micro-F1 | 0,9170 | 0,9170 |
| Relevanz P / R / Acc | 0,8818 / 0,8774 / 0,8839 | dito |

Exakt reproduziert, weil der Lader seit gestern deterministisch ist (Keyset nach `id`,
kein `ORDER BY RANDOM()`). Dass die Vorhersage und der Produktivlauf sich auf die
vierte Stelle treffen, ist der eigentliche Beleg dafür, dass die Messung von gestern
den Produktivpfad beschrieben hat und nicht ein Laborartefakt war.

**Die Abstain-Schwelle wurde mitkalibriert: −1,442** (Vorabrechnung sagte −1,418).
Gegenprobe auf einer ANDEREN Stichprobe (10.564 Zeilen, `mod(id,173)` statt
`mod(id,91)`): Abstain **6,72 %** bei Zielquote 7,2 % — und **12,58 %**, wenn dort die
alte Konstante −1,0 gegolten hätte. Der Fund von gestern Abend hat also real eine
Verdopplung der `mega_trend = NULL`-Quote verhindert, eine Stunde bevor sie in Betrieb
gegangen wäre.

**Die Alarmkette hat funktioniert**, und zwar vollständig: `job_failed / discovery_loop`
ausgelöst 26.09. 17:36 (die Regel fand den rc=1 vom 20.09. beim ersten Messlauf nach
dem Merge), **entwarnt 27.09. 06:52** — eine Minute nach dem erfolgreichen Lauf. Das
ist der Zyklus, den die Regel verspricht, einmal komplett durchlaufen. Offen bleibt
`job_failed / advisory` (rc=143 vom 14.09., entferntes Feature); er fällt am 28./29.09.
aus dem 14-Tage-Fenster und entwarnt sich selbst.

Nebenbei behoben: `meta.json` trug weder Laufzeit noch Spitzenspeicher, weil die Datei
geschrieben wurde, BEVOR `total_s` und `peak_rss_gb` gesetzt waren — der Report daneben
hatte sie, die Herkunftsdatei am Modell nicht. Genau die liest man aber, wenn man
Wochen später wissen will, was ein Lauf gekostet hat.

Offen: `inclusive_and_human_centric_design` bleibt trotz Gewichtung bei Recall 0,481
(2.961 Zeilen) — kein Gewichtungsproblem, sondern eine inhaltlich unscharfe Klasse.
Wiedervorlage bei der nächsten Taxonomie-Runde. Und der erste Nachtlauf mit den neuen
Heads ist Montag, 28.09., 02:45; danach gehört `filtered/processed` in
`data/cycle_log.jsonl` angesehen (zuletzt 65/300 = 22 %), weil die
Relevanz-Trefferquote um 2,6 Punkte gefallen ist.

## 2026-09-27 · change · 35B gestoppt, Ruhezustand 8B; GPU abends für Schlagwort-Piloten belegt

Auf :8090 lief seit Sa 26.09. 19:13 **Qwen3.6-35B** (`start-active.sh` → `start-qwen3.6-35b.sh`,
kein Besitzvermerk) statt des Ruhezustands. Owner 27.09.: „Wenn wir das 35B nicht benötigen,
kannst du es stoppen." Seit 23:02 wieder **Qwen3-8B** (`start-qwen3-8b-208k.sh`) — den
erwartet der Wächter um 07:45; der Nachtlauf 02:45 hätte ihn ohnehin hergestellt.

Dazwischen war die Karte für zwei Piloten belegt (22:06–22:38 und 22:41–23:02), angemeldet
über `data/llama-server.tag_eval.pid` und `ops_events` (Job `tag_eval`), damit
`gpu_foreign` nicht mailt. Ergebnis: `docs/tag_eval_2026-09-27.md` — keine kleinen LLMs
für Tags, Reranker nur bei Patenten besser und in llama.cpp zu langsam (17–25 Paare/s).
Neu in `~/llama.cpp/models`: Qwen3-Reranker-0.6B (Q8_0), Qwen3.5-4B und Gemma 4 E4B (je Q4,
zusammen ~7 GB, nicht gebraucht — Löschen auf Owner-Wort).

