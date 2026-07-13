import { NextResponse } from "next/server";
import { AUTH_ENABLED, clearSessionCookie } from "@/lib/auth";

export const dynamic = "force-dynamic";

/** POST /api/auth/logout — clear the session cookie. */
export async function POST(request: Request) {
  const base = process.env.PUBLIC_BASE_URL || new URL(request.url).origin;
  if (AUTH_ENABLED) await clearSessionCookie();
  return NextResponse.json({ ok: true, redirect: `${base}/trends` });
}
