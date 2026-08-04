/**
 * Grounding check — TypeScript port of pipeline/grounding.py (issue #71).
 *
 * The review UI has to show WHICH tokens the gate objected to, live against the
 * current database. The detection itself lives in Python (it runs inside the
 * publish gate), so this is a deliberate second implementation.
 *
 * ⚠️ Keep in sync with pipeline/grounding.py. Both are covered by the same
 * fixtures — the German number-format case and the substring allowance are the
 * ones that break first if the two drift apart.
 */

const YEAR_RE = /(?<!\d)(?:19|20)\d{2}(?!\d)/g;
// Digit runs bounded by "no adjacent digit/separator" rather than \b.
//
// \b fails on CJK: in "140以上の通貨" both '0' and '以' are word characters, so
// there is no boundary and the number stays invisible — the check then flags a
// figure the (Japanese/Korean/Chinese) source plainly states as fabricated.
// Measured on the live backlog 2026-08-04; it also fixes Korean "2,900만"
// previously being read as the garbage token "2,".
const NUM_RE = /(?<![\d.,])\d[\d.,]*%?|[$€£]\s?\d[\d,.]*/g;

/** Years / numbers / percentages / money amounts appearing in `text`. */
function concreteTokens(text: string): Set<string> {
  const out = new Set<string>();
  for (const m of text.matchAll(YEAR_RE)) out.add(m[0]);
  for (const m of text.matchAll(NUM_RE)) out.add(m[0].replace(/ /g, ""));
  return out;
}

/**
 * Quantities the source states as a WORD, which the body legitimately renders
 * as a numeral. Without this the gate reports its own blind spot as a
 * fabrication: "Around half of melanomas" -> "50% of melanoma cases" was held
 * as invented. Roughly half our sources are German, where this is the norm
 * ("die Hälfte", "ein Viertel", "ein Fünftel", "halbe Milliarde").
 *
 * Only EXACT, unambiguous equivalences belong here — "many" or "most" has no
 * numeric value and must keep failing the check.
 */
const FRACTION_WORDS: [RegExp, string[]][] = [
  [/h[aä]lb\w*|hälfte|\bhalf\b/i, ["50"]],
  [/\bviertel\b|\bquarter\b/i, ["25"]],
  [/\bdrittel\b|\bthird\b/i, ["33", "34"]],
  [/\bfünftel\b|\bfuenftel\b|\bfifth\b/i, ["20"]],
  [/zwei\s+drittel|two[-\s]thirds/i, ["66", "67"]],
  [/drei\s+viertel|three[-\s]quarters/i, ["75"]],
  [/one\s+in\s+five|jede[rn]?\s+fünfte/i, ["20"]],
  [/one\s+in\s+four|jede[rn]?\s+vierte/i, ["25"]],
  [/one\s+in\s+three|jede[rn]?\s+dritte/i, ["33", "34"]],
];

/** Spelled-out cardinals: a German "fünf Milliarden" vs an English "$5 billion". */
const CARDINAL_WORDS: Record<string, string> = {
  one: "1", eins: "1", ein: "1", eine: "1", two: "2", zwei: "2",
  three: "3", drei: "3", four: "4", vier: "4", five: "5", fünf: "5",
  fuenf: "5", six: "6", sechs: "6", seven: "7", sieben: "7", eight: "8",
  acht: "8", nine: "9", neun: "9", ten: "10", zehn: "10", eleven: "11",
  elf: "11", twelve: "12", zwölf: "12", zwanzig: "20", twenty: "20",
};

/** "half a trillion" / "halbe Milliarde" -> the scaled figure the body prints. */
const SCALED_FRACTION_RE =
  /(h[aä]lb\w*|\bhalf\b|\bviertel\b|\bquarter\b|drei\s+viertel|three[-\s]quarters)[\s\w]{0,12}?(milliarde\w*|billion|trillion|billionen|million\w*)/gi;
const SCALE_VALUE: Record<string, string> = { h: "500", v: "250", q: "250", d: "750", t: "750" };

/** Numerals a source implies in words. Source-side only. */
function impliedTokens(text: string): Set<string> {
  const out = new Set<string>();
  if (!text) return out;
  const low = text.toLowerCase();
  for (const [re, values] of FRACTION_WORDS) {
    if (re.test(low)) for (const v of values) out.add(v);
  }
  for (const m of low.matchAll(SCALED_FRACTION_RE)) {
    const v = SCALE_VALUE[m[1][0]];
    if (v) out.add(v);
  }
  for (const [word, digit] of Object.entries(CARDINAL_WORDS)) {
    if (new RegExp(`\\b${word}\\b`, "i").test(low)) out.add(digit);
  }
  return out;
}


/**
 * Digits bound into a NAME are not a quantitative claim: COVID-19, LTG-001,
 * PAC-3, MAI-Cyber-1. Requiring the prefix to be capitalised is what separates
 * these from a real invented figure like "the under-25 demographic", where the
 * lowercase word carries an actual (and in that case fabricated) measurement.
 */
const IDENTIFIER_DIGIT_RE = /(?:\b[A-Z][A-Za-z]*|[A-Z]{2,})-\d[\d.,]*/g;

function identifierDigits(text: string): Set<string> {
  const out = new Set<string>();
  for (const m of (text || "").matchAll(IDENTIFIER_DIGIT_RE)) {
    out.add(m[0].split("-").pop()!);
  }
  return out;
}

/**
 * Reduce a number token to its bare digit run. Strips BOTH '.' and ',' —
 * English and German swap their thousands/decimal separators ("8,192" ==
 * "8.192" == 8192; "29.5" == "29,5"), and roughly half our sources are German,
 * so keeping either separator would flag correct figures as fabricated.
 */
function normToken(t: string): string {
  return t.replace(/[,.$€£% ]/g, "");
}

/**
 * Concrete tokens in `body` that do not appear in `source`. Empty = grounded.
 *
 * The substring allowance keeps false positives low: a body saying "8,000" is
 * grounded when the source contains that digit run, so we flag real inventions
 * rather than reformatting.
 */
export function ungroundedSpecifics(body: string, source: string): string[] {
  if (!body) return [];
  const srcRaw = concreteTokens(source || "");
  const srcNorm = new Set([...srcRaw].map(normToken));
  // Word-implied numerals match EXACTLY and never feed the substring
  // allowance: "fünf" implies "5", and letting a bare "5" ground a body's
  // "150" by substring would gut the check.
  const implied = impliedTokens(source || "");
  const names = identifierDigits(body);
  const bad: string[] = [];
  for (const t of concreteTokens(body)) {
    if (srcRaw.has(t) || names.has(t)) continue;
    const n = normToken(t);
    if (srcNorm.has(n) || implied.has(n)) continue;
    let contained = false;
    if (n.length > 2) {
      for (const s of srcNorm) {
        if (n.includes(s) || s.includes(n)) {
          contained = true;
          break;
        }
      }
    }
    if (!contained) bad.push(t);
  }
  return bad;
}

/**
 * Assemble the grounding source from the material the content model saw:
 * title + excerpt (raw_content when available) + extractive token lists.
 * Mirrors source_from_parts() in pipeline/grounding.py so the UI judges an
 * article by exactly the same standard the publish gate applied.
 */
export function sourceFromParts(
  title: string | null | undefined,
  excerpt: string | null | undefined,
  ...tokenLists: (string[] | null | undefined)[]
): string {
  const parts: string[] = [title || "", excerpt || ""];
  for (const list of tokenLists) {
    if (list && list.length) parts.push(list.map(String).join(" "));
  }
  return parts.filter((p) => p).join(" ");
}
