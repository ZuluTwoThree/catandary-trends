import type { Metadata } from "next";
import Link from "next/link";
import { getMethodologyStats } from "@/lib/db";
import HeroInstrument from "@/components/landing/HeroInstrument";
import TechReader from "@/components/landing/TechReader";
import MomentumBoard from "@/components/landing/MomentumBoard";
import ProofCounter from "@/components/landing/ProofCounter";
import Reveal from "@/components/landing/Reveal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Catandary — See it in the research before you see it in the market",
  description:
    "Evidence-based, local-first trend & foresight intelligence. Catandary reads the whole innovation chain — science, patents, funding, market — and turns over a million signals into trend clusters, momentum and technology-improvement rates, every number traceable to its primary source.",
  openGraph: {
    title: "Catandary — Evidence-based trend & foresight intelligence",
    description:
      "Reads the whole innovation chain — science → patents → funding → market. Foresight you can cite.",
    type: "website",
  },
};

// Verified fallbacks (live DB, 2026-07-21) if the stats query is unavailable.
const FALLBACK = { analyzed: 1059838, published: 60482, sources: 243 };

export default async function LandingPage() {
  let stats = FALLBACK;
  try {
    const s = await getMethodologyStats();
    stats = {
      analyzed: s.analyzed || FALLBACK.analyzed,
      published: s.published || FALLBACK.published,
      sources: s.sources || FALLBACK.sources,
    };
  } catch {
    stats = FALLBACK;
  }

  const proof = [
    { value: stats.analyzed, display: "", label: "Signals analysed" },
    { value: stats.published, display: "", label: "Articles published" },
    { value: stats.sources, display: "", label: "Primary sources" },
    { value: null, display: "100%", label: "Local analysis" },
  ];

  return (
    <>
      {/* ===== HERO ===== */}
      <header className="lp-hero">
        <div className="lp-wrap lp-hero-grid">
          <div>
            <span className="lp-eyebrow">Evidence-based foresight</span>
            <h1 className="lp-hero-h">
              See it in the research <em>before</em> you see it in the market.
            </h1>
            <p className="lp-hero-sub">
              Catandary reads the whole innovation chain — science, patents, funding, market —
              and turns over a million signals into trend clusters, momentum and
              technology-improvement rates. Every number traces back to the primary source
              you can click.
            </p>
            <div className="lp-cta-row">
              <Link className="lp-btn lp-btn-primary" href="/trends/newsletter">
                Get the weekly briefing
              </Link>
              <Link className="lp-btn" href="/trends/foresight">
                Explore the live engine <span className="lp-arw">→</span>
              </Link>
            </div>
            <ProofCounter items={proof} />
          </div>
          <HeroInstrument />
        </div>
      </header>

      {/* ===== PROBLEM ===== */}
      <section className="lp-section" aria-labelledby="lp-problem-h">
        <div className="lp-wrap">
          <span className="lp-eyebrow lp-kicker" id="lp-problem-h">
            The gap
          </span>
          <Reveal>
            <div className="lp-problem-grid">
              <p className="lp-problem-big">
                By the time a trend is a headline, it is already late. The signal was in the{" "}
                <b>research years earlier</b>, then in the patents, then in the funding — long
                before it reached the market you read about.
              </p>
              <p>
                Most trend tools only watch the market: press releases and news, the last stop
                on the chain. So they tell you what already happened, hand you a number with no
                source, and leave you unable to defend it. Catandary was built to read the
                earlier stages — and to show its working every step of the way.
              </p>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ===== MECHANISM ===== */}
      <section className="lp-section" id="mechanism" aria-labelledby="lp-mech-h">
        <div className="lp-wrap">
          <span className="lp-eyebrow lp-kicker">How it works</span>
          <h2 className="lp-section-h" id="lp-mech-h">
            Four moves from raw signal to defensible insight.
          </h2>
          <Reveal>
            <div className="lp-steps">
              <div className="lp-step">
                <span className="lp-no">01 · Collect</span>
                <h3>Read the chain</h3>
                <p>
                  Only legal primary sources — RSS, official APIs and open datasets — across
                  science, patents, funding and market. No aggregators, no scraping.
                </p>
                <span className="lp-tag">243 sources</span>
              </div>
              <div className="lp-step">
                <span className="lp-no">02 · Classify</span>
                <h3>Locally, on one GPU</h3>
                <p>
                  Local models tag each signal on 8 industry verticals, 6 PESTEL dimensions
                  and a mega/macro/micro horizon. Nothing leaves the machine.
                </p>
                <span className="lp-tag">8 × 6 × 3 taxonomy</span>
              </div>
              <div className="lp-step">
                <span className="lp-no">03 · Cluster</span>
                <h3>Find what&apos;s moving</h3>
                <p>
                  Signals group by meaning into trend clusters, ranked by momentum — measured
                  as share of attention, so a growing corpus can&apos;t fake a growing trend.
                </p>
                <span className="lp-tag">221 live clusters</span>
              </div>
              <div className="lp-step">
                <span className="lp-no">04 · Attribute</span>
                <h3>Show the source</h3>
                <p>
                  Every trend links back to the primary source it was built from. Any article
                  that invents a figure or date is held for review, not published.
                </p>
                <span className="lp-tag">source enforced</span>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ===== PILLARS ===== */}
      <section className="lp-section" aria-labelledby="lp-pil-h">
        <div className="lp-wrap">
          <span className="lp-eyebrow lp-kicker">Why it&apos;s different</span>
          <h2 className="lp-section-h" id="lp-pil-h">
            Foresight you can actually cite.
          </h2>
          <Reveal>
            <div className="lp-pillars">
              <article className="lp-pillar">
                <svg className="lp-ic" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                  <rect x="2" y="30" width="6" height="8" fill="#a78bfa" />
                  <rect x="12" y="24" width="6" height="14" fill="#60a5fa" />
                  <rect x="22" y="18" width="6" height="20" fill="#34d399" />
                  <rect x="32" y="10" width="6" height="28" fill="#d4ff3a" />
                </svg>
                <h3>The whole chain, one corpus</h3>
                <p>
                  Science, patents, funding and market signals sit on a single lead-time axis,
                  so you see how <em>early</em> a theme is — not just that it has arrived.
                </p>
                <div className="lp-ev">Evidence · 4 tiers, ~42.6M patents to 1990</div>
              </article>
              <article className="lp-pillar">
                <svg className="lp-ic" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                  <circle cx="16" cy="16" r="11" stroke="#d4ff3a" strokeWidth="2" />
                  <path d="M24 24l12 12" stroke="#d4ff3a" strokeWidth="2" />
                </svg>
                <h3>Evidence, not vibes</h3>
                <p>
                  Every trend, cluster and rate links to its primary source. A grounding gate
                  holds back any generated figure that isn&apos;t in the source material.
                </p>
                <div className="lp-ev">Evidence · source_url NOT NULL + grounding gate</div>
              </article>
              <article className="lp-pillar">
                <svg className="lp-ic" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                  <path d="M3 30C10 30 12 8 20 8s10 22 17 22" stroke="#d4ff3a" strokeWidth="2" fill="none" />
                  <circle cx="37" cy="30" r="3" fill="#d4ff3a" />
                </svg>
                <h3>Improvement rates that mean something</h3>
                <p>
                  A Technology Improvement Rate built on the peer-reviewed SPNP method (Singh,
                  Triulzi &amp; Magee, 2021), read over a ~109-million-edge patent-citation graph.
                </p>
                <div className="lp-ev">Method · peer-reviewed, not proprietary</div>
              </article>
              <article className="lp-pillar">
                <svg className="lp-ic" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                  <path d="M20 4l14 6v9c0 9-6 14-14 17-8-3-14-8-14-17V10z" stroke="#d4ff3a" strokeWidth="2" fill="none" />
                  <path d="M14 20l4 4 8-9" stroke="#d4ff3a" strokeWidth="2" fill="none" />
                </svg>
                <h3>Honest by construction</h3>
                <p>
                  The engine withholds rates it can&apos;t trust — too recent, or off the
                  calibrated range — and only puts a lead-time number where the data proves it.
                  It says &ldquo;unknown&rdquo; when it doesn&apos;t know.
                </p>
                <div className="lp-ev">Validation · 23/24 known trends, 6/6 momentum</div>
              </article>
              <article className="lp-pillar">
                <svg className="lp-ic" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                  <rect x="4" y="4" width="32" height="32" rx="2" stroke="#d4ff3a" strokeWidth="2" />
                  <rect x="11" y="11" width="18" height="18" fill="#d4ff3a" opacity=".25" />
                  <circle cx="20" cy="20" r="3" fill="#d4ff3a" />
                </svg>
                <h3>Local, open, affordable</h3>
                <p>
                  Runs on local models and open data — no per-token cloud cost, no single-vendor
                  lock-in — which is what puts board-grade foresight at a self-service price.
                </p>
                <div className="lp-ev">Cost · one 24GB GPU, no cloud in the loop</div>
              </article>
              <article className="lp-pillar">
                <svg className="lp-ic" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                  <circle cx="20" cy="20" r="16" stroke="#8a8d82" strokeWidth="1.5" />
                  <circle cx="20" cy="20" r="9" stroke="#8a8d82" strokeWidth="1.5" />
                  <circle cx="27" cy="13" r="3" fill="#d4ff3a" />
                  <circle cx="14" cy="24" r="2.4" fill="#60a5fa" />
                </svg>
                <h3>The deliverable teams already think in</h3>
                <p>
                  A trend radar with lead-time rings, cluster momentum, and one-click evidence —
                  the format an innovation team hands to a board, without the enterprise
                  procurement.
                </p>
                <div className="lp-ev">Product · radar · clusters · technology · export</div>
              </article>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ===== INTERACTIVE DEMO ===== */}
      <section className="lp-section" id="engine" aria-labelledby="lp-demo-h">
        <div className="lp-wrap">
          <span className="lp-eyebrow lp-kicker">Read the instrument</span>
          <h2 className="lp-section-h" id="lp-demo-h">
            Pick a technology. Watch it read.
          </h2>
          <p className="lp-lede">
            Two questions the engine answers for any technology:{" "}
            <span className="lp-hi">how early is it</span> across the innovation chain, and{" "}
            <span className="lp-hi">how fast is it actually improving</span>.
          </p>
          <TechReader />
          <div className="lp-cta-row">
            <Link className="lp-btn" href="/trends/foresight/technology">
              Try it live on your own technology <span className="lp-arw">→</span>
            </Link>
          </div>
        </div>
      </section>

      {/* ===== MOMENTUM BOARD ===== */}
      <section className="lp-section" aria-labelledby="lp-mov-h">
        <div className="lp-wrap">
          <span className="lp-eyebrow lp-kicker">Live intelligence</span>
          <h2 className="lp-section-h" id="lp-mov-h">
            What&apos;s moving now.
          </h2>
          <p className="lp-lede">
            Clusters the engine surfaced bottom-up, ranked by share-of-voice momentum. These six
            were hand-checked against public reality — and all six matched.
          </p>
          <MomentumBoard />
          <div className="lp-cta-row">
            <Link className="lp-btn" href="/trends/foresight/clusters">
              See the full cluster board <span className="lp-arw">→</span>
            </Link>
          </div>
        </div>
      </section>

      {/* ===== TRUST / TECHNOLOGY ===== */}
      <section className="lp-section" aria-labelledby="lp-trust-h">
        <div className="lp-wrap">
          <span className="lp-eyebrow lp-kicker">Technology &amp; trust</span>
          <h2 className="lp-section-h" id="lp-trust-h">
            Built to be checked.
          </h2>
          <Reveal>
            <div className="lp-pillars" style={{ marginTop: "2.2rem" }}>
              <article className="lp-pillar">
                <h3>Local-first analysis</h3>
                <p>
                  Filtering, classification, embeddings and article generation all run on local
                  models on the owner&apos;s own GPU. Cloud is a scoped, one-time backfill
                  exception — never the operating mode.
                </p>
                <div className="lp-ev">
                  Scope · applies to the content pipeline. Account &amp; email data use named EU
                  processors (Stripe, Resend, Hetzner).
                </div>
              </article>
              <article className="lp-pillar">
                <h3>Attribution enforced at the data layer</h3>
                <p>
                  A trend without a source URL can&apos;t physically exist — it&apos;s a
                  NOT-NULL column, not a template convention. And a grounding check holds any
                  article that introduces an unsourced figure.
                </p>
                <div className="lp-ev">Honesty · no fabricated numbers reach auto-publish</div>
              </article>
              <article className="lp-pillar">
                <h3>Tested, backed up, recoverable</h3>
                <p>
                  Continuous integration runs the suite against a real vector database on every
                  change; nightly backups have a verified restore of 20-million-plus rows. Ops
                  maturity, not aspiration.
                </p>
                <div className="lp-ev">Reliability · CI + verified restore runbook</div>
              </article>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ===== DIFFERENTIATION ===== */}
      <section className="lp-section" aria-labelledby="lp-cmp-h">
        <div className="lp-wrap">
          <span className="lp-eyebrow lp-kicker">Where it sits</span>
          <h2 className="lp-section-h" id="lp-cmp-h">
            Between the black box and the enterprise contract.
          </h2>
          <Reveal>
            <div className="lp-compare">
              <div className="lp-col">
                <h3>Keyword trend tools</h3>
                <span className="lp-who">≈ €0–100 / mo</span>
                <ul>
                  <li>Watch the market only — the last stop</li>
                  <li>A score with no source behind it</li>
                  <li>Opaque scoring you can&apos;t defend</li>
                  <li>No patent or science signal</li>
                </ul>
              </div>
              <div className="lp-col mid">
                <h3>Catandary</h3>
                <span className="lp-who">€0 free · €99–799 / mo</span>
                <ul>
                  <li>The whole chain: science → patents → funding → market</li>
                  <li>Every number one click from its primary source</li>
                  <li>Peer-reviewed improvement-rate method, shown openly</li>
                  <li>Honest gates: withholds what it can&apos;t prove</li>
                  <li>Local models → self-service price</li>
                </ul>
              </div>
              <div className="lp-col">
                <h3>Enterprise foresight suites</h3>
                <span className="lp-who">€50k+ / year</span>
                <ul>
                  <li>Powerful, broad coverage</li>
                  <li>Closed methodology, long procurement</li>
                  <li>Priced for large organisations</li>
                  <li>Rarely traceable to the raw source</li>
                </ul>
              </div>
            </div>
          </Reveal>
          <p className="lp-note" style={{ maxWidth: "60em" }}>
            Positioning, not a benchmark: the €50k+ and keyword-tool boundaries are our read of
            the market, offered to show where Catandary aims — not a head-to-head test.
          </p>
        </div>
      </section>

      {/* ===== PRICING ===== */}
      <section className="lp-section" id="pricing" aria-labelledby="lp-price-h">
        <div className="lp-wrap">
          <span className="lp-eyebrow lp-kicker">Access</span>
          <h2 className="lp-section-h" id="lp-price-h">
            Start free. Grow into the engine.
          </h2>
          <p className="lp-lede">
            The free layer is the real product — 60,000+ curated articles and a weekly briefing.
            The paid tiers open the foresight engine.
          </p>
          <Reveal>
            <div className="lp-prices">
              <div className="lp-price">
                <span className="lp-pname">Free</span>
                <div className="lp-amt">€0</div>
                <p className="lp-blurb">
                  Curated trend articles, browsing, search and the weekly newsletter.
                </p>
                <ul>
                  <li>Published trend articles</li>
                  <li>Vertical &amp; PESTEL browsing</li>
                  <li>Search</li>
                  <li>Weekly newsletter</li>
                  <li>Corpus counter &amp; mega-trend teasers</li>
                </ul>
                <Link className="lp-btn lp-btn-primary" href="/trends/newsletter">
                  Start free
                </Link>
              </div>
              <div className="lp-price">
                <span className="lp-pname">Starter</span>
                <div className="lp-amt">
                  €99<small>/mo</small>
                </div>
                <p className="lp-blurb">
                  Watch what&apos;s moving: the cluster explorer with momentum and evidence.
                </p>
                <ul>
                  <li>Everything in Free</li>
                  <li>Cluster explorer</li>
                  <li>Trend radar</li>
                  <li>Saved searches &amp; alerts</li>
                </ul>
                <Link className="lp-btn" href="/trends/pricing">
                  Request early access
                </Link>
              </div>
              <div className="lp-price feat">
                <span className="lp-pname">Pro</span>
                <div className="lp-amt">
                  €499<small>/mo</small>
                </div>
                <p className="lp-blurb">
                  The foresight edge: lead-time, technology trajectories and export.
                </p>
                <ul>
                  <li>Everything in Starter</li>
                  <li>Technology explorer &amp; CPC lead-time</li>
                  <li>TIR metrics &amp; trajectory</li>
                  <li>Trend evolution &amp; lineage</li>
                  <li>CSV / dossier export</li>
                </ul>
                <Link className="lp-btn lp-btn-primary" href="/trends/pricing">
                  Request early access
                </Link>
              </div>
              <div className="lp-price">
                <span className="lp-pname">Super Pro+</span>
                <div className="lp-amt">
                  €799<small>/mo</small>
                </div>
                <p className="lp-blurb">
                  Ask the engine your own questions: on-demand analysis and API.
                </p>
                <ul>
                  <li>Everything in Pro</li>
                  <li>On-demand analysis of your scopes</li>
                  <li>
                    API access <em>— coming soon</em>
                  </li>
                  <li>Raw evidence graph</li>
                  <li>Custom reports</li>
                </ul>
                <Link className="lp-btn" href="/trends/pricing">
                  Request early access
                </Link>
              </div>
            </div>
          </Reveal>
          <div className="lp-hypercare">
            <div>
              <div className="lp-amt">
                Hypercare · €1,499
                <small style={{ fontFamily: "var(--font-mono)", fontSize: ".7rem", color: "var(--color-muted)" }}>
                  /day
                </small>
              </div>
              <p style={{ fontSize: ".85rem", color: "var(--color-muted)", marginTop: ".4rem", maxWidth: "40em" }}>
                Dedicated, hands-on analyst support tailored to your questions — a bespoke
                engagement, not a subscription. €999/day from the second engagement.
              </p>
            </div>
            <a className="lp-btn" href="mailto:trends@catandary.de?subject=Catandary%20Hypercare">
              Talk to us
            </a>
          </div>
        </div>
      </section>

      {/* ===== FAQ ===== */}
      <section className="lp-section" aria-labelledby="lp-faq-h">
        <div className="lp-wrap">
          <span className="lp-eyebrow lp-kicker">Questions</span>
          <h2 className="lp-section-h" id="lp-faq-h">
            The honest answers.
          </h2>
          <div className="lp-faq">
            <details open>
              <summary>Where does the data come from?</summary>
              <p>
                243 legal primary sources — trade-press RSS feeds, official APIs and open
                datasets across science (OpenAlex, preprints), patents, public funding, and
                market news. No aggregator scraping; every source is curated by hand. Each
                published trend keeps a working link to the original.
              </p>
            </details>
            <details>
              <summary>Is the foresight method proprietary?</summary>
              <p>
                No — and we&apos;d rather be clear about that. The Technology Improvement Rate is
                built on a published, peer-reviewed method (SPNP citation centrality; Singh,
                Triulzi &amp; Magee, Research Policy, 2021). Others use it too. Our edge is the
                corpus, the calibration, the evidence transparency and the price — not a secret
                formula.
              </p>
            </details>
            <details>
              <summary>How accurate is it — really?</summary>
              <p>
                On our own corpus the engine recovered 23 of 24 known trends bottom-up and
                matched 6 of 6 hand-checked momentum-direction calls against public reality. It
                withholds absolute improvement rates it can&apos;t yet trust (recent years, or
                beyond the calibrated range) and only headlines a lead-time number where the data
                proves it. Direction and shape are the reliable output; we say so.
              </p>
            </details>
            <details>
              <summary>Is my data private?</summary>
              <p>
                The trend-analysis pipeline runs entirely on local models — the source corpus
                never touches a cloud API. If you create an account, the data needed to run it
                (your email for login and the newsletter, payment status for billing) is
                processed by named EU-based providers (Resend, Stripe, Hetzner). We use no
                third-party analytics and no tracking cookies.
              </p>
            </details>
            <details>
              <summary>Who is it for?</summary>
              <p>
                Corporate innovation and foresight teams who need a radar they can defend;
                agencies and consultants who need cited trend dossiers per client industry; and
                independent analysts who want data-driven &ldquo;what&apos;s rising&rdquo; without
                an enterprise contract.
              </p>
            </details>
            <details>
              <summary>What does it cost?</summary>
              <p>
                The content layer and weekly briefing are free. The foresight engine is €99
                (Starter), €499 (Pro) or €799 (Super Pro+) per month, with a sales-led Hypercare
                day-rate for bespoke work. The paid tiers are opening in early access.
              </p>
            </details>
          </div>
        </div>
      </section>

      {/* ===== FINAL CTA ===== */}
      <section className="lp-section lp-final" id="subscribe" aria-labelledby="lp-final-h">
        <div className="lp-wrap">
          <span className="lp-eyebrow lp-plain lp-kicker" style={{ justifyContent: "center" }}>
            Foresight you can cite
          </span>
          <h2 className="lp-section-h" id="lp-final-h">
            See it early.
            <br />
            Then prove it.
          </h2>
          <p className="lp-lede">
            One email a week: the trends rising across science, patents and funding — before they
            reach the market — each linked to its source.
          </p>
          <div className="lp-cta-row" style={{ justifyContent: "center" }}>
            <Link className="lp-btn lp-btn-primary" href="/trends/newsletter">
              Get the weekly briefing
            </Link>
            <Link className="lp-btn" href="/trends">
              Browse the trends <span className="lp-arw">→</span>
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
