# Geschäftsmodell Catandary Foresight — „gemessene Lage je Feld"

> **Intern, Arbeitsdokument für den Owner** (Auftrag 2026-09-19). Führt die
> Angebotskonzepte vom 19.09. zu einem Modell zusammen. Zahlen sind aus der
> Live-DB gemessen (19.09.2026, 453 GB); Kosten und Zeiten sind Schätzungen und
> als solche markiert. Ehrlichkeitsregeln der Launch-Site gelten (kein
> Methoden-USP, TIR = relative Entwicklung, keine Früherkennungs-Claims).
> Grundlage: `docs/value_proposition_field_watch_2026-09-19.md` (Option C),
> Owner-Entscheide 26.08. (kein SaaS, sales-led) und 19.09. (Dossiers raus).

## 1. Ziel und Zahl

**1.000–2.000 € Gewinn je Monat** aus dem vorhandenen Bestand, ohne neues
Modell, ohne Hosting-Umbau, ohne Accounts oder Checkout. Bei laufenden Kosten
von rund 150 €/Monat (Abschnitt 8) heißt das **1.200–2.200 € Umsatz je Monat**
— das sind **zwei bis fünf Kunden**, nicht Reichweite. Reichweite gibt es
heute nicht: 3 Newsletter-Abonnenten (davon der Owner), 139 Metrik-Zeilen, Seite
bis 01.10. auf `noindex`.

## 2. Ein Satz

*Catandary misst, wie sich ein Technologiefeld über vier Ebenen bewegt —
Wissenschaft, Patent, Förderung, Markt — aus 21,9 M datierten Signalen seit 1990,
und liefert diese Lage je Feld als Blatt, als Abo und als Arbeitstag. Geschrieben
wird wenig, gemessen alles.*

Der Befund dahinter (19.09., 48 Dossierläufe): alles, was die Plattform zählt,
hat kein Leser je beanstandet; alles, was das Modell schreiben musste, wackelte.
Das Modell dreht das um — **das Messen ist das Produkt, Prosa kommt vom Owner.**

## 3. Übersicht (Canvas)

| Baustein | Inhalt |
|---|---|
| **Kunden** | (1) Innovations-/Technologiemanagement im DACH-Mittelstand — Typ Suwelack (Abonnent seit 12.08., FOOD); (2) Transferstellen und Institute; (3) VC-/CVC-Associates; (4) Patentanwälte, die Landschaften für 3–5 k weiterverkaufen und eine Vorstufe brauchen |
| **Felder** | nur dort, wo der Korpus trägt: TECH (10,5 k Artikel/30 d), BIZ (7,3 k), ECO (5,7 k), HEALTH (4,7 k), FOOD (1,7 k). FASHION/DESIGN (≈600) tragen kein Abo |
| **Wertversprechen** | Zeitreihe statt Momentaufnahme; vier Ebenen; acht Vertikale + DACH-Quellen; Schwächen stehen als Zelle in der Tabelle (0 Signale Förderung = 0); Preis unter den Enterprise-Anbietern (GetFocus/TechNext: gleiche SPNP-Methode, andere Preisklasse) |
| **Angebot** | Leiter mit vier Stufen, Festpreise sichtbar (Abschnitt 4) |
| **Kanäle** | catandary.de/trends (Launch 01.10.) mit Preisblock + drei Muster-Sheets · LinkedIn (die selbst erstellten Analysen als Teaser) · Newsletter (Website-Edition + freigegebener Versand) · direkte Ansprache bekannter Kontakte |
| **Beziehung** | sales-led, persönlich: Einrichtungsgespräch je Feld, Rechnung, keine Selbstbedienung |
| **Einnahmen** | Rechnung; einmalig (Sheet, Setup, Tag) + wiederkehrend (Field Watch, jährlich fakturiert) |
| **Schlüsselaktivitäten** | Nachtlauf (läuft) · Field-Watch-Wochenlauf (Cron) · Sheet-Erstellung (1 Owner-Tag) · Durchsicht Field Watch (~1 h je Kunde/Woche) · Akquise (1 LinkedIn-Post/Woche, 10 Direktkontakte/Monat) |
| **Schlüsselressourcen** | Korpus (21,9 M Signale, 45,5 M Werke, 18,7 M Patente mit Graph, 685 CPC-Zeitreihen, 145 k Startups, 523 Nester, 28 Themes) · RTX 3090 · Pipeline/Cron · Owner-Fachwissen |
| **Kosten** | ≈150 €/Monat Betrieb (Schätzung, Abschnitt 8) + Owner-Zeit ≈3 Tage/Monat im Zielzustand |
| **Nicht Teil des Modells** | Dossier-/Advisor-Prosa · SaaS/Self-Service/Checkout · Werbung/Sponsoring · Radar · Verkauf von `raw_content` |

