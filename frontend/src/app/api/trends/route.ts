import { NextRequest, NextResponse } from "next/server";
import { getTrends, getTrendsCount, getVerticalCounts } from "@/lib/db";
import { VERTICALS } from "@/lib/types";
import type { Trend, Vertical } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Public trends API. Hardened per CONF-01/ARCH-03: status is pinned to
 * 'published' (the old pass-through served unpublished drafts and rejected
 * items), parameters are validated, and internal pipeline fields (confidence,
 * auto_published, raw_entry_id, status) are stripped before the response
 * (CONF-04).
 */

const VALID_VERTICALS = new Set(VERTICALS.map((v) => v.id));

function toPublicTrend(t: Trend) {
  const {
    raw_entry_id: _rawEntryId,
    confidence: _confidence,
    auto_published: _autoPublished,
    status: _status,
    ...pub
  } = t as Trend & Record<string, unknown>;
  return pub;
}

function intParam(value: string | null, fallback: number, max: number): number | null {
  if (value === null) return fallback;
  const n = Number(value);
  if (!Number.isFinite(n) || !Number.isInteger(n) || n < 0) return null;
  return Math.min(n, max);
}

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;

  const verticalRaw = searchParams.get("vertical");
  const vertical = verticalRaw ? verticalRaw.toUpperCase() : undefined;
  if (vertical && !VALID_VERTICALS.has(vertical as Vertical)) {
    return NextResponse.json(
      { error: `unknown vertical — expected one of ${[...VALID_VERTICALS].join(", ")}` },
      { status: 400 }
    );
  }

  const limit = intParam(searchParams.get("limit"), 50, 100);
  const offset = intParam(searchParams.get("offset"), 0, 1_000_000);
  if (limit === null || offset === null) {
    return NextResponse.json(
      { error: "limit and offset must be non-negative integers" },
      { status: 400 }
    );
  }

  // Public API serves published content only — no status pass-through.
  const status = "published";

  try {
    const [trends, total, verticalCounts] = await Promise.all([
      getTrends({ status, vertical: vertical as Vertical | undefined, limit, offset }),
      getTrendsCount({ status, vertical: vertical as Vertical | undefined }),
      getVerticalCounts(status),
    ]);

    return NextResponse.json({
      trends: trends.map(toPublicTrend),
      total,
      limit,
      offset,
      verticalCounts,
    });
  } catch (e) {
    console.error("/api/trends failed:", e);
    return NextResponse.json(
      { error: "temporarily unavailable — please retry" },
      { status: 500 }
    );
  }
}
