import { notFound } from "next/navigation";
import type { Metadata } from "next";
import {
  getAllAnalyses,
  getAnalysisBySlug,
  formatAnalysisDate,
  analysisImageExists,
  analysisImagePath,
} from "@/lib/analyses";
import MarkdownBody from "@/components/MarkdownBody";
import AnalysisCta from "@/components/AnalysisCta";

// Static generation over the published (non-draft) set — a draft (like
// content/analyses/_template.md) is deliberately absent here, so it falls
// through to the dynamic render below, which 404s it the same way as an
// unknown slug (#93: "draft: true wird nirgends gelistet/gerendert").
export function generateStaticParams() {
  return getAllAnalyses().map((a) => ({ slug: a.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const analysis = getAnalysisBySlug(slug);
  if (!analysis) return { title: "Analysis not found" };

  const hasImage = analysisImageExists(analysis.image);

  return {
    title: `${analysis.title} — Catandary Trends`,
    description: analysis.teaser,
    openGraph: {
      title: analysis.title,
      description: analysis.teaser,
      type: "article",
      // Omitted (not an empty array) when the frontmatter's image file is
      // missing — the root `opengraph-image.tsx` then supplies the
      // site-default OG image instead of a broken link. No crash either way.
      ...(hasImage ? { images: [{ url: analysisImagePath(analysis.image) }] } : {}),
    },
  };
}

export default async function AnalysisPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const analysis = getAnalysisBySlug(slug);
  if (!analysis) notFound();

  return (
    <div className="mx-auto max-w-3xl px-6 py-14">
      <article>
        <header className="mb-10 border-b border-border pb-8">
          <span className="eyebrow">Analysis</span>
          <h1 className="font-display text-4xl md:text-[44px] leading-[1.1] tracking-tight text-paper mt-4 mb-6">
            {analysis.title}
          </h1>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            <time dateTime={analysis.date}>{formatAnalysisDate(analysis.date)}</time>
            <span className="text-border">——</span>
            <span>
              <span className="text-muted/70">By /</span>{" "}
              <span className="text-paper">{analysis.author}</span>
            </span>
            <span className="text-border">——</span>
            {/* The provenance header is itself part of the pitch (#93: "Eine
                Analyse mit Namen und Stand ist genau das, was das automatische
                Radar nicht liefern konnte") — the corpus snapshot date, not
                the publish date, is what makes a claim checkable. */}
            <span title="The corpus snapshot this analysis was built from, not the publish date">
              <span className="text-muted/70">Corpus as of /</span>{" "}
              <span className="text-paper">{formatAnalysisDate(analysis.corpus_asof)}</span>
            </span>
          </div>
        </header>

        <MarkdownBody source={analysis.body} />

        <AnalysisCta />
      </article>
    </div>
  );
}
