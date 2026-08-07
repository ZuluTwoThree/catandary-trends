# Mega-Discovery auf dem 1,13M-Korpus — Befunde (2026-08-07)

**Läufe:** `scripts/discover_trends.py` mit dem kalibrierten Sampler und den
kalibrierten Cluster-Parametern (`docs/mega_discovery_calibration.md`).
Read-only; `mega_trends.yaml` wurde nicht angefasst.
Roh-Logs: `data/discovery/` (A_legacy, B_tier_capped, C_calibrated, D_mega_splits).

## Ausgangslage

| | |
|---|---|
| Trends gesamt | 1.134.488 (alle embedded) |
| Kanonische Mega-Trends | 22 (`mega_trends.yaml`) |
| Klassen im Distill-Head | **21** (`models/distill/meta.json`, 2026-07-26) |
| Ohne Mega-Trend | 7.395 (0,7 %) |

Tier-Verteilung: market 643.921 · science 234.474 · api/funding 195.624 · patent 60.469.
Quellenkonzentration: NIH RePORTER 13,1 % · TechCrunch 11,5 % (243 Quellen gesamt).

## Befund 1 — die Schieflage ist Korpus-Komposition, nicht Taxonomie

`personalized_health_and_longevity` hält 329.827 Signale (29 %), davon **153.649 aus
dem Funding-Tier** (NIH RePORTER) und 95.021 aus science. Im reinen Markt-Blick
rangiert es auf Platz 4 (68.239) hinter `financial_innovation` (119.796),
`clean_energy` (96.279) und `AI` (84.072). Der Science-/Grant-Backfill hat
Biomedizin hereingespült — jede Analyse auf dem rohen Korpus misst das mit.

Konsequenz für den Discoverer: Der Draw ist jetzt tier-balanciert und deckelt jede
Quelle bei 5 % der Stichprobe. Ohne das findet Dichte-Clustering den Hausstil von
NIH RePORTER und TechCrunch und nennt ihn „Thema".

## Befund 2 — die Taxonomie hat **kein Lückenproblem**

Der kalibrierte globale Lauf (50k, tier-balanciert, ARI 0,77, 11 Themen) liefert:

- **0 NEW** — kein dichter Kern im Korpus, den die 22 Kanonischen nicht abdecken
- **4 SPLIT** — und zwar exakt die vier größten Labels
- **18 von 22 Kanonischen sind in keinem Thema dominant**

Das ist kein Coverage-Problem. Es ist das Gegenteil: **vier Labels ziehen 65 % des
Korpus an sich, während 18 Labels aushungern.**

| Kanonisch | Signale | |
|---|---:|---|
| personalized_health_and_longevity | 329.827 | SPLIT-Kandidat |
| artificial_intelligence_and_automation | 155.961 | SPLIT-Kandidat |
| financial_innovation_and_inclusion | 134.941 | SPLIT-Kandidat |
| clean_energy_transition | 123.152 | SPLIT-Kandidat |
| … | | |
| creator_economy_and_platform_shift | 5.100 | ausgehungert |
| cultural_heritage_and_identity | 1.865 | ausgehungert |
| virtual_worlds_consolidation | 579 | ausgehungert |
| **platformization_of_culture** | **0** | Head kennt die Klasse nicht (#40) |

## Befund 3 — was in den vier Attraktoren steckt

Clustering **innerhalb** jedes Labels (`--layer scope --mega <key>`, k=8,
tier-balancierter 33–37k-Draw). Die Sub-Themen sind nicht Facetten *eines* Trends,
sondern eigenständige Mega-Trends — teils solche, **für die bereits ein eigener
kanonischer Key existiert, der aber leer läuft**:

**personalized_health_and_longevity** = die gesamte Biomedizin
→ Clinical Research/ML · Neuroscience · Digital Health · Pharma/Biotech ·
Medical Devices · Drug Discovery · Precision Medicine · Public Health/Vaccines
*(Neuroscience-Cluster n=5.706 — während `mental_health_and_neuro_wellness` als
eigener Key existiert.)*

**artificial_intelligence_and_automation** = die gesamte Tech-F&E
→ Wireless/Network Optimization · Space Exploration · Neuroscience/ML · AI Ethics ·
Deep Learning · **Quantum Computing** · **Chip Design/Semiconductor** · AI Research
*(Quantum und Halbleiter sind in jeder gängigen Taxonomie eigene Mega-Trends.)*

**financial_innovation_and_inclusion** = alles, was mit Geld zu tun hat
→ Business Strategy · VC/Impact Investing · Algorithmic Trading ·
**Healthcare Policy/Research Funding** · Economic Policy · **Music Industry/Streaming** ·
Fintech · IPO
*(Das Label greift auf die **Form** des Signals — Finanzierungsrunde, Deal —
statt auf sein Thema. Musik-Streaming und Gesundheitspolitik landen hier.)*

**clean_energy_transition** = Energie + Klima + Materialien + Mobilität
→ **Electric Vehicles/Renewables (n=7.897)** · Carbon Capture · Climate Policy ·
Energy Efficiency/ML · Smart Grid · Solar · **Perovskite/Material Science** ·
Battery/Storage
*(`electric_and_autonomous_mobility` (22.725), `climate_resilience_and_adaptation`,
`bio_revolution_and_new_materials` und `circular_economy_and_zero_waste` existieren
als eigene Keys — ihre Signale sitzen teilweise hier.)*

**inclusive_and_human_centric_design** (37.518, der LIFESTYLE-Catch-all) ist gar kein
Mega-Trend, sondern eine Sammelschublade
→ Social Justice · **Social Media/Content Creation (n=5.426)** · Urban Design ·
Product Design · Gender Equality/Education · Workplace Culture/Remote Work ·
Brand Strategy/Beauty · Travel Industry
*(Genau das Material, für das `platformization_of_culture` und
`creator_economy_and_platform_shift` gedacht sind — beide laufen leer.)*

## Was daraus folgt

Der ursprüngliche #40-Plan („neue Keys kuratieren → Head retrainieren → reclassify")
zielt auf ein Problem, das die Daten nicht zeigen. Die Reihenfolge muss sich drehen:

1. **Nicht neue Keys erfinden** — 0 NEW über 1,13M Signale ist ein klares Ergebnis.
2. **Die vier Attraktoren aufteilen** und die 18 leer laufenden Keys *aktivieren*.
   Ein Teil der Arbeit ist reine Zuordnung, keine Taxonomie-Änderung: die EV-,
   Neuro-, Material- und Creator-Signale haben schon einen passenden Key.
3. **Die Ursache liegt im Klassifikator, nicht in der Liste.** Der Distill-Head
   lernt aus `trends.mega_trend`-Teacher-Labels — also aus genau dieser Kollaps-
   Struktur. Ein Retrain auf dem Ist-Bestand reproduziert sie. Vor dem Retrain
   braucht es eine Zuordnungslogik, die die feinen Keys erreichbar macht
   (z. B. kuratierte Seed-Mengen je Key statt gelerntem Prior).

**Owner-Gate:** Punkt 2 ist eine Kuratier-Entscheidung (welche Sub-Themen werden
eigene Keys, welche gehen auf bestehende Keys), Punkt 3 hängt davon ab.
