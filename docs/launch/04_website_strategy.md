# Deliverable 4 — Website Strategy

## 1. Goals & conversion

| Priority | Goal | Metric | Reality check |
|---|---|---|---|
| **P0** | Free newsletter signup (the **only live** conversion) | `/api/newsletter` opt-ins | works today (Resend verified) |
| **P1** | Explore the live engine | clicks to `/trends/foresight`, radar, technology | live, no login |
| **P2** | Foresight interest (demo/access request) | mailto / contact submits | sales-led; no booking flow yet |
| **P3** | SEO discovery | organic to `/` and `/trends` | 60k indexable articles already |

**Primary CTA everywhere:** *Get the weekly briefing.* **Secondary:** *Explore the engine.*
We do **not** gate the hero behind "book a demo" — the product is browsable, so the site's
job is to make people *look*, then subscribe.

## 2. Sitemap (focused launch, not bloated)

```
/                     Launch home (THIS build — new; replaces the /trends redirect)
/trends               Existing app — free article grid (unchanged)
/trends/foresight     Existing — the engine hub (radar/clusters/technology/lead-time/evolution)
/trends/methodology   Existing — "How we measure" (trust)
/trends/pricing       Existing — 4 tiers + Hypercare
/trends/newsletter    Existing — signup + archive (primary lead magnet)
/impressum /datenschutz   German legal (from docs/legal drafts — publish before go-live)
```

The launch home is a **single, long, well-paced page** that tells the whole story and
funnels into the already-built product. No new sub-pages are invented; every deep link
points at a real, live surface.

## 3. Home-page dramaturgy (section-by-section content map)

| # | Section | Job | Real content / proof | CTA |
|---|---|---|---|---|
| 1 | **Hero** | Category + outcome + product-in-motion in 5 s | Headline + animated **lead-time chain** (the core mechanism) + live proof counter | Newsletter / Explore |
| 2 | **The problem** | Why market-news is too late | "By the time it's news, it's late. The signal was in the science years earlier." | — |
| 3 | **Mechanism** | How it works in 4 steps | Collect (243 sources) → Classify (local models, 8×6×3 taxonomy) → Cluster (momentum) → Attribute (every source clickable) | — |
| 4 | **Pillars** | The 5 value pillars | pillars from positioning L4, each with a mini-visual | Explore |
| 5 | **Interactive demo** | Let them *feel* the engine | (a) lead-time chain scrubber; (b) a canned **TIR trajectory** for a real example (e.g. solid-state battery / CRISPR) with accelerating/maturing verdict | Try it live → |
| 6 | **What's moving now** | Live intelligence proof | momentum board styled like the real cluster cards (rising/declining) | See all clusters |
| 7 | **Technology & trust** | Earn belief | local-first diagram · evidence enforced (`source_url NOT NULL`) · grounding gate · honest gates · CI/backup | How we measure → |
| 8 | **Differentiation** | Fair vs. the status quo | 3-column: keyword tools / **Catandary** / enterprise suites — factual, no strawman | — |
| 9 | **Pricing** | The offering | Free/€99/€499/€799 + Hypercare, rebuilt cleanly (no Stripe test artifacts) | Start free |
| 10 | **FAQ** | Kill objections | data sources, "is it accurate?", local/privacy, who it's for, price | — |
| 11 | **Final CTA** | One decision | "Foresight you can cite." → newsletter + explore | Newsletter / Explore |
| — | **Footer** | Nav + legal + honest status | links, Impressum/Datenschutz, "built locally in Germany" | — |

## 4. User paths

- **Curious analyst:** hero → mechanism → interactive demo → *newsletter*. (fast, no login)
- **Corporate evaluator:** hero → pillars → technology/trust → differentiation → *explore
  engine* → pricing → *demo request*.
- **Agency:** hero → interactive demo → pricing (export/dossier) → *sample dossier*.
- **Skeptic:** hero → "honest by construction" → methodology → validation figures → trust.

## 5. Content-to-evidence mapping rule

Every section's copy cites a **V#** from the Truth Matrix inline in the source comments, so
a reviewer can trace any sentence to its evidence. No sentence without a grade.

## 6. Analytics (privacy-first, deferred)

Reuse existing `/api/track` (cookieless page_view/share). Add event hooks for `cta_click`,
`newsletter_submit`, `demo_open`, `explore_engine`, `pricing_view`. No third-party
analytics, no consent banner needed (matches the owner's cookieless doctrine). Ship the
hooks; wiring a dashboard is Phase 2 (`lead_tracking.md`).
