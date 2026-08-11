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
