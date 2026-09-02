import { describe, it, expect, afterEach } from "vitest";
import { isSameOrigin, allowedHosts, readJsonBody } from "./apiGuards";

function req(headers: Record<string, string>, init: RequestInit = {}): Request {
  return new Request("http://app.local/api/x", { method: "POST", headers, ...init });
}

afterEach(() => {
  delete process.env.PUBLIC_BASE_URL;
});

describe("isSameOrigin", () => {
  it("accepts an Origin matching the Host header", () => {
    expect(isSameOrigin(req({ host: "localhost:3001", origin: "http://localhost:3001" }))).toBe(true);
  });

  it("rejects a cross-site Origin", () => {
    expect(isSameOrigin(req({ host: "localhost:3001", origin: "https://evil.example" }))).toBe(false);
  });

  it("rejects the opaque origin 'null'", () => {
    expect(isSameOrigin(req({ host: "localhost:3001", origin: "null" }))).toBe(false);
  });

  it("accepts the PUBLIC_BASE_URL host even when Host differs (proxy in front)", () => {
    process.env.PUBLIC_BASE_URL = "https://catandary.de";
    expect(isSameOrigin(req({ host: "localhost:3001", origin: "https://catandary.de" }))).toBe(true);
  });

  it("accepts X-Forwarded-Host", () => {
    expect(
      isSameOrigin(req({ host: "localhost:3001", "x-forwarded-host": "catandary.de", origin: "https://catandary.de" }))
    ).toBe(true);
  });

  it("falls back to Referer when Origin is absent", () => {
    expect(isSameOrigin(req({ host: "localhost:3001", referer: "http://localhost:3001/trends/x" }))).toBe(true);
    expect(isSameOrigin(req({ host: "localhost:3001", referer: "https://evil.example/" }))).toBe(false);
  });

  it("does not let a matching Referer rescue a mismatching Origin", () => {
    expect(
      isSameOrigin(req({ host: "localhost:3001", origin: "https://evil.example", referer: "http://localhost:3001/" }))
    ).toBe(false);
  });

  it("fails closed with neither Origin nor Referer", () => {
    expect(isSameOrigin(req({ host: "localhost:3001" }))).toBe(false);
  });

  it("compares hosts case-insensitively and ignores an unparsable PUBLIC_BASE_URL", () => {
    process.env.PUBLIC_BASE_URL = "not a url";
    expect(allowedHosts(req({ host: "Localhost:3001" }))).toEqual(new Set(["localhost:3001"]));
    expect(isSameOrigin(req({ host: "Localhost:3001", origin: "http://LOCALHOST:3001" }))).toBe(true);
  });
});

describe("readJsonBody", () => {
  it("parses a small JSON object", async () => {
    const r = await readJsonBody(req({}, { body: JSON.stringify({ a: 1 }) }), 1024);
    expect(r).toEqual({ ok: true, value: { a: 1 } });
  });

  it("rejects an oversize declared Content-Length with 413 without reading", async () => {
    const r = await readJsonBody(req({ "content-length": "5000" }, { body: "{}" }), 1024);
    expect(r).toEqual({ ok: false, status: 413, error: "payload too large" });
  });

  it("rejects an oversize streamed body with 413", async () => {
    const big = JSON.stringify({ email: "x".repeat(5000) });
    const r = await readJsonBody(req({}, { body: big }), 1024);
    expect(r).toEqual({ ok: false, status: 413, error: "payload too large" });
  });

  it("rejects malformed JSON and non-object JSON with 400", async () => {
    expect(await readJsonBody(req({}, { body: "{nope" }), 1024)).toMatchObject({ ok: false, status: 400 });
    expect(await readJsonBody(req({}, { body: "[1,2]" }), 1024)).toMatchObject({ ok: false, status: 400 });
    expect(await readJsonBody(req({}, { body: "null" }), 1024)).toMatchObject({ ok: false, status: 400 });
    expect(await readJsonBody(req({}, { body: '"str"' }), 1024)).toMatchObject({ ok: false, status: 400 });
  });

  it("treats an empty body as bad request", async () => {
    expect(await readJsonBody(req({}), 1024)).toMatchObject({ ok: false, status: 400 });
  });
});
