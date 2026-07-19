# Alpha Rollout & Lead-Generierung (Epic W4)

Entwurf für die Markteinführung der Alpha. Der Agent baut Assets + Tracking; das
Outreach führst du (Markt-Wissen, Kontakte).

## Rollout-Stufenplan

1. **Internes Go** — Alpha-Checkliste (`docs/alpha_checklist.md`, folgt) + UX-Gate
   bestanden, alle Dienste reboot-fest. Prod-Merge `epic/alpha` → `dev` → `main`
   wellenweise hinter Feature-Flags (Auth/Paywall zunächst **aus** auf Prod).
2. **Pilot (geschlossen)** — 3–5 handverlesene Kontakte je Segment. Zugang per
   `set_user_tier.py` (Admin-Override, kein Zahlungszwang). Feedback-Formular
   (unten). Auth **an**, Paywall **aus** für Piloten (voller Zugang).
3. **Öffentliche Alpha** — Pricing sichtbar, Stripe **Testmode** (Hinweis „Alpha
   preview"). Auth an, Paywall an, Testmode-Checkout.
4. **Live-Zahlungen** — separater Post-Alpha-Schritt: Stripe live, Rechtstexte
   final (Anwaltsprüfung), Widerruf-Checkbox im Checkout.

**Gate zwischen 1 und 2:** UX-Qualitäts-Gate + Owner-Freigabe je Prod-Merge.

## Zielsegmente (alle drei, Owner-Entscheid)

| Segment | Was zieht | Einstiegs-Deliverable |
|---|---|---|
| **B2B-Innovationsteams** | Radar, Lead-Time, Methodik-Trust | Trend-Radar + Foresight-Dossier |
| **Agenturen/Berater** | Export, Dossiers, Alerts | CSV/Dossier-Export je Kundenbranche |
| **Prosumer/Analysten** | Cluster-Explorer, Evolution, Suche | Self-Service, niedriger Einstiegspreis |

## Feedback-Formular (Pilot)

Minimal, 5 Fragen (als Google-Form o. ä. oder simple Seite):
1. Was hast du in den ersten 60 Sekunden verstanden?
2. Welche Ansicht war am nützlichsten (Radar / Evolution / Lead-Time / Cluster)?
3. Was hat gefehlt / verwirrt?
4. Würdest du dafür zahlen — welcher Tier/Preis?
5. Für welche konkrete Aufgabe würdest du es einsetzen?

## Erfolgs-Signale der Alpha

- ≥3 Piloten je Segment nutzen es ≥2×
- ≥1 „dafür würde ich zahlen" je Segment
- Newsletter-Signup-Conversion messbar (s. lead_tracking.md)
- 0 kritische UX-/Datenfehler im Pilotzeitraum
