#!/usr/bin/env python3
"""Patent ingester — the longest-lead-time signal for the foresight engine.

Pulls bibliographic patent data (title + abstract + CPC class + publication date
+ applicant) into `raw_entries`, scoped by CPC class + date window so the volume
stays sane (patents are millions/year). Each entry then flows through the normal
signal pipeline (relevance/extraction/classification → embedding) and lands in the
signal space, where `trend_signal_type='patent'` marks it as an early lead
indicator for the lead-time analysis (research → patent → funding → product).

Provider: EPO Open Patent Services (OPS) — worldwide coverage, free throttled tier,
title + abstract + CPC. Needs free OAuth credentials (register at
https://developers.epo.org → consumer key + secret), put them in .env:

    EPO_OPS_KEY=...
    EPO_OPS_SECRET=...

Why OPS and not USPTO ODP: the ODP "Patent File Wrapper" API only exposes US
*application* prosecution metadata (no abstract / CPC), a poor fit for trend
signals. OPS gives the inventive content (title + abstract + classification)
worldwide. Lens.org is an alternative (JSON, Bearer token) — same normalized
record shape, swap `_ops_*` for a `_lens_*` provider.

Usage:
    python scripts/ingest_patents.py --selftest                 # validate parsing, no creds
    python scripts/ingest_patents.py --cpc A23 --vertical FOOD --after 2020-01-01 --before 2026-07-01 --dry-run
    python scripts/ingest_patents.py --cpc A23 --vertical FOOD --after 2020-01-01 --before 2026-07-01
    python scripts/ingest_patents.py --vertical FOOD --after 2024-01-01 --before 2026-07-01   # all FOOD CPC classes
"""
from __future__ import annotations

import argparse
import base64
import logging
import os
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

from pipeline import db

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OPS_BASE = "https://ops.epo.org/3.2"
# EPO portal calls these "Consumer Key" / "Consumer Secret"; accept both names.
EPO_OPS_KEY = os.getenv("EPO_OPS_CONSUMER_KEY") or os.getenv("EPO_OPS_KEY", "")
EPO_OPS_SECRET = os.getenv("EPO_OPS_CONSUMER_SECRET_KEY") or os.getenv("EPO_OPS_SECRET", "")

# CPC (Cooperative Patent Classification) section/class → Catandary vertical.
# Curated so a CPC-scoped pull maps onto our taxonomy. A pulled patent's
# vertical is taken from the query (we pull per class), so this is also the
# canonical list of "which CPC classes feed which vertical".
CPC_VERTICAL: dict[str, list[str]] = {
    "FOOD": ["A23", "A21", "A22", "A01H", "C12C", "C12G", "C12J", "C13"],   # foods, baking, brewing, agri-genetics, sugar
    "HEALTH": ["A61", "A61K", "A61P", "C12N", "C12Q", "G16H"],              # medical, pharma, biotech, health informatics
    "ECO": ["Y02", "Y04", "F03D", "H02S", "C02F", "B09", "F24S"],          # climate-mitigation tech, wind, solar, water, waste
    "TECH": ["G06", "G06F", "G06N", "H04", "H01L", "G06Q"],                 # computing, AI/ML, comms, semiconductors
    "DESIGN": ["E04", "B44", "A47", "F21"],                                 # building/architecture, decorative, furniture, lighting
    "FASHION": ["A41", "A43", "A44", "A45", "D01", "D03", "D06"],           # apparel, footwear, textiles, dyeing
    "BIZ": ["G06Q"],                                                        # business methods / commerce
    "LIFESTYLE": ["A63", "G07F"],                                           # sports/games/amusement, vending
}

# Longest-prefix-first so A61K wins over A61 when routing a CPC code to a vertical.
_PREFIX_VERTICAL: list[tuple[str, str]] = sorted(
    ((p, v) for v, ps in CPC_VERTICAL.items() for p in ps), key=lambda x: -len(x[0]))


def vertical_for_cpc(cpc_list) -> str | None:
    """Route a patent to a Catandary vertical by its CPC codes (inventive codes
    preferred). Returns None if no code falls in any of our verticals' classes —
    which doubles as the relevance filter (drops off-scope chemistry/mechanics)."""
    if not cpc_list:
        return None
    codes = [c.get("code", "") for c in cpc_list if c.get("inventive")] \
        or [c.get("code", "") for c in cpc_list]
    for code in codes:
        for prefix, vert in _PREFIX_VERTICAL:
            if code.startswith(prefix):
                return vert
    return None


def _dashed_key(country: str, number: str, kind: str) -> str:
    """Canonical patent node key: country-number-kind (e.g. AU-2012247900-B9).
    The shared format across OPS/BDDS/HF ingest + the patent_links graph — the
    citation-graph joins and kind_code() all assume the dashes."""
    country, number, kind = (country or "").strip(), (number or "").strip(), (kind or "").strip()
    return f"{country}-{number}-{kind}" if country and number else ""


