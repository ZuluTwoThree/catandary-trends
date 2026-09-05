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

_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
# Digit runs bounded by "no adjacent digit/separator" rather than \b.
#
# \b fails on CJK: in "140以上の通貨" both '0' and '以' are word characters, so
# there is no boundary and the number stays invisible — the check then flags a
# figure the (Japanese/Korean/Chinese) source plainly states as fabricated.
# Measured on the live backlog 2026-08-04; it also fixes Korean "2,900만"
# previously being read as the garbage token "2,".
_NUM_RE = re.compile(r"(?<![\d.,\u00b7])\d[\d.,\u00b7]*%?|[$€£]\s?\d[\d,.\u00b7]*")


def _concrete_tokens(text: str) -> set[str]:
    out = {m.group(0) for m in _YEAR_RE.finditer(text)}
    for m in _NUM_RE.finditer(text):
        out.add(m.group(0).replace(" ", ""))
    return out


# Quantities the source states as a WORD, which the body legitimately renders as
# a numeral. Without this the gate reports its own blind spot as a fabrication:
# "Around half of melanomas" -> "50% of melanoma cases" was held as invented.
# Roughly half our sources are German, where this is the norm ("die Hälfte",
# "ein Viertel", "ein Fünftel", "halbe Milliarde").
#
# Only EXACT, unambiguous equivalences belong here. A word like "many" or
# "most" has no numeric value and must keep failing the check.
_FRACTION_WORDS: dict[str, tuple[str, ...]] = {
    # fraction -> the percentages a body may reasonably write for it
    r"h[aä]lb\w*|hälfte|\bhalf\b": ("50",),
    r"\bviertel\b|\bquarter\b": ("25",),
    r"\bdrittel\b|\bthird\b": ("33", "34"),
    r"\bfünftel\b|\bfuenftel\b|\bfifth\b": ("20",),
    r"zwei\s+drittel|two[-\s]thirds": ("66", "67"),
    r"drei\s+viertel|three[-\s]quarters": ("75",),
    # "one in five" / "jeder Fünfte" style ratios
    r"one\s+in\s+five|jede[rn]?\s+fünfte": ("20",),
    r"one\s+in\s+four|jede[rn]?\s+vierte": ("25",),
    r"one\s+in\s+three|jede[rn]?\s+dritte": ("33", "34"),
}

# Cardinals spelled out. Needed because a German source writes "fünf Milliarden
# US-Dollar" where the English body writes "$5 billion".
_CARDINAL_WORDS: dict[str, str] = {
    "one": "1", "eins": "1", "ein": "1", "eine": "1",
    "two": "2", "zwei": "2", "three": "3", "drei": "3",
    "four": "4", "vier": "4", "five": "5", "fünf": "5", "fuenf": "5",
    "six": "6", "sechs": "6", "seven": "7", "sieben": "7",
    "eight": "8", "acht": "8", "nine": "9", "neun": "9",
    "ten": "10", "zehn": "10", "eleven": "11", "elf": "11",
    "twelve": "12", "zwölf": "12", "zwanzig": "20", "twenty": "20",
}

# A fraction directly modifying a magnitude ("half a trillion", "halbe
# Milliarde") yields the scaled figure the body prints: 500 / 250 / 750.
_SCALED_FRACTION_RE = re.compile(
    r"(h[aä]lb\w*|\bhalf\b|\bviertel\b|\bquarter\b|drei\s+viertel|three[-\s]quarters)"
    r"[\s\w]{0,12}?(milliarde\w*|billion|trillion|billionen|million\w*)",
    re.IGNORECASE,
)
_SCALE_VALUE = {"h": "500", "v": "250", "q": "250", "d": "750", "t": "750"}


def _implied_tokens(text: str) -> set[str]:
    """Numerals a source implies in words. Source-side only — a body that spells
    a figure out is not making a claim the check needs to police."""
    if not text:
        return set()
    low = text.lower()
    out: set[str] = set()
    for pattern, values in _FRACTION_WORDS.items():
        if re.search(pattern, low, re.IGNORECASE):
            out.update(values)
    for m in _SCALED_FRACTION_RE.finditer(low):
        out.add(_SCALE_VALUE.get(m.group(1)[0], ""))
    for word, digit in _CARDINAL_WORDS.items():
        if re.search(rf"\b{word}\b", low):
            out.add(digit)
    # "the '80s" -> the body's "1980s"; assume the 20th century, which is what
    # an apostrophised decade means in every source we carry.
    for m in _SHORT_DECADE_RE.finditer(text or ""):
        out.add(f"19{m.group(1)}")
    # "2.5 thousand products" -> the body's "2,500 products".
    for m in _SCALED_NUMBER_RE.finditer(low):
        factor = next((v for k, v in _SCALE_FACTOR.items() if m.group(2).startswith(k)), 0)
        if factor:
            value = float(m.group(1).replace(",", "."))
            scaled = value * factor
            if scaled == int(scaled):
                out.add(str(int(scaled)))
    out.discard("")
    return out


