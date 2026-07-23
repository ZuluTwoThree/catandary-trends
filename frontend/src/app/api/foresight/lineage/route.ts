import { NextResponse } from "next/server";
import { canAccess } from "@/lib/entitlement";
import { getLatestLineage, getLineageScopes } from "@/lib/foresight";

export const dynamic = "force-dynamic";

/**
 * GET /api/foresight/lineage?scope=vertical:HEALTH | ?vertical=HEALTH
 *
 * Thin read layer over the persisted lineage artifacts (foresight_lineage_*).
 * Serves the latest lineage per scope; no clustering in the request path.
 */
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
  const vertical = url.searchParams.get("vertical");
  const scope =
    url.searchParams.get("scope") ||
    (vertical ? `vertical:${vertical.toUpperCase()}` : "global");

  const data = await getLatestLineage(scope);
  if (!data) {
    return NextResponse.json(
      { scope, nodes: [], edges: [], available_scopes: await getLineageScopes() },
      { status: 200 }
    );
  }
  return NextResponse.json({ ...data, available_scopes: await getLineageScopes() });
}
