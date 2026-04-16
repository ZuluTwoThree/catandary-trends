# Catandary Trends — Design Revamp Plan

## Current State

The frontend uses a generic dark-mode Tailwind setup: Inter font, purple accent (`#c084fc`), flat `#0a0a0a` background, emoji-based vertical icons, pill badges. It's functional but visually indistinct — could be any SaaS dashboard. The existing **Foresight Workbench mockup** (`mockups/foresight-search.html`) establishes a far more refined design language: Fraunces serif, JetBrains Mono data labels, chartreuse accent, grain overlay, editorial grid with ruled lines.

## Shared Principles (all options)

- **No emojis.** Replace all vertical/PESTEL icons with typographic abbreviations, SVG icons, or colored markers
- **Professional typography.** Display font + mono for data + clean sans for body
- **Vertical identity via color only** — each vertical gets a distinct hue, no emoji
- **Information density.** Trend intelligence should feel like a Bloomberg terminal, not a blog
- **Source attribution prominent.** Trust signal for professional audiences

---

## Option A — "Editorial Intelligence"

> Inspired by: Financial Times, The Economist, Monocle

**Tone:** Refined editorial. A newspaper for trend intelligence. Warm, literate, authoritative.

**Typography:**
- Display: **Fraunces** (optical sizing, italic for emphasis)
- Data/Labels: **JetBrains Mono** (uppercase, letter-spaced)
- Body: **Source Sans 3** or **Libre Franklin**

**Color:**
```
--ink:     #0a0c0a        (deep black-green)
--paper:   #f4f1e8        (warm off-white, for text on dark)
--accent:  #d4ff3a        (electric chartreuse — from Workbench)
--muted:   #8a8d82
--border:  #2a2d25
```

**Visual Language:**
- Ruled lines (1px solid, dashed for secondary divisions)
- Corner brackets on feature elements (like the Workbench search box `::before`)
- Section numbering in mono (`01 —`, `02 —`)
- Grain overlay on body (SVG noise at 3.5% opacity)
- Subtle radial gradient glow from top (chartreuse tint)

**Card Design:**
- No rounded corners. Sharp rectangles with 1px ruled borders
- Vertical indicator: 3px left border in vertical color
- Top-left: vertical abbreviation in mono (e.g. `TECH`), colored
- Title in Fraunces 18px weight 400, tracking tight
- Source + date in JetBrains Mono 10px uppercase
- CRS score as thin progress bar, not a number

**Header:**
- `Catandary.` in Fraunces 800, the dot in chartreuse
- Navigation in JetBrains Mono 10px uppercase, letter-spaced
- No background — separated by a single ruled line

**Hero:**
- Large Fraunces italic headline: "Cross-Industry *Trend Intelligence*" (accent on italic)
- Eyebrow label: `—— SIGNAL INTELLIGENCE` in mono

**Signature detail:** Corner-bracket decorations on key containers. The Workbench's `::before` pseudo-element pattern of accent-colored L-shaped corners.

---

## Option B — "Swiss Data Room"

> Inspired by: Swiss International Style, Dieter Rams, Bloomberg Terminal

**Tone:** Clinical precision. Grid-obsessed. Data speaks, decoration is noise.

**Typography:**
- Display: **Instrument Serif** (sharp, geometric serif)
- Data/Labels: **IBM Plex Mono** (industrial mono)
- Body: **IBM Plex Sans** (clean, engineered)

**Color:**
```
--bg:      #111111        (pure dark)
--surface: #1a1a1a
--text:    #e0e0e0
--accent:  #00e5a0        (mint/teal — clinical, fresh)
--muted:   #666666
--border:  #333333
--red:     #ff4d4d
--amber:   #ffb800
```

**Visual Language:**
- Strict 8px grid system
- No decorative elements — information IS the decoration
- Thick (2px) top borders on sections, colored by category
- Monospaced numbers everywhere (tabular figures)
- Status indicators: small squares (4x4px) instead of dots or badges

**Card Design:**
- Flat, no border radius, no shadow
- 2px top border in vertical color
- Content left-aligned, strict hierarchy
- Vertical tag: colored square + abbreviation in Plex Mono
- Metadata row: pipe-separated values in mono `STAT News | 12 Apr 2026 | CRS 87`

**Header:**
- Horizontal rule top + bottom
- Logo: `CATANDARY` in IBM Plex Mono 600, all caps, tracked wide
- Nav items with active indicator = 2px bottom border

**Hero:**
- Left-aligned. Instrument Serif 48px. No subheading.
- Below: live metrics bar — `4,782 signals | 8 verticals | 23 mega-trends` in mono

**Signature detail:** A persistent thin status bar at the very top of the page showing live signal counts per vertical as tiny colored blocks — like a miniature heatmap.

---

## Option C — "Dark Observatory"

> Inspired by: NASA mission control, Astronomy dashboards, Dark Sky apps

**Tone:** Cosmic, observational. You're looking at signals from the horizon. Atmospheric depth.

**Typography:**
- Display: **Playfair Display** (elegant, high-contrast serif)
- Data/Labels: **Space Mono** (technical, slightly playful mono)
- Body: **DM Sans** (geometric, modern)

