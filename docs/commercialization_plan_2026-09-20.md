# Kommerzialisierungsplan — Pivot „gemessene Lage je Feld"

> **Intern, Arbeitsdokument für den Owner** (Auftrag 2026-09-20). Setzt auf
> `docs/business_model_2026-09-19.md` (Modell) und den Musterblättern in
> `docs/samples/` auf. Ziel bleibt: **1.000–2.000 € Gewinn je Monat** aus dem
> vorhandenen Bestand, sales-led, ohne SaaS. Der Plan ist in Wochen ab dem
> 22.09.2026 gerechnet und hat drei Entscheidungstore; jedes Datum ist absolut.
> Ehrlichkeitsregeln der Launch-Site gelten überall (kein Methoden-USP, TIR =
> relative Entwicklung, keine Früherkennungs-Claims).

## 0. Der Pivot in einem Absatz

Bis zum 19.09. war das Produkt ein *geschriebener* Bericht (Dossier), der nie
abgabetauglich wurde. Ab jetzt ist das Produkt eine *gemessene* Lage je
Technologiefeld über vier Ebenen — Wissenschaft, Patent, Förderung, Markt — als
Blatt, als Wochen-Abo und als Arbeitstag. Geschrieben wird ein Absatz, und den
schreibt der Owner. Die beiden Muster (LFP-Sheet, Field Watch FOOD W38) belegen,
dass die Blätter ohne Redaktion aus der DB fallen; alles, was jetzt fehlt, ist
Verkauf und ein sauberer Betriebspfad.

## 1. Das Angebot, verkaufsfertig

| | **Technology Trajectory Sheet** | **Field Watch** | **Hypercare-Tag** |
|---|---|---|---|
| Was | ein Feld, 6 Seiten: Reifegrad-Karte, vier Ebenen 1990–heute, 12 Quartale, Anmelder/Klassen, Akteure, Nester, dünne Zellen, Einordnung, Methodik | 3 Felder, wöchentliches Blatt (5 Seiten) + Quartals-Scorecard (= Sheet je Feld) | ein Tag live an den Werkzeugen mit dem Team des Kunden |
| Preis | **1.490 €** einmalig | **390 €/Monat**, +90 € je weiteres Feld, **Setup 900 €**; Pilot 3 Monate zu 290 €/Monat | **1.200 €/Tag** (+ Reise) |
| Laufzeit | 5 Werktage ab Feldfreigabe | 12 Monate, jährlich fakturiert; Pilot monatlich | — |
| Lieferung | PDF per Mail + 30-min-Durchsprache | PDF Montag bis 09:00 + Kundenseite `trends/clients/<kunde>/` (htpasswd) | vor Ort oder Tailscale-Share |
| Feld-Definition | Owner mappt die Kundenphrase auf Suchbegriffe + CPC-Anker, Kunde gibt frei (Checkpoint) | dito je Feld im Setup | — |
| Nicht enthalten | Prognose, Empfehlung, fremde Volltexte, Rechtsrahmen (auf Wunsch als gekennzeichneter Anhang, +390 €) | dito | — |
| Upsell | → Field Watch (Setup entfällt, wenn das Sheet-Feld übernommen wird) | → Sheet für ein viertes Feld, → Tag | → Field Watch |

Namen auf der Website: *Trajectory Sheet*, *Field Watch*, *Analyst Day* (Englisch,
wie die ganze Site). „Super Pro+" und „Individual analyses" werden durch diese
drei ersetzt — die alten Namen erklärten nichts.

**Was das Sheet verspricht (und was nicht):** jede Zahl mit n, Fenster, Methode;
Take-off, Vorlauf und Verbesserungsrate als *Messung* aus dem Korpus; dünne
Zellen stehen im Blatt. Kein „wir erkennen früh", kein „einzigartige Methode".

## 2. Positionierung und Botschaft

- **Ein Satz:** *We measure how a technology field moves across science, patents,
  funding and market — from 21.9 M dated signals since 1990 — and hand you the
  numbers, not a narrative.*
