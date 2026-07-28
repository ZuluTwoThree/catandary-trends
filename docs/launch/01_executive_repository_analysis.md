# Deliverable 1 — Executive Repository Analysis

**Repo:** `catandary-trends` · **Analyzed:** 2026-07-21 · **Method:** 6 parallel subsystem
readers over the full codebase + live PostgreSQL COUNT queries (numbers below are
DB-verified today, not the stale `CLAUDE.md` figures dated 2026-05-29).

> Governing rule for this whole package: **only V (Verified) claims ship publicly.**
> See `02_product_truth_matrix.md` for the per-claim evidence grade that every line
> of website copy must trace back to.

---

## 1. Product in one paragraph

**Catandary** is a cross-industry **trend & foresight intelligence platform** that runs
its entire analysis pipeline on **local LLMs** (one RTX 3090, no cloud in the loop). It
ingests innovation signals across the full maturity chain — **science → patents → funding
→ market** — classifies them with a local multi-stage pipeline, and derives foresight
artifacts on top: bottom-up trend clusters, share-of-voice momentum, cross-tier
**lead-time** analysis, and **Technology Improvement Rates** computed from a ~109 M-edge
patent-citation graph. It ships as two layers: **Catandary Trends** (free curated
articles + weekly newsletter — the lead magnet) and **Catandary Foresight** (the paid
engine — clusters, radar, lead-time, TIR, evolution, export).

**Category:** evidence-based, local-first lead-time trend & foresight intelligence.
**Market:** German-rooted (catandary.de), English content, B2B — innovation teams,
agencies/consultants, prosumer analysts. **Price band:** €0 / €99 / €499 / €799 per
month + a sales-led €1,499/day Hypercare, deliberately positioned between free
black-box keyword tools and €50 k+/yr enterprise innovation suites.

---

## 2. Technical inventory

| Layer | Stack (verified in repo) |
|---|---|
| **Pipeline** | Python 3.12, a 10-stage batch pipeline (`pipeline/llm_processor.py`), Pydantic schemas, `feed_poller`, `article_fetcher` (trafilatura), `reclassify`, `auto_publisher`, `run_full_cycle` orchestrator |
| **Local LLM serving** | `llama.cpp` `llama-server` on `127.0.0.1:8090` (production) / Ollama `127.0.0.1:11434` (default fallback); Anthropic Claude Haiku = one-time backfill only |
| **Models** | Qwen3-8B (208 K ctx, 24 parallel slots) for filter/extract/classify/reclassify; Qwen3-Embedding-8B (4096-dim); **Gemma-4-26B-A4B** for content-gen; distilled linear heads on embeddings for the GPU-free fast path |
| **Foresight** | `pipeline/foresight.py` (spherical k-means clusters, SoV momentum, cross-window lineage), `scripts/spnp_centrality.py` + `scripts/tir_trajectory.py` (SPNP centrality → K(t) improvement rate), CPC lead-time |
| **Data** | PostgreSQL 16 + pgvector (prod), SQLite (test/CI/frozen fallback) from one schema (`pipeline/db.py`); HNSW ANN on a 1024-dim Matryoshka prefix |
| **Frontend** | Next.js 16 (App Router) + React 19 + Tailwind v4 + TypeScript; IBM Plex Serif/Mono/Sans; "Editorial Intelligence" dark theme (chartreuse `#d4ff3a` on ink `#0a0c0a`) |
| **Monetization** | Dependency-free magic-link auth (HMAC session cookie), dependency-free Stripe (signature-verified, idempotent webhook), env-gated paywall/entitlement, 4 tiers + Hypercare |
| **Ops** | Hetzner VPS + Caddy (auto-HTTPS) + systemd user unit; nightly `pg_dump` + verified restore runbook; GitHub Actions CI (pytest against real pgvector, lint, vitest, build, clean-tree check) plus a separate weekly/on-dependency-change Security Audit workflow (`npm audit --high`, `pip-audit`) |

**Core objects (glossary the site must teach):** *signal*, *trend* (curated article),
*vertical* (8), *PESTEL* (6), *mega/macro/micro*, *lead-time tier* (4), *cluster*,
*momentum / share-of-voice*, *TIR / SPNP centrality*, *CPC classes*, *CRS (Catandary
Relevance Score)*, *grounding gate*.

---

## 3. Verified scale (live DB, 2026-07-21)

| Metric | Value | How verified |
|---|---:|---|
| Published trend articles | **60,482** | `SELECT count(*) … status='published'` |
| — by vertical | TECH 19,283 · BIZ 11,265 · ECO 9,436 · HEALTH 8,102 · FOOD 4,211 · LIFESTYLE 3,593 · DESIGN 2,314 · FASHION 2,278 | grouped count |
| Embedded foresight signals | **1,059,838** | `status='signal'` |
| All records embedded | **1,123,554 (100 %)** | `embedding_1024 IS NOT NULL` |
| Raw entries ingested | **21.4 M** | `count(*) raw_entries` |
| Active primary sources | **243** (138 trade media · 66 research · 24 API · 15 press wire) | grouped count |
| Canonical mega-trends | **21** | distinct `mega_trend` |
| Foresight clusters (live) | **221** | `foresight_clusters` |
| Patent citation edges | **~108.8 M** | `patent_links` reltuples |
| Patents with SPNP centrality | **~42.6 M** | `patent_spnp_full` reltuples |
| Patent → CPC mappings | **~376 M** | `patent_cpc_full` reltuples |
| OpenAlex science citations | **~11.3 M** | `openalex_citations` reltuples |
| Published content date span | 2026-03-31 → 2026-07-20 | min/max `published_at` |
| Newsletter subscribers | **1** | `newsletter_subscribers` — honest gap |
| Paying customers | **0** | auth/paywall gated off, Stripe test-mode |

