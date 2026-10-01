import { NextResponse } from "next/server";
import { canReview } from "@/lib/review-access";
import { sameOrigin, serviceUnitState, switchService } from "@/lib/discover";

export const dynamic = "force-dynamic";

/** GET /api/foresight/discover/service — is the discovery service on? */
export async function GET() {
  if (!canReview()) return new Response("Not found", { status: 404 });
  return NextResponse.json(await serviceUnitState());
}

/** POST /api/foresight/discover/service {on: boolean} — switch it on or off (frees ~4 GB). */
export async function POST(request: Request) {
  if (!canReview()) return new Response("Not found", { status: 404 });
  if (!sameOrigin(request)) return NextResponse.json({ error: "cross-origin" }, { status: 403 });
  const { on } = (await request.json().catch(() => ({}))) as { on?: unknown };
  if (typeof on !== "boolean") return NextResponse.json({ error: "on must be true or false" }, { status: 400 });
  return NextResponse.json(await switchService(on));
}