# Digits bound into a NAME are not a quantitative claim: COVID-19, LTG-001,
# PAC-3, MAI-Cyber-1. Requiring the prefix to be capitalised is what separates
# these from a real invented figure like "the under-25 demographic", where the
# lowercase word carries an actual (and in that case fabricated) measurement.
_IDENTIFIER_DIGIT_RE = re.compile(r"(?:\b[A-Z][A-Za-z]*|[A-Z]{2,})-\d[\d.,]*")

# The same thing without a hyphen, where the digits are welded to the name:
# CO2, SO2, H2O, PM2.5, B2B, Inspire360, COVID19. Requiring the digits to be
# ATTACHED (no space, no hyphen) is what keeps this narrow — "August 4" and
# "Under 25" are separate tokens and stay subject to the check.
_ATTACHED_DIGIT_RE = re.compile(r"\b[A-Z][A-Za-z]*\d[\d.,]*")


# Words whose following number is a DESIGNATOR, not a measurement: "Scope 1
# emissions", "Article 6 market", "737 MAX 8", "Phase 2 results". A general
# "capitalised word + space + number" rule would be far too broad — it would
# also excuse "Under 25" and "August 4" — so this stays an explicit list of
# terms that name a thing rather than measure one. Heavy in ESG and regulatory
# copy, which is a large share of this corpus.
_DESIGNATOR_RE = re.compile(
    r"\b(?:Scope|Article|Artikel|Phase|Tier|Level|Class|Klasse|Type|Typ|Model|"
    r"Modell|Series|Serie|Chapter|Kapitel|Section|Paragraf|Annex|Anhang|Figure|"
    r"Abbildung|Table|Tabelle|Stage|Stufe|Grade|Category|Kategorie|MAX|Mark|"
    r"Version|Gen|Generation|Industry|Industrie|Web)\s+(\d[\d.,]*)",
    re.IGNORECASE,
)

# "the '80s" and "the 1980s" are the same decade. Without this the body's
# expanded form reads as a fabricated year.
_SHORT_DECADE_RE = re.compile(r"['’](\d0)s\b")

# "2.5 thousand products" in the source vs "2,500 products" in the body.
_SCALED_NUMBER_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(thousand|tausend|million\w*|milliarde\w*|billion|trillion)",
    re.IGNORECASE,
)
_SCALE_FACTOR = {"thousand": 1_000, "tausend": 1_000, "million": 1_000_000,
                 "milliarde": 1_000_000_000, "billion": 1_000_000_000,
                 "trillion": 1_000_000_000_000}


def _designator_digits(text: str) -> set[str]:
    """Numbers that name a thing rather than measure one."""
    return {m.group(1) for m in _DESIGNATOR_RE.finditer(text or "")}


def _identifier_digits(text: str) -> set[str]:
    """Digit runs that occur only as part of a capitalised identifier."""
    out: set[str] = set()
    for m in _IDENTIFIER_DIGIT_RE.finditer(text or ""):
        out.add(m.group(0).split("-")[-1])
    for m in _ATTACHED_DIGIT_RE.finditer(text or ""):
        digits = re.search(r"\d[\d.,]*", m.group(0))
        if digits:
            out.add(digits.group(0))
    return out


def _norm_token(t: str) -> str:
    """Reduce a number token to its bare digit run for comparison. Strips BOTH
    '.' and ',' — English and German swap their thousands/decimal separators
    ("8,192"=="8.192"==8192; "29.5"=="29,5"), and ~half our sources are German,
    so keeping either separator would flag correct figures as fabricated. The
    Lancet and other medical journals use a MIDDLE DOT ("13·4%") — same
    reason, else every clinical figure from those sources reads as invented.

    Leading zeros go too. A source dateline "Published online: 04 August 2026"
    against a body "on August 4, 2026" is the same date, and without this the
    day number reads as a fabricated figure — the day is too short (1-2 chars)
    to reach the substring allowance."""
    for ch in (",", ".", "\u00b7", "$", "€", "£", "%", " "):
        t = t.replace(ch, "")
    return t.lstrip("0") or "0"


