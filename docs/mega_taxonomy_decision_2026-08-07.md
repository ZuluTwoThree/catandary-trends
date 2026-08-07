# Taxonomie-Entscheidungsvorlage: neue Keys & Umzuordnungen (2026-08-07)

Grundlage: `docs/mega_discovery_findings_2026-08-07.md` (kalibrierte Läufe auf dem
1,13M-Korpus). Namensvorschläge: **lokal von Gemma-4-26B** generiert
(llama-server :8090, `data/discovery/new_key_labels.yaml`) — der Anthropic-Pfad
ist ohne Guthaben; `--label-backend local` ist seit heute der Default.

**Status: VORSCHLAG — Owner kuratiert. `mega_trends.yaml` unangetastet.**

## A · Kandidaten für NEUE Keys (kein bestehender Key passt)

| # | Vorschlag (EN / DE) | Evidenz (Sub-Thema, Stichproben-n) | Herkunft | Tiers | Lead |
|---|---|---|---|---|---|
| A1 | Quantum Information Science / Quanteninformatik | Quantum Computing · Scientific Research, n=3.649 | AI-Attraktor | 4 | funding→market −41 Mo |
| A2 | Next-Generation Semiconductor Architectures / Halbleiter-Architekturen der nächsten Generation | Chip Design · Semiconductor, n=3.177 | AI-Attraktor | 4 | science→market 140 Mo |
| A3 | Orbital Economy Expansion / Ausbau der Orbitalwirtschaft | Space Exploration, n=5.681 — ⚠️ Cluster gemischt (Rep-Titel teils Airline/UX), vor Aufnahme enger schneiden | AI-Attraktor | 3 | funding→market −77 Mo |
| A4 | Evolution of Work Models / Wandel der Arbeitsmodelle | Workplace Culture · Remote Work, n=4.278 | Catch-all `inclusive_…` | 3 | science→market 86 Mo |
| A5 | Education & Lifelong Learning / Bildung & lebenslanges Lernen *(Gemma-Vorschlag „Human Capital Development" ist zu sperrig — einfacherer Name empfohlen)* | Gender Equality · Education, n=4.603 + global EMERGING „STEM Education" n=203 | Catch-all + global | 3 | science→market 144 Mo |
| A6 | Digital Healthcare Integration / Digitale Gesundheitsintegration | Digital Health · Health Tech, n=4.229 | PH-Attraktor | 4 | science→market 56 Mo |

## B · Umzuordnung auf BESTEHENDE, leer laufende Keys (keine Taxonomie-Änderung)

| Sub-Thema (n in Stichprobe) | sitzt heute in | gehört zu |
|---|---|---|
| Electric Vehicles · Renewables (7.897) | clean_energy_transition | `electric_and_autonomous_mobility` (22,7k) |
| Neuroscience (5.706 + 5.288) | personalized_health / AI | `mental_health_and_neuro_wellness` (44,2k) |
| Climate Change · Climate Policy (5.393) | clean_energy_transition | `climate_resilience_and_adaptation` (47,6k) |
| Social Media · Content Creation (5.426 + 395 global) | Catch-all `inclusive_…` | `creator_economy_and_platform_shift` (5,1k) bzw. `platformization_of_culture` (0!) |
| Urban Design · Sustainable Design (4.822) | Catch-all `inclusive_…` | `connected_living_and_smart_spaces` (5,8k) *oder* `regenerative_design_and_net_positive` — Owner-Entscheid |
| Brand Strategy · Beauty (4.170) | Catch-all `inclusive_…` | `new_luxury_and_premiumization` (14,5k) |
| Travel · Post-Pandemic Recovery (3.722) | Catch-all `inclusive_…` | `experience_economy_and_immersive_design` (4,6k) |
| Music Industry · Streaming (3.281) | financial_innovation | `platformization_of_culture` (0) |
| Perovskite · Material Science (2.811 + 362 global) | clean_energy_transition | `bio_revolution_and_new_materials` (19,4k) |

## C · Bewusst KEINE Empfehlung

| Sub-Thema | Warum kein Key |
|---|---|
| Healthcare Policy · Research Funding (3.954) | Politik-/Förderdimension, kein Mega-Trend — gehört in PESTEL **P**, thematisch zum jeweiligen Fach-Key |
| Wireless · 5G · Network Optimization (6.515) | Infrastruktur-Grundrauschen; falls doch, eher zu `connected_living_and_smart_spaces` |
| Kerne der vier Attraktoren (Drug Discovery, Deep Learning, VC/Fintech, Solar/Storage …) | bleiben unter ihren heutigen Keys — die Attraktoren werden schlanker, nicht aufgelöst |

## Nach dem Owner-Entscheid (Reihenfolge fix)

1. `mega_trends.yaml` um die freigegebenen A-Keys erweitern (Format: key, name_en/de, description, horizon, icon)
2. **Seed-Labels** je neuem/aktiviertem Key aus den Discovery-Cluster-Zuordnungen ziehen (die Läufe liefern die `rep_ids`/Cluster-Mitgliedschaft)
3. Distill-Head-Retrain mit `classes` = finale Key-Zahl (löst zugleich den #40-Zirkel: `platformization_of_culture` ist heute untrainierbar, weil 0 Teacher-Labels existieren)
4. Reclassify der Attraktor-Bestände (Dry-Run → Messung → Live), Erfolgsmaß: Anteil der vier Attraktoren < 50 % des Korpus, ausgehungerte Keys > 0
5. CLAUDE.md-Zahlen nachziehen (22 → n Keys, „21 kanonische" ist bereits stale)
