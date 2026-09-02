/**
 * Render-mode switch for the two ways this one source tree is built
 * (design: docs/audits/2026-09-02_static_export_design.md, Schritt 2):
 *
 *  - Workstation instance (`npm run build` / `next start`, :3001/:3004):
 *    public pages render per request, exactly as the former
 *    `export const dynamic = "force-dynamic"` lines did.
 *  - Static export (`STATIC_EXPORT=1`, scripts/build_public_static.sh):
 *    the same pages prerender to HTML for the Hetzner webspace.
 *
 * Next only accepts route-segment config (`dynamic`, `revalidate`, …) as a
 * literal export, so an env-conditional `dynamic` is impossible. The escape
 * hatch is `connection()` (next/server): awaiting it opts a render into
 * request-time dynamic rendering — the same effect as `force-dynamic` — and
 * the call is simply skipped in the export build. `await dynamicUnlessStatic()`
 * at the top of a page function replaces the old literal one-to-one.
 *
 * `isStaticExport()` reads the NEXT_PUBLIC_ mirror so client components (the
 * page-view tracker, the newsletter signup) can branch on it too: next.config
 * sets `env.NEXT_PUBLIC_STATIC_EXPORT` from `STATIC_EXPORT`, and Next inlines
 * NEXT_PUBLIC_* at build time into both bundles.
 */
import { cache } from "react";

export function isStaticExport(): boolean {
  return (
    process.env.NEXT_PUBLIC_STATIC_EXPORT === "1" ||
    process.env.STATIC_EXPORT === "1"
  );
}

/**
 * Replacement for `export const dynamic = "force-dynamic"` on public pages.
 * No-op in the static export; otherwise marks the render dynamic.
 *
 * `next/server` is imported lazily so this module stays safe to import from
 * client components (which only ever call `isStaticExport()`).
 */
export async function dynamicUnlessStatic(): Promise<void> {
  if (isStaticExport()) return;
  const { connection } = await import("next/server");
  await connection();
}

/* ---------- Metadata gate (static export only) ---------- */

interface Deferred {
  promise: Promise<void>;
  resolve: () => void;
}

/**
 * Per-render handshake between `generateMetadata` and the page body,
 * needed only for byte-stable exports.
 *
 * React streams the RSC payload in resolution order. A page with
 * `generateMetadata` has two async subtrees racing against each other: the
 * metadata tree (title, `<link rel=icon>`, the metadata outlet — emitted as
 * lazily outlined rows a microtask after the metadata resolves) and the page
 * body (emitted when its own queries return). When the body's last DB round
 * trip lands within the same tick as the metadata flush, the module-reference
 * row of the page's client component lands before the metadata rows instead
 * of after them — same rows, different order, ~5 % of article pages flipped
 * between two exports (2026-09-02). The rows are semantically
 * order-independent, but the incremental upload compares bytes.
 *
 * Fix: `generateMetadata` calls `metadataSettled()` when it returns; the page
 * body awaits `afterMetadata()` before returning its tree. Two macrotask hops
 * after the metadata promise let every microtask-scheduled flush of the
 * metadata subtree run first (its tail does no I/O). Outside the export both
 * are no-ops; the gate is also time-capped so a render can never hang on it.
 *
 * `cache()` keys the deferred to the request, so generateMetadata and the page
 * of the same render share it while parallel renders do not.
 */
const metadataGate = cache((): Deferred => {
  let resolve!: () => void;
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  return { promise, resolve };
});

/** Call at the end of `generateMetadata` (a `finally` is the right place). */
export function metadataSettled(): void {
  if (!isStaticExport()) return;
  metadataGate().resolve();
}

const METADATA_GATE_CAP_MS = 250;

/** Await right before the page returns its tree. No-op outside the export. */
export async function afterMetadata(): Promise<void> {
  if (!isStaticExport()) return;
  await Promise.race([
    metadataGate().promise,
    new Promise<void>((r) => setTimeout(r, METADATA_GATE_CAP_MS)),
  ]);
  await new Promise<void>((r) => setImmediate(r));
  await new Promise<void>((r) => setImmediate(r));
}
