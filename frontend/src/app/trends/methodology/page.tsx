import { getMethodologyStats } from "@/lib/db";
import ForesightCta from "@/components/ForesightCta";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "How We Measure — Catandary Trends",
  description:
    "Our method: legal primary sources across four lead-time tiers (research, patents, funding, market), analyzed by local models, with every trend traceable to its original source.",
};

const TIERS = [
  {
    key: "science",
    label: "Science",
    color: "#a78bfa",
    horizon: "earliest",
    desc: "Peer-reviewed research and preprints (OpenAlex, arXiv, bioRxiv, journals). The first place a new idea appears — often years before the market.",
  },
  {
    key: "patent",
    label: "Patents",
    color: "#60a5fa",
    horizon: "early",
    desc: "Patent filings (EPO, DOCDB). Committed R&D investment, filed on average ~7 years before a technology reaches the market.",
  },
  {
    key: "funding",
    label: "Funding",
    color: "#34d399",
    horizon: "mid",
    desc: "Public research & innovation grants (NSF, NIH, OpenAIRE, UKRI). Where money is being committed — before the products exist.",
  },
  {
    key: "market",
    label: "Market",
    color: "#d4ff3a",
    horizon: "now",
    desc: "Trade press, industry newsrooms and press wires. Confirmation that a trend has reached the market.",
  },
];

function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div className="font-display text-[34px] md:text-[40px] leading-none text-paper tabular-nums">
        {value}
      </div>
      <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted mt-2">
        {label}
      </div>
    </div>
  );
}

export default async function MethodologyPage() {
  const s = await getMethodologyStats();

  return (
    <div className="mx-auto max-w-4xl px-6 md:px-10 py-14">
      {/* Hero */}
      <div className="mb-14">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Method &amp; Trust
        </div>
        <h1 className="font-display text-4xl md:text-[56px] leading-[1.03] tracking-tight text-paper mb-5">
          How we <span className="italic">measure</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          No black box. We read legal primary sources across four lead-time
          tiers, analyze them with local models, and keep every trend traceable
          to the original source you can click through to.
        </p>
      </div>

      {/* Numbers */}
      <section className="mb-16 grid grid-cols-2 md:grid-cols-4 gap-8 border-y border-border py-10">
        <Stat value={fmt(s.analyzed)} label="Signals analyzed" />
        <Stat value={fmt(s.published)} label="Curated articles" />
        <Stat value={fmt(s.sources)} label="Active sources" />
        <Stat value={fmt(s.megaTrends)} label="Mega-trends" />
      </section>

      {/* The four tiers */}
      <section className="mb-16">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-6">
          01 — The lead-time chain
        </div>
        <p className="font-sans text-text leading-relaxed max-w-2xl mb-8">
          A trend rarely appears everywhere at once. It shows up first in
          research, then in patents and funding, and only later in the market.
          By tracking all four tiers separately, we can see where a theme is
          today — and how early it is.
        </p>
        <div className="space-y-3">
          {TIERS.map((t, i) => (
            <div
              key={t.key}
              className="border border-border border-l-[3px] bg-card/40 p-5 flex items-start gap-5"
              style={{ borderLeftColor: t.color }}
            >
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted shrink-0 pt-1 w-6">
                {String(i + 1).padStart(2, "0")}
              </div>
              <div className="min-w-0">
                <div className="flex items-baseline gap-3 mb-1 flex-wrap">
                  <span
                    className="font-display text-[20px] text-paper"
                    style={{ color: t.color }}
                  >
                    {t.label}
                  </span>
                  <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted">
                    {t.horizon}
                  </span>
                  {s.tierCounts[t.key] !== undefined && (
                    <span className="font-mono text-[10px] text-muted tabular-nums">
                      {fmt(s.tierCounts[t.key])} signals
                    </span>
                  )}
                </div>
                <p className="font-sans text-sm text-text leading-relaxed">
                  {t.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
        <p className="font-sans text-sm text-muted leading-relaxed max-w-2xl mt-6">
          Measured in our own corpus: patent signals precede the market by a
          median of ~7 years across trend clusters. Coverage spans
          {s.dateSpan.first ? ` ${s.dateSpan.first}` : ""} to
          {s.dateSpan.last ? ` ${s.dateSpan.last}` : ""}.
        </p>
      </section>

      {/* Pipeline */}
      <section className="mb-16">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-6">
          02 — From source to signal
        </div>
        <ol className="space-y-4 max-w-2xl">
          {[
            ["Collect", "We pull only legal primary sources — RSS feeds, official APIs and open datasets. No aggregators, no scraping of third-party content."],
            ["Filter", "Each item is judged for relevance and de-duplicated, so noise and repeats never reach the analysis."],
            ["Classify", "Local models assign industry verticals, PESTEL dimensions, signal type and a canonical signal theme."],
            ["Cluster", "Signals are grouped by meaning (their embeddings), revealing trend clusters and their momentum over time."],
            ["Attribute", "Every published article and every cluster links back to the primary sources it is built from."],
          ].map(([step, desc], i) => (
            <li key={step} className="flex items-start gap-5">
              <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent shrink-0 pt-1 w-6">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div>
                <span className="font-display text-[17px] text-paper">{step}. </span>
                <span className="font-sans text-sm text-text leading-relaxed">{desc}</span>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* Trust commitments */}
      <section className="mb-16">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-6">
          03 — What you can rely on
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[
            ["Traceable", "Every trend links to its primary source. Nothing is asserted without a citation you can check."],
            ["Independent", "We run on local models and open data — not on any single vendor's feed or agenda."],
            ["Relevance-scored", "Each signal carries a Catandary Relevance Score (0–100) weighing cross-industry impact, breadth and maturity."],
            ["Momentum, normalized", "Trend momentum is measured as share of attention over time, so a growing corpus never masquerades as a growing trend."],
          ].map(([h, d]) => (
            <div key={h} className="border border-border bg-card/40 p-5">
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent mb-2">
                {h}
              </div>
              <p className="font-sans text-sm text-text leading-relaxed">{d}</p>
            </div>
          ))}
        </div>
      </section>

      <ForesightCta />
    </div>
  );
}
