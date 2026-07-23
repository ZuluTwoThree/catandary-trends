import crypto from "crypto";
import { cookies } from "next/headers";
import { q, q1, withTransaction } from "./pg";

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
const COOKIE = "cat_session";
const SESSION_DAYS = 30;
const TOKEN_TTL_MIN = 15;
/** Minimum AUTH_SECRET length treated as safe for HMAC session signing. */
const MIN_SECRET_LEN = 16;

/** production build (read at call time so tests can toggle it). */
export function isProduction(): boolean {
  return process.env.NODE_ENV === "production";
}

/**
 * A usable session-signing secret, or "" if there is none strong enough. Read at
 * call time (not a module const) so it honours env changes and so every session
 * path — minting AND verifying — applies the same gate. In production a set-but-
 * weak secret (< 16 chars) is treated as NO secret: forgeable sessions are as bad
 * as unsigned ones, so we fail closed rather than trust a weak key.
 */
function sessionSecret(): string {
  const s = process.env.AUTH_SECRET || "";
  if (isProduction() && s.length < MIN_SECRET_LEN) return "";
  return s;
}

/**
 * Fail loud when auth is enabled in production but misconfigured, rather than
 * running silently insecure (empty HMAC secret; a 'console' transport that only
 * logs the link so nobody can sign in AND would leak it; missing Resend key).
 * All checks read env at call time. Throws on any problem.
 */
export function assertAuthConfigured(): void {
  if (process.env.AUTH_ENABLED !== "1" || !isProduction()) return;
  const problems: string[] = [];
  if (!process.env.AUTH_SECRET || process.env.AUTH_SECRET.length < 16)
    problems.push("AUTH_SECRET missing or shorter than 16 chars");
  if ((process.env.EMAIL_TRANSPORT || "console") !== "resend")
    problems.push("EMAIL_TRANSPORT must be 'resend' in production (console leaks/undeliverable)");
  if (!process.env.RESEND_API_KEY) problems.push("RESEND_API_KEY missing");
  if (problems.length) throw new Error(`auth misconfigured for production: ${problems.join("; ")}`);
}

export type Tier = "free" | "starter" | "pro" | "superpro";

/**
 * Guard for post-signin redirect targets carried through the magic-link flow:
 * only same-origin absolute paths, no protocol-relative ("//host") escapes.
 */
export function isSafeInternalPath(path: string | undefined | null): path is string {
  return typeof path === "string" && path.startsWith("/") && !path.startsWith("//");
}

export interface SessionUser {
  id: number;
  email: string;
  tier: Tier;
}

function b64url(buf: Buffer): string {
  return buf.toString("base64url");
}

function hmac(payload: string, secret: string): string {
  return b64url(crypto.createHmac("sha256", secret).update(payload).digest());
}

/** Build a signed session cookie value for a user id. Throws when there is no
 *  strong-enough secret, so we never mint a session a forger could reproduce. */
export function makeSessionValue(uid: number): string {
  const secret = sessionSecret();
  if (!secret) throw new Error("cannot mint session: AUTH_SECRET missing or too weak");
  const exp = Date.now() + SESSION_DAYS * 864e5;
  const payload = b64url(Buffer.from(JSON.stringify({ uid, exp })));
  return `${payload}.${hmac(payload, secret)}`;
}

function verifySessionValue(value: string | undefined): number | null {
  const secret = sessionSecret();
  if (!value || !secret) return null; // no strong secret ⇒ no cookie is trusted (fail closed)
  const [payload, sig] = value.split(".");
  if (!payload || !sig) return null;
  // constant-time compare
  const expected = hmac(payload, secret);
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
  // Atomic compare-and-set: the UPDATE ... WHERE used=FALSE ... RETURNING is a
  // single statement, so of two concurrent requests only ONE flips the row and
  // gets a result — the other sees no row and returns null. (The old SELECT-then-
  // UPDATE let both pass the check and consume the same token twice.)
  //
  // Marking the token used AND upserting its user MUST be one transaction: if the
  // upsert failed after a bare UPDATE committed, the token would be spent with no
  // user behind it, permanently locking that address out. On any failure we roll
  // back, leaving the token unused so the link stays valid.
  let outcome: { id: number; email: string; optIn: boolean } | null = null;
  try {
    outcome = await withTransaction(async (client) => {
      const tok = await client.query(
        "UPDATE magic_tokens SET used = TRUE " +
          "WHERE token_hash = $1 AND used = FALSE AND expires_at > NOW() " +
          "RETURNING email, newsletter_opt_in",
        [hashToken(raw)]
      );
      if (tok.rowCount === 0) return null; // invalid/expired/used → commit (no-op), null
      const email = tok.rows[0].email as string;
      const optIn = tok.rows[0].newsletter_opt_in as boolean;
      const usr = await client.query(
        "INSERT INTO app_users (email, newsletter_opt_in, last_login_at) " +
          "VALUES ($1, $2, NOW()) " +
          "ON CONFLICT (email) DO UPDATE SET last_login_at = NOW(), " +
          "  newsletter_opt_in = app_users.newsletter_opt_in OR EXCLUDED.newsletter_opt_in " +
          "RETURNING id",
        [email, optIn]
      );
      const id = usr.rows[0]?.id as number | undefined;
      if (id == null) throw new Error("app_users upsert returned no id"); // → ROLLBACK, token stays unused
      return { id, email, optIn };
    });
  } catch (e) {
    console.error("consumeMagicToken transaction failed (rolled back):", e);
    return null;
  }
  if (!outcome) return null;
  // Best-effort, non-transactional: a newsletter mirror hiccup must not undo a
  // successful sign-in (the token is already legitimately consumed).
  if (outcome.optIn) await syncNewsletterSubscriber(outcome.email);
  return outcome.id;
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
export async function sendMagicLink(
  email: string,
  raw: string,
  opts?: { next?: string; base?: string }
): Promise<string> {
  // Prefer the explicit PUBLIC_BASE_URL, then the caller's request origin —
  // the old hardcoded :3004 fallback produced dead links (ARCH-19).
  const base = process.env.PUBLIC_BASE_URL || opts?.base || "http://localhost:3001";
  const next = isSafeInternalPath(opts?.next) ? opts?.next : undefined;
  const link =
    `${base}/api/auth/callback?token=${encodeURIComponent(raw)}` +
    (next ? `&next=${encodeURIComponent(next)}` : "");
  const transport = process.env.EMAIL_TRANSPORT || "console";

  if (transport === "resend") {
    if (!process.env.RESEND_API_KEY) {
      throw new Error("RESEND_API_KEY missing — cannot send magic link");
    }
    let res: Response;
    try {
      res = await fetch("https://api.resend.com/emails", {
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
      });
    } catch (e) {
      // Network/transport failure — surface it; do NOT report success.
      throw new Error(`resend request failed: ${e instanceof Error ? e.message : e}`);
    }
    if (!res.ok) {
      // Non-2xx (e.g. 422 invalid, 401 bad key, 429) — fetch does not throw on
      // these, so an unchecked call would silently "succeed". Surface it.
      const detail = await res.text().catch(() => "");
      throw new Error(`resend returned ${res.status}: ${detail.slice(0, 200)}`);
    }
  } else {
    console.log(`[auth] magic link for ${email}: ${link}`);
  }
  return link;
}
