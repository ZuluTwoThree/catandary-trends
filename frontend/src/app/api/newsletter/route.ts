import { NextRequest, NextResponse } from "next/server";
import { q, q1 } from "@/lib/pg";

export const dynamic = "force-dynamic";

// GET — fetch latest newsletter edition (or specific week)
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const year = searchParams.get("year");
    const week = searchParams.get("week");
    const listOnly = searchParams.get("list") === "true";

    // Check if table exists
    const tableExists = await q1<{ ok: string | null }>(
      "SELECT to_regclass('newsletter_editions')::text as ok"
    );
    if (!tableExists?.ok) {
      return NextResponse.json({ edition: null, archive: [] });
    }

    // Archive listing
    if (listOnly) {
      const editions = await q(
        "SELECT id, year, week, total_signals, created_at::text as created_at " +
          "FROM newsletter_editions ORDER BY year DESC, week DESC LIMIT 24"
      );
      return NextResponse.json({ archive: editions });
    }

    // Specific edition or latest
    const row =
      year && week
        ? await q1(
            "SELECT * FROM newsletter_editions WHERE year = $1 AND week = $2 LIMIT 1",
            [Number(year), Number(week)]
          )
        : await q1(
            "SELECT * FROM newsletter_editions ORDER BY year DESC, week DESC LIMIT 1"
          );

    if (!row) {
      return NextResponse.json({ edition: null });
    }

    // Parse JSON fields (stored as TEXT)
    const edition = row as Record<string, unknown>;
    for (const field of ["vertical_summaries", "mega_trend_radar", "trend_refs"]) {
      if (edition[field] && typeof edition[field] === "string") {
        try {
          edition[field] = JSON.parse(edition[field] as string);
        } catch {
          // keep as string
        }
      }
    }

    return NextResponse.json({ edition });
  } catch (error) {
    console.error("Newsletter GET error:", error);
    return NextResponse.json(
      { error: "Failed to load newsletter" },
      { status: 500 }
    );
  }
}

// POST — newsletter signup
export async function POST(request: NextRequest) {
  try {
    const { email } = await request.json();

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return NextResponse.json(
        { error: "Bitte gib eine gültige Email-Adresse ein." },
        { status: 400 }
      );
    }

    const existing = await q1<{ id: number; unsubscribed_at: string | null }>(
      "SELECT id, unsubscribed_at::text as unsubscribed_at FROM newsletter_subscribers WHERE email = $1",
      [email]
    );

    if (existing) {
      if (existing.unsubscribed_at) {
        await q(
          "UPDATE newsletter_subscribers SET unsubscribed_at = NULL, subscribed_at = NOW() WHERE id = $1",
          [existing.id]
        );
        return NextResponse.json({
          message: "Willkommen zurück! Du bist wieder angemeldet.",
        });
      }
      return NextResponse.json({ message: "Du bist bereits angemeldet." });
    }

    await q("INSERT INTO newsletter_subscribers (email) VALUES ($1)", [email]);
    return NextResponse.json({
      message: "Erfolgreich angemeldet! Du erhältst bald die ersten Trends.",
    });
  } catch (error) {
    console.error("Newsletter signup error:", error);
    return NextResponse.json(
      { error: "Ein Fehler ist aufgetreten. Bitte versuche es erneut." },
      { status: 500 }
    );
  }
}