- **Drei Belege, die auf die Site dürfen:** 18,7 M Patente mit Zitationsgraph;
  45,5 M Forschungswerke; 658 kuratierte Quellen in acht Vertikalen (DACH-stark).
  Alle Zahlen live aus der Methodik-Statistik, nicht aus dem Kopf.
- **Abgrenzung:** GetFocus/TechNext messen mit derselben SPNP-Methode zu
  Enterprise-Preisen. Unser Unterschied ist nicht die Methode, sondern (a) vier
  Ebenen in einem Korpus, (b) Preise, die ein Mittelständler ohne Budgetrunde
  freigeben kann, (c) die Ehrlichkeit der Darstellung — „wo die Evidenz dünn ist"
  ist eine Tabelle im Blatt.
- **Was nie gesagt wird:** Früherkennung, Prognose, „KI-gestützte Beratung",
  Kundenlogos, Methoden-USP. TIR heißt „improvement rate, relative".

## 3. Zielkunden und wie die Liste entsteht

Vier Segmente, priorisiert nach Nähe zum Korpus und zur Kasse:

| # | Segment | Warum | Erstliste (30 Namen) kommt aus |
|---|---|---|---|
| 1 | Innovations-/Technologiemanagement im DACH-Mittelstand, FOOD/ECO/HEALTH/TECH | kauft ohne Ausschreibung, hat konkrete Felder, kennt keine Patentanalytik | dem Newsletter (Suwelack, seit 12.08.), Presse-Akteuren der starken Felder (Extraktion), Startup-Korpus DE (2.518 Firmen), Bodensee/Allgäu-Nähe |
| 2 | Transferstellen, Fraunhofer-/Hochschul-Institute | brauchen Marktebene zu ihrer Wissenschaftsebene | Institutionen-Tabelle des Forschungskorpus (`research_institutions`) für die Pilotfelder |
| 3 | VC-/CVC-Associates (Cleantech, FoodTech, Digital Health) | Sheet als Vorstufe zur Due Diligence | Funding-Signale der letzten 12 Monate (Investoren-Feld in `startup_events`) |
| 4 | Patentanwälte | verkaufen Landschaften für 3–5 k weiter; Sheet = Vorstufe für 1,5 k | Kanzleien mit Elektrochemie-/Biotech-Schwerpunkt, Region zuerst |

FASHION/DESIGN bleiben Schaufenster (Entscheid 20.09.): Felder daraus nur, wenn
ein Kunde sie bringt (Textilfasern, Biomaterialien — messbar über die Materialklassen).

## 4. Vertriebsprozess

```
Kontakt → 20-min-Gespräch → Feldprobe (1 Seite, kostenlos) → Angebot → Sheet
       → Field-Watch-Pilot (3 Monate) → Jahres-Abo → Analyst Day
```

