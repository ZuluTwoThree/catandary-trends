# Volltext-Vektoren gegen Dedup-Vektoren — Messung 2026-09-11 22:22

Grundgesamtheit: **95,023** Trends mit beiden Vektoren ([('signal', 88737), ('published', 4663), ('draft', 1590), ('rejected', 33)]); Anfragen: 1200 (je 600 published / uebrige), k = 10, Kosinus. Textgewinn Volltext/Anriss: Median 1.1×, Anteil ≥ 3×: 5 %.

## 1. Sehen die Raeume dasselbe? (Jaccard@10 zwischen den Nachbarlisten)
- mittlere Ueberlappung **0.37** (Median 0.33); 1 % der Anfragen haben KEINEN gemeinsamen Nachbarn
- mittlerer Kosinus zum naechsten Nachbarn: Dedup 0.687, Volltext 0.700

## 2. Satzform oder Inhalt? Anteil der Nachbarn mit …
| | Dedup-Raum | Volltext-Raum |
|---|---|---|
| derselben Quelle (Form) | 39.9 % | 40.3 % |
| demselben Mega-Trend (Inhalt) | 76.3 % | 75.5 % |
| derselben Vertikale (Inhalt) | 78.2 % | 78.5 % |
| nur `signal` (n=591): dieselbe Quelle / derselbe Mega-Trend | 68.9 % / 83.2 % | 69.9 % / 82.8 % |
| nur `published` (n=600): dieselbe Quelle / derselbe Mega-Trend | 11.8 % / 69.4 % | 11.3 % / 68.3 % |
| Textgewinn < 2× (Volltext ≈ Anriss, z. B. Abstracts) (n=706): dieselbe Quelle / derselbe Mega-Trend | 59.6 % / 80.3 % | 60.6 % / 80.1 % |
| Textgewinn ≥ 3× (echter Volltext) (n=482): dieselbe Quelle / derselbe Mega-Trend | 11.7 % / 70.1 % | 11.2 % / 68.3 % |

Lesart: sinkt der Quellen-Anteil und steigt der Inhalts-Anteil, gruppiert der Raum nach Thema statt nach Satzform. Bei Abstracts (Textgewinn < 2×) sehen beide Raeume fast denselben Text — Unterschiede sind dort nicht zu erwarten.

## 3. kNN-Mehrheitsvotum (k = 10)
| Ziel | Dedup-Raum | Volltext-Raum | n |
|---|---|---|---|
| Vertikale, alle | 85.2 % | 85.7 % | 1200 |
| Vertikale, nur published (Stage-8-geprueft) | 78.0 % | 80.2 % | 600 |
| Vertikale, published mit Textgewinn ≥ 3× | 78.6 % | 80.5 % | 473 |
| Mega-Trend, alle (Kopf-Label, dedup-nah) | 86.6 % | 84.6 % | 1127 |
| Mega-Trend, nur published | 82.1 % | 78.1 % | 558 |
| Mega-Trend, published mit Textgewinn ≥ 3× | 82.6 % | 77.9 % | 443 |

Schieflage beachten: Mega-Trend und Vertikale der Signale kommen von den Distill-Koepfen, die auf dem Dedup-Vektor trainiert sind — der alte Raum ist hier im Vorteil. Zieht der neue gleich oder vorbei, wiegt das doppelt.

