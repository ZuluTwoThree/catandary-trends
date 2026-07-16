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

## Umgesetzt

- `TRUNC_YEARS` ist jetzt **substrat-bewusst + env-gated**: `TIR_TRUNC_YEARS` überschreibt; ohne Override bleibt **alles bei 7** (Prod unverändert, verifiziert: :3001 zeigt weiter 2019/accelerating). Der Code trägt die Begründung + den Recommendation-Kommentar.
- Opt-in-Test: `TIR_TRUNC_YEARS=4 …`.

## Empfehlung (Owner-Entscheidung)

1. **Nicht** TRUNC=4 als stillen Default flippen (product-facing, kippt Headlines).
2. **Paket schnüren:** TRUNC=4 **plus** Richtungsband-Re-Zentrierung (neue mundane Baseline am 2020–2022-Rand messen → `ACCEL_PP/DECEL_PP/MATURE_PP` um ~0,15 nach unten verschieben), dann Kontroll-Domänen validieren (F16B steady, KI/CRISPR beschleunigend/reifend, Solar reifend). Erst dann Default-Flip.
3. Alternativ konservativ **TRUNC=5** (letztes Jahr 2021) prüfen, falls der 2022-Rand zu unreif erscheint.
