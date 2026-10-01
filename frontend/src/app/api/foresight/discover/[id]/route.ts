import { NextResponse } from "next/server";
import { canReview } from "@/lib/review-access";
import { sameOrigin, serviceFetch, type DiscoverJob } from "@/lib/discover";

export const dynamic = "force-dynamic";

const ID = /^[0-9a-f]{12}$/;

/** GET /api/foresight/discover/<job> — state, log, preview, result. */
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  if (!canReview()) return new Response("Not found", { status: 404 });
  const { id } = await ctx.params;
  if (!ID.test(id)) return NextResponse.json({ error: "bad id" }, { status: 400 });
  const r = await serviceFetch<DiscoverJob>(`/jobs/${id}`);
  return r.ok ? NextResponse.json(r.data) : NextResponse.json({ error: r.error }, { status: r.status });
}

/** POST /api/foresight/discover/<job> {action: "confirm" | "discard"}. */
export async function POST(request: Request, ctx: { params: Promise<{ id: string }> }) {
  if (!canReview()) return new Response("Not found", { status: 404 });
  if (!sameOrigin(request)) return NextResponse.json({ error: "cross-origin" }, { status: 403 });
  const { id } = await ctx.params;
  if (!ID.test(id)) return NextResponse.json({ error: "bad id" }, { status: 400 });
  const { action } = (await request.json().catch(() => ({}))) as { action?: string };
  if (action !== "confirm" && action !== "discard") {
    return NextResponse.json({ error: "action must be confirm or discard" }, { status: 400 });
  }
  const r = await serviceFetch<DiscoverJob>(`/jobs/${id}/${action}`, { method: "POST", body: {} });
  return r.ok ? NextResponse.json(r.data) : NextResponse.json({ error: r.error }, { status: r.status });
}
