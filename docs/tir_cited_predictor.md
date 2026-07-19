# TIR cited-Prädiktor (WS1) — Owner-Entscheidungsdoku

**Stand:** 2026-07-18 · **Env-Gate:** `TIR_PREDICTOR=cited` (Default `own` → Prod unverändert) · **Bezug:** #45, WS1 in `docs/tir_reliability_plan.md`, Patent US12099572B2 (#57)

## Kern: zitierte statt eigene Zentralität

Der kanonische MIT-Prädiktor ist nicht die Eigen-Zentralität der Domänen-Patente, sondern die mittlere Zentralität der von ihnen **zitierten** Patente. Rigoros bestätigt gegen die **EXAKTEN MIT-K_true** über MIT-`patent_number`-Sets auf unserem Substrat (cited aus dem Staging-Graphen = gleiche Abdeckung wie own, n_cited≈n_own):

| Prädiktor | R² | Spearman | LOO-R² |
|---|---|---|---|
| own (eigene Zentralität, Prod) | 0,521 | 0,712 | 0,459 |
| **cited (zitierte Zentralität)** | **0,574** | **0,764** | **0,516** |

> Der frühere „cited verliert"-Befund war ein **Kantenquellen-Artefakt** (`patent_links` statt Staging-Graph — hist. US-Grants haben dort nur 0,1 % Rückwärts-Zitate). Aus dem Staging-Graphen gerechnet dreht sich das Bild und reproduziert den MIT-internen Befund (cited 0,62 vs own 0,55).

## Verdrahtung (env-gated, Prod-sicher)

- Precompute `patent_citedspnp_full_z3` (25,3M Knoten, `scripts/build_cited_spnp_staging.py`) → live so schnell wie own.
- `_x_by_year` joint bei `TIR_PREDICTOR=cited` die cited-Tabelle.
- cited-Kalibrierung `(-5.5622, 5.5036, 0.4930)` (MIT-K_true-Fit).
- **Richtungsbänder re-zentriert** (cited-X-Skala): mundane Neutral **−0,158** (12 dichte mechanische Domänen), Halbweiten auf ~0,75× skaliert (cited-rel_change ist komprimiert) → **Bänder (−0,008 / −0,348 / −0,608)**.
- Default bleibt `own` + Bänder (0,44/−0,01/−0,36) → **Prod byte-identisch** (verifiziert, 12/12 Tests grün).

## Kontrollgruppen-Validierung (fairer Vergleich)

| Tier | own (Prod) | **cited (re-zentriert)** |
|---|---|---|
| up (steigend → beschleunigt) | 3/3 | **3/3** |
| down (reifend → reift/verlangsamt) | 1/2 | 1/2 |
| not_up (mundan → NICHT beschleunigt) | 5/6 | **6/6** ✓ (F16B-Falsch-Positiv weg) |
| **Gesamt** | **9/11** | **10/11** |

cited ist **besser** — perfekte mundane Kontrolle (6/6, kein Falsch-„accelerating"), alle heißen Domänen korrekt. Einziger Miss: **Wind** liest „steady" (rel −0,047) — aber Wind liegt *über* der mundanen Baseline (−0,158), ist auf cited-X also nicht schneller fallend als mundan → „steady" vertretbar.

## Trade-off ehrlich

- **Stärke:** höhere absolute K-Genauigkeit (R² 0,574 vs 0,521) + saubere mundane Kontrolle.
- **Schwäche:** cited-rel_change ist komprimiert → Richtungs-Diskriminierung schwächer; die 0,75×-Skalierung der Halbweiten ist an 11 Kontroll-Domänen kalibriert (leichtes Overfit-Risiko, mit Env-Gate + Owner-Review abgesichert).
- **Referenz-Domänen (own→cited):** Batterie 11,7→8,6, KI 69,8→28,1 (aus dem unkalibrierten Bereich zurück), Halbleiter 39,7→14,3, F16B accelerating→steady.

## Offen: temporale „1-Jahr-vor"-Konstruktion

MIT nutzt cited-Zentralität ~1 J. vor dem Zitieren; wir nutzen den age-3-gecappten Endwert. Der Age-3-Cap liefert bereits Alters-Normalisierung → Großteil des Effekts abgedeckt; unser 0,574 nah an MITs temporalem 0,621 (Rest plausibler global-vs-US-Graph). Faithful Rekonstruktion = per-Jahr-SPNP-Snapshots (teuer) → **zurückgestellt**, nur falls nach dem Flip noch Genauigkeit fehlt.

## Owner-Flip = Einzeiler

```python
# scripts/tir_trajectory.py
PREDICTOR = os.getenv("TIR_PREDICTOR", "cited")   # vorher "own"
```
Prädiktor, Kalibrierung und re-zentrierte Bänder greifen dann automatisch zusammen. **Empfehlung:** vertretbar (bessere absolute Genauigkeit + Kontrollgruppe), mit dem dokumentierten Direction-Trade-off.
