/**
 * /api/newsletter signup hardening (security review 2026-09-02, E-5).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const q = vi.fn();
const q1 = vi.fn();
vi.mock("@/lib/pg", () => ({ q: (...a: unknown[]) => q(...a), q1: (...a: unknown[]) => q1(...a) }));

import { NextRequest } from "next/server";
import { GET, POST } from "./route";
import { _resetRateLimit } from "@/lib/rateLimit";

const HOST = "localhost:3001";

function post(body: unknown, headers: Record<string, string> = {}): NextRequest {
  return new NextRequest(`http://${HOST}/api/newsletter`, {
    method: "POST",
    headers: { host: HOST, origin: `http://${HOST}`, "content-type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

beforeEach(() => {
  q.mockReset();
  q1.mockReset();
  _resetRateLimit();
});

describe("POST /api/newsletter", () => {
  it("rejects cross-site and header-less callers with 403", async () => {
    expect((await POST(post({ email: "a@b.co" }, { origin: "https://evil.example" }))).status).toBe(403);
    const bare = new NextRequest(`http://${HOST}/api/newsletter`, {
      method: "POST",
      headers: { host: HOST },
      body: JSON.stringify({ email: "a@b.co" }),
    });
    expect((await POST(bare)).status).toBe(403);
    expect(q1).not.toHaveBeenCalled();
  });

  it("rejects an oversize body with 413 and malformed JSON with 400", async () => {
    expect((await POST(post({ email: "a@b.co", pad: "x".repeat(2000) }))).status).toBe(413);
    expect((await POST(post("{nope"))).status).toBe(400);
    expect((await POST(post({ email: 42 }))).status).toBe(400);
    expect((await POST(post({ email: "not-an-email" }))).status).toBe(400);
    expect(q1).not.toHaveBeenCalled();
  });

  it("normalises the address and inserts a new subscriber", async () => {
    q1.mockResolvedValueOnce(null);
    q.mockResolvedValue([]);
    const res = await POST(post({ email: "  New.Person@Example.COM " }));
    expect(res.status).toBe(200);
    expect(q1.mock.calls[0][1]).toEqual(["new.person@example.com"]);
    expect(String(q1.mock.calls[0][0])).toMatch(/LOWER\(email\) = \$1/);
    expect(String(q.mock.calls[0][0])).toMatch(/INSERT INTO newsletter_subscribers/);
    expect(q.mock.calls[0][1]).toEqual(["new.person@example.com"]);
  });

  it("caps repeated attempts for one address", async () => {
    q1.mockResolvedValue({ id: 1, unsubscribed_at: null });
    let last = 0;
    for (let i = 0; i < 4; i++) last = (await POST(post({ email: "same@x.io" }))).status;
    expect(last).toBe(429);
  });

  it("caps sign-ups per client", async () => {
    q1.mockResolvedValue(null);
    q.mockResolvedValue([]);
    let last = 0;
    for (let i = 0; i < 6; i++) last = (await POST(post({ email: `u${i}@x.io` }))).status;
    expect(last).toBe(429);
  });
});

describe("GET /api/newsletter", () => {
  it("ignores non-integer year/week instead of sending NaN to pg", async () => {
    q1.mockResolvedValueOnce({ ok: "newsletter_editions" }).mockResolvedValueOnce(null);
    const res = await GET(new NextRequest(`http://${HOST}/api/newsletter?year=abc&week=1`));
    expect(res.status).toBe(200);
    // fell through to the "latest edition" query (no params)
    expect(q1.mock.calls[1][1]).toBeUndefined();
  });
});
