import { NextResponse } from "next/server";
import { canReview } from "@/lib/review-access";
import { searchSpace } from "@/lib/signalSpace";

export const dynamic = "force-dynamic";

/**
 * GET /api/foresight/space/search?run=<id>&q=<terms>[&layout=alt]
 *
 * Body: the packed 16-byte records of every match that has a place in the
 * cloud (decode with lib/spaceCloud.unpack). The counts travel in headers so
 * the body stays a plain binary the browser can hand to the GPU as it is.
 */
export async function GET(request: Request) {
  if (!canReview()) return new Response("Not found", { status: 404 });
  const url = new URL(request.url);
  const run = Number(url.searchParams.get("run"));
  const query = (url.searchParams.get("q") ?? "").trim();
  if (!Number.isInteger(run) || run <= 0) return NextResponse.json({ error: "bad run" }, { status: 400 });
  if (query.length < 2 || query.length > 120) {
    return NextResponse.json({ error: "query must be 2–120 characters" }, { status: 400 });
  }
  const res = await searchSpace(run, query, url.searchParams.get("layout") === "alt");
  if (!res) {
    return NextResponse.json(
      { error: "this run has no placed signals — recompute the cloud" },
      { status: 404 }
    );
  }
  return new Response(new Uint8Array(res.records), {
    headers: {
      "Content-Type": "application/octet-stream",
      "Cache-Control": "private, no-store",
      "X-Matches": String(res.matches),
      "X-Outside": String(res.outside),
      "X-Sources": JSON.stringify(res.bySource),
      "X-Failed": res.failed.join(","),
    },
  });
}
