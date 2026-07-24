# TIR-Methodenvergleich: MIT (Singh/Triulzi/Magee) vs. Catandary — inkl. 1757er-Abgleich

Stand: 2026-07-24. Erstellt aus einer Multi-Agenten-Analyse (5 Quellen-Reader, Synthese,
10 adversariell verifizierte Kernaussagen) plus quantitativem Erst-Abgleich gegen den
Forscher-Datensatz. Quellen: Paper-PDFs in `/mnt/data-hdd/shared_tir_research/`,
Forscher-Notebooks (github.com/GiorgioTriulzi/TechnologyPerformanceImprovementEstimates),
Forscher-Datendrop `/mnt/data-hdd/` (30 Kalibrierdomänen, 2026-07-12) und die
1757-Domänen-Prognosen (`Technology_improvement_rates_for_all_technologies_Singh_Triulzi_Magee_May6.csv`,
= Zenodo 10.5281/zenodo.4779831, erhalten 2026-07-24).

---

## 1. Die MIT-Methode (Papers + Original-Notebooks)

**Pipeline (Singh/Triulzi/Magee 2021, Research Policy; Basis: Triulzi/Alstott/Magee 2020 TFSC):**

1. **Korpus:** 5.083.263 US-Utility-Patente, Grant 1976–06/2015, PatentsView; Nicht-Utility
   (D/PP/H/RE/T) entfernt.
2. **Domänen (COM invertiert):** Alle UPC-3-digit × IPC-4-char Klassenpaare (284.472),
   Overlap gegen Zufallserwartung getestet, Patent → größter Overlap (Dedup, jedes Patent
   in genau 1 Domäne), ≥100 Patente → **1757 Domänen** = 97,2 % des US-Systems. CPC kommt
   in keinem der Papers vor.
3. **SPNP-Zentralität** (Hummon/Doreian 1989, Batagelj 2003): SPNP(v) = (incoming paths+1)
   ·(outgoing paths+1), gemessen **3 Jahre nach Grant** (t+3).
4. **Normalisierung:** 1000 randomisierte Netzwerke (Edge-Swaps, erhalten: In-/Out-Grad,
   Zitationsalter-Profil, Haupt-USPC-Klassen-Anteil) → z-Score → **Rank-Perzentil je
   Grant-Jahr**. Code: github.com/jeffalstott/patent_centralities (nicht in den Notebooks).
