# Vergangenheit des Signalraums vervollständigen, ohne die DB aufzublähen (Plan, 2026-10-03)

**Status:** Plan + Probelauf (`scripts/history_plan.py`, schreibt nichts). Noch nichts eingebettet.

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

## Nächste Schritte (nicht gebaut)

1. Tabelle `history_vectors` (additiv) und ein Einbett-Lauf mit zwei Arbeitern: 3090 lokal
   und 5080 auf bequietUbuntu per SSH-llama-server. Die 5080 nur nach Owner-Freigabe, weil
   es dort kein festes Fenster gibt. Der Lauf ist in Stücken fortsetzbar.
2. Wolke und Archiv-Scan lesen die Nebentabelle mit Gewicht. Die Wolke bekommt die
   Zitationskanten als gebündelte Flüsse zwischen Nestern.
