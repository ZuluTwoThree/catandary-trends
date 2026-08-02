# Horizont-Radar: Befund und Redesign-Vorschlag

**Stand:** 2026-07-30 · Branch `dev` · Bezug: Issue #3 (Foresight-Visualisierungen), Owner-Vorgabe „Radar soll strategisches Tool sein, kein Trend-Dump"

Teil 1 ist der verifizierte Befund am bestehenden Radar, Teil 2 das Zielbild,
Teil 3–5 die Optionen (Positionierung, Layout, Trendkarten-Icon), Teil 6 die
Datenlücken. **Teil 7 hält die getroffenen Entscheidungen und die erste
Umsetzung fest**, einschließlich der Fehlklassifikationen, die der Kalibrierlauf
aufgedeckt hat.

## Entscheidungen (Owner, 2026-07-30)

| Frage | Entscheidung |
|---|---|
| Positionierung | **Hybrid je Dimension** (§3.6): Technologie über TIR/Takeoff, Regulatorik über Meilenstein-Gates je Jurisdiktion, Markt über Produktstarts je Region; Override-Schicht vorgesehen |
| Layout | **Matrix als Arbeitsansicht + Polar als Export** (§4, Layout 2 + 1) |
| Trendkarten | **Profil-Punkte** (§5, Variante iii) |
| Erster Schnitt | **Referenz-Radar „Alternative Proteine"** mit 8 Feldern |

---

## 1. Befund: was das Radar heute tut

Geprüft: `frontend/src/components/foresight/TrendRadar.tsx`,
`frontend/src/lib/foresight.ts:236-338`, `frontend/src/app/trends/foresight/radar/page.tsx`,
`frontend/src/app/api/foresight/radar/route.ts`, `pipeline/foresight.py:63-71`,
`pipeline/foresight_snapshot.py`, plus Live-DB und gerendertes DOM auf :3004.

### 1.1 Die Ringe messen nicht Reife, sondern Quellenherkunft

Die vier Ringe (Research / Patents / Funding / Market) kommen aus
`TIER_FILTERS` in `pipeline/foresight.py:63`:

```python
"science":  s.source_type = 'research' OR source_name LIKE '%Preprints%'
"patent":   source_name LIKE 'Google Patents%' OR 'EPO %'
"funding":  source_name LIKE 'NIH RePORTER%' | 'NSF %' | 'OpenAIRE%' | 'UKRI%' | 'SEC Form D%'
"market":   s.source_type IN ('trade_media','press_wire','brand')
```

Der Ring ist also eine **Eigenschaft der Quelle**, nicht des Trends. Ein Blip im
Research-Ring bedeutet ausschließlich „dieses Cluster besteht aus Signalen, die
aus Forschungsquellen kamen". Über die Reife der Technologie sagt das nichts:
dieselbe Technologie erzeugt gleichzeitig Preprints, Patente und
Produktmeldungen. Die Ringposition ist eine Korpus-Partition, kein Befund.

### 1.2 Es gibt keine Identität über die Ringe hinweg — die zentrale Aussage der Seite ist unmöglich

Jeder Ring wird **separat geclustert** (ein eigener `foresight_runs`-Eintrag pro
Tier, `getRadarData` iteriert über die vier Runs). Konsequenz, an der Live-DB
geprüft: die Label-Mengen der vier Ringe sind **vollständig disjunkt** —
Schnittmenge 0 in allen sechs Ring-Paaren.

Die Seite verspricht aber wörtlich (`radar/page.tsx:67`):
> „Watch what is climbing toward the middle."

Das kann die Datenstruktur nicht leisten. Ein Cluster kann sich nicht nach innen
bewegen, weil es in den inneren Ringen kein Gegenstück mit derselben Identität
gibt. Die Kernmetapher des Radars ist nicht implementierbar, solange
Ring = eigenständiges Clustering ist.

### 1.3 Die Objekte sind breite Forschungsfelder, keine Technologiefelder

Die größten Blips heißen real:

| Ring | Beispiel-Labels | Signale |
|---|---|---|
| Research | „Food Safety · Food Science", „Clinical Trials · Clinical Trial" | 11.393 / 11.101 |
| Patents | „Cloud Computing · Cybersecurity", „Machine Learning · AI" | 7.100 / 4.292 |
| Funding | „Regenerative Medicine · Stem Cell Research" | 10.928 |
| Market | „Venture Capital · Funding Round", „Consumer Electronics · Wearable Technology" | 40.719 / 33.369 |

