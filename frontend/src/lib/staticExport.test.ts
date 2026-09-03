/**
 * Drift guards for the static export (design Schritt 1/2):
 *
 *  1. frontend/static-export.exclude — the rsync exclusion list the export
 *     build strips from the staging tree — must mirror BLOCKED_PREFIXES in
 *     lib/publicMode.ts in both directions, plus the fixed set of things
 *     `output: "export"` cannot build (Proxy, API routes, ...).
 *  2. No page that survives the exclusion may still carry the literal
 *     `dynamic = "force-dynamic"` (the export refuses it) or a `route.ts`
 *     handler — the replacement is `await dynamicUnlessStatic()`.
 *
 * Reads the real files under src/app so a renamed or newly added route is
 * caught here, not at 06:30 on the cron.
 */
import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { BLOCKED_PREFIXES } from "@/lib/publicMode";

const FRONTEND = path.resolve(__dirname, "..", "..");
const APP = path.join(FRONTEND, "src", "app");

function readExcludes(): string[] {
  const raw = fs.readFileSync(path.join(FRONTEND, "static-export.exclude"), "utf-8");
  return raw
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l !== "" && !l.startsWith("#"));
}

/** Entries the export drops beyond the public-mode block list. */
const NOT_EXPORTABLE = [
  "src/proxy.ts",
  "src/app/api/",
  "src/app/trends/newsletter/unsubscribe/",
  "src/app/trends/vertical/",
];

function isExcluded(relFromFrontend: string, excludes: string[]): boolean {
  return excludes.some((e) => {
    if (!e.startsWith("src/")) return false;
    return e.endsWith("/") ? relFromFrontend.startsWith(e) : relFromFrontend === e;
  });
}

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else out.push(full);
  }
  return out;
}

describe("static-export.exclude mirrors BLOCKED_PREFIXES", () => {
  const excludes = readExcludes();
  const srcExcludes = excludes.filter((e) => e.startsWith("src/"));

  it("every blocked page prefix is excluded; blocked API prefixes are covered by src/app/api/", () => {
    for (const prefix of BLOCKED_PREFIXES) {
      const expected = prefix.startsWith("/api/") ? "src/app/api/" : `src/app${prefix}/`;
      expect(srcExcludes, `missing exclusion for ${prefix}`).toContain(expected);
    }
  });

  it("every src/ exclusion is either a blocked prefix or a known non-exportable path", () => {
    const allowed = new Set([
      ...BLOCKED_PREFIXES.filter((p) => !p.startsWith("/api/")).map((p) => `src/app${p}/`),
      ...NOT_EXPORTABLE,
    ]);
    for (const e of srcExcludes) {
      expect(allowed.has(e), `${e} is excluded but is neither blocked nor non-exportable`).toBe(true);
    }
  });

  it("every excluded src/ path exists on disk (a renamed route would leave the list stale)", () => {
    for (const e of srcExcludes) {
      expect(fs.existsSync(path.join(FRONTEND, e)), `${e} does not exist`).toBe(true);
    }
  });

  it("the build artefact exclusions are present", () => {
    for (const e of ["node_modules/", ".next/", ".next-*/", "out/", ".export/", ".env", ".env.*"]) {
      expect(excludes).toContain(e);
    }
  });
});

