# TIR-Verlässlichkeit: Umsetzungsplan

**Branch:** `feat/tir-reliability` · **Stand:** 2026-07-16 · **Bezug:** #45, #43, [[tir-computation-state]], [[tir-centrality-normalization-method]], [[usp-tir-mit-research]]

## Ausgangslage (belegt)

- Default-Substrat ist `fullz3` (`patent_spnp_full_z3`, z-Score-Null + Age-3-Cap), gebaut aus **eingefrorenen** Staging-Shards vom 2026-07-11 / `full_graph_cache`. Benchmark: **Spearman 0,700 · R² 0,457 · σ²=0,421** gegen 23 selbst-transkribierte Magee-Domänen.
- `patent_links` steht bei **113,58 Mio.** Kanten (Substrate auf 112,0 Mio. gerechnet). Die +1,58 Mio. sind 1,4 %, konzentriert am Rand 2025/26 — den `TRUNC_YEARS=7` (letztes vollständiges Jahr = 2019) ohnehin abschneidet. **→ Neu-Rechnen des Netzwerks allein bewegt die berichteten Werte praktisch nicht.**
- **Neuer Hebel entdeckt:** `/mnt/data-hdd/Domains_patent_info.csv` (348 MB, 30 Domänen, per-Patent) + `performance_time_series.csv` (29 Domänen, echte Performance-Zeitreihen) sind der **originale Singh/Triulzi/Magee-Datensatz**. Spalte `SPNP_count_t3_randomized_zscore_RPbyYear` ist **exakt das X des Papers** — das, was `fullz3` nachbaut. Bisher völlig ungenutzt.

## Ziel

