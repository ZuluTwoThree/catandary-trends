import {
  ARTICLE_DISCLOSURE_ARIA,
  ARTICLE_DISCLOSURE_EN,
  ARTICLE_DISCLOSURE_LABEL,
  ARTICLE_DISCLOSURE_QUALIFIER,
} from "@/lib/aiDisclosure";

/**
 * The AI label on a feed article (issue #99, owner mandate 2026-09-06).
 *
 * EU AI Act Art. 50 (4) wants the disclosure where the reader meets the text,
 * not in a colophon — so this sits directly under the title/meta block, above
 * the summary, and is the first thing after the headline that is not a badge.
 *
 * Shape: a native `<details>`. The short label is always visible; the full
 * sentence is one click away and, crucially, works with JavaScript disabled —
 * which the static export on the shared hosting has to assume. A `title=`
 * tooltip would not do: it is invisible to touch and to most screen readers.
 * The wrapper is `role="note"` with an accessible name rather than an
 * `aria-label` on the summary, which would have replaced the visible words
 * "AI-generated" in the accessibility tree with a paraphrase.
 *
 * Deliberately text-only. The Commission's EU icons for this label are
 * optional; a raster/SVG icon would be one more asset on a static host and
 * would say less than the two words do. Retro-fitting one is a drop-in here.
 *
 * Pure and prop-free on purpose: every published article is produced the same
 * way, so there is nothing to parameterise, and the unit test can render it.
 */
export default function AiArticleDisclosure() {
  return (
    <div role="note" aria-label={ARTICLE_DISCLOSURE_ARIA} className="mb-8">
      <details className="border border-border bg-card/40" data-testid="ai-disclosure">
        <summary className="cursor-pointer px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          <span className="text-paper">{ARTICLE_DISCLOSURE_LABEL}</span>
          <span className="text-border"> / </span>
          <span>{ARTICLE_DISCLOSURE_QUALIFIER}</span>
        </summary>
        <p className="border-t border-border px-3 py-3 font-sans text-[12px] normal-case leading-[1.6] tracking-normal text-muted">
          {ARTICLE_DISCLOSURE_EN}
        </p>
      </details>
    </div>
  );
}
