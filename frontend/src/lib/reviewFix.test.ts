import { describe, expect, it } from "vitest";
import { dropSentencesWith, replaceName } from "./review";

const BODY =
  "UK Foreign Secretary David Lammy argues that climate loss dictates stability. " +
  "Clean energy investment reaches $2.2 trillion in 2026. That shift follows policy change.";

describe("dropSentencesWith", () => {
  it("removes every sentence carrying the unsupported token", () => {
    const out = dropSentencesWith(BODY, "David Lammy")!;
    expect(out).not.toContain("David Lammy");
    expect(out).toContain("Clean energy investment");
  });
  it("returns null when nothing matches or everything would go", () => {
    expect(dropSentencesWith(BODY, "Angela Merkel")).toBeNull();
    expect(dropSentencesWith("One sentence with X.", "X")).toBeNull();
  });
});

describe("replaceName", () => {
  it("uses the source form everywhere in the body", () => {
    expect(replaceName("Kemi Badenoch said. Kemi Badenoch left.", "Kemi Badenoch", "Badenoch"))
      .toBe("Badenoch said. Badenoch left.");
  });
  it("returns null when there is nothing to change", () => {
    expect(replaceName(BODY, "Kemi Badenoch", "Badenoch")).toBeNull();
    expect(replaceName(BODY, "David Lammy", "David Lammy")).toBeNull();
  });
});
