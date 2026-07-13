# Morgen-Briefing (Nacht 2026-07-13 → 14)

Autonome Nachtarbeit an Welle 2. Alles auf `epic/alpha`, hinter Feature-Flags (Prod 3001 unberührt). Diese Datei sammelt, was von dir gebraucht wird.

## ⏳ Auf DICH wartend (Owner-Tasks)

1. **Stripe-Account (Testmode)** anlegen → API-Keys (test) in `.env`: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`. Ohne den kann der Checkout-/Webhook-Pfad nicht end-to-end getestet werden (Code ist gebaut, env-gated).
2. **Resend-DNS-Verifizierung** (SPF/DKIM für catandary.de im Resend-Dashboard) — ohne die stellt kein Magic-Link / Newsletter real zu. Der Auth-Flow ist mit Konsolen-Transport testbar gebaut.
3. **Preispunkte 3 Tiers** (Starter/Pro/Super Pro+, $100–500-Korridor) — Beträge nennen, dann lege ich die Stripe-Prices + Pricing-Seite final an.

## ❓ Entscheidungen (bis 7:30 zurückgestellt, gesammelt)

_(werden im Laufe der Nacht hier ergänzt)_

## ✅ In der Nacht erledigt

- **W0.6 Restore-Test voll verifiziert:** mit der von dir angelegten vector-Extension restauriert der Backup-Dump die `trends`-Tabelle vollständig (1.117.625 Zeilen inkl. Embeddings). Runbook: `docs/restore_runbook.md`.
- **W2.1 Magic-Link-Auth** (`#17`): abhängigkeitsfrei (kein NextAuth), HMAC-Session-Cookie, Resend-oder-Konsole-Transport, `/account` + Sign-in, Newsletter-Opt-in-Spiegel. End-to-end getestet. Hinter `AUTH_ENABLED` (Prod unberührt). **Entscheidung: custom statt NextAuth v5-beta** — Build-Risiko auf Next 16 vermieden; bitte absegnen oder Wechsel wünschen.
- **W2.2 Entitlement-Gating** + **W2.3 Stripe** (env-gated): Tier-Matrix (free/starter/pro/superpro), `TierGate` (Teaser + Upgrade-Karte), Pricing-Seite, Checkout+Webhook (dependency-free via fetch/crypto), Admin-CLI `set_user_tier.py`. Gating beidseitig getestet. Hinter `PAYWALL_ENABLED` (Default aus).
- Dev-Server auf **3004** läuft (Paywall aus = normaler Zustand) für dein Review: `/account/signin`, `/trends/pricing`.

- **W2.5 Newsletter-Sender** (`#16`): Resend-Batch, signierter One-Click-Unsubscribe (Python↔Frontend-Round-Trip getestet), Idempotenz (`sent_at`), Dry-Run. Cron-Zeile (Mo 9:00 generate && send) vorbereitet, auskommentiert bis DNS verifiziert.
- **W2.3 Stripe** (env-gated): Checkout + Webhook (dependency-free), wartet auf deinen Stripe-Account zum End-to-End-Test.
- **W2.7 Rechtstexte-Entwürfe**: `docs/legal/` (Impressum/Datenschutz/AGB/Widerruf) — **DRAFTs, Anwaltsprüfung nötig**, Platzhalter + AVV-Checkliste.
- **W0.6 vollständig verifiziert** (Restore mit vector-Extension: trends 1.117.625 Zeilen; Scratch-DB gedroppt, 161GB frei).

_(wird weiter ergänzt — als Nächstes W2.6 Landing + Welle-3-Tasks)_