„Venture Capital · Funding Round" ist kein Technologiefeld, sondern eine
Signalgattung. Ein Strategie-Anwender kann mit diesen Objekten keine Entscheidung
treffen — sie sind zu grob und teils gar keine Technologien. Der Anwender kann
außerdem **nicht sagen, was ihn interessiert**: die einzige Steuerung ist der
Vertical-Filter, sonst liegt der gesamte Korpus über alle Vertikalen auf einer
Scheibe.

### 1.4 Überlappung ist strukturell, nicht kosmetisch

Nachgerechnet mit der Geometrie aus `TrendRadar.tsx:65-97` und den echten 97
Blips des aktuellen Snapshots:

- **97 Blips** auf **7 Segmenten × 4 Ringen**, davon nur **17 von 28 Zellen belegt**
- Dichteste Zellen: HEALTH/Funding **17 Blips**, TECH/Research **15**, TECH/Patents **15**
- Blip-Radien 7,7–18,0 px in einem 640-px-SVG
- Der Jitter kennt nur **5 Winkelplätze** (`(n % 5) - 2`) und **6 px** Radialversatz pro Reihe (`Math.floor(n/5) * 6`)
- Ergebnis: **151 überlappende Paare**, bei **65** liegt der Mittelpunkt eines Punktes *innerhalb* eines anderen. **86 von 97 Blips (89 %) überlappen mindestens einen Nachbarn.**
- Schlimmster Fall: zwei Punkte mit Radiensumme 26,6 px in **6,0 px** Abstand

Das ist keine Dichte-Panne bei Ausreißern, sondern die Regel: 36-px-Punkte werden
6 px auseinander gesetzt. Jeder Fix, der die Punktzahl nicht senkt **oder** die
Kollision auflöst, verschiebt das Problem nur.

### 1.5 Es gibt keinen Drill-down

Der Klick auf einen Blip führt nach `/trends/foresight/clusters?vertical=X`
(`TrendRadar.tsx:249`) — also auf eine **nach Vertikale gefilterte Liste**. Die
angeklickte Cluster-Identität wird dabei **verworfen**. Eine Cluster-Detailseite
existiert nicht (`app/trends/foresight/clusters/` enthält nur `page.tsx`). Der
Nutzer kann einen Punkt also nicht vertiefen — bestätigt genau die Kritik.

Zusätzlich: **an den Punkten steht kein Text**, nur ein Momentum-Glyph (↗ → ↘).
Um zu erfahren, was ein Punkt *ist*, muss man ihn einzeln hovern — bei 97 Punkten
mit 89 % Überlappung praktisch unbenutzbar, auf Touch gar nicht.

### 1.6 Der Snapshot ist ein Einmal-Artefakt

`foresight_runs` enthält **genau einen** Run pro Tier, alle vom **2026-07-13**.
Die Seite schreibt „Updated Jul 14, 2026" — heute 16 Tage alt. Es gibt **keinen
Cron-Job** für `foresight_snapshot.py` (weder in der User-Crontab noch in
`scheduled_cycle.sh`). Das Radar veraltet ohne Gegenmaßnahme monoton, während die
Pipeline täglich ~500 neue Trends erzeugt.

### 1.7 Zwei widersprüchliche Tier-Taxonomien im selben Produkt

