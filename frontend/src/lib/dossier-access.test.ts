/**
 * Access guard for the owner-only dossier desk.
 *
 * Dossiers are proprietary owner documents — the guard must default to
 * CLOSED: a deployment that knows nothing about DOSSIERS_ENABLED has to 404,
 * never expose an order slip or a report. Same contract as the review queue
 * guard (review-access.test.ts).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const holder: { session: unknown } = { session: null };

vi.mock("@/lib/auth", async () => {
  return {
    get AUTH_ENABLED() {
      return process.env.AUTH_ENABLED === "1";
    },
    getSession: vi.fn(async () => holder.session),
  };
});

async function load(dossiers?: string, auth?: string) {
  vi.resetModules();
  if (dossiers === undefined) delete process.env.DOSSIERS_ENABLED;
  else process.env.DOSSIERS_ENABLED = dossiers;
  if (auth === undefined) delete process.env.AUTH_ENABLED;
  else process.env.AUTH_ENABLED = auth;
  return await import("@/lib/dossier-access");
}

beforeEach(() => {
  holder.session = null;
});
afterEach(() => {
  delete process.env.DOSSIERS_ENABLED;
  delete process.env.AUTH_ENABLED;
  vi.resetModules();
});

describe("canManageDossiers", () => {
  it("is closed when DOSSIERS_ENABLED is unset — the safe default", async () => {
    const m = await load(undefined, "0");
    expect(await m.canManageDossiers()).toBe(false);
  });

  it("is closed for any value other than '1'", async () => {
    for (const v of ["0", "true", "yes", ""]) {
      const m = await load(v, "0");
      expect(await m.canManageDossiers()).toBe(false);
    }
  });

  it("opens with the flag while auth is off (localhost operation today)", async () => {
    const m = await load("1", "0");
    expect(await m.canManageDossiers()).toBe(true);
  });

  it("additionally demands a session once auth is on", async () => {
    const m = await load("1", "1");
    expect(await m.canManageDossiers()).toBe(false); // anonymous
    holder.session = { email: "owner@example.com", tier: "free" };
    expect(await m.canManageDossiers()).toBe(true);
  });
});

describe("slugifyTopic parity", () => {
  // Must mirror pipeline.dossier_orders.slugify — a topic ordered from the
  // page and one ordered from the CLI have to land in the SAME series.
  it("matches the python slugify on representative inputs", async () => {
    const { slugifyTopic } = await import("@/lib/dossiers");
    expect(slugifyTopic("Solid-State Batteries")).toBe("solid-state-batteries");
    expect(slugifyTopic("Präzisions-Fermentation (DACH)")).toBe(
      "prazisions-fermentation-dach"
    );
    expect(slugifyTopic("???")).toBe("dossier");
    expect(slugifyTopic("a".repeat(120))).toHaveLength(80);
  });
});
