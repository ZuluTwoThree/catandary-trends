# Morgen-Briefing (Nacht 2026-07-13 → 14)

Autonome Nachtarbeit an Welle 2. Alles auf `epic/alpha`, hinter Feature-Flags (Prod 3001 unberührt). Diese Datei sammelt, was von dir gebraucht wird.

## ⏳ Auf DICH wartend (Owner-Tasks)

1. **Stripe-Account (Testmode)** anlegen → API-Keys (test) in `.env`: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`. Ohne den kann der Checkout-/Webhook-Pfad nicht end-to-end getestet werden (Code ist gebaut, env-gated).
2. **Resend-DNS-Verifizierung** (SPF/DKIM für catandary.de im Resend-Dashboard) — ohne die stellt kein Magic-Link / Newsletter real zu. Der Auth-Flow ist mit Konsolen-Transport testbar gebaut.
3. **Preispunkte 3 Tiers** (Starter/Pro/Super Pro+, $100–500-Korridor) — Beträge nennen, dann lege ich die Stripe-Prices + Pricing-Seite final an.

## ❓ Entscheidungen (bis 7:30 zurückgestellt, gesammelt)

1. **Auth: custom Magic-Link statt NextAuth** — abhängigkeitsfrei gebaut, um Build-Risiko auf Next 16 zu vermeiden. Bitte absegnen oder Wechsel wünschen.
2. **Volltext-Fetcher (#11 W3.1):** braucht `trafilatura` (neuer Python-Dep). Ich habe ihn **nicht** unbeaufsichtigt installiert. OK, ihn in requirements aufzunehmen? Dann baue ich den Fetcher (größter Content-Qualitäts-Hebel).
3. **Lead-Tracking** (`docs/gtm/lead_tracking.md`): personenfreie, cookielose Zähl-Events — so bauen (kein Consent-Banner) oder anders?
4. **Filter-Bar einklappen + Lead-Time-Story-Grafik** — bewusst fürs UX-Gate zurückgestellt; baue ich nach deinem Blick.
5. **Prod-Merge:** `epic/alpha` ist ~20 Commits vor `dev`. Wann erster wellenweiser Merge (Auth/Paywall bleiben per Flag aus auf Prod)?

## ✅ In der Nacht erledigt

- **W0.6 Restore-Test voll verifiziert:** mit der von dir angelegten vector-Extension restauriert der Backup-Dump die `trends`-Tabelle vollständig (1.117.625 Zeilen inkl. Embeddings). Runbook: `docs/restore_runbook.md`.
- **W2.1 Magic-Link-Auth** (`#17`): abhängigkeitsfrei (kein NextAuth), HMAC-Session-Cookie, Resend-oder-Konsole-Transport, `/account` + Sign-in, Newsletter-Opt-in-Spiegel. End-to-end getestet. Hinter `AUTH_ENABLED` (Prod unberührt). **Entscheidung: custom statt NextAuth v5-beta** — Build-Risiko auf Next 16 vermieden; bitte absegnen oder Wechsel wünschen.
- **W2.2 Entitlement-Gating** + **W2.3 Stripe** (env-gated): Tier-Matrix (free/starter/pro/superpro), `TierGate` (Teaser + Upgrade-Karte), Pricing-Seite, Checkout+Webhook (dependency-free via fetch/crypto), Admin-CLI `set_user_tier.py`. Gating beidseitig getestet. Hinter `PAYWALL_ENABLED` (Default aus).
- Dev-Server auf **3004** läuft (Paywall aus = normaler Zustand) für dein Review: `/account/signin`, `/trends/pricing`.

- **W2.5 Newsletter-Sender** (`#16`): Resend-Batch, signierter One-Click-Unsubscribe (Python↔Frontend-Round-Trip getestet), Idempotenz (`sent_at`), Dry-Run. Cron-Zeile (Mo 9:00 generate && send) vorbereitet, auskommentiert bis DNS verifiziert.
- **W2.3 Stripe** (env-gated): Checkout + Webhook (dependency-free), wartet auf deinen Stripe-Account zum End-to-End-Test.
- **W2.7 Rechtstexte-Entwürfe**: `docs/legal/` (Impressum/Datenschutz/AGB/Widerruf) — **DRAFTs, Anwaltsprüfung nötig**, Platzhalter + AVV-Checkliste.
- **W0.6 vollständig verifiziert** (Restore mit vector-Extension: trends 1.117.625 Zeilen; Scratch-DB gedroppt, 161GB frei).

- **W2.6 Landing value-first**: „What's moving"-Leiste (steigende Cluster, Klartext + Radar-Link) über dem Grid. Sub-Hero existierte schon.
- **W3.7 Export** (Agentur-Segment): CSV-Export der Cluster + druckfähige **Dossier**-Seite (`/trends/foresight/dossier`), Pro-gated. Getestet.
- **W4 GTM-Assets**: `docs/gtm/` — Rollout-Stufenplan, Lead-Tracking-Plan, Segment-1-Pager.

### Zum Anschauen auf 3004 (Dev-Server, Paywall AUS = Normalzustand)
- `/trends` (Landing mit „What's moving"), `/trends/foresight/radar`, `/trends/foresight/evolution?vertical=HEALTH`
- `/trends/foresight/dossier?vertical=HEALTH`, `/trends/pricing`, `/account/signin` (Magic-Link-Flow, Link erscheint in der Konsole/Server-Log)

### z3 fertig + validiert (W1.5 / #45) — **deine Entscheidung nötig**
`patent_spnp_full_z3` gebaut (42,4M Knoten). **Benchmark klar besser als Default** (Spearman 0,700 vs 0,65). Aber Trajektorien zeigen einen **Trade-off**: z3 behebt die Hot-Domain-Kompression (Li-Batterie liest `full` fälschlich als „reifend", z3 korrekt „beschleunigt"), erkauft mit einem mundane-Artefakt (F16B). Ich habe z3 als `TIR_SUBSTRATE=fullz3` verdrahtet, **Default bei `full` gelassen** (produktsichtbarer Wechsel = deine Entscheidung). Empfehlung + Details in #45. → **Wechsel zu fullz3?**

### run_full_cycle (dein Wunsch) — erledigt
Sauber durch (exit 0): **917 neue Trends** akquiriert (368 auto-published bei conf≥0,85, 549 als Draft zurückgehalten), 0 Fehler, llama-server neu gestartet. Die neuen Signale sind live in der DB.

### W1.6 Mega-Taxonomie — Kandidaten fertig, **deine Kuratierung nötig**
LIFESTYLE-Discovery gefahren (46.877 Signale) → `lifestyle_mega.candidate.yaml`. **3 Kandidaten** für die Entertainment/Social/Culture-Lücke: `evolution_of_social_media_platforms` + `platformization_of_culture` (net-neu), `the_rise_of_the_creator_economy` (überlappt evtl. bestehendes). + 1 Split-Kandidat. Details + meine Einordnung in #40. → **Welche in `mega_trends.yaml`?** Danach fahre ich Retrain + Reclassify. (Dabei einen weiteren Post-Postgres-Bug im Proposer gefixt.)

### Gesamtstand Epic
Welle 0 ✅ · Welle 1 ✅ (bis auf z3-Validierung + W1.6-Kuratierung) · Welle 2 ✅ (bis auf Owner-Gates Stripe/DNS) · Welle 3 teilweise (Export ✅). Alle Tests grün (115 Python + Frontend-tsc). 4 Issues geschlossen (#28/#35/#38/#41).
