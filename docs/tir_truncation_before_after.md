# TIR Truncation-Frontier für `fullz3`: TRUNC 7 → 4 — Vorher/Nachher

**Stand:** 2026-07-16 · **Substrat:** `fullz3` (z-Score-Null + Age-3-Cap, geschlossenes Netz) · **Bezug:** #45 WS2, [[tir-computation-state]]

## Frage
Ist „letztes vollständiges Jahr = 2019" (`TRUNC_YEARS=7`) für `fullz3` noch korrekt, oder liegt der Horizont später?

## Befund
`TRUNC_YEARS=7` wurde für den **alten `full`-Substrat ohne Age-Cap** kalibriert (mittlere SPNP-Zentralität kippt dort ab ~2019 Richtung 0,5 = Immaturität). `fullz3` hat den **Age-3-Forward-Cap**, der Kohorten ~3 Jahre früher vergleichbar macht. Empirisch (geschlossenes Netz, große, stabile Domänen) hält die Zentralität ohne 0,5-Regression bis ~2022–2023:

- **KI G06N** (95k+ Patente/J): mittlere pctl 0,657 / 0,662 / 0,613 bei 2022 / 2023 / 2024
- **Batterie H01M10** (31–35k/J): solide bis 2024

→ Methodenhorizont Age-3 = `Jahr+3 ≤ heute` → **2023**; begrenzt durch Zitationsdaten-Nachlauf (dicht bis ~2024) ist das letzte **voll** vollständige Jahr **~2022**. Also ~3 Jahre später als 2019.

