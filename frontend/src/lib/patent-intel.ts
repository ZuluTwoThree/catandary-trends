/** Reine Rechenfunktionen für das Technology-Intelligence-Panel (#75).
 *  Eingaben sind die tip_*-Referenztabellen aus den PATSTAT-TIP-Runden. */

export interface NplRow { publn_year: number; citations: number; npl_citations: number }
export interface SurvivalRow { filing_year: number; cohort_size: number; age_years: number; cessations: number }
export interface CountryRow { filing_year: number; ctry: string; families: number }
export interface OppositionRow { event_year: number; event_code: string; applications: number }
export interface GroupRow { cpc_group: string; filing_year: number; families: number }

/** NPL-Anteil (0..1) für ein Jahr; null wenn Jahr fehlt oder leer. */
export function nplShare(rows: NplRow[], year: number): number | null {
  const r = rows.find((x) => x.publn_year === year);
  return r && r.citations > 0 ? r.npl_citations / r.citations : null;
}

/** Anteil der Kohorte, der binnen `age` Jahren fallengelassen wurde (0..1).
 *  age_years -1 (Kohorte ohne Cease-Events) zählt als 0 Cessations. */
export function ceasedWithin(rows: SurvivalRow[], filingYear: number, age: number): number | null {
  const cohort = rows.filter((r) => r.filing_year === filingYear);
  if (cohort.length === 0) return null;
  const size = cohort[0].cohort_size;
  if (size <= 0) return null;
  const ceased = cohort
    .filter((r) => r.age_years >= 0 && r.age_years < age)
    .reduce((s, r) => s + r.cessations, 0);
  return ceased / size;
}

/** Top-N Länder eines Anmeldejahres mit Anteil (0..1) an allen gelisteten
 *  Familien des Jahres. */
export function topCountries(
  rows: CountryRow[], year: number, n: number,
): { ctry: string; families: number; share: number }[] {
  const inYear = rows.filter((r) => r.filing_year === year);
  const total = inYear.reduce((s, r) => s + r.families, 0);
  if (total === 0) return [];
  return [...inYear]
    .sort((a, b) => b.families - a.families)
    .slice(0, n)
    .map((r) => ({ ctry: r.ctry, families: r.families, share: r.families / total }));
}

/** Anteil eines Landes in einem Jahr (0..1); null wenn Jahr leer. */
export function countryShare(rows: CountryRow[], year: number, ctry: string): number | null {
  const inYear = rows.filter((r) => r.filing_year === year);
  const total = inYear.reduce((s, r) => s + r.families, 0);
  if (total === 0) return null;
  return (inYear.find((r) => r.ctry === ctry)?.families ?? 0) / total;
}

/** EP-Einspruchsquote je Jahr: 26 / (26 + 26N). */
export function oppositionRate(rows: OppositionRow[], year: number): number | null {
  const opposed = rows.find((r) => r.event_year === year && r.event_code === "26")?.applications ?? 0;
  const not = rows.find((r) => r.event_year === year && r.event_code === "26N")?.applications ?? 0;
  return opposed + not > 0 ? opposed / (opposed + not) : null;
}

/** Wachstumsstärkste CPC-Hauptgruppen: mittlere Familien/Jahr der letzten
 *  `recentYears` Jahre vs. der Basisperiode davor. Nur Gruppen mit
 *  Substanz in der Basis (>= minBase im Schnitt), sonst dominieren
 *  Neu-Codes mit Quasi-Null-Basis die Liste. */
export function emergingGroups(
  rows: GroupRow[], splitYear: number, n: number, minBase = 20,
): { group: string; recentAvg: number; baseAvg: number; growth: number }[] {
  const byGroup = new Map<string, GroupRow[]>();
  for (const r of rows) {
    (byGroup.get(r.cpc_group) ?? byGroup.set(r.cpc_group, []).get(r.cpc_group)!).push(r);
  }
  const out: { group: string; recentAvg: number; baseAvg: number; growth: number }[] = [];
  for (const [group, g] of byGroup) {
    const base = g.filter((r) => r.filing_year < splitYear);
    const recent = g.filter((r) => r.filing_year >= splitYear);
    if (base.length === 0 || recent.length === 0) continue;
    const baseAvg = base.reduce((s, r) => s + r.families, 0) / base.length;
    const recentAvg = recent.reduce((s, r) => s + r.families, 0) / recent.length;
    if (baseAvg < minBase) continue;
    out.push({ group, baseAvg, recentAvg, growth: recentAvg / baseAvg - 1 });
  }
  return out.sort((a, b) => b.growth - a.growth).slice(0, n);
}
