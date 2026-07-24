# TIR-Richtungs-Holdout — vorab fixierte Erwartungen (Paper-Pflichtanalyse #11)

**Zweck:** Frisches Richtungs-Kontrollset, disjunkt von (a) den Band-Tuning-Domänen
(F16B/A47B/B65D), (b) der kompletten 11er-Kontrollgruppe aus
`tir_trajectory_validate.py` (C12N15/11, A61K39, C12N15, H02S, F03D, F16B, A47B,
B65D, F16H, F04B, B25B) und (c) den 23 kuratierten cpc_insights-Subklassen.
Ersetzt die teilweise In-Sample-10/11-Validierung (§4.7 des Paper-Drafts).

**Protokoll:** Die folgenden Erwartungen wurden VOR jeder Auswertung fixiert und
committet (Commit-Zeitstempel = Beleg der Reihenfolge). Erwartungsquellen sind
externe, dokumentierte Technologie-Trends — nicht unsere eigenen Kurven. Die
Auswertung (`scripts/tir_direction_holdout.py`) läuft danach einmalig auf dem
aktiven Prod-Pfad (fullz3+cited, Defaults); Ergebnisse werden unverändert
berichtet, inklusive Fehlschlägen. Tier-Regeln wie im Bestands-Kontrollset:
`up` → muss `accelerating`; `down` → muss `maturing|decelerating`;
`not_up` → darf NICHT `accelerating` (Zurückhalten zählt als Bestehen).

| # | Technologie | CPC-Pattern | Erwartung | Dokumentierte Begründung (extern) |
|---|---|---|---|---|
| 1 | LiDAR-Systeme | `G01S17%` | up | Boom durch autonomes Fahren/Robotik seit ~2015; stark wachsende Anmeldezahlen |
| 2 | Wärmepumpen-Heizung | `F25B30%` | up | Energiewende/Gebäudewende; dokumentierter Nachfrage- und F&E-Schub in den 2020ern |
| 3 | Wasserstoff-Erzeugung/-Speicherung | `C01B3%` | up | „Hydrogen economy"-Investitionswelle; nationale H2-Strategien ab ~2020 |
| 4 | Optische Datenspeicher (CD/DVD/Blu-ray) | `G11B7%` | down | Verdrängung durch Streaming/Flash; Markt- und F&E-Niedergang seit ~2010 |
| 5 | Fotografischer Film (Silberhalogenid) | `G03C%` | down | Digitalfotografie-Verdrängung; langer dokumentierter Niedergang seit ~2000 |
| 6 | Verbrennungsmotor-Einspritzung | `F02M%` | down | Elektrifizierung des Antriebsstrangs; rückläufige Verbrenner-F&E seit ~2017 |
| 7 | Schlösser/Schließtechnik | `E05B%` | not_up | Reife Alltagstechnik; keine dokumentierte Beschleunigung |
| 8 | Schreibgeräte | `B43K%` | not_up | Reife Alltagstechnik; keine dokumentierte Beschleunigung |
| 9 | Sanitär-Installationen | `E03C%` | not_up | Reife Alltagstechnik; keine dokumentierte Beschleunigung |
| 10 | Mechanische Uhrwerke | `G04B%` | not_up | Reifes Handwerksfeld (Quarz/Smartwatch-Verdrängung); keine Beschleunigung |

**Bekannte Risiken (vorab notiert):** Dünne aktuelle Fenster können bei #4/#5
zu `uncertain`/`insufficient_data` führen — das zählt für `down` als Fehlschlag
(regelkonform), wird aber gesondert ausgewiesen. #6 könnte durch Hybrid-F&E
länger stabil geblieben sein als erwartet.
