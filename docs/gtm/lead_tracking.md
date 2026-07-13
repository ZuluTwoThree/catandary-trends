# Lead-Funnel-Tracking (Epic W4.2) — Plan

Ziel: die Akquise-Conversion messbar machen, **cookielos & aggregiert**
(Owner-/DSGVO-Vorgabe — kein Consent-Banner nötig).

## Ist-Zustand
`/api/track` erfasst nur `page_view`/`share` pro Trend (Tabelle `trend_metrics`).
Für den Lead-Funnel fehlt eine Event-Ebene.

## Vorschlag: `funnel_events` (aggregiert, personenfrei)

Eine schlanke Zähl-Tabelle statt Einzel-Events mit Personenbezug:

```
funnel_events(event TEXT, day DATE, count INT, PRIMARY KEY(event, day))
```

Events (nur Zähler, kein Nutzerbezug, keine IP):
- `landing_view` — Startseite geladen
- `foresight_view` — eine Foresight-Ansicht geöffnet (Radar/Evolution/…)
- `gate_view` — eine TierGate-Upgrade-Karte gesehen
- `signin_request` — Magic-Link angefordert
- `signup_complete` — Account erstmals angelegt
- `newsletter_optin` — Newsletter-Häkchen beim Signup
- `checkout_start` / `checkout_success` — Stripe (Testmode)

Increment per `INSERT … ON CONFLICT (event,day) DO UPDATE count = count+1`.
Kein Cookie, keine UTM-Speicherung mit Personenbezug (UTM nur zur aggregierten
Kampagnen-Zählung, falls überhaupt).

## Dashboard
Interne Seite `/ops/funnel` (Admin-gated) oder ein einfacher SQL-Report im
`monthly_source_check`-Stil: Signups/Woche, Gate→Signin→Signup-Rate,
Newsletter-Wachstum, Checkout-Rate. Erst nach Owner-OK bauen (kleiner Aufwand).

## Warum noch nicht gebaut
Bewusst als Plan zurückgestellt — die Event-Punkte hängen an den finalen
Landing-/Gate-Flows (UX-Gate) und an der Frage, ob wirklich alles personenfrei
bleiben soll. Ein Nachtbau würde die UX-Review-Fläche unnötig vergrößern.
Umsetzung: ein `bumpFunnel(event)`-Helper + Aufrufe an den 8 Punkten + Report.