> **Achtung CPC-Migration:** H01L (Halbleiter) fällt von ~117k (2019) auf 88 (2022) — **kein** Immaturitäts-Droop, sondern die CPC-Reorganisation H01L→H10D/H10H/H10K ab ~2023 (#43). Domänen-Definitions-Artefakt, orthogonal zum Horizont. H01L als Benchmark für den Horizont ist deshalb untauglich.

## Vorher/Nachher (isoliert: gleiche Daten, nur TRUNC 7 vs 4)

| Domäne | last_compl. | K_median | K_recent | K_latest | Richtung | rel_ch |
|---|--:|--:|--:|--:|--|--:|
| **Batterie H01M10** VORHER(7) | 2019 | 11,7 | 13,5 | 13,5 | accelerating | +0,458 |
| NACHHER(4) | 2022 | 11,7 | 13,5 | 8,6 | **decelerating** | −0,563 |
| **KI G06N** VORHER(7) | 2019 | 69,8 | — | — | decelerating | −0,629 |
| NACHHER(4) | 2022 | 63,4 | — | — | decelerating | −0,500 |
| **Solar H02S** VORHER(7) | 2019 | 16,9 | 14,7 | 14,1 | maturing | −0,029 |
| NACHHER(4) | 2022 | 16,7 | 14,1 | 8,8 | **decelerating** | −0,562 |
| **Wireless H04W** VORHER(7) | 2019 | 22,7 | 29,7 | 22,7 | maturing | −0,246 |
| NACHHER(4) | 2022 | 23,8 | 26,4 | 26,4 | maturing | −0,126 |
| **Käse A23C19** VORHER(7) | 2019 | 6,3 | 9,8 | 16,5 | uncertain | +1,365 |
| NACHHER(4) | 2022 | 6,5 | 11,7 | 11,5 | uncertain | +0,203 |
| **Schrauben F16B** VORHER(7) | 2019 | 10,3 | 9,9 | 11,0 | **accelerating** | +0,682 |
| NACHHER(4) | 2022 | 10,3 | 10,5 | 10,1 | **steady** | +0,010 |
| **Genome C12Q1/6869** VORHER(7) | 2019 | 17,5 | 39,9 | 23,2 | uncertain | −0,794 |
| NACHHER(4) | 2022 | 17,8 | 23,2 | 18,3 | decelerating | −0,722 |

**Neu sichtbare Jahre (solides n, kein Rausch-Artefakt):**
- Batterie: 2020 K=12,0 (n=107k) · 2021 K=10,2 (n=130k) · 2022 K=8,6 (n=146k)
- KI: 2020 K=35,3 (n=131k) · 2021 K=35,6 (n=216k) · 2022 K=39,0 (n=300k)
- Wireless: 2020 K=24,2 (n=309k) · 2021 K=26,5 (n=355k) · 2022 K=26,4 (n=354k)
- Schrauben: 2020 K=11,0 (n=34k) · 2021 K=10,5 (n=38k) · 2022 K=10,1 (n=36k)

## Interpretation

**Der Gewinn ist echt:** Die neu sichtbaren Jahre haben durchweg großes n (100k+), sind also kein Dünn-Daten-Rauschen, und die Bewegung ist **nicht uniform** — KI/Wireless steigen leicht (35→39 / 24→26), Batterie/Solar/Genome fallen. Das ist genau die Rezenz-Diskriminierung (heiß vs. reifend), die `TRUNC=7` verwarf. Zwei Ablesungen werden **klar besser**: F16B-Schrauben `accelerating → steady` (der bekannte Falsch-Positiv aus dem +0,15-Baseline verschwindet), Wireless bleibt sauber maturing.

**Aber ein simpler Flip ist nicht sauber:** Der jüngste Rand (2020–2022) trägt noch eine **milde Abwärts-Neigung** (Rest-Immaturität + Zitationsdaten-Nachlauf, vom Age-3-Cap reduziert aber nicht eliminiert). Die Richtungsbänder (`ACCEL_PP=+0,15`, kalibriert auf den ALTEN 2019-Rand) sind damit **fehlzentriert**: die mundane Baseline liegt am neuen Rand bei ~0 (F16B +0,01, Wireless −0,13) statt +0,15. Ohne Re-Zentrierung kippen mehrere Headlines nach `decelerating` (Batterie, Solar) — teils real (reifende Felder), teils Rand-Bias, nicht sauber trennbar.

## Richtungsband-Re-Zentrierung (Teil 2 des Pakets)

Die mundane Baseline (Median rel_change über 12 dichte mechanische Domänen — F16B/
A47B/B65D/B23C/F16D/B62D/E04B/B65G/F16K/B60R/F16H/B25B) verschiebt sich mit dem
Rand:

| Horizont | mundane Neutral | Bänder (ACCEL / MATURE / DECEL), Halbweiten +0,20/−0,25/−0,60 |
|---|--:|---|
| TRUNC=7 (2019, Prod) | **+0,227** | 0,44 / −0,01 / −0,36 |
| TRUNC=4 (2022) | **−0,220** | −0,02 / −0,47 / −0,82 |

Der Rand kippt also die Baseline um ~0,45 nach unten — Möbel −0,66, Bau −0,84,
Behälter −0,55: Domänen, die unmöglich „in der Innovationsrate reifen", also ein
**Rand-Artefakt**, das das Band absorbieren muss. `fullz3` schaltet die Bänder jetzt
**mit dem TRUNC-Horizont mit** (Prod TRUNC=7 byte-identisch; die re-zentrierten
Bänder greifen nur bei TRUNC≤4).

## Kontrollgruppen-Validierung (fairer Vergleich, gleiche Erwartungen)

`tir_trajectory_validate.py`, Tiers an die Post-Backfill-Dichte angepasst (Zahnräder/
Pumpen/Handwerkzeug sind nicht mehr dünn → jetzt „mundan, darf nicht beschleunigen"):

**Beide Einstellungen: 9/11.** Die Re-Zentrierung kompensiert den Rand-Shift
vollständig — TRUNC=4 ist **gleich gut** wie Prod und gewinnt zusätzlich 3 Jahre Kurve.

| Domäne | Tier | DIR@7 (rel) | DIR@4 (rel) | Bewertung |
|---|---|---|---|---|
| CRISPR | steigend | accelerating (+0,50) | **accelerating** (+0,25) | ✅ beide |
| Impfstoffe | steigend | accelerating (+0,44) | **accelerating** (+0,07) | ✅ beide |
| mRNA | steigend | accelerating (+0,64) | **accelerating** (+0,05) | ✅ beide |
| Solar | reifend | maturing (−0,03) | maturing (−0,56) | ✅ beide |
| **Wind** | reifend | **accelerating** (+0,49) ❌ | steady (−0,20) ❌ | @4 *weniger* falsch |
| **Schrauben F16B** | mundan | accelerating (+0,68) ❌ | accelerating (+0,01) ❌ | Ausreißer, beide |
| Möbel | mundan | steady (+0,13) | maturing (−0,66) | ✅ beide (kein accel) |
| Behälter | mundan | steady (+0,15) | maturing (−0,55) | ✅ beide |
| Zahnräder | mundan | steady (+0,32) | steady (−0,05) | ✅ beide |
| Pumpen | mundan | maturing (−0,02) | maturing (−0,72) | ✅ beide |
| Handwerkzeug | mundan | maturing (−0,05) | maturing (−0,76) | ✅ beide |

Die **2 verbleibenden Fehler scheitern bei BEIDEN** Einstellungen, sind also nicht
durch die TRUNC-Änderung verursacht: **F16B** ist ein echter Flach-Ausreißer (bleibt
+0,01, während die anderen mundanen Domänen einbrechen → relativ „beschleunigend");
**Wind** ist grenzwertig — und liest bei TRUNC=4 *besser* („steady" statt fälschlich
„accelerating" wie in Prod).

**Ehrliche Rest-Grenze:** Der 2022-Rand hat große mundane Streuung (−0,84 … +0,01);
die Re-Zentrierung korrigiert den Median, nicht die Streuung. Einige mundane Domänen
lesen daher „maturing" (Möbel/Behälter) statt „steady" — für die Kontrolle „darf nicht
beschleunigen" unschädlich, aber ein Zeichen, dass Einzel-Richtungen am neuen Rand
rauschiger sind. **Verlässlich am Rand: die Kurve/K-Werte; die Richtung mit etwas
mehr Vorbehalt.**

## Umgesetzt (env-gated, Prod unverändert)

- `TRUNC_YEARS` substrat-bewusst + `TIR_TRUNC_YEARS`-Override; Default überall **7**.
- fullz3-Bänder schalten **automatisch mit** dem TRUNC-Horizont (TRUNC≤4 → re-zentriert).
- `tir_trajectory_validate.py`-Tiers auf Post-Backfill-Dichte aktualisiert.
- Verifiziert: Prod :3001 unverändert (2019/accelerating, Bänder 0,44/−0,01/−0,36).
  Opt-in-Test: `TIR_TRUNC_YEARS=4 …`.

## Default-Flip = Einzeiler (Owner-Freigabe)

Das Paket ist vollständig. Um es scharf zu schalten, in `tir_trajectory.py` **eine
Zeile** ändern:

```python
_TRUNC: dict[str, int] = {"fullz3": 4}   # vorher: {}
```

Das setzt TRUNC_YEARS=4 für fullz3 → die re-zentrierten Bänder greifen automatisch mit.
Kein weiterer Eingriff, keine Substrat- oder Frontend-Änderung nötig.

**Empfehlung:** Flip vertretbar (gleiche Kontrollgruppen-Qualität, 3 Jahre mehr
Signal). Falls der 2022-Rand zu rauschig erscheint, konservativ **TRUNC=5** (2021)
als Zwischenschritt — dann müsste die Baseline für TRUNC=5 einmal nachgemessen werden.
