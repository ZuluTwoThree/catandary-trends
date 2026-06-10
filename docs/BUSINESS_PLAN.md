# Catandary Trend-Radar — Geschäftsplan & 90-Tage-Umsatzpfad

**Stand:** 2026-06-10 · **Variante:** Branch `product/trend-radar` (isoliert vom Hauptstand)
**Ziel:** ≥ 3.000 € MRR innerhalb von 90 Tagen ab erstem Verkaufsversuch, betreibbar von einer Person.

---

## 1. Produktentscheidung

**Catandary Trend-Radar** ist ein produktisiertes B2B-Abo: ein **personalisiertes, wöchentliches
Trend-Briefing** (Deutsch, E-Mail + Web-Portal) auf Basis der bestehenden Catandary-Pipeline —
4.700+ kuratierte Trend-Artikel aus 43 verifizierten Primärquellen, 8 Industrie-Vertikale,
PESTEL- und Mega-Trend-Taxonomie, CRS-Scoring, semantische Suche.

Der Kunde konfiguriert einmalig:
- **Vertikale** (FOOD/TECH/HEALTH/ECO/DESIGN/FASHION/BIZ/LIFESTYLE)
- **Watchlist** (eigene Keywords: Wettbewerber, Technologien, Themen)
- **Branding** (Logo/Farbe — White-Label ab Pro-Tier)

Danach läuft alles automatisch: Pipeline sammelt → klassifiziert → generiert → Briefing-Generator
selektiert pro Kunde die Top-Signale der Woche → Versand + Portal-Update. **Grenzkosten pro
zusätzlichem Kunden: ~0 € und ~0 Minuten** (lokale LLMs, kein API-Volumen, kein manueller
Redaktionsaufwand). Genau das macht es solo-tauglich.

### Warum dieses Produkt (und nicht die Alternativen)

| Option | Verworfen weil |
|---|---|
| Self-Serve-SaaS (29–99 €/Monat, Dashboard-Zugang) | Braucht 30–100 Kunden in 90 Tagen → erfordert Inbound-Traffic/SEO/Ads, die ein No-Name-Solo in 90 Tagen nicht aufbaut |
| Paid Newsletter (B2C, 9–29 €/Monat) | Gleiche Volumen-Falle, dazu hoher Churn |
| Beratung/Workshops auf Trend-Basis | Skaliert nicht, ist kein wiederkehrender Produktumsatz, Delivery frisst den Solo-Operator |
| Datenlizenz/API an Großkunden | Sales-Cycle 6–12 Monate, Procurement-Hürden — unvereinbar mit 90 Tagen |

**Productized Subscription mit 249–890 €/Monat** ist der einzige Zuschnitt, bei dem **7–10 Kunden
reichen**, der Sales-Cycle kurz ist (Einzelentscheider) und Delivery automatisiert bleibt.

---

## 2. Zielkunde (ICP)

**Primär: Innovations-, Trend- und Strategieberatungen im DACH-Raum, 1–20 Mitarbeiter.**

- **Schmerz:** Berater verbringen 1–2 Tage/Monat mit manueller Trend-Recherche pro Mandat.
  Etablierte Tools (WGSN, Trendwatching Premium, Stylus) kosten 8.000–30.000 €/Jahr und sind
  englisch/global statt DACH-tauglich.
- **Kaufverhalten:** Inhaber entscheidet selbst, Budget 200–900 €/Monat ist Portokasse gegen
  einen Beratertag (1.200–1.800 €). Sales-Cycle: 1–3 Gespräche.
- **Hebel:** White-Label — die Beratung verschickt das Briefing unter eigener Marke an ihre
  Endkunden und macht aus 490 € Einkauf 2.000–3.000 € Retainer-Umsatz. Wir verkaufen kein
  Tool, sondern Marge.
- **Auffindbarkeit:** Sehr gut. LinkedIn-Suche „Innovationsberatung“, BDU-Mitgliederliste,
  Trendforscher-Szene (zukunftsInstitut-Umfeld, VDI-Arbeitskreise) — mehrere hundert
  identifizierbare Firmen in DACH.

**Sekundär: Innovationsmanager im Mittelstand (100–2.000 MA)** — kaufen Solo/Pro-Tier als
internes Radar. **Tertiär: Kommunikations-/Markenagenturen** — nutzen Briefings für
Pitch-Vorbereitung und Kunden-Newsletter.

---

## 3. Pricing

| Tier | Preis/Monat | Leistungsumfang |
|---|---|---|
| **Radar Solo** | **249 €** | 2 Vertikale, 10 Watchlist-Keywords, wöchentl. Briefing (DE), Portal-Zugang, 1 Empfänger |
| **Radar Pro** | **490 €** | Alle 8 Vertikale, 30 Keywords, **White-Label** (eigenes Logo/Farbe), bis 5 Empfänger, Mega-Trend-Monatsreport |
| **Radar Agency** | **890 €** | Wie Pro, plus **3 getrennte Mandanten-Radare** (eigene Konfiguration + Branding je Endkunde), Weitergaberecht |

