"""Date a pocket by the calendar of research and patents, not by our signal space (2026-10-01).

Owner 01.10.: "Patente und Forschung tragen kalendarische Daten zur zeitlichen Einordnung,
die nutzbar sein müssten." The emerging layer dates a pocket by the first month its
lookalikes appear in the SIGNAL SPACE — and research and patents only reached the signal
space in breadth in 2026, so most domain pockets came out "first seen 2026-07" whatever
their real age (Redox flow batteries, magnesium batteries, …).

The two corpora outside the signal space carry real dates and are searchable:
research_corpus (OpenAlex, 45.5 M works, in breadth from 2010) and patent_search
(20.0 M patents, from 1990), both with a GIN full-text index. This module asks them,
year by year, how often a pocket's vocabulary appears:

  1. phrases: the n-grams (1-3 words) that set the pocket's member titles apart from the
     rest of its domain — share in the pocket × log(share in pocket / share in domain);
  2. query: domain anchor (the free term and its spellings, or a domain's phrases) AND
     any of the top phrases, as a tsquery (`&&`, `||` of phraseto_tsquery);
  3. per year and corpus: matching documents, and the same per million documents of
     that year — the corpora grow unevenly (patents 2010-15 are thin, research doubles
     in 2024), so only the normalised series has a shape;
  4. first year (≥ 3 documents), take-off (first year at ≥ 15 % of the peak rate, the
     Field Watch rule), growth (last three complete years over the three before). A
     first year at the start of a corpus is reported as an edge ("2010 or earlier").

It is a text count, so it inherits the weakness of words: the query is stored and shown
next to the dates, so the reader sees what was counted.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from pipeline.db import get_connection

logger = logging.getLogger("calendar_dating")

CORPORA = {
    # name: (table, year expression, first year in breadth)
    "science": ("research_corpus", "year", 2010),
    "patent": ("patent_search", "extract(year from published)::int", 1990),
}
MIN_DOCS = 3
TAKEOFF_SHARE = 0.15
MAX_PHRASES = 2
MIN_PHRASE_SHARE = 0.12
STOP = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "were", "using",
    "used", "use", "via", "into", "based", "study", "studies", "new", "novel", "review",
    "analysis", "approach", "method", "methods", "results", "effect", "effects", "role",
    "case", "data", "model", "models", "system", "systems", "research", "paper", "report",
    "toward", "towards", "through", "between", "among", "their", "its", "can", "may", "our",
    "how", "what", "why", "who", "when", "where", "not", "development", "high", "performance",
    "enhanced", "improved", "efficient", "advanced", "application", "applications", "towards",
    "under", "over", "its", "his", "her", "has", "have", "will", "into", "than", "more", "one",
    "two", "first", "all", "also", "after", "about", "des", "der", "und", "les", "del",
    "comprising", "same", "thereof", "including", "having",
}
_TOKEN = re.compile(r"[a-z][a-z0-9]+")
_totals_cache: dict[str, dict[int, int]] = {}
# Counting both corpora by year takes ~55 s (45.5 M + 20.0 M rows); they grow monthly
# (OpenAlex sync on the 5th, patent sweep on Tuesdays), so a week-old count is fine.
TOTALS_FILE = Path(os.getenv("CALENDAR_TOTALS_FILE",
                             str(Path.home() / ".cache" / "catandary" / "calendar_totals.json")))
TOTALS_MAX_AGE_S = 7 * 24 * 3600


def _tokens(title: str) -> list[str]:
    return _TOKEN.findall((title or "").lower())


def _ngrams(tokens: list[str], nmax: int = 3) -> set[str]:
    out = set()
    for n in range(1, nmax + 1):
        for i in range(len(tokens) - n + 1):
            g = tokens[i:i + n]
            if g[0] in STOP or g[-1] in STOP or len(g[0]) < 3 or len(g[-1]) < 3:
                continue
            out.add(" ".join(g))
    return out


def nest_phrases(member_titles: list[str], domain_titles: list[str], anchor: list[str],
                 k: int = MAX_PHRASES) -> list[str]:
    """The k phrases that set these titles apart from the domain's (see module doc)."""
    anchor_words = {w for a in anchor for w in _tokens(a)}
    anchor_words |= {w.rstrip("s") for w in anchor_words}
    nd = max(len(domain_titles), 1)
    nn = max(len(member_titles), 1)
    dom = Counter(g for t in domain_titles for g in _ngrams(_tokens(t)))
    mem = Counter(g for t in member_titles for g in _ngrams(_tokens(t)))
    scored = []
    for g, c in mem.items():
        share = c / nn
        if share < MIN_PHRASE_SHARE or c < 3:
            continue
        words = g.split()
        if all(w in anchor_words or w.rstrip("s") in anchor_words for w in words):
            continue
        lift = share / max(dom.get(g, 0) / nd, 1e-6)
        if lift <= 1.2:
            continue
        # longer phrases are more specific; a small bonus keeps "thermal runaway" over "thermal"
        scored.append((share * math.log(lift) * (1 + 0.25 * (len(words) - 1)), g))
    scored.sort(reverse=True)
    picked: list[str] = []
    for _, g in scored:
        if any(g in p or p in g for p in picked):
            continue
        picked.append(g)
        if len(picked) >= k:
            break
    return picked


