import { q, q1 } from "./pg";

/**
 * OpenAlex-Live-Layer (#83): serverseitige On-Demand-Frische auf dem
 * Snapshot-Korpus.
 *
 * Seit #93 (kein SaaS, keine Accounts — 2026-09-03) gibt es nur noch die
 * Owner-Instanz, und die ist unbegrenzt: das frühere Super-Pro-Gate und der
 * 25/Tag-Zähler je Account (`research_live_usage`) sind entfernt; die
 * Tabelle bleibt ungenutzt stehen. `LiveAccess`/`consumeLive` bleiben als
 * Vertrag der Aufrufer (Research Explorer, Paper-Seite) erhalten, damit ein
 * Budget — etwa gegen den OpenAlex-Tageskontingent — jederzeit wieder
 * eingehängt werden kann, ohne die Seiten anzufassen.
 *
 * Budget-Ökonomie (Header-Messung 2026-08-16, Key = 10.000 Credits/Tag):
 * Singleton- und Autocomplete-Calls kosten 0 Credits, Listen-Filter 1,
 * title_and_abstract.search ~10. Cache-Treffer kosten kein Budget.
 * Der API-Key bleibt serverseitig (env), erreicht nie den Client.
 */

const API = "https://api.openalex.org";
export const LIVE_DAILY_LIMIT = 25;

/* ---------- Zugriff & Tagesbudget ---------- */

export interface LiveAccess {
  /** Kein Tageslimit — auf der Owner-Instanz immer true. */
  unlimited: boolean;
  used: number;
  remaining: number;
}

export async function liveAccess(): Promise<LiveAccess> {
  return { unlimited: true, used: 0, remaining: LIVE_DAILY_LIMIT };
}

/** Eine Live-Abfrage verbrauchen — no-op, solange der Zugriff unbegrenzt ist. */
export async function consumeLive(access: LiveAccess): Promise<void> {
  if (access.unlimited) return;
}

/* ---------- Cache + HTTP ---------- */

async function apiGet(path: string, params: Record<string, string>): Promise<unknown | null> {
  const key = process.env.OPENALEX_API_KEY;
  const u = new URL(API + path);
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v);
  if (key) u.searchParams.set("api_key", key);
  try {
    const r = await fetch(u, { signal: AbortSignal.timeout(8000), cache: "no-store" });
    if (!r.ok) return null; // 429/5xx: Feature degradiert still auf Snapshot-Stand
    return await r.json();
  } catch {
    return null;
  }
}

/**
 * Cache-first-Fetch. `fresh` sagt dem Aufrufer, ob ein echter API-Zugriff
 * passierte (nur dann Budget ziehen). Fehlgeschlagene Fetches werden NICHT
 * gecacht — der nächste Versuch darf es wieder probieren.
 */
async function cached<T>(
  kind: string, cacheKey: string, ttlMinutes: number,
  fetcher: () => Promise<T | null>,
): Promise<{ data: T | null; fresh: boolean }> {
  const hit = await q1<{ payload: T }>(
    `SELECT payload FROM research_live_cache
     WHERE kind = $1 AND key = $2
       AND fetched_at > CURRENT_TIMESTAMP - ($3 || ' minutes')::interval`,
    [kind, cacheKey, String(ttlMinutes)]);
  if (hit) return { data: hit.payload, fresh: false };
  const data = await fetcher();
  if (data !== null) {
    await q(
      `INSERT INTO research_live_cache (kind, key, payload, fetched_at)
       VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
       ON CONFLICT (kind, key) DO UPDATE
         SET payload = EXCLUDED.payload, fetched_at = CURRENT_TIMESTAMP`,
      [kind, cacheKey, JSON.stringify(data)]);
  }
  return { data, fresh: data !== null };
}

/* ---------- Feature 1+2+6: Paper-Live (Singleton + cites:) ---------- */

export interface LiveWork {
  cited_by_count: number | null;
  counts_by_year: { year: number; cited_by_count: number }[];
  is_oa: boolean;
  oa_url: string | null;
  referenced_works: string[];
  related_works: string[];
  citing: LiveHit[];
}

export interface LiveHit {
  id: string;
  title: string;
  year: number | null;
  cited_by_count: number | null;
  doi: string | null;
  published: string | null;
}

function toHit(w: Record<string, unknown>): LiveHit {
  return {
    id: String(w.id ?? ""),
    title: String(w.title ?? w.display_name ?? ""),
    year: (w.publication_year as number) ?? null,
    cited_by_count: (w.cited_by_count as number) ?? null,
    doi: (w.doi as string) ?? null,
    published: (w.publication_date as string) ?? null,
  };
}

const shortId = (id: string) => id.split("/").pop() ?? id;

/** Nur-Cache-Blick (beliebig alt) — für „Budget aufgebraucht"-Fälle. */
export async function peekLiveWork(workId: string): Promise<LiveWork | null> {
  const hit = await q1<{ payload: LiveWork }>(
    "SELECT payload FROM research_live_cache WHERE kind = 'work' AND key = $1",
    [workId]);
  return hit?.payload ?? null;
}

