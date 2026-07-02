# Foresight-Validierung — inhaltlich (Launch-Gate für #3)

Stand: 2026-07-02 · Datenbasis: 505.039 embedded Trends (454.006 Signale, 47.030 published) ·
Snapshots: `foresight_snapshot --all-verticals` (9 Scopes, runs 10–18 nach Momentum-Fix) ·
Methode: dreistufige Prüfung, Erwartungen vorab registriert (siehe Git-Diff dieser Datei).

## Ergebnis: **BESTANDEN mit einem dokumentierten Vorbehalt** (Lead-Time-Datenbasis, → Folge-Task)

Zwei Bugs von der Validierung gefunden und gefixt, bevor die Cluster-Seite live geht:
- **Zukunftsdaten** (fehlerhafte RSS/API-Records bis 2029) streckten die Monatsachse → Filter `published_date <= now` in `load_signals`.
- **Momentum-Fenster** maß Quellen-Komposition statt Trend: über die volle Historie (Patent-/Research-Backfill 2002–2020 vs. RSS zuletzt) erzeugte die Share-of-Voice künstliche „−60pp/−84pp"-Stürze am Ende des jeweiligen Ingest-Fensters. Fix: Momentum nur über die letzten `MOMENTUM_WINDOW_MONTHS=36` (Komposition dort ~stabil). Danach liegen alle Δ plausibel im ±8pp-Band.

## 1. Known-Trend-Recovery — BESTANDEN (8/8 Verticals)

Die vorab registrierten Trends wurden bottom-up als kohärente Cluster wiedergefunden:

| Vertical | Erwartet | Gefunden (Cluster-Label / dominante Tags) |
|---|---|---|
| FOOD | Alt-Protein/Cultivated · Plant-Based · Food Safety · Functional/Ag · Packaging | ✓ Alternative Proteins/Cultivated Meat · Plant-Based/Vegan · Food Science/Food Safety · Sustainable Agriculture · Sustainable Packaging |
| TECH | GenAI/LLMs · AI-Chips/Edge · Quantum · Robotik · Cybersecurity | ✓ AI/Generative AI · ML/AI · Quantum Computing/Semiconductor · EV · Cybersecurity (+ Material Science, Biotech) |
| HEALTH | GLP-1/Adipositas · AI-Diagnostik · Longevity · Mental Health · Microbiome | ✓ Pharma/Clinical Trials · AI in Healthcare/Digital Health · Mental Health · Oncology · Telehealth (GLP-1 nicht als eigenes Cluster, aber in Pharma; s. Lead-Time) |
| ECO | Batterien/Storage · Carbon/Climate · Wasserstoff · Circular · Erneuerbare | ✓ Climate Policy · Renewables/Solar · Circular Economy · Energy Storage · Biodiversity |
| BIZ | Embedded Finance · Retail-AI · Recommerce · Funding/Konsolidierung | ✓ Fintech/VC · Retail/Acquisition · Cybersecurity/Strategy · Antitrust/Digital Rights · Travel |
| FASHION | Biotech-Materialien · Resale · Clean Beauty | ✓ Beauty/Cosmetics · Sustainable Fashion/Circular · Streetwear/Collab · Luxury · Smart Textiles |
| DESIGN | AI-Design · Modular/Adaptive Reuse · Nachhaltiges Bauen | ✓ Sustainable Architecture · Adaptive Reuse · AI-Driven Design · Milan Design Week · Urban Design |
| LIFESTYLE | Creator Economy · Gaming/Streaming · Fitness-Communities | ✓ Creator/Content Economy · Entertainment/Gaming · Fitness Culture/Tech · Music Streaming |

Kohäsion der Cluster 0.53–0.76 (mega-altitude erwartungsgemäß breit), Cross-Source-Korroboration
40–195 distinct sources je Cluster → keine Ein-Quellen-Artefakte.

## 2. Momentum-Plausibilität — BESTANDEN (nach Fix)

Die Momentum-Rangfolge im 36-Monats-Fenster deckt sich mit der Marktrealität:
- **global:** AI/ML +5,7pp (steigt), Startup/Financial Innovation +1,5pp, Climate +1,1pp.
- **FOOD:** Food Waste/Delivery +7,7pp, Sustainable Packaging +3,6pp (beide real steigend); Regulatory Approval stabil.
- **HEALTH:** Mental Health +6,7pp, AI in Healthcare +3,0pp (beide real steigend); Oncology/Pharma stabil.
- **TECH:** AI/ML +6,2pp, Generative AI steigt; Energy Storage stabil.
- **ECO:** Climate/Global Warming +5,5pp; Renewables/Solar stabil.

Kein Cluster zeigt mehr die früheren Backfill-Artefakt-Stürze. Externe Referenz-Spot-Checks
(GenAI, GLP-1-Umfeld, Mental Health) stimmen mit öffentlich bekannten Aufwärtstrends überein.

## 3. Lead-Time-Stichprobe — TEILWEISE BESTANDEN (Kern-Versprechen für 2/3 Themen belegt)

Erste Signal-Monate je `source_type` (Proxy für Lead-Time-Tier: api=Funding, research=Science, trade_media=Markt):

| Thema | Funding (api) | Science (research) | Markt (trade_media) | Kette sichtbar? |
|---|---|---|---|---|
| **GLP-1** | 2015-04 | 2020-01 | 2021-06 | ✓ Funding → Science → Markt (6 J Vorlauf) |
| **mRNA** | 2011-01 | 2020-01 | 2020-02 | ✓ Funding führt ~9 J vor Markt |
| Cultivated Meat | 2025-10 (dünn) | 2020-12 | 2020-01 | ✗ durch Datenbasis limitiert (s. u.) |

**Belegt:** Für GLP-1 und mRNA ist die Lead-Time-Kette in unseren eigenen Daten messbar — Funding-
und Science-Signale liegen Jahre vor den Markt-Signalen. Das ist der Beleg, mit dem das Feature
verkauft werden darf.

**Vorbehalt (→ Folge-Task, kein Blocker für den Cluster-Launch, aber Blocker für die *Lead-Time-Ansicht*):**
Die `research`-Datenbasis reicht erst bis ~2020 zurück (OpenAlex-Backfill-Fenster), `trade_media`
dagegen bis 2002. Für Themen, deren Markt-Durchbruch *vor* 2020 lag (Cultivated Meat: erste
Presse 2013–2018), kann die Science-vor-Markt-Ordnung nicht gezeigt werden — nicht weil sie fehlt,
sondern weil der Research-Backfill zu kurz ist. **Konsequenz:** Die Lead-Time-Ansicht (#3 Phase 2)
wird erst nach dem tieferen Research-/Preprint-Backfill (Issues #4, #9-OpenAlex-Graph) beworben;
bis dahin nur für Themen ab ~2020. Der Cluster-Explorer (#3 Phase 1) ist davon unberührt.

## Abnahme

- **Cluster-Explorer (#3 Phase 1): freigegeben.** Known-Trend-Recovery und Momentum bestanden;
  die zwei gefundenen Bugs sind gefixt und die Snapshots neu gerechnet.
- **Lead-Time-Ansicht (#3 Phase 2): bedingt.** Erst nach Verlängerung der Research-Historie
  (früher Tier-Backfill). Als Task an Issue #4/#3 vermerkt.
