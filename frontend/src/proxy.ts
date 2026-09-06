import { NextResponse, type NextRequest } from "next/server";
import { isPublicMode, isBlockedInPublicMode } from "@/lib/publicMode";

/**
 * Public-mode route gate (issue #93, Etappe 1).
 *
 * Enforced centrally in Proxy (Next 16's rename of `middleware.ts` — same
 * NextRequest/NextResponse API and matcher config, function renamed from
 * `middleware` to `proxy`) rather than per-page: the blocked surface spans
 * ~20 page and route files (the whole /trends/foresight tree and the two
 * review pages) and a single matcher here avoids touching every one of them
 * individually — cheaper to keep in sync with the "Fällt weg" list in
 * lib/publicMode.ts, and it can't be bypassed by adding a new page under an
 * already-blocked prefix without updating anything here.
 *
 * PUBLIC_MODE unset/0 (today's workstation instance on :3001): this function
 * returns immediately and behaves exactly as if the file didn't exist.
 *
 * API paths get a plain JSON 404 (matches what a fetch() caller expects).
 * Page paths are rewritten to a path nothing in the app tree defines, which
 * lets Next.js's own routing render the branded not-found.tsx (src/app/
 * not-found.tsx) with a real 404 status — Proxy itself cannot call the
 * notFound() helper (that only works in Server Components / Route Handlers).
 */
/**
 * RFC 8058 one-click unsubscribe: the mail's List-Unsubscribe URL is the
 * page path (built by pipeline/newsletter_sender.py) and providers POST
 * `List-Unsubscribe=One-Click` to it. A page cannot read a POST body and
 * — since the E-7 fix — no longer writes on render, so a plain POST to
 * that path is handed to the route that does. Server Actions (marked by
 * the next-action header) are left alone; the page has none today.
 */
const UNSUBSCRIBE_PAGE = "/trends/newsletter/unsubscribe";
const UNSUBSCRIBE_ROUTE = "/api/newsletter/unsubscribe";

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (
    pathname === UNSUBSCRIBE_PAGE &&
    request.method === "POST" &&
    !request.headers.has("next-action")
  ) {
    const url = request.nextUrl.clone();
    url.pathname = UNSUBSCRIBE_ROUTE; // query (email, token) travels along
    return NextResponse.rewrite(url);
  }

  if (!isPublicMode()) return NextResponse.next();

  if (!isBlockedInPublicMode(pathname)) return NextResponse.next();

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const url = request.nextUrl.clone();
  url.pathname = "/public-mode-404";
  return NextResponse.rewrite(url);
}

export const config = {
  matcher: [
    "/trends/foresight/:path*",
    "/trends/review/:path*",
    "/trends/quality-preview/:path*",
    "/trends/dossiers/:path*",
    "/trends/newsletter/review/:path*",
    "/api/foresight/:path*",
    "/trends/newsletter/unsubscribe",
  ],
};
