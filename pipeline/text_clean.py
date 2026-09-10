"""Quelltext entschlacken, bevor er in ein Prompt oder ein Embedding geht.

Manche Feeds legen HTML im Anriss ab (`<p class="wp-block-paragraph">`,
`&#8217;`, ganze Anker-Tags), und der Volltext-Fetcher liefert gelegentlich
Reste davon mit. In einem Prompt frisst das Zeichenbudget ohne Beleg zu tragen;
in einem Embedding verschiebt es den Vektor in Richtung Markup statt Inhalt —
und genau diese Verwechslung von Form und Inhalt war der Befund vom 2026-09-09
(der Vorschlagsraum clusterte Foerderbescheide nach ihrer Satzform).

Der WORTLAUT bleibt unangetastet: Tags raus, Entities aufloesen, Leerraum
normalisieren. Sonst waere der Auszug als Zitat nicht mehr brauchbar
(scripts/corpus_research.py zeigt ihn als Beleg mit „quote from HERE").
"""
from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_BLANKS_RE = re.compile(r"[ \t]*\n\s*\n\s*")


def clean_source_text(text: str | None) -> str:
    """HTML-Tags und Entities raus, Leerraum normalisieren. Wortlaut bleibt."""
    if not text:
        return ""
    return _BLANKS_RE.sub("\n\n", html.unescape(_TAG_RE.sub("", text))).strip()