def source_from_parts(title: str | None, excerpt: str | None, *token_lists) -> str:
    """Assemble the grounding source from the material the content model saw:
    title + excerpt (raw_content when available) + any extractive token lists
    (key_claims, key_figures, dates, quotes, geography). Centralising this keeps
    the content re-roll guard and the auto-publish gate in sync (#11) — the gate
    must check the body against the SAME specifics the model was given, otherwise
    a figure present only in the full text gets falsely flagged as fabricated."""
    parts: list[str] = [title or "", excerpt or ""]
    for lst in token_lists:
        if lst:
            parts.append(" ".join(str(x) for x in lst))
    return " ".join(p for p in parts if p)


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
    # Word-implied numerals match EXACTLY and never feed the substring
    # allowance: "fünf" implies "5", and letting a bare "5" ground a body's
    # "150" by substring would gut the check.
    implied = _implied_tokens(source or "")
    names = _identifier_digits(body) | _designator_digits(body)
    bad: list[str] = []
    for t in _concrete_tokens(body):
        if t in src_raw or t in names:
            continue
        n = _norm_token(t)
        if n in src_norm or n in implied:
            continue
        # Both sides must be long enough. A short source token would otherwise
        # swallow anything containing it — with leading zeros stripped, a
        # source "04" would ground a body's invented "400".
        if len(n) > 2 and any(len(s) > 2 and (n in s or s in n) for s in src_norm):
            continue
        bad.append(t)
    return bad

# --- Deterministic figure extraction (2026-08-21) ---------------------------
# Measured on 14 articles: asking the 8B for key_figures yielded 44 items of
# which exactly ONE was both verbatim and actually a number. The model does not
# extract tokens, it writes summarising sentences ("Over £13 billion lost on the
# FTSE 100") — correct in substance, but its own words, so a verbatim check
# rejects them and the grounding gate cannot use them. A regex finds 188 figures
# across the same articles, all verbatim by construction, at zero GPU cost.
#
# The snippet matters as much as the number: "$70" alone tells a writer nothing,
# while the sentence it sits in is evidence. Both come straight from the source,
# so nothing here can invent anything.

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_TAG_RE = re.compile(r"<[^>]+>")


def figures_with_context(text: str, limit: int = 10, window: int = 160) -> list[str]:
    """Figures from `text`, each with the verbatim sentence around it.

    Ordered by information density (most distinct figures first), deduplicated
    per sentence, capped at `limit`. Returns [] for empty input.
    """
    if not text:
        return []
    clean = _TAG_RE.sub(" ", text)
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for sent in _SENT_SPLIT.split(clean):
        sent = " ".join(sent.split())
        if not sent or len(sent) < 8:
            continue
        toks = _concrete_tokens(sent)
        if not toks:
            continue
        if len(sent) > window:
            # keep the part around the first figure rather than a blunt prefix
            first = min((sent.find(t) for t in toks if sent.find(t) >= 0), default=0)
            start = max(0, first - window // 3)
            sent = ("…" if start else "") + sent[start:start + window].rstrip() + "…"
        key = sent.lower()
        if key in seen:
            continue
        seen.add(key)
        scored.append((len(toks), sent))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:limit]]

def _norm_for_match(s: str) -> str:
    """Whitespace and typographic variants unified, so the check fails on real
    divergence rather than on a line break or a curly apostrophe."""
    s = s.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u00a0", " ")
    return " ".join(s.split()).lower()


def verbatim_only(items: list[str], source: str) -> list[str]:
    """Keep only entries that actually appear in `source`.

    Applied to quotes and geography, where verbatim copying is both expected and
    achievable. NOT to key_claims: a claim is meant to condense, so requiring it
    verbatim would empty the field. And not to key_figures either — those no
    longer come from the model at all (figures_with_context).
    """
    if not items or not source:
        return []
    src = _norm_for_match(source)
    return [it for it in items
            if it and len(it.strip()) > 1 and _norm_for_match(it) in src]



