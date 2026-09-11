# Volltext-Vektoren gegen Dedup-Vektoren — Messung 2026-09-11 22:44 — nur Lauf 2026-09-11 07:40..2026-09-11 08:15 (UTC)

Grundgesamtheit: **19,294** Trends mit beiden Vektoren ([('signal', 15139), ('published', 3383), ('draft', 748), ('rejected', 24)]); Anfragen: 1200 (je 600 published / uebrige), k = 10, Kosinus. Textgewinn Volltext/Anriss: Median 1.1×, Anteil ≥ 3×: 18 %.

## 1. Sehen die Raeume dasselbe? (Jaccard@10 zwischen den Nachbarlisten)
- mittlere Ueberlappung **0.41** (Median 0.43); 0 % der Anfragen haben KEINEN gemeinsamen Nachbarn
- mittlerer Kosinus zum naechsten Nachbarn: Dedup 0.659, Volltext 0.672

## 2. Satzform oder Inhalt? Anteil der Nachbarn mit …
| | Dedup-Raum | Volltext-Raum |
|---|---|---|
| derselben Quelle (Form) | 45.9 % | 47.1 % |
| demselben Mega-Trend (Inhalt) | 72.6 % | 72.1 % |
| derselben Vertikale (Inhalt) | 74.1 % | 73.9 % |
| nur `signal` (n=567): dieselbe Quelle / derselbe Mega-Trend | 79.3 % / 81.2 % | 81.2 % / 80.8 % |
| nur `published` (n=600): dieselbe Quelle / derselbe Mega-Trend | 16.0 % / 65.0 % | 16.7 % / 64.3 % |
| Textgewinn < 2× (Volltext ≈ Anriss, z. B. Abstracts) (n=673): dieselbe Quelle / derselbe Mega-Trend | 69.3 % / 78.4 % | 71.3 % / 77.7 % |
| Textgewinn ≥ 3× (echter Volltext) (n=509): dieselbe Quelle / derselbe Mega-Trend | 15.9 % / 65.5 % | 16.1 % / 65.2 % |

Lesart: sinkt der Quellen-Anteil und steigt der Inhalts-Anteil, gruppiert der Raum nach Thema statt nach Satzform. Bei Abstracts (Textgewinn < 2×) sehen beide Raeume fast denselben Text — Unterschiede sind dort nicht zu erwarten.

## 3. kNN-Mehrheitsvotum (k = 10)
| Ziel | Dedup-Raum | Volltext-Raum | n |
|---|---|---|---|
| Vertikale, alle | 81.8 % | 81.7 % | 1200 |
| Vertikale, nur published (Stage-8-geprueft) | 75.0 % | 76.2 % | 600 |
| Vertikale, published mit Textgewinn ≥ 3× | 76.0 % | 76.2 % | 484 |
| Mega-Trend, alle (Kopf-Label, dedup-nah) | 83.4 % | 82.8 % | 1107 |
| Mega-Trend, nur published | 77.8 % | 78.0 % | 554 |
| Mega-Trend, published mit Textgewinn ≥ 3× | 78.1 % | 79.2 % | 452 |

Schieflage beachten: Mega-Trend und Vertikale der Signale kommen von den Distill-Koepfen, die auf dem Dedup-Vektor trainiert sind — der alte Raum ist hier im Vorteil. Zieht der neue gleich oder vorbei, wiegt das doppelt.

