import Link from "next/link";
import { linkPrefetch } from "@/lib/renderMode";
import {
  parseMarkdown,
  parseInline,
  type MdHeadingLevel,
  type InlineNode,
} from "@/lib/markdown";
import { safeHref } from "@/lib/safeHref";

/** Typography matches the trend article body (`TrendArticle.tsx`) and the
 *  methodology page — same font-sans/leading/size for running text, so an
 *  analysis reads as the same publication as a trend article. */
const TEXT_CLASS = "text-text leading-[1.75] text-[15px] font-sans";

const HEADING_CLASS: Record<MdHeadingLevel, string> = {
  2: "font-display text-[26px] md:text-[28px] leading-[1.2] text-paper mt-10 mb-4",
  3: "font-display text-[20px] leading-[1.3] text-paper mt-8 mb-3",
  4: "font-display text-[17px] leading-[1.35] text-paper mt-6 mb-2",
  5: "font-mono text-[11px] uppercase tracking-[0.16em] text-muted mt-6 mb-2",
  6: "font-mono text-[10px] uppercase tracking-[0.16em] text-muted mt-6 mb-2",
};

function Inline({ nodes }: { nodes: InlineNode[] }) {
  return (
    <>
      {nodes.map((n, i) => {
        if (n.type === "bold") {
          return (
            <strong key={i} className="text-paper font-medium">
              {n.text}
            </strong>
          );
        }
        if (n.type === "link") {
          const href = safeHref(n.href);
          if (!href) return <span key={i}>{n.text}</span>; // F-3: unsafe scheme → text
          const isExternal = /^https?:\/\//i.test(href);
          return isExternal ? (
            <a
              key={i}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
            >
              {n.text}
            </a>
          ) : (
            <Link prefetch={linkPrefetch()} key={i} href={href} className="text-accent hover:underline">
              {n.text}
            </Link>
          );
        }
        return <span key={i}>{n.text}</span>;
      })}
    </>
  );
}

function Heading({ level, children }: { level: MdHeadingLevel; children: React.ReactNode }) {
  const className = HEADING_CLASS[level];
  switch (level) {
    case 2:
      return <h2 className={className}>{children}</h2>;
    case 3:
      return <h3 className={className}>{children}</h3>;
    case 4:
      return <h4 className={className}>{children}</h4>;
    case 5:
      return <h5 className={className}>{children}</h5>;
    case 6:
      return <h6 className={className}>{children}</h6>;
  }
}

/**
 * Renders an analysis body from the Markdown subset defined in
 * `lib/markdown.ts`. See that file's header comment for exactly what is (and
 * is not) supported — this component makes no attempt to handle anything
 * `parseMarkdown`/`parseInline` didn't already recognize.
 */
export default function MarkdownBody({ source }: { source: string }) {
  const blocks = parseMarkdown(source);

  return (
    <div className="max-w-none">
      {blocks.map((block, i) => {
        if (block.type === "heading") {
          return (
            <Heading key={i} level={block.level}>
              <Inline nodes={parseInline(block.text)} />
            </Heading>
          );
        }

        if (block.type === "list") {
          const items = block.items.map((item, j) => (
            <li key={j} className={TEXT_CLASS}>
              <Inline nodes={parseInline(item)} />
            </li>
          ));
          return block.ordered ? (
            <ol key={i} className="list-decimal pl-6 space-y-1.5 mb-6">
              {items}
            </ol>
          ) : (
            <ul key={i} className="list-disc pl-6 space-y-1.5 mb-6">
              {items}
            </ul>
          );
        }

        return (
          <p key={i} className={`${TEXT_CLASS} mb-5`}>
            <Inline nodes={parseInline(block.text)} />
          </p>
        );
      })}
    </div>
  );
}
