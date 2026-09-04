#!/usr/bin/env python3
"""Ingest historical works from a journal via the free OpenAlex API.

For the academic/journal sources, OpenAlex gives complete dated histories with
abstracts — no scraping, no key, no Firecrawl. The journal is resolved to an
OpenAlex source id by name; works in the date range are pulled (cursor-paginated)
and inserted as raw_entries with the publication date and reconstructed abstract.

Usage:
    python scripts/ingest_openalex.py --source-name "Food Policy" \
        --after 2015-01-01 --before 2023-01-01 --dry-run
    python scripts/ingest_openalex.py --source-name "Nature Food" --after 2021-01-01

Work-type gate (#73, 2026-09-05): the concept sweeps (--concept/--vertical,
incl. --fresh) admit only OpenAlex types article/preprint/review/book-chapter
and skip repository deposits (Zenodo, figshare, GitHub …) — see `admit_work`
and pipeline/research_kinds.py. The admitted type lands in openalex_meta.
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline import db
from pipeline.config import load_sources
from pipeline.research_kinds import RESEARCH_WORK_TYPES, is_repository_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OPENALEX = "https://api.openalex.org"
# OpenAlex is now a freemium credit service: $0.10/day with no key, $1/day with a
# free key. A persistent 429 = the daily budget is exhausted (resets midnight UTC),
# NOT a reputation throttle — backoff alone won't recover it, the api_key will.
# Get a free key at openalex.org/settings/api and set OPENALEX_API_KEY.
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "")
MAILTO = "trends@catandary.de"  # legacy polite-pool hint; harmless under the new model
HEADERS = {"User-Agent": f"CatandaryTrends/1.0 (mailto:{MAILTO})"}


def _get(client: httpx.Client, url: str, params: dict, timeout: int = 40,
         tries: int = 6) -> dict | None:
    """GET with the polite-pool `mailto` param and exponential backoff on 429.

    The first ingest hit the common-pool rate limit (mailto only in the UA, not
    as a query param) → resolve calls returned 429 → sources were silently
    skipped. Sending `mailto` puts us in the polite pool; on 429/5xx we back off
    and retry instead of treating it as 'no results'."""
    params = {**params, "mailto": MAILTO}
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY
    for i in range(tries):
        try:
            r = client.get(url, params=params, timeout=timeout)
        except Exception as e:  # noqa: BLE001 — transient network
            logger.warning("OpenAlex request error (%s), retry %d/%d", e, i + 1, tries)
            time.sleep(2 ** i)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            # Daily budget exhausted (resets midnight UTC) OR >100 req/s burst. A
            # short burst clears with backoff; an exhausted budget will not — bail
            # after the retries rather than block forever (caller skips the source).
            remaining = r.headers.get("X-RateLimit-Remaining")
            wait = min(30, 2 ** i + 1)
            logger.warning("OpenAlex 429 (remaining=%s%s) — backoff %ds (try %d/%d)",
                           remaining, "" if OPENALEX_API_KEY else ", NO api_key set",
                           wait, i + 1, tries)
            time.sleep(wait)
            continue
        if r.status_code in (500, 502, 503):
            time.sleep(min(30, 2 ** i + 1))
            continue
        logger.error("OpenAlex %s: %s", r.status_code, r.text[:160])
        return None
    logger.error("OpenAlex: exhausted retries for %s (daily budget? set OPENALEX_API_KEY)", url)
    return None


def find_source_entry(name: str) -> dict | None:
    cfg = load_sources()
    for vert, groups in cfg.get("verticals", {}).items():
        for key in ("sources", "science"):
            for s in groups.get(key, []) or []:
                if isinstance(s, dict) and s.get("name") == name:
                    return {**s, "vertical": vert}
    for grp in cfg.get("cross_industry", {}).values():
        if isinstance(grp, list):
            for s in grp:
                if isinstance(s, dict) and s.get("name") == name:
                    return {**s, "vertical": "CROSS"}
    return None


def resolve_source_id(client: httpx.Client, name: str) -> tuple[str, str] | None:
    """Return (openalex_source_id, display_name) for the best name match.

    Picks the candidate with the most works (the real top journal dwarfs tiny
    same-named sources — fixes Nature/Science/PNAS resolving to an empty/wrong
    source), preferring journal-type sources. Tries the name with sources.yaml
    annotations like '(main)' stripped, then the raw name."""
    cleaned = re.sub(r"\s*\([^)]*\)", "", name).strip()
    for q in dict.fromkeys([cleaned, name]):  # de-dup, keep order
        data = _get(client, f"{OPENALEX}/sources",
                    {"search": q, "per_page": 10,
                     "select": "id,display_name,works_count,type"})
        results = (data or {}).get("results", [])
        if not results:
            continue
        best = max(results, key=lambda r: ((r.get("type") == "journal"),
                                           r.get("works_count") or 0))
        return best["id"], best["display_name"]
    return None


def reconstruct_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))[:2000]


def iter_works(client: httpx.Client, source_id: str, after: str, before: str):
    sid = source_id.rsplit("/", 1)[-1]  # S12345
    filt = (f"primary_location.source.id:{sid},"
            f"from_publication_date:{after},to_publication_date:{before}")
    cursor = "*"
    while cursor:
        data = _get(client, f"{OPENALEX}/works", {
            "filter": filt, "per_page": 100, "cursor": cursor,  # 100 = API max
            "select": "id,title,publication_date,abstract_inverted_index,doi,primary_location",
        })
        if data is None:
            return
        for w in data.get("results", []):
            yield w
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(0.2)


def landing_url(work: dict) -> str:
    loc = work.get("primary_location") or {}
    return loc.get("landing_page_url") or work.get("doi") or work.get("id") or ""


def _short(oa_id: str) -> str:
    """OpenAlex URL id -> short id (https://openalex.org/W123 -> W123)."""
    return (oa_id or "").rsplit("/", 1)[-1]


# --- Graph layer (issue #9): Subfield display-name -> Catandary vertical.
# Deterministic like vertical_for_cpc, but on the OpenAlex topic hierarchy
# (domain->field->subfield). Keyword-matched on the subfield (then field) name so
# it survives OpenAlex re-numbering; unmapped -> CROSS (kept, refinable later).
SUBFIELD_VERTICAL: list[tuple[str, str]] = [
    # FOOD
    ("food science", "FOOD"), ("agronomy", "FOOD"), ("crop science", "FOOD"),
    ("animal science", "FOOD"), ("horticulture", "FOOD"), ("agricultural", "FOOD"),
    ("soil science", "FOOD"), ("aquaculture", "FOOD"),
    # HEALTH
    ("medicine", "HEALTH"), ("pharmacology", "HEALTH"), ("pharmaceutical", "HEALTH"),
    ("immunology", "HEALTH"), ("microbiology", "HEALTH"), ("genetics", "HEALTH"),
    ("biochemistry", "HEALTH"), ("neuroscience", "HEALTH"), ("oncology", "HEALTH"),
    ("cardiology", "HEALTH"), ("physiology", "HEALTH"), ("cell biology", "HEALTH"),
    ("molecular biology", "HEALTH"), ("nursing", "HEALTH"), ("public health", "HEALTH"),
    ("psychiatry", "HEALTH"), ("epidemiology", "HEALTH"), ("endocrinology", "HEALTH"),
    ("nutrition", "HEALTH"), ("biotechnology", "HEALTH"),
    # TECH
    ("artificial intelligence", "TECH"), ("computer", "TECH"), ("software", "TECH"),
    ("signal processing", "TECH"), ("electrical", "TECH"), ("electronic", "TECH"),
    ("information systems", "TECH"), ("human-computer", "TECH"), ("telecommunication", "TECH"),
    ("computer vision", "TECH"), ("machine learning", "TECH"), ("robotics", "TECH"),
    ("semiconductor", "TECH"),
    # ECO
    ("environmental", "ECO"), ("renewable energy", "ECO"), ("ecology", "ECO"),
    ("pollution", "ECO"), ("climate", "ECO"), ("waste", "ECO"), ("sustainability", "ECO"),
    ("energy engineering", "ECO"), ("water", "ECO"), ("atmospheric", "ECO"),
    # BIZ
    ("business", "BIZ"), ("economics", "BIZ"), ("finance", "BIZ"), ("management", "BIZ"),
    ("marketing", "BIZ"), ("accounting", "BIZ"),
    # DESIGN
    ("architecture", "DESIGN"), ("building", "DESIGN"), ("urban", "DESIGN"),
    # FASHION
    ("textile", "FASHION"), ("polymer", "FASHION"),
    # LIFESTYLE
    ("tourism", "LIFESTYLE"), ("media", "LIFESTYLE"), ("communication", "LIFESTYLE"),
    ("sports science", "LIFESTYLE"), ("education", "LIFESTYLE"),
]


def vertical_for_topic(primary_topic: dict | None) -> str:
    """Route a work to a vertical by its primary topic's subfield (then field)
    display name. Unmapped -> CROSS (never dropped)."""
    if not primary_topic:
        return "CROSS"
    for level in ("subfield", "field"):
        name = ((primary_topic.get(level) or {}).get("display_name") or "").lower()
        for kw, vert in SUBFIELD_VERTICAL:
            if kw in name:
                return vert
    return "CROSS"


# --- Concept-expansion mode (issue #4): pull the SCIENCE tier by topic across ALL
# journals, not journal-by-journal. Targets the pre-2020 research history the
# lead-time validation found missing (science->market lead reads ~0 because the
# research tier only reaches ~2020). Curated concepts per vertical keep it out of
# the OpenAlex firehose; a citations gate removes predatory/irrelevant noise
# (works pre-2020 have accumulated citations, so the gate is meaningful there).
CONCEPT_SHARDS: dict[str, list[str]] = {
    "TECH": ["artificial intelligence", "machine learning", "robotics",
             "quantum computing", "semiconductor", "computer vision",
             # 2026-08 taxonomy expansion — science coverage for the new keys
             # quantum_information_science / next_generation_semiconductors /
             # orbital_economy_expansion (docs/mega_taxonomy_decision_2026-08-07.md)
             "quantum information", "photonics", "aerospace engineering",
             "space exploration", "satellite"],
    "HEALTH": ["immunotherapy", "gene therapy", "obesity", "neurodegeneration",
               "precision medicine", "microbiome",
               # digital_healthcare_integration
               "telemedicine", "digital health", "health informatics"],
    "FOOD": ["food science", "alternative protein", "fermentation",
             "sustainable agriculture", "food security"],
    "ECO": ["renewable energy", "carbon capture", "battery", "photovoltaics",
            "climate change mitigation"],
    "BIZ": ["financial technology", "supply chain management", "electronic commerce",
            # evolution_of_work_models ("remote work" ist kein OpenAlex-Konzept —
            # das kanonische Konzept heisst "telecommuting")
            "human resource management", "telecommuting", "organizational behavior"],
    "FASHION": ["textile", "biomaterials", "cosmetics"],
    # "sustainable architecture" does not resolve against the OpenAlex concepts
    # API (zero results, verified 2026-08-28, #81) — replaced by the two
    # concepts that jointly cover the theme: "sustainable design" (C121217528,
    # 33k works, the general sustainability-in-design concept) + "green
    # building" (C2984362373, 14.6k works, the built-environment angle).
    "DESIGN": ["sustainable design", "green building", "urban design"],
    # "creator economy" does not resolve either (zero results, same check) —
    # replaced by "influencer marketing" (C26011011, 44k works) + "user-generated
    # content" (C101293273, 22k works), which together cover the monetization
    # and content-production sides of the theme without duplicating the
    # existing "social media" shard below.
    "LIFESTYLE": ["social media", "video games", "influencer marketing", "user-generated content",
                  # education_and_lifelong_learning
                  "educational technology", "higher education", "lifelong learning"],
}


def resolve_concept_id(client: httpx.Client, name: str) -> tuple[str, str] | None:
    """Return (concept_id, display_name) for the best-matching OpenAlex concept.
    Picks the highest works_count match (the canonical broad concept, not a niche
    same-named one)."""
    data = _get(client, f"{OPENALEX}/concepts",
                {"search": name, "per_page": 10,
                 "select": "id,display_name,works_count,level"})
    results = (data or {}).get("results", [])
    if not results:
        return None
    best = max(results, key=lambda r: r.get("works_count") or 0)
    return best["id"], best["display_name"]


def iter_works_by_concept(client: httpx.Client, cid: str, after: str, before: str,
                          min_citations: int):
    """Cursor-paginate works for a concept in the date range, gated on citations.
    Sorted by cited_by_count desc so the most-established works come first (and a
    per-shard cap can stop early on the long low-citation tail)."""
    c = cid.rsplit("/", 1)[-1]  # C12345
    filt = (f"concepts.id:{c},from_publication_date:{after},"
            f"to_publication_date:{before},cited_by_count:>{min_citations}")
    cursor = "*"
    while cursor:
        data = _get(client, f"{OPENALEX}/works", {
            "filter": filt, "per_page": 100, "cursor": cursor,
            "sort": "cited_by_count:desc",
            "select": "id,title,publication_date,abstract_inverted_index,doi,"
                      "primary_location,cited_by_count,type,is_retracted,counts_by_year",
        })
        if data is None:
            return
        for w in data.get("results", []):
            yield w
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(0.2)


# --- Citation-free fresh sweep (issue #51): the cited-concept pull above is
# gated on cited_by_count and sorted by it, so recent works (which have no
# citations yet) are structurally excluded — exactly the works a LEAD signal
# needs. This mode pulls citation-free, freshest-first, and stays separate from
# the #9 graph path so the established citation graph is untouched.
def count_works(client: httpx.Client, filt: str) -> int | None:
    """meta.count for a works filter, without pulling the works (#51 Step 1:
    size the corpus before deciding to ingest it)."""
    data = _get(client, f"{OPENALEX}/works", {"filter": filt, "per_page": 1, "select": "id"})
    if data is None:
        return None
    return (data.get("meta") or {}).get("count")


def iter_works_fresh(client: httpx.Client, cid: str, after: str, before: str):
    """Citation-FREE, freshest-first works for a concept (#51 lead sweep). No
    cited_by_count gate (recent works have none — that's the point); sorted
    publication_date:desc so the newest works arrive first (a per-shard cap then
    takes the freshest slice)."""
    c = cid.rsplit("/", 1)[-1]  # C12345
    filt = (f"concepts.id:{c},from_publication_date:{after},"
            f"to_publication_date:{before}")
    cursor = "*"
    while cursor:
        data = _get(client, f"{OPENALEX}/works", {
            "filter": filt, "per_page": 100, "cursor": cursor,
            "sort": "publication_date:desc",
            "select": "id,title,publication_date,abstract_inverted_index,doi,"
                      "primary_location,cited_by_count,type,is_retracted,counts_by_year",
        })
        if data is None:
            return
        for w in data.get("results", []):
            yield w
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(0.2)


def admit_work(w: dict) -> tuple[bool, str]:
    """Work-type gate for the concept sweeps (#73, 2026-09-05). Returns
    (admit, reason): reason is the OpenAlex `type` when admitted, `type:<t>`
    when the type is outside RESEARCH_WORK_TYPES (dataset, software, other,
    paratext, peer-review, erratum, editorial, letter, …; missing type counts as
    `type:none`), or `repository` when the landing URL / DOI points at a data or
    software repository (Zenodo, figshare, Dryad, OSF, GitHub/GitLab, Software
    Heritage, Dataverse) — the second net, because Zenodo deposits are often
    typed `article`. Rationale + numbers: pipeline/research_kinds.py."""
    wtype = (w.get("type") or "").strip().lower()
    if wtype not in RESEARCH_WORK_TYPES:
        return False, f"type:{wtype or 'none'}"
    if is_repository_url(landing_url(w), w.get("doi")):
        return False, "repository"
    return True, wtype


def measure_fresh_corpus(after: str, before: str, vertical_filter: str) -> dict:
    """#51 Step 1: size the citation-FREE fresh corpus over the curated concepts
    for the date range via meta.count, WITHOUT pulling anything. Prints per-concept
    counts + a summed total and the Go/No-Go verdict (issue thresholds: <200k →
    defer, >1M → full sweep). Note: concepts overlap, so the sum is an upper bound
    on unique works, useful for relative sizing."""
    if vertical_filter.upper() == "ALL":
        jobs = [(c, v) for v, cs in CONCEPT_SHARDS.items() for c in cs]
    else:
        v = vertical_filter.upper()
        jobs = [(c, v) for c in CONCEPT_SHARDS.get(v, [])]
        if not jobs:
            logger.error("no curated concepts for vertical %s", v)
            return {"total": 0, "rows": [], "verdict": "n/a"}
    rows: list[tuple[str, str, int | None]] = []
    total = 0
    print(f"{'concept':32s} {'vert':9s} {'count':>12s}   [{after}..{before}, citation-free]")
    with httpx.Client(headers=HEADERS) as client:
        for concept, vert in jobs:
            resolved = resolve_concept_id(client, concept)
            if not resolved:
                rows.append((concept, vert, None))
                print(f"{concept:32s} {vert:9s} {'RESOLVE-ERR':>12s}")
                continue
            cid, _disp = resolved
            c = cid.rsplit("/", 1)[-1]
            filt = (f"concepts.id:{c},from_publication_date:{after},"
                    f"to_publication_date:{before}")
            n = count_works(client, filt)
            rows.append((concept, vert, n))
            if n:
                total += n
            print(f"{concept:32s} {vert:9s} {(format(n, ',') if n is not None else 'ERR'):>12s}")
            time.sleep(0.1)
    verdict = ("DEFER (<200k)" if total < 200_000 else
               "FULL SWEEP (>1M)" if total > 1_000_000 else
               "PARTIAL (200k-1M) — pull the strongest verticals first")
    print(f"{'TOTAL (sum, overlap-inflated)':32s} {'':9s} {total:>12,}")
    print(f"Verdict: {verdict}")
    return {"total": total, "rows": rows, "verdict": verdict}


def iter_works_graph(client: httpx.Client, filt: str):
    """Cursor-paginate works with the FULL graph select (issue #9): referenced_works
    (citation edges), topics (domain layer), cited_by_count + counts_by_year
    (native forward velocity), type + is_retracted."""
    cursor = "*"
    while cursor:
        data = _get(client, f"{OPENALEX}/works", {
            "filter": filt, "per_page": 100, "cursor": cursor,
            "select": "id,title,publication_date,abstract_inverted_index,doi,"
                      "primary_location,type,cited_by_count,counts_by_year,"
                      "is_retracted,referenced_works,primary_topic,topics",
        })
        if data is None:
            return
        for w in data.get("results", []):
            yield w
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(0.15)


def science_subfields(vertical_filter: str = "") -> list[tuple[str, str, str]]:
    """(subfield_id, display_name, vertical) for every OpenAlex subfield that
    routes to one of our verticals (via vertical_for_topic on the subfield name).
    Fetched live so it stays in sync with OpenAlex's 252-subfield taxonomy.
    vertical_filter='' → all non-CROSS; else that vertical only."""
    out: list[tuple[str, str, str]] = []
    with httpx.Client(headers=HEADERS) as client:
        data = _get(client, f"{OPENALEX}/subfields",
                    {"per_page": 200, "select": "id,display_name"})
    for s in (data or {}).get("results", []):
        name = s.get("display_name") or ""
        vert = vertical_for_topic({"subfield": {"display_name": name}})
        if vert == "CROSS":
            continue
        if vertical_filter and vert != vertical_filter.upper():
            continue
        out.append((s["id"].rsplit("/", 1)[-1], name, vert))
    return out


def ingest_topic_graph(scope: str, after: str, before: str, min_citations: int,
                       cap: int, dry_run: bool) -> dict:
    """Graph-layer ingest (issue #9). `scope` = an OpenAlex topic id (T#####),
    a subfield id (subfields/####), or a free-text search. Pulls each work as a
    SCIENCE-tier node (raw_entries.openalex_id) + citation edges + topic rows +
    native forward-velocity meta. GPU-free, no LLM (vertical is topic-derived)."""
    st = {"works": 0, "inserted": 0, "duplicates": 0, "skipped": 0,
          "edges": 0, "topics": 0}
    raw_buf, cit_buf, top_buf, meta_buf = [], [], [], []
    src_ids: dict[str, int] = {}

    if scope.upper().startswith("T") and scope[1:].isdigit():
        filt = f"primary_topic.id:{scope}"
    elif scope.startswith("subfields/"):
        filt = f"primary_topic.subfield.id:https://openalex.org/{scope}"
    else:
        filt = f"default.search:{scope}"
    filt += (f",from_publication_date:{after},to_publication_date:{before}"
             f",cited_by_count:>{min_citations}")

    with httpx.Client(headers=HEADERS) as client:
        logger.info("[openalex-graph] scope=%s | %s..%s | cited>%d cap=%d",
                    scope, after, before, min_citations, cap)
        for w in iter_works_graph(client, filt):
            st["works"] += 1
            wid = _short(w.get("id"))
            url = landing_url(w)
            title = (w.get("title") or "").strip()
            if not wid or not url or not title:
                st["skipped"] += 1
                continue
            vert = vertical_for_topic(w.get("primary_topic"))
            if dry_run:
                st["inserted"] += 1
                if st["inserted"] >= cap:
                    break
                continue
            if vert not in src_ids:
                src_ids[vert] = db.upsert_source(
                    name=f"OpenAlex Science ({vert})",
                    feed_url=f"openalex://science/{vert}", source_type="research", vertical=vert)
            excerpt = "[Science · OpenAlex] " + reconstruct_abstract(
                w.get("abstract_inverted_index"))
            raw_buf.append((src_ids[vert], url, title, excerpt[:2000],
                            w.get("publication_date"), wid))
            for dst in w.get("referenced_works", []):
                cit_buf.append((wid, _short(dst)))
            for i, tp in enumerate(w.get("topics", []) or []):
                top_buf.append((wid, _short(tp.get("id")), (tp.get("display_name") or "")[:120],
                                ((tp.get("subfield") or {}).get("display_name") or "")[:80],
                                ((tp.get("field") or {}).get("display_name") or "")[:80],
                                ((tp.get("domain") or {}).get("display_name") or "")[:60],
                                tp.get("score"), 1 if i == 0 else 0))
            import json as _json
            meta_buf.append((wid, w.get("cited_by_count"),
                             _json.dumps(w.get("counts_by_year") or []),
                             w.get("type"), 1 if w.get("is_retracted") else 0))
            st["inserted"] += 1
            if len(raw_buf) >= 2000:
                ins = db.insert_raw_entries_batch_oa(raw_buf)
                st["duplicates"] += len(raw_buf) - ins
                st["edges"] += db.insert_openalex_citations(cit_buf)
                st["topics"] += db.insert_openalex_topics(top_buf)
                db.insert_openalex_meta(meta_buf)
                raw_buf.clear(); cit_buf.clear(); top_buf.clear(); meta_buf.clear()
            if st["inserted"] >= cap:
                break
        if raw_buf:
            ins = db.insert_raw_entries_batch_oa(raw_buf)
            st["duplicates"] += len(raw_buf) - ins
            st["edges"] += db.insert_openalex_citations(cit_buf)
            st["topics"] += db.insert_openalex_topics(top_buf)
            db.insert_openalex_meta(meta_buf)
    tag = "[dry] würde einfügen" if dry_run else "eingefügt"
    print(f"[graph] {scope}: {st['works']} works | {tag} {st['inserted']} | "
          f"{st['duplicates']} dup | {st['edges']} edges | {st['topics']} topics | {st['skipped']} skip")
    return st


def ingest_concept(concept: str, vertical: str, after: str, before: str,
                   min_citations: int, cap: int, dry_run: bool,
                   fresh: bool = False) -> dict:
    """Ingest a concept's works as SCIENCE-tier raw_entries (source_type=research
    so the lead-time tier map treats them as science). Excerpt prefixed
    `[Science · <concept>]` to carry the tier into the embedding.

    fresh=True (#51): citation-free, freshest-first — the lead-signal sweep. Uses
    a distinct source (`OpenAlex fresh: …`) so it never mixes with the cited pull
    or the #9 citation graph.

    Work-type gate (#73): only papers pass `admit_work` — repository deposits
    (Zenodo/figshare/GitHub …) and non-paper types are skipped and counted in
    `skipped_type` (per type) / `skipped_repo`. The admitted type is stored in
    `openalex_meta.work_type` (node key `raw_entries.openalex_id`), which
    build_research_index.py turns into `research_signals.kind`."""
    stats: dict = {"works": 0, "inserted": 0, "duplicates": 0, "skipped": 0,
                   "skipped_repo": 0, "skipped_type": {}}
    meta_buf: list[tuple] = []

    def _flush_meta() -> None:
        if meta_buf and not dry_run:
            db.insert_openalex_meta(meta_buf)
        meta_buf.clear()

    with httpx.Client(headers=HEADERS) as client:
        resolved = resolve_concept_id(client, concept)
        if not resolved:
            logger.error("OpenAlex: could not resolve concept '%s'", concept)
            return stats
        cid, disp = resolved
        logger.info("[openalex-concept%s] %s -> %s (%s) | %s..%s | %s cap=%d",
                    " · FRESH" if fresh else "", concept, cid, disp, after, before,
                    "citation-free" if fresh else f"cited>{min_citations}", cap)
        src_name = f"OpenAlex fresh: {disp}" if fresh else f"OpenAlex: {disp}"
        src_feed = (f"{OPENALEX}/works?concept={cid.rsplit('/',1)[-1]}"
                    + ("&fresh=1" if fresh else ""))
        source_id = -1 if dry_run else db.upsert_source(
            name=src_name, feed_url=src_feed,
            source_type="research", vertical=vertical)
        works_iter = (iter_works_fresh(client, cid, after, before) if fresh
                      else iter_works_by_concept(client, cid, after, before, min_citations))
        for w in works_iter:
            stats["works"] += 1
            url = landing_url(w)
            title = (w.get("title") or "").strip()
            if not url or not title:
                stats["skipped"] += 1
                continue
            admitted, reason = admit_work(w)
            if not admitted:
                if reason == "repository":
                    stats["skipped_repo"] += 1
                else:
                    t = reason.split(":", 1)[1]
                    stats["skipped_type"][t] = stats["skipped_type"].get(t, 0) + 1
                logger.debug("skip %s (%s): %s", _short(w.get("id")), reason, title[:80])
                continue
            excerpt = f"[Science · {disp}] " + reconstruct_abstract(
                w.get("abstract_inverted_index"))
            pub = w.get("publication_date")
            wid = _short(w.get("id")) or None
            if dry_run:
                stats["inserted"] += 1
            else:
                eid = db.insert_raw_entry(source_id, url, title, excerpt[:2000], pub,
                                          openalex_id=wid)
                stats["duplicates" if eid is None else "inserted"] += 1
            if wid:
                meta_buf.append((wid, w.get("cited_by_count"),
                                 json.dumps(w.get("counts_by_year") or []),
                                 reason, 1 if w.get("is_retracted") else 0))
                if len(meta_buf) >= 500:
                    _flush_meta()
            if stats["inserted"] >= cap:
                break
    _flush_meta()
    tag = "[dry] würde einfügen" if dry_run else "eingefügt"
    typed = ", ".join(f"{t} {n}" for t, n in sorted(stats["skipped_type"].items(),
                                                    key=lambda kv: -kv[1]))
    print(f"{concept:32s}: {stats['works']:5d} works | {tag} {stats['inserted']:5d} | "
          f"{stats['duplicates']} dup | {stats['skipped']} skip | "
          f"{sum(stats['skipped_type'].values())} non-paper type"
          f"{f' ({typed})' if typed else ''} | {stats['skipped_repo']} repository")
    return stats


def ingest(name: str, after: str, before: str, dry_run: bool) -> dict:
    src = find_source_entry(name)
    vertical = src["vertical"] if src else "CROSS"
    stats = {"works": 0, "inserted": 0, "duplicates": 0, "skipped": 0}

    with httpx.Client(headers=HEADERS) as client:
        # An explicit `openalex_id` in sources.yaml wins over name search — used
        # for sources whose display name doesn't match the OpenAlex journal
        # (e.g. "Science Magazine News" -> Science S3880285, "Matter (Cell Press)"
        # where a generic "Matter" search hits physics journals instead).
        explicit = (src or {}).get("openalex_id")
        resolved = (explicit, name) if explicit else resolve_source_id(client, name)
        if not resolved:
            logger.error("OpenAlex: could not resolve source '%s'", name)
            return stats
        sid, disp = resolved
        logger.info("[openalex] %s -> %s (%s) | %s..%s", name, sid, disp, after, before)

        source_id = -1 if dry_run else db.upsert_source(
            name=name, feed_url=(src or {}).get("feed_url", sid),
            source_type="trade_media", vertical=vertical)  # CHECK-safe source_type

        for w in iter_works(client, sid, after, before):
            stats["works"] += 1
            url = landing_url(w)
            title = (w.get("title") or "").strip()
            excerpt = reconstruct_abstract(w.get("abstract_inverted_index"))
            pub = w.get("publication_date")
            if not url or not title:
                stats["skipped"] += 1
                continue
            if dry_run:
                stats["inserted"] += 1
                continue
            eid = db.insert_raw_entry(source_id, url, title, excerpt[:2000], pub)
            stats["duplicates" if eid is None else "inserted"] += 1

    tag = "[dry] würde einfügen" if dry_run else "eingefügt"
    print(f"{name}: {stats['works']} works | {tag} {stats['inserted']} | "
          f"{stats['duplicates']} dup | {stats['skipped']} skip")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Ingest OpenAlex works — by journal (--source-name) or by "
                    "concept across all journals (--concept / --vertical)")
    ap.add_argument("--source-name", help="journal mode: one source by name")
    ap.add_argument("--concept", help="concept mode: one concept name (e.g. 'obesity')")
    ap.add_argument("--vertical", help="concept mode: vertical, or ALL to run the "
                    "curated CONCEPT_SHARDS for every vertical")
    ap.add_argument("--after", default="2010-01-01", help="YYYY-MM-DD (default 2010-01-01)")
    ap.add_argument("--before", default="2020-01-01",
                    help="YYYY-MM-DD (default 2020-01-01 — the pre-2020 science gap)")
    ap.add_argument("--min-citations", type=int, default=5,
                    help="concept mode: only works with cited_by_count above this "
                         "(noise gate; meaningful for pre-2020 works)")
    ap.add_argument("--cap", type=int, default=3000, help="concept mode: max inserts per concept")
    ap.add_argument("--graph", help="graph mode (#9): OpenAlex topic id (T#####), "
                    "subfield id (subfields/####), or free-text search — ingests the "
                    "full graph layer (nodes + citation edges + topics + forward velocity)")
    ap.add_argument("--science-sweep", metavar="VERTICAL",
                    help="broaden science: graph-ingest EVERY relevant OpenAlex subfield "
                         "(a vertical, or ALL). Deep historical science backbone.")
    ap.add_argument("--fresh", action="store_true",
                    help="concept mode (#51): citation-FREE, freshest-first lead sweep "
                         "(no cited_by_count gate; separate 'OpenAlex fresh:' sources)")
    ap.add_argument("--measure", action="store_true",
                    help="#51 Step 1: only measure meta.count of the citation-free corpus "
                         "over the curated concepts for --vertical (or ALL) in the date "
                         "range; writes nothing. Use to size before ingesting.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # Measurement (#51 Step 1) — count-only, no DB, no writes
    if args.measure:
        measure_fresh_corpus(args.after, args.before, args.vertical or "ALL")
        return 0

    # Science sweep (#9 breadth) — graph-ingest across all relevant subfields
    if args.science_sweep:
        db.init_db()
        vf = "" if args.science_sweep.upper() == "ALL" else args.science_sweep
        subs = science_subfields(vf)
        logger.info("[science-sweep] %d subfields | %s..%s | cited>%d cap=%d/subfield",
                    len(subs), args.after, args.before, args.min_citations, args.cap)
        grand = 0
        for sid, name, vert in subs:
            logger.info("── subfield %s (%s → %s)", sid, name, vert)
            s = ingest_topic_graph(f"subfields/{sid}", args.after, args.before,
                                   args.min_citations, args.cap, args.dry_run)
            grand += s["inserted"]
        logger.info("[science-sweep] DONE: %d inserted across %d subfields", grand, len(subs))
        return 0

    # Graph mode (issue #9) — the science graph layer
    if args.graph:
        db.init_db()  # ensure openalex_* tables exist
        s = ingest_topic_graph(args.graph, args.after, args.before,
                               args.min_citations, args.cap, args.dry_run)
        return 0 if s["works"] or args.dry_run else 1

    # Journal mode (unchanged)
    if args.source_name:
        s = ingest(args.source_name, args.after, args.before, args.dry_run)
        if not args.dry_run and s["inserted"]:
            print(f"  -> {s['inserted']} neue datierte raw_entries (processed=0)")
        return 0

    # Concept mode
    if not (args.concept or args.vertical):
        ap.error("need --source-name (journal) or --concept/--vertical (concept mode)")

    if args.concept and args.vertical and args.vertical.upper() != "ALL":
        jobs = [(args.concept, args.vertical.upper())]
    elif args.concept:
        ap.error("--concept also needs --vertical (the tier's vertical label)")
    elif args.vertical and args.vertical.upper() == "ALL":
        jobs = [(c, v) for v, cs in CONCEPT_SHARDS.items() for c in cs]
    else:  # --vertical FOO → that vertical's curated shards
        v = args.vertical.upper()
        jobs = [(c, v) for c in CONCEPT_SHARDS.get(v, [])]
        if not jobs:
            ap.error(f"no curated concepts for vertical {v}; pass --concept explicitly")

    grand: dict = {"works": 0, "inserted": 0, "duplicates": 0, "skipped": 0, "skipped_repo": 0}
    grand_types: dict[str, int] = {}
    for concept, vert in jobs:
        s = ingest_concept(concept, vert, args.after, args.before,
                           args.min_citations, args.cap, args.dry_run,
                           fresh=args.fresh)
        for k in grand:
            grand[k] += s.get(k, 0)
        for t, n in s.get("skipped_type", {}).items():
            grand_types[t] = grand_types.get(t, 0) + n
    tag = "[dry] würde einfügen" if args.dry_run else "eingefügt"
    typed = ", ".join(f"{t} {n}" for t, n in sorted(grand_types.items(), key=lambda kv: -kv[1]))
    print(f"{'TOTAL':32s}: {grand['works']:5d} works | {tag} {grand['inserted']:5d} | "
          f"{grand['duplicates']} dup | {grand['skipped']} skip | "
          f"{sum(grand_types.values())} non-paper type{f' ({typed})' if typed else ''} | "
          f"{grand['skipped_repo']} repository")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
