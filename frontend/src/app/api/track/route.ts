import { NextRequest, NextResponse } from "next/server";
import { q, q1 } from "@/lib/pg";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const { trend_id, event } = await request.json();

    if (!trend_id || !event) {
      return NextResponse.json({ error: "Missing fields" }, { status: 400 });
    }

    const validEvents = ["page_view", "share"];
    if (!validEvents.includes(event)) {
      return NextResponse.json({ error: "Invalid event" }, { status: 400 });
    }

    const existing = await q1<{ id: number }>(
      "SELECT id FROM trend_metrics WHERE trend_id = $1",
      [trend_id]
    );

    if (!existing) {
      await q(
        "INSERT INTO trend_metrics (trend_id, page_views, shares, updated_at) VALUES ($1, $2, $3, NOW())",
        [trend_id, event === "page_view" ? 1 : 0, event === "share" ? 1 : 0]
      );
    } else {
      const column = event === "page_view" ? "page_views" : "shares";
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
