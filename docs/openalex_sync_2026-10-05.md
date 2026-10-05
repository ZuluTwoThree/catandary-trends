# OpenAlex-Monats-Sync 05.10.2026 — was OpenAlex verändert hat, Halt, Vorschläge

> Owner 05.10. abends: „Halte ihn kontrolliert an. Dann gib mir ein Update, was OpenAlex verändert
> hat und wie wir in Zukunft besseren Nutzen aus dem Sync ziehen und die Datenbank weniger unter
> Last halten." Gemessen am 05.10.2026; alle Zahlen aus S3-Listing, `openalex_snap_state`,
> `pg_stat_user_tables` und einer Stichprobe aus der jüngsten Partition.

## 1. Was passiert ist

- Cron `0 2 5 * *` startete `sync_openalex_monthly.sh` um 02:00. Im September war nichts zu tun
  (7 min). Diesmal: **2.040 Part-Dateien, davon 1.375 neu**.
- Schritt 1 (Snapshot-Ingest) lief 18 h. Die Datenbank stand den ganzen Tag unter Last; der
  Export-Build der Website scheiterte um 08:33 an einem `statement_timeout` (Mega-Seiten).
- **Kontrolliert angehalten 05.10. ~20:00** (Owner): erst Wrapper (Schritte 2–5 starten nicht),
  dann der Ingest-Hauptprozess; die vier Arbeitsprozesse haben ihr laufendes Teilstück zu Ende
  geschrieben (Zeilen + Archivdatei + Erledigt-Vermerk) → `openalex_snap_state` 3.641 → 3.645,
  keine halben Teilstücke. Stand: **1.198 von 1.375 neuen Teilstücken** erledigt, offen **177**
  (`updated_date=2026-09-22` 126 von 160, `2026-09-23` 50 von 50; zusammen ~150 GB Parquet).
  **Schritte 2–5 (Journale, Archiv-Extrakt, Förderer/OA, Statistik) sind für den ganzen Monat
  noch nicht gelaufen**; `research_corpus_meta.total` steht noch auf dem 05.09. (45.598.470).
- Fortsetzen: `scripts/sync_openalex_monthly.sh` (alle Schritte resumable über ihre State-Tabellen).
  Dauer der Schritte 2–4 bei diesem Umfang ist **nicht gemessen** — im September liefen sie leer.

## 2. Was OpenAlex verändert hat

| | |
|---|---|
| Snapshot jetzt | 2.040 Dateien, 707 GB, Partitionen `updated_date` 2016-06-24 … 2026-09-23 |
| verschwundene Datumspartitionen seit dem letzten Lauf | 114 (z. B. 2016-10-14 … 2025-11-04) — ihre Werke stehen jetzt in neueren Partitionen |
| Partitionen Juli–Sept. 2026 | 1.367 Dateien, **614 GB = 87 % des Volumens** |
| Schema | 49 Spalten; alle, die wir lesen, unverändert vorhanden |

**OpenAlex hat fast den ganzen Bestand mit neuem `updated_date` neu ausgegeben.** Für uns zählt,
was sich an den Werken ändert. Stichprobe 3.000 gefilterte Werke aus `updated_date=2026-09-23`:

- 2.354 (78 %) stehen schon im Korpus. Bei **51 % davon hat sich die Zitationszahl geändert**
  (Median +2). Der Sync verwirft diese Änderungen (`ON CONFLICT (id) DO NOTHING`, s. Kopf von
  `sync_openalex_monthly.sh`); `cited_by_count`/`fwci` in `research_corpus` altern also.
- Die neuen Werke sind nicht nur neue Veröffentlichungen: viele tragen `created_date` 2016 ff. —
  ältere Werke, die erst jetzt unseren Filter passieren (Abstract vorhanden, englisch, bei
  Jahrgängen ≤ 2023 mindestens ein Zitat).

**Ertrag des Laufs:** Zähler „übernommen" 25,3 Mio. (= Werke, die den Typ-/Sprach-/Jahresfilter
passieren, *inklusive* vorhandener). Tatsächlich eingefügt: **1.509.474 Zeilen** (`n_tup_ins` seit
dem Statistik-Reset 26.09.; außer dem Sync schreibt nichts in die Tabelle) — rund **6 %**.

## 3. Warum die Datenbank so leidet

1. **Volltext-Vektor für Duplikate.** `INSERT_TMPL` berechnet `to_tsvector` über Titel + bis zu
   16.000 Zeichen Abstract für **jede** Zeile im Batch — auch für die ~94 %, die danach am
   Primärschlüssel abprallen. Das ist die meiste CPU des Laufs, für nichts.
2. **Kein Zeitfenster, kein sanfter Halt.** Der Lauf nimmt sich so viele Stunden, wie er braucht,
   und kollidiert mit Backup (01:30), Publish (02:00), Nachtlauf (02:45), Samstags-Ingestern.
   Es gibt keinen SIGTERM-Pfad, der „keine neuen Teilstücke mehr, laufende fertig" macht.
