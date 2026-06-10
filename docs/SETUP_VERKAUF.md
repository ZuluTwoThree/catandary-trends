# Trend-Radar — Verkaufs- & Betriebs-Setup (Solo-Operator-Runbook)

Vom Code zum kaufbereiten Produkt in einem Nachmittag. Reihenfolge einhalten.

## 1. Stripe einrichten (≈ 45 Min, einmalig)

1. Stripe-Konto (https://dashboard.stripe.com) mit Firmendaten + USt-IdNr.
2. **Produkte anlegen:** „Radar Team" 249 €/Monat, „Radar Pro" 490 €/Monat —
   jeweils wiederkehrend, zzgl. Steuer (Stripe Tax aktivieren), SEPA-Lastschrift +
   Karte erlauben. Optional je ein Jahres-Preis (2.540 € / 4.998 €).
3. **Payment Links erzeugen** (je Produkt: „Zahlungslink erstellen", Felder
   „Firmenname" + „USt-IdNr." als Pflichtfelder ergänzen).
4. Links in `frontend/.env.local` eintragen:
   ```
   NEXT_PUBLIC_STRIPE_LINK_TEAM=https://buy.stripe.com/...
   NEXT_PUBLIC_STRIPE_LINK_PRO=https://buy.stripe.com/...
   ```
   Frontend neu bauen → die Landing Page verlinkt automatisch auf Stripe statt auf den
   Test-Mailto.
5. Agency-Tier läuft bewusst **nicht** über Payment Link, sondern über Stripe Invoicing
   nach Angebot (docs/sales/ANGEBOT_VORLAGE.md) — höherer Preis, Gespräch gehört dazu.
6. Benachrichtigung: Stripe-E-Mail bei neuer Subscription reicht als „Webhook" für den
   Solo-Betrieb. (Ein automatischer Webhook-Provisioner lohnt erst ab ~30 Kunden.)

## 2. E-Mail-Versand (≈ 20 Min, einmalig)

1. Resend-Konto (https://resend.com), Domain `catandary.de` verifizieren (SPF/DKIM).
2. In `.env`: `RESEND_API_KEY=re_...` und `BRIEFING_FROM="Catandary Trend-Radar <radar@catandary.de>"`.
3. Postfach/Alias `radar@catandary.de` einrichten (Empfang!) — alle CTAs zeigen darauf.
4. Testlauf: `python -m pipeline.briefing_generator --customer <id> --send`.

## 3. Produktion (bestehende Hetzner-Config + 2 Cron-Zeilen)

```cron
# Bestehende Pipeline (Feeds, LLM, Publish) — unverändert
# Trend-Radar Briefings: Montag 06:30, Versand
30 6 * * 1  cd /srv/catandary-trends && .venv/bin/python -m pipeline.briefing_generator --send
# Tägliche Watchlist-Alerts (Team+): Dienstag-Freitag 07:00
0 7 * * 2-5 cd /srv/catandary-trends && .venv/bin/python -m pipeline.briefing_generator --alerts --send
# Trial-Abläufe prüfen: täglich 08:00 (manuelle Liste reicht)
0 8 * * *   cd /srv/catandary-trends && .venv/bin/python scripts/radar_admin.py list --status active
```

`PORTAL_BASE_URL=https://catandary.de` in `.env` setzen, damit Briefing-Links stimmen.

## 4. Workflow: Vom Kauf zum ersten Briefing (< 15 Min pro Neukunde)

**Trial (aus Outreach/Demo):**
```bash
python scripts/radar_admin.py trial --name "Firma GmbH" --email kontakt@firma.de \
  --contact "Vorname Name" --verticals TECH,ECO --keywords "wasserstoff,kreislaufwirtschaft"
python -m pipeline.briefing_generator --customer <id> --send   # erstes Briefing sofort
# Portal-Link aus der CLI-Ausgabe in die Onboarding-Mail kopieren
```

**Zahlender Kunde (Stripe-Mail kommt rein):**
```bash
python scripts/radar_admin.py convert <id> --tier pro          # falls vorher Trial
# oder neu: python scripts/radar_admin.py add --tier pro --stripe-id cus_... ...
```

**White-Label aktivieren:**
```bash
python scripts/radar_admin.py set <id> --brand-name "Mandanten-Radar" \
  --brand-color "#1a472a" --brand-logo-url "https://kunde.de/logo.png"
```

**Kündigung:** `python scripts/radar_admin.py cancel <id>` + Subscription in Stripe beenden.

**MRR-Stand:** `python scripts/radar_admin.py mrr` — zeigt Distanz zum 3.000-€-Ziel.

## 5. Wochenrhythmus im Betrieb

| Wann | Was | Dauer |
|---|---|---|
| Mo 06:30 | Briefings gehen automatisch raus (Cron) | 0 |
| Mo 09:00 | Stichprobe: 2 Briefings im Outbox-Ordner/Portal gegenlesen | 30 Min |
| Mo + Di vorm. | Outreach-Block: 30 Erstkontakte + Follow-ups (docs/sales/OUTREACH.md) | 2× 3 h |
| Mi–Fr | Demos (docs/sales/DEMO_SCRIPT.md), Trial-Betreuung, Onboardings | nach Bedarf |
| Fr | Funnel-Tabelle aktualisieren, Antwortraten gegen Annahmen A1/A2 prüfen (BUSINESS_PLAN.md) | 30 Min |

## 6. Rechtliches (vor dem ersten zahlenden Kunden)

- Impressum + Datenschutzerklärung auf catandary.de um Radar-Verarbeitung ergänzen
  (gespeichert: Firmenname, Ansprechpartner, Empfängeradressen; Hosting Hetzner DE).
- AGB-Kurzfassung oder die Konditionen-Tabelle aus der Angebotsvorlage verwenden.
- AV-Vertrag als Muster bereithalten (Standard-DSGVO-Vorlage genügt für diesen Datenumfang).
- Quellenzitate: Briefings verlinken Originalquellen und enthalten eigenständige Texte —
  presserechtlich unkritisch; bei Weitergabe (White-Label) bleibt die Quellenangabe Pflicht
  (steht so in der Angebotsvorlage).
