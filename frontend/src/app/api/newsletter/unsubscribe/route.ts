import { NextRequest, NextResponse } from "next/server";
import { q } from "@/lib/pg";
import { verifyUnsubscribe } from "@/lib/unsubscribe";
import { rateLimitInfo, clientIp } from "@/lib/rateLimit";
import { readTextBody } from "@/lib/apiGuards";

export const dynamic = "force-dynamic";

/**
 * POST /api/newsletter/unsubscribe — the only path that writes an
 * unsubscribe (security review 2026-09-02, E-7). Two callers:
 *
 *  1. The confirmation form on /trends/newsletter/unsubscribe (a person
 *     clicked the link in the mail, saw the page, pressed the button).
 *     Redirects back to the page with ?done=1 / ?invalid=1.
 *  2. RFC 8058 one-click: the mail provider POSTs
 *     `List-Unsubscribe=One-Click` to the List-Unsubscribe URL. That URL is
 *     the page path (pipeline/newsletter_sender.py builds it), which
 *     src/proxy.ts rewrites here for non-action POSTs. Must answer 2xx
 *     directly — providers do not follow redirects.
 *
 * The HMAC token is the authorisation; there is deliberately no same-origin
 * check (provider POSTs are cross-origin by nature). Mail-scanner GETs on the
 * page no longer unsubscribe anyone — that was the point.
 */
const RL_LIMIT = 20;
const RL_WINDOW_MS = 60_000;
const MAX_BODY_BYTES = 2048;
const PAGE = "/trends/newsletter/unsubscribe";

async function bodyParams(request: NextRequest): Promise<URLSearchParams | null> {
  const text = await readTextBody(request, MAX_BODY_BYTES);
  if (text === null) return null;
  const ct = (request.headers.get("content-type") || "").toLowerCase();
  if (ct.startsWith("application/json")) {
    try {
      const v = JSON.parse(text) as Record<string, unknown>;
      const p = new URLSearchParams();
      for (const k of ["email", "token", "confirm"]) {
        if (typeof v?.[k] === "string") p.set(k, v[k] as string);
      }
      return p;
    } catch {
      return new URLSearchParams();
    }
  }
  return new URLSearchParams(text);
}

export async function POST(request: NextRequest) {
  const rl = rateLimitInfo(`unsubscribe:${clientIp(request)}`, RL_LIMIT, RL_WINDOW_MS);
  if (!rl.ok) {
    return NextResponse.json(
      { error: "Too many requests" },
      { status: 429, headers: { "retry-after": String(rl.retryAfterSec) } }
    );
  }

  const params = await bodyParams(request);
  if (params === null) {
    return NextResponse.json({ error: "payload too large" }, { status: 413 });
  }
  // RFC 8058 one-click carries the identity in the URL and only the marker
  // in the body; our form carries everything in the body. Query wins.
  const query = request.nextUrl.searchParams;
  const email = (query.get("email") ?? params.get("email") ?? "").trim();
  const token = (query.get("token") ?? params.get("token") ?? "").trim();
  const oneClick = params.has("List-Unsubscribe");

  const ok = verifyUnsubscribe(email, token);
  if (!ok) {
    if (oneClick) return NextResponse.json({ error: "invalid token" }, { status: 400 });
    return NextResponse.redirect(new URL(`${PAGE}?invalid=1`, request.nextUrl), 303);
  }

  try {
    await q(
      "UPDATE newsletter_subscribers SET unsubscribed_at = NOW() " +
        "WHERE LOWER(email) = $1 AND unsubscribed_at IS NULL",
      [email.toLowerCase()]
    );
  } catch (error) {
    console.error("Unsubscribe error:", error);
    // A DB hiccup must not strand the person on an error page they cannot act
    // on: report the outcome honestly and let them retry.
    if (oneClick) return NextResponse.json({ error: "temporarily unavailable" }, { status: 503 });
    return NextResponse.redirect(new URL(`${PAGE}?error=1`, request.nextUrl), 303);
  }

  if (oneClick) {
    return new NextResponse("unsubscribed", { status: 200, headers: { "content-type": "text/plain" } });
  }
  return NextResponse.redirect(new URL(`${PAGE}?done=1`, request.nextUrl), 303);
}
