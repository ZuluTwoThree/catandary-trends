import { describe, it, expect } from "vitest";
import { safeHref } from "./safeHref";

describe("safeHref", () => {
  it("passes http(s) URLs, site-relative paths and fragments", () => {
    expect(safeHref("https://example.com/a?b=1#c")).toBe("https://example.com/a?b=1#c");
    expect(safeHref("HTTP://EXAMPLE.COM")).toBe("HTTP://EXAMPLE.COM");
    expect(safeHref("/trends/some-slug")).toBe("/trends/some-slug");
    expect(safeHref("#section")).toBe("#section");
    expect(safeHref("  https://example.com  ")).toBe("https://example.com");
  });

  it("rejects script-bearing and unknown schemes", () => {
    for (const bad of [
      "javascript:alert(1)",
      "JavaScript:alert(1)",
      " javascript:alert(1)",
      "java\nscript:alert(1)",
      "java\tscript:alert(1)",
      "data:text/html;base64,PHNjcmlwdD4=",
      "vbscript:msgbox",
      "file:///etc/passwd",
      "mailto:x@y.z",
      "ftp://host/x",
    ]) {
      expect(safeHref(bad), JSON.stringify(bad)).toBeNull();
    }
  });

  it("rejects protocol-relative URLs, empty and non-string input", () => {
    expect(safeHref("//evil.example/x")).toBeNull();
    expect(safeHref("")).toBeNull();
    expect(safeHref("   ")).toBeNull();
    expect(safeHref(null)).toBeNull();
    expect(safeHref(undefined)).toBeNull();
    expect(safeHref("http://")).toBeNull();
    expect(safeHref("https:///x")).toBeNull();
  });
});
