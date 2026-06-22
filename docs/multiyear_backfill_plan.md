# Plan: Mehrjahres-Backfill-Ingest — Datenlücken aller Verticals schließen (2020 → Juni 2026)

**Stand 2026-06-22.** Ziel: eine **durchgehende, dichte Signal-Historie** statt der
aktuellen „2024-Insel (Backfill) + dünnes RSS (2025/26)". Schließt die Lücken
**2020-01 bis 2026-06** für **alle 8 Verticals** über die entkoppelten
Acquisition-Kanäle (WP-REST / OpenAlex). Rein Beschaffung — kein LLM, keine GPU.

## Warum (Befund)

FOOD/DESIGN-Cluster-Trajektorien sind aussagekräftig, aber die Zeitachse ist eine
2024-Insel (Backfill) + 2025/26-RSS mit Loch dazwischen und vor 2024. Für echte
Trajektorien/S-Kurven/Lead-Time-Verschiebungen (= das Foresight-Produkt) braucht es
eine **lückenlose Mehrjahres-Serie**. Verfügbarkeit bestätigt (Stichprobe FOOD):
WP-Quellen liefern 600–2.500 Posts/Jahr 2020-23, OpenAlex-Journale 200–900 Works/Jahr.

## Fenster & Kanäle

- **Fenster:** `2020-01-01` … `2026-07-01`. (2024 ist schon ingestet → URL-Unique-Dedup
  überspringt die Überlappung automatisch; man kann das ganze Fenster fahren.)
- **WP-REST-API** (~44 Quellen): gratis, datiert, Volltext. Hauptlast.
- **OpenAlex** (~57 Journale): mit `OPENALEX_API_KEY` ($1/Tag-Budget — pacen).
- **Sitemap-Kanal weglassen** (schwach/undatiert, Befund Welle 0).

## Volumen & Wachstum (grob)

- 2024 ergab ~142k raw_entries. 6,5 Jahre × alle Verticals ≈ **~500k–900k roh**
  (vor Noise-Caps), getrieben von den Volumen-Giganten.
- DB-Wachstum: raw_entries einige GB; Embeddings erst bei Klassifizierung
  (16 KB/Signal). Beschaffung selbst ist billig.

## Noise-Handling (wichtig bei 6,5 Jahren)

Die Volumen-Giganten mit niedriger Pass-Rate (Variety 22 %, Hollywood Reporter 19 %,
WWD ~Fashion-Noise) **blähen den Korpus über 6,5 Jahre massiv auf** (Variety allein
~600k Posts gesamt). Optionen:
1. **Pro-Quelle-Cap beim Ingest** (z. B. max N/Monat) für die Giganten — empfohlen.
2. **Ausschluss** der reinen Noise-Quellen (Variety/HR) — schließt LIFESTYLE-Lücke
   dann über die *sauberen* LIFESTYLE-Quellen (Hypebeast 79 % etc.).
3. Alles ziehen, später filtern — verschwendet Klassifizierungs-Durchsatz.

→ `ingest_wordpress.py` um einen `--max-per-month`/`ingest_cap`-Parameter erweitern
(oder `sources.yaml`-Feld `ingest_cap`), für die in der Qualitätsanalyse als rauschig
markierten Quellen.

## OpenAlex-Budget pacen

$1/Tag mit Key. 2024-OpenAlex kostete ~$0,08 (~10k Works). 6,5 Jahre × Journale
≈ ~60–80k Works ≈ **~$0,5–0,6 gesamt** → passt, aber **pro-Tag-Limit** beachten:
über mehrere Tage verteilen oder den vorhandenen 429-Backoff (`_get`) die
Drosselung handhaben lassen. `/rate-limit` vor jedem Lauf prüfen.

## Ausführung

- **Dry-Run-Probe ÜBERSPRINGEN** (war der teure/langsame Teil in Welle 0) — direkt
  realer Ingest, URL-Unique-Dedup macht es resumierbar/idempotent.
- **Pro Vertical** ingesten (alignt mit der Pro-Vertical-Klassifizierungs-Strategie):
  ```
  python scripts/ingest_backfill.py --vertical FOOD   --after 2020-01-01 --before 2026-07-01 --only WP
  python scripts/ingest_backfill.py --vertical FOOD   --after 2020-01-01 --before 2026-07-01 --only ACADEMIC
  # … je Vertical; WP zuerst (frei), OpenAlex budget-gepaced danach
  ```
- **Optional nach Jahr chunken** (`--after 2020-01-01 --before 2021-01-01`, …) um
  Läufe zu bounden und Fortschritt sichtbar zu machen.
- **Entkoppelt:** läuft ohne GPU/LLM, blockiert weder Klassifizierung noch Normalbetrieb.

## Reihenfolge im Gesamtbild

1. **(parallel, jetzt)** Mehrjahres-Ingest anstoßen → tiefer Roh-Korpus, gratis/Cent.
2. **Schema-Trim** (Relevanz ohne `reason`) → ~2× Relevanz-Durchsatz.
3. **Voll-Lauf lokal** (`signal_batch --backend local`) **pro Vertical** über den
   vertieften Korpus → dichte Mehrjahres-Signale.
4. **Foresight-Engine** (Cluster/Trajektorien) auf der lückenlosen Serie = das Produkt.

## Verweise
- `scripts/ingest_backfill.py` (Router), `ingest_wordpress.py`, `ingest_openalex.py`
- Befund Datenlücken: `docs/a2_food_evaluation.md`, Memory `foresight-engine-is-the-product`
- Lokaler Klassifizierer: `docs/local_parallel_classification_plan.md` (validiert via DESIGN)
