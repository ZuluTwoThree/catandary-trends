/** Uni→Industrie-Transfer-Serie aus den PATSTAT-Sektor-Anteilen (#14).
 *
 * Eingabe: tip_sector_shares-Zeilen einer Technologie-Achse. "University"
 * zählt jeden PSN-Sektor, der UNIVERSITY enthält (auch Mischformen wie
 * "GOV NON-PROFIT UNIVERSITY") — die Frage ist "steckt eine Uni dahinter?",
 * nicht "ist es ausschließlich eine Uni?".
 */

export interface SectorShareRow {
  filing_year: number;
  psn_sector: string;
  families: number;
}

export interface TransferPoint {
  year: number;
  total: number;
  university: number;
  /** Anteil 0..1; null wenn das Jahr keine Familien hat */
  uniShare: number | null;
}

export function computeTransferSeries(rows: SectorShareRow[]): TransferPoint[] {
  const byYear = new Map<number, { total: number; university: number }>();
  for (const r of rows) {
    const y = byYear.get(r.filing_year) ?? { total: 0, university: 0 };
    y.total += r.families;
    if (r.psn_sector.toUpperCase().includes("UNIVERSITY")) {
      y.university += r.families;
    }
    byYear.set(r.filing_year, y);
  }
  return [...byYear.entries()]
    .sort(([a], [b]) => a - b)
    .map(([year, { total, university }]) => ({
      year,
      total,
      university,
      uniShare: total > 0 ? university / total : null,
    }));
}
