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


## Live-Dienst: Begriff eingeben, Nester in Sekunden (01.10.2026)

Owner 01.10.: Domänen als beliebige, nicht vorhersehbare Begriffe im Frontend übergeben,
die Signale live auswählen und darin live Nester finden. Gebaut als residenter Dienst
`pipeline/domain_service.py` (127.0.0.1:8093, Unit `deploy/systemd/catandary-domain-service.service`)
plus Seite `/trends/foresight/discover`.

**Speicher statt Datenbank.** Der Dienst hält jedes eingebettete Signal (signal, published,
draft) als Einheitsvektor in halber Genauigkeit: 2.017.286 Zeilen, 3,94 GB, dazu Monat,
Ebene, Status und Quelle je Zeile. Erstaufbau aus Postgres 5:40 min (`--rebuild`), danach
lädt er die Kopie aus `~/.cache/catandary/domain_service` in 3 s und liest vor jedem Auftrag
nur die neuen Zeilen nach (Status von Entwürfen wird nachgezogen). Saat aus dem Volltext
kommt weiter aus der Datenbank (2–4 s); alles andere — nächste Vektoren, Hintergrund-
Stichprobe, Sonde, Mitgliedschaft über alle 2 Mio., Ausschnitt, Archiv-Datierung — rechnet
er im Speicher mit **demselben Code** wie der Kommandozeilenpfad (`domains.train` und
`emerging.scan_history` nehmen ihre Daten jetzt injiziert).

**Tempo (gemessen 01.10.):** Auswahl 7–12 s, Nester 0,4–13 s (inklusive Benennung) —
gegen 95–100 s und 174–505 s auf dem Kommandozeilenpfad.

**Zwei Stufen je Auftrag.** *Auswahl* trainiert die Sonde und zeigt eine Vorschau: Mitglieder
in den letzten 12 Monaten und im ganzen Archiv, je Ebene, 14 Stichproben „drin" und 8
„knapp draußen", und wie viele Mitglieder den Begriff wörtlich tragen (Stichprobe 400,
Titel + Zusammenfassung + Auszug + Abstract + Tags, Pluralformen gleich). Erst nach
Bestätigung *Nester*.

**Was für freie Begriffe anders ist** (alles gemessen, nichts geschätzt):

| Stellschraube | Wert | Warum |
|---|---|---|
| Fenster | 12 Monate (6/24 wählbar) | „solid-state battery" hatte in 90 Tagen 398 Mitglieder und keine Nester |
| Mindestgröße Ausschnitt | 150 Signale | statt 800 |
| Mindestgröße Nest | 15 unter 1.500 Signalen, sonst 30 | |
| Volltext-Saat | wörtlich nachgeprüft | der Stemmer macht „precision" und „precise" gleich, die Tag-Liste setzt „precision" neben „fermentation": von 1.063 Signal-Treffern trugen 432 den Begriff, von 14 Patenten 2 |
| Vektor-Saat | füllt nur auf 500 auf | neben 1.224 wörtlichen Treffern zogen die 1.000 nächsten Vektoren die Sonde in allgemeine Fermentation |
| Saat-Recall je Ebene | 0,5 statt 0,7 | Anteil mit dem Begriff: digital twin 0,26 → 0,67, humanoid robots 0,32 → 0,45, solid-state battery 0,41 → 0,49, batteries 0,71 → 0,81 |
| Dichteprüfung | dichteste 40 % der eigenen Zellen, **je Ebene** | absolut 0,75 ließ 51–84 % der Domäne in Nestern; ein Quantil über alle Zellen behielt bei „batteries" 16 Forschungs- und 0 Markt-/Patentnester (Forschung liegt dichter); Quantil 0,50/0,60/0,75 → 38/29/19 Nester, bei 0,75 fielen Festkörper und Recycling heraus |
| Zusammenlegen | roh ≥ 0,92 **und** domänenzentriert ≥ 0,70 | roh allein trennt nicht: die zwei Zink-Ionen-Nester lagen bei 0,939, verschiedene Lithium-Themen bei 0,947; zentriert 0,749 gegen < 0,63 |
| Untergruppen | Average Linkage auf zentrierten Zentroiden, Schnitt 0,7 | 60 Batterie-Nester: 0,6 → 26, 0,7 → 14, 0,8 → 8 Gruppen; bei 0,7 je eine Gruppe für Zink/wässrig, Lithium/Natrium, Thermik, Netz/EV, Speicherprojekte, Recycling, Zustandsschätzung |
| Benennung | ruhendes 8B auf :8090, nur wenn kein Job die Karte hält | nie ein GPU-Handover aus einer Web-Anfrage; sonst bleiben die Schlagwort-Etiketten. Gruppennamen nur aus den Nest-Namen (mit Mitgliedstiteln benannte das Modell die Chemie-Gruppe nach ihrem größten Nest) |

