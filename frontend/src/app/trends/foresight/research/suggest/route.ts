import { NextRequest, NextResponse } from "next/server";
import { suggestLocal } from "@/lib/db";
import { suggestAuthors } from "@/lib/openalex-live";
import { canAccess } from "@/lib/entitlement";

export const dynamic = "force-dynamic";

/** Typeahead-Vorschläge fürs Research-Suchfeld (#83).
 *
 *  journal/funder/institution kommen aus lokalen Distinct-Aggregaten
 *  (keine API, Starter wie die Suche selbst). author läuft über das
 *  OpenAlex-Autocomplete (0 Credits — zählt deshalb NICHT gegen das
 *  25/Tag-Live-Budget, ist aber wie alle Live-API-Features Super-Pro). */
export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const kind = (sp.get("kind") ?? "").trim();
  const qText = (sp.get("q") ?? "").trim();
  if (qText.length < 2 || qText.length > 120) {
    return NextResponse.json({ s: [] });
  }
  if (kind === "journal" || kind === "funder" || kind === "institution") {
    if (!(await canAccess("starter"))) return NextResponse.json({ s: [] });
    return NextResponse.json({ s: await suggestLocal(kind, qText) });
  }
  if (kind === "author") {
    if (!(await canAccess("superpro"))) return NextResponse.json({ s: [] });
    return NextResponse.json({ s: await suggestAuthors(qText) });
  }
  return NextResponse.json({ s: [] });
}