describe("the surviving app tree is exportable", () => {
  const excludes = readExcludes();
  const files = walk(APP).map((f) => path.relative(FRONTEND, f).split(path.sep).join("/"));
  const surviving = files.filter((f) => !isExcluded(f, excludes));

  it("keeps the public routes", () => {
    for (const must of [
      "src/app/page.tsx",
      "src/app/trends/(feed)/page.tsx",
      "src/app/trends/[slug]/page.tsx",
      "src/app/trends/page/[n]/page.tsx",
      "src/app/trends/v/[vertical]/page.tsx",
      "src/app/trends/v/[vertical]/page/[n]/page.tsx",
      "src/app/trends/mega/page.tsx",
      "src/app/trends/mega/[megatrend]/page.tsx",
      "src/app/trends/methodology/page.tsx",
      "src/app/trends/newsletter/page.tsx",
      "src/app/trends/expired/page.tsx",
      "src/app/trends/imprint/page.tsx",
      "src/app/trends/privacy/page.tsx",
      "src/app/trends/enquiry/page.tsx",
      "src/app/analysis/page.tsx",
      "src/app/analysis/[slug]/page.tsx",
      "src/app/trends/sitemap.ts",
      "src/app/trends/index.json/route.ts",
      "src/app/robots.ts",
      "src/app/not-found.tsx",
    ]) {
      expect(surviving).toContain(must);
    }
  });

  it("every surviving dynamic segment exports generateStaticParams (the export needs the list)", () => {
    const dynamicPages = surviving.filter((f) => /\[[^\]]+\]\/page\.tsx$/.test(f));
    expect(dynamicPages.length).toBeGreaterThanOrEqual(5);
    for (const f of dynamicPages) {
      const src = fs.readFileSync(path.join(FRONTEND, f), "utf-8");
      expect(src, `${f} lacks generateStaticParams`).toMatch(/export\s+(async\s+)?function\s+generateStaticParams/);
    }
  });

  it("links the relocated root pages only via sitePath (they are 404s on the webspace)", () => {
    // lib/sitePaths.ts: /imprint, /privacy, /enquiry live under /trends in the export.
    const tree = [...surviving, ...walk(path.join(FRONTEND, "src", "components")).map((f) =>
      path.relative(FRONTEND, f).split(path.sep).join("/"))];
    const offenders = tree.filter((f) => {
      if (!/\.tsx?$/.test(f) || /\.test\.tsx?$/.test(f)) return false;
      const src = fs.readFileSync(path.join(FRONTEND, f), "utf-8");
      return /href=["'`]\/(imprint|privacy|enquiry)["'`]/.test(src);
    });
    expect(offenders).toEqual([]);
  });

  it("keeps only force-static GET route handlers (API routes cannot be exported)", () => {
    // The search index is the one handler the export builds — a static
    // file like the sitemap. Anything request-time (POST, dynamic) must
    // stay under src/app/api/ and out of the export.
    const handlers = surviving.filter((f) => /\/route\.tsx?$/.test(f));
    expect(handlers).toEqual(["src/app/trends/index.json/route.ts"]);
    for (const f of handlers) {
      const src = fs.readFileSync(path.join(FRONTEND, f), "utf-8");
      expect(src, `${f} lacks force-static`).toMatch(/export\s+const\s+dynamic\s*=\s*["']force-static["']/);
      expect(src, `${f} exports a non-GET method`).not.toMatch(
        /export\s+(async\s+)?function\s+(POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b/
      );
    }
  });

  it("has no literal force-dynamic left (use `await dynamicUnlessStatic()` instead)", () => {
    const offenders = surviving.filter((f) => {
      if (!/\.(ts|tsx)$/.test(f)) return false;
      const src = fs.readFileSync(path.join(FRONTEND, f), "utf-8");
      return /export\s+const\s+dynamic\s*=\s*["']force-dynamic["']/.test(src);
    });
    expect(offenders).toEqual([]);
  });

  it("metadata route handlers are force-static (the export requires the literal)", () => {
    for (const f of ["src/app/trends/sitemap.ts", "src/app/robots.ts", "src/app/icon.tsx", "src/app/opengraph-image.tsx"]) {
      const src = fs.readFileSync(path.join(FRONTEND, f), "utf-8");
      expect(src, `${f} lacks force-static`).toMatch(/export\s+const\s+dynamic\s*=\s*["']force-static["']/);
    }
  });

  it("no surviving page references the Proxy-only block list at build time", () => {
    // proxy.ts is gone in the export; nothing else may import it.
    const importers = surviving.filter((f) => {
      if (!/\.(ts|tsx)$/.test(f)) return false;
      return /from\s+["']@\/proxy["']/.test(fs.readFileSync(path.join(FRONTEND, f), "utf-8"));
    });
    expect(importers).toEqual([]);
  });
});
