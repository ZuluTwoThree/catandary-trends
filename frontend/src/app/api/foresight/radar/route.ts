import { NextResponse } from "next/server";
import { canAccess } from "@/lib/entitlement";
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
  const data = await getRadarData(vertical ? vertical.toUpperCase() : null);
  return NextResponse.json(data);
}
