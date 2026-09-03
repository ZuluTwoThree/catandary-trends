import { getPublicIndexRows } from "@/lib/db";
import { PUBLIC_ARCHIVE_DAYS } from "@/lib/archiveWindow";
import { isPublicMode } from "@/lib/publicMode";
import { isStaticExport } from "@/lib/renderMode";
import { buildIndexEntries, serializeIndex } from "@/lib/staticSearch";

/**
 * /trends/index.json — the search index of the static export (design
 * Schritt 5 / D, lib/staticSearch.ts): every published article of the
 * public window, one JSON object per line, in the listing's order.
 * components/StaticSearch.tsx fetches it lazily on the first interaction.
 *
 * `force-static` is the literal the export requires for a route handler
 * (same as trends/sitemap.ts); the workstation build therefore renders it
 * once at build time too. Outside a public deployment (no PUBLIC_MODE, no
 * export) it is an empty array: the workstation feed has the server-side
 * `?q=` search and never loads this file. In the export a database error
 * fails the build on purpose — build_public_static.sh checks the file.
 */
export const dynamic = "force-static";

export async function GET(): Promise<Response> {
  let body = "[]\n";
  if (isStaticExport() || isPublicMode()) {
    try {
      body = serializeIndex(buildIndexEntries(await getPublicIndexRows(PUBLIC_ARCHIVE_DAYS)));
    } catch (err) {
      if (isStaticExport()) throw err;
      console.warn("index.json: database unavailable, empty index —", (err as Error).message);
    }
  }
  return new Response(body, {
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}
