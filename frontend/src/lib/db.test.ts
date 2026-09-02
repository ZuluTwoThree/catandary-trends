/**
 * Public read layer — the article-by-slug lookup must not leak unpublished
 * rows (security review 2026-09-02, E-6). The pg layer is mocked; what is
 * asserted is the SQL the function sends, not a database.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const q = vi.fn();
const q1 = vi.fn();
vi.mock("./pg", () => ({ q: (...a: unknown[]) => q(...a), q1: (...a: unknown[]) => q1(...a) }));

import { getTrendBySlug } from "./db";

const sqlOf = (call: unknown[]) => String(call[0]).replace(/\s+/g, " ").trim();

beforeEach(() => {
  q.mockReset();
  q1.mockReset();
});

describe("getTrendBySlug", () => {
  it("filters to published rows by default", async () => {
    q1.mockResolvedValue(null);
    await getTrendBySlug("some-slug");
    expect(q1).toHaveBeenCalledTimes(1);
    const sql = sqlOf(q1.mock.calls[0]);
    expect(sql).toMatch(/WHERE t\.slug = \$1 AND t\.status = 'published'/);
    expect(q1.mock.calls[0][1]).toEqual(["some-slug"]);
  });

  it("returns null for a slug that exists only as draft/rejected/signal", async () => {
    // The status filter is in the SQL, so the mock (standing in for pg)
    // finds nothing — the page then 404s instead of rendering the draft.
    q1.mockResolvedValue(null);
    expect(await getTrendBySlug("held-draft")).toBeNull();
  });

  it("drops the status filter only when explicitly asked", async () => {
    q1.mockResolvedValue(null);
    await getTrendBySlug("some-slug", { includeUnpublished: true });
    const sql = sqlOf(q1.mock.calls[0]);
    expect(sql).toMatch(/WHERE t\.slug = \$1$/);
    expect(sql).not.toMatch(/status = 'published'/);
  });

  it("parses a published row into a Trend", async () => {
    q1.mockResolvedValue({
      id: 1,
      slug: "s",
      title_en: "T",
      status: "published",
      verticals: '["FOOD"]',
      pestel: ["T"],
      tags: null,
      brands: [],
      companies: [],
      regions: [],
      auto_published: 1,
    });
    const t = await getTrendBySlug("s");
    expect(t?.verticals).toEqual(["FOOD"]);
    expect(t?.tags).toEqual([]);
    expect(t?.auto_published).toBe(true);
  });
});
