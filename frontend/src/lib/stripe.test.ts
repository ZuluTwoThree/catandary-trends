import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import crypto from "crypto";

// Capture DB writes; the webhook route only uses q().
const q = vi.fn();
vi.mock("@/lib/pg", () => ({
  q: (...a: unknown[]) => q(...a),
  q1: vi.fn(),
  getPool: vi.fn(),
}));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => undefined, set: () => {}, delete: () => {} }),
}));

function sign(body: string, secret: string, t = Math.floor(Date.now() / 1000)): string {
  const v1 = crypto.createHmac("sha256", secret).update(`${t}.${body}`).digest("hex");
  return `t=${t},v1=${v1}`;
}

async function loadStripe() {
  vi.resetModules();
  return import("@/lib/stripe");
}
async function loadWebhook() {
  vi.resetModules();
  return import("@/app/api/stripe/webhook/route");
}
async function postEvent(
  POST: (r: Request) => Promise<Response>,
  event: unknown,
  sigHeader: string
): Promise<Response> {
  const body = JSON.stringify(event);
  return POST(
    new Request("http://x/api/stripe/webhook", {
      method: "POST",
      body,
      headers: { "stripe-signature": sigHeader },
    })
  );
}
/** find the first captured q() call whose SQL matches `re`. */
function sqlCall(re: RegExp): { sql: string; params: unknown[] } | undefined {
  const c = q.mock.calls.find((call) => re.test(String(call[0])));
  return c ? { sql: String(c[0]), params: c[1] as unknown[] } : undefined;
}

const SECRET = "whsec_primary";

beforeEach(() => {
  q.mockReset().mockResolvedValue(undefined);
  vi.stubEnv("STRIPE_WEBHOOK_SECRET", SECRET);
  vi.stubEnv("STRIPE_PRICE_STARTER", "price_starter");
  vi.stubEnv("STRIPE_PRICE_PRO", "price_pro");
  vi.stubEnv("STRIPE_PRICE_SUPERPRO", "price_super");
});
afterEach(() => vi.unstubAllEnvs());

describe("verifyWebhook signature", () => {
  it("accepts a valid signature and returns the parsed event", async () => {
    const { verifyWebhook } = await loadStripe();
    const body = JSON.stringify({ type: "ping" });
    expect(verifyWebhook(body, sign(body, SECRET))).toMatchObject({ type: "ping" });
  });

  it("rejects a tampered body", async () => {
    const { verifyWebhook } = await loadStripe();
    const sig = sign(JSON.stringify({ type: "ping" }), SECRET);
    expect(verifyWebhook(JSON.stringify({ type: "evil" }), sig)).toBeNull();
  });

  it("rejects an expired timestamp (replay)", async () => {
    const { verifyWebhook } = await loadStripe();
    const body = JSON.stringify({ type: "ping" });
    const oldT = Math.floor(Date.now() / 1000) - 600;
    expect(verifyWebhook(body, sign(body, SECRET, oldT))).toBeNull();
  });

  it("verifies with an OLD secret during rotation (comma-separated secrets)", async () => {
    vi.stubEnv("STRIPE_WEBHOOK_SECRET", "whsec_new,whsec_old");
    const { verifyWebhook } = await loadStripe();
    const body = JSON.stringify({ type: "ping" });
    // signed only with the old secret — must still verify
    expect(verifyWebhook(body, sign(body, "whsec_old"))).toMatchObject({ type: "ping" });
  });

  it("accepts a header carrying multiple v1 signatures if one matches", async () => {
    const { verifyWebhook } = await loadStripe();
    const body = JSON.stringify({ type: "ping" });
    const t = Math.floor(Date.now() / 1000);
    const good = crypto.createHmac("sha256", SECRET).update(`${t}.${body}`).digest("hex");
    const header = `t=${t},v1=deadbeef,v1=${good}`;
    expect(verifyWebhook(body, header)).toMatchObject({ type: "ping" });
  });
});

