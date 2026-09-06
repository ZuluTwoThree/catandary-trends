# Agentischer Newsletter-Entwurf — Prototyp am Beispiel 2026-W35

> **Owner-Entscheid 06.09.2026: Es bleibt beim heutigen Einmalwurf — nichts wird geaendert.**
> Der agentische Loop wird NICHT integriert (Befund: Zahlen verschwinden, keine Konvergenz,
> einziger Gewinn 0 Floskeln). Auch die vorgeschlagene schlanke Variante (deterministische
> Nachpruefungen + ein gezielter Neuwurf) wird bewusst nicht gebaut. Das Skript
> `scripts/newsletter_agentic_draft.py` bleibt als dokumentierter Versuch liegen und wird
> von nichts aufgerufen.


Erzeugt: 2026-09-06T12:42:44+00:00 — `scripts/newsletter_agentic_draft.py` (Prototyp, NICHT integriert).

## Aufbau

- Modell fuer alle drei Rollen: `gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf`
- Temperaturen: Schreiber 0.65 (Editorial) / 0.6 (Vertikale), Kritiker 0.0, Ueberarbeiter 0.3
- Abbruch bei Gesamtnote >= 4.5 UND keinem offenen Mangel der Kategorie Belegtreue UND null unbelegten Zahlen in der maschinellen Pruefung
- Rundenbudget: 5; genutzt: 5
- Ergebnis: **Rundenbudget (5) erschoepft**
- Laufzeit: 56 s; Tokenaufwand grob: ~38.602 in / ~6.819 out
- Datengrundlage: 3272 veroeffentlichte Signale der Woche, 8 Vertikale (Ist-Edition nannte 3287)

## Rundenprotokoll

| Runde | Gesamt | Belegtreue | Spezifitaet | Verdichtung | Ton | Struktur | Maengel | unbelegte Zahlen | Floskeln | Woerter (Ed/Vert) | s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **2.8** | 1 | 4 | 3 | 2 | 4 | 8 | 0 | 1 | 139/337 | 12.9 |
| 2 | **2.4** | 1 | 3 | 2 | 4 | 2 | 6 | 0 | 0 | 139/177 | 10.0 |
| 3 | **2.8** | 1 | 3 | 2 | 4 | 4 | 8 | 0 | 0 | 158/179 | 10.4 |
| 4 | **2.5** | 1 | 3 | 4 | 4 | 2 | 5 | 0 | 0 | 105/195 | 10.6 |
| 5 | **2.8** | 1 | 4 | 3 | 4 | 2 | 6 | 0 | 0 | 123/205 | 6.2 |

### Hauptkritik je Runde

**Runde 1 — 2.8/5 (1 offene(r) Mangel der Kategorie Belegtreue)**

  - [tone] "Market shifts defined the business landscape" — Banned phrase 'landscape' used.
  - [evidence] "African gaming revenue is doubling global growth rates" — The data states revenue grew 11.9% and 'doubling the global market growth', not that the revenue itself is doubling the growth rate.
  - [density] "Market shifts dominated technology signals as AI infrastructure expands. Artificial Intelligence & Automation " — The vertical repeats the editorial's points about AI/water and Keystone/Alloy without adding new analytical depth or specific data points.

**Runde 2 — 2.4/5 (1 offene(r) Mangel der Kategorie Belegtreue)**

  - [evidence] "African gaming revenue growth is double the global market growth rate" — The data states revenue grew 11.9% to $1.98bn, which 'doubled the global market growth', not that the growth rate itself was double the global rate.
  - [density] "Vitalfluid secured €17.2 million to scale its plasma-based crop protection technology." — This is a near-identical repetition of the signal mentioned in the editorial without adding new analytical depth.
  - [density] "Consumer trust deficits are impacting the adoption of cultivated meat in Europe." — This is a near-identical repetition of the signal mentioned in the editorial.

