# Deliverable 2 — Product Truth Matrix

The **binding source of truth** for every marketing claim. No copy ships unless it maps to
a **V** row here (or a **D** row explicitly framed as "in development / early access").
**H** rows are listed so we know what **must not** be said.

**Evidence classes** — **V** verified in code/live app/DB · **D** documented/planned ·
**H** hypothesis (no public use without owner sign-off).

---

## A. VERIFIED — safe to publish as present-tense fact

| # | Theme | Claim (as usable copy) | Repo / DB evidence | Site section | Required qualification | Release |
|---|---|---|---|---|---|---|
| V1 | Corpus scale | "Over **1 million** innovation signals analyzed; **60,000+** curated trend articles published." | live DB: 1,059,838 signals · 60,482 published | Hero, Methodology, Counter | Use a **live counter** (methodology `getMethodologyStats`), not a hard-coded number | ✅ |
| V2 | Sources | "**243** legal primary sources across 8 industries." | live DB `sources` active=138 trade+66 research+24 api+15 wire | Trust, Methodology | "Primary sources" = RSS/API/open data, curated policy | ✅ |
| V3 | Lead-time chain | "We track the whole maturity chain: **science → patents → funding → market**." | `pipeline/foresight.py` TIER_FILTERS; README:40-60; methodology page | Hero, Mechanism | — | ✅ |
| V4 | Local-first | "Every step runs on **local models on one GPU** — no cloud in the loop." | `scheduled_cycle.sh` all-llamacpp; loopback endpoints; `anthropic_client.py` = backfill only | Trust/Technology | Scope "local" to the **content pipeline**; user PII still uses Stripe/Resend/Hetzner | ✅ |
| V5 | Evidence | "Every trend links to its **primary source** — traceability is enforced." | `db.py` `source_url TEXT NOT NULL`; `TrendArticle.tsx` Original Source link | Trust, Cards | NOT NULL ≠ URL still reachable | ✅ |
| V6 | Anti-fabrication | "Articles that introduce a figure or date absent from the source are **held for review**, not published." | `pipeline/grounding.py`; `auto_publisher.py:107-114` grounding gate | Trust | Gate can fail **open** if source text unloadable — say "held", not "impossible" | ✅ |
| V7 | Taxonomy | "Each signal is classified on **8 verticals × 6 PESTEL dimensions × mega/macro/micro**." | `db.py` schema; `types.ts`; distill heads | Mechanism, Cards | PESTEL is prompt-enforced, not a DB constraint | ✅ |
| V8 | Distill fast path | "A distilled model reproduces the LLM classifier on **1M+** labels — **91 %** vertical / **98 %** mega top-3 agreement." | `models/distill/meta.json` (n=1,010,460) | Technology/deep-dive | "agreement with the LLM teacher", not ground-truth accuracy | ✅ |
| V9 | Clusters/momentum | "**221** trend clusters, ranked by **share-of-voice momentum** (rising/stable/declining)." | live DB `foresight_clusters`=221; `foresight.py` SoV | Foresight, "Moving now" | Momentum meaningful only inside the recent stable window | ✅ |
| V10 | Momentum honesty | "Momentum is **normalized** as share of attention, so a growing corpus can't fake a growing trend." | `foresight.py analyze()`; methodology "Momentum, normalized" | Trust, Differentiation | — | ✅ |
| V11 | TIR engine | "A **Technology Improvement Rate** built on the peer-reviewed **SPNP** method (Singh, Triulzi & Magee, 2021), computed over a **~109 M-edge** patent-citation graph." | `spnp_centrality.py`, `tir_trajectory.py`; live DB `patent_links`≈108.8M | Foresight, Technology | Cite the method as **peer-reviewed and shared**, never "our unique method" | ✅ |
| V12 | TIR direction | "The engine reads whether a technology is **accelerating, maturing or steady** — the S-curve phase." | `tir_trajectory.py classify()` | Technology | Headline **direction/shape**; absolute rate only where calibrated | ✅ |
| V13 | TIR honesty gates | "It **withholds** rates it can't trust — beyond the calibrated range or too recent to verify." | `tir_trajectory.py` CALIB_MAX=50, TRUNC=7 | Technology, Trust | Reliable absolute rate currently to **~2019** | ✅ |
| V14 | Validation | "In our own tests the engine recovered **23 of 24** known trends bottom-up and matched **6/6** momentum-direction calls with public reality." | `docs/foresight_validation.md` | Trust/Proof | Frame as **internal validation**, small hand-checked samples | ✅ |
| V15 | Ad-hoc resolution | "Type any technology; it resolves to the right **patent CPC classes** and returns one improvement-rate curve you can re-scope." | `tech_analyze.py resolve_candidates`; `TechnologyTool.tsx` | Foresight demo | ~10–40 s (GPU); pre-cache demo queries | ✅ |
| V16 | Patent graph depth | "A patent graph spanning **~42.6 M** patents and **~376 M** CPC mappings back to 1990." | live DB reltuples; README | Technology, Scale | — | ✅ |
| V17 | Search | "**Semantic search** with a live analytics sidebar — timeline, lead-time path, cross-vertical, PESTEL, related terms." | `ForesightCockpit.tsx`; `/api/search`; HNSW `embedding_1024` | Product demo | Analytics render at ≥30 matches | ✅ |
| V18 | Design system | Editorial-Intelligence identity: chartreuse `#d4ff3a` on ink `#0a0c0a`, IBM Plex trio, grain/brackets/crosshair/eyebrow. | `globals.css`; `layout.tsx` | Whole site | — | ✅ |
| V19 | Pricing (owner 2026-09-20 — replaces the SaaS tiers, which were removed from code on 2026-09-03, #93) | "**Trajectory Sheet** 1,490 € per field · **Field Watch** 390 €/month for three fields, setup 900 €, +90 €/month per field, 3-month pilot 290 €/month · **Analyst Day** 1,200 € · **field probe free**." | `docs/business_model_2026-09-19.md` §4; `docs/commercialization_plan_2026-09-20.md` §1; samples `docs/samples/` → `/trends/samples/*.pdf`; generators `scripts/field_watch_demo/` | Services, FAQ | Invoiced, excl. VAT, no checkout/account; "measured, not narrated" — no forecast, no recommendation; improvement rate = relative; thin cells printed on every sheet | ✅ |
| V20 | Security engineering | "Passwordless magic-link login, signature-verified idempotent payment webhook, per-IP rate limiting, fail-closed secrets." | `auth.ts`, `stripe.ts`, `rateLimit.ts` + tests | Trust (optional deep) | Code is built + tested; frame capabilities, not "live payments" | ✅ (framed) |
| V21 | Reliability/ops | "Tested disaster recovery — nightly backups with a verified restore of 20 M+ rows; CI runs against a real pgvector database." | `restore_runbook.md`; `.github/workflows/ci.yml` | Trust deep-dive | — | ✅ |
| V22 | Independence | "Runs on **local models + open data** — not tied to any single vendor's feed." | local serving + open datasets | Differentiation | — | ✅ |

## B. DOCUMENTED / PLANNED — only as "in development / early access / roadmap"

| # | Claim | Evidence | How to say it |
|---|---|---|---|
| D1 | API access (Super Pro+) | `tiers.ts`; `alpha_epic_plan.md:22` "coming soon" | "**API — coming soon**" |
| D2 | Absolute lead-time numbers beyond the 18 proven CPCs | `foresight_validation.md` | "we put a number on it **where the data can prove it** (18 areas today, expanding)" |
| D3 | Cross-tier lead-time as a polished end-user feature | README "active focus" | "lead-time explorer (**beta**)" |
| D4 | Hetzner + Caddy public deployment | `Caddyfile`, systemd unit | "**deploys to** Hetzner + Caddy"; not "is live in production" until released |
| D5 | GDPR/DSGVO readiness | `docs/legal/*.draft.md` | "German legal pages **in preparation**"; never "GDPR compliant" |
| D6 | Newsletter automation | `newsletter_sender.py`, #16, Resend verified | "**weekly** newsletter"; don't imply a large list (1 subscriber) |
| D7 | Cookieless funnel analytics | `lead_tracking.md` | internal only — not a public claim |
| D8 | Custom-Vertical on demand ("Ihre Branche in ~2 Tagen als vollwertige Technologie-Achse") | Alle Bausteine einzeln V-belegt: 205-GB-Back-File lokal (`/mnt/data-hdd/bdds_backfile`), `ingest_patents.py ingest_bdds(cpc_filter=…)`, Assignee-Re-Parse 9h gemessen (#7), TIP-Runden-Workflow 2× durchexerziert (#14/#75), Panel je Achse live (#74). **Aber:** noch nie end-to-end für eine kundenfremde Branche (z. B. E21 Bergbau) durchgeführt | Sales-Gespräch/Angebot: "Ihre Branche ist **auf Anfrage binnen weniger Tage** als eigene Technologie-Achse im System — mit Anmelder-Ranking, Länder-Rennen, Lead-Times und Transfer-Kurven." **Nicht** als Website-Copy mit fixem "2 Tage"-Versprechen, bis einmal real erbracht (dann → V mit gemessener Dauer) |

## C. HYPOTHESIS — DO NOT PUBLISH without explicit owner sign-off

| # | Forbidden claim | Why |
|---|---|---|
| H1 | Any certification (ISO 27001, SOC 2, TÜV, "certified secure") | **Zero** artifacts exist — fabrication |
| H2 | "GDPR/DSGVO compliant" as a guarantee | Legal texts are unsigned drafts; no DPA concluded |
| H3 | "Unique / proprietary / world-first foresight method" | SPNP is peer-reviewed and used by competitors |
| H4 | Customer counts, logos, testimonials, "trusted by", revenue, ROI | No customers, no revenue |
| H5 | "Your data never leaves our servers" (blanket) | User PII goes to Stripe/Resend/Hetzner |
| H6 | Present-year absolute TIR ("AI improves X %/yr **today**") | Reliable only to ~2019; recent years withheld |
| H7 | "We predict the future / guaranteed foresight" | Engine reads direction from evidence; no guarantees |
| H8 | Specific token-speeds / benchmarks (129 t/s, etc.) as measured performance | Doc-only reference values, not reproducible |
| H9 | "Fully bilingual product" | Article content is English-only (DE columns NULL) |
| H10 | "Faster/cheaper than [named competitor]" | No benchmark; price band is an assumption |

---

## D. The five hero proof points (all V, all live-DB backed)

1. **1M+ signals analyzed · 60k+ articles published** (V1)
2. **science → patents → funding → market**, one corpus (V3)
3. **243** primary sources, every trend **clickable to its source** (V2, V5)
4. **~109 M-edge** patent graph → **Technology Improvement Rate** on the peer-reviewed MIT/SPNP method (V11)
5. **100 % local** analysis on one GPU; **honest by construction** (withholds what it can't prove) (V4, V13)