describe("webhook handler — order independence & idempotency", () => {
  it("subscription.updated BEFORE checkout.completed resolves the user via metadata", async () => {
    const { POST } = await loadWebhook();
    const event = {
      type: "customer.subscription.updated",
      data: {
        object: {
          id: "sub_1",
          customer: "cus_1",
          status: "active",
          metadata: { user_id: "42", tier: "pro", price_id: "price_pro" },
          items: { data: [{ price: { id: "price_pro" } }] },
        },
      },
    };
    const res = await postEvent(POST, event, sign(JSON.stringify(event), SECRET));
    expect(res.status).toBe(200);
    const call = sqlCall(/WHERE id = \$2/);
    expect(call).toBeDefined();
    expect(call!.sql).toMatch(/tier = \$3/);
    expect(call!.params).toEqual(["cus_1", 42, "pro"]);
  });

  it("checkout.completed sets customer, subscription and tier by user id", async () => {
    const { POST } = await loadWebhook();
    const event = {
      type: "checkout.session.completed",
      data: {
        object: {
          customer: "cus_9",
          subscription: "sub_9",
          client_reference_id: "7",
          metadata: { user_id: "7", tier: "starter", price_id: "price_starter" },
        },
      },
    };
    const res = await postEvent(POST, event, sign(JSON.stringify(event), SECRET));
    expect(res.status).toBe(200);
    const call = sqlCall(/stripe_customer_id = COALESCE/);
    expect(call!.sql).toMatch(/tier = \$4/);
    expect(call!.params).toEqual(["cus_9", "sub_9", 7, "starter"]);
  });

  it("trialing status counts as an active paid tier", async () => {
    const { POST } = await loadWebhook();
    const event = {
      type: "customer.subscription.updated",
      data: { object: { id: "s", customer: "c", status: "trialing", metadata: { user_id: "5" }, items: { data: [{ price: { id: "price_super" } }] } } },
    };
    await postEvent(POST, event, sign(JSON.stringify(event), SECRET));
    const call = sqlCall(/WHERE id = \$2/);
    expect(call!.params).toEqual(["c", 5, "superpro"]);
  });

  it("subscription.deleted downgrades to free by user id", async () => {
    const { POST } = await loadWebhook();
    const event = {
      type: "customer.subscription.deleted",
      data: { object: { id: "s", customer: "c", metadata: { user_id: "8" } } },
    };
    await postEvent(POST, event, sign(JSON.stringify(event), SECRET));
    const call = sqlCall(/tier = 'free'/);
    expect(call!.sql).toMatch(/WHERE id = \$1/);
    expect(call!.params).toEqual([8]);
  });

  it("does NOT change tier for an active but unknown price (no wrong downgrade)", async () => {
    const { POST } = await loadWebhook();
    const event = {
      type: "customer.subscription.updated",
      data: { object: { id: "s", customer: "c", status: "active", metadata: { user_id: "3" }, items: { data: [{ price: { id: "price_unmapped" } }] } } },
    };
    await postEvent(POST, event, sign(JSON.stringify(event), SECRET));
    const call = sqlCall(/WHERE id = \$2/);
    expect(call).toBeDefined();
    expect(call!.sql).not.toMatch(/tier =/); // tier left untouched
    expect(call!.params).toEqual(["c", 3]);
  });

  it("rejects an invalid signature with 400", async () => {
    const { POST } = await loadWebhook();
    const event = { type: "customer.subscription.deleted", data: { object: { metadata: { user_id: "1" } } } };
    const res = await postEvent(POST, event, "t=123,v1=bad");
    expect(res.status).toBe(400);
    expect(q).not.toHaveBeenCalled();
  });

  it("is idempotent: a duplicate delivery repeats the same write", async () => {
    const { POST } = await loadWebhook();
    const event = {
      type: "customer.subscription.deleted",
      data: { object: { id: "s", customer: "c", metadata: { user_id: "8" } } },
    };
    const sig = sign(JSON.stringify(event), SECRET);
    await postEvent(POST, event, sig);
    await postEvent(POST, event, sig);
    const frees = q.mock.calls.filter((c) => /tier = 'free'/.test(String(c[0])));
    expect(frees).toHaveLength(2);
    expect(frees[0][1]).toEqual(frees[1][1]); // same params → same effect
  });
});