**Runde 3 — 2.8/5 (1 offene(r) Mangel der Kategorie Belegtreue)**

  - [evidence] "The acceleration in these sectors reflects a decisive movement toward decentralized infrastructure and decarbo" — The data does not support the causal claim that market shifts reflect a movement toward decentralized infrastructure; it only states that market shifts are the dominant signal type.
  - [density] "Market shifts dominated technology signals." — This is a filler sentence that repeats the signal type data without adding analytical value.
  - [density] "Market shifts defined business activity, particularly regarding financial innovation." — This is a generic summary of the signal types already listed in the data.

**Runde 4 — 2.5/5 (1 offene(r) Mangel der Kategorie Belegtreue)**

  - [evidence] "African gaming revenue grew 11.9% to $1.98bn, doubling the global market growth" — The data states the revenue grew 11.9% to $1.98bn, and that this amount doubled the global market growth, not that the revenue itself doubled the growth rate.
  - [structure] "Financial Innovation & Inclusion and Clean Energy Transition are gaining momentum as market shifts dominate th" — The editorial section consists of only two paragraphs instead of the required three.
  - [specificity] "Trends are emerging in plasma technology for crop protection and the environmental impact of AI infrastructure" — The summary is too abstract; it fails to name the specific companies or technologies mentioned in the signals (e.g., Vitalfluid).

**Runde 5 — 2.8/5 (1 offene(r) Mangel der Kategorie Belegtreue)**

  - [evidence] "African gaming revenue grew 11.9% to $1.98bn, a figure that doubled the global market growth rate." — The data states the revenue doubled the global market growth, not that the figure itself doubled the rate.
  - [structure] "Financial Innovation & Inclusion and Clean Energy Transition are gaining momentum as market shifts dominate th" — The editorial is too short; the three paragraphs combined are approximately 115 words, failing the 150-200 word requirement.
  - [density] "Vitalfluid is scaling plasma-based crop protection technology through a €17.2 million funding round. AI infras" — The TECH vertical repeats the exact same two signals from the editorial without adding new context or categorization.

## Vorher / Nachher — Editorial

### A) Ist-Text der Edition 2026-W35 (Datenbank, unveraendert)

Financial Innovation & Inclusion and Clean Energy Transition are gaining significant momentum. This upward trajectory in capital movement and infrastructure deployment is driving a market shift across multiple sectors.

Meta's $18bn settlement for teen safety highlights a critical pivot toward Digital Trust & Data Sovereignty. Meanwhile, the merger between CIX and Carbonplace signals a move toward consolidated carbon markets, while U.S. gas power pipelines for data centers have reached 189 GW. Vitalfluid’s €17.2 million funding round further demonstrates the scaling of plasma-based crop protection as a chemical-free alternative.

A critical tension is emerging between Artificial Intelligence & Automation and resource scarcity. The surge in global water consumption by data centers and semiconductor plants creates a direct conflict with Climate Resilience & Adaptation goals. This resource competition will force a mandatory integration of water-efficient cooling technologies into all upcoming AI infrastructure projects.

### B) Runde 1 — Schreiber allein (heutiger Produktionspfad, frisch erzeugt)

Financial Innovation & Inclusion and Clean Energy Transition are gaining significant momentum as market shifts dominate the weekly signal count. The acceleration in these sectors reflects a decisive movement toward decentralized infrastructure and decarbonized industrial assets.

Meta’s $18bn settlement for teen safety signals a tightening regulatory environment for digital platforms, while the planned merger of CIX and Carbonplace aims to consolidate fragmented carbon markets. Simultaneously, the energy requirements of AI infrastructure are driving a surge in global water consumption and a massive expansion in U.S. gas-fired capacity for data centers.

A critical convergence is emerging between Artificial Intelligence & Automation and resource scarcity, specifically regarding water and energy. The expansion of data centers and semiconductor fabrication is directly accelerating demand for gas-fired power and freshwater resources. This dependency creates a direct link between digital scaling and physical resource volatility.

### C) Nach dem Loop (Runde 5)

