import { NextRequest, NextResponse } from "next/server";
import { q, q1 } from "@/lib/pg";
import { rateLimitInfo, clientIp } from "@/lib/rateLimit";
import { isSameOrigin, readJsonBody } from "@/lib/apiGuards";

export const dynamic = "force-dynamic";

// Engagement counter feeds the "engagement_desc" sort — an unguarded write
// endpoint is a ranking-manipulation lever (security review 2026-09-02, E-5).
// One page view per article read is the honest rate; 60/min leaves room for
// fast browsing and prefetch noise.
const TRACK_LIMIT = 60;
const TRACK_WINDOW_MS = 60_000;
const MAX_BODY_BYTES = 256; // {"trend_id":2147483647,"event":"page_view"} is 44
const MAX_TREND_ID = 2_147_483_647; // integer column
const VALID_EVENTS = ["page_view", "share"] as const;
type TrackEvent = (typeof VALID_EVENTS)[number];

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  const rl = rateLimitInfo(`track:${clientIp(request)}`, TRACK_LIMIT, TRACK_WINDOW_MS);
  if (!rl.ok) {
    return NextResponse.json(
      { error: "Too many requests" },
      { status: 429, headers: { "retry-after": String(rl.retryAfterSec) } }
    );
  }

  const body = await readJsonBody(request, MAX_BODY_BYTES);
  if (!body.ok) {
    return NextResponse.json({ error: body.error }, { status: body.status });
  }
  const { trend_id, event } = body.value;

  // Reject bad ids here rather than letting pg turn a string into a 500.
  if (
    typeof trend_id !== "number" ||
    !Number.isInteger(trend_id) ||
    trend_id <= 0 ||
    trend_id > MAX_TREND_ID
  ) {
    return NextResponse.json({ error: "Invalid trend_id" }, { status: 400 });
  }
  if (typeof event !== "string" || !(VALID_EVENTS as readonly string[]).includes(event)) {
    return NextResponse.json({ error: "Invalid event" }, { status: 400 });
  }
  const ev = event as TrackEvent;

  try {
    // Only published articles have a public page to be viewed or shared — a
    // draft/rejected/signal id (or one that does not exist) is discarded
    // before any write; this also spares the FK error on an unknown id.
    const known = await q1<{ ok: number }>(
      "SELECT 1 AS ok FROM trends WHERE id = $1 AND status = 'published'",
      [trend_id]
    );
    if (!known) {
      return NextResponse.json({ error: "Unknown trend" }, { status: 404 });
    }

    const existing = await q1<{ id: number }>(
      "SELECT id FROM trend_metrics WHERE trend_id = $1",
      [trend_id]
    );

    if (!existing) {
      await q(
        "INSERT INTO trend_metrics (trend_id, page_views, shares, updated_at) VALUES ($1, $2, $3, NOW())",
        [trend_id, ev === "page_view" ? 1 : 0, ev === "share" ? 1 : 0]
      );
    } else {
      // Column name from a two-value whitelist above, never from the request.
      const column = ev === "page_view" ? "page_views" : "shares";
      await q(
        `UPDATE trend_metrics SET ${column} = COALESCE(${column}, 0) + 1, updated_at = NOW() WHERE trend_id = $1`,
        [trend_id]
      );
    }

    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("Track error:", error);
    return NextResponse.json({ error: "Tracking failed" }, { status: 500 });
  }
}
