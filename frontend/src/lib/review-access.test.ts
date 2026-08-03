/**
 * Access guard for the review queue (issue #71).
 *
 * Publishing/rejecting are writes to live content. The guard must default to
 * CLOSED: a deployment that knows nothing about REVIEW_ENABLED has to 404,
 * never expose the queue.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const holder: { session: unknown } = { session: null };

vi.mock("@/lib/auth", async () => {
  return {
    get AUTH_ENABLED() {
      return process.env.AUTH_ENABLED === "1";
    },
    getSession: vi.fn(async () => holder.session),
  };
});

async function load(review?: string, auth?: string) {
  vi.resetModules();
  if (review === undefined) delete process.env.REVIEW_ENABLED;
  else process.env.REVIEW_ENABLED = review;
  if (auth === undefined) delete process.env.AUTH_ENABLED;
  else process.env.AUTH_ENABLED = auth;
  return await import("@/lib/review-access");
}

beforeEach(() => {
  holder.session = null;
});
afterEach(() => {
  delete process.env.REVIEW_ENABLED;
  delete process.env.AUTH_ENABLED;
  vi.resetModules();
});

describe("canReview", () => {
  it("is closed when REVIEW_ENABLED is unset — the safe default", async () => {
    const m = await load(undefined, "0");
    expect(await m.canReview()).toBe(false);
  });

  it("is closed for any value other than '1'", async () => {
    for (const v of ["0", "true", "yes", ""]) {
      const m = await load(v, "0");
      expect(await m.canReview()).toBe(false);
    }
  });

  it("opens with the flag while auth is off (localhost operation today)", async () => {
    const m = await load("1", "0");
    expect(await m.canReview()).toBe(true);
  });

  it("additionally demands a session once auth is on", async () => {
    const m = await load("1", "1");
    expect(await m.canReview()).toBe(false); // anonymous
    holder.session = { email: "owner@example.com", tier: "free" };
    expect(await m.canReview()).toBe(true);
  });

  it("the flag alone never overrides a missing session when auth is on", async () => {
    holder.session = null;
    const m = await load("1", "1");
    expect(await m.canReview()).toBe(false);
  });
});
