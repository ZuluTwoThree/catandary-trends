/**
 * Unsubscribe tokens fail closed (security review 2026-09-02, E-7).
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import crypto from "crypto";
import { unsubscribeToken, verifyUnsubscribe, unsubscribeConfigured } from "./unsubscribe";

const SECRET = "0123456789abcdef0123456789abcdef";

/** Mirror of pipeline/newsletter_sender.unsubscribe_token. */
function pythonSideToken(email: string, secret: string): string {
  return crypto.createHmac("sha256", secret).update(email.toLowerCase()).digest("hex").slice(0, 32);
}

afterEach(() => {
  delete process.env.AUTH_SECRET;
});

describe("with a configured secret", () => {
  beforeEach(() => {
    process.env.AUTH_SECRET = SECRET;
  });

  it("verifies the token the sender puts into the mail (case-insensitive address)", () => {
    const t = pythonSideToken("Person@Example.com", SECRET);
    expect(unsubscribeConfigured()).toBe(true);
    expect(unsubscribeToken("person@example.com")).toBe(t);
    expect(verifyUnsubscribe("Person@Example.com", t)).toBe(true);
    expect(verifyUnsubscribe("person@example.com", t)).toBe(true);
  });

  it("rejects a token for a different address, a tampered token and a malformed one", () => {
    const t = pythonSideToken("a@x.io", SECRET);
    expect(verifyUnsubscribe("b@x.io", t)).toBe(false);
    expect(verifyUnsubscribe("a@x.io", t.slice(0, 31) + (t.endsWith("0") ? "1" : "0"))).toBe(false);
    expect(verifyUnsubscribe("a@x.io", t.toUpperCase())).toBe(false);
    expect(verifyUnsubscribe("a@x.io", t + "0")).toBe(false);
    expect(verifyUnsubscribe("a@x.io", "")).toBe(false);
    expect(verifyUnsubscribe("", t)).toBe(false);
    expect(verifyUnsubscribe("not-an-address", pythonSideToken("not-an-address", SECRET))).toBe(false);
  });
});

describe("without a usable secret (fail closed)", () => {
  it("cannot sign tokens when AUTH_SECRET is unset", () => {
    expect(unsubscribeConfigured()).toBe(false);
    expect(() => unsubscribeToken("a@x.io")).toThrow(/AUTH_SECRET/);
  });

  it("refuses the token an attacker would compute with an empty key", () => {
    const forged = pythonSideToken("victim@x.io", "");
    expect(verifyUnsubscribe("victim@x.io", forged)).toBe(false);
  });

  it("treats a short secret as unconfigured", () => {
    process.env.AUTH_SECRET = "short";
    expect(unsubscribeConfigured()).toBe(false);
    expect(verifyUnsubscribe("a@x.io", pythonSideToken("a@x.io", "short"))).toBe(false);
  });
});