- **Feldprobe** = Abschnitt 1 des Sheets („Auf einen Blick") für das Feld des
  Interessenten, 15 Minuten Rechenzeit, kein Text. Sie ist der Türöffner: die
  Zahlen des eigenen Feldes überzeugen, nicht das Muster.
- **Gesprächsleitfaden** (20 min): welche drei Felder, wer liest das Blatt, was
  wird heute dafür gekauft (Berater, Reports, nichts), welche Entscheidung hängt
  daran. Wer keine Entscheidung nennt, bekommt die Feldprobe und den Newsletter,
  kein Angebot.
- **Angebot** = einseitig, Leistungsbeschreibung aus Abschnitt 1, Preis, Termin.
  Rechnung nach Lieferung (Sheet) bzw. vorab (Field Watch, jährlich; Pilot monatlich).
- **Annahmen für die Rechnung:** 10 Direktkontakte → 3 Gespräche → 2 Feldproben →
  1 Angebot → 0,5 Auftrag. Für ein Sheet je Monat braucht es also ~20 Kontakte je
  Monat in den ersten drei Monaten; danach trägt Weiterempfehlung und LinkedIn.

## 5. Kanäle und Kadenz

| Kanal | Kadenz | Inhalt |
|---|---|---|
| Direktansprache (Mail/LinkedIn-Nachricht) | 20 je Monat, Di/Do | drei Sätze: Feld benennen, eine Zahl aus der Feldprobe, Gespräch anbieten |
| LinkedIn-Post | 1 je Woche, Mi | ein Sheet-Ausschnitt (Chart + drei Zahlen), z. B. „96 % der LFP-Anmeldungen 2021–26 sind chinesisch — und es ist eine Recycling-Welle"; Link auf die Site |
| Website | ab 01.10. | Preisblock, drei Muster-PDFs, „Request a field probe" |
| Newsletter | Di 09:00 (läuft) | je Ausgabe ein Kasten „Field of the week" mit drei Zahlen; Versand nach Freigabe |
| Empfehlung | ab erstem Kunden | jedes Sheet endet mit „Für welches Feld würde ein Kollege das brauchen?" |

Keine Messen, keine Anzeigen, kein Content-SEO — Reichweite ist nicht Teil der
Rechnung (Google-Risiko auf 32 k KI-Artikeln/Monat).

## 6. Arbeitspaket Website (`docs/launch/preview.html`, bis 30.09.)

1. Service-Band umbauen: drei Karten *Trajectory Sheet 1.490 € · Field Watch
   390 €/mo · Analyst Day 1.200 €* mit je einem Satz, „what's inside", „not
   included"; Hinweis „prices excl. VAT, invoiced, no checkout".
2. Muster-PDFs als Download (`/samples/…`), im Kopf „Sample — real data, example
   customer"; das Sheet-Feld LFP, das Field Watch FOOD.
3. CTA „Request a field probe" → `mailto:contact@catandary.de?subject=Field probe: <your field>`;
   FAQ-Eintrag „What is a field?" (Phrasenliste + Patentklassen, vom Analysten
   gemappt, vom Kunden freigegeben).
4. Kommentar-Relikte entfernen (`scripts/corpus_research.py` steht noch im
   HTML-Kommentar, ist seit 19.09. gelöscht); Ehrlichkeits-Matrix
   (`docs/launch/02_product_truth_matrix.md`) um die drei Produkte ergänzen.
5. Methodik-Seite: Abschnitt „Field Watch method" (Ebenenregel, Quellenpanel,
   Take-off-Regel, K-Kalibrierung bis 2019) — derselbe Text wie im Blatt.
6. Kundenbereich: `trends/clients/.htaccess` + htpasswd auf dem Webspace,
   ausgenommen vom Publisher-Löschen (Allowlist wie `newsletter/**`), noindex.

## 7. Arbeitspaket Produkt (aus `scripts/field_watch_demo/` → Betrieb)

| Wann | Was | Aufwand |
|---|---|---|
| ~~W39~~ **erledigt 20.09.** | `scripts/field_watch.py <kunde>`: liest `fields/<kunde>.yaml` (Name, Felder, Suchbegriffe, CPC-Anker), rechnet Woche + Quartale, schreibt `field_watch_runs` und PDF nach `data/field_watch/<kunde>/<woche>.pdf` | — |
| ~~W39~~ **erledigt 20.09.** | Reifegradblock ohne Archiv-Tag: `pipeline/field_watch.quant_block` über die CPC-Anker (`tir_trajectory`, `cycle_time`, Zentralitäts-Peak portiert) | — |
| ~~W40~~ **erledigt 20.09.** | Feldprobe `field_watch.py --probe "<phrase>"` (Seite 1 + Kandidatenklassen; ohne `--cpc` GPU-Handover) | — |
| ~~W41~~ **Vorlage steht** | `weekly_field_watch.sh` + Crontab-Zeile Sa 12:30 (Notiz in die Montags-Mail, `ops_events`); **scharf erst mit dem Merge nach `main`** | Owner |
| ~~W42~~ **erledigt 20.09.** | Kundenseite: `field_watch.py --export` baut `index.html` + PDFs; Upload per SFTP nach `trends/clients/<kunde>/` (Publisher-Schutz `OWNER_SUBTREES`, `.htaccess`-Vorlagen) | — |
| nach erstem Kunden | lokale NER auf dem Signalpfad (GLiNER/spaCy), damit Akteure zählbar werden; OA-Lücke Materialforschung nur bei FASHION/DESIGN-Feld | 3 Tage |
| nach zweitem Kunden | Rechtsrahmen-Anhang (artikelweise Rechtstexte, `pipeline/legal_text.py` existiert) als gekennzeichneter Zusatz | 2 Tage |

