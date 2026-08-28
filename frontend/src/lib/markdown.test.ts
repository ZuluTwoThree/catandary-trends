import { describe, it, expect } from "vitest";
import { parseMarkdown, parseInline } from "@/lib/markdown";

describe("parseMarkdown — block structure", () => {
  it("returns an empty array for empty input", () => {
    expect(parseMarkdown("")).toEqual([]);
    expect(parseMarkdown("   \n\n  ")).toEqual([]);
  });

  it("shifts heading levels by one, capped at h6", () => {
    expect(parseMarkdown("# One")).toEqual([{ type: "heading", level: 2, text: "One" }]);
    expect(parseMarkdown("## Two")).toEqual([{ type: "heading", level: 3, text: "Two" }]);
    expect(parseMarkdown("##### Five")).toEqual([{ type: "heading", level: 6, text: "Five" }]);
    expect(parseMarkdown("###### Six")).toEqual([{ type: "heading", level: 6, text: "Six" }]);
  });

  it("does not treat more than 6 leading hashes as a heading (falls through as text)", () => {
    expect(parseMarkdown("####### Seven")).toEqual([
      { type: "paragraph", text: "####### Seven" },
    ]);
  });

  it("strips trailing closing hashes from ATX headings", () => {
    expect(parseMarkdown("## Title ##")).toEqual([{ type: "heading", level: 3, text: "Title" }]);
  });

  it("joins soft-wrapped lines within a paragraph with a single space", () => {
    expect(parseMarkdown("Line one\nLine two\nLine three")).toEqual([
      { type: "paragraph", text: "Line one Line two Line three" },
    ]);
  });

  it("splits paragraphs on blank lines", () => {
    expect(parseMarkdown("First para.\n\nSecond para.")).toEqual([
      { type: "paragraph", text: "First para." },
      { type: "paragraph", text: "Second para." },
    ]);
  });

  it("parses an unordered list with - or *", () => {
    expect(parseMarkdown("- one\n- two\n* three")).toEqual([
      { type: "list", ordered: false, items: ["one", "two", "three"] },
    ]);
  });

  it("parses an ordered list", () => {
    expect(parseMarkdown("1. first\n2. second\n10. tenth")).toEqual([
      { type: "list", ordered: true, items: ["first", "second", "tenth"] },
    ]);
  });

  it("ends a list at the first non-list line and starts a new paragraph", () => {
    expect(parseMarkdown("- a\n- b\nnot a list item")).toEqual([
      { type: "list", ordered: false, items: ["a", "b"] },
      { type: "paragraph", text: "not a list item" },
    ]);
  });

  it("handles a heading, paragraph and list in sequence (the template's shape)", () => {
    const blocks = parseMarkdown(
      "## The question\n\nSome context.\n\n- point one\n- point two\n\n## What we found\n\nMore text."
    );
    expect(blocks).toEqual([
      { type: "heading", level: 3, text: "The question" },
      { type: "paragraph", text: "Some context." },
      { type: "list", ordered: false, items: ["point one", "point two"] },
      { type: "heading", level: 3, text: "What we found" },
      { type: "paragraph", text: "More text." },
    ]);
  });
});

describe("parseInline — bold and links", () => {
  it("returns plain text as a single text node", () => {
    expect(parseInline("plain text")).toEqual([{ type: "text", text: "plain text" }]);
  });

  it("parses bold spans", () => {
    expect(parseInline("a **bold** word")).toEqual([
      { type: "text", text: "a " },
      { type: "bold", text: "bold" },
      { type: "text", text: " word" },
    ]);
  });

  it("parses markdown links", () => {
    expect(parseInline("see [the source](https://example.com/x)")).toEqual([
      { type: "text", text: "see " },
      { type: "link", text: "the source", href: "https://example.com/x" },
    ]);
  });

  it("parses a link to an internal path", () => {
    expect(parseInline("[Ask us](/enquiry)")).toEqual([
      { type: "link", text: "Ask us", href: "/enquiry" },
    ]);
  });

  it("handles bold and a link together", () => {
    expect(parseInline("**Important:** see [this](/x) for detail.")).toEqual([
      { type: "bold", text: "Important:" },
      { type: "text", text: " see " },
      { type: "link", text: "this", href: "/x" },
      { type: "text", text: " for detail." },
    ]);
  });

  it("returns an empty array for an empty string", () => {
    expect(parseInline("")).toEqual([]);
  });
});
