import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { AI_CRAWLER_USER_AGENTS, aiCrawlerRegex } from "./aiCrawlers";

const HTACCESS = ["public-export/trends/.htaccess", "public-export/_next/.htaccess"].map((f) =>
  readFileSync(join(process.cwd(), f), "utf8"),
);

describe("AI crawler lock-out", () => {
  it("lists the big four AI crawlers", () => {
    for (const ua of ["GPTBot", "ClaudeBot", "CCBot", "Bytespider", "Google-Extended"]) {
      expect(AI_CRAWLER_USER_AGENTS).toContain(ua);
    }
  });

  it("builds an Apache-safe regex (spaces and dots escaped)", () => {
    const rx = aiCrawlerRegex();
    expect(rx).toContain("Kangaroo\\ Bot");
    expect(rx).not.toMatch(/\(|\)/);
    expect(new RegExp(rx, "i").test("Mozilla/5.0 (compatible; GPTBot/1.2)")).toBe(true);
    expect(new RegExp(rx, "i").test("Mozilla/5.0 (compatible; Googlebot/2.1)")).toBe(false);
  });

  it("keeps both .htaccess files in sync with the list and the TDM header", () => {
    for (const text of HTACCESS) {
      expect(text).toContain('Header always set TDM-Reservation "1"');
      expect(text).toContain(`RewriteCond %{HTTP_USER_AGENT} (${aiCrawlerRegex()}) [NC]`);
      expect(text).toContain("RewriteRule .* - [F,L]");
    }
  });
});
