/**
 * Minimal Markdown subset for analysis bodies (issue #93, Etappe 2).
 *
 * The repo has no Markdown library (checked before adding this — no remark/
 * marked/mdx anywhere in frontend/package.json, and the one other place that
 * renders Markdown-ish text, `trends/newsletter/page.tsx`'s `RichText`,
 * hand-rolls its own `[text](url)` regex rather than pulling one in). Analysis
 * bodies only need headings/paragraphs/lists/links/bold, so a hand-rolled
 * parser stays small and dependency-free instead of pulling in a general
 * CommonMark engine for a feature this narrow.
 *
 * Supported, deliberately:
 *  - ATX headings `#`..`######`, SHIFTED by one level: a source `#`/`##`
 *    becomes `<h2>`/`<h3>` (capped at h6). The page itself renders the
 *    analysis title as `<h1>`, so body headings must not compete for it.
 *  - Paragraphs: blank-line-separated blocks; soft-wrapped lines inside a
 *    paragraph are joined with a single space (no hard line breaks).
 *  - Unordered lists (`-` or `*`) and ordered lists (`1.`, `2.`, ...) — flat
 *    only, no nesting.
 *  - Inline `**bold**` and inline `[text](url)` links.
 *
 * Deliberately NOT supported (renders as literal characters, not an error):
 * italics, inline code / fenced code blocks, blockquotes, images, tables,
 * nested or mixed lists, raw HTML. Keep analysis content to this subset.
 */

export type MdHeadingLevel = 2 | 3 | 4 | 5 | 6;

export type MdBlock =
  | { type: "heading"; level: MdHeadingLevel; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; ordered: boolean; items: string[] };

export type InlineNode =
  | { type: "text"; text: string }
  | { type: "bold"; text: string }
  | { type: "link"; text: string; href: string };

const HEADING_RE = /^(#{1,6})\s+(.+?)\s*#*\s*$/;
const UL_ITEM_RE = /^[-*]\s+(.+)$/;
const OL_ITEM_RE = /^\d+\.\s+(.+)$/;

export function parseMarkdown(source: string): MdBlock[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: MdBlock[] = [];
  const paragraphBuf: string[] = [];

  const flushParagraph = () => {
    if (paragraphBuf.length > 0) {
      blocks.push({ type: "paragraph", text: paragraphBuf.join(" ").trim() });
      paragraphBuf.length = 0;
    }
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      flushParagraph();
      i++;
      continue;
    }

    const heading = HEADING_RE.exec(line);
    if (heading) {
      flushParagraph();
      const level = Math.min(heading[1].length + 1, 6) as MdHeadingLevel;
      blocks.push({ type: "heading", level, text: heading[2].trim() });
      i++;
      continue;
    }

    const isOrdered = OL_ITEM_RE.test(line);
    const isUnordered = UL_ITEM_RE.test(line);
    if (isOrdered || isUnordered) {
      flushParagraph();
      const itemRe = isOrdered ? OL_ITEM_RE : UL_ITEM_RE;
      const items: string[] = [];
      while (i < lines.length) {
        const m = itemRe.exec(lines[i]);
        if (!m) break;
        items.push(m[1].trim());
        i++;
      }
      blocks.push({ type: "list", ordered: isOrdered, items });
      continue;
    }

    paragraphBuf.push(line.trim());
    i++;
  }
  flushParagraph();

  return blocks;
}

const INLINE_RE = /(\*\*[^*]+\*\*|\[[^\]]+\]\([^)\s]+\))/g;
const BOLD_RE = /^\*\*([^*]+)\*\*$/;
const LINK_RE = /^\[([^\]]+)\]\(([^)\s]+)\)$/;

export function parseInline(text: string): InlineNode[] {
  return text
    .split(INLINE_RE)
    .filter((part) => part !== "")
    .map((part): InlineNode => {
      const bold = BOLD_RE.exec(part);
      if (bold) return { type: "bold", text: bold[1] };
      const link = LINK_RE.exec(part);
      if (link) return { type: "link", text: link[1], href: link[2] };
      return { type: "text", text: part };
    });
}
