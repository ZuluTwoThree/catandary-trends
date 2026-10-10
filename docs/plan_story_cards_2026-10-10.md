# Plan: Story-Artikel, Signalkarten, Messkontext (Entwurf 10.10.2026)

Grundlage: `docs/article_value_measure_2026-10-10.md`. Heute schreibt Stufe 6 je Meldung einen
~150-Wörter-Artikel aus genau einer Quelle (1.060/Tag). Messung: ~76 Ereignisse/Tag haben ≥ 2
unabhängige Quellen; ein Messkontext aus Forschung/Patenten/Förderung findet sich per Vektornähe bei
~21 % der Artikel (HEALTH 43 %, BIZ 7 %, DESIGN 0 %); ~127 Artikel/Tag sind Folgeberichte.

Zielbild — drei Formen statt einer:

| Form | Menge | Inhalt | wer schreibt |
|---|---|---|---|
| **Story-Artikel** | ~76/Tag (Ereignisse mit ≥ 2 Quellen) + Einzelmeldungen mit Kontext | Synthese mit Zuordnung je Aussage + Messblock | Modell (Synthese), SQL (Messblock) |
| **Signalkarte** | alle übrigen relevanten Meldungen | übersetzter Titel, Quelle, Link, Signaltyp, Ebene, Kontextzeile | niemand (Übersetzung 8B) |
| **Themenseite** | Mega-Themen, Nester | Karten + Messreihe | SQL (+ optional Owner-Absatz) |

Leitplanken: keine Massen-UPDATEs auf `trends` (neue Tabellen/additive Spalten), alles hinter
Schaltern mit Rückweg auf den heutigen Pfad, jede Phase mit Messgate, Merges nach `main` einzeln
vorgelegt, keine 5080 ohne Owner-Wort.

## Phase 0 — Entscheidungsdaten (Owner, parallel)
1. **Google Search Console** für catandary.de einrichten (Owner-Konto). Nach 2–3 Wochen:
   Impressionen/Klicks je Seitentyp (Artikel, Listing, Mega-Themen, Methodik). Entscheidet, wie viel
   Gewicht Einzelartikel-Seiten für die Suche wirklich haben.
2. **Anwalt:** Titel + maschinell übersetzter Titel + Link ohne Auszug (Presseverleger-LSR §87f ff.
   UrhG); Kennzeichnung bei Mehrquellen-Synthese (AI Act Art. 50 Abs. 4).
3. **Owner-Entscheid:** wie viel des Messblocks öffentlich ist (Vorschlag: eine Kennzahl offen,
   Rest hinter dem Field-Watch-Gate).

## Phase 1 — Ereignis-Erkennung im Nachtlauf (nichts Öffentliches ändert sich)
- `pipeline/story_events.py`: Gruppierung wie gemessen (Kosinus ≥ 0,80 auf `embedding_1024` bzw.
  Präfix von `raw_entries.embedding_blob`, 48 h, Union-Find, Ereignis = ≥ 2 Hosts) über **alle
  Presse-Einträge** inkl. Dedup-Verworfener, nicht nur Veröffentlichte. Verkettungsbremse: Gruppe
  > 25 Einträge → zweiter Durchgang mit 0,85.
- Tabellen `story_events` (id, first_seen, last_seen, lead_entry, n_hosts, n_entries, label) und
  `story_members` (event_id, raw_entry_id, trend_id NULL, host, sim) — additiv, in `init_db`.
- Läuft nach Stufe 5 im Cycle (CPU, Sekunden); ersetzt mittelfristig `group_stories.py` (#109,
  Markenschlüssel). „Also reported by" liest die neue Tabelle.
- **Gate (2 Wochen Beobachtung):** ≥ 90 % saubere Ereignisse in einer Handprobe von 50; Stabilität
  (Ereignis wächst über Tage, keine Zerfaserung); Ereignisse/Tag.

## Phase 2 — Messkontext als Dienst (deterministisch, kein Modelltext)
- `pipeline/context_block.py`, Ausgabe JSON aus nur berechneten Fakten mit Links:
  1. **Vektornähe je Ebene** über den Domain-Dienst (:8093 hält 2,1 Mio. Vektoren im Speicher; neuer
     Endpunkt `/context`): Primärbestände (Preprints/OpenAlex/Journale, Patente, Förderregister),
     ebenen-zentriert, Schwellen 0,55 / 0,52 / 0,55 (Eichung 10.10., je Vertikale nachprüfen).
  2. **Phrasensuche** im ganzen Bestand (`corpus_api.term_counts`: `research_corpus` 47,7 Mio.,
     `patent_search`), Jahreszählung → „im Korpus seit …“, Wachstum 3 Jahre. Dafür ein neues
     Extraktionsfeld `technology_terms` (≤ 3, wörtlich gegen die Quelle geprüft wie `quotes`).
  3. **Nest-Zugehörigkeit** (Regel des Archiv-Scans) mit Alter/Momentum des Nests.
