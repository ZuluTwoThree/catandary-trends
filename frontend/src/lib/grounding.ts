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
  const bad: string[] = [];
  for (const t of concreteTokens(body)) {
    if (srcRaw.has(t)) continue;
    const n = normToken(t);
    if (srcNorm.has(n)) continue;
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