/** Singleton (0 Credits) + Top-zitierende Werke (1 Credit). TTL 24 h. */
export async function liveWorkContext(
  workId: string,
): Promise<{ data: LiveWork | null; fresh: boolean }> {
  return cached<LiveWork>("work", workId, 24 * 60, async () => {
    const [w, cites] = await Promise.all([
      apiGet(`/works/${workId}`, {}) as Promise<Record<string, unknown> | null>,
      apiGet("/works", {
        filter: `cites:${workId}`,
        sort: "cited_by_count:desc",
        "per-page": "7",
        select: "id,title,publication_year,publication_date,cited_by_count,doi",
      }) as Promise<{ results?: Record<string, unknown>[] } | null>,
    ]);
    if (!w) return null;
    const oa = (w.open_access ?? {}) as Record<string, unknown>;
    return {
      cited_by_count: (w.cited_by_count as number) ?? null,
      counts_by_year: ((w.counts_by_year as { year: number; cited_by_count: number }[]) ?? [])
        .filter((c) => c.year && c.cited_by_count >= 0)
        .sort((a, b) => a.year - b.year),
      is_oa: !!oa.is_oa,
      oa_url: (oa.oa_url as string) ?? null,
      referenced_works: ((w.referenced_works as string[]) ?? []).map(shortId),
      related_works: ((w.related_works as string[]) ?? []).map(shortId),
      citing: (cites?.results ?? []).map((r) => ({ ...toHit(r), id: shortId(String(r.id ?? "")) })),
    };
  });
}

/* ---------- Feature 4: Latest (live) je Topic/Suchtext ---------- */

/** Kommas/Doppelpunkte brechen die OpenAlex-Filtersyntax — raus damit. */
const filterSafe = (s: string) => s.replace(/[,:]/g, " ").replace(/\s+/g, " ").trim();

/** Neueste Werke live (Topic-Filter 1 Credit, Textsuche ~10). TTL 6 h. */
export async function liveLatest(
  opts: { topic?: string; text?: string },
): Promise<{ data: LiveHit[] | null; fresh: boolean }> {
  const label = opts.topic ? `t:${opts.topic}` : `q:${opts.text}`;
  return cached<LiveHit[]>("latest", label.slice(0, 500), 6 * 60, async () => {
    const since = new Date(Date.now() - 60 * 86_400_000).toISOString().slice(0, 10);
    // Topics sind nur per ID filterbar (display_name ist kein Filter-Feld) —
    // Name → T-ID über den Topics-Endpunkt auflösen (1 Credit), Fallback
    // auf Textsuche wenn die Auflösung scheitert.
    let filter: string | null = null;
    if (opts.topic) {
      const t = (await apiGet("/topics", {
        filter: `display_name.search:${filterSafe(opts.topic)}`,
        "per-page": "1", select: "id",
      })) as { results?: { id?: string }[] } | null;
      const tid = t?.results?.[0]?.id;
      if (tid) filter = `primary_topic.id:${shortId(tid)},from_publication_date:${since}`;
    }
    if (!filter) {
      const text = filterSafe(opts.text ?? opts.topic ?? "");
      if (!text) return null;
      filter = `title_and_abstract.search:${text},from_publication_date:${since}`;
    }
    const j = (await apiGet("/works", {
      filter,
      sort: "publication_date:desc",
      "per-page": "8",
      select: "id,title,publication_year,publication_date,cited_by_count,doi",
    })) as { results?: Record<string, unknown>[] } | null;
    if (!j) return null;
    return (j.results ?? []).map((r) => ({ ...toHit(r), id: shortId(String(r.id ?? "")) }));
  });
}

/* ---------- Feature 5: Author-/Institution-Spotlight ---------- */

export interface Spotlight {
  id: string;
  name: string;
  hint: string | null;
  works_count: number | null;
  cited_by_count: number | null;
  h_index: number | null;
  i10_index: number | null;
  orcid: string | null;
  homepage: string | null;
  country: string | null;
}

/** Autocomplete (0 Credits) → Singleton (0 Credits). TTL 7 Tage. */
export async function liveSpotlight(
  kind: "author" | "institution", name: string,
): Promise<{ data: Spotlight | null; fresh: boolean }> {
  const path = kind === "author" ? "authors" : "institutions";
  return cached<Spotlight>(`spot:${kind}`, name.toLowerCase().slice(0, 300), 7 * 24 * 60,
    async () => {
      const ac = (await apiGet(`/autocomplete/${path}`, { q: name })) as
        { results?: { id?: string; display_name?: string; hint?: string }[] } | null;
      const top = ac?.results?.[0];
      if (!top?.id) return null;
      const e = (await apiGet(`/${path}/${shortId(top.id)}`, {})) as
        Record<string, unknown> | null;
      if (!e) return null;
      const stats = (e.summary_stats ?? {}) as Record<string, number>;
      const ids = (e.ids ?? {}) as Record<string, string>;
      const geo = (e.geo ?? {}) as Record<string, string>;
      const lastInst = ((e.last_known_institutions as { display_name?: string }[]) ?? [])[0];
      return {
        id: shortId(String(e.id ?? "")),
        name: String(e.display_name ?? top.display_name ?? name),
        hint: lastInst?.display_name ?? top.hint ?? null,
        works_count: (e.works_count as number) ?? null,
        cited_by_count: (e.cited_by_count as number) ?? null,
        h_index: stats.h_index ?? null,
        i10_index: stats.i10_index ?? null,
        orcid: ids.orcid ?? null,
        homepage: (e.homepage_url as string) ?? null,
        country: geo.country_code ?? (e.country_code as string) ?? null,
      };
    });
}

/* ---------- Feature 3: Autoren-Typeahead (API, 0 Credits) ---------- */

/** Autocomplete-Vorschläge für Autorennamen (0 Credits, ungezählt). */
export async function suggestAuthors(
  qText: string,
): Promise<{ v: string; n: number | null }[]> {
  const ac = (await apiGet("/autocomplete/authors", { q: qText })) as
    { results?: { display_name?: string; works_count?: number }[] } | null;
  return (ac?.results ?? [])
    .filter((r) => r.display_name)
    .slice(0, 8)
    .map((r) => ({ v: r.display_name as string, n: r.works_count ?? null }));
}
