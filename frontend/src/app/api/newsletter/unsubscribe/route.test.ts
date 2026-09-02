/**
 * Unsubscribe is a POST with a verified token, never a GET side effect
 * (security review 2026-09-02, E-7). Covers the browser form path and the
 * RFC 8058 one-click path, plus the fail-closed secret.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import crypto from "crypto";

const q = vi.fn();
vi.mock("@/lib/pg", () => ({ q: (...a: unknown[]) => q(...a), q1: vi.fn() }));

import { NextRequest } from "next/server";
import { POST } from "./route";
import { _resetRateLimit } from "@/lib/rateLimit";
import { proxy } from "@/proxy";

const SECRET = "0123456789abcdef0123456789abcdef";
const HOST = "localhost:3001";
const tokenFor = (email: string, secret = SECRET) =>
  crypto.createHmac("sha256", secret).update(email.toLowerCase()).digest("hex").slice(0, 32);

function form(fields: Record<string, string>, url = `http://${HOST}/api/newsletter/unsubscribe`) {
  return new NextRequest(url, {
    method: "POST",
    headers: { host: HOST, "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(fields).toString(),
  });
}

beforeEach(() => {
  q.mockReset();
  q.mockResolvedValue([]);
  _resetRateLimit();
  process.env.AUTH_SECRET = SECRET;
});
afterEach(() => {
  delete process.env.AUTH_SECRET;
});

describe("POST /api/newsletter/unsubscribe — confirmation form", () => {
  it("unsubscribes on a valid token and redirects to the done state", async () => {
    const res = await POST(form({ email: "Person@X.io", token: tokenFor("person@x.io"), confirm: "1" }));
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe(`http://${HOST}/trends/newsletter/unsubscribe?done=1`);
    expect(q).toHaveBeenCalledTimes(1);
    expect(String(q.mock.calls[0][0])).toMatch(/SET unsubscribed_at = NOW\(\)/);
    expect(q.mock.calls[0][1]).toEqual(["person@x.io"]);
  });

  it("does not write on a wrong token and redirects to the invalid state", async () => {
    const res = await POST(form({ email: "person@x.io", token: tokenFor("other@x.io"), confirm: "1" }));
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toContain("invalid=1");
    expect(q).not.toHaveBeenCalled();
  });

  it("fails closed when AUTH_SECRET is missing — even for the empty-key token", async () => {
    delete process.env.AUTH_SECRET;
    const res = await POST(form({ email: "victim@x.io", token: tokenFor("victim@x.io", ""), confirm: "1" }));
    expect(res.headers.get("location")).toContain("invalid=1");
    expect(q).not.toHaveBeenCalled();
  });

  it("rejects an oversize body", async () => {
    const res = await POST(form({ email: "a@x.io", token: tokenFor("a@x.io"), pad: "x".repeat(4000) }));
    expect(res.status).toBe(413);
    expect(q).not.toHaveBeenCalled();
  });
});

describe("RFC 8058 one-click (identity in the URL, marker in the body)", () => {
  const link = (email: string, token: string) =>
    `http://${HOST}/trends/newsletter/unsubscribe?email=${encodeURIComponent(email)}&token=${token}`;

  it("proxy hands a plain POST on the page path to the route, query intact", () => {
    const req = new NextRequest(link("a@x.io", "t"), { method: "POST" });
    const res = proxy(req);
    const rewrite = res.headers.get("x-middleware-rewrite");
    expect(rewrite).toContain("/api/newsletter/unsubscribe");
    expect(rewrite).toContain("email=a%40x.io");
    expect(rewrite).toContain("token=t");
  });

  it("proxy leaves GETs and Server-Action POSTs on the page alone", () => {
    expect(proxy(new NextRequest(link("a@x.io", "t"))).headers.get("x-middleware-rewrite")).toBeNull();
    const action = new NextRequest(link("a@x.io", "t"), { method: "POST", headers: { "next-action": "abc" } });
    expect(proxy(action).headers.get("x-middleware-rewrite")).toBeNull();
  });

  it("answers 200 directly (no redirect) on a valid token", async () => {
    const res = await POST(form({ "List-Unsubscribe": "One-Click" }, link("a@x.io", tokenFor("a@x.io"))));
    expect(res.status).toBe(200);
    expect(q.mock.calls[0][1]).toEqual(["a@x.io"]);
  });

  it("answers 400 on an invalid token without writing", async () => {
    const res = await POST(form({ "List-Unsubscribe": "One-Click" }, link("a@x.io", tokenFor("b@x.io"))));
    expect(res.status).toBe(400);
    expect(q).not.toHaveBeenCalled();
  });
});