**Distill fast path** (`models/distill/meta.json`): trained on **1,010,460** teacher-labeled
trends; **91.2 %** vertical top-1 agreement, **98.1 %** mega-trend top-3 agreement,
90.8 % PESTEL micro-F1 vs the 8B LLM.

**Internal foresight validation** (`docs/foresight_validation.md`): **23/24** known trends
recovered bottom-up; **6/6** momentum-direction calls match public reality; lead-time
numbers stated only for the **18 CPC areas** the corpus can prove.

---

## 4. Development stage

- **Pipeline & foresight engine:** production-grade, running nightly, self-scoping,
  safety-capped, incident-hardened. **Mature.**
- **Free content layer (`/trends`):** live, 60 k articles, full browse/search/newsletter.
  **Mature.**
- **Foresight UI (radar, clusters, technology/TIR, lead-time, evolution):** built and
  browsable. **Beta-mature; data-dependent empty states exist.**
- **Monetization (accounts, paywall, Stripe):** fully coded + unit-tested, **gated off**;
  Stripe test-mode only; **no live payments.**
- **Public launch:** not yet released — the running instance is a localhost:3001 demo
  (owner is his own first user). **Pre-launch.**
- **Marketing site:** **does not exist** — `/` is a 5-line redirect to `/trends`. This
  package builds it (also closes open issue #44).

---

## 5. Genuine differentiators (defensible)

1. **The lead-time chain is the data model, not a feature.** Every signal is stamped with
   the maturity stage it was observed at (science/patent/funding/market); all four tiers
   share one schema, so per-technology lead time is *measurable*, not asserted.
2. **Fully local at real scale.** The entire pipeline — including a 26B content model and
   4096-dim embeddings — runs on one 24 GB consumer GPU via an automatic mid-cycle GPU
   handover. No per-token cloud cost; the source corpus never leaves the machine.
3. **Evidence on every number.** `source_url` is `NOT NULL` at the schema level; a
   grounding gate holds any article that introduces a figure/date absent from its source.
   Traceability is enforced, not cosmetic.
4. **Honest by construction.** The engine withholds absolute rates it can't trust
   (post-2019, >50 %/yr), scopes lead-time to what the corpus proves, and normalizes
   momentum as share-of-attention so a growing corpus can't fake a growing trend.
5. **A distilled fast path** reproduces the 8B classifier at ~zero marginal cost (91 %/98 %
   agreement over 1 M trends), which is what makes million-signal foresight affordable.
6. **Ad-hoc technology resolution:** free-text phrase → ranked CPC classes → one TIR you
   can re-scope — versus competitors' fixed domain catalogs.

---

## 6. Technical & positioning risks (must shape copy)

| Risk | Consequence for the site |
|---|---|
| **Stale docs vs reality** | Never quote CLAUDE.md's 137 sources / 26 k trends. Use live-DB numbers or a live counter. |
| **No methodology moat** | GetFocus + TechNext use the same SPNP method (TechNext are the paper's authors, hold US12099572B2). **Never** claim a unique/proprietary method — cite the peer-reviewed basis and differentiate on corpus/calibration/price/GTM. |
| **No customers/revenue** | Zero fabricated traction, testimonials, logos, or "trusted by". |
| **Paid layer gated off** | Present tiers as the *offering*; don't imply live billing or active subscribers. |
| **TIR reliable only to ~2019** | Never headline present-year absolute rates; lead with direction/shape and the honest gate. |
| **Legal texts are drafts** | No "GDPR compliant" / certification badges. Scope "local-first" to the content pipeline (user PII does go to Stripe/Resend/Hetzner). |
| **Config-default ≠ production** | "Gemma-4-26B / 208 K" is true of the scheduled path; phrase as production behavior, not a bare default. |
| **Mixed-language UI** | The Technology tool UI is currently German while the app is English — reconcile before screenshots. |

---

## 7. Open questions (reversible assumptions made)

1. **Launch surface** — assuming the paid Foresight tiers are presented as the offering
   with pricing, but the primary CTA is the **free newsletter** (the only live conversion)
   + a "request access / book a demo" for Foresight. *(Reversible.)*
2. **Language** — **English-primary** site (matches the live product, UI, methodology
   page) with German legal pages (statutory for catandary.de). *(Reversible.)*
3. **Live gate state** — treating "gates off / no live payments" as canonical per owner
   memory, despite `.env.local` currently showing test-mode gates on. *(Confirm before
   go-live.)*
4. **Domain** — landing at `catandary.de` root, app stays at `catandary.de/trends`.
