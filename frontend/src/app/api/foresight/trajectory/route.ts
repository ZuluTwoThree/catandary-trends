import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * GET /api/foresight/trajectory — DEPRECATED (2026-07-24).
 *
 * This legacy endpoint resolved the technology domain differently from the
 * merged Technology tool (all embedding candidates vs. the curated default
 * selection) and therefore returned CONTRADICTORY numbers for the same query
 * (verified live: "solid state battery" → 10.2%/yr accelerating here vs.
 * 7.4%/yr direction-withheld in /analyze). One question, one number:
 * /api/foresight/analyze is the single freetext entry point now.
 */
export async function GET() {
  return NextResponse.json(
    {
      error: "deprecated — this endpoint returned a differently-resolved domain " +
             "than the Technology tool and has been retired",
      use: "/api/foresight/analyze?q=<phrase>",
    },
    { status: 410 }
  );
}