5. **Prädiktor & Regression:** Domänen-Mittel X_i (ungewichtet, alle Domänen-Patente
   1976–2015, kein Zeitfenster) → OLS über die 30 empirisch vermessenen Domänen:
   - Paper Gl. 5 (own-Prädiktor, Basis der 1757 Prognosen): **K̂ = e^(6.22·X − 4.97)·e^(σ²/2)**
   - Paper Gl. 13 / Notebooks (cited-Prädiktor `meanSPNPcited_1year_before_randomized_zscore_RPbyYear`):
     6.15987/−5.01885. Own/cited korrelieren auf Domänen-Ebene mit 0,97.
   - Notebooks: `smf.ols('log_K ~ X')`, HC1-robuste SEs (Suffix `_HSR` =
     „heteroskedasticity-robust" — daher die CSV-Spalte `predicted_log_K_HSR`),
     Rücktransformation mit Smearing `·e^(σ²/2)` (erklärt den ~21–29-%-Aufschlag von
     `Predicted K` über `exp(log_K_HSR)` in der CSV).
6. **Zeitmodell:** **Ein statischer K-Wert je Domäne**, per Generalized-Moore's-Law-Annahme
   zeitkonstant. Keine Fensterung, keine Richtungsaussagen. Triulzi 2020 warnt explizit:
   „short term TIRs are not reliably estimated".
7. **K_true (Ground Truth):** ln(Performance)-OLS-Steigung aus kuratierten
   Performance-Zeitreihen (Magee et al. 2016 / Benson&Magee 2015; 28→30 Domänen).
   Wird in den Notebooks fertig geliefert (`PERFORMANCE_DOMAINS_K_Kr2.csv`), nicht gefittet.
8. **Validierung:** MCCV je Stichjahr 1980–2013 (50/50-Domänen-Splits, 100 Iterationen,
   ≥100-Patente-Gate; Test-Korrelation ~0,72 ab den 1990ern), LOO-Bootstrap
   (63 % innerhalb ±10 pp, 87 % innerhalb ±15 pp). Entropie- und Obsoleszenz-Indizes
   waren Kandidaten-Prädiktoren und **verloren** gegen die SPNP-cited-Zentralität.
9. **Notebook-Detail:** Der „faster than"-Paarvergleich addiert Standardabweichungen statt
   Varianzen (konservativ; weicht von der im Kommentar zitierten Statistik-Referenz ab).

## 2. Die Catandary-Methode (aktiver Prod-Pfad)

`scripts/tir_trajectory.py` (Substrat-Default `fullz3`, Prädiktor-Default `cited` seit
`e0f462c`, 2026-07-18):

1. **Korpus:** Weltweites DOCDB/BDDS-Archiv, alle Länder/Kind-Codes, kein Sprachfilter;
   Graph 42,58 Mio. Knoten / 145,5 Mio. Kanten, Jahre 1784–2026 (Snapshot 2026-07-11).
   Publikationsjahr als Grant-Jahr-Proxy; Same-Year-Kanten für DAG-Erzwingung verworfen.
2. **Domänen:** CPC-LIKE-Pattern-Mengen (fein, kuratiert/embedding-gestützt) — explizit
   als Proxy für die COM-Sets markiert (`calibrate_tir.py:15–17`).
3. **SPNP:** identische Definition, Log-Space-Implementierung (segment-logsumexp);
   t+3 als **Age-3-Forward-Cap** (`--age-cap 3`).
4. **Normalisierung:** **R=100** Randomisierungen (statt 1000), Klassen-Erhalt über
   **CPC-3-Zeichen-Präfix** (statt Haupt-USPC), Bucket-Permutation äquivalent zu den
   Paper-Swap-Constraints → z-Score → Jahres-Perzentil (`spnp_from_staging.py:177–210`).
   Legacy-Substrate `db`/`full` nutzen stattdessen eine Degree-OLS-Regression (bricht am
   Voll-Graph, CRISPR flach) — `db` ist noch im Endpoint `/api/foresight/tir` aktiv.
5. **Prädiktor:** `cited` = Mittel der Perzentile der zitierten Patente, aber als
   **age-3-gecappter Endwert** statt MITs t−1-Snapshot (dokumentierte Approximation,
   `docs/tir_cited_predictor.md:41–43`).
6. **Kalibrierung:** Eigener Refit gegen die **exakten MIT-Patent-Sets + exakte K_true**
   (`mit_calibrate_substrate.py`, 511.506 (Domäne,Patent)-Zeilen aus dem Datendrop,
   effektiv n=29 — MAGNETIC_MAT hat keine Zeitreihe):
   **K̂ = e^(−5.5622 + 5.5036·X)·e^(0.4930/2)** — R²=0,574 / Spearman 0,764 / LOO-R²=0,516
   (cited schlägt own 0,521/0,712/0,459). Koeffizienten sind bewusst substratgebunden:
   unser X darf nie in die MIT-Formel, und umgekehrt.
7. **Catandary-Erweiterungen ohne MIT-Gegenstück:** rollierende K(t)-Kurve (5-J.-Fenster),
   Richtungsklassifikation ACCEL/MATURE/DECEL mit re-zentrierten Bändern, Dichte-Gates
   (MIN_N=100/Fenster, DOMAIN_MIN_TOTAL=500, Richtungs-Gate Median-n≥1000),
   TRUNC=7 → letztes vollständiges Jahr 2019, CALIB_MAX=50 %/yr (Absolutwert-Withhold),
   4-Tier-Richtungs-Kontrollgruppe (10/11 mit cited).

## 3. Gemeinsamkeiten (bewusst übernommen)

1. Zielgröße K = jährliche exponentielle Verbesserungsrate (ln-Steigung, GML).
2. Identische SPNP-Definition inkl. +1-Termen.
3. t+3-Messfenster (als Age-3-Cap).
4. Nullmodell-Architektur: grad-/alters-/klassen-erhaltende Randomisierung → z-Score →
   Jahres-Perzentil.
5. cited-Prädiktor = Gewinner-Prädiktor aus Triulzi 2020, bei uns zusätzlich auf dem
   eigenen Substrat empirisch bestätigt.
6. Log-lineare Kalibrierform mit Smearing-Korrektur.
7. Ground-Truth-Bindung an dieselben MIT-Performance-Zeitreihen, seit dem Datendrop auf
   den exakten MIT-Patent-Sets.
8. Ungewichtete Patent-Mittelung je Domäne.

## 4. Unterschiede

| Dimension | MIT | Catandary | Bewertung |
|---|---|---|---|
| Korpus | 5,08 M US-Utility 1976–2015 | 42,6 M weltweit 1784–2026 | **bedeutungsverändernd** (andere Normalisierungs-Population; s. Abgleich §7) |
| Domänen | COM UPC×IPC (1757, disjunkt, Rausch-Test) | CPC-LIKE-Patterns (Proxy) | **bedeutungsverändernd** (andere Patent-Sets; Proxy-R² 0,42–0,46 vs. 0,521 exakte Sets bei own) |
| SPNP-Numerik | Batagelj auf Zählwerten | Log-Space (logsumexp) | harmlos |
| Randomisierungen | R=1000 | R=100 | harmlos (mehr z-Score-Rauschen, mittelt sich) |
| Klassen-Erhalt im Nullmodell | Haupt-USPC | CPC-3-Präfix | klein, unquantifiziert |
| Prädiktor (Prognosen) | own@t+3 (Gl. 5) | cited@age-3-Endwert | Wahl harmlos (r=0,97), Snapshot-Abweichung echte Approximation |
| Koeffizienten | 6.22/−4.97 | −5.5622/5.5036 (Refit) | notwendig & korrekt (andere X-Skala) |
| Zeitmodell | statisch, zeitkonstant | K(t) + Richtung + K_recent | **eigenständiges Catandary-Produkt**, außerhalb der MIT-Validierung |
| Gates | ≥100 Patente | MIN_N/DOMAIN_MIN_TOTAL/Richtungs-Gate/CALIB_MAX/TRUNC | Catandary-Ehrlichkeitsschicht |
| Validierung | MCCV ~0,72, LOO ±10–15 pp | LOO-R² 0,516 (n=29), Kontrollgruppe 10/11 | etwas schwächer, kein MCCV/Bootstrap |

**Vergleichbar mit MIT ist am ehesten K_median über die volle Historie auf exakten oder gut
approximierten Domänen-Sets. K_recent, K(t) und Richtungslabels sind Catandary-Konstrukte
auf MIT-Fundament und dürfen nicht als „MIT-Zahl" kommuniziert werden.**

## 5. Verifikationsstand der Kernaussagen

10 Kernaussagen adversariell geprüft (Workflow 2026-07-24): **K1–K9 CONFIRMED**, K10
REFUTED (der behauptete „1757er-Abgleich-Blocker" — die CSV traf während der Analyse ein).
Wesentliche Präzisierungen aus der Verifikation:

- K2: Der reine Set-Effekt (CPC-Proxy vs. exakte MIT-Sets) ist 0,42–0,46 vs. **0,521**
  (gleicher own-Prädiktor); 0,574 enthält zusätzlich den own→cited-Wechsel.
- K6: Beispiel-Korrektur — der cpc_insights-Snapshot für KI (G06N) zeigt `tir_pct=None`
  (`above_calibrated_range`), nicht 69,8; korrektes Divergenz-Beispiel ist H01M
  (Snapshot 10,1 vs. own-Referenz 11,7 vs. live cited 8,6 %/yr).
- **Doku-Drift (offen, fixen):** `docs/tir_cited_predictor.md:3` („Default own") und
  Kommentar `tir_trajectory.py:74–75` sind stale — Code-Default ist seit `e0f462c` `cited`.
  Memory `ws1-cited-predictor` entsprechend aktualisiert.
- **Drei parallel kursierende TIR-Zahlen im Produkt:** live fullz3+cited,
  `cpc_insights`-Snapshots 2026-07-06 (full+own), `/api/foresight/tir` (db+own, alte
  Koeffizienten). Deployment-, kein Methodenproblem — konsolidieren.

## 6. Forscher-Datenlage (lokal)

- `/mnt/data-hdd/Domains_patent_info.csv` — 511.506 (Domäne,Patent)-Zeilen
  (497.021 distinkte Patente), 30 Kalibrierdomänen, 54 Variablen inkl. beider Prädiktoren.
- `/mnt/data-hdd/performance_time_series.csv` — K_true-Basis, 29 Domänen.
- `/mnt/data-hdd/DF_means_*.xlsx` + Variable Dictionaries.
- `/mnt/data-hdd/shared_tir_research/Technology_improvement_rates_..._May6.csv` —
  **die 1757 Prognosen** (Spalten: Domain Code UPC-IPC, Predicted K %/a, predicted_log_K_HSR,
  Domain Size; K-Spanne 2–216 %/a, Σ Size 4,94 M).
- Fehlt lokal: `All_patents_info.csv` (patent-level Zentralitäten des Voll-Korpus) —
  öffentlich auf Mendeley Data (doi:10.17632/f4fj887y67.1), bei Bedarf ziehen.
- Original-Code: github.com/GiorgioTriulzi/TechnologyPerformanceImprovementEstimates
  (4 Notebooks) + github.com/jeffalstott/patent_centralities (Normalisierung).

## 7. Quantitativer Erst-Abgleich gegen die 1757 Prognosen (2026-07-24)

**Setup:** MIT-Domänen-Codes (UPC×IPC4) auf ihren IPC4-Teil aggregiert (größen-gewichtetes
geometrisches Mittel von K; 1757 Domänen → 544 IPC4-Subklassen). Unsere Seite: mittlere
`cited_pctl` je CPC4-Subklasse über alle Patente mit Grant-Jahr **1976–2015**
(= MIT-Zeitfenster), aktive Prod-Kalibrierung, Floor n≥500. Skript:
Scratchpad `abgleich_1757.py`; ein SQL-Pass über `patent_cpc_full` (376 M Zeilen).

**Ergebnis:**

| Variante | n Subklassen | Spearman | Pearson (ln K) | Median MIT | Median wir |
|---|---|---|---|---|---|
| **US-only** (korpus-vergleichbar) | 526 | **0,704** | **0,774** | 10,0 %/a | 11,1 %/a |
| Welt (Prod-Definition) | 516 | 0,588 | 0,662 | 10,0 %/a | 6,6 %/a |
| Kombiniert | 539 | 0,668 | 0,759 | 10,0 %/a | 8,6 %/a |

**Interpretation:**

1. **US-only reproduziert das MIT-Ranking mit Spearman 0,70 über 526 Subklassen** — auf
   dem Niveau der MIT-eigenen Out-of-sample-Selbstübereinstimmung (MCCV ~0,72). Das mit
   komplett unabhängiger Datenbasis (DOCDB statt PatentsView), R=100, CPC-Klassen,
   cited@age-3 statt own@t+3 und eigenem Refit. Die Level-Mediane stimmen (11,1 vs. 10,0).
   → Starke externe Validierung des eigenen Substrats (relevant für #33/USP-Ehrlichkeit).
2. **Der Welt-Korpus drückt Ränge und Niveaus** (0,59; Median 6,6) — der im
   Methodenvergleich vorhergesagte Korpus-Effekt ist real und messbar. Die Prod-Zahlen
   auf Weltbasis sind eine eigene Skala, keine MIT-Reproduktion.
3. **Systematische Kompression am oberen Ende:** Software-/Netzwerk-Subklassen
   (G06F 114→40, H04L 95→32, G06Q 121→41, H04W 101→26 %/a) — unser Refit (b=5,50,
   Trainings-K_true max ~47,5 %) extrapoliert flacher als MITs Gl. 5 (b=6,22); genau der
   Bereich, den CALIB_MAX=50 im Produkt ohnehin zurückhält. Rangfolge bleibt konsistent.
4. **Bekannter Artefakt bestätigt:** H01L matcht nur 852 Patente (CPC-Migration
   H01L→H10x, #43) — Halbleiter-Vergleich über `H01L` ist unbrauchbar, Migrations-Mapping
   nötig.

**Grenzen des Erst-Abgleichs:** IPC4-Aggregation verwischt COM-Domänen (~3,2 MIT-Domänen
je IPC4); Vergleich cited-basiert vs. own-basiert; CPC≈IPC nur auf Subklassen-Ebene.

## 7b. Ausbaustufe: Abgleich je COM-Domäne (2026-07-24, Nachtlauf)

**Exakte Domänen-Rekonstruktion:** `All_patents_info.csv` (3,3 GB, Mendeley
doi:10.17632/f4fj887y67.1, jetzt lokal `/mnt/data-hdd/`) liefert USPC-Mainclass +
IPC-Mainclass je Patent → Zuordnung jedes US-Patents zu seinem publizierten
Domain-Code (mainclass×IPC4). Ergebnis: **1751/1757 Domänen besetzt**, 2,82 M
Patente zugeordnet; ln-Size-Korrelation gegen die publizierten Domain Sizes
**0,819**, Median-Size-Ratio 0,724 (Subset erwartbar: wir haben nur die
Hauptklassen-Paare, das Paper nutzte die vollen Klassifikationslisten).

**Abgleich je Domäne** (unser X̄ = cited_pctl, US-Grants 1976–2015, aktive
Prod-Kalibrierung):

| Floor | n Domänen | Spearman | Pearson (ln K) | Median MIT / wir |
|---|---|---|---|---|
| n≥100 | 1299 | 0,675 | 0,772 | 10,0 / 10,97 %/a |
| **n≥500** | 651 | **0,679** | **0,798** | **11,0 / 11,02 %/a** |

Auf echter Domänen-Granularität (2,5× mehr Einheiten als der IPC4-Erstabgleich)
bleibt die Übereinstimmung auf demselben Niveau (Pearson-ln steigt sogar auf
0,80), und die Level-Mediane decken sich fast exakt. Skripte/Daten:
Session-Scratchpad `com_domain_abgleich.py`, `com_abgleich_domains.csv`.

**Surrogat-Qualität CPC-Signaturen (30 Gold-Domänen):** Greedy-F1-Signaturen aus
CPC-Maingroups erreichen nur mediokre Set-Rekonstruktion (F1 Median **0,496**,
Spanne 0,08–0,78) — aber **X̄_gold vs. X̄_signatur korrelieren mit Pearson 0,987**.
Der Domänen-Mittelwert-Prädiktor ist nahezu invariant gegen Set-Rauschen: für den
TIR zählt die richtige Technologie-Nachbarschaft, nicht die exakte Set-Grenze.
Das rechtfertigt den CPC-Pattern-Proxy des Produkts quantitativ.
(Skript `com_signatures.py`, Ergebnis `com_signatures_result.json`.)

## 7c. Patentweiser Normalisierungs-Crosswalk (2026-07-24)

2.974.440 US-Grants patentweise gejoint (unsere fullz3-Perzentile vs. die
publizierten MIT-Normalisierungswerte aus `All_patents_info.csv`):

| Paar | Pearson | Spearman | n |
|---|---|---|---|
| unsere own vs. MIT own@t3 (like-for-like) | 0,509 | 0,537 | 2,73 M |
| unsere cited (age-3-Endwert) vs. MIT cited@t−1 | 0,516 | 0,541 | 2,52 M |
| unsere own vs. MIT own@2015 | 0,228 | 0,238 | 2,94 M |
| **MIT-intern: own@t3 vs. own@2015** | **0,448** | 0,448 | 2,73 M |
| MIT-intern: own@t3 vs. cited@t−1 | 0,752 | 0,752 | 2,54 M |
| wir-intern: own vs. cited | 0,612 | 0,615 | 2,91 M |

**Einordnung:** Patent-Level-Zentralität ist inhärent verrauscht — selbst MITs
eigene zwei Messpunkte (t+3 vs. 2015) korrelieren nur mit 0,448. Unsere 0,51
gegen deren t3-Wert liegt darüber; erst die Domänen-Mittelung erzeugt die
0,68–0,80 aus §7b. Die K5-Approximation (cited@age-3 statt @t−1) kostet
patentweise nichts Messbares. Ära-Stabilität (cited): 1980–84: 0,30 →
1990–94: 0,53 → 2000–04: 0,66 (frühe Jahre = dünnere historische
Zitationsabdeckung im DOCDB). Lineare Übersetzungsfits: MIT_own_t3 =
0,446·X_ours+0,221 bzw. MIT_cited_t1 = 0,672·X_ours+0,071 (resid SD je ~0,25).

**Übersetzungstest (Kompressions-Frage):** Ein linearer Crosswalk lässt die
Domänen-Ränge mathematisch unverändert (linearer Map im Exponenten). Informativ
sind nur die Level: Die Software-Topdomänen erreichen auch in MIT-Skala + MIT-
Gl. 13 nur ~45–47 %/a (MIT publiziert 160–216). **Die High-End-Kompression ist
also kein Artefakt unserer Refit-Steigung, sondern steckt im Top-Tail der
gemessenen X-Verteilung — global-linear nicht behebbar.** Konsequenz: das
CALIB_MAX-Withhold bleibt die ehrliche Behandlung; Alternative wäre eine
Tail-spezifische Kalibrierung (Future Work).

## 7d. CPC-Migrations-Fix H01L→H10x (2026-07-24)

DOCDB reklassifiziert rückwirkend: `H01L%` matcht nur noch 8.978 Zeilen, die
H10-Familie 1,34 M distinct Patente. Fix: `CPC_MIGRATIONS`-Map +
`expand_cpc_patterns()` in `tir_trajectory.py` (greift in allen konsolidierten
Pfaden). Halbleiter-Domäne: **852 → 1.011.919 Patente**, K = 12,4 %/a,
Richtung „steady" statt Migrations-Artefakt. Grenze: Nur Subklassen-Patterns
werden expandiert (keine 1:1-Gruppen-Konkordanz).

## 8. Nächste Schritte

1. ~~Doku-Drift fixen~~ ✓ erledigt 2026-07-24 (`tir_cited_predictor.md`,
   `tir_trajectory.py`-Kommentar, `build_cpc_insights.py:340`).
2. ~~Die drei parallelen TIR-Pfade konsolidieren~~ ✓ erledigt 2026-07-24:
   `tir_for_cpc.py` läuft jetzt über `tir_trajectory.trajectory` (aktive Defaults)
   statt `spnp_centrality.domain_k` (db+own+alte Koeffizienten);
   cpc_insights-Snapshots auf fullz3+cited neu gebaut. Ein Codepfad, eine Zahl.
3. ~~Feiner Abgleich (Domänen-Surrogate statt IPC4)~~ ✓ erledigt 2026-07-24 — §7b.
4. ~~Patentweiser Normalisierungs-Crosswalk~~ ✓ erledigt 2026-07-24 — §7c.
   (2015-Snapshot-Level-Vergleiche weitgehend durch MITs eigene Spaltenpaare
   ersetzbar; echter Snapshot-Build nur bei explizitem Bedarf.)
5. ~~H01L/H10x-Migrations-Mapping (#43-Teilaspekt)~~ ✓ erledigt 2026-07-24 — §7d.
6. R=1000-Build als Genauigkeits-Upgrade erwägen (`tir_reliability_plan.md`) —
   Kosten ~19–22 h Single-Core-CPU für nur √R-Rauschgewinn (Faktor 3,2);
   Crosswalk-Befund (Patent-Level-Rauschen dominiert ohnehin) senkt die Priorität.
7. Tail-/nichtlineare Kalibrierung fürs High-End erforschen (statt CALIB_MAX
   nur zurückzuhalten) — siehe §7c.