- Jahreszahlung: −15 % (verbessert Cashflow, senkt Churn).
- **14 Tage Test ohne Kreditkarte** — Token-Portal + 2 echte Briefings. Das Produkt verkauft
  sich über die erste Briefing-Mail, nicht über Folien.
- Preisanker im Pitch: „Ein WGSN-Seat kostet 10.000 €+ im Jahr. Ein einziger Beratertag kostet
  1.500 €. Radar Pro kostet 16 € pro Werktag.“

**Zahlungsabwicklung:** Stripe Payment Links (Solo/Pro) — kein Checkout-Code, PCI-frei,
SEPA + Kreditkarte, Kunde kann *morgen* kaufen. Agency-Tier per Rechnung (Stripe Invoicing).
Onboarding nach Zahlung: 1 CLI-Befehl, < 5 Minuten manuelle Arbeit pro Neukunde.

---

## 4. Positionierung

> **„Das Trend-Radar für den DACH-Mittelstand und seine Berater: 43 internationale
> Primärquellen, 8 Branchen, jede Woche auf Deutsch in Ihrem Postfach — unter Ihrer Marke,
> wenn Sie wollen. Zum Preis von einem Beratertag pro Quartal.“**

Differenzierung:
1. **Deutsch + DACH-Fokus** — WGSN/Trendwatching liefern global/englisch; wir liefern
   verwertbar für deutsche Kundenkommunikation.
2. **White-Label by design** — kein etabliertes Trend-Tool erlaubt Weitervermarktung; wir
   machen sie zum Kernfeature.
3. **Primärquellen-Transparenz** — jedes Signal verlinkt die Originalquelle; kein Aggregator-Nebel.
4. **Preis** — Faktor 10–20 unter Enterprise-Tools, ohne „Demo buchen“-Theater.

---

## 5. Go-to-Market: der 90-Tage-Pfad zu 3.000 € MRR

### Kanal

**Direktansprache (LinkedIn + E-Mail) durch den Gründer.** Kein Ads-Budget, kein SEO-Hoffen.
Listenbau aus: LinkedIn Sales Navigator („Innovationsberatung“, „Trendforschung“,
„Foresight“ DACH), BDU-Verzeichnis, Aussteller-/Speakerlisten einschlägiger Konferenzen
(z. B. Zukunftskongress, TREND FORUM), Agentur-Rankings (W&V, Horizont).
**Realistisch identifizierbar: 400–600 passende Firmen.** Der Plan braucht 360 Kontakte → Markt
ist groß genug, aber nicht beliebig — siehe kritische Annahme A5.

### Wochenplan

| Phase | Wochen | Aktivität | Output |
|---|---|---|---|
| Setup | 1–2 | Liste (150 Accounts), Stripe-Links live, Demo-Radar mit echtem Briefing, eigenes LinkedIn-Profil schärfen | Verkaufsfähig ab Tag 10 |
| Welle 1 | 3–6 | 30 personalisierte Erstkontakte/Woche (15 LinkedIn + 15 E-Mail), je Kontakt 2 Follow-ups | 120 Kontakte |
| Welle 2 | 7–10 | Weitere 30/Woche + Demos + Trials betreuen; jede Demo endet mit Trial-Aktivierung im Gespräch | 240 kum. |
| Abschluss | 11–13 | Trials konvertieren, Referenzen einholen, Welle 3 (120 Kontakte) anlaufen lassen | 360 kum. |

Aufwand: 30 Erstkontakte + Follow-ups + 2–4 Demos ≈ **10–12 h/Woche Vertrieb** — solo machbar,
weil Delivery automatisiert ist.

### Funnel-Rechnung (konservativ)

| Stufe | Rate | Ergebnis aus 360 Kontakten |
|---|---|---|
| Antwort (personalisiert, klarer Schmerz, Trial-CTA) | 10 % | 36 Antworten |
| Antwort → Demo/Gespräch | 60 % | 22 Demos |
| Demo → Trial (14 Tage, ohne Karte, im Gespräch aktiviert) | 70 % | 15 Trials |
| Trial → zahlend (Produkt liefert 2 echte Briefings) | 60 % | **9 Kunden** |

### Umsatzrechnung

Erwarteter Mix bei 9 Kunden (Beratungen bevorzugen Pro/Agency wegen White-Label):

| Tier | Kunden | MRR |
|---|---|---|
| Solo (249 €) | 4 | 996 € |
| Pro (490 €) | 4 | 1.960 € |
| Agency (890 €) | 1 | 890 € |
| **Summe** | **9** | **3.846 €** |

