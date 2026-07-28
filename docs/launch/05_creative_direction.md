# Deliverable 5 — Creative Direction

## 1. Concept: "The Instrument"

The visual language is derived from the product itself — **an instrument that reads
signals across time**. Not floating spheres or neon abstractions; the imagery is
*measurement*: a horizontal **lead-time axis** (science → market), **signals as marks**
that travel and cluster, **momentum as a line**, **improvement as a curve**. The mood is a
mission-control readout crossed with an editorial science journal: dark, precise,
confident, restrained. **Cinematic restraint, technical confidence, product clarity.**

Three directions were considered; the chosen one fuses the first two:

1. **Editorial Intelligence** *(chosen base — already the app's identity)* — near-black
   ink, warm off-white type, one electric chartreuse accent, IBM Plex trio, film grain,
   mono eyebrow labels, corner brackets, terminal live-dot. Distinctive, ownable, already
   tokenized in `globals.css`.
2. **The Lead-Time Instrument** *(chosen motion/data layer)* — a left-to-right time axis
   with four tier lanes; marks flow, converge into clusters, and resolve into a momentum
   line. This *is* the hero mechanism.
3. **Blueprint / schematic** *(rejected as a base, borrowed for detail)* — too cold and
   generic as a whole, but its thin rules, crosshairs and monospace annotations survive as
   texture.

## 2. Design tokens (carried from `globals.css`, extended for the landing)

```
/* Core */
--ink:        #0a0c0a   /* background */
--surface:    #111310
--surface-2:  #161914
--edge:       #2a2d25
--rule:       #3a3d35
--text:       #d8d5c8
--paper:      #f4f1e8   /* bright headline text */
--muted:      #8a8d82
--accent:     #d4ff3a   /* chartreuse — the single hero accent */
--accent-deep:#a8cc28
--warn:       #ff6b3a

/* Lead-time tiers (also the vertical/PESTEL palette from the app) */
--tier-science: #a78bfa   /* violet — earliest */
--tier-patent:  #60a5fa   /* blue */
--tier-funding: #34d399   /* green */
--tier-market:  #d4ff3a   /* chartreuse — now */

/* Momentum */
--rising:  #22c55e  --stable: #a3a3a3  --declining: #ef4444
```

- **Type:** Display = IBM Plex Serif (production, `next/font`); the standalone preview uses
  a refined editorial serif system-stack (Iowan/Palatino/Georgia). Data/labels = IBM Plex
  Mono. Body = IBM Plex Sans. Responsive with `clamp()` throughout.
- **Scale:** hero `clamp(2.6rem, 6vw, 5.5rem)`; section head `clamp(1.8rem, 3.5vw, 3rem)`;
  body 15–18px; mono labels 10–11px, `letter-spacing: .2em`, uppercase.
- **Spacing:** 8px base; section rhythm `clamp(5rem, 12vh, 9rem)` vertical.
- **Surfaces:** 1px `--edge` borders, no heavy shadows; hover reveals corner brackets;
  dashed rules as separators.
- **Grid:** 12-col max-width 1200px; deliberate asymmetry (7/5, 8/4) and a few grid-breaking
  full-bleed data bands.
- **Motifs:** fixed film-grain overlay (opacity .03), mono eyebrow with leading rule,
  crosshair corner marks, blinking live-dot status bar, tabular-nums for all data.

## 3. Motion system

| Property | Rule |
|---|---|
| **Purpose** | Motion only to explain the mechanism, guide the eye, or confirm state — never decoration |
| **Load** | One orchestrated hero reveal: eyebrow → headline → subhead → proof counter → the lead-time animation starts (staggered `animation-delay`, ≤900 ms total) |
| **Scroll** | Light reveal-up on section entry (IntersectionObserver); **no** scroll-jacking, pinning, or slow-scroll |
| **Duration/easing** | 200–700 ms; `cubic-bezier(.2,.7,.2,1)` |
| **Hero anim** | Canvas/SVG, ≤60 fps, throttles/pauses off-screen; **static poster** fallback |
| **Reduced motion** | `prefers-reduced-motion`: no flow animation, counter shows final value, sparkline draws instantly — full content, zero movement |

## 4. Hero storyboard — "the lead-time chain"

The literal product mechanism, animated:

1. **0.0 s — Rest:** four faint horizontal lanes labeled `SCIENCE · PATENTS · FUNDING ·
   MARKET`, a thin time axis beneath. Grain + live-dot.
2. **0.3 s — Ingest:** small marks (signals) fade in at the left of the top lanes and drift
   rightward at tier-appropriate speeds (science fastest to originate, market last).
3. **1.0 s — Converge:** marks of the same theme pull together into a **cluster** node that
   grows with count; a faint link connects a science mark to its later market mark.
4. **1.6 s — Resolve:** a **momentum line** draws across the bottom from the cluster's
   share-of-voice; a small `↗ RISING` tag snaps in.
5. **2.2 s — Read:** a callout reads `research led the market by ~N years` (only shown as a
   scoped, honest example), and the headline/CTA are already fully legible above it.
6. **Loop:** gentle, slow re-ingest; never distracting. Pauses when scrolled past.

Mobile: fewer marks, 3 lanes, shorter axis; same story. WebGL not required (Canvas 2D).

## 5. Data-visualization style

- **Sparklines:** 2px chartreuse polyline, accent end-dot, `<title>` for a11y (matches
  `Sparkline.tsx`).
- **TIR trajectory:** line + ~68 % CI band, rate/cumulative toggle, greyed "unreliable
  recent years" zone (honesty made visible).
- **Lead-time rings / lanes:** the four tiers, earliest outward/leftward, momentum glyphs
  `↗ → ↘`.
- **Every chart:** one clear message, legend, accessible label, alt text, responsive,
  real or clearly-labeled demo data.

## 6. Asset strategy

- SVG for all diagrams, icons, the logo mark, the lead-time schematic.
- No stock or generic AI imagery. The "product shots" are **real UI** (radar, cluster
  cards, technology chart) or faithful SVG re-creations — never invented screens.
- Social/OG image: the lead-time schematic + headline on ink, exported at 1200×630.
- Favicon: a chartreuse crosshair/target mark (the "reading an instrument" motif).

## 7. Accessibility & performance guardrails (non-negotiable)

WCAG 2.2 AA: semantic landmarks, visible focus, skip link, AA contrast (chartreuse on ink
passes for large text; body uses `--text`/`--paper`), no color-only meaning (glyphs +
labels on momentum/PESTEL), full reduced-motion path. Budgets: LCP ≤2.5 s, INP ≤200 ms,
CLS ≤0.1; the hero canvas is lazy and never blocks the headline/CTA text.
