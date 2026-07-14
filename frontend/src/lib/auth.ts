import crypto from "crypto";
import { cookies } from "next/headers";
import { q, q1 } from "./pg";

/**
 * Lightweight, dependency-free magic-link auth (Epic W2.1, issue #17).
 *
 * Chosen over NextAuth v5-beta deliberately: on bleeding-edge Next 16 a beta
 * auth library is a night-time build risk, and the alpha only needs an
 * email-gate + tier gating. This is ~a page of transparent code with zero new
 * deps — Node crypto for signing, Resend via fetch for delivery.
 *
 * Session = a signed httpOnly cookie {uid, exp} (HMAC-SHA256, AUTH_SECRET).
 * The tier is always re-read from app_users so upgrades take effect at once.
 *
 * Everything is gated on AUTH_ENABLED=1 — unset (prod today) means no auth
 * surface at all, so the deployed site is unaffected until we flip it.
 */

export const AUTH_ENABLED = process.env.AUTH_ENABLED === "1";
const SECRET = process.env.AUTH_SECRET || "";
const COOKIE = "cat_session";
const SESSION_DAYS = 30;
const TOKEN_TTL_MIN = 15;

export type Tier = "free" | "starter" | "pro" | "superpro";

export interface SessionUser {
  id: number;
  email: string;
  tier: Tier;
}

function b64url(buf: Buffer): string {
  return buf.toString("base64url");
}

function sign(payload: string): string {
  return b64url(crypto.createHmac("sha256", SECRET).update(payload).digest());
}

/** Build a signed session cookie value for a user id. */
export function makeSessionValue(uid: number): string {
  const exp = Date.now() + SESSION_DAYS * 864e5;
  const payload = b64url(Buffer.from(JSON.stringify({ uid, exp })));
  return `${payload}.${sign(payload)}`;
}

function verifySessionValue(value: string | undefined): number | null {
  if (!value || !SECRET) return null;
  const [payload, sig] = value.split(".");
  if (!payload || !sig) return null;
  // constant-time compare
  const expected = sign(payload);
  if (
    sig.length !== expected.length ||
    !crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected))
  )
    return null;
  try {
    const { uid, exp } = JSON.parse(Buffer.from(payload, "base64url").toString());
    if (typeof uid !== "number" || typeof exp !== "number" || Date.now() > exp)
      return null;
    return uid;
  } catch {
    return null;
  }
}

/** Current logged-in user (fresh tier from DB), or null. */
export async function getSession(): Promise<SessionUser | null> {
  if (!AUTH_ENABLED) return null;
  const jar = await cookies();
  const uid = verifySessionValue(jar.get(COOKIE)?.value);
  if (uid == null) return null;
  const user = await q1<{ id: number; email: string; tier: string }>(
    "SELECT id, email, tier FROM app_users WHERE id = $1",
    [uid]
  );
  if (!user) return null;
  return { id: user.id, email: user.email, tier: (user.tier as Tier) || "free" };
}

export async function setSessionCookie(uid: number): Promise<void> {
  const jar = await cookies();
  jar.set(COOKIE, makeSessionValue(uid), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_DAYS * 864e5 / 1000,
  });
}

export async function clearSessionCookie(): Promise<void> {
  const jar = await cookies();
  jar.delete(COOKIE);
}

/* ------------------------------ magic tokens ------------------------------ */

function hashToken(raw: string): string {
  return crypto.createHash("sha256").update(raw).digest("hex");
}

/** Create a single-use magic token, store its hash, return the raw token. */
export async function createMagicToken(
  email: string,
  newsletterOptIn: boolean
): Promise<string> {
  const raw = crypto.randomBytes(32).toString("base64url");
  // Compute expiry in SQL (NOW() + interval) so it shares the same clock as the
  // `expires_at < NOW()` check — the column is TIMESTAMP WITHOUT TIME ZONE and a
  // JS toISOString() (UTC) would be read as local, expiring tokens immediately.
  await q(
    "INSERT INTO magic_tokens (token_hash, email, expires_at, newsletter_opt_in) " +
      `VALUES ($1, $2, NOW() + INTERVAL '${TOKEN_TTL_MIN} minutes', $3)`,
    [hashToken(raw), email.toLowerCase().trim(), newsletterOptIn]
  );
  return raw;
}

/**
 * Consume a magic token: validate (exists, unused, unexpired), mark used,
 * upsert the app_user, apply newsletter opt-in, return the user id. Null on
 * any failure (invalid/expired/used).
 */
export async function consumeMagicToken(raw: string): Promise<number | null> {
  const row = await q1<{
    id: number;
    email: string;
    used: boolean;
    expired: boolean;
    newsletter_opt_in: boolean;
  }>(
    "SELECT id, email, used, (expires_at < NOW()) AS expired, newsletter_opt_in " +
      "FROM magic_tokens WHERE token_hash = $1",
    [hashToken(raw)]
  );
  if (!row || row.used || row.expired) return null;
  await q("UPDATE magic_tokens SET used = TRUE WHERE id = $1", [row.id]);

  const optIn = row.newsletter_opt_in;
  const user = await q1<{ id: number }>(
    "INSERT INTO app_users (email, newsletter_opt_in, last_login_at) " +
      "VALUES ($1, $2, NOW()) " +
      "ON CONFLICT (email) DO UPDATE SET last_login_at = NOW(), " +
      "  newsletter_opt_in = app_users.newsletter_opt_in OR EXCLUDED.newsletter_opt_in " +
      "RETURNING id",
    [row.email, optIn]
  );
  if (optIn) await syncNewsletterSubscriber(row.email);
  return user?.id ?? null;
}

/** Mirror an opt-in into the existing newsletter_subscribers table if present. */
async function syncNewsletterSubscriber(email: string): Promise<void> {
  try {
    await q(
      "INSERT INTO newsletter_subscribers (email, confirmed, subscribed_at) " +
        "VALUES ($1, TRUE, NOW()) ON CONFLICT (email) DO NOTHING",
      [email]
    );
  } catch {
    // table shape may differ / not exist — non-fatal for auth
  }
}

/* --------------------------------- email --------------------------------- */

/**
 * Send the magic link. Transport is EMAIL_TRANSPORT: 'resend' (real, needs
 * RESEND_API_KEY + a verified domain) or 'console' (logs the link — the
 * night/dev default while DNS is unverified). Returns the link so callers can
 * surface it in dev.
 */
export async function sendMagicLink(email: string, raw: string): Promise<string> {
  const base = process.env.PUBLIC_BASE_URL || "http://localhost:3004";
  const link = `${base}/api/auth/callback?token=${encodeURIComponent(raw)}`;
  const transport = process.env.EMAIL_TRANSPORT || "console";

  if (transport === "resend" && process.env.RESEND_API_KEY) {
    await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: process.env.NEWSLETTER_FROM || "Catandary Trends <trends@catandary.de>",
        to: [email],
        subject: "Your Catandary Trends sign-in link",
        html:
          `<p>Click to sign in to Catandary Trends (valid ${TOKEN_TTL_MIN} minutes):</p>` +
          `<p><a href="${link}">Sign in</a></p>` +
          `<p style="color:#888;font-size:12px">If you didn't request this, ignore this email.</p>`,
      }),
    }).catch((e) => console.error("resend send failed:", e));
  } else {
    console.log(`[auth] magic link for ${email}: ${link}`);
  }
  return link;
}
