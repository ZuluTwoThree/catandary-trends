import { NextResponse } from "next/server";
import { getRadarData } from "@/lib/foresight";

export const dynamic = "force-dynamic";

/**
 * GET /api/foresight/radar?vertical=HEALTH
 *
 * Thin read layer over the tier-scoped snapshot artifacts. Serves the latest
 * radar blips (one set per lead-time tier); ?vertical scopes to one segment.
 * No clustering in the request path.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const vertical = url.searchParams.get("vertical");
  const data = await getRadarData(vertical ? vertical.toUpperCase() : null);
  return NextResponse.json(data);
}