**Color:**
```
--void:    #05060a        (near-black with blue tint)
--surface: #0d0f16
--text:    #c8cad0
--accent:  #6c9fff        (soft electric blue)
--accent2: #a78bfa        (soft violet, secondary)
--muted:   #4a4e5a
--border:  #1e2130
--warm:    #f59e42        (warm orange for alerts)
```

**Visual Language:**
- Deep layered backgrounds with subtle gradient meshes (blue/violet glow spots)
- Cards have soft 1px borders + subtle inner glow on hover
- Thin luminous lines (accent-colored, 0.5px or 1px with low opacity)
- Breathing animations on key metrics (slow pulse opacity 0.7-1.0)
- Frosted glass effect on overlays (`backdrop-filter: blur`)

**Card Design:**
- Rounded corners (8px) with 1px semi-transparent border
- Soft gradient background (surface to slightly lighter)
- Vertical: circle (12px) in vertical color + name
- Title in Playfair 17px, body in DM Sans
- Hover: border brightens, subtle lift shadow

**Header:**
- Transparent, floating over a subtle top gradient
- `Catandary` in Playfair Display 500, accent color on `C`
- Nav with soft pill-shaped active state

**Hero:**
- Large Playfair headline with soft text-shadow for depth
- Subtitle fades in with delay animation
- Background: radial gradient mesh (blue center, violet edges, fading to void)

**Signature detail:** Soft luminous "scan line" — a 1px horizontal accent line that slowly animates downward across the page on initial load, like a radar sweep. CSS-only animation.

---

## Option D — "Brutalist Press"

> Inspired by: Bloomberg Businessweek covers, Experimental editorial, David Carson

**Tone:** Bold, opinionated, slightly aggressive. A design that has something to say.

**Typography:**
- Display: **Clash Display** (geometric, bold, modern)
- Data/Labels: **Fira Code** (ligatures, technical)
- Body: **Satoshi** (geometric sans, clean)

**Color:**
```
--bg:      #f5f0e8        (warm cream — LIGHT MODE)
--surface: #ffffff
--text:    #1a1a1a
--accent:  #ff3d00        (bold vermillion red)
--accent2: #0055ff        (electric blue)
--muted:   #999999
--border:  #e0dcd4
--dark:    #1a1a1a        (for inversions)
```

**Visual Language:**
- **Light mode** — bold departure from every other trend platform
- Oversized typography (hero headline 72px+)
- Thick borders (2-3px) on key elements
- Selective color inversions (accent bg + white text for CTAs)
- Vertical bars as bold color stripes
- Asymmetric grid — some cards span 2 columns
- Diagonal text elements for labels (rotated -90deg)

**Card Design:**
- White background, thick 2px border, no radius
- Top: bold color stripe (4px) in vertical color
- Vertical name in Clash Display 12px bold, uppercase
- Title in Clash Display 20px weight 600
- Source in small Fira Code, muted
- Hover: background inverts to dark, text to light

**Header:**
- Full-width. `CATANDARY` in Clash Display 800, massive (28px+)
- `.TRENDS` appended in accent color
- Nav items: underline on hover, no background effects

**Hero:**
- Headline fills the width: `TREND` stacked over `INTELLIGENCE` in Clash Display 72px
- Subtitle: in Satoshi, small, right-aligned — creating asymmetry
- Decorative: a large `//` in accent color, oversized, partially clipped

**Signature detail:** On every page load, the vertical-color stripes on cards animate in from the left with staggered timing (50ms delay per card), creating a visual "barcode" sweep effect.

---

## Comparison Matrix

| Aspect | A: Editorial Intelligence | B: Swiss Data Room | C: Dark Observatory | D: Brutalist Press |
|--------|--------------------------|-------------------|--------------------|--------------------|
| Theme | Dark | Dark | Dark | **Light** |
| Mood | Warm, authoritative | Clinical, precise | Atmospheric, deep | Bold, opinionated |
| Display Font | Fraunces | Instrument Serif | Playfair Display | Clash Display |
| Accent | Chartreuse `#d4ff3a` | Mint `#00e5a0` | Blue `#6c9fff` | Vermillion `#ff3d00` |
| Corners | Sharp | Sharp | Rounded (8px) | Sharp |
| Density | High | Very high | Medium | Medium |
| Decorative | Corner brackets, grain | Minimal, status bar | Glow, gradients | Thick borders, inversions |
| Closest to Workbench | **Direct evolution** | Different philosophy | Different mood | Total departure |
| Best for | Professional B2B audience | Data-heavy power users | Design-aware audience | Bold brand statement |

## Recommendation

**Option A** is the natural evolution of the Workbench mockup — same fonts, same accent, same design vocabulary. It would create perfect visual continuity between the free Trends platform and the premium Foresight product.

**Option B** is the safest bet for a pure data/intelligence platform — maximally professional, zero fluff.

**Option C** has the most visual wow-factor but risks feeling more "consumer" than "B2B intelligence."

**Option D** is the boldest departure — memorable but polarizing. The light mode alone would differentiate it from every competitor.
