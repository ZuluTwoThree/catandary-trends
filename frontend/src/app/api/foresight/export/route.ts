import { NextResponse } from "next/server";
import { getLatestClusterRun } from "@/lib/foresight";

export const dynamic = "force-dynamic";

/**
 * GET /api/foresight/export?scope=global|vertical:FOOD&format=csv
 *
 * Exports the latest cluster snapshot for a scope as CSV — the working artefact
 * the agency/consultant segment wants. One row per cluster: label, size,
 * momentum, sources, top tags, dominant mega-trend.
 */
function csvCell(v: unknown): string {
  const s = String(v ?? "");
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const vertical = url.searchParams.get("vertical");
  const scope =
    url.searchParams.get("scope") ||
    (vertical ? `vertical:${vertical.toUpperCase()}` : "global");

  const data = await getLatestClusterRun(scope);
  if (!data) {
    return NextResponse.json({ error: "no snapshot for scope" }, { status: 404 });
  }

  const header = [
    "label",
    "size",
    "momentum",
    "sov_delta_pp",
    "n_sources",
    "primary_vertical",
    "mega_trend",
    "top_tags",
  ];
  const rows = data.clusters
    .slice()
    .sort((a, b) => b.sov_delta_pp - a.sov_delta_pp)
    .map((c) =>
      [
        c.label,
        c.size,
        c.momentum,
        c.sov_delta_pp,
        c.n_sources,
        c.verticals[0] ?? "",
        c.mega_trend ?? "",
        c.top_tags.slice(0, 8).join("; "),
      ]
        .map(csvCell)
        .join(",")
    );
  const csv = [header.join(","), ...rows].join("\n") + "\n";

  const stamp = new Date().toISOString().slice(0, 10);
  const fname = `catandary-${scope.replace(":", "-")}-${stamp}.csv`;
  return new NextResponse(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${fname}"`,
    },
  });
}
