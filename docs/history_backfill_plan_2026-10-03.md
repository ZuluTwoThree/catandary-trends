# Vergangenheit des Signalraums vervollständigen, ohne die DB aufzublähen (Plan, 2026-10-03)

**Status (03.10. 11:05):** gebaut, der Einbettlauf auf 3090 + 5080 läuft. Tabellen `history_items` /
`history_vectors` (additiv, `pipeline/history_vectors.py`), Warteschlange 1.333.777, Vektoren im
Tablespace `hdd`. Wolke und Nester lesen die Vergangenheit noch nicht.

## Anlass

Owner-Fragen 03.10.: Lässt sich die Signalwolke mit dem Zitationsgraphen der TIR verbinden?
Und wie wird die Datenbasis der Vergangenheit vollständiger, ohne dass die DB wächst?

Gemessen (03.10.):
- Patente mit Vektor im Signalraum: 267.846, davon 81 % aus 2024–2026.
- Sie zitieren 903.262 verschiedene Patente. Davon haben 340.160 Text, aber fast keines hat einen Vektor.
- Kanten mit beiden Enden in der Wolke: nur 6.316.

## Strategie

1. **Zählen braucht keine Vektoren.** Mengen je Jahr liefert die Volltextsuche über den
   ganzen Bestand (`research_corpus`, `patent_search`; so arbeitet `calendar_dating`).
   Vektoren braucht nur, wer einen Punkt in die Wolke setzen oder einem Nest zuordnen will.
2. **Stichprobe statt Bestand, geschichtet nach Monat und Ebene.**
   - Zufallsschicht: je Monat und Ebene 2.000 Dokumente, gezogen über den kleinsten Hash
     (`(k * 2654435761) mod 2^32`, wie die Wolke).
   - Patente: je DOCDB-Familie eine Veröffentlichung, datiert auf die früheste.
   - Jeder Punkt trägt das Gewicht `Rahmen / Stichprobe` seines Monats. Ohne Gewicht
     sähe die Vergangenheit im Archiv-Scan hundertfach dünner aus.
3. **Zitationsschicht:** jede Patentfamilie mit Text, die ein Patent im Signalraum zitiert.
   Sie ist die Brücke zum TIR-Graphen, ausdrücklich nicht repräsentativ, gekennzeichnet und
   nie gewichtet.
4. **Eigene Nebentabelle, nicht `trends`.**
   - Inhalt: Dokument-Verweis, Monat, Ebene, Gewicht, Schicht, 1024er-Präfix als float16
     (gepackte Bytes; `pgvector` 0.6 kennt kein `halfvec`).
   - Weggelassen: 4096er, HNSW, Textkopie. Der Text liegt schon in `raw_entries` bzw.
     `research_corpus`.
   - Begründung: Eine Zeile in `trends` kostet ~33 KB (16 KB 4096er, 4 KB 1024er, ~8 KB
     Anteil am 17-GB-HNSW). Massen-INSERTs dort blähen den Index; Feed, Suche und Richter
     sollen diese Zeilen nie sehen.
   - Kandidat für den Tablespace `hdd` (s. u.), denn es sind kalte, sequenziell gelesene Daten.
5. **Gleiches Textrezept wie der Signalpfad:** Titel + Abstract[:500] (Signale: Titel +
   Excerpt[:500]), sonst wäre es ein anderer Vektorraum.
6. **Platz:** Die drei `*_old`-Tabellen (36 GB) wandern auf die HDD statt gelöscht zu werden
   (Owner 03.10.): `scripts/move_cold_tables_to_hdd.sh [--apply]`. Das Skript legt den
   Tablespace `hdd` unter `/mnt/data-hdd/pg_tablespace` an (einmalig `sudo`) und verschiebt
   Tabellen samt Indizes. Folgen für den Restore: `docs/restore_runbook.md`.

## Probelauf (03.10., Quote 2.000/Monat, bis Ende 2022, 147 s)

| Ebene | Monate | Rahmen (mit Abstract) | schon im Raum | Zufallsschicht | davon einzubetten | Zitationsschicht einzubetten |
|---|---|---|---|---|---|---|
| Patente 1990–2022 | 396 | 7.858.251 Familien | 43.767 | 792.000 | 787.768 | 227.317 (von 262.964 zitierten) |
| Forschung 2010–2022 | 156 | 29.307.128 Arbeiten | 188.054 | 312.000 | 311.564 | — |

