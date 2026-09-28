import { canReview } from "@/lib/review-access";
import { getAllBlob, getSpaceBlob } from "@/lib/signalSpace";

export const dynamic = "force-dynamic";

/**
 * GET /api/foresight/space/points?run=<id>[&all=1][&layout=alt] — the packed signal cloud
 * (16 bytes per point, layout in lib/spaceCloud.ts): the sample that defines
 * the layout (600 a month, 1.7 MB), or with all=1 every signal of the window
 * placed into it (all_points, 1.5M, ~24 MB). Owner-only twice over:
 * /api/foresight is a PUBLIC_MODE-blocked prefix, and canReview() refuses in
 * public mode and the static export as well. A run never changes after it is
 * written, so the run id is a perfect ETag.
 */
export async function GET(request: Request) {
  if (!canReview()) return new Response("Not found", { status: 404 });
  const params = new URL(request.url).searchParams;
  const run = Number(params.get("run"));
  const all = params.get("all") === "1";
  const alt = params.get("layout") === "alt"; // the run's second layout (since 28.09.)
  if (!Number.isInteger(run) || run <= 0) return new Response("bad run", { status: 400 });
  const etag = `"space-${run}${all ? "-all" : ""}${alt ? "-alt" : ""}"`;
  if (request.headers.get("if-none-match") === etag) {
    return new Response(null, { status: 304, headers: { ETag: etag } });
  }
  const blob = all ? await getAllBlob(run, alt) : await getSpaceBlob(run, alt);
  if (!blob) return new Response("Not found", { status: 404 });
  return new Response(new Uint8Array(blob), {
    headers: {
      "Content-Type": "application/octet-stream",
      "Cache-Control": "private, max-age=86400",
      ETag: etag,
    },
  });
}