TIR **absolut** verlässlicher machen (der einzige verbleibende große Vorbehalt aus #45) und das Substrat vom eingefrorenen Snapshot in einen wartbaren Zustand bringen — ohne das freigegebene Frontend-Verhalten (#36) zu brechen.

## Nicht-Ziele

- Kein Umbau der Trajectory-UX (freigegeben, #36).
- Keine Default-Substrat-Umschaltung ohne Owner-Freigabe (product-facing, wie schon bei fullz3).
- Kein multilingualer Korpus (#27), kein OpenAlex (#9/#51) — separate Stränge.

---

## Workstream 1 — Kalibrierung gegen den echten MIT-Datensatz *(größter Hebel, keine neuen Patentdaten)*

**Warum zuerst:** Hebt die *absolute* Genauigkeit (R²=0,457 heute) und macht den USP „basiert auf aktueller MIT-Forschung" **belegbar statt nur zitierbar** — Ehrlichkeits-Gate aus [[usp-tir-mit-research]]. Reine CPU/Numpy-Arbeit, Stunden nicht Tage, kein GPU, kein Rebuild nötig.

### 1a. Ground-Truth-K je Domäne herleiten
- `performance_time_series.csv` einlesen → pro der 29 Domänen ein exponentieller Fit `log(perf) ~ Jahr`, Steigung = wahres K. Das ersetzt unsere 23 handübertragenen Magee-Raten durch **die Zielgröße, gegen die das Paper selbst kalibriert**.
- Deliverable: `scripts/mit_ground_truth.py` → Tabelle/CSV `domain, K_true, n_years, r2_fit`.

### 1b. Unser SPNP patentgenau gegen MIT validieren
- Join `Domains_patent_info.patent_number` ↔ unsere `patent_spnp_full*` (US-Grant-Pub-Numbers normalisieren, Format `US-XXXXXXX-B2`).
- Vergleich unser `spnp_pctl` vs. MIT `SPNP_count_t3_randomized_zscore_RPbyYear` **pro Patent**: Spearman + Bland-Altman. Deckt auf, ob unsere Normalisierung driftet (offener Punkt in [[tir-centrality-normalization-method]]) — und **auf welchem Substrat** (`full`/`fullz`/`fullz3`) sie am nächsten an MIT liegt.
- Deliverable: `scripts/validate_spnp_vs_mit.py` → Report je Substrat.

### 1c. Neu kalibrieren gegen echte Domänen-Mitgliedschaft
- `recalibrate_full.py` erweitern: statt CPC-Muster-Proxy die **MIT-eigenen patent_number-Sets** als Domänen-Scope nutzen (entfernt die CPC-Mapping-Fehlerquelle komplett). X = Mittel unseres `spnp_pctl` über die echten Domänen-Patente; Ziel = K_true aus 1a.
- Refit `ln(K)=a+b·X` je Substrat; das Substrat mit bestem Out-of-Sample (LOO-CV Spearman/R²) gewinnt.
- Deliverable: neue `_CALIB[...]`-Koeffizienten + CV-Report. **Akzeptanz:** R² > 0,457 **und** patent-level Spearman vs MIT (1b) ≥ 0,7 auf dem gewählten Substrat.

### 1d. Entscheidung Default-Substrat + Koeffizienten
- Evidenz-Paket an Owner (wie #45): welcher Substrat+Fit, was gewinnt/verliert (Trajectory-Spot-Check gegen die alten Referenzdomänen aus [[tir-computation-state]]: Batterie/Halbleiter/Käse/F16B).
- **Owner-Gate.** Erst nach Freigabe `SUBSTRATE`-Default / `_CALIB` in `tir_trajectory.py` ändern.

### 1e. Prädiktor-Experiment: *zitierte* vs. eigene Zentralität — ✅ ENTSCHIEDEN (2026-07-18, `scripts/mit_calibrate.py`)
**Befund bestätigt am ORIGINAL-MIT-Datensatz** (29 Domänen, K_true aus `performance_time_series.csv`, X aus `Domains_patent_info.csv`):

| Prädiktor | R² | Spearman | LOO-R² (OOS) |
|---|---|---|---|
| A — eigene Zentralität (`SPNP_count_t3`, unser aktueller) | 0,549 | 0,788 | 0,489 |
| **B — zitierte Zentralität (`meanSPNPcited`, Patent-kanonisch)** | **0,621** | **0,831** | **0,557** |

**B schlägt A durchgängig** und reproduziert den publizierten Paper-Wert (r≈0,80). Unsere A-Koeffizienten (a=−5,10/b=6,23) liegen fast exakt auf dem Paper K=e^(6,16·X−5,02) → Pipeline liest MIT korrekt.
- **Umsetzung + NEGATIV-BEFUND (2026-07-18):** cited-Zentralität live zu teuer (18s/Domäne) → einmal vorberechnet in `patent_citedspnp_full_z3` (8,25M Patente, `scripts/build_cited_spnp.py`). **ABER:** Auf UNSEREM Substrat kalibriert dieser naive cited-Prädiktor (Mittel der `spnp_pctl` ALLER zitierten Patente) **schlechter** als own (BENCH: R²=0,28/Spearman=0,57 vs own ~0,46/0,70). **→ NICHT umgeschaltet** (würde verschlechtern). Grund: Der MIT-Vorteil hängt an der exakten Konstruktion `meanSPNPcited_1year_before` (Zentralität der zitierten Patente gemessen **1 Jahr VOR** dem zitierenden Patent, US-only-Graph) — unser „Mittel aller zitierten pctl" bildet das nicht ab (kein temporaler Snapshot, globaler Graph verdünnt).
- **Nächster Schritt, um den MIT-Vorteil zu heben:** (a) sauberer Test gegen die EXAKTEN MIT-K_true über MIT-`patent_number`-Sets auf unserem Substrat (statt BENCH-Proxy — der könnte die Rauschquelle sein); (b) falls cited weiter verliert: temporale „1-Jahr-vor"-Konstruktion nachbauen (braucht cited-Zentralität zum Zitationszeitpunkt, nicht den finalen t+3-Wert). Precompute-Tabelle + `mit_calibrate.py` bleiben als Basis. Der MIT-Befund (cited>own) bleibt wissenschaftlich gültig — nur unsere Umsetzung trägt ihn noch nicht.

### 1f. Weitere kanonische Parameter aus dem Patent-Volltext *(NEU)*
- **Randomisierungen R=1000** statt 100 für das Produktions-`_z3` (Patent nennt 1000 als kanonisch; #45 hatte es als Option). Stabilere z-Scores, adressiert die Optik/Wireless-Kompression.
- **t+3 bestätigt** — unser Age-3-Cap ist exakt die MIT-Wahl (grant+3). ✅ keine Änderung nötig, aber jetzt belegbar.
- **Domänen-Qualitäts-Filter (optional):** MIT verwirft Klassen-Overlaps unter der **Zufallserwartung** (Signifikanztest), nicht nur < n. Idee für unsere Ad-hoc-CPC-Domänen als Rausch-Schutz.
- **Validierungs-Messlatten:** r=0,80 / R²=0,64 (kreuzschnittlich), 0,72 OOS post-1990 — als Zielwerte in 1c/1d führen.

### 1g. Literatur-Anschluss *(NEU — Zitations-Hülle in `docs/tir_literature/`)*
Weiterentwicklungen, die WS1/WS2 informieren (Volltexte OA in `/mnt/data-hdd/tir_literature/pdfs`):
- **Jiang & Luo 2021** (deep neural embeddings über die 1757 Domänen + Rates) — Blaupause für unser Embedding-Domänen-Scoping.
- **Rezazadegan et al. 2024** (TIR für AI-Subdomänen via Zentralität) — feine Subdomänen (#43).
- **Ho et al. 2025** (Multilayer: Patente+Publikationen+Trials+Markt) — Multi-Source-Layer (#9).
- **Lai et al. 2026** („effects of prediction time points") — vor WS2b (Truncation) lesen.
- **Park et al. 2025 / Sarica & Luo 2023** (Declining Disruptiveness = Datenartefakt durch Null-Zitat-Werke) — bestätigt unseren Kompositions-Drift-Befund, liefert Korrekturmethodik.
- **Fronzetti Colladon 2025** (Composite-Zentralität Katz/Degree/Betweenness + Text-Mining) — SPNP allein ist nicht mehr State-of-the-Art; mit Embeddings+breiterem Korpus potenziell vor GetFocus/TechNext.

---

## Workstream 2 — Truncation-Frontier *(der eigentliche Verlässlichkeits-Frontier am „Jetzt")*

**Warum:** Ein Foresight-Tool wird an der Aussage über *jetzt* gemessen; heute ist verlässlich nur ≤2019 (`TRUNC_YEARS=7`). Das ist die tiefste Grenze — und **kein Datenvolumen-Problem**, sondern ein Methodenproblem (Forward-Zitat-Reifung).

### 2a. Age-Cap-Kohortierung ausreizen
- `fullz3` nutzt Age-3. Prüfen, wie nah an heute berichtet werden **darf**, wenn Zentralität konsequent bei `grant+N` gemessen wird (Kohorten bei fixem Alter vergleichbar → jüngere Jahre werden berichtbar statt ausgegraut). Kandidaten N∈{2,3,5} — MIT liefert `SPNP_count_t2/t3/t5/t8_...` als Referenz, wie weit man gehen kann.
- **Akzeptanz:** letztes verlässliches Jahr rückt nachweisbar näher an heute, ohne dass mundane Domänen (F16B/B23C) fälschlich „beschleunigen".

### 2b. Truncation-Flag datengetrieben statt Konstante
- `TRUNC_YEARS=7` durch ein **substrat-/domänen-gemessenes** Reifungshorizont-Kriterium ersetzen (ab wann stabilisiert sich der mittlere Perzentil-Rang der Kohorte?), abgeleitet aus 2a. Konservativ, mit Ehrlichkeits-Ausgrauung wie bisher.
- **Nur** vorschlagen, wenn 2a einen echten Gewinn zeigt; sonst dokumentieren, dass 7 der ehrliche Horizont bleibt.

---

## Workstream 3 — Lebendiges Substrat *(Hygiene-Voraussetzung; hier gehört „inkl. neuer Kanten neu rechnen" hin)*

**Warum:** Das Substrat ist ein Snapshot vom 2026-07-11 und veraltet still. Aktuell **kann** es nicht wachsen — `catchup_bdds.py` verwirft die Downloads (`/tmp`, kein `--keep-files`), kein Pfad führt ins Staging. Ohne diesen Fix ist jeder künftige Rebuild ein No-op.

### 3a. Staging-Leak schließen (Voraussetzung)
- `catchup_bdds.py`: `--keep-files --scratch /mnt/data-hdd/bdds_frontfile` durchreichen, damit Wochendaten als Zips erhalten bleiben. Cron (`weekly_patents.sh`, #50) entsprechend.
- **Akzeptanz:** nach einem Wochenlauf liegen die Zips auf der HDD und `parse_patents_to_staging.py` (resumable) erzeugt daraus neue `nodes-/edges-`Shards.

### 3b. Substrat-Rebuild-Kadenz definieren
- Skript, das Front-File-Shards ins Staging parst → SPNP (`spnp_from_staging.py`, Graph-Cache-Reuse) → CPC → Rekalibrierung (WS1-Pipeline), als **ein** reproduzierbarer Lauf. Quartalsweise oder bei ≥X % Kantenwachstum.
- **Realismus-Hinweis im Doc:** Ein Rebuild verschiebt den Truncation-Horizont **nicht** (das leistet nur WS2 + Jahre akkumulierter Zitate). Der Wert von WS3 ist Währung/Reproduzierbarkeit, nicht Sofort-Genauigkeit.
- **Erst dann** lohnt „Netzwerk inkl. der 113,58 Mio. Kanten neu rechnen" — als Teil dieser Kadenz, nicht als Einzelaktion.

---

## Reihenfolge & Abhängigkeiten

```
WS1 (Kalibrierung)  ──► liefert Rekalibrier-Pipeline + Substrat-Entscheidung
   │                     (nutzt vorhandene Substrate, kein Rebuild)
   ├──► WS2 (Truncation) baut auf 1b/1c auf (MIT t2/t3/t5 als Referenz)
   └──► WS3 (Substrat)   nutzt WS1-Rekalibrierung als letzten Schritt jedes Rebuilds
WS3a (Leak-Fix) kann sofort parallel — reine Ops, blockiert nichts, verhindert weiteren Datenverlust
```

**Empfohlener Start:** WS3a (5-Zeilen-Ops-Fix, stoppt die wachsende Lücke) **parallel** zu WS1a–1c (der echte Genauigkeitsgewinn). WS1d + WS2 nach Owner-Gate.

## Risiken

- **MIT-Pub-Number-Matching:** ihre `patent_number` ist US-Grant-ID ohne Kind-Code; unser Node-Set ist `US-…-B2`. Matching-Quote in 1b messen, bevor 1c darauf baut (Fallback: `patent_spnp_usgrant`, das ist der US-Grant-Subgraph).
- **Substrat-Wechsel ist product-facing:** strikt hinter Owner-Gate (WS1d), inkl. Trajectory-Spot-Checks gegen die freigegebenen Referenzformen.
- **HDD-Platz:** Front-File-Zips + neue Shards — vor 3b `df -h /mnt/data-hdd` prüfen.

## Rollback

Alle Substrate sind env-gated (`TIR_SUBSTRATE`); Koeffizienten in `_CALIB`. Kein Schritt löscht bestehende Tabellen (neue `--out-table`). Default-Umschaltung ist eine einzelne Zeile, revertierbar.

## Offene Owner-Entscheidungen

1. Default-Substrat nach WS1 wechseln — ja/nein (Evidenz kommt aus 1d).
2. Truncation-Horizont datengetrieben lockern (WS2b) — nur falls 2a Gewinn zeigt.
3. Rebuild-Kadenz (WS3b): Quartal vs. Schwellenwert.
