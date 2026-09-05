"""Garbage detector for generated article bodies (#11, 2026-09-05).

On 2026-09-05 a backlog cycle inserted 22 consecutive drafts whose bodies were
token soup — "M M M M M       仪器(", "original original original fig fig",
"URLURLURL" — with relevance confidence up to 0.93. The content guard in
llm_processor had rejected every one of them, but llamacpp_client.chat_structured
returns the LAST result once the validate budget is spent ("a flagged body beats
None"), so the garbage was stored like any other draft. A further 43 published
bodies from April–June carried the older pattern: an English article with a few
leaked CJK tokens ("more than a simple续约").

This module is the HARD guard those cases were missing. It is deliberately pure
(text in, reasons out; no DB, no pipeline imports) so the same rules run in
Stage 6 (re-roll, never store), the auto-publish gate (hold), the draft judge
(hold, never release), the review UI (TypeScript port, frontend/src/lib/
content-guard.ts — keep in sync) and the corpus re-check script.

Rules (a)–(e) are the owner's specification; (f) and (g) were added because
they are the most distinctive symptoms of the real 22 bodies:

  (a) non-Latin script share > 0.5 % of characters  (Greek excluded — α/β/µ
      are legitimate in science copy)
  (b) repetition: one word ≥ 4× in a row, or a letter group glued to itself
      ≥ 3× ("URLURLURL", "ineineine", "文章文章文章")
  (c) unique-word share < 35 % once the body has ≥ 40 words
  (d) fewer than 60 words
  (e) non-word characters > 25 % of all characters
  (f) a run of ≥ 6 spaces/tabs (the soup is padded with them)
  (g) with a source: non-Latin letters in the body that the source does not
      contain at all — an English article about a Japanese company may quote
      its name in kanji, but "续约" in a PR-Newswire story is a leak

Calibrated 2026-09-05 on 2,615 random published bodies (0 false alarms with
their sources) against the 22 garbage drafts and the 43 CJK-leak articles.
"""
from __future__ import annotations

import re

MIN_WORDS = 60
NON_LATIN_MAX_SHARE = 0.005
UNIQUE_WORD_MIN_SHARE = 0.35
UNIQUE_WORD_MIN_COUNT = 40
NON_WORD_MAX_SHARE = 0.25

# Letters of scripts that never belong in an English article unless the source
# itself uses them. Greek is intentionally absent (α-synuclein, β-cells, µm).
_NON_LATIN_RE = re.compile(
    "["
    "Ѐ-ԯ"   # Cyrillic (+ supplement)
    "԰-֏"   # Armenian
    "֐-׿"   # Hebrew
    "؀-ۿݐ-ݿ"  # Arabic
    "ऀ-෿"   # Devanagari … Sinhala
    "฀-๿"   # Thai
    "Ⴀ-ჿ"   # Georgian
    "ᄀ-ᇿ"   # Hangul Jamo
    "぀-ヿ"   # Hiragana, Katakana
    "㄰-㆏"   # Hangul compatibility Jamo
    "㐀-䶿一-鿿"  # CJK unified ideographs (+ ext A)
    "가-힯"   # Hangul syllables
    "豈-﫿"   # CJK compatibility ideographs
    "ｦ-ﾟ"   # halfwidth Katakana
    "]"
)

# "fig fig fig fig", "Ch Ch Ch Ch" — the same word four or more times running.
_WORD_REPEAT_RE = re.compile(r"\b(\w+)(?:\s+\1\b){3,}", re.IGNORECASE)
# "URLURLURL", "BarBarBar", "ineineine" — a letter group glued to itself three
# or more times. Letters only: "1,000,000" and "000000" must not count.
_GLUED_REPEAT_RE = re.compile(r"([^\W\d_]{2,}?)\1{2,}")
_SPACE_RUN_RE = re.compile(r"[ \t]{6,}")
_WORD_RE = re.compile(r"\w+", re.UNICODE)
# Characters an article legitimately contains besides letters, digits and
# whitespace. Anything else — braces, backslashes, pipes, stray symbols — is
# counted as non-word for rule (e).
_ALLOWED_PUNCT = set(".,;:!?'\"()[]-–—’‘“”„«»%$€£¥&/…+°§*#@=~")


def _words(body: str) -> list[str]:
    return _WORD_RE.findall(body)


def garbage_reasons(body: str | None, source: str | None = None) -> list[str]:
    """Reasons why `body` is unusable garbage; empty list = looks like prose.

    `source` (title + excerpt/full text + extraction) enables rule (g); without
    it only the body-intrinsic rules (a)–(f) run. Callers that have the source
    should pass it — the CJK-leak pattern is otherwise invisible in a long,
    otherwise fluent body (2 leaked characters in 1,700 are 0.1 %).
    """
    text = (body or "").strip()
    if not text:
        return ["empty"]
    reasons: list[str] = []
    n_chars = len(text)

    non_latin = _NON_LATIN_RE.findall(text)
    share = len(non_latin) / n_chars
    if share > NON_LATIN_MAX_SHARE:
        reasons.append(f"non_latin_script:{share:.1%}")
    elif non_latin and source is not None:
        leaked = sorted(set(non_latin) - set(_NON_LATIN_RE.findall(source)))
        if leaked:
            reasons.append("script_leak:" + "".join(leaked[:8]))

    m = _WORD_REPEAT_RE.search(text)
    if m:
        reasons.append(f"word_repetition:{m.group(1)}")
    m = _GLUED_REPEAT_RE.search(text)
    if m:
        reasons.append(f"glued_repetition:{m.group(1)}")

    words = _words(text)
    n_words = len(words)
    if n_words < MIN_WORDS:
        reasons.append(f"too_short:{n_words}w")
    if n_words >= UNIQUE_WORD_MIN_COUNT:
        uniq = len({w.lower() for w in words}) / n_words
        if uniq < UNIQUE_WORD_MIN_SHARE:
            reasons.append(f"low_diversity:{uniq:.0%}")

    non_word = sum(1 for ch in text
                   if not (ch.isalnum() or ch.isspace() or ch in _ALLOWED_PUNCT))
    nw_share = non_word / n_chars
    if nw_share > NON_WORD_MAX_SHARE:
        reasons.append(f"non_word_chars:{nw_share:.0%}")

    if _SPACE_RUN_RE.search(text):
        reasons.append("whitespace_run")
    return reasons


def is_garbled(body: str | None, source: str | None = None) -> bool:
    return bool(garbage_reasons(body, source))
