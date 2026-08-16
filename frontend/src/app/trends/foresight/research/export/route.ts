import { NextRequest, NextResponse } from "next/server";
import { getResearchCorpus } from "@/lib/db";
import { parseResearchQuery } from "@/lib/research-search";
import { canAccess } from "@/lib/entitlement";

export const dynamic = "force-dynamic";

/** CSV-Export der Research-Treffer (#83) — Pro-Feature, max 1.000 Zeilen.
 *  OpenAlex-Daten sind CC0, der Export ist lizenzrechtlich sauber. */

function csvField(v: unknown): string {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export async function GET(req: NextRequest) {
  if (!(await canAccess("pro"))) {
    return NextResponse.json(
      { error: "CSV export is part of the Pro plan." },
      { status: 402 });
  }
  const sp = req.nextUrl.searchParams;
  const parsed = parseResearchQuery((sp.get("q") ?? "").trim());
  const topic = (sp.get("topic") ?? "").trim();
  const flagRaw = (sp.get("flag") ?? "").trim();
  const flag = flagRaw === "landmark" || flagRaw === "review"
    ? (flagRaw as "landmark" | "review") : undefined;
  const hasFilter = parsed.text || parsed.doi || parsed.arxiv || topic
    || parsed.author || parsed.institution || parsed.journal
    || parsed.funder || parsed.country || flag
    || parsed.yearFrom !== undefined;
  if (!hasFilter) {
    return NextResponse.json(
      { error: "Add a search or filter before exporting." }, { status: 400 });
  }
  const { rows } = await getResearchCorpus({
    q: parsed.text || undefined,
    doi: parsed.doi,
    arxiv: parsed.arxiv,
    topic: topic || undefined,
    author: parsed.author,
    institution: parsed.institution,
    journal: parsed.journal,
    funder: parsed.funder,
    country: parsed.country,
    noRetracted: sp.get("nr") === "1",
    flag,
    limit: 1000,
    offset: 0,
  });
  const header = ["title", "authors", "year", "type", "topic", "journal",
    "cited_by_count", "fwci", "is_retracted", "doi", "openalex_id"];
  const lines = [header.join(",")];
  for (const r of rows) {
    lines.push([
      csvField(r.title), csvField(r.authors), r.year ?? "", r.type ?? "",
      csvField(r.topic), csvField(r.journal), r.cited_by_count ?? "",
      r.fwci ?? "", r.is_retracted ? "true" : "false", csvField(r.doi),
      `https://openalex.org/${r.id}`,
    ].join(","));
  }
  return new NextResponse(lines.join("\r\n") + "\r\n", {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": 'attachment; filename="catandary-research-export.csv"',
      "X-Source": "OpenAlex (CC0) via Catandary Trends",
    },
  });
}
