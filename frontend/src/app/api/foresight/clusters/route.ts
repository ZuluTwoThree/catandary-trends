import { NextResponse } from "next/server";
import { getClusterScopes, getLatestClusterRun } from "@/lib/foresight";

export const dynamic = "force-dynamic";

/**
 * GET /api/foresight/clusters?scope=global | ?vertical=FOOD
 *
 * Thin read layer over the persisted snapshot artifacts — serves the latest
 * run per scope for client-side consumers (future radar view, workbench).
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const vertical = url.searchParams.get("vertical");
  const scope =
    url.searchParams.get("scope") ||
    (vertical ? `vertical:${vertical.toUpperCase()}` : "global");

  const data = getLatestClusterRun(scope);
  if (!data) {
    return NextResponse.json(
      { scope, run: null, clusters: [], available_scopes: getClusterScopes() },
      { status: 200 }
    );
  }
  return NextResponse.json({
    scope,
    run: data.run,
    clusters: data.clusters,
    available_scopes: getClusterScopes(),
  });
}
