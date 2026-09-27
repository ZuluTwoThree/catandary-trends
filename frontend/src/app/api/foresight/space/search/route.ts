import { NextResponse } from "next/server";
import { canReview } from "@/lib/review-access";
import { searchSpace } from "@/lib/signalSpace";

export const dynamic = "force-dynamic";

/** GET /api/foresight/space/search?run=<id>&q=<terms> — indices of the cloud's matching points. */
export async function GET(request: Request) {
  if (!canReview()) return new Response("Not found", { status: 404 });
  const url = new URL(request.url);
  const run = Number(url.searchParams.get("run"));
  const query = (url.searchParams.get("q") ?? "").trim();
  if (!Number.isInteger(run) || run <= 0) return NextResponse.json({ error: "bad run" }, { status: 400 });
  if (query.length < 2 || query.length > 120) {
    return NextResponse.json({ error: "query must be 2–120 characters" }, { status: 400 });
  }
  const res = await searchSpace(run, query);
  if (!res) return NextResponse.json({ error: "run not found" }, { status: 404 });
  return NextResponse.json(res);
}
