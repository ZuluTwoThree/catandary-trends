import { NextRequest, NextResponse } from "next/server";
import Database from "better-sqlite3";
import path from "path";

export const dynamic = "force-dynamic";

const DB_PATH =
  process.env.DATABASE_PATH ||
  path.join(process.cwd(), "..", "data", "catandary.db");

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

    const db = new Database(DB_PATH);
    try {
      const existing = db
        .prepare("SELECT id FROM trend_metrics WHERE trend_id = ?")
        .get(trend_id) as { id: number } | undefined;

      if (!existing) {
        db.prepare(
          "INSERT INTO trend_metrics (trend_id, page_views, shares, updated_at) VALUES (?, ?, ?, datetime('now'))"
        ).run(
          trend_id,
          event === "page_view" ? 1 : 0,
          event === "share" ? 1 : 0
        );
      } else {
        const column = event === "page_view" ? "page_views" : "shares";
        db.prepare(
          `UPDATE trend_metrics SET ${column} = ${column} + 1, updated_at = datetime('now') WHERE trend_id = ?`
        ).run(trend_id);
      }

      return NextResponse.json({ ok: true });
    } finally {
      db.close();
    }
  } catch (error) {
    console.error("Track error:", error);
    return NextResponse.json({ error: "Tracking failed" }, { status: 500 });
  }
}