- **Einzubetten:** 1.326.649 Texte.
- **Rechenzeit, 3090 + 5080 parallel:** **7,3 h**. Die 5080 trägt 63 %, die 3090 37 %
  (Raten vom 28.09.: 18,5 bzw. 32 Texte/s bei ~600 Zeichen). Auf der 3090 allein wären es
  19,9 h. Die Vektoren beider Karten sind austauschbar (Kosinus 0,998).
- **Speicher:** 2,9 GB Nebentabelle (in `trends` wären es ~44 GB).
- **RAM:** +2,7 GB, falls der Discover-Dienst die Vergangenheit mitlädt (optional).
- Rohdaten: `data/history_plan.json`.

## Befunde und Grenzen

- **Der Patentrahmen spiegelt unseren BDDS-Bestand, nicht die Welt.**
  - 1990–2004 sind es nur ~45–70k Familien je Jahr, ab 2005 ~200k, ab 2017 ~700k–1,15 Mio.
  - Innerhalb eines Monats ist die Stichprobe repräsentativ für den Rahmen. Absolute
    Mengen über Jahre sind deshalb nicht vergleichbar, Anteile je Monat schon. So
    normalisieren Wolke und Messachsen ohnehin (je 10.000 Signale desselben Monats).
- **Die Zitationsschicht ballt sich 2016–2022** (je ~17–26k). Das sind die Patente, auf
  denen die heutigen aufbauen.
- **Forschung vor 2010** bleibt dünn wie `research_corpus` selbst.
- **Einzelfragen bleiben Zufall:** „Liegt Patent X in Nest Y?" ist für die Vergangenheit
  nur dann beantwortbar, wenn X gezogen wurde (oder zitiert ist).

## Gebaut (03.10.)

- **Tabellen:**
  - `history_items`: eine Zeile je Dokument der Stichprobe. Felder: Ebene, Verweis, Monat,
    Schicht (`random` | `cited`), Kennzeichen `cited`, Gewicht und die Buchführung der Arbeiter.
  - `history_vectors`: Item → 1024er-Präfix, L2-normiert, float16 (2.048 B), plus Gerät.
  - Breite Zeilen werden nur einmal geschrieben, nie geändert; die Buchführung liegt auf den
    schmalen Items. Die Vektortabelle liegt im Tablespace `hdd`.
- **Auswahl** `scripts/history_embed.py select`: 1.021.777 Patente (792.000 Zufall + 229.777
  zitiert) und 312.000 Arbeiten in 7,5 min.
- **Arbeiter** `scripts/history_embed.py work --host URL --name GERÄT`:
  - holen sich Pakete per `FOR UPDATE SKIP LOCKED`, beliebig viele Arbeiter auf beliebig
    vielen Karten;
  - ein Paket, dessen Vormerkung älter als 20 min ist, wird wieder frei; ein abgebrochener
    Lauf verliert also nichts, und ein Neustart macht weiter;
  - mit `--handover` holt der Arbeiter auf der lokalen 3090 das Einbettmodell auf :8090 und
    stellt danach den Ruhezustand (8B) wieder her.
- **Zwei Karten** `scripts/run_history_embed.sh`:
  - hält auf bequietUbuntu Nemotron an, startet dort Qwen3-Embedding-8B auf :8095 und
    startet die Unit im EXIT-Trap wieder;
  - lokal ein Arbeiter mit Handover;
  - `history_embed` steht in `GPU_GUARD_PATTERNS`, der Nachtlauf wartet also auf ihn;
  - Logs: `~/logs/history-embed-{run,3090,5080}-<Zeit>.log`.
- **Prüfung** `scripts/history_embed.py check --host URL`: bettet Patente ein, die schon in
  `trends` stehen, und vergleicht mit `embedding_1024`, ohne etwas zu schreiben. Ergebnis
  03.10. auf dem CPU-Embedder: Median 0,998, Minimum 0,994.
- **Gemessen im Lauf:** 5080 ~35 Texte/s, 3090 ~26/s (beide höher als die Schätzung), also
  ~6 h statt 7,3 h.
- **Platz:** Die `*_old`-Tabellen liegen seit 03.10. im Tablespace `hdd`; auf `/` sind 34 GB
  mehr frei.

## Nächste Schritte (nicht gebaut)

1. Wolke und Archiv-Scan lesen die Nebentabelle mit Gewicht. Die Wolke bekommt die
   Zitationskanten als gebündelte Flüsse zwischen Nestern.
