import { NextResponse } from "next/server";
import { AUTH_ENABLED, createMagicToken, sendMagicLink } from "@/lib/auth";

export const dynamic = "force-dynamic";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/**
 * POST /api/auth/request  { email, newsletter?: boolean }
 * Creates a magic token and emails the sign-in link. Always returns the same
 * ok:true (no account enumeration). In dev/console transport the link is also
 * returned so the flow is testable before DNS verification.
 */
export async function POST(request: Request) {
  if (!AUTH_ENABLED) {
    return NextResponse.json({ error: "auth disabled" }, { status: 404 });
  }
  let body: { email?: string; newsletter?: boolean };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "bad request" }, { status: 400 });
  }
  const email = (body.email || "").toLowerCase().trim();
  if (!EMAIL_RE.test(email)) {
    return NextResponse.json({ error: "invalid email" }, { status: 400 });
  }
  const raw = await createMagicToken(email, Boolean(body.newsletter));
  const link = await sendMagicLink(email, raw);

  const devLink =
    (process.env.EMAIL_TRANSPORT || "console") === "console" ? link : undefined;
  return NextResponse.json({ ok: true, ...(devLink ? { devLink } : {}) });
}
