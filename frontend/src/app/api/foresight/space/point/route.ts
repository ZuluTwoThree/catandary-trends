import { NextResponse } from "next/server";
import { canReview } from "@/lib/review-access";
import { getSpacePoint } from "@/lib/signalSpace";

export const dynamic = "force-dynamic";

/** GET /api/foresight/space/point?id=<trend id> — title, source and link for a clicked point. */
export async function GET(request: Request) {
  if (!canReview()) return new Response("Not found", { status: 404 });
  const id = Number(new URL(request.url).searchParams.get("id"));
  if (!Number.isInteger(id) || id <= 0) return NextResponse.json({ error: "bad id" }, { status: 400 });
  const p = await getSpacePoint(id);
  if (!p) return NextResponse.json({ error: "not found" }, { status: 404 });
  return NextResponse.json(p);
}
