# OpenAlex-Vollakquise — Plan (Science-Signal)

Analog zum **BDDS-Backfill** der Patente (EPO-Bulk), aber: OpenAlex wird **über die
REST-API** akquiriert, nicht über den Bulk-Snapshot. Ergebnis ist das eigenständige
**„Science"-Signal** (research→preprint) neben dem Patent-**„Technology"-Signal** —
mit vollem **Graph-Layer** (Topics + Citations), sodass die dichten TIR-Metriken
greifen.

## BDDS ↔ OpenAlex — die Analogie

| BDDS / Patente | OpenAlex |
|---|---|
| EPO-Bulk (Produkt 3 Front / 14 Back-File) | **REST-API** `/works` (kein Bulk-Pull; Snapshot bewusst nicht genutzt) |
| OAuth password grant | `api_key` / Polite-Pool (`mailto=`) — `OPENALEX_API_KEY` in `.env` |
| CPC-Scoping (Haystack-Reduktion) | **Topic-Scoping** (`primary_topic.id` / `topics.id`) |
| `vertical_for_cpc` | `vertical_for_topic` (Topic-Subfield → Vertical, deterministisch) |
| `pub_number` (Knoten-Key) | OpenAlex Work-ID (`Wxxxx…`) |
| `patent_links` (cites/family) | `openalex_citations` (`referenced_works` → Edges) |
| `patent_cpc` | `openalex_topics` |
| kind_code (A=App=früh) | `type=preprint` (früheste Stufe) |
| forward via Invertierung | `cited_by_count` + `counts_by_year` (**nativ**) |
| Front-File / Back-File | **Front-Fill** (`from_publication_date`) / **Back-Fill** (volles Datumsfenster je Topic) |

## Warum API statt Snapshot

Der OpenAlex-Snapshot (~400 GB, S3) ist ein eigener Infra-Brocken (Download +
Entpacken + Parsen der `works/*.gz`). Die REST-API deckt unsere **gescopte** Menge
(Vertical-Topics, Datumsfenster) im **bestehenden Nutzungsplan** ab: Polite-Pool ist
gratis, `select=` trimmt die Payload, `cursor` paginiert beliebig tief. Für unsere
Topic-Teilmenge ist das schneller produktiv als der Voll-Snapshot.

## API-Mechanik

- **Endpoint:** `GET /works?filter=<…>&select=<…>&per-page=200&cursor=*`
- **Auth/Politeness:** `api_key=` (haben wir) oder `mailto=` → Polite-Pool. Limits ~**10 req/s, 100k req/Tag**; bei `per-page=200` theoretisch ~20M Works/Tag → politely pacen (Backoff bei 429, nächtlich verteilen).
- **`select=`** nur die Foresight-Felder → kleine Payloads:
  `id,title,abstract_inverted_index,publication_date,type,primary_topic,topics,referenced_works,cited_by_count,counts_by_year,grants,is_retracted,language`
- **`cursor=*`** statt `page` (Pflicht jenseits 10k Treffer).
- **`group_by`-Bonus:** `/works?filter=…&group_by=publication_year` liefert **Volumen pro Jahr pro Topic ohne die Works zu ziehen** → das Trajektorien-/SoV-Volumensignal quasi gratis (für die Frühphase, vor dem Voll-Ingest).

## Scoping (Haystack-Reduktion)

