import { NextRequest, NextResponse } from "next/server";
import Database from "better-sqlite3";
import path from "path";

export const dynamic = "force-dynamic";

const DB_PATH = process.env.DATABASE_PATH
  || path.join(process.cwd(), "..", "data", "catandary.db");

// GET — fetch latest newsletter edition (or specific week)
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const year = searchParams.get("year");
    const week = searchParams.get("week");
    const listOnly = searchParams.get("list") === "true";

    const db = new Database(DB_PATH, { readonly: true });
    try {
      // Check if table exists
      const tableExists = db
        .prepare(
          "SELECT name FROM sqlite_master WHERE type='table' AND name='newsletter_editions'"
        )
        .get();

      if (!tableExists) {
        return NextResponse.json({ edition: null, archive: [] });
      }

      // Archive listing
      if (listOnly) {
        const editions = db
          .prepare(
            "SELECT id, year, week, total_signals, created_at FROM newsletter_editions ORDER BY year DESC, week DESC LIMIT 24"
          )
          .all();
        return NextResponse.json({ archive: editions });
      }

      // Specific edition or latest
      let row;
      if (year && week) {
        row = db
          .prepare(
            "SELECT * FROM newsletter_editions WHERE year = ? AND week = ? LIMIT 1"
          )
          .get(Number(year), Number(week));
      } else {
        row = db
          .prepare(
            "SELECT * FROM newsletter_editions ORDER BY year DESC, week DESC LIMIT 1"
          )
          .get();
      }

      if (!row) {
        return NextResponse.json({ edition: null });
      }

      // Parse JSON fields
      const edition = row as Record<string, unknown>;
      for (const field of [
        "vertical_summaries",
        "mega_trend_radar",
        "trend_refs",
      ]) {
        if (edition[field] && typeof edition[field] === "string") {
          try {
            edition[field] = JSON.parse(edition[field] as string);
          } catch {
            // keep as string
          }
        }
      }

      return NextResponse.json({ edition });
    } finally {
      db.close();
    }
  } catch (error) {
    console.error("Newsletter GET error:", error);
    return NextResponse.json(
      { error: "Failed to load newsletter" },
      { status: 500 }
    );
  }
}

// POST — newsletter signup (unchanged)
export async function POST(request: NextRequest) {
  try {
    const { email } = await request.json();

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return NextResponse.json(
        { error: "Bitte gib eine gültige Email-Adresse ein." },
        { status: 400 }
      );
    }

    const db = new Database(DB_PATH);
    try {
      // Ensure table exists
      db.exec(`
        CREATE TABLE IF NOT EXISTS newsletter_subscribers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email TEXT UNIQUE NOT NULL,
          verticals TEXT DEFAULT '[]',
          confirmed INTEGER DEFAULT 0,
          subscribed_at TEXT DEFAULT (datetime('now')),
          unsubscribed_at TEXT
        )
      `);

      const existing = db
        .prepare("SELECT id, unsubscribed_at FROM newsletter_subscribers WHERE email = ?")
        .get(email) as { id: number; unsubscribed_at: string | null } | undefined;

      if (existing) {
        if (existing.unsubscribed_at) {
          db.prepare(
            "UPDATE newsletter_subscribers SET unsubscribed_at = NULL, subscribed_at = datetime('now') WHERE id = ?"
          ).run(existing.id);
          return NextResponse.json({ message: "Willkommen zurück! Du bist wieder angemeldet." });
        }
        return NextResponse.json({ message: "Du bist bereits angemeldet." });
      }

      db.prepare("INSERT INTO newsletter_subscribers (email) VALUES (?)").run(email);
      return NextResponse.json({ message: "Erfolgreich angemeldet! Du erhältst bald die ersten Trends." });
    } finally {
      db.close();
    }
  } catch (error) {
    console.error("Newsletter signup error:", error);
    return NextResponse.json(
      { error: "Ein Fehler ist aufgetreten. Bitte versuche es erneut." },
      { status: 500 }
    );
  }
}
