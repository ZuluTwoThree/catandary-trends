# Deliverable 8 — Handover

## 1. What was built

**Strategy package** (`docs/launch/`):
`01_executive_repository_analysis.md`, `02_product_truth_matrix.md`, `03_positioning_brief.md`,
`04_website_strategy.md`, `05_creative_direction.md`, `07_launch_kit.md`, this file, and
`site_preview.html` (the self-contained, publishable preview).

**Production landing page** (in the Next.js app):
| File | Role |
|---|---|
| `frontend/src/app/page.tsx` | The landing (server component). **Replaces the old `/` → `/trends` redirect.** Pulls live corpus stats; `dynamic = "force-dynamic"`. |
| `frontend/src/components/landing/HeroInstrument.tsx` | `"use client"` — the animated lead-time instrument (Canvas 2D, DPR-aware, pauses off-screen, reduced-motion poster). |
| `frontend/src/components/landing/TechReader.tsx` | `"use client"` — interactive TIR trajectory + lead-time lanes (illustrative, labelled). |
| `frontend/src/components/landing/MomentumBoard.tsx` | Server component — six validated momentum cards + inline SVG sparklines. |
| `frontend/src/components/landing/ProofCounter.tsx` | `"use client"` — count-up; **SSR renders the real live numbers**. |
| `frontend/src/components/landing/Reveal.tsx` | `"use client"` — scroll-reveal wrapper. |
| `frontend/src/app/globals.css` | Appended a namespaced `.lp-*` stylesheet (reuses existing Editorial-Intelligence tokens + a lead-time tier palette). No existing rule changed. |

The landing renders **inside the existing app layout** (app `Header`/`Footer` bracket it),
so navigation and chrome stay consistent. All CTAs deep-link to real, live surfaces
(`/trends/newsletter`, `/trends/foresight`, `/trends/foresight/technology`,
`/trends/foresight/clusters`, `/trends/pricing`).

## 2. Setup & build

```bash
cd frontend
npm install          # already satisfied in this repo
npm run lint         # clean
npm run build        # clean — root route "/" is ƒ (dynamic, server-rendered)
```
Verified 2026-07-21: build + lint pass; `next start` serves `/` at HTTP 200 with live
SSR numbers (`1,123,554` signals · `60,482` articles · `243` sources · `100%`).

## 3. Deploying it (makes the landing the public home)

Per the repo's deploy convention (systemd unit, since #38):
```bash
cd frontend && npm run build && systemctl --user restart catandary-frontend
```
> **Deliberate step — read first.** This makes `/` show the marketing landing instead of
> redirecting to `/trends`. It is an intentional change of the site's front door (closes
> open issue **#44**). Merge `dev → main` first if you want prod (3001) to serve it, per the
> branch strategy. The app itself is unchanged and still lives at `/trends`.

## 4. Environment / data dependencies

- The landing calls `getMethodologyStats()` (live corpus counter). It is wrapped in
  try/catch with **verified fallbacks** (`analyzed 1,059,838 · published 60,482 · sources
  243`), so it renders even if the DB is briefly unavailable. Frontend DB access uses the
  local socket default (`lib/pg.ts`) — leave `DATABASE_URL` unset in prod, as documented.
- No new env vars, no new dependencies (no Three.js/GSAP/Framer added — the hero is Canvas
  2D by design, keeping the performance budget). Nothing external is fetched.

## 5. Content maintenance

- All landing copy lives in `page.tsx` and the components — plain text, easy to edit.
- **Rule:** any claim added to the site must first exist as a **V** row in
  `02_product_truth_matrix.md` with evidence. Copy and matrix move together.
- Demo data: `MomentumBoard.tsx` uses the six validated clusters from
  `docs/foresight_validation.md`; `TechReader.tsx` curves are illustrative and labelled.
  Both can be re-pointed at live snapshots in Phase 2.

## 6. Accessibility & performance (built-in)

Semantic landmarks/headings, visible focus, AA-contrast body text, momentum encoded with
glyph+label (not color alone), full `prefers-reduced-motion` paths (hero → static poster,
count-up → final value, reveals → instant). Canvas is lazy and never blocks the headline/CTA
text; no external fonts/scripts/images. Budget targets: LCP ≤2.5s, INP ≤200ms, CLS ≤0.1.

## 7. Known limitations / honesty ledger

1. **Preview vs production fonts:** `site_preview.html` uses a system editorial-serif stack
   (Artifact CSP blocks font CDNs); the Next.js page uses the real **IBM Plex** via
   `next/font`. Same design language.
2. **Paid tiers are early-access:** auth/paywall are gated off and Stripe is test-mode. Copy
   says "Request early access" — do **not** flip to live-billing language until Stripe is
   live, legal pages published, and DPAs signed.
3. **Legal pages required before go-live:** publish `docs/legal/*.draft.md`
   (Impressum/Datenschutz mandatory for catandary.de). Footer links are placeholders.
4. **Live gate state is inconsistent** (`.env.local` shows test-mode gates on; owner memory
   says off) — reconcile before launch.
5. **TIR recency:** absolute rates reliable to ~2019 by design; the demo greys the recent
   zone and labels curves illustrative — keep that framing.
6. **Doc drift found during analysis** (report only, not fixed here): CLAUDE.md scale
   numbers are stale (2026-05-29); the TIR predictor default already flipped `own→cited`
   while several docs still say `own`. See `01_executive_repository_analysis.md §6` and
   `02_product_truth_matrix.md`. Worth a constitutional doc-sync pass.

## 8. Recommended Phase 2

- **Playwright + Lighthouse CI** for the landing (nav, CTA, demo interaction, responsive,
  a11y) — extend the existing GitHub Actions workflow.
- **Export the OG/social image + favicon SVG** (lead-time schematic on ink) and wire
  `metadata.openGraph.images`.
- **Wire the newsletter form inline** on the landing to `POST /api/newsletter` (currently
  deep-links to `/trends/newsletter`, which already works).
- **A booking flow** for the "20-minute demo" CTA (currently mailto).
- **German i18n** of the landing if the DACH B2B motion wants a `/de` variant (article
  content stays English).
- **Point the demo widgets at live snapshots** (real cluster board + a cached popular-query
  TIR) once a public-safe cache exists.
- **Reconcile & publish** legal pages; finalize live gate state; then flip paid copy from
  "early access" to live.
