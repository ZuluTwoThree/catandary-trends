import { NextRequest, NextResponse } from "next/server";
import { getTrends, getTrendsCount, getVerticalCounts } from "@/lib/db";
import type { Vertical } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;

  const status = searchParams.get("status") || undefined;
  const vertical = (searchParams.get("vertical") as Vertical) || undefined;
  const limit = Math.min(parseInt(searchParams.get("limit") || "50"), 100);
  const offset = parseInt(searchParams.get("offset") || "0");

  const trends = await getTrends({ status, vertical, limit, offset });
  const total = await getTrendsCount({ status, vertical });
  const verticalCounts = await getVerticalCounts(status);

  return NextResponse.json({
    trends,
    total,
    limit,
    offset,
    verticalCounts,
  });
}
