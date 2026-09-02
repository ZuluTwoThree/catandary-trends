import crypto from "crypto";

/**
 * One-click unsubscribe token — HMAC(email, AUTH_SECRET), matching
 * pipeline/newsletter_sender.unsubscribe_token so links from sent newsletters
 * verify here. Constant-time compare.
 *
 * Fail closed (security review 2026-09-02, E-7): with AUTH_SECRET missing the
 * old code computed HMACs over an empty key, so anyone could derive a valid
 * token for any address. Now a missing or short secret makes token creation
 * throw and verification return false — nobody gets unsubscribed by a link
 * the server could not have signed.
 */
const MIN_SECRET_LEN = 16; // same bar as lib/auth.ts
const TOKEN_LEN = 32; // hex chars — the sender truncates the digest to 32
const TOKEN_RE = /^[0-9a-f]{32}$/;
const MAX_EMAIL_LEN = 254;

function secret(): string {
  const s = process.env.AUTH_SECRET || "";
  if (s.length < MIN_SECRET_LEN) {
    throw new Error("AUTH_SECRET missing or shorter than 16 chars — unsubscribe tokens cannot be signed");
  }
  return s;
}

/** Whether the server is able to sign/verify unsubscribe tokens at all. */
export function unsubscribeConfigured(): boolean {
  return (process.env.AUTH_SECRET || "").length >= MIN_SECRET_LEN;
}

export function unsubscribeToken(email: string): string {
  return crypto
    .createHmac("sha256", secret())
    .update(email.toLowerCase())
    .digest("hex")
    .slice(0, TOKEN_LEN);
}

export function verifyUnsubscribe(email: string, token: string): boolean {
  if (!email || !token) return false;
  if (email.length > MAX_EMAIL_LEN || !email.includes("@")) return false;
  if (!TOKEN_RE.test(token)) return false;
  let expected: string;
  try {
    expected = unsubscribeToken(email);
  } catch {
    return false; // unconfigured server → nothing verifies
  }
  return crypto.timingSafeEqual(Buffer.from(token), Buffer.from(expected));
}