1. **Topic→Vertical-Map** bauen: OpenAlex hat 4 Domains → 26 Fields → ~252 Subfields → ~4.500 Topics. Mapping auf der **Subfield-Ebene** (handhabbar, ~252 Einträge) → 8 Verticals. Off-scope Subfields = kein Pull.
2. **Filter je Vertical:** `filter=primary_topic.subfield.id:<…>,from_publication_date:<…>,to_publication_date:<…>`.
3. **Typ:** alles (article/review/**preprint**) — `type` wird gespeichert, nicht gefiltert (preprint = Frühsignal).

## Zwei Phasen (Front-File/Back-File-Analog)

- **Front-Fill (laufend):** `from_publication_date=<letzter Lauf>` je Vertical → neue Works. Billig, täglich/wöchentlich (Cron, wie der RSS-Poller).
- **Back-Fill (historisch, einmalig tief):** volles Fenster (z. B. **2010+**) je gescoptem Subfield, über die API-Tagesbudgets verteilt. Das ist das „Produkt-14"-Äquivalent.

## Storage (Graph-Layer)

- **`raw_entries`:** Knoten-Key = Work-ID. *Empfehlung:* das bestehende Knoten-Key-Feld generisch wiederverwenden (`pub_number` ist nur ein externer ID-String) **oder** `openalex_id`-Spalte ergänzen. `title` + aus `abstract_inverted_index` **rekonstruierter** Abstract; `source_type='science'`, `trend_signal_type='research'`.
- **`openalex_citations(src_work, dst_work, link_type='cites', UNIQUE(src,dst))`** — aus `referenced_works` (gleiches Muster + `INSERT OR IGNORE`/`ON CONFLICT` wie `patent_links`).
- **`openalex_topics(work_id, topic_id, subfield, field, domain, score, is_primary)`** — wie `patent_cpc`, denormalisiert für den Domain-Rollup.
- **`cited_by_count` + `counts_by_year`** (kleine JSON-Spalte oder `openalex_citations_by_year`) für die Velocity.
- **Dedup:** OpenAlex ist bereits dedupliziert; Work-ID/DOI unique → URL-Dedup in `insert_raw_entry`.

## Quantitative Indikatoren — auf „Science" abgestimmt

`tir_graph`-Logik wiederverwenden, aber:
- **Feld-Normierung (Pflicht):** Zitationsraten variieren ~10× zwischen Feldern → `cited_by_percentile_year` nutzen **oder** innerhalb Topic-Subfield normalisieren. (Patente brauchten das kaum.)
- **Zitationsfenster** feldabhängig (~2 J statt 3) für „Immediate Importance".
- **Acceleration** = Slope von `counts_by_year` → der Emerging-Front-Marker.
- **Zitations-Lag:** frische Works zitatarm → für *aktuelle* Trends ist **Topic-Volumen/-Wachstum** (via `group_by`) das Frühsignal; Zitate bestätigen ältere.
- **Co-Citation / Bibliographic-Coupling-Cluster** = Research Fronts (Science-spezifisch, zusätzlich zu den Embedding-Clustern).
- **`is_retracted`** = Negativsignal (analog patent „lapsed").

## Volumen & Pacing

Gescopt auf unsere Vertical-Subfields, 2010+: grobe Größenordnung **~10–30 Mio. Works** (von 250M). Über den Polite-Pool in Tagesbudgets → Tage–Wochen Back-Fill, danach billiger Front-Fill. `referenced_works` (~30–40 Refs/Work) erzeugt einen großen, aber auflösbaren Edge-Graph → **triggert (wie der Patent-Back-File) die Postgres+pgvector-Migration**.

## Phasen-Reihenfolge

```
1. Topic→Vertical-Map (Subfield-Ebene)            (Code, GPU-frei)
2. ingest_openalex erweitern: Graph-Layer          (raw_entries + openalex_citations + openalex_topics + counts_by_year)
   — select=, cursor, Polite-Pool, Abstract-Reconstruct, Topic→Vertical
3. group_by-Volumen-Probe je Vertical/Jahr         (Scope/Volumen verifizieren, fast gratis)
4. Back-Fill gescopt (2010+), API-Budget-paced     (Science-Korpus)   → Postgres-Migration
5. tir_graph für Science (feld-normiert)           (dichte Forward-Metriken!)
6. Front-Fill als Cron                             (laufend)
7. Cross-Tier-Fusion Science↔Technology↔Funding    (Lead-Time-Kette messbar)
```

## Offene Entscheidung

**Back-Fill-Scope:** welche Vertical-Subfields + Datumsfenster zuerst. Empfehlung
(analog Patent-Back-File): die hochwertigen Tiers **TECH/HEALTH/ECO**-Subfields,
Fenster **2018+** zuerst (Überlapp mit Patenten/Trade-Media → stabile Kohorte für
SoV/Cross-Tier), dann tiefer + breiter.
