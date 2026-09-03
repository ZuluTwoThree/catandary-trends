import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { isStaticExport } from "@/lib/renderMode";

/**
 * /trends/tdm-policy — the human-readable side of the machine-readable
 * text-and-data-mining reservation (owner decision 2026-09-03). Referenced by
 * <meta name="tdm-policy">, /.well-known/tdmrep.json and the TDM-Reservation
 * header. Export-only like the other /trends/* legal addresses.
 */
export const metadata: Metadata = {
  title: "Text and data mining policy — Catandary Trends",
  description: "Catandary reserves text and data mining rights for catandary.de. Licensing on request.",
  alternates: { canonical: "/trends/tdm-policy" },
};

export default function TdmPolicyPage() {
  if (!isStaticExport()) notFound();
  return (
    <main className="mx-auto max-w-3xl px-6 py-16 font-serif leading-relaxed">
      <p className="font-mono text-xs uppercase tracking-widest text-neutral-500">Policy</p>
      <h1 className="mt-2 text-3xl">Text and data mining reservation</h1>
      <p className="mt-6">
        Catandary reserves the right to text and data mining for all content on
        catandary.de, including the trend feed, analyses and newsletter editions
        (§ 44b Abs. 3 UrhG; Art. 4(3) Directive (EU) 2019/790). The reservation
        is expressed in machine-readable form through the <code>TDM-Reservation</code>{" "}
        HTTP header, the <code>tdm-reservation</code> meta tag on every page and{" "}
        <code>/.well-known/tdmrep.json</code> (TDMRep, W3C Community Group).
      </p>
      <p className="mt-4">
        Automated collection of this site for training or evaluating machine
        learning models, for building text corpora or for any other form of
        text and data mining is not permitted without a licence. Known AI
        crawlers are additionally refused at the HTTP level.
      </p>
      <p className="mt-4">
        Search engine indexing, link previews, reading, quoting under the
        statutory quotation right and linking to any page remain welcome.
      </p>
      <p className="mt-4">
        Licensing requests and questions: <a className="underline" href="mailto:trends@catandary.de">trends@catandary.de</a>.
        Each article on this site names and links its primary source; removal
        requests from rights holders are handled within 72 hours.
      </p>
    </main>
  );
}
