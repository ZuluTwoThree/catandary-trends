import { q, q1 } from "./pg";

/**
 * Startup Explorer (#87 Phase 3) — Query-Schicht über den Phase-1/2-Tabellen
 * (startup_companies/events + Brücken-Links).
 *
 * Konventionen wie die anderen Explorer: parametrisierte Queries, excluded-
 * Firmen (Fondsvehikel, Presse-Artefakte) sind überall herausgefiltert, und
 * als "belegte Substanz" zählt die Patent-Brücke NUR tech-bestätigt
 * (match_score >= 0.85; die Spalte ist REAL, 0.9 wäre dort 0.8999…) — die Stufe-1-Namensmatches bleiben unsichtbar
 * (Plan §4: lieber schweigen als falsch behaupten).
 */

export interface VentureRow {
  id: number;
  name: string;
  country: string | null;
  region: string | null;
  city: string | null;
  sector: string | null;
  verticals: string[];
  event_count: number;
  first_event_at: string | null;
  last_event_at: string | null;
  total_funding_usd: number | null;
  founded_date: string | null;
  has_patents: boolean;
  has_research: boolean;
}

export interface VentureStats {
  companies: number;
  events: number;
  with_patents: number;
  cross_source: number;
}

export async function getVentureStats(): Promise<VentureStats> {
  const row = await q1<Record<string, string>>(`
    SELECT
      (SELECT COUNT(*) FROM startup_companies WHERE excluded IS NULL) AS companies,
      (SELECT COUNT(*) FROM startup_events e
        JOIN startup_companies c ON c.id = e.company_id
        WHERE c.excluded IS NULL) AS events,
      (SELECT COUNT(DISTINCT company_id) FROM startup_patent_links
        WHERE match_score >= 0.85) AS with_patents,
      (SELECT COUNT(*) FROM (
         SELECT e.company_id FROM startup_events e
         JOIN startup_companies c ON c.id = e.company_id
         WHERE c.excluded IS NULL
         GROUP BY e.company_id HAVING COUNT(DISTINCT e.event_type) >= 2) x
      ) AS cross_source
  `);
  return {
    companies: Number(row?.companies ?? 0),
    events: Number(row?.events ?? 0),
    with_patents: Number(row?.with_patents ?? 0),
    cross_source: Number(row?.cross_source ?? 0),
  };
}

export const VENTURE_EVENT_TYPES: [string, string][] = [
  ["regd_offering", "SEC Form D filing"],
  ["press_round", "Press-verified round"],
  ["sbir_award", "SBIR/STTR award"],
  ["grant", "EU grant (CORDIS)"],
  ["launch", "Launch (Hacker News)"],
  ["clinical", "Clinical trial"],
  ["fda_clearance", "FDA 510(k) clearance"],
];

export async function searchVentures(options: {
  q?: string;
  vertical?: string;
  country?: string;
  etype?: string;
  limit: number;
  offset: number;
}): Promise<{ rows: VentureRow[]; total: number }> {
  const where: string[] = ["c.excluded IS NULL"];
  const params: unknown[] = [];
  if (options.q) {
    params.push(`%${options.q}%`);
    where.push(`(c.name ILIKE $${params.length} OR EXISTS (
      SELECT 1 FROM startup_aliases a
      WHERE a.company_id = c.id AND a.alias ILIKE $${params.length}))`);
  }
  if (options.vertical) {
    params.push(JSON.stringify([options.vertical]));
    where.push(`c.verticals @> $${params.length}::jsonb`);
  }
  if (options.country) {
    params.push(options.country);
    where.push(`c.country = $${params.length}`);
  }
  if (options.etype) {
    params.push(options.etype);
    where.push(`EXISTS (SELECT 1 FROM startup_events e
      WHERE e.company_id = c.id AND e.event_type = $${params.length})`);
  }
  params.push(options.limit, options.offset);
  const rows = await q<VentureRow & { total: string }>(
    `SELECT c.id, c.name, c.country, c.region, c.city, c.sector, c.verticals,
            c.event_count, c.first_event_at::text, c.last_event_at::text,
            c.total_funding_usd::float8 AS total_funding_usd,
            c.founded_date::text,
            EXISTS (SELECT 1 FROM startup_patent_links l
                    WHERE l.company_id = c.id AND l.match_score >= 0.85) AS has_patents,
            EXISTS (SELECT 1 FROM startup_research_links r
                    WHERE r.company_id = c.id) AS has_research,
            COUNT(*) OVER() AS total
     FROM startup_companies c
     WHERE ${where.join(" AND ")}
     ORDER BY c.event_count DESC, c.last_event_at DESC NULLS LAST, c.id
     LIMIT $${params.length - 1} OFFSET $${params.length}`,
    params,
  );
  return { rows, total: rows.length ? Number(rows[0].total) : 0 };
}

export interface VentureEvent {
  event_type: string;
  event_date: string;
  amount: number | null;
  currency: string | null;
  round_label: string | null;
  investors: string[];
  meta: Record<string, unknown>;
  source: string;
  source_url: string;
}

export interface VenturePatent {
  pub_number: string;
  title: string | null;
  published: string | null;
}

export async function getVenture(id: number) {
  const company = await q1<VentureRow & {
    website: string | null; founders: string[]; cik: string | null;
    lei: string | null; ch_number: string | null; wikidata_qid: string | null;
    employees: number | null;
  }>(
    `SELECT id, name, country, region, city, sector, verticals, website,
            founders, cik, lei, ch_number, wikidata_qid, employees,
            event_count, first_event_at::text, last_event_at::text,
            total_funding_usd::float8 AS total_funding_usd, founded_date::text
     FROM startup_companies WHERE id = $1 AND excluded IS NULL`, [id]);
  if (!company) return null;
  const [events, patents, patentTotal, research] = await Promise.all([
    q<VentureEvent>(
      `SELECT event_type, event_date::text, amount::float8 AS amount, currency,
              round_label, investors, meta, source, source_url
       FROM startup_events WHERE company_id = $1
       ORDER BY event_date DESC LIMIT 200`, [id]),
    q<VenturePatent>(
      `SELECT l.pub_number, r.title,
              LEAST(r.published_date, NOW())::date::text AS published
       FROM startup_patent_links l
       LEFT JOIN raw_entries r ON r.pub_number = l.pub_number
       WHERE l.company_id = $1 AND l.match_score >= 0.85
       ORDER BY r.published_date DESC NULLS LAST LIMIT 25`, [id]),
    q1<{ n: string }>(
      `SELECT COUNT(*) AS n FROM startup_patent_links
       WHERE company_id = $1 AND match_score >= 0.85`, [id]),
    q<{ openalex_id: string }>(
      `SELECT openalex_id FROM startup_research_links
       WHERE company_id = $1 LIMIT 5`, [id]),
  ]);
  return {
    company, events, patents,
    patentTotal: Number(patentTotal?.n ?? 0),
    researchInstitutions: research.map((r) => r.openalex_id),
  };
}
