"""Name emerging nests with the local model, and refuse names it cannot support.

Two tags joined by a middot is not a trend name. "Beauty · Beauty Industry" and
"World · Action" say almost nothing, and the second one is in fact a pocket
about world-action models in robotics — the tags simply had no way to say so.

A nest is a handful of documents that sit together, so naming it is a small,
grounded task: read the titles, say what they have in common. That makes it
exactly the kind of job a local model does well and exactly the kind it can
also fake, so every name is checked against the nest's own words before it is
accepted. Anything the check rejects falls back to the deterministic tag label,
and the reason is recorded rather than hidden.

The model never sees the measurements (age, lift, sources). It names, nothing
else — the numbers stay with the code that computed them.
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger("nest_naming")

# Same engine as Research Pulse and Stage 6 (see CLAUDE.md). Explicit rather
# than config.STAGE5_MODEL, whose default is still the 35B.
NAME_MODEL = os.getenv("NEST_NAME_MODEL", "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf")
NAME_SEED = int(os.getenv("NEST_NAME_SEED", "15"))
NAME_TEMPERATURE = float(os.getenv("NEST_NAME_TEMPERATURE", "0.1"))
NAME_MAX_TITLES = 14
NAME_MIN_WORDS = 2
NAME_MAX_WORDS = 7
NAME_MAX_CHARS = 64

SYSTEM_PROMPT = (
    "You name topics. The user gives you titles of documents that a clustering "
    "step put together. Reply with a short, specific name for what they have in "
    "common — the thing itself, not a description of it.\n"
    "Rules, all of them hard:\n"
    "- 2 to 7 words, no final punctuation, no quotation marks, no colon.\n"
    "- Use only words that appear in the titles or tags you were given.\n"
    "- Be specific. 'Machine Learning Research' names nothing; "
    "'Retrieval Augmented Generation' names something.\n"
    "- Do not add a place, a year, a number or a company that is not in the input.\n"
    "- If the titles have nothing specific in common, reply with exactly: NONE"
)

# Words that may appear in a name without being in the nest's own text: they
# carry grammar, not substance.
GLUE = {
    "and", "for", "with", "in", "of", "the", "a", "an", "on", "to", "from",
    "into", "via", "by", "as", "at", "or",
}

# A name made only of these is a category, not a trend.
EMPTY_NAMES = {
    "research", "technology", "innovation", "science", "trends", "studies",
    "development", "analysis", "applications", "systems", "methods", "advances",
    "new technology trends", "emerging technology", "scientific research",
    "machine learning research", "artificial intelligence research",
}


def unshout(title: str) -> str:
    """Patent titles arrive in capitals (DOCDB). Shown to the model like that, it
    answers in kind ("BEAM Measurement Method FOR Three-dimensional Antenna ARRAY",
    30.09.), and a five-letter capital word looks like an acronym to titlecase().
    A title that is mostly capitals goes in as sentence case; tokens with a digit
    (5G, CD137) keep their spelling."""
    letters = [c for c in title if c.isalpha()]
    if len(letters) < 8 or sum(c.isupper() for c in letters) < 0.8 * len(letters):
        return title
    words = []
    for i, w in enumerate(title.split()):
        if any(ch.isdigit() for ch in w):
            words.append(w)
        else:
            low = w.lower()
            words.append(low[:1].upper() + low[1:] if i == 0 else low)
    return " ".join(words)


def build_prompt(titles: list[str], tags: list[str]) -> str:
    lines = ["Tags: " + ", ".join(tags[:10]) if tags else "Tags: none",
             "", "Titles:"]
    for t in titles[:NAME_MAX_TITLES]:
        clean = unshout(re.sub(r"\s+", " ", (t or "").strip()))[:160]
        if clean:
            lines.append(f"- {clean}")
    lines += ["", "Name for what these have in common:"]
    return "\n".join(lines)


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^A-Za-z0-9]+", (text or "").lower()) if w]


def _variants(word: str) -> list[str]:
    """The word and its plausible singular. A pocket that says "battery" can be
    named "Batteries" without the model having invented anything."""
    out = [word]
    if len(word) > 4:
        if word.endswith("ies"):
            out.append(word[:-3] + "y")
        elif word.endswith("es"):
            out.append(word[:-2])
        if word.endswith("s"):
            out.append(word[:-1])
    return out


def titlecase(name: str) -> str:
    """House casing. The model answers "image processing" as readily as
    "Image Processing"; a card must not show both."""
    from pipeline.foresight import ACRONYM_DISPLAY
    out = []
    for w in name.split():
        low = w.lower().strip(".,")
        if low in ACRONYM_DISPLAY:
            out.append(ACRONYM_DISPLAY[low])
        elif low in GLUE and out:
            out.append(low)                     # "for", "and" stay lower mid-name — also "FOR"
        elif w.isupper() and len(w) <= 5:
            out.append(w)                       # RAG, LLM, 5G — as written
        elif w.isupper():
            out.append(w.capitalize())          # patent titles SHOUT; cards do not
        elif low in GLUE and out:
            out.append(low)                     # "for", "and" stay lower mid-name
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def clean_name(raw: str) -> str:
    """Strip the wrapping a chat model likes to add."""
    t = (raw or "").strip()
    t = re.sub(r"^(name|topic|answer)\s*[:\-]\s*", "", t, flags=re.I)
    t = t.split("\n")[0].strip()
    t = t.strip("\"'`*").strip()
    t = re.sub(r"[.;,:]+$", "", t).strip()
    return re.sub(r"\s+", " ", t)


def check_name(name: str, titles: list[str], tags: list[str]) -> str | None:
    """None if the name is usable, otherwise the reason it is not.

    The grounding rule is the same one the article pipeline uses: every word
    that carries meaning has to be in the source. A model that invents
    "Perovskite Tandem Modules" for a pocket that never says "tandem" is
    writing a plausible label for a thing we did not measure."""
    if not name:
        return "empty"
    if name.strip().upper() == "NONE":
        return "model declined"
    if len(name) > NAME_MAX_CHARS:
        return f"{len(name)} characters"
    words = name.split()
    if not (NAME_MIN_WORDS <= len(words) <= NAME_MAX_WORDS):
        return f"{len(words)} words"
    if name.lower() in EMPTY_NAMES:
        return "generic name"
    substantive = [w for w in _words(name) if w not in GLUE]
    if not substantive:
        return "no substance"
    if all(w in EMPTY_NAMES for w in substantive):
        return "generic name"
    blob = " ".join(_words(" ".join(titles) + " " + " ".join(tags)))
    for w in substantive:
        if not any(v in blob for v in _variants(w)):
            return f"word not in the documents: {w}"
    return None


def name_nest(titles: list[str], tags: list[str], chat=None,
              model: str = NAME_MODEL, attempts: int = 2) -> tuple[str | None, str | None]:
    """(name, note). name is None when nothing passed the check."""
    if chat is None:
        from pipeline.llamacpp_client import chat as _chat
        chat = _chat
    prompt = build_prompt(titles, tags)
    last_reason = "no answer"
    for i in range(attempts):
        try:
            raw = chat(model=model, prompt=prompt, system=SYSTEM_PROMPT,
                       temperature=NAME_TEMPERATURE, seed=NAME_SEED + i,
                       max_tokens=32)
        except Exception as exc:                      # server gone, model swapped
            return None, f"model error: {exc.__class__.__name__}"
        name = clean_name(raw)
        reason = check_name(name, titles, tags)
        if reason is None:
            return titlecase(name), None
        last_reason = reason
    return None, last_reason


def name_nests(nests: list[dict], chat=None, model: str = NAME_MODEL,
               progress=None) -> dict:
    """Attach `llm_label` / `llm_label_note` to every nest. Never raises.

    Names must also be unique within a run: two FASHION pockets both came back
    as "Cosmetic Composition" (2026-09-15), which on a page of cards is worse
    than no name at all. The second one keeps its tag label and says why.

    Returns a small summary so the run log can say how many names held up."""
    named = 0
    used: set[str] = set()
    for i, nest in enumerate(nests):
        titles = nest.get("name_titles") or nest.get("rep_titles") or []
        tags = nest.get("top_tags") or []
        name, note = name_nest(titles, tags, chat=chat, model=model)
        if name and name.lower() in used:
            name, note = None, "duplicate of another pocket"
        nest["llm_label"] = name
        nest["llm_label_note"] = note
        if name:
            used.add(name.lower())
            named += 1
        if progress and (i + 1) % 20 == 0:
            progress(i + 1, len(nests))
    logger.info("named %d of %d nests", named, len(nests))
    return {"named": named, "total": len(nests)}
