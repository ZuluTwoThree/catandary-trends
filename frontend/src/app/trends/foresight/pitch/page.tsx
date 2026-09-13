import Link from "next/link";
import DeckNav from "@/components/foresight/DeckNav";
import { getBriefingStats } from "@/lib/db";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Catandary Foresight — Briefing",
  description:
    "Situation, complication, resolution: how Catandary Foresight turns a corpus of research, patents, funding and market signals into dated, source-checked technology dossiers.",
};

/**
 * /trends/foresight/pitch — the customer briefing, in the browser.
 *
 * A deck, not a page: one idea per screen, presented from the owner instance
 * (Tailscale Serve) to a prospect. Built on the McKinsey SCR-Q frame —
 * Situation, Complication, Resolution, Question — because that is the order a
 * board hears an argument in. Owner-only like the rest of /trends/foresight
 * (PUBLIC_MODE 404, not in the static export): the numbers are live corpus
 * aggregates, and the page cites work that is still in review.
 *
 * Honesty rules from the launch site apply (docs/launch/): no method USP,
 * no customer logos, TIR framed as relative development rather than
 * prediction, corpus numbers from the database rather than a slide from May.
 */

const fmt = (n: number | null) => (n == null ? "—" : new Intl.NumberFormat("en-US").format(n));
const compact = (n: number | null) =>
  n == null
    ? "—"
    : n >= 1_000_000
      ? `${(n / 1_000_000).toFixed(1)} M`
      : n >= 1_000
        ? `${(n / 1_000).toFixed(0)} k`
        : fmt(n);

const SLIDES = [
  "Cover",
  "Situation",
  "Complication",
  "Resolution",
  "How it is checked",
  "Question",
  "Limits & contact",
];

function Slide({
  id,
  eyebrow,
  children,
}: {
  id: number;
  eyebrow: string;
  children: React.ReactNode;
}) {
  return (
    <section
      data-slide
      id={`s${id}`}
      className="flex min-h-[92vh] scroll-mt-4 flex-col justify-center border-t border-border px-6 py-16 md:px-10"
    >
      <div className="mx-auto w-full max-w-5xl">
        <div className="mb-8 flex items-center justify-between">
          <span className="eyebrow">{eyebrow}</span>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
            {String(id + 1).padStart(2, "0")} / {String(SLIDES.length).padStart(2, "0")}
          </span>
        </div>
        {children}
      </div>
    </section>
  );
}

function Big({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="font-display text-[clamp(2rem,4.6vw,3.6rem)] font-medium leading-[1.05] tracking-tight text-paper">
      {children}
    </h2>
  );
}

function Lede({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-6 max-w-3xl font-sans text-[clamp(1.05rem,1.5vw,1.3rem)] leading-relaxed text-text">
      {children}
    </p>
  );
}

function Cell({ no, title, body }: { no: string; title: string; body: React.ReactNode }) {
  return (
    <div className="bg-card p-6">
      <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-accent">{no}</div>
      <h3 className="font-display text-[1.25rem] font-medium text-paper">{title}</h3>
      <p className="mt-2 font-sans text-[0.95rem] leading-relaxed text-muted">{body}</p>
    </div>
  );
}

