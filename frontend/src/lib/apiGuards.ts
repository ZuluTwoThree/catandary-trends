/**
 * Guards for the small state-changing endpoints a browser calls with a plain
 * fetch() — newsletter signup, engagement tracking, unsubscribe (security
 * review 2026-09-02, E-5/E-7). Two concerns, kept deliberately simple:
 *
 *  - Same-origin: a page on any other site must not be able to subscribe an
 *    address or pump a trend's page views from a visitor's browser. Origin /
 *    Referer cannot be forged cross-site, so matching them against our own
 *    host closes that hole. A non-browser client can set both — that is what
 *    the rate limiter is for; this check is about browsers.
 *  - Bounded bodies: read at most `maxBytes`, streaming, and cancel beyond
 *    that — `request.json()` would buffer whatever arrives first.
 */

/** Hosts a browser request to this app may legitimately originate from. */
export function allowedHosts(request: Request): Set<string> {
  return allowedHostsFromHeaders(request.headers);
}

/**
 * Same, from a bare Headers object — what a Server Action gets from
 * `headers()` (next/headers); it has no Request to hand over. The dossier
 * desk's actions (#95) start GPU work, so they run this check too.
 */
export function allowedHostsFromHeaders(headers: Headers): Set<string> {
  const hosts = new Set<string>();
  const base = process.env.PUBLIC_BASE_URL;
  if (base) {
    try {
      hosts.add(new URL(base).host.toLowerCase());
    } catch {
      // unparsable PUBLIC_BASE_URL — fall through to the request's own host
    }
  }
  for (const name of ["x-forwarded-host", "host"]) {
    const v = headers.get(name);
    if (v) hosts.add(v.split(",")[0].trim().toLowerCase());
  }
  return hosts;
}

function hostOf(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).host.toLowerCase();
  } catch {
    return null;
  }
}

/**
 * True when the request's Origin (authoritative — browsers always send it on
 * POST) or, failing that, its Referer names one of our own hosts. Neither
 * header present → false (fail closed): every browser POST carries Origin, so
 * this only ever rejects non-browser callers that did not bother to set it.
 */
export function isSameOrigin(request: Request): boolean {
  return isSameOriginHeaders(request.headers);
}

/** `isSameOrigin` for a bare Headers object (Server Actions). */
export function isSameOriginHeaders(headers: Headers): boolean {
  const allowed = allowedHostsFromHeaders(headers);
  if (allowed.size === 0) return false;
  const origin = headers.get("origin");
  if (origin !== null) {
    // "null" is what browsers send for opaque origins (sandboxed frames,
    // file://, redirects across origins) — never one of ours.
    if (origin === "null") return false;
    const h = hostOf(origin);
    return h !== null && allowed.has(h);
  }
  const ref = hostOf(headers.get("referer"));
  return ref !== null && allowed.has(ref);
}

export type BodyResult<T> =
  | { ok: true; value: T }
  | { ok: false; status: number; error: string };

/**
 * Read the body as UTF-8, aborting once more than `maxBytes` have arrived.
 * `null` = too large (declared or actual).
 */
export async function readTextBody(request: Request, maxBytes: number): Promise<string | null> {
  const declared = Number(request.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > maxBytes) return null;
  const body = request.body;
  if (!body) return "";
  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel().catch(() => {});
      return null;
    }
    chunks.push(value);
  }
  return Buffer.concat(chunks).toString("utf8");
}

/**
 * Parse a JSON object body of at most `maxBytes`. Oversize → 413, malformed
 * or non-object JSON → 400. The caller still validates every field.
 */
export async function readJsonBody<T extends Record<string, unknown> = Record<string, unknown>>(
  request: Request,
  maxBytes: number
): Promise<BodyResult<T>> {
  let text: string | null;
  try {
    text = await readTextBody(request, maxBytes);
  } catch {
    return { ok: false, status: 400, error: "bad request" };
  }
  if (text === null) return { ok: false, status: 413, error: "payload too large" };
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return { ok: false, status: 400, error: "bad request" };
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { ok: false, status: 400, error: "bad request" };
  }
  return { ok: true, value: value as T };
}