Regeln: kein Modelltext im Produktpfad (der Pulse-Absatz bleibt Pulse); jede
Zahl im Blatt hat n, Fenster, Methode; Tests für Ebenenregel, Panel und
Take-off (`tests/test_field_watch.py`); README + Handbuch im selben Commit.

## 8. Administration und Recht (bis 15.10.)

- **Leistungsbeschreibung** je Produkt (eine Seite, aus Abschnitt 1) + Kurz-AGB:
  Korpusmessung, keine Markt- oder Anlageberatung, keine Gewähr für
  Vollständigkeit fremder Quellen, Nutzungsrecht intern beim Kunden,
  Weitergabe an Dritte nur mit Quellenvermerk „Catandary". Anwalt für die
  Kurz-AGB einmalig (~500 €), zusammen mit dem laufenden AI-Act-Mandat.
- **Rechnung/USt:** Regelbesteuerung, Reverse-Charge bei EU-Kunden; Rechnungs-
  vorlage mit Leistungszeitraum (Field Watch jährlich = Leistungszeitraum 12 Monate).
- **KI-Kennzeichnung:** Blätter tragen den Fuß „deterministische Abfragen, kein
  Modelltext; Einordnung vom Analysten" — bleibt wahr, solange kein Modell in
  den Produktpfad kommt. Der Pulse-Absatz (Gemma) darf nur mit Badge ins Blatt.
- **§ 44b UrhG:** Blätter enthalten Titel, Quelle, Link, eigene Zahlen; nie
  `raw_content`. Der Kundenbereich ist kein Weiterverbreiten fremder Texte.
- **Datenschutz Kundenbereich:** htpasswd, kein Tracking, Datenschutzhinweis
  auf der Kundenseite; Kundendaten (Name, Felder) nur in `fields/<kunde>.yaml`
  (nicht im öffentlichen Export, `.gitignore`).
- **Vertragsdauer Field Watch:** 12 Monate, Pilot 3 Monate monatlich kündbar.

## 9. Zeitplan und Tore

| Woche | Vertrieb | Produkt/Website | Tor |
|---|---|---|---|
| **W39** 22.–28.09. | Liste 30 Namen aus Abschnitt 3; Suwelack-Mail mit Feldprobe Präzisionsfermentation (liegt vor) | Website-Umbau (Abschnitt 6, Punkte 1–4); `field_watch.py` Teil 1 | |
| **W40** 29.09.–05.10. | Launch-Post 01.10. (LFP-Recycling-Welle); 10 Direktkontakte | Launch `/trends` ohne noindex; Feldprobe-Kommando | |
| **W41–42** 06.–19.10. | 10 Kontakte je Woche; 2–3 Gespräche | Cron + Kundenseite; AGB/Leistungsbeschreibung | |
| **W43–44** 20.10.–02.11. | erste Angebote; Post je Woche | Handbuchkapitel; Tests | **Tor 1 (31.10.): ≥ 5 Gespräche, ≥ 3 Feldproben** — sonst Segmentwechsel (Patentanwälte/VC vor Mittelstand) |
| **Nov** | erstes Sheet liefern; Pilot-Angebote | NER, wenn Kunde da | **Tor 2 (30.11.): ≥ 1 bezahlter Auftrag** — sonst Preis auf 990 €/Sheet senken und Feldprobe breiter streuen |
| **Dez** | 2 Field-Watch-Piloten | Scorecard-Lauf | |
| **Q1 2027** | Piloten → Jahres-Abo; Sheet je Monat | Rechtsrahmen-Anhang | **Tor 3 (31.01.): ≥ 2 Field Watch oder ≥ 3 Sheets verkauft** — sonst zurück auf Sheet + Analyst Day allein (Field Watch als Bonus statt Abo) |

