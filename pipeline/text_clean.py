"""Strip what every abstract shares before a text is embedded (2026-09-28).

Owner: the leading word "Abstract", section labels and HTML remnants must not be
embedded — texts that share them would look similar BECAUSE of the shared
boilerplate, not because of their subject. Measured on 3,000 Food Science /
Nutrition abstracts (OpenAlex): 20 % start with a label ("Background" 287,
"Abstract" 284, "Introduction" 78 ...), structured abstracts carry inline labels
("Results:" 224, "Methods:" 164, "Conclusion:" 142, upper-case variants as many
again), 12 % hold markup (<i> 412, <sup> 86, <scp> 68, JATS tags, and whole tags
escaped as &lt;...&gt;), 31 end in a copyright line.

What it does, in this order:
  1. unescape entities twice (JATS arrives as &amp;lt;jats:p&amp;gt; as well),
  2. drop tags — only things that LOOK like a tag: "<" directly followed by a
     letter. "p < 0.05" and "x<0.1" survive,
  3. drop copyright tails ("© 2024 Elsevier ...", "This article is protected by
     copyright. All rights reserved."),
  4. drop section labels: any number of them at the start ("Abstract Background:"),
     and inline ones when followed by a colon ("... Results: ..."),
  5. collapse whitespace.

Content words are never touched: "Keywords: a, b" keeps a, b; a label word inside
a sentence ("the results were") stays because only "Label:" is removed inline.
"""
from __future__ import annotations

import html
import re

LABELS = (
    "abstract", "graphical abstract", "summary", "background", "backgrounds", "introduction",
    "context", "objective", "objectives", "aim", "aims", "purpose", "rationale", "importance",
    "method", "methods", "methodology", "materials and methods", "material and methods",
    "design", "setting", "settings", "participants", "subjects", "interventions",
    "main outcome measures", "measurements", "result", "results", "findings",
    "conclusion", "conclusions", "discussion", "interpretation", "significance",
    "implications", "limitations", "highlights", "keywords", "key words",
)
_LABEL_ALT = "|".join(sorted((re.escape(x) for x in LABELS), key=len, reverse=True))

_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9:_-]*(?:\s[^<>]{0,200})?/?>")
_COPYRIGHT = re.compile(
    r"(?:\s*(?:©|\(c\)|copyright\b)[^.]*(?:\.|$).*$)"
    r"|(?:\s*this article is protected by copyright\..*$)"
    r"|(?:\s*all rights reserved\.?\s*$)",
    re.IGNORECASE | re.DOTALL,
)
# at the start: a label, then ":", ".", a dash, or just a space before a capital/digit
_LEAD = re.compile(rf"^\s*(?:{_LABEL_ALT})\b\s*(?:[:.\-–—]\s*|\s+(?=(?-i:[A-Z0-9\"'(])))", re.IGNORECASE)
# inline: only "Label:" (a colon makes it a heading, not a word in a sentence)
_INLINE = re.compile(rf"(?<![A-Za-z])(?:{_LABEL_ALT})\s*:\s*", re.IGNORECASE)
_WS = re.compile(r"\s+")


# --- clean_source_text: the module's first function (#102, 2026-09-10) -------------
# Kept verbatim. It keeps the WORDING (tags out, entities resolved, whitespace
# normalised) so an excerpt stays quotable; clean_text() below goes further and
# removes shared boilerplate before an embedding. No caller left since the
# dossier removal (19.09.), kept so nothing disappears silently.
_TAG_RE = re.compile(r"<[^>]+>")
_BLANKS_RE = re.compile(r"[ \t]*\n\s*\n\s*")


def clean_source_text(text: str | None) -> str:
    """HTML-Tags und Entities raus, Leerraum normalisieren. Wortlaut bleibt."""
    if not text:
        return ""
    return _BLANKS_RE.sub("\n\n", html.unescape(_TAG_RE.sub("", text))).strip()


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    t = html.unescape(html.unescape(text))
    t = _TAG.sub(" ", t)
    t = _COPYRIGHT.sub("", t)
    for _ in range(4):                 # "Abstract Background: ..." — labels can stack
        new = _LEAD.sub("", t, count=1)
        if new == t:
            break
        t = new
    t = _INLINE.sub(" ", t)
    return _WS.sub(" ", t).strip()


def embed_text(title: str | None, body: str | None, max_body: int | None = 500) -> str:
    """The text the embedder sees: cleaned title + cleaned body, cut AFTER cleaning
    (so boilerplate never eats the budget). `max_body=None` keeps the whole body."""
    b = clean_text(body)
    if max_body is not None:
        b = b[:max_body]
    return f"{clean_text(title)}\n{b}"
