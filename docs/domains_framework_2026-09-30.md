# Frei wählbare Domänen — zweistufige Nester-Suche (2026-09-30)

**Owner:** Nester sollen in frei gewählten Domänen gefunden werden — 5G/6G in *Wireless*,
humanoide Roboter in *Robotics* —, unabhängig von den Vertikal-Etiketten der Pipeline,
weil die Ähnlichkeit der Einbettungen präziser sein kann als das Textlesen des 8B.

## Aufbau

**Stufe 1 — Mitgliedschaft aus dem Embedding** (`pipeline/domains.py`):

- Eine Domäne ist eine **Definition** in `domains.yaml` (Repo-Wurzel): Name und Saat-Quellen,
  die nicht von unseren Klassifikatoren stammen — **CPC-Präfixe** der Patentprüfer
  (`patent_cpc`), **OpenAlex-Themen/-Subfelder** (Forschung über DOI), **Phrasen** (Volltext
  in Titel/Zusammenfassung/Tags, Forschungs- und Patent-Abstracts — die einzige Saat, die
  auch die Presse erreicht).
- Daraus eine **lineare Sonde** (logistische Regression) auf dem 1024er-Präfix gegen einen
  zufälligen Hintergrund des Korpus (60.000). Merkmale **ebenen-zentriert** (Mittelvektor je
  Ebene abgezogen, wie die Themen-Anordnung der Wolke). Positive je Ebene auf 30.000
  gedeckelt, damit keine Saat eine Ebene überflutet.
- **Schwelle je Ebene**, gesetzt auf einen Anteil der Saat (`target_recall`, Standard 0,7),
  nie unter 0,5. Eine Präzisions-Eichung wurde verworfen: bei Domänenanteilen um 0,3 %
  (Forschung, Presse) kippt ein einziger Fehltreffer unter ~4.000 Hintergrundzeilen die
  Schätzung — die Schwellen gingen auf 0,99 und behielten ein Fünftel der Saat. Eine
  gemeinsame Schwelle wurde verworfen, weil die Patente sie bestimmten. Die Fehltreffer-Rate
  auf dem (unbeschrifteten, also pessimistischen) Hintergrund steht je Ebene in den Metriken.
- Zeilen der Pseudo-Quellen `OpenAlex corpus: …` (#114, anders eingebettet) bleiben aus dem
  **Training** heraus, nie aus der Mitgliedschaft.
- Gespeichert in der Tabelle **`domain_probes`** (joblib-Bytes, Schwellen, Metriken,
  Messung) — beide Worktrees und die Owner-App sehen dieselbe Sonde.

**Stufe 2 — Nester in der Domäne** (`pipeline/emerging_snapshot.py`, Bereich
`domain:<schlüssel>`): der 90-Tage-Ausschnitt wird auf die Mitglieder beschränkt, dann
Feinzerlegung, Dichteprüfung, Beschreibung und Benennung wie immer. Der **Archiv-Scan zählt
nur Mitglieder** (`scan_history(member=…)`): Datierung, Monatssummen und Neuheit gelten
innerhalb der Domäne.

## Bedienung

```bash
.venv/bin/python -m pipeline.domains list                       # definierte und trainierte Domänen
.venv/bin/python -m pipeline.domains train wireless --measure   # Sonde trainieren + auf 90 Tage anwenden (~1 min)
.venv/bin/python -m pipeline.emerging_snapshot --scope domain:wireless
.venv/bin/python -m pipeline.emerging_snapshot --all-domains    # alle trainierten (~7 min je Domäne)
```

Neue Domäne: Eintrag in `domains.yaml`, `train`, dann Nester rechnen. Seite:
`/trends/foresight/emerging?domain=<schlüssel>` (Reiterzeile „by domain"); der Knopf
*Recompute pockets* rechnet seit diesem Umbau auch alle trainierten Domänen.

## Erste Messung (30.09., Beispiel-Domänen)

| Domäne | Saat (CPC / OpenAlex / Phrasen) | Mitglieder 90 Tage | nach Ebene | Nester |
|---|---|---|---|---|
| Wireless | H04W, H04B7, H01Q, H04L5, H04L27 / 9 Themen / 5G, 6G, Wi-Fi, O-RAN … | 10.014 | Patente 8.252 · Forschung 1.503 · Presse 227 | 91 |
| Robotics | B25J, B62D57, B25H / 11 Themen / humanoid robot, cobot, exoskeleton … | 6.718 | Forschung 3.833 · Patente 2.105 · Presse 681 | 51 |
| Elektromobilität | B60L, B60K1, B60K6, H02J7, B60W20 / 3 Themen / EV charging, V2G … | 4.603 | Patente 1.750 · Forschung 1.489 · Presse 1.349 | 32 |

Stichproben der Mitglieder: Presse und Förderung bei Wireless durchweg treffend (5G-Slicing,
Starlink, O-RAN, 6G-Förderung), Forschung überwiegend (Grenzfälle: IoT-Überwachung).
Beispiel-Nester: Robotics — *Vision-Language-Action Models* (275, 6 Monate), *World Action
Models* (140, 3 Monate), *Humanoid Whole-Body Control* (109), *Dexterous Hand*, *Quadrupedal
Locomotion*; Wireless — *6G Communications*, *6G NTN Satellite Connectivity*,
*Reconfigurable Intelligent Surface*, *Sub-band Full Duplex*, *Ambient IoT*; Elektromobilität —
Ladesäulen, Thermal Runaway, Vehicle-to-Grid, Akku-Recycling, *Tesla Semi*.

## Grenzen und nächste Stellschrauben

- **Alter vieler Patent-Nester ist ein Korpus-Artefakt:** Patente gibt es im Signalraum fast
  nur seit August 2026 (rollendes Fenster) und für Food (#114). Ein 3GPP-Thema wirkt deshalb
  „3 Monate alt". Das Alter ist nur so gut wie die Abdeckung der Ebene.
- **Dichteprüfung in engen Domänen zu nachgiebig:** 51–75 % der Mitglieder liegen in Nestern
  (global ~12 %), weil Dokumente einer Domäne einander ohnehin ähnlich sind. Die Nester sind
  damit eher Unterthemen als „dichte, neue Taschen". Nächster Schritt: Kohäsion relativ zur
  Domäne (Median-Ähnlichkeit der Mitglieder) statt absolut.
- **Elektromobilität franst in allgemeine Fahrzeugtechnik aus** (Display, Kamera, Beleuchtung,
  digitaler Schlüssel) — die Saat braucht Schärfung (engere CPC-Präfixe) oder eine höhere
  `target_recall`-Strenge.
- Der Hintergrund ist unbeschriftet; gemessene Fehltreffer-Raten sind Obergrenzen.
