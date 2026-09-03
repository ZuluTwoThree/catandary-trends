import type { Metadata } from "next";
import Link from "next/link";
import { getMethodologyStats } from "@/lib/db";
import HeroInstrument from "@/components/landing/HeroInstrument";
import LaunchCountdown from "@/components/landing/LaunchCountdown";
import TechReader from "@/components/landing/TechReader";
import MomentumBoard from "@/components/landing/MomentumBoard";
import ProofCounter from "@/components/landing/ProofCounter";
import Reveal from "@/components/landing/Reveal";
import { dynamicUnlessStatic } from "@/lib/renderMode";
import { sitePath } from "@/lib/sitePaths";

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
  await dynamicUnlessStatic();

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
      {/* ===== LAUNCH COUNTDOWN ===== */}
      <LaunchCountdown />

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
                source, and leave you unable to defend it to a stakeholder. Catandary was built
                to read the earlier stages — and to show its working every step of the way.
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
                <span className="lp-no">01 · Acquisition</span>
                <h3>We read the chain</h3>
                <p>
                  Referencing primary sources from open datasets across science, patents,
                  funding and market. No aggregator APIs, no scraping.
                </p>
                <span className="lp-tag">~250 sources</span>
              </div>
              <div className="lp-step">
                <span className="lp-no">02 · Classify</span>
                <h3>All local infrastructure</h3>
                <p>
                  We tag each signal on 8 industry verticals, 6 PESTEL dimensions and a
                  mega/macro/micro horizon. Nothing leaks into the cloud.
                </p>
                <span className="lp-tag">8 × 6 × 3 taxonomy</span>
              </div>
              <div className="lp-step">
                <span className="lp-no">03 · Cluster</span>
                <h3>Reason what&apos;s moving</h3>
                <p>
                  We group signals by meaning into clusters and rank by momentum — measured as
                  share of attention. Our growing corpus can&apos;t fake a growing trend.
                </p>
                <span className="lp-tag">221 live clusters</span>
              </div>
              <div className="lp-step">
                <span className="lp-no">04 · Attribute</span>
                <h3>We show the source</h3>
                <p>
                  Every signal links to the primary source it was built from. Any trend we
                  publish is based on data available for review.
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
                  <rect x="2" y="30" width="6" height="8" fill="var(--t-science)" />
                  <rect x="12" y="24" width="6" height="14" fill="var(--t-patent)" />
                  <rect x="22" y="18" width="6" height="20" fill="var(--t-funding)" />
                  <rect x="32" y="10" width="6" height="28" fill="var(--t-market)" />
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
                  Our Technology Improvement Estimate is built on peer-reviewed scientific
                  models developed at MIT. We process about 150 million data points from the
                  global patent body.
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
                  Our algorithm withholds information it can&apos;t trust — too recent, too noisy
                  or off the calibrated range — we publish only what the data proves. It says so
                  when we don&apos;t know.
                </p>
                <div className="lp-ev">Validation · known trends recovered and momentum confirmed</div>
              </article>
              <article className="lp-pillar">
                <svg className="lp-ic" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                  <rect x="4" y="4" width="32" height="32" rx="2" stroke="#d4ff3a" strokeWidth="2" />
                  <rect x="11" y="11" width="18" height="18" fill="#d4ff3a" opacity=".25" />
                  <circle cx="20" cy="20" r="3" fill="#d4ff3a" />
                </svg>
                <h3>Local, open, affordable</h3>
                <p>
                  Runs on local infrastructure and open data — no cloud cost, no vendor
                  lock-in — which is what puts board-grade foresight at a self-service price.
                </p>
                <div className="lp-ev">Cost · all local machines, no cloud in the loop</div>
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
                  Cluster momentum with one-click evidence — the format an innovation
                  team hands to a board, without the enterprise procurement.
                </p>
                <div className="lp-ev">Product · clusters · technology · lead-time · export</div>
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
            Choose a technology. Type and watch it read.
          </h2>
          <p className="lp-lede">
            Two questions our engine answers for any technology:{" "}
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
                  Filtering, classification, and our algorithms all run on our own local
                  infrastructure. Cloud is not the operating mode.
                </p>
                <div className="lp-ev">
                  Scope · applies to the content pipeline. Account &amp; email data use only
                  reputable processors.
                </div>
              </article>
              <article className="lp-pillar">
                <h3>Attribution enforced at the data layer</h3>
                <p>
                  In our database a trend without a source can&apos;t physically exist. And a
                  grounding check holds any article that introduces an unsourced figure.
                </p>
                <div className="lp-ev">Honesty · no fabricated info reaches publish</div>
              </article>
              <article className="lp-pillar">
                <h3>Tested, backed up, recoverable</h3>
                <p>
                  Continuous integration runs the suite against a real database on every change;
                  nightly backups have verified restores of 20-million-plus records. Ops
                  maturity, not aspiration.
                </p>
                <div className="lp-ev">Reliability · CI &amp; verified restore runbook</div>
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
                <span className="lp-who">free feed · analyses quoted per engagement</span>
                <ul>
                  <li>The whole chain: science → patents → funding → market</li>
                  <li>Every number one click from its primary source</li>
                  <li>Peer-reviewed scientific method, shown openly</li>
                  <li>Honest gates: withholds what it can&apos;t prove</li>
                  <li>Runs on our own hardware — no cloud, no platform fee</li>
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

      {/* ===== ACCESS (sales-led — no tiers, no checkout since #93) ===== */}
      <section className="lp-section" id="access" aria-labelledby="lp-access-h">
        <div className="lp-wrap">
          <span className="lp-eyebrow lp-kicker">Access</span>
          <h2 className="lp-section-h" id="lp-access-h">
            The feed is free. The engine is a conversation.
          </h2>
          <p className="lp-lede">
            No tiers, no checkout, no self-service. The public feed and the weekly briefing are
            open to everyone; everything deeper is scoped and quoted per engagement.
          </p>
          <Reveal>
            <div className="lp-prices lp-prices-3">
              <div className="lp-price">
                <span className="lp-pname">Free · for everyone</span>
                <div className="lp-amt lp-amt-text">The public feed</div>
                <p className="lp-blurb">
                  The last 30 days of trend articles, browsing, search and the weekly briefing.
                </p>
                <ul>
                  <li>Trend articles from the last 30 days — each with its primary source</li>
                  <li>Vertical &amp; PESTEL browsing, full-text search</li>
                  <li>28 Mega Signal Themes</li>
                  <li>Weekly newsletter with archive</li>
                </ul>
                <Link className="lp-btn lp-btn-primary" href="/trends/newsletter">
                  Get the weekly briefing
                </Link>
              </div>
              <div className="lp-price feat">
                <span className="lp-pname">Super Pro+ · ongoing</span>
                <div className="lp-amt lp-amt-text">Supervised access to the engine</div>
                <p className="lp-blurb">
                  Standing access to the full corpus and the tools behind it, as a supported
                  service.
                </p>
                <ul>
                  <li>Recurring analyses on your watch list</li>
                  <li>Clusters, technology trajectories, research &amp; patent explorers</li>
                  <li>Direct line to the person who built them</li>
                  <li>Scoped and quoted per engagement</li>
                </ul>
                <Link className="lp-btn lp-btn-primary" href={sitePath("/enquiry")}>
                  Talk to us
                </Link>
              </div>
              <div className="lp-price">
                <span className="lp-pname">Individual analysis · one question</span>
                <div className="lp-amt lp-amt-text">A dated, sourced write-up</div>
                <p className="lp-blurb">
                  Technology dossier, company dossier or trend assessment — built by hand from
                  the whole corpus.
                </p>
                <ul>
                  <li>One clearly scoped question</li>
                  <li>Fixed turnaround, agreed up front</li>
                  <li>Every claim with its primary source — including what the evidence does not show</li>
                  <li>Hands-on analyst days on request (Hypercare, billed by the day)</li>
                </ul>
                <Link className="lp-btn" href={sitePath("/enquiry")}>
                  Request an analysis
                </Link>
              </div>
            </div>
          </Reveal>
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
                ~250 primary sources — official APIs and open datasets across science, patents,
                public funding, and market news. No aggregator scraping; every source is curated
                by hand. Each published trend keeps a working link to the original.
              </p>
            </details>
            <details>
              <summary>Is the foresight method proprietary?</summary>
              <p>
                No — and we&apos;d rather be clear about that. Our Technology Improvement
                Estimate comes from peer-reviewed research at MIT. Others use it too. Our edge is
                the data corpus, the calibration, the evidence transparency and the price — not a
                secret formula.
              </p>
            </details>
            <details>
              <summary>How accurate is it — really?</summary>
              <p>
                On our own corpus the engine recovered known trends bottom-up and matched
                hand-checked momentum-direction calls against public reality. It withholds
                absolute improvement rates it can&apos;t yet trust and only headlines a number
                where the data proves it. Direction and shape are the most reliable output; we
                say so.
              </p>
            </details>
            <details>
              <summary>Is my data private?</summary>
              <p>
                The trend-analysis pipeline runs entirely on local infrastructure — the source
                corpus never touches a cloud API. There are no accounts: the only personal data
                we process is the email address you give us for the weekly briefing, delivered
                by an EU-based provider. We use no third-party analytics.
              </p>
            </details>
            <details>
              <summary>Who is it for?</summary>
              <p>
                Corporate innovation and foresight teams who need technology data they can
                defend; investors, agencies and consultants who need cited trend dossiers per
                client industry; and independent analysts who want data-driven
                &ldquo;what&apos;s rising&rdquo; without an enterprise contract.
              </p>
            </details>
            <details>
              <summary>What does it cost?</summary>
              <p>
                The last 30 days of trend articles and the weekly briefing are free. Everything
                deeper — Super Pro+ access and individual analyses — is scoped and quoted per
                engagement; hands-on analyst days are billed by the day. No tiers, no
                subscription: write to us with the question you need answered.
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
