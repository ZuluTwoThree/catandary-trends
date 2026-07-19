import { NextResponse } from "next/server";
import {
  AUTH_ENABLED,
  assertAuthConfigured,
  createMagicToken,
  isProduction,
  sendMagicLink,
} from "@/lib/auth";
import { rateLimit, clientIp } from "@/lib/rateLimit";

export const dynamic = "force-dynamic";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Abuse limits: many-from-one-IP and repeated-per-address are both bounded, and
// the rate-limiter caps its own key count so flooding distinct emails/IPs cannot
// grow memory without bound.
const IP_LIMIT = 10; // magic-link requests per IP per window
const IP_WINDOW_MS = 60_000;
const EMAIL_LIMIT = 4; // per address per hour
const EMAIL_WINDOW_MS = 3_600_000;

/**
 * POST /api/auth/request  { email, newsletter?: boolean }
 * Creates a magic token and emails the sign-in link. Always returns the same
 * ok:true for any syntactically valid email (no account enumeration). The link
 * is only ever echoed back (devLink) in non-production console transport.
 */
export async function POST(request: Request) {
  if (!AUTH_ENABLED) {
    return NextResponse.json({ error: "auth disabled" }, { status: 404 });
  }
  // Fail loud (not silently insecure) if prod auth is misconfigured.
  try {
    assertAuthConfigured();
  } catch (e) {
    console.error("auth misconfigured:", e);
    return NextResponse.json({ error: "auth temporarily unavailable" }, { status: 503 });
  }

  let body: { email?: string; newsletter?: boolean };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "bad request" }, { status: 400 });
  }
  const email = (body.email || "").toLowerCase().trim();
  if (!EMAIL_RE.test(email) || email.length > 254) {
    return NextResponse.json({ error: "invalid email" }, { status: 400 });
  }

  // Rate limit per IP and per email (same 429 regardless of account existence).
  const ip = clientIp(request);
  if (!rateLimit(`auth:ip:${ip}`, IP_LIMIT, IP_WINDOW_MS)) {
    return NextResponse.json({ error: "too many requests" }, { status: 429, headers: { "retry-after": "60" } });
  }
  if (!rateLimit(`auth:email:${email}`, EMAIL_LIMIT, EMAIL_WINDOW_MS)) {
    return NextResponse.json({ error: "too many requests" }, { status: 429, headers: { "retry-after": "300" } });
  }

  const raw = await createMagicToken(email, Boolean(body.newsletter));

  let link: string;
  try {
    link = await sendMagicLink(email, raw);
  } catch (e) {
    // A real send failure (Resend non-2xx / network) must NOT report success.
    console.error("magic link send failed:", e);
    return NextResponse.json({ error: "could not send sign-in email" }, { status: 502 });
  }

  // devLink is exposed ONLY outside production, and only for the console transport
  // (which itself is forbidden in production by assertAuthConfigured).
  const devLink =
    !isProduction() && (process.env.EMAIL_TRANSPORT || "console") === "console" ? link : undefined;
  return NextResponse.json({ ok: true, ...(devLink ? { devLink } : {}) });
}
