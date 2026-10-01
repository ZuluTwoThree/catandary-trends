import { NextResponse } from "next/server";
import { canReview } from "@/lib/review-access";
import { sameOrigin, serviceFetch } from "@/lib/discover";

export const dynamic = "force-dynamic";

/** DELETE /api/foresight/discover/domains/<q_key> — remove a free-term domain and its runs. */
export async function DELETE(request: Request, ctx: { params: Promise<{ key: string }> }) {
  if (!canReview()) return new Response("Not found", { status: 404 });
  if (!sameOrigin(request)) return NextResponse.json({ error: "cross-origin" }, { status: 403 });
  const { key } = await ctx.params;
  if (!/^q_[a-z0-9_]{1,38}$/.test(key)) return NextResponse.json({ error: "bad key" }, { status: 400 });
  const r = await serviceFetch<{ key: string; runs_deleted: number }>(`/domains/${key}/delete`, {
    method: "POST",
    body: {},
  });
  return r.ok ? NextResponse.json(r.data) : NextResponse.json({ error: r.error }, { status: r.status });
}
