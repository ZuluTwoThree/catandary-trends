"""Grounding check (#11): detect fabricated specifics in generated bodies.

The content model only ever sees the source excerpt + extracted claims, so any
concrete token (a year, a multi-digit number, a percentage, a money amount) in
the body that does not appear in that source material is fabricated — e.g. an
invented "by 2025" compliance deadline or a made-up percentage. An A/B eval
(scripts/ab_test_prompt.py) measured this at ~1/3 of bodies, and bounded content
re-rolls do not reliably remove it, so the publish gate holds such articles for
review rather than auto-publishing an invented fact.

Kept dependency-free (no pipeline imports) so both llm_processor (the content
re-roll guard) and auto_publisher (the publish gate) can use it without a cycle.
"""
from __future__ import annotations

import re

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_NUM_RE = re.compile(r"\b\d[\d,.]{1,}\b|\b\d+%|[$€£]\s?\d[\d,.]*")


def _concrete_tokens(text: str) -> set[str]:
    out = {m.group(0) for m in _YEAR_RE.finditer(text)}
    for m in _NUM_RE.finditer(text):
        out.add(m.group(0).replace(" ", ""))
    return out


def _norm_token(t: str) -> str:
    """Reduce a number token to its bare digit run for comparison. Strips BOTH
    '.' and ',' — English and German swap their thousands/decimal separators
    ("8,192"=="8.192"==8192; "29.5"=="29,5"), and ~half our sources are German,
    so keeping either separator would flag correct figures as fabricated."""
    for ch in (",", ".", "$", "€", "£", "%", " "):
        t = t.replace(ch, "")
    return t


def ungrounded_specifics(body: str, source: str) -> list[str]:
    """Concrete tokens (year / number / % / money) in `body` that do not appear
    in `source` (title + excerpt + extracted claims). Empty list = grounded.

    The substring allowance keeps false positives low: a body "8,000" is treated
    as grounded when the source says "8,000" (or contains that digit run), so we
    flag genuine inventions, not reformatting."""
    if not body:
        return []
    src_raw = _concrete_tokens(source or "")
    src_norm = {_norm_token(t) for t in src_raw}
    bad: list[str] = []
    for t in _concrete_tokens(body):
        if t in src_raw:
            continue
        n = _norm_token(t)
        if n in src_norm or any(n in s or s in n for s in src_norm if len(n) > 2):
            continue
        bad.append(t)
    return bad