## 4. Die Angebotsleiter

| Stufe | Produkt | Preis | Lieferung | Aufwand Owner | Quelle in der Plattform |
|---|---|---|---|---|---|
| 0 | **Frei**: Trends der letzten 30 Tage, Newsletter, drei Muster-Sheets | 0 € | Website, Mail | läuft | statischer Export, `newsletter_editions` |
| 1 | **Technology Trajectory Sheet** — ein Feld, 6–8 Seiten: Reifegrad-Karte (CPC-Bündel, Zykluszeit, Verbesserungsrate relativ), Erstauftritt + Abstand je Ebene, Bewegung je Quartal anteilsnormiert, 5–10 nächste Nester, Akteure als Untergrenze, eine Seite Einordnung vom Owner | **1.490 €** einmalig, 5 Werktage | PDF | 1 Tag | `dossier_quant`-Kaskade, Cluster-Panel, `emerging.py`, `tiers.py`, `cpc_leadtime_summary`, Startup Explorer |
| 2 | **Field Watch** — 3 Felder, wöchentlich: Pulse (Volumen vs. Vier-Wochen-Median, Cluster, 4 Papers), Bewegung je Ebene, neue Nester, neue Akteure; Quartals-Scorecard | **390 €/Monat** (jährlich), **+90 €** je weiteres Feld, **Setup 900 €** einmalig (Feld-Mapping auf CPC/Korpusbegriffe = Owner-Checkpoint) | PDF je Woche + Kundenseite `trends/clients/<kunde>/` hinter htpasswd auf dem Webspace | Einrichtung 1 Tag, dann ~1 h/Woche | `research_pulse`-Mechanik je Kundenfeld, `field_watch.py` (zu bauen), Cron Sa 12:30 |
| 3 | **Hypercare-Tag** — live an den Werkzeugen (Cluster, Explorer, Nester, Startups) im Team des Kunden | **1.200 €/Tag** | vor Ort oder Tailscale-Share für den Termin | 1 Tag | Owner-Instanz :3001 |
| opt. | **Datenlieferung** an Trend-/Innovationsagenturen: monatlicher Export der klassifizierten Signale (Titel, Quelle+Link, Vertikale, PESTEL, Mega, Region, Brands — **nie** `raw_content`) | 300–800 €/Monat | CSV/Parquet | Export-Skript einmal, dann Minuten | `trends` |