def _tsquery(anchor: list[str], phrases: list[str]) -> tuple[str, list[str]]:
    """SQL tsquery expression + params: (a1 || a2 …) && (p1 || p2 …)."""
    parts, params = [], []
    if anchor:
        parts.append("(" + " || ".join(["phraseto_tsquery('english', ?)"] * len(anchor)) + ")")
        params += anchor
    if phrases:
        parts.append("(" + " || ".join(["phraseto_tsquery('english', ?)"] * len(phrases)) + ")")
        params += phrases
    return " && ".join(parts), params


def corpus_totals(name: str) -> dict[int, int]:
    """Documents per year of a corpus — memory, then a week-old file, then the database."""
    if name in _totals_cache:
        return _totals_cache[name]
    try:
        disk = json.loads(TOTALS_FILE.read_text(encoding="utf-8"))
        if time.time() - float(disk.get("at", 0)) < TOTALS_MAX_AGE_S and name in disk:
            _totals_cache[name] = {int(y): int(n) for y, n in disk[name].items()}
            return _totals_cache[name]
    except (OSError, ValueError):
        disk = {}
    table, yexpr, _ = CORPORA[name]
    with get_connection() as c:
        c.execute("SET statement_timeout = '600s'")
        rows = c.execute(f"SELECT {yexpr} AS y, count(*) AS n FROM {table} GROUP BY 1").fetchall()
    _totals_cache[name] = {int(r["y"]): int(r["n"]) for r in rows if r["y"] is not None}
    try:
        fresh = {k: v for k, v in (disk or {}).items() if k in CORPORA}
        if time.time() - float((disk or {}).get("at", 0)) >= TOTALS_MAX_AGE_S:
            fresh = {}
        fresh[name] = {str(y): n for y, n in _totals_cache[name].items()}
        fresh["at"] = time.time() if "at" not in fresh else fresh["at"]
        TOTALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOTALS_FILE.write_text(json.dumps(fresh), encoding="utf-8")
    except OSError as exc:
        logger.warning("could not cache corpus totals: %s", exc)
    return _totals_cache[name]


def warm() -> None:
    """Load both corpora's yearly totals (the service calls this at start)."""
    for name in CORPORA:
        try:
            corpus_totals(name)
        except Exception as exc:                          # noqa: BLE001
            logger.warning("corpus totals for %s unavailable: %s", name, exc)


def yearly_counts(name: str, anchor: list[str], phrases: list[str]) -> dict[int, int]:
    table, yexpr, _ = CORPORA[name]
    expr, params = _tsquery(anchor, phrases)
    with get_connection() as c:
        c.execute("SET statement_timeout = '120s'")
        rows = c.execute(f"SELECT {yexpr} AS y, count(*) AS n FROM {table} "
                         f"WHERE tsv @@ ({expr}) GROUP BY 1", params).fetchall()
    return {int(r["y"]): int(r["n"]) for r in rows if r["y"] is not None}


def summarise(counts: dict[int, int], totals: dict[int, int], start: int,
              this_year: int | None = None) -> dict:
    """first year, take-off, growth, and the series per million (complete years only
    for the shape; the running year is listed but never decides anything)."""
    this_year = this_year or date.today().year
    years = list(range(start, this_year + 1))
    n = [int(counts.get(y, 0)) for y in years]
    pm = [round(1e6 * counts.get(y, 0) / totals[y], 3) if totals.get(y) else 0.0 for y in years]
    complete = [i for i, y in enumerate(years) if y < this_year]
    first = next((years[i] for i in range(len(years)) if n[i] >= MIN_DOCS), None)
    peak = max((pm[i] for i in complete), default=0.0)
    takeoff = next((years[i] for i in complete if n[i] >= MIN_DOCS and pm[i] >= TAKEOFF_SHARE * peak),
                   None) if peak > 0 else None
    last3 = [pm[i] for i in complete[-3:]]
    prev3 = [pm[i] for i in complete[-6:-3]]
    growth = (round(sum(last3) / sum(prev3), 2) if prev3 and sum(prev3) > 0 else None)
    pre = sum(counts.get(y, 0) for y in counts if y < start)
    return {"first": first, "edge": first == start, "takeoff": takeoff, "growth": growth,
            "total": int(sum(n)), "before_start": int(pre), "years": years, "counts": n,
            "per_million": pm}


def date_nest(anchor: list[str], phrases: list[str]) -> dict:
    out: dict = {"anchor": anchor, "phrases": phrases}
    if not phrases and not anchor:
        return out
    for name, (_, _, start) in CORPORA.items():
        try:
            out[name] = summarise(yearly_counts(name, anchor, phrases), corpus_totals(name), start)
        except Exception as exc:                          # noqa: BLE001
            logger.warning("calendar dating failed on %s for %s: %s", name, phrases, exc)
    return out


def date_nests(nests: list[dict], member_titles: list[list[str]], domain_titles: list[str],
               anchor: list[str], workers: int = 4) -> None:
    """Attach `calendar` to each nest, in place. Never raises."""
    for name in CORPORA:
        try:
            corpus_totals(name)
        except Exception as exc:                          # noqa: BLE001
            logger.warning("corpus totals for %s unavailable: %s", name, exc)
            return
    for n, titles in zip(nests, member_titles):
        n["calendar_phrases"] = nest_phrases(titles, domain_titles, anchor)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda n: date_nest(anchor, n["calendar_phrases"])
                              if n["calendar_phrases"] else None, nests))
    for n, r in zip(nests, results):
        n["calendar"] = r
