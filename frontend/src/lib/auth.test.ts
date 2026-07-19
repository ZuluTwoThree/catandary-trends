import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import crypto from "crypto";

// Mock the DB + Next runtime so importing auth.ts / the route touches neither a
// real Postgres nor next/headers.
const q = vi.fn();
const q1 = vi.fn();

// Stateful backing for the transaction + cookie mocks. Reset in beforeEach. The
// vi.mock factories run lazily (at import, after resetModules), so referencing
// this top-level object from inside them is safe.
const store = {
  cookieValue: undefined as string | undefined,
  tokens: new Map<string, { used: boolean; email: string; optIn: boolean }>(),
  failUpsert: false,
  nextUserId: 100,
};

vi.mock("@/lib/pg", () => ({
  q: (...a: unknown[]) => q(...a),
  q1: (...a: unknown[]) => q1(...a),
  getPool: vi.fn(),
  // Emulate a real BEGIN/COMMIT/ROLLBACK against the in-memory token store so the
  // transactional guarantee (token not consumed if the user upsert fails) is
  // actually exercised, not just asserted on statement shape.
  withTransaction: async (fn: (client: unknown) => Promise<unknown>) => {
    const snapshot = new Map([...store.tokens].map(([k, v]) => [k, { ...v }]));
    const client = {
      query: async (sql: string, params: unknown[] = []) => {
        if (/UPDATE magic_tokens SET used = TRUE/.test(sql)) {
          const t = store.tokens.get(params[0] as string);
          if (!t || t.used) return { rowCount: 0, rows: [] };
          t.used = true;
          return { rowCount: 1, rows: [{ email: t.email, newsletter_opt_in: t.optIn }] };
        }
        if (/INSERT INTO app_users/.test(sql)) {
          if (store.failUpsert) throw new Error("upsert boom");
          return { rowCount: 1, rows: [{ id: store.nextUserId }] };
        }
        return { rowCount: 0, rows: [] };
      },
    };
    try {
      return await fn(client);
    } catch (e) {
      store.tokens = snapshot; // ROLLBACK
      throw e;
    }
  },
}));
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (_name: string) => (store.cookieValue ? { value: store.cookieValue } : undefined),
    set: () => {},
    delete: () => {},
  }),
}));

function jsonReq(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request("http://x/api/auth/request", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

// resetModules re-evaluates auth.ts module-level consts (AUTH_ENABLED) and gives
// the route a fresh rate-limiter, so each scenario is isolated.
async function loadRoute() {
  vi.resetModules();
  return import("@/app/api/auth/request/route");
}
async function loadAuth() {
  vi.resetModules();
  return import("@/lib/auth");
}

function sha(raw: string): string {
  return crypto.createHash("sha256").update(raw).digest("hex");
}

beforeEach(() => {
  q.mockReset().mockResolvedValue(undefined);
  q1.mockReset().mockResolvedValue(undefined);
  store.cookieValue = undefined;
  store.tokens = new Map();
  store.failUpsert = false;
  store.nextUserId = 100;
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

describe("session verification — fail closed on every path", () => {
  it("accepts a validly signed cookie and loads the user", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const auth = await loadAuth();
    store.cookieValue = auth.makeSessionValue(7);
    q1.mockResolvedValue({ id: 7, email: "a@b.com", tier: "pro" });
    expect(await auth.getSession()).toEqual({ id: 7, email: "a@b.com", tier: "pro" });
  });

  it("rejects a forged cookie (wrong signature) without hitting the DB", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const auth = await loadAuth();
    const good = auth.makeSessionValue(7);
    const [payload, sig] = good.split(".");
    store.cookieValue = `${payload}.${"a".repeat(sig.length)}`; // same length, wrong bytes
    q1.mockResolvedValue({ id: 7, email: "a@b.com", tier: "pro" });
    expect(await auth.getSession()).toBeNull();
    expect(q1).not.toHaveBeenCalled();
  });

  it("in production a set-but-weak AUTH_SECRET trusts NO cookie (even one it signed)", async () => {
    // Mint under the weak secret in dev (allowed), then verify under production.
    vi.stubEnv("AUTH_SECRET", "short"); // < 16 chars
    vi.stubEnv("NODE_ENV", "development");
    const auth = await loadAuth();
    store.cookieValue = auth.makeSessionValue(7);
    q1.mockResolvedValue({ id: 7, email: "a@b.com", tier: "pro" });
    vi.stubEnv("NODE_ENV", "production"); // weak secret is now unusable → fail closed
    expect(await auth.getSession()).toBeNull();
    expect(q1).not.toHaveBeenCalled();
  });

  it("refuses to MINT a session in production with a weak AUTH_SECRET", async () => {
    vi.stubEnv("AUTH_SECRET", "short");
    vi.stubEnv("NODE_ENV", "production");
    const auth = await loadAuth();
    expect(() => auth.makeSessionValue(7)).toThrow();
  });
});

describe("consumeMagicToken — single-use, atomic, transactional", () => {
  it("consumes once and returns null on the second (already-used) attempt", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const raw = "raw-token";
    store.tokens.set(sha(raw), { used: false, email: "a@b.com", optIn: false });
    store.nextUserId = 7;
    const auth = await loadAuth();
    expect(await auth.consumeMagicToken(raw)).toBe(7);
    expect(store.tokens.get(sha(raw))!.used).toBe(true);
    expect(await auth.consumeMagicToken(raw)).toBeNull();
  });

  it("rolls back — token stays unused — when the user upsert fails", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const raw = "raw-2";
    store.tokens.set(sha(raw), { used: false, email: "c@d.com", optIn: false });
    store.failUpsert = true;
    const auth = await loadAuth();
    expect(await auth.consumeMagicToken(raw)).toBeNull();
    // The link must remain valid: a failed upsert cannot burn the token.
    expect(store.tokens.get(sha(raw))!.used).toBe(false);
    // And a subsequent healthy attempt still works.
    store.failUpsert = false;
    store.nextUserId = 42;
    expect(await auth.consumeMagicToken(raw)).toBe(42);
  });

  it("returns null for an unknown/invalid token", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const auth = await loadAuth();
    expect(await auth.consumeMagicToken("never-issued")).toBeNull();
  });

  it("mirrors a newsletter opt-in after a successful consume", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const raw = "raw-3";
    store.tokens.set(sha(raw), { used: false, email: "e@f.com", optIn: true });
    store.nextUserId = 9;
    q.mockResolvedValue(undefined);
    const auth = await loadAuth();
    expect(await auth.consumeMagicToken(raw)).toBe(9);
    expect(q.mock.calls.some((c) => /newsletter_subscribers/.test(String(c[0])))).toBe(true);
  });
});