# --- Person-name grounding (#11, 2026-09-05) --------------------------------
# Owner review 05.09.: the content model turns "Henkel-Chef Knobel" into
# "Henkel CEO Markus Knobel" (real: Carsten). Numbers were policed, names were
# not — a proxy count found foreign proper names in 7–18 % of published bodies.
# Rule: a capitalised bigram "Given Surname" whose first token is a known given
# name (pipeline.first_names) or follows a title/role (CEO, Minister, Dr.) is a
# PERSON, and every word of it must stand in the source. Generic capitalised
# bigrams ("Storage System", "Middle Eastern") never trigger because "Storage"
# is not a given name and nothing titles it.
import unicodedata

from pipeline.first_names import FIRST_NAMES

_NAME_TOKEN_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*")
_POSSESSIVE_RE = re.compile(r"['’]s$")

# A role word right before a capitalised word makes that word a person even
# when the given name is unknown or absent ("CEO Knobel", "Minister Xu").
_TITLES = frozenset("""
ceo cfo coo cto cio cmo cso president vice chancellor minister ministerin
secretary senator governor mayor commissioner ambassador professor prof dr
doctor mr mrs ms herr frau sir dame lord lady founder co-founder cofounder
chairman chairwoman chairperson chair director analyst economist researcher
spokesperson spokesman spokeswoman author chef kanzler kanzlerin präsident
präsidentin direktor direktorin gründer gründerin sprecher sprecherin
vorstandschef vorstandschefin geschäftsführer geschäftsführerin ministre
président directeur fondateur
""".split())

# Name particles that may sit between given name and surname.
_PARTICLES = frozenset("""
von van de der den del della di da do dos du la le bin ibn al el y of zu zur
ter te af auf und
""".split())

# Capitalised words that are never the surname (or given name) of a person in
# this check — role words, organisations, places, dates, demonyms. They stop a
# title from capturing "Chief Executive Officer" and a given name from capturing
# "Emma Foundation".
_NON_NAME_CAPS = frozenset("""
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
""".split())

# A person's name used as the name of an institution, instrument or brand is
# not a claim about a person: "Justus Liebig University", "James Webb Space
# Telescope", "Max Planck Institute". Owner 2026-09-05: institutions and
# places are a warning at most, never a hold.
_ORG_SUFFIX = frozenset("""
institute institut institutes university universität universitaet college
school foundation stiftung hospital klinik clinic center centre zentrum space
telescope observatory prize preis award medal lecture street straße strasse
platz airport stadium arena museum library bibliothek laboratory lab labs
company co inc ltd gmbh ag group holding bank capital partners brothers sons
son gesellschaft
""".split())

# Person-shaped names that are brands or institutions in this corpus (the
# 2026-09-05 sweep: "Eli Lilly" 35×, "James Webb" 11×, "Levi Strauss" 4×).
_NOT_PERSONS = frozenset("""
eli lilly|james webb|levi strauss|justus liebig|ludwig maximilian|max planck|
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
alfred nobel|leonardo da vinci|george washington|abraham lincoln|thomas jefferson
""".replace("\n", "").split("|"))


_ABBREV_TITLES = frozenset({"dr", "prof", "mr", "mrs", "ms"})


def _title_before(prev: str, gap: str) -> bool:
    """`prev` is used as a TITLE for the word that follows: capitalised role
    word ("CEO", "Minister", "Chef", "Dr.") with only whitespace in between —
    or a period, but only for abbreviations ("Dr. Oetker"). A lowercase
    "doctor." ending the previous sentence titles nothing, and an all-caps
    "DR Congo" / "MS Office" is not "Dr"/"Ms"."""
    low = prev.lower().rstrip(".")
    if low not in _TITLES or not prev[0].isupper():
        return False
    if low in _ABBREV_TITLES and prev.isupper() and len(prev) > 1:
        return False
    gap = gap.strip()
    return gap == "" or (gap == "." and low in _ABBREV_TITLES)


def _namelike(tok: str) -> bool:
    """Capitalised word with lowercase continuation: 'Knobel', 'McDonald',
    'O’Brien', 'Jean-Claude' — but not 'AI', 'NASA', 'POSTECH’s' or 'iPhone',
    and not a hyphenated compound with an organisation word in it
    ('Heinrich-Heine-University')."""
    tok = _POSSESSIVE_RE.sub("", tok)
    if len(tok) < 2 or not tok[0].isupper():
        return False
    rest = tok[1:]
    if not any(ch.islower() for ch in rest):
        return False
    # at most one further capital: McDonald, DeSantis, O’Brien, Jean-Claude
    if sum(1 for ch in rest if ch.isupper()) > 2:
        return False
    return not any(p.lower() in _NON_NAME_CAPS for p in re.split(r"[-'’]", tok))


