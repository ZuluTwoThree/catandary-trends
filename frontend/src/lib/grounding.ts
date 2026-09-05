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

import { FIRST_NAMES } from "./first-names";

const YEAR_RE = /(?<!\d)(?:19|20)\d{2}(?!\d)/g;
// Digit runs bounded by "no adjacent digit/separator" rather than \b.
//
// \b fails on CJK: in "140以上の通貨" both '0' and '以' are word characters, so
// there is no boundary and the number stays invisible — the check then flags a
// figure the (Japanese/Korean/Chinese) source plainly states as fabricated.
// Measured on the live backlog 2026-08-04; it also fixes Korean "2,900만"
// previously being read as the garbage token "2,".
const NUM_RE = /(?<![\d.,·])\d[\d.,·]*%?|[$€£]\s?\d[\d,.·]*/g;

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


/**
 * Words whose following number is a DESIGNATOR, not a measurement: "Scope 1
 * emissions", "Article 6 market", "737 MAX 8". A general "capitalised word +
 * space + number" rule would be far too broad — it would also excuse "Under
 * 25" and "August 4" — so this stays an explicit list of terms that name a
 * thing rather than measure one. Heavy in ESG and regulatory copy.
 */
const DESIGNATOR_RE =
  /\b(?:Scope|Article|Artikel|Phase|Tier|Level|Class|Klasse|Type|Typ|Model|Modell|Series|Serie|Chapter|Kapitel|Section|Paragraf|Annex|Anhang|Figure|Abbildung|Table|Tabelle|Stage|Stufe|Grade|Category|Kategorie|MAX|Mark|Version|Gen|Generation|Industry|Industrie|Web)\s+(\d[\d.,]*)/gi;

function designatorDigits(text: string): Set<string> {
  const out = new Set<string>();
  for (const m of (text || "").matchAll(DESIGNATOR_RE)) out.add(m[1]);
  return out;
}

