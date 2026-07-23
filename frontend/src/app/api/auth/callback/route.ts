import { NextResponse } from "next/server";
import {
  AUTH_ENABLED,
  consumeMagicToken,
  isSafeInternalPath,
  setSessionCookie,
} from "@/lib/auth";

export const dynamic = "force-dynamic";

/**
 * GET /api/auth/callback?token=...  — consume the magic token, set the session
 * cookie, redirect into the app. Invalid/expired/used tokens redirect to a
 * friendly error on the sign-in page.
 */
export async function GET(request: Request) {
  const base = process.env.PUBLIC_BASE_URL || new URL(request.url).origin;
  if (!AUTH_ENABLED) {
    return NextResponse.redirect(`${base}/trends`);
  }
  const params = new URL(request.url).searchParams;
  const token = params.get("token") || "";
  const uid = token ? await consumeMagicToken(token) : null;
  if (uid == null) {
    return NextResponse.redirect(`${base}/account/signin?error=link`);
  }
  await setSessionCookie(uid);
  // Optional validated post-signin destination (e.g. back to /trends/pricing
  // when the user was interrupted mid-checkout) — internal paths only.
  const next = params.get("next");
  return NextResponse.redirect(`${base}${isSafeInternalPath(next) ? next : "/account"}`);
}
