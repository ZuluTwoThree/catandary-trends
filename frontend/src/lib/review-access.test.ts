/**
 * Access guard for the review queue (issue #71, simplified by #93).
 *
 * Publishing/rejecting are writes to live content. The guard must be CLOSED
 * on anything public (PUBLIC_MODE preview, static export) and open on the
 * owner instance — there are no accounts any more, so no third state.
 */
import { describe, it, expect, afterEach } from "vitest";
import { canReview } from "@/lib/review-access";

afterEach(() => {
  delete process.env.PUBLIC_MODE;
  delete process.env.STATIC_EXPORT;
  delete process.env.NEXT_PUBLIC_STATIC_EXPORT;
});

describe("canReview", () => {
  it("is open on the owner instance (no PUBLIC_MODE, no export)", () => {
    expect(canReview()).toBe(true);
  });

  it("is closed under PUBLIC_MODE=1", () => {
    process.env.PUBLIC_MODE = "1";
    expect(canReview()).toBe(false);
  });

  it("is closed in the static export build (both env spellings)", () => {
    process.env.STATIC_EXPORT = "1";
    expect(canReview()).toBe(false);
    delete process.env.STATIC_EXPORT;
    process.env.NEXT_PUBLIC_STATIC_EXPORT = "1";
    expect(canReview()).toBe(false);
  });

  it("treats any PUBLIC_MODE value other than '1' as the owner instance", () => {
    for (const v of ["0", "true", "yes", ""]) {
      process.env.PUBLIC_MODE = v;
      expect(canReview()).toBe(true);
    }
  });
});
