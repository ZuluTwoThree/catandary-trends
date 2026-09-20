import { getMethodologyStats } from "@/lib/db";
import ForesightCta from "@/components/ForesightCta";
import { dynamicUnlessStatic } from "@/lib/renderMode";

export const metadata = {
  title: "How We Measure — Catandary Trends",
  description:
    "Our method: the Catandary proprietary database across four lead-time tiers (science, patents, funding, market), measured by local models, with every trend traceable to its source.",
};

const TIERS = [
  {
    key: "science",
    label: "Science",
    color: "#a78bfa",
    horizon: "earliest",
    desc: "Peer-reviewed research and preprints — 45.5 million scholarly works. The first place a new idea appears, often years before the market.",
  },
  {
    key: "patent",
    label: "Patents",
    color: "#60a5fa",
    horizon: "early",
    desc: "Patent records — 42.6 million, 18.7 million of them in the citation graph our sheets measure. Committed R&D investment, filed on average ~7 years before a technology reaches the market.",
  },
  {
    key: "funding",
    label: "Funding",
    color: "#34d399",
    horizon: "mid",
    desc: "Public research and innovation grants, and financing rounds reported in the trade press. Where money is being committed — before the products exist.",
  },
  {
    key: "market",
    label: "Market",
    color: "#d4ff3a",
    horizon: "now",
    desc: "Trade press, company newsrooms and press releases across eight industries. Confirmation that a trend has reached the market.",
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
  await dynamicUnlessStatic();
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
          No black box. We measure the Catandary proprietary database — 21.9
          million dated signals since 1990 — across four lead-time tiers with
          local models, and keep every trend traceable to a source you can
          click through to.
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
          Measured in the database: patent signals precede the market by a
          median of ~7 years across trend clusters. Coverage spans
          {s.dateSpan.first ? ` ${s.dateSpan.first}` : ""} to
          {s.dateSpan.last ? ` ${s.dateSpan.last}` : ""}.
        </p>
      </section>

      {/* Pipeline */}
      <section className="mb-16">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-6">
          02 — From the database to a signal
        </div>
        <ol className="space-y-4 max-w-2xl">
          {[
            ["Hold", "The Catandary proprietary database keeps every signal dated and attributed to its source — science, patents, funding and market, since 1990."],
            ["Filter", "Each item is judged for relevance and de-duplicated, so noise and repeats never reach the analysis."],
            ["Classify", "Local models assign industry verticals, PESTEL dimensions, signal type and a canonical signal theme."],
            ["Cluster", "Signals are grouped by meaning (their embeddings), revealing trend clusters and their momentum over time."],
            ["Attribute", "Every published article and every cluster links back to the sources it is built from."],
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
            ["Traceable", "Every trend links to its source. Nothing is asserted without a citation you can check."],
            ["Independent", "We run on local models and our own database — not on any single vendor's feed or agenda."],
            ["Relevance-scored", "Each signal carries a Catandary Relevance Score (0–100) weighing cross-industry impact, breadth and maturity."],
            ["Momentum, normalized", "Trend momentum is measured as share of attention over time, so a growing database never masquerades as a growing trend."],
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

      {/* Field method — the rules printed on every Trajectory Sheet / Field
          Watch (owner 2026-09-20). Same wording as the sheets' "Methodik"
          table; if a rule changes there, it changes here. */}
      <section id="field-method" className="mb-16">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-6">
          04 — How a field is measured
        </div>
        <p className="font-sans text-sm text-text leading-relaxed max-w-2xl mb-5">
          Our client reports (Trajectory Sheet, Field Watch) measure one field across four tiers. These are
          the rules behind every number; each sheet prints them together with its n, window and method.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[
            ["Field", "A list of search phrases, matched against the signal records and the patent records of the database, plus one or more patent classes for the citation graph. Mapped by us, signed off by the client, printed on the sheet."],
            ["Tier", "By kind of record: science (papers and preprints), patents, funding (public grants and financing rounds — including rounds reported in the trade press), market (trade press, company newsrooms, press releases)."],
            ["Share, not count", "Yearly and quarterly figures are shares per 10,000 signals of that tier — this removes our own collection ramp. Quarters use a fixed source panel: only sources active in both the first and the last four quarters of the window count."],
            ["Take-off", "The first year a tier reaches 15 % of its peak year with at least three hits. A take-off at the edge of a data window is reported as a boundary, never as a lead time."],
            ["Improvement rate", "Peer-reviewed SPNP method on the patent citation graph, five-year windows, median over complete windows. Calibrated to ~2019; later windows carry the direction, not the magnitude. It is a relative rate, not a forecast."],
            ["Thin cells", "Where a tier has fewer than five signals, where a window is incomplete, or where only 13 % of press rows carry an extracted actor name, the sheet says so in a table. No model writes any part of a sheet; one paragraph of reading is written by a person and labelled."],
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

      {/* Our AI agent — the page the User-Agent points at (V2, 2026-09-11):
          the agent names itself and links here; the contact lives here, not in
          every publisher's request log. Owner 2026-09-20: "AI agent", not
          "crawler" — the facts publishers need (token, rate, robots, TDM
          opt-outs, contact) stay exactly as they were. */}
      <section id="ai-agent" className="mb-16">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-6">
          05 — Our AI agent
        </div>
        <div className="border border-border bg-card/40 p-5 space-y-3">
          <p className="font-sans text-sm text-text leading-relaxed">
            The Catandary AI agent reads publicly available articles to keep the database current across
            industries. It identifies itself as <code className="font-mono text-[12px] text-paper">CatandaryTrendsBot/1.0</code>,
            requests at most one page per second per site, and respects <code className="font-mono text-[12px]">robots.txt</code>{" "}
            (address the token <code className="font-mono text-[12px]">CatandaryTrendsBot</code> to allow, limit or exclude it).
          </p>
          <p className="font-sans text-sm text-text leading-relaxed">
            Machine-readable opt-outs from text and data mining are honoured on every page: the{" "}
            <code className="font-mono text-[12px]">TDM-Reservation</code> header, the{" "}
            <code className="font-mono text-[12px]">tdm-reservation</code> meta tag,{" "}
            <code className="font-mono text-[12px]">noai</code> robots directives and{" "}
            <code className="font-mono text-[12px]">/.well-known/tdmrep.json</code>. Where an opt-out is set, only the
            headline and the feed teaser are kept. Every published trend links back to its source.
          </p>
          <p className="font-sans text-sm text-text leading-relaxed">
            Questions, corrections or removal requests:{" "}
            <a href="mailto:trends@catandary.de" className="text-accent underline underline-offset-4">trends@catandary.de</a>
            {" "}— removal requests are acted on within 72 hours.
          </p>
        </div>
      </section>

      <ForesightCta />
    </div>
  );
}
