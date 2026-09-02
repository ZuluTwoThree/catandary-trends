/**
 * /api/track hardening (security review 2026-09-02, E-5): same-origin,
 * rate limit, bounded body, typed id, published-only target.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const q = vi.fn();
const q1 = vi.fn();
vi.mock("@/lib/pg", () => ({ q: (...a: unknown[]) => q(...a), q1: (...a: unknown[]) => q1(...a) }));

import { NextRequest } from "next/server";
import { POST } from "./route";
import { _resetRateLimit } from "@/lib/rateLimit";

const HOST = "localhost:3001";

function post(body: unknown, headers: Record<string, string> = {}): NextRequest {
  return new NextRequest(`http://${HOST}/api/track`, {
    method: "POST",
    headers: {
      host: HOST,
      origin: `http://${HOST}`,
      "content-type": "application/json",
      ...headers,
    },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

beforeEach(() => {
  q.mockReset();
  q1.mockReset();
  _resetRateLimit();
});

describe("POST /api/track", () => {
  it("rejects a cross-site origin before touching the database", async () => {
    const res = await POST(post({ trend_id: 1, event: "page_view" }, { origin: "https://evil.example" }));
    expect(res.status).toBe(403);
    expect(q1).not.toHaveBeenCalled();
  });

  it("rejects a non-integer trend_id with 400 instead of a pg-driven 500", async () => {
    for (const bad of ["12", 1.5, -3, 0, 2 ** 31, null]) {
      const res = await POST(post({ trend_id: bad, event: "page_view" }));
      expect(res.status, `trend_id=${String(bad)}`).toBe(400);
    }
    expect(q1).not.toHaveBeenCalled();
  });

  it("rejects an unknown event", async () => {
    const res = await POST(post({ trend_id: 1, event: "purchase" }));
    expect(res.status).toBe(400);
  });

  it("rejects an oversize body with 413", async () => {
    const res = await POST(post({ trend_id: 1, event: "page_view", pad: "x".repeat(600) }));
    expect(res.status).toBe(413);
  });

  it("discards ids that are not a published trend (404, no write)", async () => {
    q1.mockResolvedValueOnce(null); // published check
    const res = await POST(post({ trend_id: 42, event: "page_view" }));
    expect(res.status).toBe(404);
    expect(q).not.toHaveBeenCalled();
    expect(String(q1.mock.calls[0][0])).toMatch(/status = 'published'/);
  });

  it("increments an existing metrics row for a published trend", async () => {
    q1.mockResolvedValueOnce({ ok: 1 }).mockResolvedValueOnce({ id: 9 });
    q.mockResolvedValue([]);
    const res = await POST(post({ trend_id: 42, event: "share" }));
    expect(res.status).toBe(200);
    expect(String(q.mock.calls[0][0])).toMatch(/SET shares = COALESCE\(shares, 0\) \+ 1/);
    expect(q.mock.calls[0][1]).toEqual([42]);
  });

  it("rate-limits after the per-client budget", async () => {
    q1.mockResolvedValue({ ok: 1, id: 1 });
    q.mockResolvedValue([]);
    let last = 0;
    for (let i = 0; i < 61; i++) {
      last = (await POST(post({ trend_id: 1, event: "page_view" }))).status;
    }
    expect(last).toBe(429);
  });
});