→ **Puffer von 846 € über Ziel** (≈ 28 %). Selbst ohne den Agency-Abschluss und mit nur
3 Pro-Kunden stehen 2.466 € — dann fehlen 2 weitere Solo-Kunden, die Welle 3 (Woche 11–13,
+120 Kontakte) liefert. Break-even-Szenario rein mit Solo-Tier: 13 Kunden nötig — auch das
liegt im Funnel-Korridor, wenn Welle 3 durchläuft.

Reihenfolge der Abschlüsse (erwartet): Wochen 5–7 erste 2–3 Solo/Pro aus Welle 1,
Wochen 8–11 der Block aus Welle 2 (4–5 Kunden inkl. erstem Agency über Referenz aus Welle 1),
Wochen 12–13 Rest aus Trial-Konversionen.

### Kritische Annahmen — woran der Plan scheitert

| # | Annahme | Risiko, wenn falsch | Frühindikator & Gegenmaßnahme |
|---|---|---|---|
| A1 | **10 % Antwortrate** auf personalisierte Erstansprache | Bei 5 % halbiert sich der Funnel → 4–5 Kunden ≈ 1.700 € | Nach 60 Kontakten messen; unter 7 %: Messaging-Variante B (Beispiel-Briefing direkt anhängen), Kanalmix Richtung Telefon |
| A2 | **Trial→Paid 60 %** | Bei 30 % nur 4–5 Kunden | Trial-Engagement tracken (Portal-Logins, Mail-Opens); inaktive Trials in Woche 1 anrufen |
| A3 | **Briefing-Qualität überzeugt deutschsprachige Profis** | Churn/Nicht-Konversion trotz Interesse | Vor Welle 1: 3 Pilot-Briefings an befreundete Berater, Feedback einarbeiten |
| A4 | Solo-Operator hält **10–12 h/Woche Vertrieb** 13 Wochen durch | Funnel verhungert oben | Feste Vertriebsblöcke (Mo/Di vormittags); Delivery ist automatisiert, darf nicht als Ausrede dienen |
| A5 | **Markttiefe:** ≥ 400 erreichbare ICP-Accounts in DACH | Welle 3 findet keine frischen Kontakte | Ab Woche 8 Sekundär-ICP (Innovationsmanager Mittelstand) in die Listen mischen |
| A6 | White-Label erzeugt **Agency-Nachfrage** | Ohne Agency-Tier fehlen 890 € → durch 2× Solo oder 1× Pro + 1× Solo ersetzbar | Agency aktiv erst ab Woche 7 pitchen, wenn Referenz-Logos existieren |

**Größtes Einzelrisiko:** A1 × A2 multiplizieren sich. Worst Case (5 % Antwort, 30 % Trial-Conversion)
ergibt 2–3 Kunden ≈ 1.000 € MRR nach 90 Tagen — dann ist das Produkt nicht tot, aber der
Zeitplan um ~90 Tage gestreckt. Der Plan steht und fällt mit der Disziplin im Outreach, nicht
mit der Technik.

---

## 6. Delivery-Betrieb (Solo-Tauglichkeit)

| Tätigkeit | Aufwand | Automatisierung |
|---|---|---|
| Briefing-Erzeugung + Versand | 0 min/Woche | Cron: `python -m pipeline.briefing_generator --send` |
| Pipeline (Feeds → LLM → Publish) | bereits automatisiert | bestehende Cron-Kette |
| Neukunden-Onboarding | < 5 min | `python scripts/radar_admin.py add ...` |
| Kündigungen | < 2 min | `radar_admin.py cancel` + Stripe |
| Qualitäts-Stichprobe | 30 min/Woche | manuell (bewusst) |
| Support | < 1 h/Woche erwartet | E-Mail |

**Gesamt-Delivery: < 2 h/Woche bei 10 Kunden.** Kein Team, keine Skalierungsfalle bis ~50 Kunden.

---

## 7. Erfolgsmaßstab (Abgleich mit Zielvorgabe)

| Kriterium | Status |
|---|---|
| Bestehender Code unverändert | ✔ Variante lebt in eigenem Worktree/Branch `product/trend-radar` |
| Variante lauffähig | ✔ siehe README → Trend-Radar; verifiziert per Testlauf |
| Kunde könnte morgen kaufen | ✔ Stripe Payment Link + `radar_admin.py add` + erstes Briefing in < 1 h |
| Vollständiger Verkaufsweg | ✔ `docs/sales/` — Pitch, Outreach-Sequenzen, Pricing, Angebot, Einwände |
| 90-Tage-Pfad durchgerechnet | ✔ Abschnitt 5, inkl. kritischer Annahmen und Abbruchszenarien |