## 4. Silhouette auf Mega-Trend-Ebene (Stichprobe 3000, Klassen mit ≥ 20)
- Dedup-Raum **-0.041**, Volltext-Raum **-0.035** (Anlass #102: ~0,02)

## 5. Dubletten-Probe (Paare mit Dedup-Kosinus > 0,92)
- 3 Paare; Volltext-Kosinus Median **0.913**, Quartile 0.911/0.937, unter 0,7: 0 %
  - auseinander: 0.924 → 0.909 · „Oracle Health Executives Subpoenaed Following $17 Billion VA Contract “ ↔ „Congress Subpoenas Oracle Executives Over Tripled VA Electronic Health“
  - auseinander: 0.923 → 0.913 · „METHOD AND APPARATUS FOR DETERMINING TRANSMISSION CONFIGURATION INDICA“ ↔ „METHOD AND APPARATUS FOR UPLINK TRANSMISSION CONSIDERING UPLINK TRANSP“
  - auseinander: 0.923 → 0.961 · „Fraunhofer IPMS to Showcase High-Resolution Phase Modulation for Advan“ ↔ „Fraunhofer IPMS to Showcase High-Resolution Phase Modulation at Photon“

## 6. Retrieval-Probe (Top 5 je Raum, Anfrage ueber :8091)
### „gut microbiome and mental health“
- **Dedup:**
  - 0.709 · Deciphering the Gut-Brain Dialogue: A Survey-Based and In-Silico Comparative Analysis of G *(biorxiv Preprints, HEALTH)*
  - 0.657 · Genetic Overlap Between Gut Disease and Depression Identified by QIMR Berghofer *(Medical Xpress, HEALTH)*
  - 0.610 · Adjunctive Psychobiotic Lactiplantibacillus plantarum PS128 Therapy and Escitalopram in Ma *(medrxiv Preprints, HEALTH)*
  - 0.604 · Microbial Transmission Speeds Up Across Borders *(ScienceDaily Top, HEALTH)*
  - 0.583 · Gut Fungus Mucor racemosus Protects Against Radiation-Induced DNA Damage *(Medical Xpress, HEALTH)*
- **Volltext:**
  - 0.734 · Deciphering the Gut-Brain Dialogue: A Survey-Based and In-Silico Comparative Analysis of G *(biorxiv Preprints, HEALTH)*
  - 0.646 · Adjunctive Psychobiotic Lactiplantibacillus plantarum PS128 Therapy and Escitalopram in Ma *(medrxiv Preprints, HEALTH)*
  - 0.626 · Genetic Overlap Between Gut Disease and Depression Identified by QIMR Berghofer *(Medical Xpress, HEALTH)*
  - 0.590 · From Public Archive to Reusable Resource: Characterizing Gut Microbiome Metadata in the NC *(biorxiv Preprints, TECH)*
  - 0.579 · Investigating the Neuroinflammatory and Metabolomic Mechanisms by which the Gut Microbiome *(NIH RePORTER (US Biomedical Funding), HEALTH)*

### „solid-state battery manufacturing scale-up“
- **Dedup:**
  - 0.693 · ALL-SOLID-STATE BATTERY MANUFACTURING METHOD AND ALL-SOLID-STATE BATTERY MANUFACTURING APP *(EPO DOCDB (ECO), TECH)*
  - 0.654 · ALL-SOLID-STATE SECONDARY BATTERY AND MANUFACTURING METHOD THEREFOR *(EPO DOCDB (ECO), TECH)*
  - 0.646 · MOLD FOR MANUFACTURING SECONDARY BATTERY AND METHOD FOR MANUFACTURING ALL-SOLID-STATE SECO *(EPO DOCDB (ECO), TECH)*
  - 0.603 · NOVONIX Synthetic Graphite Qualification Hits 12 of 14 Parameters *(GlobeNewswire, TECH)*
  - 0.598 · SBIR Phase II: Novel electrolyzer architectures to enable low-cost chemical manufacturing  *(NSF Awards (US Federal Research Funding), TECH)*
- **Volltext:**
  - 0.679 · ALL-SOLID-STATE BATTERY MANUFACTURING METHOD AND ALL-SOLID-STATE BATTERY MANUFACTURING APP *(EPO DOCDB (ECO), TECH)*
  - 0.665 · ALL-SOLID-STATE SECONDARY BATTERY AND MANUFACTURING METHOD THEREFOR *(EPO DOCDB (ECO), TECH)*
  - 0.653 · MOLD FOR MANUFACTURING SECONDARY BATTERY AND METHOD FOR MANUFACTURING ALL-SOLID-STATE SECO *(EPO DOCDB (ECO), TECH)*
  - 0.624 · SBIR Phase II: Novel electrolyzer architectures to enable low-cost chemical manufacturing  *(NSF Awards (US Federal Research Funding), TECH)*
  - 0.609 · NOVONIX Synthetic Graphite Qualification Hits 12 of 14 Parameters *(GlobeNewswire, TECH)*

### „EU AI Act compliance obligations for companies“
- **Dedup:**
  - 0.675 · Lleida.net deploys digital trust tools at ANDICOM 2026 to target Latin American markets *(GlobeNewswire, TECH)*
  - 0.649 · EU investigates OpenAI agent takeover of German website *(Tech Xplore AI/ML, TECH)*
  - 0.640 · Grubel Secures €3 Million to Automate AI Specialization for Legal Cases *(EU-Startups, TECH)*
  - 0.636 · Cologne Court Upholds Injunction Against AEKE for Gym Monster Design Infringement *(PR Newswire, LIFESTYLE)*
  - 0.628 · Mondelēz Generates $10 Million via Celonis Process Mining *(Agro Media, BIZ)*
- **Volltext:**
  - 0.681 · Mondelēz Generates $10 Million via Celonis Process Mining *(Agro Media, BIZ)*
  - 0.670 · Software process modification platform for compliance *(EPO DOCDB (TECH), TECH)*
  - 0.662 · EU investigates OpenAI agent takeover of German website *(Tech Xplore AI/ML, TECH)*
  - 0.633 · EU Policymakers Rely on AI Act Amid Extinction Warnings *(Politico Europe, TECH)*
  - 0.632 · INFORMATION PROCESSING METHOD, INFORMATION PROCESSING DEVICE, AND COMPUTER PROGRAM *(EPO DOCDB (TECH), TECH)*

### „plant-based meat alternatives sales decline“
- **Dedup:**
  - 0.685 · UK Plant-Based Market Shifts Toward Legumes and Minimally Processed Proteins *(Green Queen, FOOD)*
  - 0.611 · UNFI Reports 1% Net Sales Decline Amid Shifting Product Mix *(Grocery Dive, BIZ)*
  - 0.610 · Jay&Joy scales plant-based cheese production through equity crowdfunding and retail expans *(Agro Media, FOOD)*
  - 0.609 · Beyond Meat and Daring Foods Pivot Toward Whole-Food Formats Amid Plant-Based Meat Slump *(FoodNavigator, FOOD)*
  - 0.592 · Social Networks Drive Meat Reduction Rates *(Plant Based News, LIFESTYLE)*
- **Volltext:**
  - 0.600 · Bauer Internalizes Plant-Based Base Production via GEA Turnkey Line *(Agro Media, FOOD)*
  - 0.563 · Beyond Diversifies into Phytosphere Protein Line Amid Declining Meat Sales *(Food Dive, FOOD)*
  - 0.563 · Plant-Based Gas Station Sells for Over $12 Million *(vegconomist, BIZ)*
  - 0.560 · Burger King Austria Launches Pumpkin Seed-Coated Plant-Based Crispy Chicken *(vegconomist, FOOD)*
  - 0.552 · UK Plant-Based Market Shifts Toward Legumes and Minimally Processed Proteins *(Green Queen, FOOD)*

### „quantum error correction milestones“
- **Dedup:**
  - 0.686 · Quantinuum Validates Helix Error Correction on 98-Qubit Helios Processor *(Quantum Computing Report, TECH)*
  - 0.612 · SURFACE CODES WITH DENSELY PACKED GAUGE OPERATORS *(EPO DOCDB (TECH), TECH)*
  - 0.600 · Methods, systems, and quantum circuits for rotating error suppression *(EPO DOCDB (TECH), TECH)*
  - 0.597 · I-Corps:  Translation Potential of Co-Designed Quantum Compilation for Life Science Applic *(NSF Awards (US Federal Research Funding), TECH)*
  - 0.597 · Altera and Riverlane Integrate QEC Interface with Agilex FPGAs *(The Quantum Insider, TECH)*
- **Volltext:**
  - 0.653 · SURFACE CODES WITH DENSELY PACKED GAUGE OPERATORS *(EPO DOCDB (TECH), TECH)*
  - 0.651 · Quantinuum Validates Helix Error Correction on 98-Qubit Helios Processor *(Quantum Computing Report, TECH)*
  - 0.608 · Methods, systems, and quantum circuits for rotating error suppression *(EPO DOCDB (TECH), TECH)*
  - 0.603 · HANDLING COMPONENT FAILURES IN SURFACE CODE CIRCUITS *(EPO DOCDB (TECH), TECH)*
  - 0.590 · HIERARCHICAL MULTIPLEXING FOR LOGICAL BLOCK ENCODING *(EPO DOCDB (TECH), TECH)*

### „circular fashion textile recycling“
- **Dedup:**
  - 0.670 · Integrating circular economy, cradle-to-cradle, and closed loop systems in fashion supply  *(OpenAlex fresh: Supply chain management, ECO)*
  - 0.664 · RETRAKT EU Conference to Address Textile Circularity and EU Legislative Pressures *(idw Pressemitteilungen, ECO)*
  - 0.639 · Arc’teryx Introduces Circular Hardshell with Replaceable Components *(WWD, FASHION)*
  - 0.621 · Peran Pendidikan Tata Busana dalam Mendukung Praktik Sustainable Fashion: Tinjauan Literat *(OpenAlex fresh: Sustainable design, FASHION)*
  - 0.608 · Primark Targets Material Composition to Drive Circularity *(TextilWirtschaft, ECO)*
- **Volltext:**
  - 0.665 · RETRAKT EU Conference to Address Textile Circularity and EU Legislative Pressures *(idw Pressemitteilungen, ECO)*
  - 0.660 · Integrating circular economy, cradle-to-cradle, and closed loop systems in fashion supply  *(OpenAlex fresh: Supply chain management, ECO)*
  - 0.618 · Primark Targets Material Composition to Drive Circularity *(TextilWirtschaft, ECO)*
  - 0.582 · SMART TEXTILES *(EPO DOCDB (TECH), TECH)*
  - 0.577 · Arc’teryx Introduces Circular Hardshell with Replaceable Components *(WWD, FASHION)*

