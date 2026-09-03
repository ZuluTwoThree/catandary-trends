import { describe, it, expect, afterEach } from "vitest";
import { RELOCATED_ROOT_PAGES, sitePath } from "@/lib/sitePaths";

describe("sitePath", () => {
  const saved = { s: process.env.STATIC_EXPORT, p: process.env.NEXT_PUBLIC_STATIC_EXPORT };
  afterEach(() => {
    if (saved.s === undefined) delete process.env.STATIC_EXPORT;
    else process.env.STATIC_EXPORT = saved.s;
    if (saved.p === undefined) delete process.env.NEXT_PUBLIC_STATIC_EXPORT;
    else process.env.NEXT_PUBLIC_STATIC_EXPORT = saved.p;
  });

  it("keeps the root URLs on the workstation", () => {
    delete process.env.STATIC_EXPORT;
    delete process.env.NEXT_PUBLIC_STATIC_EXPORT;
    for (const page of RELOCATED_ROOT_PAGES) expect(sitePath(page)).toBe(page);
  });

  it("moves the three pages under /trends in the export (server and client flag)", () => {
    process.env.STATIC_EXPORT = "1";
    expect(sitePath("/imprint")).toBe("/trends/imprint");
    expect(sitePath("/privacy")).toBe("/trends/privacy");
    expect(sitePath("/enquiry")).toBe("/trends/enquiry");
    delete process.env.STATIC_EXPORT;
    process.env.NEXT_PUBLIC_STATIC_EXPORT = "1";
    expect(sitePath("/enquiry")).toBe("/trends/enquiry");
  });
});
