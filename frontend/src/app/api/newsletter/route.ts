import { NextRequest, NextResponse } from "next/server";
import Database from "better-sqlite3";
import path from "path";

export const dynamic = "force-dynamic";

const DB_PATH = process.env.DATABASE_PATH
  || path.join(process.cwd(), "..", "data", "catandary.db");

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
          // Re-subscribe
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
