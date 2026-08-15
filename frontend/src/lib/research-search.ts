/** Smart-Query-Router für das Research-Explorer-Suchfeld (#80).
 *
 *  Erkennt DOIs, arXiv-IDs und Jahre im Freitext und übersetzt sie in echte
 *  Filter — Gegenstück zu patent-search.ts. Reine Funktion, testbar.
 */

export interface ResearchChip {
  kind: "doi" | "arxiv" | "year" | "author" | "institution" | "journal";
  label: string;
}

export interface ParsedResearchQuery {
  text: string;
  /** Normalisierter DOI (kleingeschrieben, ohne URL-Präfix). */
  doi?: string;
  /** arXiv-ID (2504.10470 bzw. mit Version). */
  arxiv?: string;
  /** Anmelder-Operatoren: author:"…" / institution:"…" / journal:"…" */
  author?: string;
  institution?: string;
  journal?: string;
  yearFrom?: number;
  yearTo?: number;
  chips: ResearchChip[];
}

const YEAR_MIN = 2010;
const YEAR_MAX = 2026;

// 10.1038/s41586-021-03819-2 — auch als https://doi.org/…-URL eingefügt
const DOI_RE = /\b(?:https?:\/\/(?:dx\.)?doi\.org\/)?(10\.\d{4,9}\/[^\s"'<>]+)/i;
// 2504.10470, 2504.10470v2, auch "arXiv:2504.10470"
const ARXIV_RE = /\b(?:arxiv:\s*)?(\d{4}\.\d{4,5})(v\d+)?\b/i;
const RANGE_RE = /\b(\d{4})\s*[-–—]\s*(\d{4})\b/;
const YEAR_RE = /\b(\d{4})\b/;

const inRange = (y: number) => y >= YEAR_MIN && y <= YEAR_MAX;

function cut(s: string, start: number, len: number): string {
  return s.slice(0, start) + " ".repeat(len) + s.slice(start + len);
}

export function parseResearchQuery(raw: string): ParsedResearchQuery {
  const out: ParsedResearchQuery = { text: "", chips: [] };
  let rest = (raw ?? "").trim();
  if (!rest) return out;

  // Operatoren zuerst. Mehrteilige Namen: Anführungszeichen ODER Heuristik —
  // ohne Quotes gehören großgeschriebene Folgewörter (Titlecase) zum Namen
  // (author:Jennifer Doudna crispr → Name "Jennifer Doudna", Text "crispr").
  // ALLCAPS (CRISPR) und Kleingeschriebenes bleiben Suchtext; die Chips
  // zeigen die Deutung, Quotes übersteuern (Owner-Befund 2026-08-15).
  // KEIN i-Flag: es würde die Titlecase-Klasse des Namens-Tails aushebeln
  // (dann fräße author:Jennifer Doudna crispr auch "crispr" — Bug 2026-08-15).
  // Case-Toleranz für die Operatornamen stattdessen explizit.
  const NAME_TAIL = String.raw`(?:\s+[A-ZÀ-Þ][a-zà-þß'’-]+)*`;
  for (const [key, re] of [
    ["author", new RegExp(String.raw`\b[Aa](?:uthor|utor|UTHOR|UTOR):\s*("([^"]+)"|(\S+${NAME_TAIL}))`)],
    ["institution", new RegExp(String.raw`\b[Ii](?:nstitution|nst|NSTITUTION|NST):\s*("([^"]+)"|(\S+${NAME_TAIL}))`)],
    ["journal", new RegExp(String.raw`\b(?:[Jj]ournal|JOURNAL|[Ss]ource|SOURCE):\s*("([^"]+)"|(\S+${NAME_TAIL}))`)],
  ] as const) {
    const m = rest.match(re);
    if (!m) continue;
    const value = (m[2] ?? m[3] ?? "").trim();
    if (!value) continue;
    (out as Record<string, unknown>)[key] = value;
    out.chips.push({ kind: key, label: value });
    rest = cut(rest, m.index ?? 0, m[0].length);
  }

  const dm = rest.match(DOI_RE);
  if (dm) {
    // Satzzeichen am Ende sind fast immer Kopier-Artefakte, keine DOI-Teile
    out.doi = dm[1].replace(/[.,;)\]]+$/, "").toLowerCase();
    out.chips.push({ kind: "doi", label: out.doi });
    rest = cut(rest, dm.index ?? 0, dm[0].length);
  } else {
    const am = rest.match(ARXIV_RE);
    // Nur mit arxiv:-Präfix ODER wenn die Zahl kein plausibles Jahr+Zahl-Paar
    // ist — "2019 1234" darf nicht als arXiv-ID verschluckt werden.
    if (am && (am[0].toLowerCase().includes("arxiv") || am[1].length + (am[2]?.length ?? 0) > 0)) {
      const yymm = parseInt(am[1].slice(0, 2), 10);
      const mm = parseInt(am[1].slice(2, 4), 10);
      if (mm >= 1 && mm <= 12 && yymm >= 7) {
        out.arxiv = am[1] + (am[2] ?? "");
        out.chips.push({ kind: "arxiv", label: `arXiv:${out.arxiv}` });
        rest = cut(rest, am.index ?? 0, am[0].length);
      }
    }
  }

  const rm = rest.match(RANGE_RE);
  if (rm) {
    const a = parseInt(rm[1], 10);
    const b = parseInt(rm[2], 10);
    if (inRange(a) && inRange(b)) {
      const [from, to] = a <= b ? [a, b] : [b, a];
      out.yearFrom = from;
      out.yearTo = to;
      out.chips.push({ kind: "year", label: `${from}–${to}` });
      rest = cut(rest, rm.index ?? 0, rm[0].length);
    }
  }
  if (out.yearFrom === undefined) {
    const ym = rest.match(YEAR_RE);
    if (ym && inRange(parseInt(ym[1], 10))) {
      out.yearFrom = out.yearTo = parseInt(ym[1], 10);
      out.chips.push({ kind: "year", label: ym[1] });
      rest = cut(rest, ym.index ?? 0, ym[0].length);
    }
  }

  out.text = rest.replace(/\s+/g, " ").trim();
  return out;
}
