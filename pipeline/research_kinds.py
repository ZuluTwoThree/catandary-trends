"""Work-type gate for the research tier (#73, Owner-Befund 2026-09-05).

OpenAlex indexes repository deposits — Zenodo software artifacts, figshare
datasets, GitHub releases, OSF projects — as Works alongside papers. The
citation-free fresh sweep (scripts/ingest_openalex.py --fresh) took them all:
in the 14 days before 2026-09-05, 2,755 of 13,367 fresh OpenAlex rows in
`research_signals` (20.6 %) pointed at a repository host — 512 of 1,091 in
"Artificial intelligence", 304 of 905 in "Computer vision" — and one of them
("sc26-submission/ad-artifacts: BatchFlow — SC26 Artifact v1.0.1", Zenodo)
surfaced as a top paper in the Research Pulse.

Two nets, both applied at ingest and mirrored in the index:

1. **Type admission** — only OpenAlex `type` values that denote a written
   research contribution are taken: article, preprint, review, book-chapter.
   Everything else (dataset, software, other, paratext, peer-review, erratum,
   editorial, letter, supplementary-materials, retraction, grant, standard,
   libguides, reference-entry — and also book, report, dissertation, which
   are documents but not the weekly paper flow the Pulse measures) is skipped
   and counted per type.
2. **Repository-host blocklist** — a work whose landing URL or DOI points at a
   data/software repository is skipped even if OpenAlex typed it `article`
   (Zenodo deposits frequently carry that type). Matched as a substring so DOI
   forms (`10.5281/zenodo.…`, `10.6084/m9.figshare.…`, `10.5061/dryad.…`) hit
   as well as landing-page hosts.

The index column `research_signals.kind` carries the result for every row:
    article | preprint | review | chapter   admitted OpenAlex type (or
                                            preprint server by source)
    artifact                                type outside the admission list
                                            or repository host
    unknown                                 no stored type, no host match
                                            (journal/press RSS, pre-#73
                                            fresh rows without meta)
Pulse and Explorer filter `kind <> 'artifact'` by default.

The pattern is used both by Python (`re`) and by PostgreSQL (`~*`), so it
must stay within the common dialect: no `?`, no `%` (the pipeline.db wrapper
rewrites `?` → `%s`), no lookarounds.
"""
from __future__ import annotations

import re

RESEARCH_WORK_TYPES: frozenset[str] = frozenset({"article", "preprint", "review", "book-chapter"})

KIND_BY_TYPE: dict[str, str] = {
    "article": "article",
    "preprint": "preprint",
    "review": "review",
    "book-chapter": "chapter",
}

KINDS: tuple[str, ...] = ("article", "preprint", "review", "chapter", "artifact", "unknown")

# Substring alternation, case-insensitive. `10\.5281/` is the Zenodo DOI prefix
# (landing pages are doi.org links, so the host alone would miss them);
# `10\.7910/DVN` is Harvard Dataverse. figshare/dryad DOIs contain the name.
REPOSITORY_HOST_PATTERN = (
    r"(zenodo\.org|10\.5281/|figshare|dryad|osf\.io|github\.com|gitlab\.com"
    r"|softwareheritage|dataverse|10\.7910/DVN)"
)
_REPO_RE = re.compile(REPOSITORY_HOST_PATTERN, re.IGNORECASE)

PREPRINT_SOURCES: tuple[str, ...] = ("arXiv Preprints", "biorxiv Preprints", "medrxiv Preprints")


def is_repository_url(*urls: str | None) -> bool:
    """True if any given URL/DOI string points at a data/software repository."""
    return any(u and _REPO_RE.search(u) for u in urls)


def kind_for(work_type: str | None, url: str | None, source: str | None = None) -> str:
    """Classify one row the way the index does (Python mirror of kind_sql)."""
    if is_repository_url(url):
        return "artifact"
    if work_type:
        return KIND_BY_TYPE.get(work_type, "artifact")
    if source in PREPRINT_SOURCES:
        return "preprint"
    return "unknown"


def kind_sql(type_expr: str, url_expr: str, source_expr: str) -> str:
    """PostgreSQL CASE expression computing `kind` from a stored OpenAlex type
    column, the URL column and the source-name column (same rules as kind_for).
    Constant strings only — safe to inline."""
    admitted = ", ".join(f"'{t}'" for t in sorted(RESEARCH_WORK_TYPES))
    type_case = " ".join(f"WHEN {type_expr} = '{t}' THEN '{k}'" for t, k in KIND_BY_TYPE.items())
    preprints = ", ".join(f"'{s}'" for s in PREPRINT_SOURCES)
    return (
        f"CASE WHEN {url_expr} ~* '{REPOSITORY_HOST_PATTERN}' THEN 'artifact' "
        f"{type_case} "
        f"WHEN {type_expr} IS NOT NULL AND {type_expr} NOT IN ({admitted}) THEN 'artifact' "
        f"WHEN {source_expr} IN ({preprints}) THEN 'preprint' "
        f"ELSE 'unknown' END"
    )


# Predicate for consumers that count papers (Pulse, Explorer default view).
# NULL-safe: rows the migration has not touched yet count as papers.
PAPER_FILTER_SQL = "coalesce({alias}kind, 'unknown') <> 'artifact'"


def paper_filter(alias: str = "") -> str:
    """`coalesce(<alias>kind,'unknown') <> 'artifact'` — alias like 'rs.'."""
    return PAPER_FILTER_SQL.format(alias=alias)