Owner-Zeit: W39–42 ≈ 3 Tage/Woche (Bau + Site), danach ≈ 1 Tag/Woche Vertrieb +
Lieferung nach Auftrag (Sheet 1 Tag, Field Watch 1 h je Kunde/Woche).

## 10. Zahlen, an denen der Plan gemessen wird

Kontakte · Gespräche · Feldproben · Angebote · Aufträge (je Monat); wiederkehrender
Monatsumsatz; Owner-Stunden je Auftrag; Newsletter-Abonnenten (heute 3). Ziel
Q1 2027: 2 × Field Watch + 1 Sheet/Monat ≈ 2.270 € Umsatz, ≈ 2.100 € Gewinn.
Budget bis dahin: Betrieb ≈ 150 €/Monat, Anwalt einmalig ≈ 500 €, sonst nichts.

## 11. Risiken

| Risiko | Gegenmittel |
|---|---|
| Niemand antwortet (kein Publikum) | Feldprobe statt Pitch — die eigene Zahl öffnet; Tor 1 zwingt zum Segmentwechsel |
| Feld-Mapping frisst Owner-Zeit | Setup-Gebühr; Mapping-Kaskade aus `dossier_quant` portieren; Probe vor Angebot begrenzt den Aufwand auf 15 min |
| Kunde erwartet Empfehlung | Leistungsbeschreibung sagt „Messung"; Analyst Day ist der Ort für Interpretation |
| Wochenzahlen einstellig (FOOD) | Blatt zeigt Woche + Quartal; Erwartung im Gespräch setzen; Felder breit genug mappen |
| Sammelrampe 2026 verzerrt Quartale | festes Quellenpanel (eingebaut), Methodik-Seite sagt es |
| Modelltext rutscht in den Produktpfad | Regel in Abschnitt 7; Kennzeichnung im Fuß nur wahr ohne Modell |
| Ein Rechner | Wochenrhythmus verträgt einen Ausfalltag; Backups laufen |

## 12. Entscheidungen jetzt

1. Namen und Preise aus Abschnitt 1 freigeben (Sheet 1.490 / Field Watch 390 + 900 / Day 1.200; Pilot 290).
2. Preise sichtbar auf der Site (Abweichung vom 26.08.) — ja.
3. Erste Direktansprache: Suwelack mit der vorhandenen Feldprobe Präzisionsfermentation.
   — **Owner 20.09.: nein, ein anderer Kunde wird gewählt** (Owner-Wahl, nicht Teil des Plans).
4. Startpunkt Bau: `field_watch.py` in W39, Cron-Merge nach `main` erst nach Vorlage.

**Stand 20.09.2026 abends — 1, 2 und 4 umgesetzt (dev):** Preise und Namen auf
der Landing (`preview.html`, Owner lädt hoch), Muster-PDFs unter `/trends/samples/`,
Methodik-Abschnitt „How a field is measured", Kundenbereich `trends/clients/`
publisher-geschützt + `.htaccess`-Vorlagen; Produkt `scripts/field_watch.py`
(Wochenblatt, Sheet, Feldprobe, Export, `field_watch_runs`, Tests), Cron-Wrapper
`weekly_field_watch.sh` + Crontab-Zeile Sa 12:30 als Vorlage. Offen aus §7:
NER (nach erstem Kunden), Rechtsrahmen-Anhang (nach zweitem); aus §6: Upload der
Landing, htpasswd auf dem Webspace (Owner); aus §8: Leistungsbeschreibung/AGB.
