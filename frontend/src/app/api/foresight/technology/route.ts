import { NextResponse } from "next/server";
import { getTechnologies, getTechnology } from "@/lib/technology";

export const dynamic = "force-dynamic";

/**
 * GET /api/foresight/technology            — all curated technology axes
 * GET /api/foresight/technology?cpc=H02S   — one technology
 *
 * Thin read layer over the precomputed cpc_insights snapshots (lead-time
 * chain, patent dynamics, convergence partners).
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const cpc = url.searchParams.get("cpc");

  if (cpc) {
    const tech = await getTechnology(cpc);
    if (!tech) {
      return NextResponse.json({ error: `unknown technology ${cpc}` }, { status: 404 });
    }
    return NextResponse.json(tech);
  }

  const technologies = await getTechnologies();
  return NextResponse.json({ count: technologies.length, technologies });
}
