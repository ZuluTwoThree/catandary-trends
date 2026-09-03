/**
 * Imprint body + metadata, rendered by /imprint (workstation) and
 * /trends/imprint (static export) — see lib/sitePaths.ts.
 */
export const IMPRINT_METADATA = {
  title: "Imprint — Catandary Trends",
  description: "Legal notice (Impressum) for Catandary Trends.",
};

/**
 * Impressum (§ 5 DDG). Address block mirrors the operator block already
 * published on the static landing at catandary.de (transferred 2026-08-28,
 * closing the #64→#93 P0 item).
 */
const OPERATOR = {
  name: "Dirk Herrmann",
  address1: "Geiselharz 40/6",
  address2: "88279 Amtzell, Germany",
  email: "trends@catandary.de",
};

export default function ImprintContent() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-14">
      <span className="eyebrow">Legal notice</span>
      <h1 className="font-display text-[36px] leading-[1.1] text-paper mt-4 mb-8">
        Imprint
      </h1>

      <section className="mb-8">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent mb-3">
          Information according to § 5 DDG
        </h2>
        <p className="text-[15px] leading-[1.7]">
          {OPERATOR.name}
          <br />
          {OPERATOR.address1}
          <br />
          {OPERATOR.address2}
        </p>
      </section>

      <section className="mb-8">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent mb-3">
          Contact
        </h2>
        <p className="text-[15px] leading-[1.7]">
          Email:{" "}
          <a href={`mailto:${OPERATOR.email}`} className="text-accent hover:underline">
            {OPERATOR.email}
          </a>
        </p>
      </section>

      <section className="mb-8">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent mb-3">
          Responsible for content
        </h2>
        <p className="text-[15px] leading-[1.7]">
          {OPERATOR.name}, address as above.
        </p>
      </section>

      <section>
        <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent mb-3">
          Content and sources
        </h2>
        <p className="text-[15px] leading-[1.7] text-muted">
          Trend articles on this site are editorially generated summaries. Every
          article links to the primary source it was derived from; the linked
          publishers hold the rights to their original reporting.
        </p>
      </section>
    </div>
  );
}
