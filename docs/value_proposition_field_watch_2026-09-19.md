# Alternative Value Proposition: „Field Watch" — die Plattform als Messinstrument, nicht als Autor

> **Intern, Arbeitsdokument für den Owner** (Auftrag 2026-09-19): eine zweite
> Wertversprechen-Linie aus dem Bestand der Plattform, falls der Scouting-Bericht
> auch nach v8/v9 nicht abgabetauglich wird. Zahlen aus CLAUDE.md und den Läufen
> vom 18./19.09.; Ehrlichkeitsregeln der Launch-Site gelten (kein Methoden-USP,
> TIR = relative Entwicklung, keine Früherkennungs-Claims).

## 1. Der Befund, aus dem die Alternative folgt

Sieben Dossierversionen zum selben Thema und 48 Läufe insgesamt zeigen ein
stabiles Muster: **Alles, was die Plattform misst und zählt, hält.** Der
Messblock (10.605 Patente in drei CPC-Klassen, Take-off 2008, Zykluszeit 6,0
Jahre, Verbesserungsrate), die Signalhistorie je Ebene, die Anteilsnormierung,
die Bewegungstabelle aus dem Korpus — kein Leser, kein Prüfer, kein Owner hat je
eine dieser Zahlen beanstandet. **Alles, was das Modell schreiben muss, wackelt:**
Beschaffung fremder Primärquellen, Verdichtung zu einer belegten Aussage,
Urteil. Die drei abgenommenen Dossiers waren die, die am nächsten am Messen
lagen (Perowskit, LFP v9 mit DR-Vorlauf).

Der Scouting-Bericht ist der Versuch, das Schreiben auf das Messen zu setzen.
Die Alternative dreht es um: **das Messen ist das Produkt, das Schreiben ist
optional.**

## 2. Field Watch — was der Kunde bekommt

Der Kunde benennt drei bis zehn **Felder** (Technologien, Märkte, Regulierungs-
räume) in seinen Worten. Die Plattform liefert je Feld eine **laufende,
gemessene Lage**, nicht eine einmalige Recherche:

