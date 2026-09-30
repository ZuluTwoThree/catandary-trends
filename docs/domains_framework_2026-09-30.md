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

## Ad-hoc: eine Domäne aus einem freien Begriff (30.09., abends)

Owner: „Ich will die Domänen im Frontend als beliebige, unvorhersehbare Begriffe übergeben …
und live die Nester darin entdecken." Machbarkeit auf dem heutigen (langsamen) Weg:
`python -m pipeline.domains adhoc "<begriff>" --measure`, dann
`emerging_snapshot --scope domain:q_<begriff>`. Saat automatisch: der Begriff als Phrase im
Volltext (Titel/Zusammenfassung/Tags, Forschungs- und Patent-Abstracts) plus die 1.000 dem
Begriff nächsten Signale (CPU-Embedder, HNSW). Schlüssel `q_…`; `--all-domains` und der
Knopf rechnen Ad-hoc-Domänen nicht mit.

| Begriff | Saat (Phrase / Vektor) | Mitglieder 90 Tage | Nester | Zeit (Sonde+Messung / Nester) |
|---|---|---|---|---|
| solid-state battery | 366 / 1.000 | 398 | **keine** — unter der Mindestgröße (800), auch nach 180 Tagen | 100 s / 174 s |
| precision fermentation | 1.273 / 999 | 684 (180 Tage: mehr) | 11 | 95 s / 505 s |
| digital twin | 3.173 / 996 | 3.475 | 31 | 98 s / 365 s |

- **precision fermentation:** das Nest *Precision Fermentation* (erster Monat 2020-11; Ebenen
  Förderung → Markt → Forschung), *Precision Fermentation for Sustainable Protein Production*
  (2024-05), *Industrial Biotechnology Production* (2026-06, stark beschleunigend),
  *Alternative Proteins and Cultivated Meat*, dazu Fermentationsverfahren-Patente.
- **digital twin:** treffend *Urban Digital Twins* (2026-07), *Battery Digital Twins and
  Management Systems* (2026-07, Beschleunigung 11), *Digital Twin Healthcare*,
  *Digital Twins in Supply Chain Management* — aber die Domäne franst in allgemeine KI/
  Industrie 4.0 aus (*AI in Medicine*, *AI-Driven Supply Chain Management*): die nächsten
  Vektoren eines breiten Begriffs reichen weit.
- **solid-state battery:** zu eng für die Mindestgröße der Nester-Suche (800 Signale im
  Ausschnitt) — die ehrliche Antwort ist „zu dünn".

**Folgerungen für einen Live-Dienst:**
1. **Tempo:** Saat 2–4 s, Sonde ~10 s; die Minuten gehen auf das Laden von ~350.000 Vektoren
   aus der Datenbank (~80–90 s je Laden, bei Verbreiterung zweimal) und den Archiv-Scan über
   2 Mio. Zeilen (~280 s). Ein Dienst mit allen Vektoren im Speicher (~4 GB, halbe Genauigkeit)
   macht daraus Sekunden.
2. **Mindestgröße für Ad-hoc senken** (z. B. 150) und das Fenster auf 12 Monate erweitern,
   sonst bleiben enge Begriffe leer.
3. **Vorschau der Auswahl vor der Nester-Suche** (Größe, Stichproben, Anteil mit dem Begriff
   im Text) — breite Begriffe franzen aus, mehrdeutige ziehen Fremdes.
4. **Dichteprüfung relativ zur Domäne:** 66–84 % der Mitglieder landen in Nestern.
