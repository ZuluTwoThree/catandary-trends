/**
 * The AI disclosure and the release desk's state rule (owner mandate
 * 2026-09-06).
 *
 * The disclosure sentence exists twice — here for the website and the release
 * view, in pipeline/newsletter_generator.py for the mail. This file pins what
 * the sentence must say; tests/test_newsletter_ai_disclosure.py pins that both
 * copies are byte-identical.
 */
import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  AI_DISCLOSURE_EN,
  ARTICLE_DISCLOSURE_ARIA,
  ARTICLE_DISCLOSURE_EN,
  ARTICLE_DISCLOSURE_LABEL,
  ARTICLE_DISCLOSURE_QUALIFIER,
  ARTICLE_GENERATOR_META,
  EDITION_BLOCKS,
  PROVENANCE_BADGE,
  editionBlock,
} from "@/lib/aiDisclosure";
import AiArticleDisclosure from "@/components/AiArticleDisclosure";
import { editionState } from "@/lib/newsletterReview";

describe("AI_DISCLOSURE_EN", () => {
  it("names the machine part, the automatic check and the human release", () => {
    expect(AI_DISCLOSURE_EN).toMatch(/generated/);
    expect(AI_DISCLOSURE_EN).toMatch(/language model/);
    expect(AI_DISCLOSURE_EN).toMatch(/checked automatically/);
    expect(AI_DISCLOSURE_EN).toMatch(/released by a person/);
  });

  it("stays one sober sentence — no marketing, no method claim", () => {
    expect(AI_DISCLOSURE_EN.length).toBeLessThan(260);
    expect(AI_DISCLOSURE_EN).not.toMatch(/best|unique|leading|proprietary|world/i);
  });

  it("is what the website edition renders", () => {
    const src = fs.readFileSync(
      path.resolve(__dirname, "..", "components", "newsletter", "EditionBody.tsx"),
      "utf-8"
    );
    expect(src).toMatch(/\{AI_DISCLOSURE_EN\}/);
  });
});

describe("EDITION_BLOCKS", () => {
  it("labels every section of an edition", () => {
    expect(EDITION_BLOCKS.map((b) => b.key)).toEqual([
      "editorial",
      "deep_dive",
      "vertical_summaries",
      "trend_refs",
      "mega_trend_radar",
    ]);
  });

  it("does not call the radar AI-written — it is arithmetic", () => {
    expect(editionBlock("mega_trend_radar")?.provenance).toBe("computed");
    expect(editionBlock("mega_trend_radar")?.detail).toMatch(/No language model/);
  });

  it("says that the curated links point at model-written articles", () => {
    const refs = editionBlock("trend_refs");
    expect(refs?.provenance).toBe("curated");
    expect(refs?.detail).toMatch(/model-written/);
  });

  it("has a badge for every provenance kind", () => {
    for (const b of EDITION_BLOCKS) expect(PROVENANCE_BADGE[b.provenance]).toBeTruthy();
  });
});

describe("editionState", () => {
  it("draft without approved_at", () => {
    expect(editionState({ approved_at: null, sent_at: null })).toBe("draft");
  });

  it("released once a person approved it", () => {
    expect(editionState({ approved_at: "2026-09-06 08:00:00", sent_at: null })).toBe("released");
  });

  it("sent beats released", () => {
    expect(
      editionState({ approved_at: "2026-09-06 08:00:00", sent_at: "2026-09-06 09:00:00" })
    ).toBe("sent");
  });
});

/**
 * The feed article's label (#99). The briefing may say a person released it;
 * the article may not — these tests pin that difference, and that the label is
 * actually on the page rather than only in a constant file.
 */
describe("ARTICLE_DISCLOSURE_EN", () => {
  it("names the machine, the single source, the automatic check and the missing human read", () => {
    expect(ARTICLE_DISCLOSURE_EN).toMatch(/generated/);
    expect(ARTICLE_DISCLOSURE_EN).toMatch(/local language model/);
    expect(ARTICLE_DISCLOSURE_EN).toMatch(/single source/);
    expect(ARTICLE_DISCLOSURE_EN).toMatch(/checked automatically/);
    expect(ARTICLE_DISCLOSURE_EN).toMatch(/without a person reading it/);
  });

  it("says the opposite of the briefing about human review", () => {
    // The briefing has a release desk since 2026-09-06, the feed has not.
    expect(AI_DISCLOSURE_EN).toMatch(/released by a person/);
    expect(ARTICLE_DISCLOSURE_EN).not.toMatch(/released by a person/);
    expect(ARTICLE_DISCLOSURE_EN).not.toBe(AI_DISCLOSURE_EN);
  });

  it("stays one sober sentence — no marketing, no method claim", () => {
    expect(ARTICLE_DISCLOSURE_EN.length).toBeLessThan(260);
    expect(ARTICLE_DISCLOSURE_EN.split(". ").length).toBe(1);
    expect(ARTICLE_DISCLOSURE_EN).not.toMatch(/best|unique|leading|proprietary|world|accurate/i);
  });
});

describe("AiArticleDisclosure", () => {
  const html = renderToStaticMarkup(createElement(AiArticleDisclosure));

  it("renders the full sentence verbatim — no paraphrase of the constant", () => {
    expect(html).toContain(ARTICLE_DISCLOSURE_EN);
  });

  it("shows the short label without expanding anything", () => {
    // Everything before </summary> is what a reader sees while collapsed.
    const visible = html.slice(0, html.indexOf("</summary>"));
    expect(visible).toContain(ARTICLE_DISCLOSURE_LABEL);
    expect(visible).toContain(ARTICLE_DISCLOSURE_QUALIFIER);
  });

  it("works without JavaScript and has an accessible name", () => {
    expect(html).toMatch(/<details/);
    expect(html).toMatch(/<summary/);
    expect(html).toContain(`aria-label="${ARTICLE_DISCLOSURE_ARIA}"`);
    expect(html).toMatch(/role="note"/);
  });

  it("is text, not a bare icon", () => {
    expect(html).not.toMatch(/<(img|svg)\b/);
  });
});

describe("the article page carries the label", () => {
  const read = (...parts: string[]) =>
    fs.readFileSync(path.resolve(__dirname, "..", ...parts), "utf-8");

  it("TrendArticle renders it above the body", () => {
    const src = read("components", "TrendArticle.tsx");
    expect(src).toMatch(/<AiArticleDisclosure \/>/);
    // Before the summary/body, i.e. in the first screenful — not a footer note.
    expect(src.indexOf("<AiArticleDisclosure />")).toBeLessThan(src.indexOf("{/* Summary */}"));
  });

  it("the JSON-LD names the software creator with the same sentence", () => {
    const src = read("components", "JsonLd.tsx");
    expect(src).toMatch(/"@type": "SoftwareApplication"/);
    expect(src).toMatch(/description: ARTICLE_DISCLOSURE_EN/);
    // The responsible author stays the organisation.
    expect(src).toMatch(/author: \{\s*"@type": "Organization"/);
  });

  it("the page metadata emits the generator hint", () => {
    const src = read("app", "trends", "[slug]", "page.tsx");
    expect(src).toMatch(/other: \{ generator: ARTICLE_GENERATOR_META \}/);
    expect(ARTICLE_GENERATOR_META).toMatch(/AI-generated/);
  });
});