| Baustein | Quelle in der Plattform | Stand heute |
|---|---|---|
| **Reifegrad-Karte** je Feld: Patentklassen, Zykluszeit, Verbesserungsrate, Take-off je Ebene, Wissenschaft→Markt-Abstand | `dossier_quant`, TIR/SPNP auf 18,7 M Patenten, Ebenen aus `tiers.py` | läuft, deterministisch, je Feld ~2 min |
| **Bewegung je Ebene und Quartal**, anteilsnormiert (je 10.000 Signale der Ebene), mit repräsentativen Signalen und Akteuren | `dossier_corpus_evidence`, Cluster-Panel-Normierung, 1,1 M Trends + Signalraum | läuft (Runde 27), 0,6 s je Feld |
| **Wochen-Pulse** je Feld: Volumen gegen Vier-Wochen-Median, Cluster mit Labels, vier zentroid-nächste Papers | `research_pulse` (heute je Mega-Theme) → je Kundenfeld | Cron seit 18.09., Übertrag auf Kundenfelder = Konfiguration |
| **Nester und Neuheit**: dichte neue Themen im Feld, Alter, Erstauftritt je Ebene, neues Vokabular | `emerging.py`, Rücktest 9/20 Trends, Median-Vorlauf 6 Monate | läuft, Knopf; Vorlauf ehrlich als Messung, nicht als Versprechen |
| **Akteure**: wer bewegt das Feld, früh gegen spät, Startup-Korpus mit Evidenz-Timeline | Startup Explorer (#87), Extraktion | Presse 13 %, Forschung 1 %, Patente 0 % Akteurabdeckung → braucht lokale NER (Runde 27) |
| **Zeitschiene und Rechtsrahmen** | Regulatorik-Sweep, Kalender aus Faktenzettel, artikelweise Rechtstexte | einziger Baustein mit Web-Anteil; als „Rahmen" gekennzeichnet |
| **Ein Absatz Prosa** je Baustein, T = 0,2, nur Zahlen aus dem Messblock | Pulse-Schreiber (Gemma), keine Recherche | seit 04.09. ohne Beanstandung |

Lieferform: eine Owner-Seite je Kundenfeld (wie `/trends/foresight/research/pulse/<theme>`),
wöchentlich aktualisiert, exportierbar als PDF/CSV, plus Quartals-Scorecard. Kein
Dossier, keine Empfehlung. Die Beratung (Advisor) bleibt sales-led obendrauf.

## 3. Warum das trägt, wo das Dossier nicht trägt

1. **Kein fremdes Material nötig.** Jede Zahl kommt aus eigenen Tabellen, die
   Prüfkette entfällt, die Streichung entfällt, der Leser entfällt.
2. **Longitudinal statt punktuell.** Der Korpus ist 21,6 M Rohzeilen tief und
   seit 1990 datiert; sein Wert ist die Zeitreihe, nicht die Momentaufnahme.
   Ein Dossier wirft die Zeitreihe in einen Anhang, den kein Leser öffnet.
3. **Skaliert ohne GPU-Stunden.** Ein Feld kostet Sekunden bis Minuten Rechnung,
   kein 27B-Lauf von 40 Minuten mit ungewissem Ausgang.
4. **Ehrlich per Konstruktion.** „Wo die Evidenz dünn ist" ist kein Abschnitt,
   sondern eine Zelle in der Tabelle (0 Signale Förderung, 2 Wissenschaft).
5. **Passt zur Positionierung.** TIR als relative Entwicklung (Owner 25.07.),
   keine Früherkennungs-Claims, Methoden-Transparenz auf der Methodik-Seite.

## 4. Was fehlt, ehrlich

- **Akteure sind auf dem Signalpfad nicht zählbar** (Extraktion nur im Artikel-
  pfad). Ohne lokale NER bleibt „wer bewegt das Feld" eine Untergrenze aus der
  Presse. Das ist die erste Investition (GLiNER/spaCy, ~0,5 GB, Runde 27).
- **Feld-Definition durch den Kunden** muss auf CPC-Klassen und Korpusbegriffe
  gemappt werden — die Kaskade aus `dossier_quant` (Kernphrase, Dichteregel,
  Titel-Schärfung) kann das, braucht aber einen Owner-Blick je Feld (der
  Checkpoint aus Stufe 1, hier als Einrichtungsschritt).
- **Regulatorik bleibt Web.** Sie gehört als Rahmen dazu, nicht als Kern.
- **Die Bewegungszahlen sind sammelrampenabhängig** (2026 ist der erste volle
  Jahrgang mit 560 Quellen). Anteilsnormierung und Quellenpanel dämpfen das, die
  Methodik-Seite muss es sagen.
- **Kein Verkaufsargument „einzigartig"**: GetFocus und TechNext messen mit
  derselben SPNP-Methode. Unterschied ist Korpusbreite (acht Vertikale, vier
  Ebenen, DACH-Quellen) und die Ehrlichkeit der Darstellung — das ist die
  Positionierung, nicht die Methode.

## 5. Erster Schnitt (zwei bis drei Tage, kein neues Modell)

1. `scripts/field_watch.py <feld>`: Reifegrad-Karte + Bewegung je Ebene/Quartal
   + Nester im Feld + Akteure (Untergrenze) + Kalender aus dem Regulatorik-Sweep
   → eine JSON-Zeile in `field_watch_runs` (additiv) und eine Owner-Seite
   `/trends/foresight/fields/<slug>` nach dem Muster der Pulse-Seite.
2. Wochen-Cron nach dem Samstags-Ingester (12:30, nach dem Pulse), je Feld ~3 min.
3. Drei Pilotfelder aus den vorhandenen Dossier-Themen (Server-Virtualisierung,
   LFP-Zellen, Präzisionsfermentation) — dort liegen Messblöcke, Korpuszahlen
   und Vergleichsdossiers schon vor; die Scorecard muss nur reproduzieren, was
   in den Dossieranhängen steht.
4. Erst danach: Kundenfeld-Editor im Desk und PDF-Export.

## 6. Entscheidung, die der Owner treffen kann

- **A:** Scouting-Bericht bleibt Kernprodukt; Field Watch als Baustein darin
  (die Reifegrad- und Bewegungssektion sind Field Watch im Kleinen).
- **B:** Field Watch wird Kernprodukt („gemessene Lage je Feld, wöchentlich");
  das Dossier wird zur Sonderleistung, der Advisor bleibt sales-led.
- **C:** beides, mit Field Watch als Einstieg (Abo) und Dossier/Advisor als
  Upsell — entspricht dem Lead-Gen-Modell der Website (30 Tage frei, Analysen als
  Teaser, Super Pro+ und Individualanalysen verkauft).

Meine Empfehlung: **C**, mit dem ersten Schnitt aus Abschnitt 5 als Beleg, ob die
Scorecard ohne Redaktion abgabetauglich ist — das lässt sich in einer Woche an
drei Feldern zeigen, und die Antwort hängt nicht am Schreiber.
