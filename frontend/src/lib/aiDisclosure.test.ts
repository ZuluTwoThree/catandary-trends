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
import {
  AI_DISCLOSURE_EN,
  EDITION_BLOCKS,
  PROVENANCE_BADGE,
  editionBlock,
} from "@/lib/aiDisclosure";
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