export default async function PitchPage() {
  const st = await getBriefingStats();

  return (
    <div className="relative">
      <DeckNav count={SLIDES.length} labels={SLIDES} />

      {/* 01 — Cover */}
      <section
        data-slide
        id="s0"
        className="flex min-h-[92vh] flex-col justify-center px-6 py-16 md:px-10"
      >
        <div className="mx-auto w-full max-w-5xl">
          <span className="eyebrow">Catandary Foresight · Briefing</span>
          <h1 className="mt-6 font-display text-[clamp(2.6rem,6.5vw,5.2rem)] font-medium leading-[1.02] tracking-tight text-paper">
            Read the signal <span className="italic text-accent">years</span> before it becomes news.
          </h1>
          <Lede>
            Technology foresight built on a corpus, not on opinion: research, patents,
            funding and market signals read together, measured against the patent record,
            and written up as dated, source-checked dossiers — with a person signing off
            before anything leaves the house.
          </Lede>
          <div className="lp-proof mt-10">
            <div>
              <div className="lp-num">{fmt(st.sources)}</div>
              <div className="lp-lbl">active sources</div>
            </div>
            <div>
              <div className="lp-num">{compact(st.analyzed)}</div>
              <div className="lp-lbl">signals analysed</div>
            </div>
            <div>
              <div className="lp-num">{compact(st.researchWorks)}</div>
              <div className="lp-lbl">research works indexed (≈)</div>
            </div>
            <div>
              <div className="lp-num">{compact(st.patents)}</div>
              <div className="lp-lbl">patents with citation graph</div>
            </div>
          </div>
          <p className="mt-8 font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
            Use ← → to move · numbers are live from the corpus
          </p>
        </div>
      </section>

      {/* 02 — Situation */}
      <Slide id={1} eyebrow="Situation">
        <Big>
          Strategy teams decide on technology from trade press and analyst decks.
        </Big>
        <Lede>
          That is not a failing — it is what is readable. But innovation does not start
          where the press picks it up. It moves through four layers, in order, and each
          layer is public years before the next one.
        </Lede>
        <div className="mt-10 grid grid-cols-1 gap-px bg-border md:grid-cols-4">
          <Cell
            no="Layer 1 · Science"
            title="Papers and preprints"
            body="Method, material, first result. Read by specialists, indexed nowhere a strategist looks."
          />
          <Cell
            no="Layer 2 · Patents"
            title="Filings and citations"
            body="Who is protecting what, and which filings the field itself keeps citing."
          />
          <Cell
            no="Layer 3 · Funding"
            title="Grants, rounds, programmes"
            body="Public money and venture money placed years before revenue."
          />
          <Cell
            no="Layer 4 · Market"
            title="Launches, contracts, plants"
            body="The layer the press reports — and the last one to move."
          />
        </div>
      </Slide>

      {/* 03 — Complication */}
      <Slide id={2} eyebrow="Complication">
        <Big>
          By the time it is a headline the lead is gone — and a good share of the
          headlines never hold.
        </Big>
        <div className="mt-10 grid grid-cols-1 gap-8 md:grid-cols-3">
          <div>
            <div className="font-display text-[2.4rem] text-accent">Volume</div>
            <p className="mt-2 font-sans text-[0.98rem] leading-relaxed text-text">
              Our sources alone produce roughly 2,500 new entries a day across eight
              industries. Nobody reads that. Everybody samples it.
            </p>
          </div>
          <div>
            <div className="font-display text-[2.4rem] text-accent">Promise vs. reality</div>
            <p className="mt-2 font-sans text-[0.98rem] leading-relaxed text-text">
              Announcements carry dates, capacities and prices that later slip, shrink or
              vanish. Read in isolation, a launch press release and a delivered plant look
              the same.
            </p>
          </div>
          <div>
            <div className="font-display text-[2.4rem] text-accent">No evidence trail</div>
            <p className="mt-2 font-sans text-[0.98rem] leading-relaxed text-text">
              Most foresight arrives as a deck with a view and no way to check it. When
              the view is wrong, nobody can say which number failed.
            </p>
          </div>
        </div>
        <p className="mt-10 max-w-3xl font-display text-[1.35rem] italic text-paper">
          The question is not “what is the next big thing?” — it is “which of the things
          already being announced will actually arrive, when, and what would prove it?”
        </p>
      </Slide>

      {/* 04 — Resolution */}
      <Slide id={3} eyebrow="Resolution">
        <Big>Catandary Foresight: corpus first, then measure, then write, then check.</Big>
        <div className="mt-10 grid grid-cols-1 gap-px bg-border md:grid-cols-2 lg:grid-cols-4">
          <Cell
            no="01 · Collect"
            title="One corpus, four layers"
            body={
              <>
                {fmt(st.sources)} curated primary sources (trade media, newsrooms,
                regulators, journals), {compact(st.researchWorks)} research works,{" "}
                {compact(st.patents)} patents with their citation graph, public and
                venture funding. Legal sources only, machine-checked for terms of use.
              </>
            }
          />
          <Cell
            no="02 · Measure"
            title="The innovation chain per field"
            body="For a technology field: where it sits on its patent-citation trajectory, how far research runs ahead of the market, which filings the field keeps citing. Relative development against 19 million patents — not a prediction."
          />
          <Cell
            no="03 · Write"
            title="A dated, cited dossier"
            body="A local model reads primary sources first, keeps a ledger of dated facts, and writes a decision document: what is moving, regulatory and IP status, what happens next, what the evidence does not support, options."
          />
          <Cell
            no="04 · Check"
            title="Deterministic, then human"
            body="Every figure is checked against the page it cites. What cannot be verified is deleted, not softened. Sources are ranked — register and regulator above company and journal above press. A person reads and signs off."
          />
        </div>
      </Slide>

      {/* 05 — Proof: how a dossier is checked */}
      <Slide id={4} eyebrow="How a dossier is checked">
        <Big>Nothing leaves the pipeline on trust.</Big>
        <div className="mt-10 grid grid-cols-1 gap-10 md:grid-cols-[1.1fr_1fr]">
          <ul className="space-y-4 font-sans text-[1rem] leading-relaxed text-text">
            {[
              ["Closed catalogue", "The model can only cite sources the run actually gathered and read. An invented reference cannot survive."],
              ["Figure check", "Each number, date and percentage is looked up on the cited page. Missing there → the sentence goes."],
              ["Source rank", "Core claims need a primary source — a register, a regulator, the company itself, a journal. Press-only claims are marked as such."],
              ["Structure", "Decision summary, actor table, dated calendar, options with trigger, horizon, effort and risk — or the gap is named in “Open questions”."],
              ["Fact density", "A dossier must carry at least two dated, primary-cited facts per hundred words. Prose does not count."],
              ["Human sign-off", "Every run lands in review. It becomes “done” only when a person has read it."],
            ].map(([t, b]) => (
              <li key={t} className="flex gap-4">
                <span className="mt-[0.55em] block h-[2px] w-5 shrink-0 bg-accent" />
                <span>
                  <span className="text-paper">{t}.</span> {b}
                </span>
              </li>
            ))}
          </ul>
          <div className="border border-border bg-card/40 p-5">
            <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
              Example · calendar block, LFP battery dossier (Sept 2026)
            </div>
            <table className="w-full font-sans text-[0.85rem] text-text">
              <thead className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
                <tr>
                  <th className="pb-2 text-left font-normal">Date</th>
                  <th className="pb-2 text-left font-normal">Event</th>
                  <th className="pb-2 text-left font-normal">Source</th>
                </tr>
              </thead>
              <tbody className="align-top">
                {[
                  ["Q2 2026", "Ultium Cells starts LFP storage-cell production, Spring Hill TN", "GM / LGES"],
                  ["End 2026", "Stellantis–CATL LFP plant, Zaragoza, begins production", "Stellantis / CATL"],
                  ["18 Aug 2027", "EU Battery Regulation due-diligence provisions apply", "EU regulation"],
                  ["2027–2031", "SK On delivers 9 GWh of LFP cells to NeoVolta", "SK On"],
                ].map(([d, e, s]) => (
                  <tr key={d + e} className="border-t border-border">
                    <td className="py-2 pr-3 font-mono text-[0.8rem] text-paper">{d}</td>
                    <td className="py-2 pr-3">{e}</td>
                    <td className="py-2 text-muted">{s}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
              Each row: a date and a citation, or it is not in the table.
            </p>
          </div>
        </div>
      </Slide>

      {/* 06 — Question */}
      <Slide id={5} eyebrow="Question">
        <Big>What is the technology question on your table?</Big>
        <Lede>
          The dossier answers one question at a time, with dates and sources. Three
          shapes we see most often:
        </Lede>
        <div className="mt-8 grid grid-cols-1 gap-px bg-border md:grid-cols-3">
          <Cell
            no="Timing"
            title="“When does this reach scale — here, not in China?”"
            body="Capacity announced vs. built, with the delays; regulatory dates; what the price curve did last year."
          />
          <Cell
            no="Skepticism"
            title="“Which of these announcements should we believe?”"
            body="Shipped product and published specs against claims; the record of corrections; who is funding whom."
          />
          <Cell
            no="Exposure"
            title="“Where does this touch our business?”"
            body="Suppliers, patents still in force, substitutes with a date — and what would have to be true for the threat to be real."
          />
        </div>
        <div className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="border border-border bg-card/40 p-6">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">Super Pro+</div>
            <h3 className="mt-2 font-display text-[1.25rem] text-paper">Ongoing intelligence partnership</h3>
            <p className="mt-2 font-sans text-[0.95rem] text-muted">
              Recurring dossiers on your watch list, a direct line to the person who built
              them, evidence attached to every claim.
            </p>
          </div>
          <div className="border border-border bg-card/40 p-6">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">Individual analysis</div>
            <h3 className="mt-2 font-display text-[1.25rem] text-paper">One question, fixed scope</h3>
            <p className="mt-2 font-sans text-[0.95rem] text-muted">
              A single technology, market or competitor move — delivered as a dated,
              sourced write-up with an agreed turnaround.
            </p>
          </div>
        </div>
      </Slide>

      {/* 07 — Limits & contact */}
      <Slide id={6} eyebrow="Limits & contact">
        <Big>What we do not claim.</Big>
        <ul className="mt-8 max-w-3xl space-y-3 font-sans text-[1rem] leading-relaxed text-text">
          <li>— We do not predict the future. We measure where a field stands relative to the patent record and report what is dated and sourced.</li>
          <li>— The dossiers are written by a language model running on our own hardware and checked automatically; a person reads every one before it is delivered, and the document says so.</li>
          <li>— The corpus is large, not complete. Every dossier lists the questions it could not answer and where it looked.</li>
        </ul>
        <div className="mt-12 flex flex-wrap items-center gap-4">
          <Link
            href="/enquiry"
            className="inline-flex items-center gap-2 bg-accent px-5 py-3 font-mono text-[10px] uppercase tracking-[0.18em] text-ink transition-colors hover:bg-accent-deep"
          >
            Request an analysis →
          </Link>
          <a
            href="https://www.linkedin.com/company/catandary"
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted underline decoration-accent/50 hover:text-text"
          >
            LinkedIn
          </a>
          <Link
            href="/trends/methodology"
            className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted underline decoration-accent/50 hover:text-text"
          >
            Methodology
          </Link>
        </div>
      </Slide>
    </div>
  );
}