Financial Innovation & Inclusion and Clean Energy Transition are gaining momentum as market shifts dominate the weekly signal count. This rise in momentum is accompanied by stable activity in Artificial Intelligence & Automation and Personalized Health & Longevity.

Meta’s $18bn settlement for teen safety signals a tightening regulatory environment for digital platforms, while the planned merger of CIX and Carbonplace aims to consolidate fragmented carbon markets. Simultaneously, the energy requirements of AI infrastructure are driving a surge in global water consumption and a massive expansion in U.S. gas-fired capacity for data centers.

This dependency creates a direct link between digital scaling and physical resource volatility. The infrastructure required to support massive AI growth places unprecedented pressure on global utility supplies and environmental stability.

## Vorher / Nachher — Vertical-Summaries

### TECH — Technology & AI

**A) Ist-Text:** Market shifts dominate the landscape as AI infrastructure drives significant water consumption in data centers. Artificial Intelligence & Automation remains the primary driver, evidenced by Keystone Cooperative partnering with Alloy Partners to build AgTech ventures.

**B) Runde 1:** Market shifts dominated technology signals as AI infrastructure expands. Artificial Intelligence & Automation drove developments in water consumption due to rising data center and semiconductor fabrication demands. Keystone Cooperative and Alloy Partners are also integrating AgTech ventures into large-scale farmer networks.

**C) Nach dem Loop:** Vitalfluid is scaling plasma-based crop protection technology through a €17.2 million funding round. AI infrastructure is also driving significant environmental impacts, specifically regarding global water consumption.

### ECO — Sustainability

**A) Ist-Text:** Market shifts define the sector as data center demand doubles planned U.S. gas power pipelines to 189 GW. Climate Resilience & Adaptation is the core driver, seen in the $26 million Series A for subsurface mapping to digitize underground infrastructure.

**B) Runde 1:** Market shifts and research drove sustainability signals, focusing on infrastructure and energy. Climate Resilience & Adaptation is a primary driver, evidenced by a $26 million Series A for subsurface mapping startups. Concurrently, data center demand is nearly doubling the planned U.S. gas-fired capacity to 189 GW.

**C) Nach dem Loop:** Sustainability trends include subsurface mapping by a former PG&E engineer's startup and the rise of photovoltaics in Berlin industrial real estate. These developments focus on infrastructure and energy.

### FOOD — Food & Beverage

**A) Ist-Text:** Market shifts and research signals indicate a focus on alternative protein scaling. Future of Food & Agriculture is the primary trend, as Maash secures €12.15M to scale mycoprotein production.

**B) Runde 1:** Market shifts and research signals focused on scaling alternative proteins. Future of Food & Agriculture is the primary driver, seen in Maash’s €12.15M raise to scale mycoprotein production. Additionally, GLP-1 medication use is driving increased protein demand for brands like Applied Nutrition.

**C) Nach dem Loop:** Activity is focused on the scaling of mycoprotein production by Maash and alternative proteins. Consumer trust issues are also impacting the adoption of cultivated meat in Europe.

## Grounding und Floskeln, maschinell gemessen

Gepruft mit `pipeline/grounding.py` gegen die `<data>`-Bloecke beider Produktions-Prompts (Titel, Summaries, Quellen, Mega-Trend-Zaehlungen). `ungrounded_specifics` = Zahl/Jahr/Betrag im Text, der in den Daten nicht vorkommt; `ungrounded_names` = Personenname ohne Beleg (laut Modul nur Warnung, blockiert den Abbruch nicht).

| Text | unbelegte Zahlen | unbelegte Namen | verbotene Floskeln | Woerter (Ed/Vert) |
|---|---|---|---|---|
| A) Ist-Edition 2026-W35 | 0 | 0 | 2 (landscape, navigate) | 141/256 |
| B) Runde 1 (Schreiber allein) | 0 | 0 | 1 (landscape) | 139/337 |
| C) Nach dem Loop (Runde 5) | 0 | 0 | 0 | 123/205 |

## Drei Laeufe, zwei Korrekturen am Prototyp