Die Leiter ist so gebaut, dass jede Stufe die nächste verkauft: das Sheet zeigt
das Feld, Field Watch hält es aktuell, der Tag holt den Kunden an die Werkzeuge.
Die Kundenseite hinter htpasswd ist bewusst **statisch** — das Hetzner-Hosting
kann das ohne eine Zeile Auth-Code; der Rückbau vom 03.09. (#93) bleibt gültig.

## 5. Gewinnrechnung (Monat, Schätzung)

| Szenario | Mix | Umsatz | Kosten | Gewinn | Owner-Zeit |
|---|---|---|---|---|---|
| **Untere Kante** | 3 × Field Watch | 1.170 € | 150 € | **≈1.020 €** | ~1,5 Tage |
| **Ziel** | 2 × Field Watch + 1 Sheet | 2.270 € | 150 € | **≈2.120 €** | ~3 Tage |
| **Ausbau** | 4 × Field Watch (davon 1 mit 5 Feldern) + 1 Sheet + 1 Tag/Quartal | ≈3.600 € | 150 € | ≈3.450 € | ~4,5 Tage |

Setup-Gebühren (900 €) und Jahresfakturierung sind hier nicht eingerechnet; sie
glätten die ersten Monate. Ein einziges Sheet pro Monat trifft das Ziel allein.

## 5a. Musterblätter (20.09.2026)

Beide Angebote sind als Muster aus der Live-DB gerechnet — reine SQL-Messung,
kein Modelltext, PDF über Playwright-Chromium (seit 20.09. abends das Produktskript
`scripts/field_watch.py --sample`, Felder `fields/example.yaml` und
`fields/example-lfp.yaml`; die Demo-Generatoren sind darin aufgegangen):

- **Technology Trajectory Sheet** — `docs/samples/trajectory_sheet_lfp_2026-09-20.pdf`
  (Lithium-Eisenphosphat-Zellen): 3.547 Patente mit Feldbegriff in zwei Wellen
  (2008–2012, 2021–), Verbesserungsrate Median 6,1 %/a (Klasse H01M4/5825,
  12.145 Patente im Graph), Zykluszeit 11,0 Jahre, 96 % der Anmeldungen 2021–26
  aus China, nach CPC überwiegend Recycling (Y02W/B09B/C02F, Brunp-Gesellschaften);
  Forschung 5.821 Werke, Anteil 0,6 → 5,2 je 10.000; Förderebene leer (3 Signale).
  Sechs Seiten, Abschnitt 7 (Einordnung) als gekennzeichneter Entwurf.
- **Field Watch** — `docs/samples/field_watch_food_2026-W38.pdf` (Beispielkunde
  Molkerei-/Lebensmittel-Mittelstand, Felder Präzisionsfermentation, pflanzliche
  Milchalternativen, faserbasierte Verpackung): je Feld und Ebene die Woche gegen
  den Median der vier Vorwochen (Präzisionsfermentation Markt 9 vs. 3,5 = +157 %,
  Wissenschaft 5 vs. 3), 12 Quartale auf festem Quellenpanel, Signale der Woche
  mit Quelle, neue Akteure (Ferm Labs, Amai Proteins, Formo …), Nester, dünne Zellen.
  Fünf Seiten, eine je Feld.

Befund aus dem Bau: die Wochenzahlen sind bei FOOD-Feldern einstellig — das Blatt
zeigt Bewegung, das Quartal Richtung; die Ehrlichkeit „dünne Zelle" ist Teil des
Formats, nicht ein Mangel. Der Reifegradblock rechnet über die
CPC-Anker der Kundendatei (`pipeline/field_watch.quant_block`: `tir_trajectory`,
Zykluszeit, Zentralität) — ohne Embedding, ohne GPU; die Anker sind der
Owner-Checkpoint des Setups.

## 6. Weg dorthin (90 Tage)

| Wann | Was | Ergebnis |
|---|---|---|
| Woche 1–2 (bis 03.10.) | `scripts/field_watch.py <feld>` + PDF-Rendering; drei Pilotfelder (LFP-Zellen, Perowskit, Präzisionsfermentation — Messblöcke liegen vor) | drei Muster-Sheets, gleichzeitig der Beleg, ob die Scorecard ohne Redaktion abgabetauglich ist |
| Woche 3 | Preisblock auf `preview.html` statt „scoped and quoted"; `trends/clients/` mit htpasswd; Rechnungsvorlage | Website verkauft mit Zahl |
| 01.10. | Launch `/trends` ohne `noindex` | Sichtbarkeit beginnt |
| Oktober | Suwelack-Kontakt anschreiben (Präzisionsfermentation als Muster); 10 Direktkontakte; 4 LinkedIn-Posts mit je einem Sheet-Ausschnitt | 3–5 Gespräche |
| November | erstes Sheet verkauft; Cron für Field Watch installiert (Merge nach `main`, dem Owner vorgelegt) | erster Umsatz |
| Dezember | zwei Field-Watch-Piloten (Pilotpreis 290 €/Monat für 6 Monate zulässig) | wiederkehrender Umsatz |
| Q1 2027 | Zielzustand aus Abschnitt 5 | 1.000–2.000 € Gewinn |

## 7. Kennzahlen, die zählen

Gespräche je Monat · verkaufte Sheets · Field-Watch-Kunden und -Felder ·
wiederkehrender Monatsumsatz · Newsletter-Abonnenten (heute 3) · Owner-Stunden
je Kunde. Nicht: Seitenaufrufe, Artikelzahl.

## 8. Kosten (Schätzung, nicht gemessen)

Workstation 24/7 (llama-server hält ~22 GB, GPU im Leerlauf 23 W gemessen,
System geschätzt 150–250 W im Mittel) ≈ 40–60 €/Monat Strom · Hetzner-Webhosting
+ Domain ≈ 15 € · Resend, Tailscale im Frei-Kontingent · Backups auf eigener
HDD. Zusammen **≈100–150 €/Monat**; die Gewinnrechnung nimmt 150 €.
Nicht enthalten: Anwalt (EU AI Act, TDM — läuft ohnehin), Buchhaltung.

## 9. Leitplanken

- **§44b UrhG:** Volltexte (`raw_content`) verlassen die Plattform nie; Sheets
  und Exporte enthalten Titel, Quelle, Link, eigene Zahlen und eigene Texte.
- **KI-Kennzeichnung (Art. 50 AI Act):** im Sheet je Absatz — Zahlen maschinell
  gerechnet, Einordnung vom Owner; kein Modelltext ohne Kennzeichen.
- **Ehrlichkeit:** TIR als relative Entwicklung; Vorlauf der Nester (Rücktest
  9/20, Median 6 Monate) ist eine Messung, kein Versprechen; Akteurabdeckung
  (Presse 13 %, Forschung 1 %, Patente 0 %) steht im Blatt; 2026 ist der erste
  volle Jahrgang mit 560 Quellen (Sammelrampe) — die Anteilsnormierung dämpft
  das, die Methodik-Seite sagt es.
- **Kein Methoden-USP:** GetFocus/TechNext messen gleich; das TechNext-Patent
  US12099572B2 ist US-only und für EU-Analysen kein Blocker.
- **Abweichung vom 26.08.:** Preise werden sichtbar. Das ist kein SaaS (keine
  Konten, kein Checkout), aber eine bewusste Änderung an „scoped and quoted" —
  Owner-Entscheid.

## 10. Risiken

| Risiko | Wirkung | Gegenmittel |
|---|---|---|
| Kein Publikum, keine Pipeline | kein erster Kunde | Direktansprache vor Reichweite; Muster-Sheets als Türöffner |
| Feld-Mapping je Kunde frisst Zeit | Setup > 1 Tag | Setup-Gebühr; Kaskade aus `dossier_quant` wiederverwenden |
| Scorecard ohne Redaktion nicht abgabetauglich | Field Watch trägt nicht | Woche 1–2 entscheidet das an drei Feldern, bevor verkauft wird |
| Akteure dünn | „wer bewegt das Feld" bleibt Untergrenze | lokale NER (GLiNER/spaCy) als erste Investition nach dem ersten Kunden |
| Ein Rechner, ein Stromkreis | Ausfall = Lieferverzug | Wochenrhythmus verträgt einen Tag Ausfall; Backups laufen (02:45) |
| Google „scaled content" auf 32 k KI-Artikeln/Monat | Reichweite bleibt aus | Reichweite ist nicht Teil der Rechnung |

## 11. Entscheidungen, die der Owner trifft

1. Preise sichtbar (Abweichung vom 26.08.) — ja/nein.
2. Field Watch als Kernprodukt (Option C aus der Field-Watch-Notiz) — ja/nein.
3. Startfelder für die drei Muster-Sheets — Vorschlag LFP, Perowskit,
   Präzisionsfermentation (Messblöcke vorhanden).
4. Erster Pilotkunde — Vorschlag der Suwelack-Kontakt (Abonnent seit 12.08.).