3. **Archivkopie wächst mit jeder Neuausgabe.** `/mnt/data-hdd/openalex_snapshot` (99 GB) bekommt
   für jedes neu ausgegebene Werk eine zweite Kopie; alte Partitionsdateien bleiben liegen.
4. **Nebenlast, unabhängig vom Sync:** der Ops-Sampler zählt alle 10 min den Backlog über
   `get_unprocessed_entries(limit=99999)` (`pipeline/ops_probe.py`). Dokumentiert mit ~2 s, gemessen
   am 05.10. abends > 60 s mit drei parallelen Workern.
5. **Der Export-Build hat keine Geduld.** Die Seitenabfragen laufen mit 20-s-Timeout; unter Last
   scheitert der ganze Build, statt es später noch einmal zu versuchen.

## 4. Vorschläge

**Weniger Last (in dieser Reihenfolge, je klein):**

1. **Vorhandene IDs vorher aussortieren:** je Batch `SELECT id FROM research_corpus WHERE id = ANY(…)`
   (Primärschlüssel, billig), nur die neuen Zeilen einfügen. Spart den Volltext-Vektor für ~94 % der Zeilen.
2. **Zeitfenster + sanfter Halt:** `--until HH:MM` und ein SIGTERM-Handler (keine neuen Teilstücke,
   laufende fertig). Der Sync läuft dann nur in freien Fenstern (z. B. 09:00–00:30, nicht Sa 06–09)
   und setzt am nächsten Tag fort, bis er fertig ist; Cron täglich „fortsetzen, wenn offen", sonst no-op.
3. **Weniger parallele Arbeitsprozesse** (4 → 2) und `nice`/`ionice` für die Python-Seite.
4. **Backlog-Messung des Samplers** auf eine billige Schätzung umstellen oder nur stündlich.
5. **Export-Build:** bei Timeout einmal nach 30 min wiederholen; oder die zwei teuren
   Abfragen (Mega-Seiten, Methodik) vorab als Datei rechnen wie schon die Methodik-Statistik.

**Mehr Nutzen aus demselben Lesen:**