def kind_code(pub_number: str) -> str:
    """Patent kind code = trailing segment of the publication number (US-123-B2 -> B2).
    A1/A2 = application (first publication), B1/B2 = grant, U = utility model, T = translation."""
    import re
    last = (pub_number or "").rsplit("-", 1)[-1]
    return last if re.fullmatch(r"[A-Z]{1,2}\d?", last) else ""


def is_application(pub_number: str) -> bool:
    """True if a first-publication/application (kind A*) — the earliest lead-time
    signal. B* = grant (years later); for trend timing prefer the A publication."""
    return kind_code(pub_number).startswith("A")


# --------------------------------------------------------------------------- #
# EPO OPS provider
# --------------------------------------------------------------------------- #

def get_token(client: httpx.Client) -> str:
    """OAuth2 client-credentials → bearer access token (valid ~20 min)."""
    if not EPO_OPS_KEY or not EPO_OPS_SECRET:
        raise RuntimeError(
            "EPO_OPS_KEY / EPO_OPS_SECRET not set. Register a free app at "
            "https://developers.epo.org and add the consumer key+secret to .env")
    basic = base64.b64encode(f"{EPO_OPS_KEY}:{EPO_OPS_SECRET}".encode()).decode()
    r = client.post(f"{OPS_BASE}/auth/accesstoken",
                    headers={"Authorization": f"Basic {basic}",
                             "Content-Type": "application/x-www-form-urlencoded"},
                    data={"grant_type": "client_credentials"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def _ops_get(client: httpx.Client, token: str, url: str, params: dict, rng: str | None = None,
             max_retries: int = 5) -> dict | None:
    """OPS GET (JSON) with bearer auth, Range pagination, and backoff on the
    throttled free tier (429/503 → exponential)."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if rng:
        headers["X-OPS-Range"] = rng  # OPS accepts X-OPS-Range or Range; X-OPS-Range avoids proxy stripping
        headers["Range"] = rng
    for attempt in range(max_retries):
        try:
            r = client.get(url, params=params, headers=headers, timeout=40)
        except Exception as exc:
            logger.warning("OPS request error (%s) — backoff", type(exc).__name__)
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (429, 503):
            wait = min(2 ** attempt * 3, 60)
            logger.warning("OPS throttled (HTTP %d) — backoff %ds (try %d/%d)",
                           r.status_code, wait, attempt + 1, max_retries)
            time.sleep(wait)
            continue
        if r.status_code == 404:
            return None  # no results for this slice
        _note_throttle(r)
        r.raise_for_status()
        return r.json()
    return None


# EPO OPS fair-usage: honor the X-Throttling-Control header. OPS reports a colour
# + per-minute allowance per service (e.g. "search=green:30"). We pace the search
# loop to stay within it and back right off on yellow/red.
import re as _re  # noqa: E402

_OPS_THROTTLE = {"search_color": "green", "search_limit": 30}


def _note_throttle(resp) -> None:
    h = resp.headers.get("X-Throttling-Control", "")
    m = _re.search(r"search=(\w+):(\d+)", h)
    if m:
        _OPS_THROTTLE["search_color"] = m.group(1)
        _OPS_THROTTLE["search_limit"] = int(m.group(2))


def _throttle_sleep() -> None:
    """Sleep between OPS searches to respect the reported per-minute allowance.
    OPS reports green/yellow/red/black (black = service blocked → back off hard)."""
    color, limit = _OPS_THROTTLE["search_color"], max(1, _OPS_THROTTLE["search_limit"])
    if color == "black":
        logger.warning("OPS throttle BLACK (service blocked) — backing off 120s")
        time.sleep(120)
    elif color == "red":
        time.sleep(15)
    elif color == "yellow":
        time.sleep(6)
    else:  # green — pace to the per-minute search limit, with margin
        time.sleep(max(2.5, 60.0 / limit + 0.5))


def search_biblio(client: httpx.Client, token: str, cql: str, page_range: str):
    """One page (Range) of /published-data/search/biblio for a CQL query.
    Returns the list of exchange-document dicts (or [])."""
    data = _ops_get(client, token, f"{OPS_BASE}/rest-services/published-data/search/biblio",
                    params={"q": cql}, rng=page_range)
    if not data:
        return []
    return _exchange_documents(data)


# --------------------------------------------------------------------------- #
# Parsing (OPS returns XML-as-JSON with ops:/exchange: keys, "$" text nodes)
# --------------------------------------------------------------------------- #

def _as_list(x):
    """OPS collapses single-element arrays to objects — normalize to a list."""
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _text(node) -> str:
    """Pull the text out of an OPS '{"$": "..."}' node (or a plain string)."""
    if isinstance(node, dict):
        return str(node.get("$", "")).strip()
    return str(node or "").strip()


def _exchange_documents(data: dict) -> list[dict]:
    sr = (data.get("ops:world-patent-data", {})
              .get("ops:biblio-search", {})
              .get("ops:search-result", {}))
    # `exchange-documents` may be a single group (dict) or a list of groups; each
    # group's `exchange-document` may itself be a single doc or a list.
    out: list[dict] = []
    for grp in _as_list(sr.get("exchange-documents")):
        if isinstance(grp, dict):
            out.extend(d for d in _as_list(grp.get("exchange-document")) if isinstance(d, dict))
    return out


def parse_exchange_document(doc: dict) -> dict | None:
    """Normalize one OPS exchange-document → a flat patent record.

    Returns {title, abstract, pub_number, pub_date, applicant, cpc, url} or None
    if it lacks a usable title."""
    bib = doc.get("bibliographic-data", {})

    # Title: prefer English, else first available.
    titles = _as_list(bib.get("invention-title"))
    title = ""
    for t in titles:
        if isinstance(t, dict) and t.get("@lang") == "en":
            title = _text(t)
            break
    if not title and titles:
        title = _text(titles[0])
    if not title:
        return None

    # Abstract (may live on doc, English preferred).
    abstract = ""
    for ab in _as_list(doc.get("abstract")):
        if not isinstance(ab, dict):
            continue
        if ab.get("@lang") in (None, "en") or not abstract:
            abstract = " ".join(_text(p) for p in _as_list(ab.get("p"))).strip()
            if ab.get("@lang") == "en":
                break

    # Publication reference: country + doc-number + kind + date (epodoc form).
    pub_number, pub_date, _pub_concat = "", None, ""
    for did in _as_list(bib.get("publication-reference", {}).get("document-id")):
        if not isinstance(did, dict):
            continue
        if did.get("@document-id-type") == "docdb":
            country = _text(did.get("country"))
            number = _text(did.get("doc-number"))
            kind = _text(did.get("kind"))
            # Canonical node key is dashed (country-number-kind), matching the
            # HF/BDDS ingest + patent_links graph. kind_code() splits on the last
            # dash — an undashed key would silently break the citation-graph join.
            pub_number = f"{country}-{number}-{kind}" if country and number else ""
            _pub_concat = f"{country}{number}{kind}"  # espacenet url uses the concatenated form
            pub_date = _text(did.get("date")) or pub_date
    # date is YYYYMMDD → ISO
    if pub_date and len(pub_date) == 8:
        pub_date = f"{pub_date[:4]}-{pub_date[4:6]}-{pub_date[6:8]}"

    # Applicant (first).
    applicant = ""
    for ap in _as_list(bib.get("parties", {}).get("applicants", {}).get("applicant")):
        if isinstance(ap, dict):
            applicant = _text(ap.get("applicant-name", {}).get("name"))
            if applicant:
                break

    # CPC classes.
    cpc = []
    for c in _as_list(bib.get("patent-classifications", {}).get("patent-classification")):
        if isinstance(c, dict) and _text(c.get("classification-scheme", {}).get("@scheme", "")) or True:
            sec = _text(c.get("section")) if isinstance(c, dict) else ""
            cls = _text(c.get("class")) if isinstance(c, dict) else ""
            if sec:
                cpc.append(f"{sec}{cls}")

    url = f"https://worldwide.espacenet.com/patent/search/family/publication/{_pub_concat}" if pub_number else ""
    return {"title": title, "abstract": abstract, "pub_number": pub_number,
            "pub_date": pub_date, "applicant": applicant, "cpc": cpc, "url": url}


def record_to_excerpt(rec: dict) -> str:
    """Build the excerpt text fed to the signal pipeline: abstract + applicant
    so classification/embedding has substance even when the abstract is short."""
    parts = []
    if rec["abstract"]:
        parts.append(rec["abstract"])
    if rec["applicant"]:
        parts.append(f"Applicant: {rec['applicant']}.")
    if rec["cpc"]:
        parts.append(f"CPC: {', '.join(rec['cpc'][:6])}.")
    return " ".join(parts).strip() or rec["title"]


# --------------------------------------------------------------------------- #
# Ingest
# --------------------------------------------------------------------------- #

def _cpc_classes_for(vertical: str, cpc: str | None) -> list[str]:
    if cpc:
        return [cpc]
    return CPC_VERTICAL.get(vertical, [])


def ingest(vertical: str, cpc: str | None, after: str, before: str,
           dry_run: bool, max_pages: int = 20) -> dict:
    """Pull patents for `vertical` (one or all of its CPC classes) in [after, before)."""
    classes = _cpc_classes_for(vertical, cpc)
    if not classes:
        logger.error("No CPC classes for vertical %s (and no --cpc given)", vertical)
        return {"fetched": 0, "inserted": 0, "duplicates": 0}
    pd_from = after.replace("-", "")
    pd_to = before.replace("-", "")

    source_id = -1 if dry_run else db.upsert_source(
        name="EPO OPS Patents", feed_url=f"{OPS_BASE}/rest-services/published-data/search",
        source_type="api", vertical=vertical)  # 'api' is CHECK-safe

    stats = {"fetched": 0, "inserted": 0, "duplicates": 0, "skipped": 0}
    with httpx.Client(headers={"User-Agent": "catandary-trends/patents"}) as client:
        token = get_token(client)
        for cls in classes:
            cql = f'cpc=/low "{cls}" and pd within "{pd_from} {pd_to}"'
            logger.info("[patents] %s | CPC %s | %s..%s", vertical, cls, after, before)
            for page in range(max_pages):
                lo = page * 100 + 1
                docs = search_biblio(client, token, cql, f"{lo}-{lo + 99}")
                if not docs:
                    break
                for doc in docs:
                    rec = parse_exchange_document(doc)
                    if rec is None or not rec["url"]:
                        stats["skipped"] += 1
                        continue
                    stats["fetched"] += 1
                    if dry_run:
                        stats["inserted"] += 1
                        continue
                    eid = db.insert_raw_entry(source_id, rec["url"], rec["title"],
                                              record_to_excerpt(rec)[:2000], rec["pub_date"],
                                              pub_number=rec["pub_number"],
                                              kind_code=kind_code(rec["pub_number"]))
                    stats["duplicates" if eid is None else "inserted"] += 1
                _throttle_sleep()  # honor OPS X-Throttling-Control (fair usage)
            logger.info("  CPC %s done: fetched=%d inserted=%d dup=%d",
                        cls, stats["fetched"], stats["inserted"], stats["duplicates"])

    tag = "[dry] " if dry_run else ""
    logger.info("%s%s patents: fetched %d | %s %d | %d dup | %d skip", tag, vertical,
                stats["fetched"], "würde einfügen" if dry_run else "eingefügt",
                stats["inserted"], stats["duplicates"], stats["skipped"])
    return stats


# --------------------------------------------------------------------------- #
# Provider 2: HuggingFace Google-Patents export (KEYLESS, worldwide, parquet)
# nbettencourt/google-patents-data-preview — 340k patents with title/abstract/
# date/cpc/assignee. Read selected columns from the auto-converted parquet over
# HTTP (skips the heavy claims/description), filter EN + our CPC classes + date,
# route to a vertical by CPC. No credentials required — works today.
# --------------------------------------------------------------------------- #

HF_GPATENTS = "nbettencourt/google-patents-data-preview"
HF_PARQUET = f"https://huggingface.co/api/datasets/{HF_GPATENTS}/parquet/default/train"
HF_NUM_FILES = 49
_GP_COLS = ["publication_number", "country_code", "title_localized", "abstract_localized",
            "publication_date", "filing_date", "cpc", "assignee_harmonized", "assignee",
            "citation", "parent", "child"]


def _pub_of(x):
    """publication_number from a citation/parent/child entry (dict or string)."""
    if isinstance(x, dict):
        return x.get("publication_number") or None
    return x or None


def patent_links(row: dict, src: str) -> list[tuple]:
    """Edges for the citation/family graph: (src, dst, link_type, category).
    'cites' = backward citation (src cites dst); 'parent'/'child' = family/continuity."""
    out = []
    for c in row.get("citation") or []:
        dst = _pub_of(c)
        if dst:
            out.append((src, dst, "cites", (c.get("category") if isinstance(c, dict) else None) or None))
    for p in row.get("parent") or []:
        dst = _pub_of(p)
        if dst:
            out.append((src, dst, "parent", None))
    for ch in row.get("child") or []:
        dst = _pub_of(ch)
        if dst:
            out.append((src, dst, "child", None))
    return out


def _en_text(localized) -> str:
    """English text from a Google-Patents '*_localized' array [{text,language}]."""
    for item in localized or []:
        if isinstance(item, dict) and item.get("language") == "en":
            return (item.get("text") or "").strip()
    return ""  # non-English → skip (the pipeline is English)


def gp_record(row: dict) -> dict | None:
    """Normalize a Google-Patents parquet row → the shared patent record, or None
    if it has no English title or no in-scope CPC class."""
    title = _en_text(row.get("title_localized"))
    if not title:
        return None
    vert = vertical_for_cpc(row.get("cpc"))
    if vert is None:
        return None
    pd = str(row.get("publication_date") or "")
    pub_date = f"{pd[:4]}-{pd[4:6]}-{pd[6:8]}" if len(pd) == 8 else None
    assignee = ""
    for a in (row.get("assignee_harmonized") or row.get("assignee") or []):
        assignee = (a.get("name") if isinstance(a, dict) else str(a)) or ""
        if assignee:
            break
    num = row.get("publication_number", "")
    return {"title": title, "abstract": _en_text(row.get("abstract_localized")),
            "pub_number": num, "pub_date": pub_date, "applicant": assignee,
            "cpc": [c.get("code", "") for c in (row.get("cpc") or [])][:8],
            "url": f"https://patents.google.com/patent/{num}/en" if num else "",
            "vertical": vert, "links": patent_links(row, num), "kind_code": kind_code(num)}


def ingest_hf_gpatents(after: str, before: str, max_files: int, dry_run: bool,
                       scratch: str = "/tmp") -> dict:
    """Stream the Google-Patents parquet files, filter to EN + our CPC classes +
    [after, before), and insert under a per-vertical 'Google Patents (V)' source."""
    import pyarrow.parquet as pq
    af, bf = int(after.replace("-", "")), int(before.replace("-", ""))
    db.init_db()  # ensure pub_number column + patent_links table exist
    src_ids: dict[str, int] = {}
    link_buf: list[tuple] = []
    st = {"scanned": 0, "matched": 0, "inserted": 0, "duplicates": 0, "skipped": 0, "links": 0}
    n = min(max_files, HF_NUM_FILES)
    with httpx.Client(timeout=180, headers={"User-Agent": "catandary-trends/patents"}) as client:
        for i in range(n):
            path = os.path.join(scratch, f"gp_{i}.parquet")
            try:
                r = client.get(f"{HF_PARQUET}/{i}.parquet", follow_redirects=True)
                r.raise_for_status()
                with open(path, "wb") as fh:
                    fh.write(r.content)
            except Exception as exc:
                logger.warning("parquet %d download failed: %s — skipping", i, exc)
                continue
            try:
                pf = pq.ParquetFile(path)
                for rg in range(pf.num_row_groups):
                    for row in pf.read_row_group(rg, columns=_GP_COLS).to_pylist():
                        st["scanned"] += 1
                        pdv = row.get("publication_date")
                        if not (pdv and af <= int(pdv) < bf):
                            continue
                        rec = gp_record(row)
                        if rec is None or not rec["url"]:
                            st["skipped"] += 1
                            continue
                        st["matched"] += 1
                        if dry_run:
                            st["inserted"] += 1
                            continue
                        v = rec["vertical"]
                        if v not in src_ids:
                            src_ids[v] = db.upsert_source(
                                name=f"Google Patents ({v})", feed_url=f"hf://google-patents/{v}",
                                source_type="api", vertical=v)
                        eid = db.insert_raw_entry(src_ids[v], rec["url"], rec["title"],
                                                  record_to_excerpt(rec)[:2000], rec["pub_date"],
                                                  pub_number=rec["pub_number"], kind_code=rec["kind_code"])
                        st["duplicates" if eid is None else "inserted"] += 1
                        # capture edges even on URL-dup, so existing patents get their graph
                        if rec["links"]:
                            link_buf.extend(rec["links"])
                            if len(link_buf) >= 5000:
                                st["links"] += db.insert_patent_links(link_buf); link_buf.clear()
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass
            if link_buf:
                st["links"] += db.insert_patent_links(link_buf); link_buf.clear()
            logger.info("parquet %d/%d — scanned=%d matched=%d inserted=%d dup=%d links=%d",
                        i + 1, n, st["scanned"], st["matched"], st["inserted"], st["duplicates"], st["links"])
    tag = "[dry] " if dry_run else ""
    logger.info("%sGoogle-Patents: scanned %d | matched %d | %s %d | %d dup | %d off-scope | %d graph-edges",
                tag, st["scanned"], st["matched"], "würde einfügen" if dry_run else "eingefügt",
                st["inserted"], st["duplicates"], st["skipped"], st["links"])
    return st


# --------------------------------------------------------------------------- #
# Provider 3: EPO BDDS DOCDB bulk (worldwide bibliographic, OFFICIAL, no sampling)
# Needs the myEPO account login (EPO_LOGIN/EPO_PASSWORD). Downloads a delivery file
# → nested per-country DOCDB XML (exch:exchange-document) → title/abstract/CPC/date/
# applicant + citations (references-cited) + INPADOC family (family-member). The
# legit production source that replaces the HF sample (see BACKLOG).
# --------------------------------------------------------------------------- #

BDDS_OAUTH = "https://login.epo.org/oauth2/aus3up3nz0N133c0V417/v1/token"
BDDS_CLIENT = "MG9hM3VwZG43YW41cE1JOE80MTc="
BDDS_API = "https://publication-bdds.apps.epo.org/bdds/bdds-bff-service/prod/api"
_EXCH = "{http://www.epo.org/exchange}"


def bdds_token(client: httpx.Client) -> str:
    """OAuth2 password grant against login.epo.org (myEPO account login)."""
    user = (os.getenv("EPO_LOGIN") or "").strip()
    pw = (os.getenv("EPO_PASSWORD") or "").strip()
    if not user or not pw:
        raise RuntimeError("EPO_LOGIN / EPO_PASSWORD not set (your myEPO account login)")
    r = client.post(BDDS_OAUTH, headers={"Authorization": f"Basic {BDDS_CLIENT}",
                    "Content-Type": "application/x-www-form-urlencoded"},
                    data={"grant_type": "password", "username": user, "password": pw, "scope": "openid"})
    r.raise_for_status()
    return r.json()["access_token"]


def _dt(e) -> str:
    return (e.text or "").strip() if e is not None else ""


def parse_docdb_document(doc) -> dict | None:
    """One DOCDB exch:exchange-document → normalized record, or None if it has no
    English title or no in-scope CPC class."""
    bib = doc.find(f"{_EXCH}bibliographic-data")
    if bib is None:
        return None
    # Canonical DASHED key (country-number-kind), matching the citation graph +
    # the OPS/HF ingest. The exchange-document carries country/doc-number/kind as
    # attributes with the FULL kind; the epodoc doc-number is concatenated AND
    # truncates the kind (B9 -> B), which would orphan the patent from the graph.
    pub = _dashed_key(doc.get("country", ""), doc.get("doc-number", ""), doc.get("kind", ""))
    if not pub:  # fallback to the data-format="docdb" publication-reference
        for pr in bib.findall(f"{_EXCH}publication-reference"):
            if pr.get("data-format") == "docdb":
                did = pr.find("document-id")
                if did is not None:
                    pub = _dashed_key(_dt(did.find("country")), _dt(did.find("doc-number")),
                                      _dt(did.find("kind")))
    if not pub:
        return None
    title = next((_dt(t) for t in bib.findall(f"{_EXCH}invention-title") if t.get("lang") == "en"), "")
    if not title:
        return None
    cpc_struct: list[tuple[str, bool]] = []  # (symbol, inventive)
    pcs = bib.find(f"{_EXCH}patent-classifications")
    if pcs is not None:
        for pc in pcs.findall("patent-classification"):
            s = _dt(pc.find("classification-symbol"))
            if s:
                val = _dt(pc.find("classification-value"))  # 'I' inventive | 'A' additional
                inv = (not val) or val.strip().upper().startswith("I")
                cpc_struct.append((s.replace(" ", ""), inv))
    cpc = [c for c, _ in cpc_struct]
    vert = vertical_for_cpc([{"code": c, "inventive": inv} for c, inv in cpc_struct])
    if vert is None:
        return None
    ab = next((a for a in doc.findall(f"{_EXCH}abstract") if a.get("lang") == "en"), None)
    abstract = " ".join(_dt(p) for p in ab.findall(f"{_EXCH}p")) if ab is not None else ""
    date = doc.get("date-publ", "")
    pub_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else None
    applicant = ""
    for an in bib.iter(f"{_EXCH}applicant-name"):
        applicant = _dt(an.find("name"))
        if applicant:
            break
    links = []
    for pc in doc.iter():  # citations live under references-cited/citation/patcit
        if pc.tag.endswith("patcit"):
            did = pc.find("document-id")
            # cited doc-id also carries country/doc-number/kind — build the dashed
            # dst so edges match the node keys (a bare doc-number never joined).
            d = _dashed_key(_dt(did.find("country")), _dt(did.find("doc-number")),
                            _dt(did.find("kind"))) if did is not None else ""
            if d:
                links.append((pub, d, "cites", None))
    for fm in doc.iter(f"{_EXCH}family-member"):
        did = fm.find("document-id")
        d = _dashed_key(_dt(did.find("country")), _dt(did.find("doc-number")),
                        _dt(did.find("kind"))) if did is not None else ""
        if d and d != pub:
            links.append((pub, d, "family", None))
    return {"title": title, "abstract": abstract, "pub_number": pub, "pub_date": pub_date,
            "applicant": applicant, "cpc": cpc[:8], "cpc_struct": cpc_struct, "vertical": vert,
            # espacenet url uses the concatenated form (no dashes)
            "url": f"https://worldwide.espacenet.com/patent/search/publication/{pub.replace('-', '')}",
            "kind_code": doc.get("kind", "") or kind_code(pub), "links": links}


def ingest_bdds(product_id: int, after: str, before: str, max_files: int,
                scratch: str, dry_run: bool, cpc_filter: str = "",
                max_outer: int = 0, skip_outer: int = 0) -> dict:
    """Download the latest delivery of a BDDS DOCDB product, parse the nested
    per-country XML, filter to our CPC classes + [after, before), insert.

    cpc_filter: keep only patents with a CPC code starting with this prefix
    (e.g. 'A23C' for dairy) — narrows a bounded sample. max_outer: cap on the
    number of outer delivery files downloaded (the full back-file is 162 files
    / tens of GB — cap it for a bounded validation run)."""
    db.init_db()
    af, bf = int(after.replace("-", "")), int(before.replace("-", ""))
    src_ids: dict[str, int] = {}
    link_buf: list[tuple] = []
    cpc_buf: list[tuple] = []
    st = {"docs": 0, "matched": 0, "inserted": 0, "duplicates": 0, "links": 0, "cpc": 0}
    with httpx.Client(timeout=600, headers={"User-Agent": "catandary-trends/patents"}) as client:
        token = bdds_token(client)
        prod = client.get(f"{BDDS_API}/products/{product_id}",
                          headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}).json()
        delivery = prod["deliveries"][0]
        did = delivery["deliveryId"]
        logger.info("[bdds] product %s delivery %s '%s' — %d files (cpc_filter=%s, max_outer=%s)",
                    product_id, did, delivery.get("deliveryName"), len(delivery["files"]),
                    cpc_filter or "-", max_outer or "all")
        outer_done = 0
        outer_seen = 0
        for f in delivery["files"]:
            if not f["fileName"].lower().endswith(".zip"):
                continue  # skip coherence CSVs and other non-DOCDB delivery files
            outer_seen += 1
            if skip_outer and outer_seen <= skip_outer:
                continue  # resume: outer files already processed in a previous run
            if max_outer and outer_done >= max_outer:
                logger.info("  reached max_outer=%d — stopping", max_outer)
                break
            outer_done += 1
            zpath = os.path.join(scratch, f["fileName"])
            logger.info("  downloading %s ...", f["fileName"])
            with client.stream("GET", f"{BDDS_API}/products/{product_id}/delivery/{did}/file/{f['fileId']}/download",
                               headers={"Authorization": f"Bearer {token}"}) as r:
                r.raise_for_status()
                with open(zpath, "wb") as fh:
                    for chunk in r.iter_bytes(1 << 20):
                        fh.write(chunk)
            with zipfile.ZipFile(zpath) as z:
                inner = [n for n in z.namelist() if n.endswith(".zip") and "/DOC/" in n]
                for name in (inner[:max_files] if max_files else inner):
                    try:
                        with z.open(name) as innerf, zipfile.ZipFile(innerf) as iz:
                            xml = iz.read(iz.namelist()[0])
                        root = ET.fromstring(xml)
                    except (zipfile.BadZipFile, ET.ParseError):
                        continue
                    for docu in root.findall(f"{_EXCH}exchange-document"):
                        st["docs"] += 1
                        date = docu.get("date-publ", "")
                        if not (len(date) == 8 and af <= int(date) < bf):
                            continue
                        rec = parse_docdb_document(docu)
                        if rec is None:
                            continue
                        if cpc_filter and not any(c.startswith(cpc_filter) for c in rec["cpc"]):
                            continue
                        st["matched"] += 1
                        if dry_run:
                            continue
                        v = rec["vertical"]
                        if v not in src_ids:
                            src_ids[v] = db.upsert_source(name=f"EPO DOCDB ({v})",
                                feed_url=f"bdds://docdb/{v}", source_type="api", vertical=v)
                        eid = db.insert_raw_entry(src_ids[v], rec["url"], rec["title"],
                            record_to_excerpt(rec)[:2000], rec["pub_date"],
                            pub_number=rec["pub_number"], kind_code=rec["kind_code"])
                        st["duplicates" if eid is None else "inserted"] += 1
                        if rec["links"]:
                            link_buf.extend(rec["links"])
                            if len(link_buf) >= 5000:
                                st["links"] += db.insert_patent_links(link_buf); link_buf.clear()
                        for code, inv in rec.get("cpc_struct", []):
                            cpc_buf.append((rec["pub_number"], code, db.cpc_subclass(code), 1 if inv else 0))
                        if len(cpc_buf) >= 5000:
                            st["cpc"] += db.insert_patent_cpc(cpc_buf); cpc_buf.clear()
                    logger.info("  %s — docs=%d matched=%d inserted=%d edges=%d",
                                name.split("/")[-1], st["docs"], st["matched"], st["inserted"], st["links"])
            try:
                os.remove(zpath)
            except OSError:
                pass
        if link_buf:
            st["links"] += db.insert_patent_links(link_buf)
        if cpc_buf:
            st["cpc"] += db.insert_patent_cpc(cpc_buf)
    tag = "[dry] " if dry_run else ""
    logger.info("%sBDDS DOCDB: docs %d | matched %d | %s %d | %d dup | %d edges | %d cpc", tag,
                st["docs"], st["matched"], "würde einfügen" if dry_run else "eingefügt",
                st["inserted"], st["duplicates"], st["links"], st["cpc"])
    return st


# --------------------------------------------------------------------------- #
# Self-test: validate parsing on a bundled OPS-shaped sample (no creds needed)
# --------------------------------------------------------------------------- #

_SAMPLE = {
  "ops:world-patent-data": {"ops:biblio-search": {"ops:search-result": {"exchange-documents": {
    "exchange-document": [{
      "bibliographic-data": {
        "publication-reference": {"document-id": [
          {"@document-id-type": "docdb", "country": {"$": "EP"},
           "doc-number": {"$": "4123456"}, "kind": {"$": "A1"}, "date": {"$": "20240515"}}]},
        "invention-title": [
          {"@lang": "de", "$": "Fermentiertes pflanzliches Proteinprodukt"},
          {"@lang": "en", "$": "Fermented plant protein product and method"}],
        "parties": {"applicants": {"applicant": [
          {"applicant-name": {"name": {"$": "NOVA FOODS GMBH"}}}]}},
        "patent-classifications": {"patent-classification": [
          {"section": {"$": "A"}, "class": {"$": "23"}},
          {"section": {"$": "C"}, "class": {"$": "12"}}]},
      },
      "abstract": [{"@lang": "en", "p": {"$": "A precision-fermentation process yields a plant protein with improved texture."}}],
    }]
  }}}}
}


def selftest() -> int:
    docs = _exchange_documents(_SAMPLE)
    assert len(docs) == 1, f"expected 1 doc, got {len(docs)}"
    rec = parse_exchange_document(docs[0])
    assert rec is not None
    assert rec["title"] == "Fermented plant protein product and method", rec["title"]
    assert rec["pub_number"] == "EP-4123456-A1", rec["pub_number"]
    assert rec["pub_date"] == "2024-05-15", rec["pub_date"]
    assert rec["applicant"] == "NOVA FOODS GMBH", rec["applicant"]
    assert rec["cpc"] == ["A23", "C12"], rec["cpc"]
    assert "precision-fermentation" in rec["abstract"], rec["abstract"]
    assert rec["url"].endswith("EP4123456A1")
    exc = record_to_excerpt(rec)
    assert "precision-fermentation" in exc and "NOVA FOODS" in exc and "A23" in exc
    # CPC→vertical map + routing
    assert "A23" in CPC_VERTICAL["FOOD"] and "A61" in CPC_VERTICAL["HEALTH"]
    assert vertical_for_cpc([{"code": "A61K9/00", "inventive": True}]) == "HEALTH"
    assert vertical_for_cpc([{"code": "F16B1/00"}]) is None  # off-scope → skipped
    # Google-Patents (HF) normalizer
    g = gp_record({"title_localized": [{"text": "Postbiotic snack bar", "language": "en"}],
                   "abstract_localized": [{"text": "A mood-claim snack.", "language": "en"}],
                   "publication_number": "US-12345-B2", "publication_date": 20230615,
                   "cpc": [{"code": "A23L33/00", "inventive": True}],
                   "assignee_harmonized": [{"name": "ACME FOODS"}],
                   "citation": [{"publication_number": "US-9000000-B1", "category": "EXA"},
                                {"publication_number": "EP-1-A1", "category": "APP"}],
                   "parent": [{"publication_number": "US-11000-A1"}], "child": []})
    assert g and g["vertical"] == "FOOD" and g["pub_date"] == "2023-06-15", g
    assert g["url"].endswith("US-12345-B2/en")
    # citation/family graph edges
    assert ("US-12345-B2", "US-9000000-B1", "cites", "EXA") in g["links"], g["links"]
    assert ("US-12345-B2", "EP-1-A1", "cites", "APP") in g["links"]
    assert ("US-12345-B2", "US-11000-A1", "parent", None) in g["links"]
    assert len(g["links"]) == 3
    assert gp_record({"title_localized": [{"text": "x", "language": "ja"}], "cpc": []}) is None  # non-EN
    # kind code / application-vs-grant
    assert g["kind_code"] == "B2"
    assert kind_code("US-2026165336-A1") == "A1" and is_application("US-2026165336-A1")
    assert kind_code("EP-4123456-B1") == "B1" and not is_application("EP-4123456-B1")
    assert kind_code("JP-H05341715-A") == "A" and is_application("JP-H05341715-A")
    print("selftest OK — OPS + Google-Patents parsing + CPC routing + kind codes validated")
    print(f"  parsed: {rec['pub_number']} ({rec['pub_date']}) '{rec['title']}' "
          f"CPC={rec['cpc']} applicant={rec['applicant']!r}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Patent ingester → raw_entries (signal space)")
    ap.add_argument("--source", choices=["hf-gpatents", "epo-ops", "epo-bdds"], default="hf-gpatents",
                    help="hf-gpatents = keyless Google-Patents (default); epo-ops = OPS query API; "
                         "epo-bdds = official DOCDB bulk (needs EPO_LOGIN/EPO_PASSWORD)")
    ap.add_argument("--product", type=int, default=3, help="epo-bdds product id (3=DOCDB front, 14=back file)")
    ap.add_argument("--vertical", help="epo-ops: required; hf-gpatents: ignored (auto-routed by CPC)")
    ap.add_argument("--cpc", help="epo-ops: specific CPC class; overrides the vertical's set")
    ap.add_argument("--after", help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--before", help="YYYY-MM-DD (exclusive)")
    ap.add_argument("--max-pages", type=int, default=20, help="epo-ops: pages (×100) per CPC class")
    ap.add_argument("--max-files", type=int, default=49, help="hf-gpatents/bdds: inner files to scan per outer (0=all)")
    ap.add_argument("--max-outer", type=int, default=0, help="epo-bdds: cap on outer delivery files (0=all; the back file is 162)")
    ap.add_argument("--skip-outer", type=int, default=0, help="epo-bdds: skip the first N outer files (resume a previous run)")
    ap.add_argument("--cpc-filter", help="epo-bdds: keep only CPC codes with this prefix (e.g. A23C)")
    ap.add_argument("--scratch", default="/tmp", help="hf-gpatents: temp dir for parquet downloads")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="validate parsing without network/creds")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not (args.after and args.before):
        ap.error("--after and --before are required (or use --selftest)")
    if args.source == "hf-gpatents":
        ingest_hf_gpatents(args.after, args.before, args.max_files, args.dry_run, args.scratch)
    elif args.source == "epo-bdds":
        ingest_bdds(args.product, args.after, args.before, args.max_files, args.scratch,
                    args.dry_run, cpc_filter=args.cpc_filter or "", max_outer=args.max_outer,
                    skip_outer=args.skip_outer)
    else:
        if not args.vertical:
            ap.error("epo-ops needs --vertical")
        ingest(args.vertical, args.cpc, args.after, args.before, args.dry_run, args.max_pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
