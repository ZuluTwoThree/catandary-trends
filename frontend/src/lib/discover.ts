/**
 * Live pocket discovery for a free term (Owner 2026-10-01) — the frontend side of
 * pipeline/domain_service.py, a resident service on 127.0.0.1:8093 that keeps every
 * embedded signal in memory. The page sends a term, shows the selection the service
 * proposes, and on confirmation lets it find, date, group and name the pockets; the
 * result is an ordinary emerging run with scope `domain:q_<term>`.
 *
 * Owner-only: the page lives under /trends/foresight and the API under /api/foresight,
 * both blocked in PUBLIC_MODE and never exported.
 */
import { q } from "./pg";
import type { ServiceHealth } from "./discoverJobs";

export type * from "./discoverJobs";

export const DOMAIN_SERVICE_URL = process.env.DOMAIN_SERVICE_URL || "http://127.0.0.1:8093";

/** Call the service; {ok:false} with a readable reason when it is down. */
export async function serviceFetch<T>(
  path: string,
  init?: { method?: string; body?: unknown }
): Promise<{ ok: true; status: number; data: T } | { ok: false; status: number; error: string }> {
  try {
    const res = await fetch(`${DOMAIN_SERVICE_URL}${path}`, {
      method: init?.method ?? "GET",
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
      body: init?.body ? JSON.stringify(init.body) : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    const data = (await res.json().catch(() => ({}))) as T & { error?: string };
    if (!res.ok) return { ok: false, status: res.status, error: data?.error || `HTTP ${res.status}` };
    return { ok: true, status: res.status, data };
  } catch {
    return {
      ok: false,
      status: 503,
      error:
        "The discovery service is not running (pipeline/domain_service.py on port 8093 — " +
        "systemctl --user start catandary-domain-service).",
    };
  }
}

export interface FreeDomain {
  key: string;
  name: string;
  nests: number | null;
  computed: string | null;
  window_days: number | null;
}

/** Free-term domains that have a probe, newest first, with their latest run. */
export async function listFreeDomains(): Promise<FreeDomain[]> {
  try {
    return await q<FreeDomain>(
      "SELECT p.key, COALESCE(p.name, p.key) AS name, r.nests, r.window_days, " +
        "to_char(COALESCE(r.created_at, p.trained_at), 'YYYY-MM-DD HH24:MI') AS computed " +
        "FROM domain_probes p LEFT JOIN LATERAL (SELECT nests, window_days, created_at " +
        "FROM emerging_runs WHERE scope = 'domain:' || p.key ORDER BY id DESC LIMIT 1) r ON TRUE " +
        "WHERE p.key LIKE 'q\\_%' ORDER BY COALESCE(r.created_at, p.trained_at) DESC"
    );
  } catch {
    return [];
  }
}

/** Same-origin check for the POST/DELETE routes (the page calls them with fetch). */
export function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  try {
    return new URL(origin).host === new URL(request.url).host ||
      new URL(origin).host === request.headers.get("host");
  } catch {
    return false;
  }
}
