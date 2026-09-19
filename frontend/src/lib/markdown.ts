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
 *  - Pipe tables (GFM shape: a header row, a `---` separator row, body rows;
 *    added 2026-09 for report-style analyses with comparison tables).
 *    Cells carry inline markup; alignment colons are ignored.
 *
 * Deliberately NOT supported (renders as literal characters, not an error):
 * italics, inline code / fenced code blocks, blockquotes, images,
 * nested or mixed lists, raw HTML. Keep analysis content to this subset.
 */

export type MdHeadingLevel = 2 | 3 | 4 | 5 | 6;

export type MdBlock =
  | { type: "heading"; level: MdHeadingLevel; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "table"; header: string[]; rows: string[][] };

export type InlineNode =
  | { type: "text"; text: string }
  | { type: "bold"; text: string }
  | { type: "link"; text: string; href: string };

const HEADING_RE = /^(#{1,6})\s+(.+?)\s*#*\s*$/;
const UL_ITEM_RE = /^[-*]\s+(.+)$/;
const OL_ITEM_RE = /^\d+\.\s+(.+)$/;
const TABLE_ROW_RE = /^\|.*\|\s*$/;
const TABLE_SEP_RE = /^\|(\s*:?-{3,}:?\s*\|)+\s*$/;

/** Split one `| a | b |` row into trimmed cells (outer pipes dropped). */
function tableCells(line: string): string[] {
  const inner = line.trim().replace(/^\|/, "").replace(/\|\s*$/, "");
  return inner.split("|").map((c) => c.trim());
}

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

    if (
      TABLE_ROW_RE.test(line) &&
      i + 1 < lines.length &&
      TABLE_SEP_RE.test(lines[i + 1].trim())
    ) {
      flushParagraph();
      const header = tableCells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && TABLE_ROW_RE.test(lines[i])) {
        const cells = tableCells(lines[i]);
        // Ragged rows are padded/truncated to the header width so the
        // rendered grid never shifts columns.
        rows.push(
          Array.from({ length: header.length }, (_, k) => cells[k] ?? "")
        );
        i++;
      }
      blocks.push({ type: "table", header, rows });
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
