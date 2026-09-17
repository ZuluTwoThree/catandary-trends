import { q } from "./pg";
import { TIERS } from "./tiers";

/**
 * Stage 3 (2026-09-17): what to type. Three suppliers, all already there —
 * the names of the emerging pockets (the naming step of 2026-09-15 pays off
 * here: a pocket's name IS the term one would enter), the new vocabulary the
 * dating scan turns up, and the questions already asked with their result.
 * A suggestion may be wrong; it is an invitation to search, not a finding.
 */

export interface Suggestion {
  term: string;
  /** e.g. "market · 7 m · 412 rows" */
  note: string;
  href: string;
}

const SCOPES = ["global", ...TIERS.map((t) => `tier:${t}`)];

function ageText(months: number | null): string {
  if (months == null) return "age ?";
  const y = Math.floor(months / 12);
  const m = months % 12;
  return y ? `${y} y ${m} m` : `${m} m`;
}

function scopeLabel(scope: string): string {
  if (scope === "global") return "all";
  if (scope.startsWith("tier:")) return scope.slice(5);
  return scope.replace("vertical:", "").toLowerCase();
}

function href(term: string, tier?: string): string {
  const p = new URLSearchParams({ q: term });
  if (tier && (TIERS as string[]).includes(tier)) p.set("tiers", tier);
  return `/trends/foresight/topic?${p.toString()}`;
}

export async function getTopicSuggestions(): Promise<{
  pockets: Suggestion[];
  vocabulary: Suggestion[];
  asked: Suggestion[];
}> {
  const empty = { pockets: [], vocabulary: [], asked: [] };
  try {
    const nests = await q<{
      name: string | null;
      age_months: number | null;
      hits_total: number | null;
      scope: string;
      new_terms: string | null;
    }>(
      "SELECT COALESCE(n.llm_label, n.label) AS name, n.age_months, n.hits_total, r.scope, n.new_terms " +
        "FROM emerging_nests n JOIN emerging_runs r ON r.id = n.run_id " +
        "WHERE r.id IN (SELECT MAX(id) FROM emerging_runs WHERE scope = ANY($1::text[]) GROUP BY scope) " +
        "ORDER BY n.novelty_lift DESC NULLS LAST, n.size DESC LIMIT 60",
      [SCOPES]
    );
    const seen = new Set<string>();
    const pockets: Suggestion[] = [];
    const vocab = new Map<string, Suggestion>();
    for (const n of nests) {
      const name = (n.name || "").trim();
      const tier = n.scope.startsWith("tier:") ? n.scope.slice(5) : undefined;
      if (name && !seen.has(name.toLowerCase()) && pockets.length < 24) {
        seen.add(name.toLowerCase());
        pockets.push({
          term: name,
          note: `${scopeLabel(n.scope)} · ${ageText(n.age_months)} · ${(n.hits_total ?? 0).toLocaleString("en-US")} rows`,
          href: href(name, tier),
        });
      }
      let terms: string[] = [];
      try {
        terms = n.new_terms ? (JSON.parse(n.new_terms) as string[]) : [];
      } catch {
        terms = [];
      }
      for (const t of terms) {
        const k = t.toLowerCase();
        if (!vocab.has(k) && vocab.size < 24)
          vocab.set(k, { term: t, note: `new vocabulary · ${scopeLabel(n.scope)}`, href: href(t, tier) });
      }
    }
    const askedRows = await q<{
      query: string;
      tiers: string;
      status: string | null;
      first: string | null;
      market_first: string | null;
      created_at: string;
    }>(
      "SELECT DISTINCT ON (query_norm) query, tiers, report::jsonb->>'status' AS status, " +
        "report::jsonb->'overall'->>'first_month' AS first, " +
        "report::jsonb->'tiers'->'market'->>'first_hit' AS market_first, created_at::text AS created_at " +
        "FROM topic_reports ORDER BY query_norm, id DESC"
    );
    const asked: Suggestion[] = askedRows
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .slice(0, 20)
      .map((r) => {
        const note =
          r.status === "ambiguous"
            ? "asked back"
            : r.status === "nothing"
              ? "nothing close"
              : `${r.first ? `since ${r.first}` : "undated"}${r.market_first ? ` · market ${r.market_first}` : ""}`;
        const p = new URLSearchParams({ q: r.query });
        if (r.tiers && r.tiers.split(",").length < TIERS.length) p.set("tiers", r.tiers);
        return { term: r.query, note, href: `/trends/foresight/topic?${p.toString()}` };
      });
    return { pockets, vocabulary: [...vocab.values()], asked };
  } catch {
    return empty; // tables missing → the page renders without suggestions
  }
}
