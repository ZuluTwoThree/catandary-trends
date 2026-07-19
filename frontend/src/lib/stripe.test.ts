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
      created: 1000,
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
    // ids persisted (customer + subscription id) on the primary user-id path
    const ids = sqlCall(/stripe_customer_id = COALESCE.*WHERE id = \$3/s);
    expect(ids!.params).toEqual(["cus_1", "sub_1", 42]);
    // tier applied, guarded by event time
    const tier = sqlCall(/SET tier = \$1, sub_event_at = to_timestamp\(\$2\) WHERE id = \$3/);
    expect(tier!.params).toEqual(["pro", 1000, 42]);
  });

  it("checkout.completed sets customer, subscription and tier by user id", async () => {
    const { POST } = await loadWebhook();
    const event = {
      type: "checkout.session.completed",
      created: 1234,
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
    const ids = sqlCall(/stripe_customer_id = COALESCE.*WHERE id = \$3/s);
    expect(ids!.params).toEqual(["cus_9", "sub_9", 7]);
    const tier = sqlCall(/SET tier = \$1, sub_event_at = to_timestamp\(\$2\) WHERE id = \$3/);
    expect(tier!.params).toEqual(["starter", 1234, 7]);
  });

  it("trialing status counts as an active paid tier", async () => {
    const { POST } = await loadWebhook();
    const event = {
      type: "customer.subscription.updated",
      created: 500,
      data: { object: { id: "s", customer: "c", status: "trialing", metadata: { user_id: "5" }, items: { data: [{ price: { id: "price_super" } }] } } },
    };
    await postEvent(POST, event, sign(JSON.stringify(event), SECRET));
    const tier = sqlCall(/SET tier = \$1, sub_event_at/);
    expect(tier!.params).toEqual(["superpro", 500, 5]);
  });

  it("subscription.deleted downgrades to free by user id, guarded by event time", async () => {
    const { POST } = await loadWebhook();
    const event = {
      type: "customer.subscription.deleted",
      created: 900,
      data: { object: { id: "s", customer: "c", metadata: { user_id: "8" } } },
    };
    await postEvent(POST, event, sign(JSON.stringify(event), SECRET));
    const call = sqlCall(/tier = 'free'/);
    expect(call!.sql).toMatch(/WHERE id = \$2/);
    expect(call!.sql).toMatch(/sub_event_at <= to_timestamp\(\$1\)/);
    expect(call!.params).toEqual([900, 8]);
  });

  it("does NOT change tier for an active but unknown price (no wrong downgrade)", async () => {
    const { POST } = await loadWebhook();
    const event = {
      type: "customer.subscription.updated",
      created: 700,
      data: { object: { id: "s", customer: "c", status: "active", metadata: { user_id: "3" }, items: { data: [{ price: { id: "price_unmapped" } }] } } },
    };
    await postEvent(POST, event, sign(JSON.stringify(event), SECRET));
    // ids still persisted, but no tier write at all
    expect(sqlCall(/stripe_customer_id = COALESCE.*WHERE id = \$3/s)).toBeDefined();
    expect(sqlCall(/SET tier =/)).toBeUndefined();
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
      created: 900,
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

/**
 * Reordering resistance, tested against a stateful fake that honours the SQL
 * ordering guard (sub_event_at <= event time). This exercises the actual outcome
 * — the final tier — not just which statements were emitted.
 */
describe("webhook handler — event reordering cannot resurrect a cancelled tier", () => {
  /** minimal app_users store emulating the guarded UPDATEs the webhook emits. */
  function useStore() {
    const users = new Map<number, { tier: string; sub_event_at: number | null; customer: string | null; sub: string | null }>();
    users.set(1, { tier: "free", sub_event_at: null, customer: null, sub: null });
    q.mockImplementation(async (sql: string, params: unknown[] = []) => {
      const u = users.get(Number(params[params.length - 1])) ??
        // customer-keyed statements key on the last param too in our tests (unused here)
        undefined;
      if (/SET tier = \$1, sub_event_at = to_timestamp\(\$2\) WHERE id = \$3/.test(sql)) {
        const [tier, created, id] = params as [string, number, number];
        const row = users.get(id)!;
        if (row.sub_event_at == null || row.sub_event_at <= created) {
          row.tier = tier;
          row.sub_event_at = created;
        }
      } else if (/tier = 'free'.*WHERE id = \$2/s.test(sql)) {
        const [created, id] = params as [number, number];
        const row = users.get(id)!;
        if (row.sub_event_at == null || row.sub_event_at <= created) {
          row.tier = "free";
          row.sub_event_at = created;
          row.sub = null;
        }
      } else if (/stripe_customer_id = COALESCE.*WHERE id = \$3/s.test(sql)) {
        const [cust, sub, id] = params as [string | null, string | null, number];
        const row = users.get(id)!;
        row.customer = row.customer ?? cust;
        row.sub = row.sub ?? sub;
      }
      void u;
      return [];
    });
    return users;
  }

  function updatedEvent(created: number, status = "active") {
    return {
      type: "customer.subscription.updated",
      created,
      data: { object: { id: "sub_1", customer: "cus_1", status, metadata: { user_id: "1", tier: "pro", price_id: "price_pro" }, items: { data: [{ price: { id: "price_pro" } }] } } },
    };
  }
  function checkoutEvent(created: number) {
    return {
      type: "checkout.session.completed",
      created,
      data: { object: { customer: "cus_1", subscription: "sub_1", metadata: { user_id: "1", tier: "pro", price_id: "price_pro" } } },
    };
  }
  function deletedEvent(created: number) {
    return {
      type: "customer.subscription.deleted",
      created,
      data: { object: { id: "sub_1", customer: "cus_1", metadata: { user_id: "1" } } },
    };
  }
  const send = async (POST: (r: Request) => Promise<Response>, ev: unknown) =>
    postEvent(POST, ev, sign(JSON.stringify(ev), SECRET));

  it("deleted(newer) then updated(older active): stays free", async () => {
    const { POST } = await loadWebhook();
    const users = useStore();
    await send(POST, deletedEvent(2000));
    await send(POST, updatedEvent(1000));
    expect(users.get(1)!.tier).toBe("free");
  });

  it("updated(older active) then deleted(newer): ends free", async () => {
    const { POST } = await loadWebhook();
    const users = useStore();
    await send(POST, updatedEvent(1000));
    await send(POST, deletedEvent(2000));
    expect(users.get(1)!.tier).toBe("free");
  });

  it("deleted(newer) then checkout(older): stays free", async () => {
    const { POST } = await loadWebhook();
    const users = useStore();
    await send(POST, deletedEvent(2000));
    await send(POST, checkoutEvent(1000));
    expect(users.get(1)!.tier).toBe("free");
  });

  it("checkout(older) then deleted(newer): ends free", async () => {
    const { POST } = await loadWebhook();
    const users = useStore();
    await send(POST, checkoutEvent(1000));
    await send(POST, deletedEvent(2000));
    expect(users.get(1)!.tier).toBe("free");
  });

  it("a genuine re-subscribe after cancel still upgrades (newer checkout wins)", async () => {
    const { POST } = await loadWebhook();
    const users = useStore();
    await send(POST, deletedEvent(2000)); // cancelled
    await send(POST, checkoutEvent(3000)); // later, real re-subscribe
    expect(users.get(1)!.tier).toBe("pro");
  });
});