- Radar: **4** Tiers `science / patent / funding / market`
- Cockpit (`ForesightCockpit.tsx:106-110`): **3** Tiers `future / market / now`, jeweils **mit Zeithorizont** beschriftet („Science / Research (5-10y)", „Trade Press (1-2y)", „Consumer / Lifestyle (real-time)")

Das Cockpit macht damit implizit schon, was das Radar tun soll: es hängt an einen
**nutzerdefinierten Suchbegriff** eine Horizont-Aussage („Signal Path"). Diese
Mechanik ist der brauchbare Kern, auf dem das Redesign aufsetzen kann — sie ist
nur nicht als Radar visualisiert und nicht mit dem Radar-Datenpfad verbunden.

### 1.8 Was gut ist und bleiben soll

- Das Readout-Panel mit Klartext, Tags und **Evidenz-Links** ist genau richtig und muss erhalten bleiben.
- Der Free-Preview/`TierGate`-Mechanismus funktioniert.
- A11y-Grundlagen sind da (`role`, `aria-label`, `tabIndex`, Touch-Targets) — nur nutzlos, solange die Punkte übereinanderliegen.
- `idx_trends_embedding_1024_hnsw` (HNSW über **alle** Trends, nicht nur published) existiert — die technische Voraussetzung, um ein nutzerdefiniertes Feld über den ganzen Signalraum aufzulösen, ist vorhanden.

---

## 2. Zielbild

Ein Radar, das eine **Handlungsempfehlung** trägt statt einer Korpus-Statistik:

| | heute | Ziel |
|---|---|---|
| Objekt auf dem Radar | auto-entdecktes Cluster (breites Feld) | **nutzerdefiniertes Technologiefeld** |
| Ringe | Quellenherkunft (4 Tiers) | **H1 / H2 / H3** = Handlungshorizont |
| Segmente | 8 Vertikalen (alle gleichzeitig) | **Dimensionen** (konfigurierbar: Technologie/Regulatorik/Markt, oder PESTEL) |
| Region | nicht vorhanden | **Slice** (EU / US / Global …) |
| Anzahl Radare | 1 fest verdrahtetes | **n konfigurierbare** (gespeichert, teilbar) |
| Drill-down | verwirft Identität | Feld × Dimension → Evidenzliste |

**Architektur-Kern:** Der PESTEL-Radar und der Technologie-Radar sind **dasselbe
Objekt mit anderem Dimensions-Set**. Ein Radar ist eine Konfiguration:

```
Radar = {
  name,
  scopes:     [Technologiefeld, …]     # je Feld: Freitext → Embedding-Query (+ optional CPC-Codes, Tags)
  dimensions: [Dimension, …]           # Preset "strategisch": Technologie | Regulatorik | Markt | Adoption
                                       # Preset "PESTEL":      P | E | S | T | En | L
                                       # Preset "Evidenz":     Science | Patent | Funding | Market  (heutiges Verhalten)
  region:     "EU" | "US" | "GLOBAL" | …
  window:     letzte N Monate
}
```

Das Beispiel des Owners fällt damit direkt aus dem Modell heraus:
**Precision Fermentation** ist *ein* Scope, der pro Dimension und Region
unterschiedliche Horizonte hat — Technologie H2, Regulatorik H3 (EU), Markt H1 (US/IL).
Nicht drei Punkte auf einem Radar, sondern **ein Feld mit einem Horizont-Profil**.
Genau dieses Profil ist die strategische Aussage.

---

## 3. Positionierungs-Optionen (H1/H2/H3 bestimmen)

### 3.0 Vorab: die Datenlage trägt das Owner-Beispiel

Machbarkeitstest an der Live-DB mit dem Scope `fermentation` (1.414 Trends,
Volltext-Match, Jahre 1990–2026):

**Signaltypen im Scope** — eine brauchbare Reifeleiter, vollständig befüllt:

| research | product_launch | funding | market_shift | partnership | regulation | patent | consumer_behavior |
|---|---|---|---|---|---|---|---|
| 799 | 216 | 163 | 124 | 54 | 39 | 12 | 7 |

**`regions` ist genau dort stark, wo es zählt:**

| signal_type | mit Region |
|---|---|
| regulation | **100 %** (39/39) |
| consumer_behavior | 100 % (7/7) |
| product_launch | **96 %** (205/213) |
| funding | 92 % (150/163) |
| partnership | 92 % (49/53) |
| market_shift | 50 % (61/123) |
| research | 38 % (301/791) |
| patent | 27 % (3/11) |

Die entscheidungsrelevanten Signale (Zulassung, Produktstart, Finanzierung) tragen
also fast immer eine Jurisdiktion; nur die generischen Forschungssignale nicht —
was wenig schadet, weil Forschung ohnehin global gelesen wird.

**Jurisdiktion × Signaltyp (ab 2022)** — das rohe Substrat einer Horizont-Zelle:

| | research | funding | partnership | product_launch | market_shift | regulation |
|---|---|---|---|---|---|---|
| **US** | 9 | 27 | 11 | **51** | 6 | 9 |
| **EU** | 21 | 47 | 15 | 44 | 9 | **16** |
| UK | 4 | 8 | 1 | 4 | 0 | 4 |
| **IL** | 0 | 5 | 4 | 5 | 1 | 3 |
| GLOBAL | 176 | 28 | 13 | 69 | 32 | 4 |

Und die Regulatorik-Signale lesen sich **exakt wie die Owner-Hypothese**:

- **US → H1:** „Remilk's Precision Fermentation Dairy Is the Second to Earn U.S. GRAS Status" (2022), „TurtleTree Obtains Self-Affirmed GRAS Status" (2023), „Onego Bio Receives FDA ‚No Questions' Letter" (2025), „FDA Clears Precision Fermentation Lamb Protein" (2026), plus Markt: „The Retail Validation of Precision Fermentation", „Fermentation's Retail Breakthrough: Chunk Foods Signals Scale for Whole Foods" (2026)
- **IL → H1:** „Remilk Is the First Precision Fermentation Dairy Approval In Israel" (2023), „Imagindairy … Earn US [GRAS]" (2023, `US,Israel`)
- **EU → H3/H2:** „Precision fermentation startups team up to tackle ‚black box' EU novel foods process" (2023), „Fermentation Can Futureproof the EU Food System – But Only With Regulatory Reform" (2025), „EU Bioeconomy Strategy to ‚Accelerate' Approvals" (2025), „EU Opens Public Consultation on Biotech Act II" (2026-05), „The Regulatory Lag: What Fermotein's EU Approval Reveals" (2026-06)

Das ist die wichtigste Erkenntnis des Papiers: **die Einordnung muss nicht
erfunden werden, sie steht in den Signalen.** Was fehlt, ist die Auswertung.

### 3.1 Option A — Evidenz-Schwerpunkt (Signal-Mix-Zentroid)

Signaltypen auf eine ordinale Reifeachse legen (Forschung → Patent → Förderung →
Partnerschaft → Produktstart/Marktbewegung), den **anteilsgewichteten Schwerpunkt**
über ein Zeitfenster berechnen und **gegen die Korpus-Baseline normalisieren**
(Lift statt Rohanteil — sonst sieht alles nach H1 aus, weil Marktquellen den
Korpus dominieren). Ergebnis ist ein **kontinuierlicher** Wert, aus dem H1/H2/H3
als Bänder fallen.

- **Datenbasis:** vollständig vorhanden (`trend_signal_type` + `sources.source_type`), kein LLM, reines SQL
- **Stärke:** liefert eine *stetige* Radialposition → Punkte müssen nicht in drei Ringe gestapelt werden, und die Bewegung nach innen über die Zeit wird erstmals wirklich berechenbar (das Versprechen aus 1.2)
- **Erklärbar:** „62 % der Signale der letzten 12 Monate liegen auf Markt-Stufe, gegenüber 38 % im Korpusmittel"
- **Schwäche:** kennt keine Schwellen — es weiß nicht, ob eine *Zulassung* vorliegt, nur dass viel Regulatorik-Rauschen da ist. Für die Regulatorik-Dimension zu grob.
- **Aufwand:** klein (1–2 Tage)

### 3.2 Option B — Meilenstein-Gates (Evidenz-Schwellen)

Pro Dimension explizite, prüfbare Regeln über gezählte Evidenz statt eines Scores:

| Dimension | H3 | H2 | H1 |
|---|---|---|---|
| Technologie | nur Forschung/Preprints | Patente + Prototypen/Partnerschaften | Produktstarts in Serie |
| Regulatorik | kein Zulassungspfad, nur Forderungen/Lücken-Berichte | Konsultation, Entwurf, Pfad eröffnet, Antrag anhängig | Zulassung erteilt / in Kraft |
| Markt | keine Produkte | Pilot, limitierter Launch | mehrere Produktstarts + Handelsverfügbarkeit |

- **Datenbasis:** Zählung vorhanden; **eine Lücke:** `trend_signal_type='regulation'` unterscheidet nicht zwischen *Konsultation* und *Zulassung erteilt* — genau die Grenze zwischen H2 und H1. Braucht einen Sub-Typ (Regelwerk auf Titel/Body + Verifikation, oder eine Distill-Head-Erweiterung).
- **Stärke:** trifft das Owner-Modell punktgenau, ist auditierbar („H1, weil 4 Zulassungen: GRAS Remilk 2022, GRAS TurtleTree 2023, FDA 2026, …"), und passt zur Hausregel „withhold what it can't prove" — bei zu wenig Evidenz sagt die Zelle **„unbekannt"** statt zu raten.
- **Schwäche:** Schwellen sind Setzungen; braucht Mindest-n und eine dokumentierte Kalibrierung.
- **Aufwand:** mittel (Sub-Typ-Anreicherung + Regelwerk, ~4–6 Tage)

### 3.3 Option C — Distill-Head / LLM-Klassifikation

Einen Embedding-Head (Infrastruktur läuft produktiv für Vertical/Mega/PESTEL) auf
(Evidenzbündel → H pro Dimension) trainieren.

- **Stärke:** fängt Graufälle, GPU-frei im Betrieb
- **Schwäche:** **Kaltstart** — jemand muss einige hundert Feld×Dimension-Fälle labeln; und es erzeugt genau den undurchsichtigen Score, den die Positionierung öffentlich ablehnt
- **Empfehlung:** **nicht als Einstieg.** Sinnvoll später als Verfeinerungsschicht über A/B, sobald Option E Labels erzeugt hat.

### 3.4 Option D — TIR/S-Kurven-Anker (nur Technologie-Dimension)

Den bestehenden Patent-Layer nutzen: `cpc_leadtime_summary` liefert
`science_takeoff`, `market_takeoff`, `reliable`; dazu k (Improvement Rate).
Vor Science-Takeoff → H3, zwischen den Takeoffs → H2, nach Market-Takeoff → H1.

- **Stärke:** bereits berechnet, peer-reviewed, gegen den MIT-Datensatz validiert — das methodisch stärkste Asset im Haus
- **Schwäche:** nur patentierbare Felder; Abdeckung endet wegen Frontfile-Rückstand (#49) ~2019/20; im Trend-Korpus selbst sind Patent-Signale dünn (12 im Test-Scope — die Patentmasse liegt im Graph, nicht in `trends`)
- **Empfehlung:** **ideal für die Technologie-Dimension, ungeeignet für alle anderen.**

### 3.5 Option E — Assistierte Platzierung (Analyst-Override)

Das System berechnet einen Vorschlag (A/B/D), der Nutzer kann pro Zelle
**überschreiben und begründen**; gespeichert an der Radar-Konfiguration.

- **Stärke:** macht das Tool board-fähig (ein Analyst will die Platzierung
  verantworten, nicht nur ansehen), rettet Zellen mit dünner Evidenz, und
  **erzeugt genau die Labels, die Option C später braucht**
- **Schwäche:** braucht Persistenz pro Nutzer (Accounts existieren, Gates aus)
- **Aufwand:** klein, sobald das Config-Objekt steht

### 3.6 Empfehlung

**Hybrid, nach Dimension getrennt — kein einzelner Mechanismus für alles:**

| Dimension | Mechanismus |
|---|---|
| Technologie | **D** (TIR/Takeoff), Fallback **A** wenn kein CPC-Match |
| Regulatorik | **B** (Gates, jurisdiktionsweise) |
| Markt / Adoption | **A** + **B** (Produktstart-Zählung pro Region) |
| alle | **E** als Override-Schicht, **C** erst nach Label-Aufbau |

Und: **jede Zelle trägt ihre Evidenz und darf „unbekannt" sein.** Ein Radar, das
bei dünner Datenlage schweigt, ist das Verkaufsargument des Hauses.

---

## 4. Layout-Optionen

Vorbemerkung: Das Überlappungsproblem ist **primär ein Mengenproblem**. Ein
strategisches Radar zeigt **8–20 bewusst gewählte Felder**, nicht 97 automatisch
entdeckte Cluster. Mit der Scope-Definition aus Teil 2 verschwindet die Ursache;
die Layout-Wahl entscheidet, wie robust es bei 20+ bleibt.

### Layout 1 — Polar mit echter Kollisionsauflösung

Ringe = H1/H2/H3 (innen = H1 = jetzt handeln), Sektoren = Dimensionen.
Punkte werden nach der Ringzuordnung **iterativ entzerrt** (Kollisions-Relaxation
innerhalb des Ring-Bands), Labels **immer sichtbar** mit Leader-Lines.

```
            Technologie
      ┌───────────────────────┐
      │   ·Feld C             │   H3  (beobachten)
      │      ┌───────────┐    │
Regu- │      │  ·Feld B  │    │   H2  (aufbauen)
lato- │      │  ┌─────┐  │    │
rik   │      │  │·A   │  │    │   H1  (handeln)
      │      │  └─────┘  │    │
      └───────────────────────┘
              Markt
```

- **+** vertraute Foresight-Sprache, exportfähig als Board-Artefakt
- **−** bleibt bei hoher Dichte anspruchsvoll; Sektor-Aufteilung kostet Fläche

### Layout 2 — Horizont-Matrix (Empfehlung als analytischer Kern)

Zeilen = Technologiefelder, Spalten = Dimensionen (+ Region als Umschalter),
Zelle = H-Badge mit Evidenzzahl. **Überlappung ist konstruktiv unmöglich.**

```
                    Technologie   Regulatorik   Markt      Adoption
Precision Ferm.        H2            H3 (EU)     H1 (US)     H2
                                     ▲ Konsultation, keine Zulassung
Cultivated Meat        H2            H3 (EU)     H2 (US)     H3
Mycoprotein            H1            H1 (EU)     H1          H1
```

- **+** liest sich als **Profil pro Feld** — genau die Aussage des Owner-Beispiels; skaliert auf beliebig viele Felder; direkt vergleichbar; barrierefrei als echte Tabelle
- **−** weniger „Radar", mehr Cockpit — als Verkaufsbild schwächer

### Layout 3 — Three-Horizons-Kurven (Sharpe)

x = Zeit, drei überlappende S-Kurven, Felder als Punkte auf ihrer Trajektorie.

- **+** zeigt **Bewegung**, nicht nur Zustand — die stärkste Story für „wir sehen es früher"
- **−** braucht Historie pro Feld; nur mit Option A (stetig) sinnvoll; erklärungsbedürftig

### Layout 4 — Horizont-Bahnen (Lane/Beeswarm)

Drei horizontale Bahnen H1/H2/H3, Punkte weichen innerhalb der Bahn aus,
Labels immer lesbar.

- **+** robusteste Dichte-Behandlung, garantiert lesbar, mobil am besten
- **−** nüchtern, kein Radar-Wiedererkennungswert

**Empfehlung:** **Layout 2 als Arbeitsansicht**, **Layout 1 als Präsentations-/
Exportansicht** aus derselben Datenstruktur. Layout 3 später, wenn Zeitreihen pro
Feld stehen.

---

## 5. Trendkarten-Icon

**Wichtige Einschränkung zuerst:** Ein einzelner Trend *ist* kein
Technologiefeld. Ein Horizont-Badge auf einer Trendkarte muss vom **Feld bzw.
Cluster** erben, dem der Trend zugeordnet ist — und das auch sagen, sonst ist es
falsche Präzision.

- **Variante i — Text-Badge:** `H2` klein in Mono, neben den PESTEL-Badges. Billigst, sofort lesbar, keine Legende nötig.
- **Variante ii — Drei-Ring-Glyph:** 12-px-SVG, der zutreffende Ring gefüllt. Schön, aber ohne Legende nicht selbsterklärend.
- **Variante iii — Profil-Punkte (Empfehlung):** drei winzige Punkte für Technologie/Regulatorik/Markt, je nach Horizont gefüllt/hohl, Tooltip mit Klartext. Transportiert genau die Mehrdimensionalität, die den Ansatz ausmacht.

Sinnvoll nur, wenn der Trend in einem definierten Feld liegt; sonst kein Badge
(statt „unbekannt"-Rauschen auf jeder Karte).

---

## 6. Datenlücken, die vor der Umsetzung zu schließen sind

1. **Region-Normalisierung fehlt.** Rohwerte sind uneinheitlich: `global` vs. `Global`, `EU` vs. `Europe` vs. `Germany`/`Belgium`, `US` vs. `United States` vs. `Wisconsin`. Braucht eine Jurisdiktions-Mapping-Tabelle (Land → Jurisdiktion → Region), sonst zersplittern die Zellen.
2. **Regulatorik-Sub-Typ fehlt** (Konsultation/Entwurf vs. Zulassung erteilt) — die H2/H1-Grenze der wichtigsten Dimension. Anreicherung nötig.
3. **`trend_level` ist wertlos:** im Test-Scope **100 % `micro`** (1.414/1.414). Als Horizont-Signal nicht verwendbar, obwohl die Taxonomie es suggeriert.
4. **Scope-Präzision:** ein Keyword-Scope `%fermentation%` fängt traditionelle Fermentation, Silage- und Futtermittelzusätze (EFSA-Dokumente) mit ein. Der Scope muss über Embeddings laufen **und vom Nutzer verfeinerbar sein** (wie die CPC-Checkboxen im Technologie-Tool) — sonst ist die Einordnung sauber gerechnet, aber auf der falschen Menge.
5. **Kein Cron für Snapshots** (siehe 1.6) — muss mit der Umsetzung eingerichtet werden, sonst ist das neue Radar in zwei Wochen so alt wie das alte.
6. **Patent-Signale im Trend-Korpus sind dünn** (12 im Test-Scope). Die Technologie-Dimension muss den Patent-**Graphen** anzapfen (Option D), nicht die Patent-Trends.


---

## 7. Umsetzung, Stand 2026-07-30

### 7.1 Was gebaut ist

| Baustein | Ort |
|---|---|
| Horizont-Engine (Jurisdiktions-Normalisierung, Regulatorik-Sub-Typen, Gates, Kopplung) | `pipeline/radar_horizons.py` |
| Referenz-Radar „Alternative Proteine", 8 Felder | `pipeline/radar_seed.py` |
| Tabellen `radar_configs / radar_scopes / radar_runs / radar_cells / radar_scope_trends` | `radar_horizons.SCHEMA` |
| Read-Layer (server) + client-sichere Typen/Labels | `frontend/src/lib/radar.ts`, `radar-shared.ts` |
| Matrix- und Polar-Ansicht mit geteiltem Readout | `frontend/src/components/foresight/HorizonBoard.tsx` |
| Profil-Punkte auf Trendkarten + Batch-Lookup | `frontend/src/components/HorizonDots.tsx`, `radar.getTrendHorizonsBatch` |
| Seite (Horizont-Radar Standard, altes Radar unter `?view=evidence`) | `frontend/src/app/trends/foresight/radar/page.tsx` |
| Neuberechnung im Cron (GPU-frei, ~25 s, nach dem Full Cycle) | `scripts/full_cycle_cron.sh` |
| Regressionstests der Kalibrierfälle | `tests/test_radar_horizons.py` (36 Tests) |

Ergebnis des Referenz-Radars: **128 Zellen, 78 eingeordnet (60 %), 50 bewusst
„unbekannt"**. Die Zielzeile reproduziert die Owner-Hypothese:

| Precision Fermentation | Technologie | Regulatorik | Markt |
|---|---|---|---|
| US | H2 | **H1** (8 Zulassungen seit 2022) | **H1** (29 Produktstarts, 3 mit Handelsbezug) |
| EU | H2 | **H3** (keine Zulassung, 4 Konsultations-/Reformsignale) | **H3** (auf H3 gekoppelt) |
| IL | H2 | **H1** (2 Zulassungen seit 2023) | **H1** (6 Produktstarts) |

### 7.2 Drei Fehler, die erst der Kalibrierlauf sichtbar machte

Der erste Lauf setzte **alle** Zellen auf H1 — plausibel aussehend und falsch.
Aufgedeckt hat das ausschließlich das Domänenwissen des Owners („in der EU gibt
es keine Zulassung"). Die Ursachen sind grundsätzlich und in Tests fixiert:

1. **`regions` ist nicht die zulassende Jurisdiktion.** „Vivici Secures FDA ‚No
   Questions' Letter" trägt `regions=[EU]`, weil Vivici niederländisch ist —
   belegt aber eine **US**-Zulassung. Ohne Korrektur wandert eine US-Freigabe in
   die EU-Zelle und macht ein blockiertes Feld handlungsfähig. **Fix:** für
   `granted` zählt nur die im Text genannte **Behörde** (FDA→US, EFSA→EU …),
   ergänzt um die explizite Jurisdiktionsnennung („Approval In Israel").
2. **Ein Tag ist kein Beweis.** „Precision Fermentation Leaders In Europe Form A
   Coalition **To Advance** Regulatory Approval" trägt den Tag
   `regulatory_approval`, sagt aber das Gegenteil: es gibt keine Zulassung,
   deshalb wird für eine geworben. **Fix:** Absichts-Guard (`REG_INTENT`) — der
   Text muss die Zulassung bestätigen, nicht anstreben.
3. **Der Patentanker traf das Produktfeld, nicht das Verfahren.** Precision
   Fermentation verankerte auf **A23C („Dairy Products")** mit Markt-Takeoff 2021
   aus *traditioneller* Milchwirtschaft → „technologisch etabliert". Ein
   Kategorienfehler. **Fix:** der CPC-Weg gilt nur bei `reliable=1` (18 von 681
   Klassen), und der Signalmix-Fallback ist **hart auf H2 gedeckelt**, weil aus
   Signalen keine Skalen- und Kostenreife ablesbar ist.

Dazu zwei Struktur-Erkenntnisse:

4. **Markt an Zulassung koppeln.** In regulierten Domänen kann der Markt nicht
   reifer sein als die Zulassung — ohne Genehmigung gibt es keinen zulässigen
   Markt. Das ist die kausale Aussage hinter dem EU-Beispiel und fängt zugleich
   Produktsignale ab, die Auslandsstarts europäischer Firmen betreffen
   (`couple_market_to_regulation`, aktiv über `radar_configs.regulated`).
5. **Anwesenheit und Abwesenheit brauchen verschiedene Schwellen.** Eine einzige
   behördliche Zulassung belegt H1 für sich. Nur die *Abwesenheits*-Schlüsse
   (H2/H3) brauchen eine Mindest-Evidenz, weil dort aus fehlenden Signalen etwas
   gefolgert wird.

### 7.3 Offene Kalibrierpunkte (Owner-Review)

- **Unregulierte Felder brauchen kein Zulassungs-Gate.** `plant-based-meat` steht
  regulatorisch auf H3, weil keine Zulassungssignale existieren — für Plant-Based
  ist aber **keine** Zulassung erforderlich. „Keine Zulassung nötig" ≠
  „blockiert". Nötig: ein Feld-Flag `requires_approval`, das die Dimension sonst
  auf „nicht zutreffend" stellt.
- **Zulassungen sind anwendungsspezifisch.** Cultivated Meat steht in der EU auf
  H1 wegen „Bene Meat Technologies Receives First-Ever EU Approval for Cultivated
  Meat **for Pet Food**" — korrekt, aber für Humanlebensmittel irreführend. Die
  Evidenz macht es prüfbar; die Trennung Human/Tierfutter ist eine Verfeinerung.
- **Scope-Präzision.** Die Terme sind handkuratiert; `%mycelial%` oder
  `%microalgae%` fangen Randfälle. Ein Embedding-basierter Scope mit
  Nutzer-Verfeinerung (wie die CPC-Checkboxen im Technologie-Tool) ist der
  nächste Ausbauschritt.
- **Analyst-Override (Option E)** ist im Schema angelegt
  (`radar_cells.override_horizon` / `override_note`, im Frontend als ✎ markiert),
  hat aber noch keine Bedien-Oberfläche.
- **PESTEL-Radar:** die Engine ist dimensionsagnostisch; ein zweites
  `dimension_set='pestel'` braucht nur PESTEL-Zellenfunktionen, keine neue
  Architektur.

### 7.4 Kalibrierung 2026-08-02: der Lithium-Ionen-Fund (Owner)

**Befund:** „Lithium Ion Battery" landete fast durchgängig auf H3/H2, obwohl die
Technologie längst diffundiert ist. Drei Ursachen, alle struktureller Natur:

1. **News messen Veränderung, nicht Zustand.** Der Signalmix im 36-Monats-Fenster
   liest reife Technik systematisch als unreif: laufende Forschung (Feststoff-
   Elektrolyte, Silizium-Anoden) färbt den Mix forschungsseitig, und niemand
   schreibt 2026 „Verbraucher kaufen jetzt Lithium-Akkus" — das war 1995–2010
   eine Nachricht. **Fix:** Etablierungs-Gate über die kumulative Markt-Historie
   des Scopes selbst: erstes aktives Marktjahr ≥10 Jahre zurück, ≥8 aktive Jahre
   (≥3 Marktsignale), ≥30 Produktstarts über die Historie → Technologie H1
   (`method='market_history'`). Kalibriert an 8 Fällen: die diffundierten
   (Li-Ion 2012, Solar 2011, EV 2010, Wärmepumpen 2012) trennen sich mit 8
   Jahren Abstand von den jungen (Quantum/PF/SSB/Cultivated Meat 2020–2021).
2. **Abwesenheit eines Zulassungsregimes ist keine Blockade.** „Keine Zulassung
   gefunden" ergab H3 („Weg wird erst gebaut") für eine Technologie, die keine
   Zulassung braucht. **Fix:** `cell_regulatory` erhält `regulated`; in
   unregulierten Domänen macht Abwesenheit **kein Urteil**, H3 braucht dort
   positive Gegenwind-Evidenz (Verbote/Blockaden ≥2). Das löst zugleich das in
   §7.3 notierte `requires_approval`-Problem (plant-based-meat).
3. **Adoption H3 neben Markt H1 war inkohärent** — wer kauft sonst die
   gestarteten Produkte? **Fix:** fehlende Verbrauchersignale sind nur dann eine
   H3-Aussage, wenn auch der Markt fehlt; bei etabliertem Markt (H1) schweigt
   die Zelle mit Begründung. Die Kopplung bleibt intakt: ist der Markt auf H3
   gedeckelt (EU-Precision-Fermentation), bleibt Adoption H3.

**Verworfen als Alternative:** CPC-Klassen-Takeoffs breiter zu nutzen. Messung:
H01M meldet Patent-Takeoff „2026" (Frontfile-Artefakt), A23C/A23J Markt-Takeoff
„2021" (die Alt-Protein-Welle selbst); die Anker-Distanz trennt den richtigen
Anker (Li-Ion→H01M, 0,473) nicht vom Kategorienfehler (PF→A23C, 0,462).

Referenz §7.1 nach dem Umbau unverändert; beabsichtigte Änderung: Adoption-
Zellen neben ungekoppeltem H1-Markt sagen jetzt „kein Urteil" statt H3.