1. **Zitationen frisch halten über eine Nebentabelle** `research_citations(id, cited_by_count, fwci,
   citation_normalized_percentile, updated_date)` — Upsert beim Lesen, ohne die 147-GB-Tabelle und
   ihre Indizes (13 GB GIN) anzufassen (vgl. Lehre „kein Massen-UPDATE auf großen Tabellen").
   Meistzitiert-Listen in Sheet, Explorer, Pulse lesen dann aktuelle Zahlen.
2. **Zurückziehungen nachziehen:** `is_retracted` als kleines UPDATE nur für die Werke, bei denen
   es kippt.
3. **Neue Felder nutzen, die wir ohnehin lesen könnten:** `referenced_works` (Zitationsgraph der
   Forschung, #84), `best_oa_location`/Lizenz (offene Lizenzen ohne OpenAlex-API-Aufrufe für
   `resolve_open_licence.py`), `citation_normalized_percentile`, `keywords`, `has_fulltext`.
4. **Archiv entdoppeln:** je Werk nur die jüngste Fassung behalten; verschwundene Partitionen löschen.

**Entscheidung offen (Owner):** wann die restlichen 177 Teilstücke und die Schritte 2–5 laufen —
Vorschlag: erst Punkte 1 und 2 der Lastliste bauen (je ~½ Tag), dann in Fenstern fortsetzen.

## 5. Umsetzung (Owner 05.10. abends)

Owner: „Deduplizierung am Anfang ist ein wichtiger Schritt, jedoch nicht um den Preis, dass wesentliche
Informationen verborgen bleiben, etwa wenn ein Abstract nachträglich hinzugefügt wird. Baue es so, dass
Daten robuster, sparsamer und mehrwertstiftend einfließen." Gebaut auf `dev`:

- **Ein Lesedurchgang, Änderungen erkennen** (`pipeline/openalex_sync.py`, `scripts/ingest_openalex_snapshot.py`):
  je Batch der bekannte Stand aus `research_work_state` (neu) und — nur wo nötig — Titel/Abstract aus
  `research_corpus`. Entscheidung je Werk siehe Tabelle; Journal/Förderer/OA/Rising-Papers im selben Durchgang.
- **Textvergleich**, nachgemessen an zwei Teilstücken (135.469 Werke): Mit reinem Leerraum-Vergleich
  galten 15 % als geändert, fast alles entferntes Markup. Mit Markup, Beschriftung („Abstract",
  „Background") und Untertitel-Kürzung als Nicht-Änderung: **2,1 %** — das sind bereinigte und
  vervollständigte Abstracts und wiederhergestellte Umlaute. Gekürzt (unser längerer Text bleibt): 0,4 %.

  | Fall | Wirkung |
  |---|---|
  | neu | Zeile + Vektor, Zustand, Journal, Förderer, OA, Rising Papers, Archiv |
  | Text echt geändert | Zeile neu (Titel, Abstract, Vektor, Metadaten), Archiv |
  | OpenAlex nur Anfangsstück (Abstract oder Titel) | nichts in research_corpus, `shortened` im Zustand |
  | zurückgezogen | Flag |
  | Zitationen/FWCI/Perzentil/Typ/OA | nur `research_work_state` (+ Rising Papers, OA) |
  | unverändert | nichts |

- **Gemessen am echten Schreiblauf** (1 Teilstück): 2.330 neu, 1.369 Text, 1 zurückgezogen, 67.385
  Zustandszeilen beim ersten Kontakt; **zweites Lesen: 0 Schreibvorgänge** (nach einem Fix: Postgres
  liefert REAL als kurze Dezimalzahl, ein exakter Vergleich hätte jedes Mal 95 % neu geschrieben).
- **Zeitfenster und sanfter Halt** im Wrapper, getestet: 2-min-Fenster → ein Teilstück, „pausiert",
  Schritte 2–5 ausgelassen.
- **Leser:** Trajectory Sheet „Meistzitierte Forschungswerke" und die Korpus-Suche (MCP) nehmen die
  frischen Zitationen/FWCI, lassen zurückgezogene Werke weg und zeigen Titel ohne Markup.
  Der Research Explorer im Frontend liest noch `research_corpus.cited_by_count` (offen).
- **Nachholen:** Timer `catandary-openalex-catchup` ab 06.10. 09:00 täglich (3 Arbeitsprozesse,
  `SYNC_REDO_SINCE=2026-10-05`): 174 offene + ~1.198 mit v1 gelesene Teilstücke. Erwartung: zwei
  bis drei Fenster. Danach Schritte 2–5 (Aggregate, Archiv-Extrakt, Statistik) automatisch.
- **Nicht umgesetzt:** Backlog-Messung des Ops-Samplers und Wiederholung des Export-Builds (eigene Punkte).

## 6. Zeitvergleich alter/neuer Weg (gemessen 05.10. abends) und Merge

Gemessen je Schritt an einem typischen Teilstück (328.042 Zeilen, 0,86 GB; Archiv-Extrakt an einer
Datei mit 22.993 Zeilen), linear auf die Zeilen hochgerechnet (±30 %).

| je Teilstück, Rechensekunden eines Prozesses | alt | v2 erster Kontakt | v2 ab dem nächsten Release |
|---|---|---|---|
| Lesen + Vergleichen | 247 | 229 | 143 |
| Schritte 2 + 4 (zwei weitere S3-Durchgänge mit JOIN aller Zeilen) | 125 | 0 | 0 |
| Schritt 3 (Archiv-Extrakt) | 9 | ~1 | ~1 |
| Summe | 381 | 230 (−40 %) | 144 (−62 %) |

Restarbeit dieses Monats (1.372 Teilstücke, ~439 Mio. Zeilen): alter Weg zu Ende ~18 h (4 Prozesse,
am Stück; verwirft Zitationen/Korrekturen/Zurückziehungen), v2-Nachholen ~28 h (3 Prozesse, in
Fenstern). v2 braucht diesmal länger, weil es die 1.198 schon mit v1 gelesenen Teilstücke neu liest.
Owner-Entscheid 05.10.: v2. **Merge nach main 05.10. 23:05**, Crontab `0 9 * * *` mit Nachhol-Env
installiert, dev-Timer gestoppt.

**Nachtrag 05.10. 23:30 (Owner):** Der Sync läuft nur noch **09:00–17:00** (`SYNC_WINDOW`, gleicher Tag;
außerhalb startet nichts, Schritte 2–5 nur bis 16:00). Das Nachholen braucht damit vier statt zwei
Tagesfenster — Erwartung: fertig gegen Ende der Woche.

**Nachtrag 05.10. 23:45 (Owner): nur schreiben, wenn der Wert sich unterscheidet.** Alle Upserts/Updates
des Ingests tragen `WHERE … IS DISTINCT FROM` (Zustand, Open-Access-Link, Rising-Papers-Zitationen,
Zurückziehung). Gemessen in einer zurückgerollten Transaktion an 15.996 Werken beim ersten Kontakt
(`updated_date=2026-09-22/part_0042`): Rising Papers 14.412 geplant → 5.390 geschrieben (37 %),
Open Access 11.195 → 2.139 (19 %) — hochgerechnet ~38 Mio. Zeilenversionen weniger im Nachholen.

## 7. Download und Verarbeitung getrennt (Owner 05.10. nachts)

Owner: „Ziel ist Download und Datenverarbeitung zu trennen. Download-Rate ist bis zu 500 Mbit/s auf FTTH."

Gemessen an einem offenen Teilstück (0,85 GB): Streamen während der Verarbeitung zog 1,4 GB über das Netz
und dauerte 184 s; Download am Stück 0,85 GB in 77 s (11 MB/s, ein Strom); Verarbeitung aus der lokalen
Datei **29 s** (15 s Lesen, 14 s Datenbank, ohne Schreiben); vorgefilterte Ablage 0,125 GB = 15 %.

Gebaut (dev):
- `scripts/download_openalex.py` — lädt offene Teilstücke parallel (`--streams`), neueste zuerst, filtert mit
  `ingest_openalex_snapshot.keep_mask` (derselbe Filter wie der Ingest), legt atomar unter
  `/mnt/data-hdd/openalex_staging/<partition>/<part>.parquet` (+ `.json` mit Zeilenzahl des Originals) ab,
  löscht die Rohdatei; Status `openalex_download_state` (additiv); Fenster/sanfter Halt wie der Ingest.
- `scripts/openalex_download.sh` — zwei Fenster 17:00–18:55 und 23:00–08:30 (Owner 06.10.: zwischen 19 und 23 Uhr
  bleibt die Leitung frei), Sperre, Laufprotokoll.
- Ingest: liest abgelegte Teilstücke lokal, gibt sie nach erfolgreicher Verarbeitung frei; `--local-only`
  verarbeitet nur Abgelegtes und meldet Ungeladenes als offen (kein vorzeitiges Abschließen).
- Sync-Wrapper: `SYNC_LOCAL_ONLY=1` (Default).

**Durchsatztest 06.10. 00:30–01:20 (Owner-Auftrag):** 2 parallele Downloads 11,3 MB/s, 4 parallel 11,6 MB/s,
8 parallel Zeitüberschreitungen (`FSTimeoutError`). Gegenprobe ohne Last: Hetzner-Speedtest (Nürnberg) und
S3 je ~11,4 MB/s ≈ 92 Mbit/s, ein Strom wie vier — **die Leitung der Workstation liefert ~92 Mbit/s, nicht 500**;
die Netzwerkkarte `enp4s0` ist mit 1000 Mb/s Vollduplex verbunden, der Engpass liegt dahinter (Switch/Router/
Kabel/Tarif — vom Rechner aus nicht bestimmbar). Folgen: `DL_STREAMS` Default 2 (einer füllt die Leitung schon);
**Bremse während des Nachtlaufs**: läuft `scheduled_cycle.sh`, laden alle Ströme zusammen höchstens
`DL_CYCLE_MBS` (7 MB/s ≈ 60 %) — getestet 6,8 MB/s. Rückstand ~614 GB ≈ 15 h Download, also gut eine Nacht
plus das Fenster 17–19 Uhr. Testfehler unterwegs: das Testskript startete nach einer überzogenen Stufe die
nächste mit bereits verstrichenem `--until`, das dann als „morgen" galt; abgebrochen, Rohdateien gelöscht.

## 8. OpenAlex-Release-Termine (aus `s3://openalex/RELEASE_NOTES.txt`, gelesen 06.10.2026)

Öffentliche Snapshot-Releases: **zweiter Mittwoch im Januar, April, Juli und Oktober** (UTC); dazwischen
gelegentlich weitere. Seit 2025-01-29 quartalsweise angekündigt, tatsächlich 2026 fast monatlich:

| Release | Inhalt laut Release Notes |
|---|---|
| 2026-09-23 | „quarterly snapshot with bug fixes and improvements" — der Release, der ~87 % neu ausgab |
| 2026-06-25 | Korrespondenzautoren überarbeitet, 57 M Werke mit corresponding_institution_ids, neue Förderer, **1,4 Mio. Abstracts wiederhergestellt** |
| 2026-05-22 | Autoren-Bereinigung (2,6 M Profile), 16 neue Förderer, Topics an Awards |
| 2026-04-29 | **PubMed-Bug abgeschnittener Abstracts behoben (7 M Werke)**, raw_orcid, Japan IRDB |
| 2026-03-30 | 12,1 M Awards, 283 neue Repository-Endpunkte, Topics/Concepts verbessert |
| 2026-02-25 | weitere Entitäten im Snapshot |
| 2026-02-03, 2026-01-15 | Datenqualität |
| 2025-11-12 | Wechsel auf das „Walden"-Datenmodell; enthält „xpac"-Datensätze, Works gesamt 463 M |
| 2025-01-29 | 350 k Junk-Abstracts entfernt; ab hier „quartalsweise" |

Nächster regulärer Termin: **Mittwoch 14.10.2026**. Der tägliche Sync (09:00–17:00) und der nächtliche
Download nehmen ihn ohne Eingriff mit.
