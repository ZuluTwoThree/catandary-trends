import { describe, it, expect } from "vitest";
import { archiveUrl } from "./deadLinks";

describe("archiveUrl", () => {
  it("builds the wayback closest-snapshot shortcut", () => {
    expect(archiveUrl("https://example.com/a")).toBe(
      "https://web.archive.org/web/2/https%3A%2F%2Fexample.com%2Fa"
    );
  });

  it("percent-encodes a query string", () => {
    expect(archiveUrl("https://example.com/a?x=1&y=2")).toBe(
      "https://web.archive.org/web/2/https%3A%2F%2Fexample.com%2Fa%3Fx%3D1%26y%3D2"
    );
  });

  it("percent-encodes a fragment so it cannot hijack the outer URL", () => {
    const url = archiveUrl("https://example.com/a#section");
    expect(url).toBe(
      "https://web.archive.org/web/2/https%3A%2F%2Fexample.com%2Fa%23section"
    );
    // no literal '#' left over — it must not become a fragment of the
    // web.archive.org URL itself (which would strip it before the request).
    expect(url.split("#").length).toBe(1);
  });

  it("percent-encodes spaces", () => {
    expect(archiveUrl("https://example.com/a b")).toContain("%20");
  });
});
