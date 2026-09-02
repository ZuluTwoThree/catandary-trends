import { NextRequest, NextResponse } from "next/server";
import { q, q1 } from "@/lib/pg";
import { rateLimitInfo, clientIp } from "@/lib/rateLimit";
import { isSameOrigin, readJsonBody } from "@/lib/apiGuards";

export const dynamic = "force-dynamic";

// Signup abuse limits (security review 2026-09-02, E-5): the route used to
// accept any syntactically valid address from anywhere, unbounded — a list-
// pollution lever. Per-IP and per-address windows, same shape as
// api/auth/request. The sender only mails confirmed = TRUE rows, so this is
// about keeping the table clean, not about outbound spam.
const SIGNUP_IP_LIMIT = 5; // sign-ups per IP …
const SIGNUP_IP_WINDOW_MS = 10 * 60_000; // … per 10 minutes
const SIGNUP_EMAIL_LIMIT = 3; // attempts per address …
const SIGNUP_EMAIL_WINDOW_MS = 24 * 3_600_000; // … per day
const MAX_BODY_BYTES = 1024; // {"email":"<254 chars>"} fits with room
const MAX_EMAIL_LEN = 254;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Small positive integer from a query param, or null. */
function intParam(v: string | null): number | null {
  if (v === null) return null;
  const n = Number(v);
  return Number.isInteger(n) && n > 0 && n < 100_000 ? n : null;
}

// GET — fetch latest newsletter edition (or specific week)
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const year = intParam(searchParams.get("year"));
    const week = intParam(searchParams.get("week"));
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
            [year, week]
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
  if (!isSameOrigin(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  const rl = rateLimitInfo(
    `newsletter:ip:${clientIp(request)}`,
    SIGNUP_IP_LIMIT,
    SIGNUP_IP_WINDOW_MS
  );
  if (!rl.ok) {
    return NextResponse.json(
      { error: "Too many sign-ups from here — please try again later." },
      { status: 429, headers: { "retry-after": String(rl.retryAfterSec) } }
    );
  }

  const body = await readJsonBody(request, MAX_BODY_BYTES);
  if (!body.ok) {
    return NextResponse.json(
      { error: body.status === 413 ? "Request too large." : "Please enter a valid email address." },
      { status: body.status }
    );
  }
  const email =
    typeof body.value.email === "string" ? body.value.email.trim().toLowerCase() : "";
  if (!email || email.length > MAX_EMAIL_LEN || !EMAIL_RE.test(email)) {
    return NextResponse.json(
      { error: "Please enter a valid email address." },
      { status: 400 }
    );
  }

  const erl = rateLimitInfo(
    `newsletter:email:${email}`,
    SIGNUP_EMAIL_LIMIT,
    SIGNUP_EMAIL_WINDOW_MS
  );
  if (!erl.ok) {
    return NextResponse.json(
      { error: "Too many attempts for this address — please try again later." },
      { status: 429, headers: { "retry-after": String(erl.retryAfterSec) } }
    );
  }

  try {
    // LOWER() on the column too: rows written before addresses were
    // normalised may still carry mixed case.
    const existing = await q1<{ id: number; unsubscribed_at: string | null }>(
      "SELECT id, unsubscribed_at::text as unsubscribed_at FROM newsletter_subscribers WHERE LOWER(email) = $1",
      [email]
    );

    if (existing) {
      if (existing.unsubscribed_at) {
        await q(
          "UPDATE newsletter_subscribers SET unsubscribed_at = NULL, subscribed_at = NOW() WHERE id = $1",
          [existing.id]
        );
        return NextResponse.json({
          message: "Welcome back — you're subscribed again.",
        });
      }
      return NextResponse.json({ message: "You're already subscribed." });
    }

    await q("INSERT INTO newsletter_subscribers (email) VALUES ($1)", [email]);
    return NextResponse.json({
      message: "You're subscribed — the first briefing lands Monday.",
    });
  } catch (error) {
    console.error("Newsletter signup error:", error);
    return NextResponse.json(
      { error: "Something went wrong. Please try again." },
      { status: 500 }
    );
  }
}
