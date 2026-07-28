import { NextResponse } from "next/server";
import { canAccess } from "@/lib/entitlement";
import { getTechnologies, getTechnology } from "@/lib/technology";
import type { TechInsight, TechPayload } from "@/lib/technology";

export const dynamic = "force-dynamic";

/**
 * GET /api/foresight/technology            — all curated technology axes
 * GET /api/foresight/technology?cpc=H02S   — one technology
 *
 * Thin read layer over the precomputed cpc_insights snapshots (lead-time
 * chain, patent dynamics, convergence partners).
 */

/**
 * Allowlist projection of the raw JSONB payload (CONF-03): the snapshot files
 * carry internal method/build fields (tir_method, built_in_s, cycle_cov, …)
 * that are not display data and must not leave the server.
 */
function toPublicTech(t: TechInsight) {
  const p = t.payload as TechPayload & { patent_dynamics: Record<string, unknown> };
  const pd = p.patent_dynamics ?? {};
  return {
    symbol: t.symbol,
    name: t.name,
    vertical: t.vertical,
    updated_at: t.updated_at,
    payload: {
      lead_time: p.lead_time,
      lead_years_science_vs_market: p.lead_years_science_vs_market,
      lead_years_patent_vs_market: p.lead_years_patent_vs_market,
      patent_dynamics: {
        hub: pd.hub,
        top_patents: pd.top_patents,
        cycle_time_years: pd.cycle_time_years,
        tir_pct: pd.tir_pct,
        tir_index: pd.tir_index,
        immediate_importance: pd.immediate_importance,
      },
      convergence: p.convergence,
    },
  };
}

export async function GET(request: Request) {
  // Entitlement guard (CONF-02): Pro data must not be free over the raw
  // API while the paywall is on. No-op while PAYWALL_ENABLED=0.
  if (!(await canAccess("pro"))) {
    return NextResponse.json(
      { error: "This data is part of the Pro plan", upgrade: "/trends/pricing" },
      { status: 402 }
    );
  }
  const url = new URL(request.url);
  const cpc = url.searchParams.get("cpc");

  if (cpc) {
    const tech = await getTechnology(cpc);
    if (!tech) {
      return NextResponse.json({ error: `unknown technology ${cpc}` }, { status: 404 });
    }
    return NextResponse.json(toPublicTech(tech));
  }

  const technologies = await getTechnologies();
  return NextResponse.json({
    count: technologies.length,
    technologies: technologies.map(toPublicTech),
  });
}
