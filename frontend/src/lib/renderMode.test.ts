/**
 * Render-mode switch for the static export (design Schritt 2): the flag
 * must be off by default (workstation instance unchanged) and
 * dynamicUnlessStatic() must opt into request-time rendering exactly when
 * the flag is off.
 */
import { describe, it, expect, vi, afterEach } from "vitest";

const connection = vi.fn(async () => undefined);
vi.mock("next/server", () => ({ connection }));

import { isStaticExport, dynamicUnlessStatic } from "@/lib/renderMode";

afterEach(() => {
  delete process.env.STATIC_EXPORT;
  delete process.env.NEXT_PUBLIC_STATIC_EXPORT;
  connection.mockClear();
});

describe("isStaticExport", () => {
  it("is off when neither flag is set — the workstation build", () => {
    expect(isStaticExport()).toBe(false);
  });

  it("is off for any value other than '1'", () => {
    for (const v of ["0", "true", "yes", ""]) {
      process.env.STATIC_EXPORT = v;
      process.env.NEXT_PUBLIC_STATIC_EXPORT = v;
      expect(isStaticExport()).toBe(false);
    }
  });

  it("is on for STATIC_EXPORT=1 (server side, next.config)", () => {
    process.env.STATIC_EXPORT = "1";
    expect(isStaticExport()).toBe(true);
  });

  it("is on for the NEXT_PUBLIC_ mirror (client bundles)", () => {
    process.env.NEXT_PUBLIC_STATIC_EXPORT = "1";
    expect(isStaticExport()).toBe(true);
  });
});

describe("dynamicUnlessStatic", () => {
  it("marks the render dynamic on the workstation (calls connection())", async () => {
    await dynamicUnlessStatic();
    expect(connection).toHaveBeenCalledTimes(1);
  });

  it("is a no-op in the static export", async () => {
    process.env.STATIC_EXPORT = "1";
    await dynamicUnlessStatic();
    expect(connection).not.toHaveBeenCalled();
  });
});
