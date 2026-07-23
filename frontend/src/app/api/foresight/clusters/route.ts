import { NextResponse } from "next/server";
import { canAccess } from "@/lib/entitlement";
import { getClusterScopes, getLatestClusterRun } from "@/lib/foresight";

export const dynamic = "force-dynamic";

/**
 * GET /api/foresight/clusters?scope=global | ?vertical=FOOD
 *
 * Thin read layer over the persisted snapshot artifacts — serves the latest
 * run per scope for client-side consumers (future radar view, workbench).
 */
export async function GET(request: Request) {
  // Entitlement guard (CONF-02): Starter data must not be free over the raw
  // API while the paywall is on. No-op while PAYWALL_ENABLED=0.
  if (!(await canAccess("starter"))) {
    return NextResponse.json(
      { error: "This data is part of the Starter plan", upgrade: "/trends/pricing" },
      { status: 402 }
    );
  }
  const url = new URL(request.url);
  const vertical = url.searchParams.get("vertical");
  const scope =
    url.searchParams.get("scope") ||
    (vertical ? `vertical:${vertical.toUpperCase()}` : "global");

  const data = await getLatestClusterRun(scope);
  if (!data) {
    return NextResponse.json(
      { scope, run: null, clusters: [], available_scopes: await getClusterScopes() },
      { status: 200 }
    );
  }
  return NextResponse.json({
    scope,
    run: data.run,
    clusters: data.clusters,
    available_scopes: await getClusterScopes(),
  });
}
