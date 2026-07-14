import crypto from "crypto";

/**
 * One-click unsubscribe token — HMAC(email, AUTH_SECRET), matching
 * pipeline/newsletter_sender.unsubscribe_token so links from sent newsletters
 * verify here. Constant-time compare.
 */
export function unsubscribeToken(email: string): string {
  const secret = process.env.AUTH_SECRET || "";
  return crypto
    .createHmac("sha256", secret)
    .update(email.toLowerCase())
    .digest("hex")
    .slice(0, 32);
}

export function verifyUnsubscribe(email: string, token: string): boolean {
  if (!email || !token) return false;
  const expected = unsubscribeToken(email);
  if (token.length !== expected.length) return false;
  return crypto.timingSafeEqual(Buffer.from(token), Buffer.from(expected));
}
