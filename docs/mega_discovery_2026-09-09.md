# Bottom-up-Entdeckung im Signalraum — zwei Läufe, 2026-09-09

Anlass: Owner-Frage „Sind die Embeddings für eine Trendanalyse ausreichend? Werden Funde in den
Embeddings z. B. bei den Dossiers oder beim Megatrend-Discoverer inhaltlich berücksichtigt?"

Werkzeug: `scripts/propose_mega_trends.py` (read-only, fasst `mega_trends.yaml` nie an). Der alte
SQLite-Prototyp `discover_mega_trends.py` wurde am selben Tag entfernt — er zeigte auf die
vor-Postgres-Datei `data/catandary.db` und war durch dieses Werkzeug abgelöst.

## Ergebnis in einem Satz

Das Verfahren läuft, aber sein Ergebnis ist überwiegend eine **Diagnose des Vektorraums**, keine
Trendentdeckung. Belastbar ist nur, was in beiden Läufen reproduziert: vier zu breite Mega-Trends
und rund siebzehn kanonische Themen ohne messbaren Fußabdruck.

## Lauf 1 — ganzer Signalpool

`--limit 60000 --no-label`, k-Suche 16…30.

| | |
|---|---|
| Silhouette über k | **0,011 – 0,021** (gewählt k=28 bei 0,021) |
| Kohäsion | 15 von 28 Clustern „weak" (0,29–0,45) |
| Verdikte | NEW 2, MERGE 4, MIXED 3, NOISE 4, COVERED 15 |

**Beide NEW-Vorschläge waren Artefakte.** Ihre Beispielsätze:

- Cluster 22 (3.116 Signale, Momentum −43,7pp): *„CFD RESEARCH CORPORATION wins $600k SBIR Phase II award"*
- Cluster 19 (1.459 Signale): *„HOLONIX SRL secures EUR 620k Horizon 2020 grant"*

Das sind Förderbescheide. Eingebettet wird `title + excerpt[:500]` — bei formelhaften Meldungen
dominiert die **Satzform** das Thema, und der Clusterer findet Vorlagen. Gemessene Ursache:
**35.748 der 60.000 gezogenen Signale (60 %) waren `source_type='api'`** (Funding, Patente).

## Lauf 2 — ohne Funding und Patente

Nach dem Einbau von `--exclude-source-types` (Default `api`), gleiche Parameter.

| | |
|---|---|
| Silhouette über k | **0,014 – 0,025** (gewählt k=19 bei 0,025) |
| Kohäsion | beide NEW-Cluster weiterhin „weak" (0,36 / 0,34) |
| Verdikte | NEW 2, MERGE 2, MIXED 3, NOISE 3, COVERED 9 |

Die NEW-Vorschläge sind jetzt **echte Themen** statt Formularsätze:

- Cluster 10 (2.934 Signale): Quantenoptik/Photonik — *„Quantum electrodynamics near a photonic
  bandgap"*; dominantes bestehendes Label `quantum_information_science` mit nur 34 %.
- Cluster 3 (2.513 Signale): Arbeitsorganisation — *„High commitment HR practices, the employment
  relationship and job performance"*; dominantes Label `artificial_intelligence_and_automation` mit
  23 %, während der passende Key `evolution_of_work_models` in **keinem** Cluster dominiert.

Beide bleiben aber schwach kohärent und haben bereits ein kanonisches Label in der Nähe — als „neuer
Mega-Trend" taugt keiner von beiden. Ihr Wert liegt woanders: sie zeigen zwei Stellen, an denen ein
vorhandener Key seinen eigenen Cluster nicht gewinnt.

## Was in beiden Läufen reproduziert (= der verwertbare Teil)

**Zu breite Mega-Trends (SPLIT).** Stabil über verschiedene k und verschiedene Pools:

| Mega-Trend | Lauf 1 | Lauf 2 |
|---|---|---|
| `personalized_health_and_longevity` | 6 Cluster | 3 Cluster |
| `artificial_intelligence_and_automation` | 4 Cluster | 3 Cluster |
| `future_of_food_and_agriculture` | 2 Cluster | 2 Cluster |
| `financial_innovation_and_inclusion` | 2 Cluster | 2 Cluster |

**Kanonische Themen ohne Fußabdruck.** 16 (Lauf 1) bzw. 17 (Lauf 2) der 28 Keys dominieren in keinem
einzigen Cluster — darunter **alle sechs Keys der Taxonomie-Erweiterung vom 2026-08-07**
(Semiconductors, Orbital Economy, Work Models, Education, Quantum, Digital Healthcare) sowie
Circular Economy, Creator Economy, Mental Health, Wearables, Virtual Worlds, New Luxury.
Entweder sind sie für diese Stichprobengröße zu klein — oder die Taxonomie ist an diesen Stellen
gewünscht statt gemessen. Das ist eine redaktionelle Frage, keine technische.

## Zwei Befunde am Werkzeugbestand

1. **Signal-Zeilen tragen praktisch keine Tags: 214 von 50.000 (0,4 %)**, gegenüber 82 % bei
   `published`. Der Distill-Pfad erzeugt keine. Deshalb sind alle `tags:`-Zeilen der Berichte leer
   und die Namensableitung liefert „[REVIEW] Cluster 22". Mit `--label-backend local` benennt ein
   Modell die Cluster; ohne LLM ist die Ausgabe unbenannt.
2. **Die Silhouette bleibt bei ~0,02.** Zur Einordnung: > 0,5 heißt deutliche Trennung, < 0,1 heißt
   „die Punkte liegen zwischen den Clustern". Auf einem Vektor aus Überschrift plus Anriss
   (Median 588 Zeichen) gibt es auf Mega-Trend-Höhe schlicht keine Struktur, die ein Clusterer
   sauber schneiden könnte. Das ist der eigentliche Befund — und das Argument für Issue #102
   (getrennte Volltext-Embeddings).

## Reproduktion

```bash
python scripts/propose_mega_trends.py --limit 60000 --no-label --out mega_trends.candidate.yaml
python scripts/propose_mega_trends.py --limit 60000 --exclude-source-types "" --no-label   # Lauf 1
```

Laufzeit je Lauf ~8 min (60.000 × 4096, k-Suche über 15 Werte), Speicher ~6 GB. Die Kandidatendateien
der beiden Läufe liegen im Scratchpad, nicht im Repo — sie sind Momentaufnahmen, keine Artefakte.
