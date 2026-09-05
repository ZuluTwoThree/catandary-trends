/**
 * Garbage detector — TypeScript port of pipeline/content_guard.py (#11,
 * 2026-09-05).
 *
 * The review UI flags bodies that are token soup ("M M M M M       仪器(") or
 * carry leaked foreign-script characters ("more than a simple续约") so the
 * reviewer sees WHY a row was held. The verdict itself is made in Python
 * (Stage 6 hard guard, auto-publish gate, draft judge, corpus re-check); this
 * is a deliberate second implementation.
 *
 * ⚠️ Keep in sync with pipeline/content_guard.py — same rules, same thresholds,
 * same reason strings. Both are covered by the same real-body fixtures.
 */

export const MIN_WORDS = 60;
const NON_LATIN_MAX_SHARE = 0.005;
const UNIQUE_WORD_MIN_SHARE = 0.35;
const UNIQUE_WORD_MIN_COUNT = 40;
const NON_WORD_MAX_SHARE = 0.25;

// Letters of scripts that never belong in an English article unless the source
// itself uses them. Greek is intentionally absent (α-synuclein, β-cells, µm).
const NON_LATIN_RE =
  /[Ѐ-ԯ԰-֏֐-׿؀-ۿݐ-ݿऀ-෿฀-๿Ⴀ-ჿᄀ-ᇿ぀-ヿ㄰-㆏㐀-䶿一-鿿가-힯豈-﫿ｦ-ﾟ]/g;

// "fig fig fig fig" — the same word four or more times running.
const WORD_REPEAT_RE = /\b(\w+)(?:\s+\1\b){3,}/i;
// "URLURLURL", "BarBarBar" — a letter group glued to itself three or more
// times. Letters only: "1,000,000" and "000000" must not count.
const GLUED_REPEAT_RE = /(\p{L}{2,}?)\1{2,}/u;
const SPACE_RUN_RE = /[ \t]{6,}/;
const WORD_RE = /[\p{L}\p{N}_]+/gu;
const ALLOWED_PUNCT = new Set(".,;:!?'\"()[]-–—’‘“”„«»%$€£¥&/…+°§*#@=~".split(""));
const ALNUM_RE = /[\p{L}\p{N}]/u;

function pct(x: number, digits: number): string {
  // Python's f"{x:.1%}" / f"{x:.0%}"
  return (x * 100).toFixed(digits) + "%";
}

/**
 * Reasons why `body` is unusable garbage; empty array = looks like prose.
 * `source` enables the script-leak rule (g); without it only the
 * body-intrinsic rules run.
 */
export function garbageReasons(body: string | null | undefined, source?: string | null): string[] {
  const text = (body ?? "").trim();
  if (!text) return ["empty"];
  const reasons: string[] = [];
  const chars = Array.from(text);
  const nChars = chars.length;

  const nonLatin = text.match(NON_LATIN_RE) ?? [];
  const share = nonLatin.length / nChars;
  if (share > NON_LATIN_MAX_SHARE) {
    reasons.push(`non_latin_script:${pct(share, 1)}`);
  } else if (nonLatin.length && source != null) {
    const inSource = new Set(source.match(NON_LATIN_RE) ?? []);
    const leaked = [...new Set(nonLatin)].filter((c) => !inSource.has(c)).sort();
    if (leaked.length) reasons.push("script_leak:" + leaked.slice(0, 8).join(""));
  }

  let m = text.match(WORD_REPEAT_RE);
  if (m) reasons.push(`word_repetition:${m[1]}`);
  m = text.match(GLUED_REPEAT_RE);
  if (m) reasons.push(`glued_repetition:${m[1]}`);

  const words = text.match(WORD_RE) ?? [];
  const nWords = words.length;
  if (nWords < MIN_WORDS) reasons.push(`too_short:${nWords}w`);
  if (nWords >= UNIQUE_WORD_MIN_COUNT) {
    const uniq = new Set(words.map((w) => w.toLowerCase())).size / nWords;
    if (uniq < UNIQUE_WORD_MIN_SHARE) reasons.push(`low_diversity:${pct(uniq, 0)}`);
  }

  let nonWord = 0;
  for (const ch of chars) {
    if (!(ALNUM_RE.test(ch) || /\s/.test(ch) || ALLOWED_PUNCT.has(ch))) nonWord++;
  }
  const nwShare = nonWord / nChars;
  if (nwShare > NON_WORD_MAX_SHARE) reasons.push(`non_word_chars:${pct(nwShare, 0)}`);

  if (SPACE_RUN_RE.test(text)) reasons.push("whitespace_run");
  return reasons;
}

export function isGarbled(body: string | null | undefined, source?: string | null): boolean {
  return garbageReasons(body, source).length > 0;
}
