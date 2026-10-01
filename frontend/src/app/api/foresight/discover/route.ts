import { NextResponse } from "next/server";
import { canReview } from "@/lib/review-access";
import { sameOrigin, serviceFetch, type DiscoverJob, type ServiceHealth } from "@/lib/discover";

export const dynamic = "force-dynamic";

/** GET /api/foresight/discover — service health + recent jobs. */
export async function GET() {
  if (!canReview()) return new Response("Not found", { status: 404 });
  const [health, jobs] = await Promise.all([
    serviceFetch<ServiceHealth>("/health"),
    serviceFetch<DiscoverJob[]>("/jobs"),
  ]);
  return NextResponse.json({
    health: health.ok ? health.data : null,
    error: health.ok ? null : health.error,
    jobs: jobs.ok ? jobs.data : [],
  });
}

/** POST /api/foresight/discover {term, also[], window_months} — start a selection. */
export async function POST(request: Request) {
  if (!canReview()) return new Response("Not found", { status: 404 });
  if (!sameOrigin(request)) return NextResponse.json({ error: "cross-origin" }, { status: 403 });
  const body = (await request.json().catch(() => ({}))) as {
    term?: unknown;
    also?: unknown;
    window_months?: unknown;
  };
  const term = typeof body.term === "string" ? body.term.trim() : "";
  if (!term || term.length > 80) {
    return NextResponse.json({ error: "Enter a term of 1-80 characters." }, { status: 400 });
  }
  const also = Array.isArray(body.also)
    ? body.also.filter((a): a is string => typeof a === "string" && a.trim().length > 0).slice(0, 6)
    : [];
  const window = Number(body.window_months) || 12;
  const r = await serviceFetch<DiscoverJob>("/jobs", {
    method: "POST",
    body: { term, also, window_months: window },
  });
  return r.ok ? NextResponse.json(r.data, { status: 202 }) : NextResponse.json({ error: r.error }, { status: r.status });
}
