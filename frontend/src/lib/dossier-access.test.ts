/**
 * Access guard for the owner dossier desk (#95, shaped by #93).
 *
 * Dossiers are proprietary owner documents. On the owner instance the desk is
 * open by default (DOSSIERS_ENABLED=0 is only the emergency-off switch); on
 * anything public — PUBLIC_MODE preview, static export — it must be CLOSED,
 * whatever the flag says. Same contract as review-access.test.ts.
 */
import { describe, it, expect, afterEach } from "vitest";
import { canManageDossiers, dossiersEnabled } from "@/lib/dossier-access";

afterEach(() => {
  delete process.env.DOSSIERS_ENABLED;
  delete process.env.PUBLIC_MODE;
  delete process.env.STATIC_EXPORT;
  delete process.env.NEXT_PUBLIC_STATIC_EXPORT;
});

describe("canManageDossiers", () => {
  it("is open on the owner instance by default (flag unset)", () => {
    expect(dossiersEnabled()).toBe(true);
    expect(canManageDossiers()).toBe(true);
  });

  it("DOSSIERS_ENABLED=0 is the emergency-off switch", () => {
    process.env.DOSSIERS_ENABLED = "0";
    expect(dossiersEnabled()).toBe(false);
    expect(canManageDossiers()).toBe(false);
  });

  it("treats any other flag value as on", () => {
    for (const v of ["1", "true", "yes", ""]) {
      process.env.DOSSIERS_ENABLED = v;
      expect(canManageDossiers()).toBe(true);
    }
  });

  it("is closed under PUBLIC_MODE=1 even with the flag explicitly on", () => {
    process.env.DOSSIERS_ENABLED = "1";
    process.env.PUBLIC_MODE = "1";
    expect(canManageDossiers()).toBe(false);
  });

  it("is closed in the static export build (both env spellings)", () => {
    process.env.STATIC_EXPORT = "1";
    expect(canManageDossiers()).toBe(false);
    delete process.env.STATIC_EXPORT;
    process.env.NEXT_PUBLIC_STATIC_EXPORT = "1";
    expect(canManageDossiers()).toBe(false);
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