def _name_forms(word: str) -> set[str]:
    """Comparable spellings: lowercase, diacritics stripped, and the German
    transliteration (Müller → mueller), so 'Mueller' and 'Muller' both match."""
    low = word.lower().replace("ß", "ss")
    stripped = "".join(ch for ch in unicodedata.normalize("NFKD", low)
                       if not unicodedata.combining(ch))
    translit = (low.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue"))
    translit = "".join(ch for ch in unicodedata.normalize("NFKD", translit)
                       if not unicodedata.combining(ch))
    return {low, stripped, translit}


def _source_words(source: str) -> set[str]:
    out: set[str] = set()
    for tok in _NAME_TOKEN_RE.findall(source or ""):
        for part in re.split(r"[-'’]", tok):
            if part:
                out |= _name_forms(part)
    return out


def _in_source(word: str, src: set[str]) -> bool:
    word = _POSSESSIVE_RE.sub("", word)
    for part in re.split(r"[-'’]", word):
        if not part:
            continue
        forms = _name_forms(part)
        # plain, possessive ("Knobels Strategie" / "Knobel's") either way
        if not (forms & src or {f + "s" for f in forms} & src
                or {f[:-1] for f in forms if f.endswith("s")} & src):
            return False
    return True


def _is_given_name(tok: str) -> bool:
    low = tok.lower()
    return low in FIRST_NAMES or low.split("-")[0] in FIRST_NAMES


def ungrounded_names(body: str, source: str) -> list[str]:
    """Person names in `body` that the source does not contain word for word.

    Returns each offending name once ("Markus Knobel"), in body order. Empty
    list = every person is referred to as the source refers to them. Only
    checks what the rule can see: given name + surname bigrams (with
    particles: "Ursula von der Leyen") and title-introduced names ("CEO
    Knobel"). Institutions and places are out of scope (owner: warning only).
    """
    if not body:
        return []
    src = _source_words(source or "")
    matches = list(_NAME_TOKEN_RE.finditer(body))
    toks = [m.group(0) for m in matches]

    def adjacent(a: int, b: int) -> bool:
        """Only whitespace between token a and token b — a sentence boundary
        ("… said Mirko. This …") must never glue two words into a name."""
        return body[matches[a].end():matches[b].start()].strip() == ""

    bad: list[str] = []
    seen: set[str] = set()
    i = 0
    while i < len(toks):
        tok = toks[i]
        low = _POSSESSIVE_RE.sub("", tok).lower()
        if not _namelike(tok) or low in _NON_NAME_CAPS or low in _TITLES or low in _PARTICLES:
            i += 1
            continue
        titled = i > 0 and _title_before(toks[i - 1],
                                         body[matches[i - 1].end():matches[i].start()])
        given = _is_given_name(tok)
        if not (titled or given):
            i += 1
            continue
        # collect: [particles] Surname — all adjacent, no punctuation between
        j = i + 1
        while j < len(toks) and toks[j].lower() in _PARTICLES and adjacent(j - 1, j):
            j += 1
        has_surname = (j < len(toks) and adjacent(j - 1, j) and _namelike(toks[j])
                       and toks[j].lower() not in _NON_NAME_CAPS
                       and toks[j].lower() not in _TITLES)
        if has_surname:
            parts = toks[i:j + 1]
            i_next = j + 1
        elif titled:
            parts = [tok]                       # "CEO Knobel"
            i_next = i + 1
        else:
            i += 1                              # lone given name: not a person claim
            continue
        words = [p for p in parts if p.lower() not in _PARTICLES]
        name = _POSSESSIVE_RE.sub("", " ".join(parts))
        key = " ".join(_POSSESSIVE_RE.sub("", w).lower() for w in words)
        # institution / brand / instrument named after a person → not a person
        nxt = toks[i_next] if i_next < len(toks) else ""
        gap = body[matches[i_next - 1].end():matches[i_next].start()].strip() if nxt else ""
        org = (nxt and gap in ("", "&", "-", "–", "und", "and")
               and _POSSESSIVE_RE.sub("", nxt).lower() in _ORG_SUFFIX)
        if org or key in _NOT_PERSONS:
            i = i_next
            continue
        if any(not _in_source(w, src) for w in words) and name not in seen:
            bad.append(name)
            seen.add(name)
        i = i_next
    return bad
