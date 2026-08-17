/** Smart-Query-Router für das Research-Explorer-Suchfeld (#80).
 *
 *  Erkennt DOIs, arXiv-IDs und Jahre im Freitext und übersetzt sie in echte
 *  Filter — Gegenstück zu patent-search.ts. Reine Funktion, testbar.
 */

export interface ResearchChip {
  kind: "doi" | "arxiv" | "year" | "author" | "institution" | "journal" | "funder" | "country";
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
  funder?: string;
  /** Zwei-Buchstaben-Ländercode (Lead-Institution). */
  country?: string;
  yearFrom?: number;
  yearTo?: number;
  chips: ResearchChip[];
}

/* ---------- Typeahead (#83) ---------- */

export interface TypeaheadContext {
  kind: "author" | "institution" | "journal" | "funder";
  /** Index des Operator-Beginns im Text (für den Ersatz beim Auswählen). */
  opStart: number;
  /** Das getippte Operator-Wort (Original-Schreibweise, ohne ":"). */
  opWord: string;
  /** Bereits getippter (Teil-)Wert hinter dem Operator. */
  value: string;
}

const TYPEAHEAD_RE =
  /(author|autor|institution|inst|journal|source|funder|förderer|foerderer):\s*"?([^":]*)$/i;
const TYPEAHEAD_KIND: Record<string, TypeaheadContext["kind"]> = {
  author: "author", autor: "author",
  institution: "institution", inst: "institution",
  journal: "journal", source: "journal",
  funder: "funder", förderer: "funder", foerderer: "funder",
};

/** Erkennt, ob der Nutzer gerade einen Operator-Wert tippt (Textende).
 *  Case-insensitiv ist hier richtig — anders als beim Parsen fertiger
 *  Queries geht es nur um den Operator-Präfix, nie um Namens-Heuristik. */
export function typeaheadContext(text: string): TypeaheadContext | null {
  const m = text.match(TYPEAHEAD_RE);
  if (!m || m.index === undefined) return null;
  const kind = TYPEAHEAD_KIND[m[1].toLowerCase()];
  if (!kind) return null;
  return { kind, opStart: m.index, opWord: m[1], value: m[2].trim() };
}

/** Baut den Text nach Auswahl eines Vorschlags: Operator-Wert wird durch
 *  den gequoteten Vorschlag ersetzt, Rest bleibt stehen. */
export function applyTypeahead(
  text: string, ctx: TypeaheadContext, chosen: string,
): string {
  return `${text.slice(0, ctx.opStart)}${ctx.opWord}:"${chosen}" `;
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
    ["funder", new RegExp(String.raw`\b(?:[Ff]under|FUNDER|[Ff]örderer|[Ff]oerderer):\s*("([^"]+)"|(\S+${NAME_TAIL}))`)],
  ] as const) {
    const m = rest.match(re);
    if (!m) continue;
    const value = (m[2] ?? m[3] ?? "").trim();
    if (!value) continue;
    out[key] = value;
    out.chips.push({ kind: key, label: value });
    rest = cut(rest, m.index ?? 0, m[0].length);
  }

  const cm = rest.match(/\b[Cc](?:ountry|OUNTRY):\s*([A-Za-z]{2})\b/);
  if (cm) {
    out.country = cm[1].toUpperCase();
    out.chips.push({ kind: "country", label: out.country });
    rest = cut(rest, cm.index ?? 0, cm[0].length);
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