/** "the '80s" and "the 1980s" are the same decade. */
const SHORT_DECADE_RE = /['\u2019](\d0)s\b/g;

/** "2.5 thousand products" in the source vs "2,500 products" in the body. */
const SCALED_NUMBER_RE =
  /(\d+(?:[.,]\d+)?)\s*(thousand|tausend|million\w*|milliarde\w*|billion|trillion)/gi;
const SCALE_FACTOR: [string, number][] = [
  ["thousand", 1e3], ["tausend", 1e3], ["million", 1e6],
  ["milliarde", 1e9], ["billion", 1e9], ["trillion", 1e12],
];

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
  // "the '80s" -> the body's "1980s"; an apostrophised decade means the 20th
  // century in every source we carry.
  for (const m of (text || "").matchAll(SHORT_DECADE_RE)) out.add(`19${m[1]}`);
  // "2.5 thousand products" -> the body's "2,500 products".
  for (const m of low.matchAll(SCALED_NUMBER_RE)) {
    const f = SCALE_FACTOR.find(([k]) => m[2].startsWith(k));
    if (!f) continue;
    const scaled = parseFloat(m[1].replace(",", ".")) * f[1];
    if (Number.isInteger(scaled)) out.add(String(scaled));
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
// The same without a hyphen, digits welded to the name: CO2, SO2, H2O, PM2.5,
// B2B, Inspire360. Requiring them ATTACHED keeps it narrow — "August 4" and
// "Under 25" are separate tokens and stay subject to the check.
const ATTACHED_DIGIT_RE = /\b[A-Z][A-Za-z]*\d[\d.,]*/g;

function identifierDigits(text: string): Set<string> {
  const out = new Set<string>();
  for (const m of (text || "").matchAll(IDENTIFIER_DIGIT_RE)) {
    out.add(m[0].split("-").pop()!);
  }
  for (const m of (text || "").matchAll(ATTACHED_DIGIT_RE)) {
    const d = m[0].match(/\d[\d.,]*/);
    if (d) out.add(d[0]);
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
  // Leading zeros go too: a source dateline "Published online: 04 August 2026"
  // against a body "on August 4, 2026" is the same date, and the day number is
  // too short (1-2 chars) to reach the substring allowance.
  return t.replace(/[,.\u00b7$€£% ]/g, "").replace(/^0+(?=.)/, "");
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
  const names = new Set([...identifierDigits(body), ...designatorDigits(body)]);
  const bad: string[] = [];
  for (const t of concreteTokens(body)) {
    if (srcRaw.has(t) || names.has(t)) continue;
    const n = normToken(t);
    if (srcNorm.has(n) || implied.has(n)) continue;
    let contained = false;
    if (n.length > 2) {
      for (const s of srcNorm) {
        // A short source token would otherwise swallow anything containing it —
        // with leading zeros stripped, "04" would ground an invented "400".
        if (s.length > 2 && (n.includes(s) || s.includes(n))) {
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

// ---------------------------------------------------------------------------
// Person-name grounding — port of ungrounded_names() in pipeline/grounding.py
// (#11, owner review 2026-09-05). "Henkel-Chef Knobel" must not become
// "Henkel CEO Markus Knobel": a capitalised bigram whose first token is a known
// given name (first-names.ts, generated from pipeline/first_names.py) or
// follows a title/role is a PERSON, and every word of it must stand in the
// source. ⚠️ Keep the rules, lists and edge cases identical to the Python.
// ---------------------------------------------------------------------------

const NAME_TOKEN_RE = /\p{L}+(?:[-'’]\p{L}+)*/gu;
const POSSESSIVE_RE = /['’]s$/;

const TITLES = new Set(`
ceo cfo coo cto cio cmo cso president vice chancellor minister ministerin
secretary senator governor mayor commissioner ambassador professor prof dr
doctor mr mrs ms herr frau sir dame lord lady founder co-founder cofounder
chairman chairwoman chairperson chair director analyst economist researcher
spokesperson spokesman spokeswoman author chef kanzler kanzlerin präsident
präsidentin direktor direktorin gründer gründerin sprecher sprecherin
vorstandschef vorstandschefin geschäftsführer geschäftsführerin ministre
président directeur fondateur
`.split(/\s+/).filter(Boolean));

const ABBREV_TITLES = new Set(["dr", "prof", "mr", "mrs", "ms"]);

const PARTICLES = new Set(`
von van de der den del della di da do dos du la le bin ibn al el y of zu zur
ter te af auf und
`.split(/\s+/).filter(Boolean));

const NON_NAME_CAPS = new Set(`
executive officer operating financial technology technical marketing
information security scientific medical digital data product strategy
sustainability innovation investment research development emeritus assistant
associate deputy senior junior general managing director manager minister
president secretary justice court department office ministry council board
committee commission elect institute institutes university college school
hospital bank group inc ltd gmbh ag se plc corp corporation company co motors
systems technologies energy health media capital partners ventures labs
foundation center centre street avenue road square park island islands bay
river lake mountain valley city state county north south east west new united
national international global european american african asian british german
french chinese japanese indian russian spanish italian eastern western northern
southern central federal royal holy saint st mount week day month year report
index prize award act agreement bill law plan summit conference forum festival
games cup league series show tour brand model pro max plus mini air ultra one
two monday tuesday wednesday thursday friday saturday sunday january february
march april may june july august september october november december syndrome
disease disorder effect theorem method process protocol scale test virus kong
space telescope observatory
`.split(/\s+/).filter(Boolean));

// A person's name used as the name of an institution, instrument or brand is
// not a claim about a person ("Justus Liebig University", "James Webb Space
// Telescope"). Owner 2026-09-05: institutions and places are a warning at most.
const ORG_SUFFIX = new Set(`
institute institut institutes university universität universitaet college
school foundation stiftung hospital klinik clinic center centre zentrum space
telescope observatory prize preis award medal lecture street straße strasse
platz airport stadium arena museum library bibliothek laboratory lab labs
company co inc ltd gmbh ag group holding bank capital partners brothers sons
son gesellschaft
`.split(/\s+/).filter(Boolean));

// Person-shaped names that are brands or institutions in this corpus.
const NOT_PERSONS = new Set(
  `eli lilly|james webb|levi strauss|justus liebig|ludwig maximilian|max planck|
robert bosch|robert koch|johns hopkins|wells fargo|goldman sachs|heinrich heine|
albert einstein|carl zeiss|friedrich schiller|johann wolfgang|ernst abbe|
fritz haber|wilhelm röntgen|wilhelm roentgen|ludwig boltzmann|erwin schrödinger|
gottfried wilhelm|marie curie|ralph lauren|calvin klein|tommy hilfiger|hugo boss|
louis vuitton|christian dior|marc jacobs|michael kors|tom ford|jimmy choo|
kate spade|tory burch|paul smith|estee lauder|estée lauder|giorgio armani|
walt disney|warner bros|philip morris|john deere|harley davidson|charles schwab|
franklin templeton|jack daniel|jim beam|johnnie walker|sara lee|betty crocker|
roman space|vera rubin|nancy grace|abu dhabi|hong kong|ben jerry|dolce gabbana|
yves saint|saint laurent|ermenegildo zegna|salvatore ferragamo|stella mccartney|
alexander mcqueen|vivienne westwood|victoria beckham|carolina herrera|
oscar de la renta|jean paul gaultier|thomas cook|marks spencer|procter gamble|
johnson johnson|ernst young|arthur andersen|rolls royce|aston martin|
david lloyd|william hill|harvey nichols|fortnum mason|dean deluca|pret manger|
alfred nobel|leonardo da vinci|george washington|abraham lincoln|thomas jefferson`
    .replace(/\n/g, "")
    .split("|")
);

const isUpper = (ch: string) => ch !== ch.toLowerCase() && ch === ch.toUpperCase();
const isLower = (ch: string) => ch !== ch.toUpperCase() && ch === ch.toLowerCase();

function titleBefore(prev: string, gap: string): boolean {
  const low = prev.toLowerCase().replace(/\.+$/, "");
  if (!TITLES.has(low) || !isUpper(prev[0])) return false;
  if (ABBREV_TITLES.has(low) && prev === prev.toUpperCase() && prev.length > 1) return false;
  const g = gap.trim();
  return g === "" || (g === "." && ABBREV_TITLES.has(low));
}

function namelike(tok: string): boolean {
  tok = tok.replace(POSSESSIVE_RE, "");
  if (tok.length < 2 || !isUpper(tok[0])) return false;
  const rest = Array.from(tok.slice(1));
  if (!rest.some(isLower)) return false;
  if (rest.filter(isUpper).length > 2) return false;
  return !tok.split(/[-'’]/).some((p) => NON_NAME_CAPS.has(p.toLowerCase()));
}

function nameForms(word: string): Set<string> {
  const low = word.toLowerCase().replace(/ß/g, "ss");
  const strip = (s: string) => s.normalize("NFKD").replace(/\p{M}/gu, "");
  const translit = low.replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue");
  return new Set([low, strip(low), strip(translit)]);
}

function sourceWords(source: string): Set<string> {
  const out = new Set<string>();
  for (const m of (source || "").matchAll(NAME_TOKEN_RE)) {
    for (const part of m[0].split(/[-'’]/)) {
      if (part) for (const f of nameForms(part)) out.add(f);
    }
  }
  return out;
}

function inSource(word: string, src: Set<string>): boolean {
  word = word.replace(POSSESSIVE_RE, "");
  for (const part of word.split(/[-'’]/)) {
    if (!part) continue;
    const forms = [...nameForms(part)];
    const ok =
      forms.some((f) => src.has(f)) ||
      forms.some((f) => src.has(f + "s")) ||
      forms.some((f) => f.endsWith("s") && src.has(f.slice(0, -1)));
    if (!ok) return false;
  }
  return true;
}

function isGivenName(tok: string): boolean {
  const low = tok.toLowerCase();
  return FIRST_NAMES.has(low) || FIRST_NAMES.has(low.split("-")[0]);
}

/**
 * Person names in `body` that the source does not contain word for word, each
 * once, in body order. Empty = every person is referred to as the source does.
 */
export function ungroundedNames(body: string, source: string): string[] {
  if (!body) return [];
  const src = sourceWords(source || "");
  const matches = [...body.matchAll(NAME_TOKEN_RE)];
  const toks = matches.map((m) => m[0]);
  const gapBetween = (a: number, b: number) =>
    body.slice(matches[a].index! + toks[a].length, matches[b].index!);
  const adjacent = (a: number, b: number) => gapBetween(a, b).trim() === "";

  const bad: string[] = [];
  const seen = new Set<string>();
  let i = 0;
  while (i < toks.length) {
    const tok = toks[i];
    const low = tok.replace(POSSESSIVE_RE, "").toLowerCase();
    if (!namelike(tok) || NON_NAME_CAPS.has(low) || TITLES.has(low) || PARTICLES.has(low)) {
      i++;
      continue;
    }
    const titled = i > 0 && titleBefore(toks[i - 1], gapBetween(i - 1, i));
    const given = isGivenName(tok);
    if (!(titled || given)) {
      i++;
      continue;
    }
    let j = i + 1;
    while (j < toks.length && PARTICLES.has(toks[j].toLowerCase()) && adjacent(j - 1, j)) j++;
    const hasSurname =
      j < toks.length &&
      adjacent(j - 1, j) &&
      namelike(toks[j]) &&
      !NON_NAME_CAPS.has(toks[j].toLowerCase()) &&
      !TITLES.has(toks[j].toLowerCase());
    let parts: string[];
    let next: number;
    if (hasSurname) {
      parts = toks.slice(i, j + 1);
      next = j + 1;
    } else if (titled) {
      parts = [tok];
      next = i + 1;
    } else {
      i++;
      continue;
    }
    const words = parts.filter((p) => !PARTICLES.has(p.toLowerCase()));
    const name = parts.join(" ").replace(POSSESSIVE_RE, "");
    const key = words.map((w) => w.replace(POSSESSIVE_RE, "").toLowerCase()).join(" ");
    // institution / brand / instrument named after a person → not a person
    const nxt = next < toks.length ? toks[next] : "";
    const gap = nxt ? gapBetween(next - 1, next).trim() : "";
    const org =
      !!nxt &&
      ["", "&", "-", "–", "und", "and"].includes(gap) &&
      ORG_SUFFIX.has(nxt.replace(POSSESSIVE_RE, "").toLowerCase());
    if (org || NOT_PERSONS.has(key)) {
      i = next;
      continue;
    }
    if (words.some((w) => !inSource(w, src)) && !seen.has(name)) {
      bad.push(name);
      seen.add(name);
    }
    i = next;
  }
  return bad;
}
