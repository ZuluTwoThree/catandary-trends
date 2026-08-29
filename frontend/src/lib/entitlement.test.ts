/**
 * Free archive window (issue #70): the pure date check and the viewer-window
 * resolution. Follows the auth.test.ts pattern — resetModules re-evaluates the
 * module-level PAYWALL_ENABLED const per test, the auth session is mocked via
 * a lazy holder.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const holder: { session: { tier: string } | null } = { session: null };

vi.mock("@/lib/auth", () => ({
  getSession: vi.fn(async () => holder.session),
}));

async function loadWith(paywall: "0" | "1") {
  vi.resetModules();
  process.env.PAYWALL_ENABLED = paywall;
  return await import("@/lib/entitlement");
}

beforeEach(() => {
  holder.session = null;
});

afterEach(() => {
  delete process.env.PAYWALL_ENABLED;
  vi.resetModules();
});

describe("withinArchiveWindow", () => {
  const days = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();

  it("null window = unlimited archive", async () => {
    const { withinArchiveWindow } = await loadWith("1");
    expect(withinArchiveWindow(days(400), null)).toBe(true);
  });

  it("keeps articles inside the window, drops older ones (28-day boundary)", async () => {
    const { withinArchiveWindow } = await loadWith("1");
    expect(withinArchiveWindow(days(27), 28)).toBe(true);
    expect(withinArchiveWindow(days(29), 28)).toBe(false);
  });

  it("fails OPEN on missing or unparseable dates — bad data never hides content", async () => {
    const { withinArchiveWindow } = await loadWith("1");
    expect(withinArchiveWindow(null, 28)).toBe(true);
    expect(withinArchiveWindow(undefined, 28)).toBe(true);
    expect(withinArchiveWindow("kein-datum", 28)).toBe(true);
  });

  it("accepts Date objects", async () => {
    const { withinArchiveWindow } = await loadWith("1");
    expect(withinArchiveWindow(new Date(), 28)).toBe(true);
    expect(withinArchiveWindow(new Date(Date.now() - 40 * 86_400_000), 28)).toBe(false);
  });
});

describe("archiveWindowDays", () => {
  it("paywall off → unlimited for everyone (deployed behavior today)", async () => {
    const { archiveWindowDays } = await loadWith("0");
    expect(await archiveWindowDays()).toBeNull();
  });

  it("paywall on + anonymous → FREE_ARCHIVE_DAYS", async () => {
    const mod = await loadWith("1");
    expect(await mod.archiveWindowDays()).toBe(mod.FREE_ARCHIVE_DAYS);
  });

  it("paywall on + free account → FREE_ARCHIVE_DAYS", async () => {
    holder.session = { tier: "free" };
    const mod = await loadWith("1");
    expect(await mod.archiveWindowDays()).toBe(mod.FREE_ARCHIVE_DAYS);
  });

  it("paywall on + starter and above → unlimited", async () => {
    for (const tier of ["starter", "pro", "superpro"]) {
      holder.session = { tier };
      const mod = await loadWith("1");
      expect(await mod.archiveWindowDays()).toBeNull();
    }
  });

  // #93: the public showcase ships only the last 30 days — PUBLIC_MODE wins
  // over paywall state AND any tier (no accounts exist on the public site).
  it("PUBLIC_MODE=1 → PUBLIC_ARCHIVE_DAYS regardless of paywall", async () => {
    process.env.PUBLIC_MODE = "1";
    try {
      for (const paywall of ["0", "1"] as const) {
        const mod = await loadWith(paywall);
        expect(await mod.archiveWindowDays()).toBe(mod.PUBLIC_ARCHIVE_DAYS);
      }
    } finally {
      delete process.env.PUBLIC_MODE;
    }
  });

  it("PUBLIC_MODE=1 → window even for a superpro session", async () => {
    process.env.PUBLIC_MODE = "1";
    try {
      holder.session = { tier: "superpro" };
      const mod = await loadWith("1");
      expect(await mod.archiveWindowDays()).toBe(mod.PUBLIC_ARCHIVE_DAYS);
    } finally {
      delete process.env.PUBLIC_MODE;
    }
  });
});