- Mindestregel: ein Block erscheint nur, wenn ≥ 1 Fakt die Schwelle hält — sonst gar keiner.
- **Gate:** Abdeckung je Vertikale gemessen (Ziel: Phrasensuche hebt die 21 % deutlich); Handprobe
  50 Blöcke ≥ 90 % „passt inhaltlich".

## Phase 3 — Story-Artikel (Stufe 6b, zuerst im Schattenbetrieb)
- Auswahl: Ereignisse mit ≥ 2 Hosts (~76/Tag) + Einzelmeldungen mit Kontextblock (Menge aus Phase 2).
- Prompt: 2–5 Quellen (je Quelle Anfang wie heute `STAGE6_SOURCE_MAX_CHARS`, plus Extraktion), jede
  Aussage mit Quellenzuordnung, Zahlen nur aus Quellen; 150–250 Wörter Synthese. Der **Messblock wird
  unter dem Text gerendert**, nicht vom Modell geschrieben.
- Gates: Garbage → Truncation → Belegprüfung gegen die **Vereinigung** der Quellen (+ Datumsregel vom
  10.10.) → Namen → Richter mit Mehrquellen-Prompt → Review-Agent. Neues
  `ARTICLE_DISCLOSURE_STORY_EN` („… from the N sources linked below …"), JSON-LD `isBasedOn` als Liste.
- Speicherung: `trends` mit additiver Spalte `kind` ('article'|'story'|'card'), Quellen in
  `story_members`.
- **Schattenbetrieb 1 Woche** (`STORY_ARTICLES=shadow`: erzeugen, nicht veröffentlichen): Haltequote
  der Gates/des Richters, Handprobe 30 gegen 30 heutige Artikel desselben Ereignisses, GPU-Minuten.

## Phase 4 — Signalkarten im Feed + Themenseiten
- Jede relevante Meldung, die weder Story noch Kontext-Einzelartikel ist → Karte (`kind='card'`):
  Titelübersetzung im 8B-Pfad (kurz, Batch), Kontextzeile aus Phase 2 falls vorhanden; Stufe 6 entfällt.
- Frontend: Kartenkomponente im Feed, Link direkt zur Quelle, **keine eigene Seite** (keine dünnen
  Seiten im Index); Story-Artikel behalten `/trends/<slug>`. `index.json`/Suche enthalten Karten.
- Themenseiten (Mega-Themen, Nester) als SEO-Einheit: Karten + Messreihe; Export und Sitemap
  entsprechend.
- Schnitt per Datum: Bestandsartikel bleiben unverändert (kein UPDATE), neue Meldungen laufen nach dem
  neuen Schema.

## Phase 5 — Umschalten, beobachten, Rückweg
- Schalter `ARTICLE_MODE=legacy|story` (Default bis zum Owner-Go `legacy`); `legacy` bleibt lauffähig.
- Beobachtung 4 Wochen: Search Console je Seitentyp, GPU-Minuten der Nacht, Haltequoten, Leserrückmeldung.
- Rückbau des alten Einzelartikel-Pfads erst nach Owner-Entscheid.

## Aufwand und Reihenfolge (grob)
| Phase | Bau | Beobachtung | abhängig von |
|---|---|---|---|
| 0 | Owner | 2–3 Wochen | — |
| 1 | 1–2 Tage | 2 Wochen | — |
| 2 | 2–3 Tage | 1 Woche | 1 (für Ereignis-Kontext) |
| 3 | 3–4 Tage | 1 Woche Schatten | 1, 2, Anwalt (Kennzeichnung) |
| 4 | 3 Tage | — | 0 (SEO, Titel-Recht), 3 |
| 5 | Schalter | 4 Wochen | 4 |

~2–3 Wochen Bau, ~6 Wochen Kalenderzeit. Erwartete Nacht-GPU: statt ~1.060 Einzelgenerierungen
~76–250 längere Synthesen + Titelübersetzungen auf dem 8B.
