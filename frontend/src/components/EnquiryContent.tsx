const CONTACT_EMAIL = process.env.CONTACT_EMAIL || "trends@catandary.de";

export const ENQUIRY_METADATA = {
  title: "Request an Analysis — Catandary Trends",
  description:
    "Two ways to work with Catandary: an ongoing Super Pro+ intelligence partnership, or a fixed-scope individual analysis on one question.",
};

const OFFERS = [
  {
    key: "superpro",
    label: "Super Pro+",
    tagline: "Ongoing intelligence partnership",
    desc: "Standing access to the corpus and our read on it — recurring analyses on the technologies and markets you track, evidence attached, on a cadence that fits your planning cycle.",
    points: [
      "Recurring analyses on your watch list",
      "Direct line to the person who built them",
      "Evidence and primary sources for every claim",
    ],
  },
  {
    key: "individual",
    label: "Individual analysis",
    tagline: "One question, evidenced answer, fixed scope",
    desc: "Bring a single question — a technology, a market, a competitor move. We read the corpus, check it against primary sources, and hand back a dated, sourced analysis with a fixed scope and turnaround.",
    points: [
      "One clearly scoped question",
      "Fixed turnaround, agreed up front",
      "Delivered as a dated, sourced write-up",
    ],
  },
] as const;

/**
 * `/enquiry` — the offer + enquiry path (#93 Etappe 2), replacing the old
 * `/trends/pricing` tier ladder for the public site. No tier comparison, no
 * checkout, no prices (owner instruction: sales-led, quoted per engagement).
 *
 * v1 contact mechanism is a `mailto:` link (no form backend yet). Deliberately
 * isolated in its own section below the offer copy so a real form can later
 * replace just that block without touching the two offer cards.
 *
 * Rendered by /enquiry (workstation) and /trends/enquiry (static export —
 * lib/sitePaths.ts). No fetch, no API route: the export ships it as is. A
 * future form backend must stay behind `isStaticExport()` or become a PHP
 * endpoint on the webspace (design 4.4).
 */
export default function EnquiryContent() {
  const subject = encodeURIComponent("Catandary — enquiry");
  const mailto = `mailto:${CONTACT_EMAIL}?subject=${subject}`;

  return (
    <div className="mx-auto max-w-3xl px-6 py-14">
      <div className="mb-12">
        <span className="eyebrow">Work with us</span>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mt-4 mb-5">
          Two ways to get <span className="italic text-accent">an answer</span>.
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          No self-serve checkout, no tier ladder — this is sales-led. Tell us
          what you need and we&apos;ll scope it together.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-12">
        {OFFERS.map((o) => (
          <div key={o.key} className="border border-border bg-card/40 p-6 flex flex-col">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-2">
              {o.label}
            </div>
            <h2 className="font-display text-[20px] text-paper mb-3">{o.tagline}</h2>
            <p className="font-sans text-sm text-text leading-relaxed mb-4">{o.desc}</p>
            <ul className="mt-auto space-y-1.5">
              {o.points.map((p) => (
                <li key={p} className="relative pl-4 text-[13px] leading-[1.5] text-muted">
                  <span className="absolute left-0 text-accent-deep" aria-hidden="true">
                    +
                  </span>
                  {p}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="border border-accent/30 bg-accent/5 p-8">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-3">
          —— Get in touch
        </div>
        <p className="font-sans text-text text-base leading-relaxed mb-6 max-w-xl">
          Send us your question, or the kind of partnership you have in mind
          — we&apos;ll reply and scope it from there. You can also find us on
          LinkedIn.
        </p>
        <a
          href={mailto}
          className="inline-flex items-center gap-2 bg-accent text-ink px-5 py-3 font-mono text-[10px] uppercase tracking-[0.18em] hover:bg-accent-deep transition-colors"
        >
          Email {CONTACT_EMAIL} →
        </a>
      </div>
    </div>
  );
}
