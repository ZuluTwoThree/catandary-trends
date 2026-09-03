import { NextRequest, NextResponse } from "next/server";
import { suggestLocal } from "@/lib/db";
import { suggestAuthors } from "@/lib/openalex-live";

export const dynamic = "force-dynamic";

/** Typeahead-Vorschläge fürs Research-Suchfeld (#83).
 *
 *  journal/funder/institution kommen aus lokalen Distinct-Aggregaten
 *  (keine API). author läuft über das OpenAlex-Autocomplete (0 Credits —
 *  zählt deshalb nicht gegen ein Live-Budget). */
export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const kind = (sp.get("kind") ?? "").trim();
  const qText = (sp.get("q") ?? "").trim();
  if (qText.length < 2 || qText.length > 120) {
    return NextResponse.json({ s: [] });
  }
  if (kind === "journal" || kind === "funder" || kind === "institution") {
    return NextResponse.json({ s: await suggestLocal(kind, qText) });
  }
  if (kind === "author") {
    return NextResponse.json({ s: await suggestAuthors(qText) });
  }
  return NextResponse.json({ s: [] });
}
