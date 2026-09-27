import { canReview } from "@/lib/review-access";
import { getSpaceBlob } from "@/lib/signalSpace";

export const dynamic = "force-dynamic";

/**
 * GET /api/foresight/space/points?run=<id> — the packed signal cloud
 * (16 bytes per point, layout in lib/spaceCloud.ts). Owner-only twice over:
 * /api/foresight is a PUBLIC_MODE-blocked prefix, and canReview() refuses in
 * public mode and the static export as well. A run never changes after it is
 * written, so the run id is a perfect ETag.
 */
export async function GET(request: Request) {
  if (!canReview()) return new Response("Not found", { status: 404 });
  const run = Number(new URL(request.url).searchParams.get("run"));
  if (!Number.isInteger(run) || run <= 0) return new Response("bad run", { status: 400 });
  const etag = `"space-${run}"`;
  if (request.headers.get("if-none-match") === etag) {
    return new Response(null, { status: 304, headers: { ETag: etag } });
  }
  const blob = await getSpaceBlob(run);
  if (!blob) return new Response("Not found", { status: 404 });
  return new Response(new Uint8Array(blob), {
    headers: {
      "Content-Type": "application/octet-stream",
      "Cache-Control": "private, max-age=86400",
      ETag: etag,
    },
  });
}