**Ergebnisse mit den endgültigen Einstellungen (01.10.):**

| Begriff | Auswahl 12 Mon. / Archiv | wörtlich | Nester / Gruppen | Auswahl / Nester |
|---|---|---|---|---|
| batteries | 6.102 / 11.584 | 0,99 | 22 / 9 — u. a. Festkörper als eigene Gruppe, Zink/Mg, Natrium-Ionen, Thermik, Zustandsschätzung + Recycling, Speicherprojekte (Presse), Elektroden (Patente) | 10,5 s / 8,0 s |
| digital twin | 1.076 / 1.797 | 0,85 | 6 / 3 — Lieferkette, Gesundheit (Kardiologie) | 7,9 s / 1,4 s |
| solid-state battery | 234 / 423 | 0,77 | 2 / 1 | 10,6 s / 0,5 s |
| humanoid robots | 382 / 526 | 0,65 | 2 / 2 — Whole-Body Control | 7,3 s / 0,4 s |
| precision fermentation | 1.155 / 2.863 | 0,19 | 9 / 4 — *Precision Fermentation Proteins* (Lactoferrin, Milchproteine) als Gruppe, daneben allgemeine Fermentation | 7,5 s / 2,4 s |

**Grenzen:**
- *precision fermentation* liegt im Vektorraum mitten in der Fermentationsforschung (die
  Quelle „OpenAlex fresh: Fermentation" stellt 937 der Mitglieder); auch mit wörtlicher Saat
  und strengerer Schwelle tragen nur 19 % den Begriff. Die Vorschau zeigt das, bevor
  gerechnet wird; ein schärferes Ergebnis brauchte Gegen-Saat („nicht: allgemeine
  Fermentation") — nicht gebaut.
- Das **Alter** bleibt eine Aussage über unsere Abdeckung: Forschung und Patente sind im
  Signalraum überwiegend jung, viele Nester datieren daher „2026-07". Nächster Schritt
  (Owner 01.10.): Patente und Forschung tragen kalendarische Daten außerhalb des
  Signalraums (Patentbestand, OpenAlex-Suchschicht) — die sollen die Datierung tragen.
- Lithium-Eisenphosphat erscheint unter „batteries" nicht als eigenes Nest.


## Kalender-Datierung: Forschung und Patente statt Signalraum (01.10.2026)

Owner 01.10.: „Patente und Forschung tragen kalendarische Daten zur zeitlichen Einordnung,
die nutzbar sein müssten." Der Signalraum hält Forschung und Patente erst seit 2026 in der
Breite, darum datierten fast alle Domänen-Nester „2026-07" — Redox-Flow- wie
Magnesium-Batterien. `pipeline/calendar_dating.py` fragt stattdessen die beiden Bestände
außerhalb des Signalraums: `research_corpus` (OpenAlex, 45,5 Mio. Arbeiten, in der Breite ab
2010) und `patent_search` (20,0 Mio. Patente ab 1990), beide mit GIN-Volltextindex.

**Verfahren je Nest:**
1. *Wendungen:* 1-3-Wort-Folgen, die die Titel des Nests vom Rest der Domäne abheben —
   Anteil im Nest × log(Anteil im Nest / Anteil in der Domäne), mindestens 12 % der Titel
   und 3 Treffer, Domänenbegriff selbst ausgenommen; die zwei besten, keine enthält die andere.
2. *Abfrage:* Anker (der freie Begriff + Schreibweisen, bei YAML-Domänen deren Phrasen) UND
   eine der Wendungen (`phraseto_tsquery`, `&&`/`||`).
3. *Je Jahr und Bestand:* Treffer und Treffer je Million Dokumente desselben Jahres — die
   Bestände wachsen ungleich (Patente 2010-15 dünn, Forschung 2024 verdoppelt).
4. *Kennzahlen:* erstes Jahr (≥ 3 Treffer; am Bestandsbeginn als „oder früher"
   gekennzeichnet), Take-off (erstes Jahr mit ≥ 15 % der Spitzenrate, Field-Watch-Regel),
   Wachstum (letzte drei vollständige Jahre über die drei davor). Das laufende Jahr zählt
   in keine Kennzahl.

**Betrieb:** Jahresbestand je Korpus ~55 s, darum in `~/.cache/catandary/calendar_totals.json`
(eine Woche gültig), vom Dienst beim Start vorgewärmt; danach 0,02-15 s je Abfrage, vier
parallel. Im Live-Dienst läuft die Datierung **nach** der Anzeige der Nester (1-40 s) und
schreibt ins gespeicherte Ergebnis (`emerging_nests.calendar`, JSON, additiv, Live-DB 01.10.).
YAML-Domänen (`emerging_snapshot --scope domain:<k>`, *Recompute pockets*) datieren mit.

**Karte:** Kopfzeile „on record since <Jahr>" statt „first seen"; Block *On the record* mit
Forschung/Patente (seit, Take-off, Wachstum, Anzahl, Kurve je Million), darunter die
gezählte Abfrage im Wortlaut und „in our signals since …". „Nur unter 18 Monaten" folgt bei
datierten Nestern dem Kalender (nicht am Bestandsbeginn, erstes Jahr ≥ Vorjahr).

**Erste Ergebnisse** (Patente: erstes Jahr / Take-off / Wachstum, gegen den Signalraum):

| Nest | Signalraum | Patente | Forschung |
|---|---|---|---|
| Sodium-Ion Battery Storage | 2024-12 | 2007 / 2019 / ×8,7 | 2011 / 2014 / ×1,3 |
| Solid-State Battery Innovation | 2022-06 | 1994 / 2018 / ×3,3 | ≤ 2010 / 2013 / ×1,4 |
| Redox Flow Battery Storage | 2026-07 | 2005 / 2009 / ×2,6 | ≤ 2010 / 2011 |
| Remaining Useful Life Prediction | 2026-07 | 2019 / 2019 / ×2,4 | 2011 / 2013 / ×1,5 |
| Cardiac Digital Twins | 2024-12 | 2025 / 2025 | 2019 / 2022 / ×5,1 |
| Digital Twin Healthcare | 2021-07 | 2019 / 2021 / ×2,7 | 2018 / 2021 / ×3,2 |
| Precision Fermented Lactoferrin | 2026-07 | 2023 / 2023 / ×4,0 | 2022 / 2023 / ×11,1 |

**Grenzen:** Es ist eine Wortzählung. Wendungen können Rauschen tragen (Firmennamen wie
„catl", „unitree"; Allerweltswörter wie „device", „project") — die Abfrage steht deshalb auf
jeder Karte. Forschung reicht nur bis 2010 zurück: etablierte Themen stehen dort auf
„2010 oder früher". Der Patentbestand trägt nicht jeden Begriff in seinem Index gleich gut
(„solid-state battery" als Anker: erstes Jahr 2018, obwohl ältere Patente existieren).
Globale, Vertikal- und Ebenen-Läufe werden (noch) nicht kalendarisch datiert — ihnen fehlt
ein Anker, und eine Wendung allein ist zu breit.
