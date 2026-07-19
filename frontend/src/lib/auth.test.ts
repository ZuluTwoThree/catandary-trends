import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock the DB + Next runtime so importing auth.ts / the route touches neither a
// real Postgres nor next/headers.
const q = vi.fn();
const q1 = vi.fn();
vi.mock("@/lib/pg", () => ({
  q: (...a: unknown[]) => q(...a),
  q1: (...a: unknown[]) => q1(...a),
  getPool: vi.fn(),
}));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => undefined, set: () => {}, delete: () => {} }),
}));

function jsonReq(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request("http://x/api/auth/request", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

// resetModules re-evaluates auth.ts module-level consts (AUTH_ENABLED, SECRET) and
// gives the route a fresh rate-limiter, so each scenario is isolated.
async function loadRoute() {
  vi.resetModules();
  return import("@/app/api/auth/request/route");
}
async function loadAuth() {
  vi.resetModules();
  return import("@/lib/auth");
}

beforeEach(() => {
  q.mockReset().mockResolvedValue(undefined);
  q1.mockReset().mockResolvedValue(undefined);
  vi.stubEnv("AUTH_ENABLED", "1");
  vi.stubEnv("AUTH_SECRET", "x".repeat(32));
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("auth request route — production misconfiguration", () => {
  it("returns 503 when AUTH_SECRET is missing in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("AUTH_SECRET", "");
    vi.stubEnv("EMAIL_TRANSPORT", "resend");
    vi.stubEnv("RESEND_API_KEY", "re_test");
    const { POST } = await loadRoute();
    const res = await POST(jsonReq({ email: "a@b.com" }));
    expect(res.status).toBe(503);
  });

  it("returns 503 when transport is console in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("EMAIL_TRANSPORT", "console");
    const { POST } = await loadRoute();
    const res = await POST(jsonReq({ email: "a@b.com" }));
    expect(res.status).toBe(503);
  });
});

describe("auth request route — dev link exposure", () => {
  it("returns devLink in non-production console transport", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("EMAIL_TRANSPORT", "console");
    const { POST } = await loadRoute();
    const res = await POST(jsonReq({ email: "a@b.com" }));
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(body.ok).toBe(true);
    expect(body.devLink).toMatch(/token=/);
  });

  it("never returns devLink in production (resend configured)", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("EMAIL_TRANSPORT", "resend");
    vi.stubEnv("RESEND_API_KEY", "re_test");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    const { POST } = await loadRoute();
    const res = await POST(jsonReq({ email: "a@b.com" }));
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(body.ok).toBe(true);
    expect(body.devLink).toBeUndefined();
  });
});

describe("auth request route — resend failures", () => {
  it("returns 502 (not success) when resend responds non-2xx", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("EMAIL_TRANSPORT", "resend");
    vi.stubEnv("RESEND_API_KEY", "re_test");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("invalid", { status: 422 })));
    const { POST } = await loadRoute();
    const res = await POST(jsonReq({ email: "a@b.com" }));
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.ok).toBeUndefined();
  });

  it("returns 502 when the resend request throws (network)", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("EMAIL_TRANSPORT", "resend");
    vi.stubEnv("RESEND_API_KEY", "re_test");
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("ECONNREFUSED"); }));
    const { POST } = await loadRoute();
    const res = await POST(jsonReq({ email: "a@b.com" }));
    expect(res.status).toBe(502);
  });
});

describe("auth request route — rate limiting", () => {
  it("429s after the per-email limit", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("EMAIL_TRANSPORT", "console");
    const { POST } = await loadRoute();
    let last = 0;
    for (let i = 0; i < 6; i++) {
      last = (await POST(jsonReq({ email: "same@b.com" }))).status;
    }
    // EMAIL_LIMIT = 4 → the 5th+ request is throttled
    expect(last).toBe(429);
  });

  it("429s after the per-IP limit across distinct emails", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("EMAIL_TRANSPORT", "console");
    const { POST } = await loadRoute();
    const hdr = { "x-forwarded-for": "203.0.113.9" };
    let last = 0;
    for (let i = 0; i < 12; i++) {
      last = (await POST(jsonReq({ email: `u${i}@b.com` }, hdr))).status;
    }
    // IP_LIMIT = 10 → the 11th+ request is throttled
    expect(last).toBe(429);
  });
});

describe("consumeMagicToken — single-use atomicity", () => {
  it("consumes once and returns null on the second (already-used) attempt", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const auth = await loadAuth();
    // 1st consume: atomic UPDATE...RETURNING yields the row, then app_users upsert
    q1.mockResolvedValueOnce({ email: "a@b.com", newsletter_opt_in: false })
      .mockResolvedValueOnce({ id: 7 })
      // 2nd consume: UPDATE...WHERE used=FALSE finds nothing → null
      .mockResolvedValueOnce(undefined);
    expect(await auth.consumeMagicToken("raw-token")).toBe(7);
    expect(await auth.consumeMagicToken("raw-token")).toBeNull();
    // the consuming statement must be a single atomic UPDATE, not SELECT-then-UPDATE
    const firstSql = String(q1.mock.calls[0][0]);
    expect(firstSql).toMatch(/UPDATE magic_tokens SET used = TRUE/);
    expect(firstSql).toMatch(/used = FALSE/);
  });
});