Alles oben stammt aus dem **dritten** Lauf. Die beiden ersten sind nicht
weggeworfen worden, sie haben den Prototyp korrigiert:

| Lauf | Konfiguration | Noten je Runde | Was der Lauf gezeigt hat |
|---|---|---|---|
| 1 | Kritiker sah nur den Editorial-Datenblock | 1,2 / 1,8 / 1,2 / 1,5 / 1,5 | **Fehler im Prototyp.** Der Kritiker erklaerte echte Signale fuer erfunden — „Maash €12.15M", „ProFound Therapeutics $35 million", „Politecnico di Milano" stehen alle im Vertikal-Block, den er nie zu sehen bekam. Die maschinelle Pruefung, die immer beide Bloecke sah, meldete in derselben Runde 0 unbelegte Zahlen und hatte recht. Behoben: `full_data_block()`, Regressionstest. |
| 2 | beide Bloecke, Kritiker auf „hart" kalibriert („You do not praise", bis zu 8 Maengel) | 2,5 / 2,4 / 2,4 / 2,2 / 2,2 | Belegtreue-Note sprang von 1 auf 4 — die Falschbefunde waren weg. Aber der Kritiker lieferte bei Temperatur 0 in **jeder** Runde acht Maengel und eine Note um 2,3, unabhaengig vom Entwurf. Eine Note, die sich nicht bewegt, taugt nicht als Abbruchbedingung. Neuer, echter Fund: der Ueberarbeiter kopierte die bei 80 Zeichen abgeschnittenen Summaries woertlich („Maash has raised €12.15M to fund the launch of a new dem"). |
| 3 | Notenanker statt Haltungsanweisung, leere Mangelliste erlaubt, Regel gegen das Kopieren abgeschnittener Fragmente | 2,8 / 2,4 / 2,8 / 2,5 / 2,8 | Der dokumentierte Lauf. Die Fragment-Kopien sind weg, die Noten variieren — aber sie steigen nicht. |

Die Protokolle der ersten beiden Laeufe liegen nicht im Repo; im Repo steht nur
das Protokoll des dritten Laufs (`data/newsletter_agentic/2026-W35.json`, nicht
versioniert).

## Einschaetzung: macht der Loop den Text besser?

*Von Hand geschrieben, nicht generiert — ein erneuter Lauf mit `--report` auf
diesen Pfad ueberschreibt alles oberhalb dieser Zeile, aber auch diesen
Abschnitt. Fuer eine Wiederholung besser einen neuen Dateinamen waehlen.*

**Urteil: schlechter. Nicht laenger — kuerzer und aermer.** Der Loop ist in
dieser Form nicht integrationsreif.

### Was messbar besser wurde

- **Floskeln:** 2 in der Ist-Edition („landscape", „navigate") → 1 nach dem
  Schreiber → **0** nach dem Loop. Der einzige eindeutige Gewinn.

### Was messbar schlechter wurde

- **Zahlen verschwinden.** ECO verliert die 189 GW („data center demand doubles
  planned U.S. gas power pipelines to 189 GW" → „Sustainability trends include
  subsurface mapping … and the rise of photovoltaics"). FOOD verliert die
  €12.15M. Das Editorial verliert im dritten Absatz seine konkrete Folgerung
  („will force a mandatory integration of water-efficient cooling technologies")
  und endet stattdessen mit zwei allgemeinen Saetzen.
- **Die Vertikale verliert ihr eigenes Signal.** TECH nannte vorher Keystone
  Cooperative/Alloy Partners — ein Signal, das *nur* dort vorkommt. Nach dem
  Loop steht dort Vitalfluid, also genau das Signal, das schon im Editorial
  steht. Das Kriterium „Verdichtung" sollte das verhindern und hat es
  verursacht.
- **Laenge:** Vertikale zusammen 337 → 205 Woerter, Editorial 139 → 123. Der
  Kritiker beanstandet in den Runden 2, 4 und 5 selbst, das Editorial
  unterschreite die 150 Woerter — und der Ueberarbeiter kuerzt trotzdem weiter.
  Die Anweisung „mach es laenger" wirkt nicht; die Anweisung „streich das"
  wirkt sofort.

### Was der Loop gar nicht geleistet hat

- **Belegtreue:** 0 unbelegte Zahlen vorher, 0 in jeder einzelnen Runde, 0
  nachher — in allen drei Laeufen. Der Produktionspfad halluziniert an dieser
  Stelle nicht, es gab nichts zu reparieren. Der Loop hat die Belegtreue nicht
  verbessert; er hat sie in Lauf 1 sechsmal falsch **beschuldigt**.
- **Konvergenz:** 2,8 / 2,4 / 2,8 / 2,5 / 2,8. Kein Aufwaertstrend. Das Modell
  haelt seine eigene fuenfte Fassung nicht fuer besser als seine erste.
- **Abbruch:** nie erreicht. In jeder Runde stand genau ein Mangel der
  Kategorie Belegtreue offen, ab Runde 2 immer derselbe: das Modell liest den
  Quellsatz „African gaming revenue grew 11.9% to $1.98bn, doubling the global
  market growth" und beharrt darauf, der Entwurf gebe ihn falsch wieder. Ein
  einziges hartnaeckiges Missverstaendnis blockiert den ganzen Loop — und zwar
  ein Missverstaendnis, bei dem die maschinelle Pruefung dem Modell dreimal
  widersprochen hat.

### Kosten

56 s und grob 38.600 Eingabe- / 6.800 Ausgabe-Token fuer fuenf Runden gegen
~5 s und grob 7.000 / 1.000 Token fuer den heutigen Einmalwurf. Der Faktor ist
etwa fuenf bis acht, absolut aber unter einer Minute — **die Kosten sind nicht
das Argument gegen den Loop.** Die Qualitaet ist es.

### Was ein zweiter Anlauf braeuchte

1. **Der Kritiker darf ueber Belegtreue nicht entscheiden.** Die
   deterministische Pruefung lag dreimal richtig, das Modell zweimal falsch.
   Belegtreue gehoert komplett an `pipeline/grounding.py`; der Kritiker
   bekaeme sie nur noch als Befund, nicht als eigenes Urteilsfeld.
2. **Ein Ueberarbeiter darf keine belegte Zahl verlieren.** Messbar: Menge der
   gegroundeten Zahlen vor und nach der Ueberarbeitung vergleichen und eine
   Fassung verwerfen, die welche einbuesst. Das ist der wichtigste einzelne
   Schutz — genau hier entsteht der Schaden.
3. **Laenge deterministisch erzwingen**, wie die Content-Gen-Guard es tut
   (`STAGE5_TARGET_BODY_WORDS`). Bitten hilft nicht.
4. **Das Kriterium „Verdichtung" ist die Schadensquelle.** Entweder streichen
   oder auf woertliche Satzdopplung einschraenken, mechanisch gemessen
   (n-Gramm-Ueberlappung), statt es dem Modell zu ueberlassen, was „dieselbe
   Aussage" heisst.
5. **Guenstigere Alternative, die den einzigen gemessenen Gewinn behaelt:**
   Einmalwurf wie heute, danach deterministische Nachpruefungen (Floskeln,
   Zahl-Erhalt, Wortzahl) und **ein** gezielter Neuwurf der beanstandeten
   Stelle. Das holt die 0 Floskeln, ohne den Text auszuduennen.

### Ehrliche Einschraenkung dieses Vergleichs

Ein Lauf, eine Woche, ein Modell. Die Ist-Edition (A) entstand am 2026-08-31 aus
3287 Signalen, die Rekonstruktion sieht 3272 — 15 Zeilen der Woche haben seither
ihren Status geaendert. Fuer den Vergleich ist die eigentliche Referenz ohnehin
**B** (Runde 1, frisch mit denselben Prompts erzeugt): B gegen C misst den Loop,
A gegen C misst zusaetzlich das Wuerfeln des Schreibers.
