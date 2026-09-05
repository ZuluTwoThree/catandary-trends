/**
 * Requeueing a failed generation (issue #71).
 *
 * A body that breaks off mid-sentence is a broken text, not a bad story, so the
 * reviewer can send the source back through the pipeline. Two properties matter
 * and are easy to get wrong: the loop guard, and the order of the two writes.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const q = vi.fn();
const q1 = vi.fn();
vi.mock("./pg", () => ({ q: (...a: unknown[]) => q(...a), q1: (...a: unknown[]) => q1(...a) }));

import { requeueForRegeneration, MAX_REGENERATION_ATTEMPTS } from "./review";

/** SQL of every q() call, whitespace-collapsed. */
const statements = () => q.mock.calls.map((c) => String(c[0]).replace(/\s+/g, " ").trim());

beforeEach(() => {
  q.mockReset();
  q1.mockReset();
});

describe("requeueForRegeneration", () => {
  it("retires the old article and reopens its source entry", async () => {
    q1.mockResolvedValue({ raw_entry_id: 55, attempts: 0 });
    q.mockResolvedValueOnce([{ id: 7 }]).mockResolvedValueOnce([]);

    expect(await requeueForRegeneration(7)).toEqual({ ok: true });

    const sql = statements();
    expect(sql[0]).toMatch(/UPDATE trends SET status = 'rejected'/);
    // Order is the safety property: if the second write fails, the article is
    // merely rejected. The reverse would leave an open entry beside a live
    // draft and produce two articles for one signal.
    expect(sql[1]).toMatch(/UPDATE raw_entries SET processed = FALSE/);
    expect(q.mock.calls[1][1]).toEqual([55]);
  });

  it("marks the retired row reviewed, so dedup stops blocking the retry", async () => {
    // Without reviewed_at the old embedding stays in the 30-day window and
    // kills the regenerated article as a duplicate of its own predecessor.
    q1.mockResolvedValue({ raw_entry_id: 55, attempts: 0 });
    q.mockResolvedValueOnce([{ id: 7 }]).mockResolvedValueOnce([]);
    await requeueForRegeneration(7);
    expect(statements()[0]).toMatch(/reviewed_at = NOW\(\)/);
  });

  it("stops after the attempt cap and leaves the source entry alone", async () => {
    q1.mockResolvedValue({ raw_entry_id: 55, attempts: MAX_REGENERATION_ATTEMPTS });

    expect(await requeueForRegeneration(7)).toEqual({
      ok: false,
      reason: "attempts_exhausted",
    });
    // Decisive: a source that truncates every time must not bounce through the
    // pipeline forever, so nothing may be written at all.
    expect(q).not.toHaveBeenCalled();
  });

  it("refuses anything that is not an open draft", async () => {
    q1.mockResolvedValue(null); // the guard's WHERE status = 'draft' found nothing
    expect(await requeueForRegeneration(7)).toEqual({ ok: false, reason: "not_draft" });
    expect(q).not.toHaveBeenCalled();
  });

  it("refuses when the trend has no source entry to reopen", async () => {
    q1.mockResolvedValue({ raw_entry_id: null, attempts: 0 });
    expect(await requeueForRegeneration(7)).toEqual({ ok: false, reason: "no_source" });
    expect(q).not.toHaveBeenCalled();
  });

  it("does not retire the row when a concurrent decision won the race", async () => {
    q1.mockResolvedValue({ raw_entry_id: 55, attempts: 0 });
    q.mockResolvedValueOnce([]); // guarded UPDATE matched nothing
    expect(await requeueForRegeneration(7)).toEqual({ ok: false, reason: "not_draft" });
    expect(statements()).toHaveLength(1); // source entry untouched
  });
});

// --- #11 (2026-09-05): person names, garbled bodies, the re-check queue ------
import { toItem, hasObjection, publishReviewed, rejectReviewed, getRecheckQueue } from "./review";

const PAD =
  " Analysts describe the change as gradual rather than abrupt, noting that " +
  "procurement teams, lenders and regulators are each adjusting their own " +
  "expectations at a different pace, so the overall picture remains mixed " +
  "and any conclusion about the wider market should be read with care, " +
  "since the underlying evidence is still being assembled and reviewed, " +
  "and several of the firms involved have declined to comment so far.";

const baseRow = {
  id: 1, slug: "s", title_en: "T", summary_en: null, primary_vertical: "BIZ",
  source_name: "Handelsblatt", source_url: "https://x", confidence: 0.9,
  created_at: "2026-09-05 12:00:00", status: "draft", review_reason: null,
  re_title: "Henkel-Chef Knobel: Margen verbessert", raw_content: null,
  excerpt: "Henkel-Chef Knobel sieht bessere Margen.", extraction_json: null,
};

describe("toItem — the two new objections (#11)", () => {
  it("flags an invented first name and highlights it", () => {
    const item = toItem({ ...baseRow, body_en: "Henkel CEO Markus Knobel said margins improved." + PAD });
    expect(item.names).toEqual(["Markus Knobel"]);
    expect(item.garbled).toEqual([]);
    expect(item.flagged).toEqual([]);
    expect(hasObjection(item)).toBe(true);
  });

  it("flags the 2026-09-05 token soup as garbled", () => {
    const item = toItem({ ...baseRow, body_en: ": writing writing市/address : writing M M M M M       仪器(" });
    expect(item.garbled.length).toBeGreaterThan(0);
    expect(hasObjection(item)).toBe(true);
  });

  it("raises no objection to a body that follows the source", () => {
    const item = toItem({ ...baseRow, body_en: "Henkel CEO Knobel sees better margins ahead." + PAD });
    expect(hasObjection(item)).toBe(false);
  });

  it("carries status and review_reason through", () => {
    const item = toItem({ ...baseRow, status: "review",
      review_reason: "recheck_2026-09-05:name:Markus Knobel", body_en: "x." + PAD });
    expect(item.status).toBe("review");
    expect(item.reviewReason).toBe("recheck_2026-09-05:name:Markus Knobel");
  });
});

describe("re-check queue actions accept status 'review'", () => {
  it("publish and reject are guarded on draft OR review", async () => {
    q.mockResolvedValue([{ id: 7 }]);
    await publishReviewed(7);
    await rejectReviewed(7);
    for (const sql of statements()) expect(sql).toMatch(/status IN \('draft', 'review'\)/);
    // publishing clears the parking reason — it is no longer in review
    expect(statements()[0]).toMatch(/review_reason = NULL/);
  });

  it("getRecheckQueue selects status 'review' and narrows on the reason prefix", async () => {
    q.mockResolvedValue([]);
    await getRecheckQueue({ reasonPrefix: "recheck_2026-09-05", limit: 50 });
    const sql = statements()[0];
    expect(sql).toMatch(/WHERE t.status = 'review'/);
    expect(sql).toMatch(/review_reason LIKE \$1/);
    expect(q.mock.calls[0][1]).toEqual(["recheck_2026-09-05%", 50]);
  });
});