## 4. Silhouette auf Mega-Trend-Ebene (Stichprobe 3000, Klassen mit ≥ 20)
- Dedup-Raum **-0.026**, Volltext-Raum **-0.019** (Anlass #102: ~0,02)

## 5. Dubletten-Probe (Paare mit Dedup-Kosinus > 0,92)
- 3 Paare; Volltext-Kosinus Median **0.961**, Quartile 0.935/0.977, unter 0,7: 0 %
  - auseinander: 0.924 → 0.909 · „Congress Subpoenas Oracle Executives Over Tripled VA Electronic Health“ ↔ „Oracle Health Executives Subpoenaed Following $17 Billion VA Contract “
  - auseinander: 0.923 → 0.961 · „Fraunhofer IPMS to Showcase High-Resolution Phase Modulation for Advan“ ↔ „Fraunhofer IPMS to Showcase High-Resolution Phase Modulation at Photon“
  - auseinander: 1.000 → 0.994 · „Trump Proposes Deregulation to Challenge Meat Processing Monopolies“ ↔ „Proposed Deregulation Targets Meat Processing Monopolies“

## 6. Retrieval-Probe (Top 5 je Raum, Anfrage ueber :8091)
### „gut microbiome and mental health“
- **Dedup:**
  - 0.761 · THE GUT–BRAIN AXIS: THE INFLUENCE OF THE INTESTINAL MICROBIOME ON NEUROINFLAMMATION AND ME *(OpenAlex fresh: Microbiome, HEALTH)*
  - 0.733 · Gut Microbiota and Mental Health: Implications for Mental Health Nursing and Microbiologic *(OpenAlex fresh: Microbiome, HEALTH)*
  - 0.728 · Microbiome Interventions Struggle to Link Biological Markers to Mental Health Outcomes *(Frontiers in Nutrition, HEALTH)*
  - 0.728 · Natural products for depression: Preclinical insights into microbiota–gut–brain axis modul *(OpenAlex fresh: Microbiome, HEALTH)*
  - 0.719 · From Gut to Mind: Impact of Probiotics on Depression, Anxiety, Mood, Gut Microbiota, Sleep *(OpenAlex fresh: Obesity, HEALTH)*
- **Volltext:**
  - 0.751 · THE GUT–BRAIN AXIS: THE INFLUENCE OF THE INTESTINAL MICROBIOME ON NEUROINFLAMMATION AND ME *(OpenAlex fresh: Microbiome, HEALTH)*
  - 0.734 · Deciphering the Gut-Brain Dialogue: A Survey-Based and In-Silico Comparative Analysis of G *(biorxiv Preprints, HEALTH)*
  - 0.734 · Microbiome Interventions Struggle to Link Biological Markers to Mental Health Outcomes *(Frontiers in Nutrition, HEALTH)*
  - 0.729 · Empirical evidence for gut microbial influence on human brain neurochemistry via the gut–b *(OpenAlex fresh: Microbiome, HEALTH)*
  - 0.717 · Gut Microbiome Composition in Older Adults with PTSD Symptoms and Trauma-Exposed Controls: *(OpenAlex fresh: Microbiome, HEALTH)*

### „solid-state battery manufacturing scale-up“
- **Dedup:**
  - 0.693 · ALL-SOLID-STATE BATTERY MANUFACTURING METHOD AND ALL-SOLID-STATE BATTERY MANUFACTURING APP *(EPO DOCDB (ECO), TECH)*
  - 0.663 · ALL-SOLID-STATE BATTERY AND METHOD FOR MANUFACTURING SAME *(EPO DOCDB (ECO), TECH)*
  - 0.662 · From Raw Materials to Recycling: Environmental Challenges and Opportunities of Solid-State *(OpenAlex fresh: Battery (electricity), TECH)*
  - 0.659 · Method of manufacturing solid electrolyte membrane, method of manufacturing all-solid-stat *(EPO DOCDB (FASHION), TECH)*
  - 0.654 · ALL-SOLID-STATE SECONDARY BATTERY AND MANUFACTURING METHOD THEREFOR *(EPO DOCDB (ECO), TECH)*
- **Volltext:**
  - 0.680 · METHOD FOR MANUFACTURING BIPOLAR ALL-SOLID-STATE BATTERY AND BIPOLAR ALL-SOLID-STATE BATTE *(EPO DOCDB (ECO), TECH)*
  - 0.679 · ALL-SOLID-STATE BATTERY MANUFACTURING METHOD AND ALL-SOLID-STATE BATTERY MANUFACTURING APP *(EPO DOCDB (ECO), TECH)*
  - 0.665 · ALL-SOLID-STATE SECONDARY BATTERY AND MANUFACTURING METHOD THEREFOR *(EPO DOCDB (ECO), TECH)*
  - 0.665 · ALL-SOLID-STATE BATTERY AND METHOD FOR MANUFACTURING SAME *(EPO DOCDB (ECO), TECH)*
  - 0.657 · ALL-SOLID-STATE SECONDARY BATTERY COMPRISING FRAME STRUCTURE AND METHOD FOR MANUFACTURING  *(EPO DOCDB (ECO), TECH)*

### „EU AI Act compliance obligations for companies“
- **Dedup:**
  - 0.753 · EU AI Act Enforcement Triggers New Transparency Mandates *(Axios, TECH)*
  - 0.693 · Leading sustainably in the digital era: a pilot study of AI literacy as a leadership compe *(OpenAlex fresh: Human resource management, TECH)*
  - 0.680 · AUDIT TRAIL REGISTRATION PROGRAM, AUDIT TRAIL REGISTRATION METHOD, AND INFORMATION PROCESS *(EPO DOCDB (TECH), TECH)*
  - 0.679 · Law of Large Numbers: Accuracy as Statistical Measure for AI Compliance and Competition *(arXiv Preprints, TECH)*
  - 0.675 · Lleida.net deploys digital trust tools at ANDICOM 2026 to target Latin American markets *(GlobeNewswire, TECH)*
- **Volltext:**
  - 0.746 · EU AI Act Enforcement Triggers New Transparency Mandates *(Axios, TECH)*
  - 0.695 · VALIDATING COMPLIANCE OF A COMPUTING SYSTEM WITH NATURAL LANGUAGE EXPRESSED POLICIES *(EPO DOCDB (TECH), TECH)*
  - 0.688 · AIMS-QA: SentenceBERT retriever model *(OpenAlex fresh: Artificial intelligence, TECH)*
  - 0.681 · Mondelēz Generates $10 Million via Celonis Process Mining *(Agro Media, BIZ)*
  - 0.674 · AUDIT TRAIL REGISTRATION PROGRAM, AUDIT TRAIL REGISTRATION METHOD, AND INFORMATION PROCESS *(EPO DOCDB (TECH), TECH)*

### „plant-based meat alternatives sales decline“
- **Dedup:**
  - 0.685 · UK Plant-Based Market Shifts Toward Legumes and Minimally Processed Proteins *(Green Queen, FOOD)*
  - 0.632 · UK Consumers Swap Processed Meat Alternatives for Whole-Food Proteins *(vegconomist, FOOD)*
  - 0.611 · UNFI Reports 1% Net Sales Decline Amid Shifting Product Mix *(Grocery Dive, BIZ)*
  - 0.610 · Jay&Joy scales plant-based cheese production through equity crowdfunding and retail expans *(Agro Media, FOOD)*
  - 0.610 · Fungal Toxins Detected in All 212 Tested Plant-Based Meat Alternatives *(ScienceDaily Top, FOOD)*
- **Volltext:**
  - 0.633 · UK Consumers Swap Processed Meat Alternatives for Whole-Food Proteins *(vegconomist, FOOD)*
  - 0.600 · Bauer Internalizes Plant-Based Base Production via GEA Turnkey Line *(Agro Media, FOOD)*
  - 0.573 · Survey data on climate change concern and consumer adoption of plant-based meat alternativ *(OpenAlex fresh: Climate change mitigation, ECO)*
  - 0.563 · Beyond Diversifies into Phytosphere Protein Line Amid Declining Meat Sales *(Food Dive, FOOD)*
  - 0.563 · Plant-Based Gas Station Sells for Over $12 Million *(vegconomist, BIZ)*

### „quantum error correction milestones“
- **Dedup:**
  - 0.713 · Learning Encodings by Maximizing State Distinguishability: Variational Quantum Error Corre *(OpenAlex fresh: Quantum information science, TECH)*
  - 0.708 · Physical Limit of Quantum Error Correction (PLQEC): Foundations, Thermodynamic Bounds, and *(OpenAlex fresh: Quantum information science, TECH)*
  - 0.706 · Optimized Matrix-Product State Simulations of Quantum Error Correction Circuits *(arXiv Preprints, TECH)*
  - 0.697 · Google Quantum AI's Deltaflow Stack Targets 10,000x Error Reduction Milestone — E8 Intelli *(OpenAlex fresh: Quantum information science, TECH)*
  - 0.692 · N45: A Scalable Surface Code Architecture for Fault-Tolerant Quantum Error Correction *(OpenAlex fresh: Quantum information, TECH)*
- **Volltext:**
  - 0.702 · QLCI: The Physics and Engineering of Practical Quantum Error Correction (PRACTIQAL) *(NSF Awards (US Federal Research Funding), TECH)*
  - 0.698 · Learning Encodings by Maximizing State Distinguishability: Variational Quantum Error Corre *(OpenAlex fresh: Quantum information science, TECH)*
  - 0.696 · Experimental validation of a compact fault-tolerant architecture for trapped ions *(arXiv Preprints, TECH)*
  - 0.687 · EFFICIENT QUANTUM ERROR DECODERS VIA ENSEMBLING *(EPO DOCDB (TECH), TECH)*
  - 0.683 · Optimized Matrix-Product State Simulations of Quantum Error Correction Circuits *(arXiv Preprints, TECH)*

### „circular fashion textile recycling“
- **Dedup:**
  - 0.674 · Разработка проекта переработки текстильных отходов в нетканые материалы *(OpenAlex fresh: Artificial intelligence, TECH)*
  - 0.670 · Integrating circular economy, cradle-to-cradle, and closed loop systems in fashion supply  *(OpenAlex fresh: Supply chain management, ECO)*
  - 0.664 · RETRAKT EU Conference to Address Textile Circularity and EU Legislative Pressures *(idw Pressemitteilungen, ECO)*
  - 0.657 · METHOD FOR SEPARATING COMPONENTS OF MIXED TEXTILE FEEDSTOCK FOR RECYCLING *(EPO DOCDB (FASHION), TECH)*
  - 0.648 · The role of emerging technologies in advancing sustainability practices in the fashion and *(OpenAlex fresh: Digital health, FASHION)*
- **Volltext:**
  - 0.665 · RETRAKT EU Conference to Address Textile Circularity and EU Legislative Pressures *(idw Pressemitteilungen, ECO)*
  - 0.660 · Разработка проекта переработки текстильных отходов в нетканые материалы *(OpenAlex fresh: Artificial intelligence, TECH)*
  - 0.660 · Integrating circular economy, cradle-to-cradle, and closed loop systems in fashion supply  *(OpenAlex fresh: Supply chain management, ECO)*
  - 0.646 · The role of emerging technologies in advancing sustainability practices in the fashion and *(OpenAlex fresh: Digital health, FASHION)*
  - 0.639 · SBIR Phase II: Innovative Nylon Fibers with Performance *(NSF Awards (US Federal Research Funding), TECH)*


## Bewertung (Owner-Frage: erfuellen die neuen Vektoren ihren Zweck?)

**Noch nicht — und der Grund liegt nicht im Modell, sondern im Text.**

1. **Fuer 95 % der eingebetteten Zeilen ist der „Volltext" gar keiner.** Median
   Textgewinn 1,1×: bei Forschungs-Signalen (Abstracts, Patente — 88.737 der
   95.023 Zeilen) IST der Anriss schon der ganze verfuegbare Text. Der zweite
   Vektor wird dort aus demselben Text gerechnet wie der erste, nur ohne die
   500-Zeichen-Kappe. Dass beide Raeume sich dann kaum unterscheiden (Jaccard
   0,37, alle Label-Masse innerhalb von ±2 Punkten), ist keine Schwaeche des
   Verfahrens — es gab nichts Zusaetzliches zu sehen.
2. **Wo echter Volltext da ist (5 %, Textgewinn ≥ 3×), zeigt sich kein
   messbarer Vorteil auf Label-Ebene.** Vertikale (LLM-geprueft) +1,9 Punkte,
   Mega-Trend −4,7 Punkte (Label kommt vom Dedup-trainierten Kopf, also
   vorbelastet). Der Quellen-Anteil unter den Nachbarn — das Mass fuer
   „Satzform statt Inhalt" — ist in beiden Raeumen gleich (11,7 vs 11,2 %).
3. **Die Silhouette auf Mega-Trend-Ebene ist in beiden Raeumen negativ**
   (−0,026 / −0,019). Der Wert von ~0,02 aus dem Anlass war keine Eigenschaft
   des Dedup-Raums, sondern der Labels: die 28 Mega-Trends bilden in keinem
   Einbettungsraum Cluster. Ein laengerer Text aendert daran nichts.
4. **Retrieval:** in 4 von 6 Proben gleichwertig, in 2 (EU AI Act, Plant-based)
   liefert der Volltext-Raum diffusere Treffer (Mondelēz/Celonis, „Plant-Based
   Gas Station"). Das ist der bekannte Effekt eines Einzelvektors ueber einen
   langen Text: viele Themen je Dokument verwaessern das Titelsignal. Die
   Kur dafuer waere Passagen-Einbettung (mehrere Vektoren je Dokument), nicht
   ein laengerer Eingabetext.
5. **Kein Schaden:** Dubletten bleiben zusammen (Median 0,961), nichts wurde
   ueberschrieben, der Dedup-Raum ist unangetastet.

**Folgen fuer den geplanten Backfill der 1,7 Millionen:** von den 1.598.503
offenen Zeilen tragen nur **18.888** einen Volltext ≥ 600 Zeichen und **17.877**
einen mit Textgewinn ≥ 3× (davon 14.986 published). Ein Backfill ueber alle
wuerde zu 99 % denselben Text ein zweites Mal einbetten — ~40 h GPU fuer
nichts. Empfehlung:

- Kandidaten auf **Textgewinn ≥ 3× (und ≥ 600 Zeichen)** beschraenken — das
  sind heute ~17.900 Zeilen, ein 25-Minuten-Lauf auf bequiet; dieselbe Regel
  fuer den 09:00-Cron. Zeilen ohne Gewinn bekommen keinen zweiten Vektor;
  Verbraucher lesen `COALESCE(embedding_full_1024, embedding_1024)` — fuer
  diese Zeilen sind beide ohnehin gleichwertig.
- Der Hebel fuer Inhaltsanalyse ist die **Textabdeckung**, nicht der zweite
  Vektor: mehr Quellen mit `fulltext: true`, Nachhollaeufe, Lizenz-Aufloesung.
- Wenn inhaltliche Naehe jenseits der Grob-Labels gemessen werden soll, braucht
  es einen Test mit unabhaengigen Labels (z. B. LLM-beurteilte Paare) und
  Passagen-Vektoren als Kandidaten — ein Experiment, kein Backfill.

Messlauf: `scripts/eval_full_text_embeddings.py --queries 600 --sil 3000`
(95.023 Zeilen, 1.200 Anfragen je 600 published/uebrige, Seed 42).
