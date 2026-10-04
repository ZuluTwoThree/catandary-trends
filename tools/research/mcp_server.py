"""MCP-Server „catandary-corpus" — der Catandary-Korpus als Werkzeuge für Claude Code /
Claude Desktop (Owner 2026-10-04, Plan `docs/plan_field_research_2026-10-04.md`).

Läuft in der Recherche-venv (`~/venvs/catandary-research`, MCP-SDK) und importiert
KEINEN Pipeline-Code: er startet den Korpus-Dienst (`pipeline/corpus_service.py`) mit
der Python der Main-venv dieses Worktrees als Kindprozess (freier Port, Einmal-Token,
endet mit uns) und reicht jeden Werkzeugaufruf per HTTP weiter.

Start (stdio): `bash tools/research/run_mcp.sh` — so steht es in `.mcp.json`.
Alles lesend; Seitenabrufe nur über den konformen Fetcher (robots, TDM, Bot-Kennung).
"""
from __future__ import annotations

import atexit
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

REPO = Path(__file__).resolve().parents[2]
MAIN_PY = os.environ.get("CATANDARY_MAIN_PYTHON") or str(REPO / ".venv" / "bin" / "python")

_service: dict[str, Any] = {}


def _start_service() -> tuple[str, str]:
    if _service.get("url") and _service["proc"].poll() is None:
        return _service["url"], _service["token"]
    token = secrets.token_urlsafe(24)
    env = dict(os.environ, CORPUS_SERVICE_TOKEN=token, PYTHONUNBUFFERED="1")
    log = open(os.environ.get("CORPUS_SERVICE_LOG", "/tmp/catandary-corpus-mcp.log"), "a")
    proc = subprocess.Popen([MAIN_PY, "-m", "pipeline.corpus_service", "--port", "0",
                             "--parent-pid", str(os.getpid())],
                            cwd=str(REPO), env=env, stdout=subprocess.PIPE, stderr=log, text=True)
    line = proc.stdout.readline() if proc.stdout else ""
    if not line:
        raise RuntimeError(f"corpus service did not start (rc={proc.poll()}), see {log.name}")
    port = json.loads(line)["port"]
    _service.update(proc=proc, token=token, url=f"http://127.0.0.1:{port}")
    atexit.register(proc.terminate)
    return _service["url"], token


def _call(tool: str, **args) -> Any:
    args = {k: v for k, v in args.items() if v is not None}
    url, token = _start_service()
    r = httpx.post(f"{url}/tool/{tool}", json=args, headers={"X-Corpus-Token": token}, timeout=900)
    data = r.json()
    if not data.get("ok"):
        raise ValueError(data.get("error") or f"HTTP {r.status_code}")
    return data["result"]


mcp = FastMCP(
    "catandary-corpus",
    instructions=(
        "Read-only access to the Catandary trend corpus: ~2M dated signals in four tiers "
        "(science, patent, funding, market) since 1990, a 45M-work research corpus (from 2010), "
        "18.7M patents with citation graph, Field Watch / Trajectory Sheet measurements for "
        "customer fields (fields/<customer>.yaml), emerging-signal nests, plus compliant web "
        "search and page fetch (CatandaryTrendsBot, robots.txt and TDM reservations respected) "
        "and EU legal acts via EUR-Lex/Cellar. Counts are corpus measurements, not market "
        "statistics. Published Catandary articles are machine-written; prefer the source text."),
)


@mcp.tool()
def search_signals(query: str, mode: str = "both", tier: str | None = None, vertical: str | None = None,
                   since: str | None = None, until: str | None = None, limit: int = 20) -> Any:
    """Search corpus signals (press, research, patents, funding) by text, meaning or both (RRF).
    mode: text | meaning | both. tier: science | patent | funding | market.
    vertical: FOOD TECH HEALTH ECO DESIGN FASHION BIZ LIFESTYLE. since/until: YYYY[-MM[-DD]]. limit <= 50."""
    return _call("search_signals", query=query, mode=mode, tier=tier, vertical=vertical,
                 since=since, until=until, limit=limit)


@mcp.tool()
def get_signal(signal_id: int, max_chars: int = 4000) -> Any:
    """One signal with source text (full text if fetched compliantly, else teaser), taxonomy,
    entities and link. max_chars caps the texts (200..20000)."""
    return _call("get_signal", signal_id=signal_id, max_chars=max_chars)


@mcp.tool()
def search_research(query: str, since_year: int | None = None, order: str = "cited", limit: int = 20) -> Any:
    """Research works (OpenAlex corpus, 2010+), full-text search over title+abstract.
    A multi-word query without quotes/OR/- is a phrase. order: cited | recent."""
    return _call("search_research", query=query, since_year=since_year, order=order, limit=limit)


@mcp.tool()
def search_patents(query: str, since: str | None = None, limit: int = 20) -> Any:
    """Patents (title+abstract index), newest first, with assignees and Espacenet link."""
    return _call("search_patents", query=query, since=since, limit=limit)


@mcp.tool()
def term_counts(terms: list[str], since_year: int = 1990) -> Any:
    """Hits per search phrase and tier (science/patent/funding/market) — for mapping a
    customer's field to corpus vocabulary (Field Watch setup)."""
    return _call("term_counts", terms=terms, since_year=since_year)


@mcp.tool()
def field_list(customer: str | None = None) -> Any:
    """Customer files (fields/*.yaml) with their fields: terms, CPC anchors, written sections."""
    return _call("field_list", customer=customer)


@mcp.tool()
def field_week(customer: str, week_date: str | None = None) -> Any:
    """Field Watch weekly measurement for all fields of a customer (week vs. median of four
    prior weeks per tier, 12 quarters on a fixed source panel, signals, actors, nests).
    week_date: any date in the week to report (default: last week). Can take a minute."""
    return _call("field_week", customer=customer, week_date=week_date)


@mcp.tool()
def field_sheet(customer: str, field: str) -> Any:
    """Trajectory Sheet measurement of one field (yearly series per tier since 1990, take-off,
    assignees, CPC subclasses, landmark patents, most-cited works, maturity block). Takes minutes."""
    return _call("field_sheet", customer=customer, field=field)


@mcp.tool()
def field_probe(phrase: str, terms: list[str] | None = None, cpc: list[str] | None = None) -> Any:
    """Field probe for a phrase (free first page of a sheet). Without CPC anchors the maturity
    block stays empty (the GPU-based class suggestion is scripts/field_watch.py --probe)."""
    return _call("field_probe", phrase=phrase, terms=terms, cpc=cpc)


@mcp.tool()
def tir_block(cpc: list[str]) -> Any:
    """Maturity block for CPC anchors: technology improvement rate K (relative development,
    not a forecast), cycle time, centrality."""
    return _call("tir_block", cpc=cpc)


@mcp.tool()
def emerging_nests(scope: str = "global", limit: int = 20) -> Any:
    """Emerging-signal nests (dense, young pockets) from the latest run of a scope, e.g.
    global, vertical:FOOD, tier:science, domain:<key>. A finder, not a verdict."""
    return _call("emerging_nests", scope=scope, limit=limit)


@mcp.tool()
def web_search(query: str, count: int = 8, domains: list[str] | None = None) -> Any:
    """Web search (Brave, SearXNG fallback). domains restricts to these hosts."""
    return _call("web_search", query=query, count=count, domains=domains)


@mcp.tool()
def fetch_url(url: str, max_chars: int = 4000, terms: list[str] | None = None) -> Any:
    """Fetch a public page compliantly (CatandaryTrendsBot, robots.txt, TDM reservation).
    No text if the site reserves TDM or blocks bots — the reason is returned. Legal texts
    (EUR-Lex via Cellar, gesetze-im-internet.de, …) are cut article-wise around `terms`."""
    return _call("fetch_url", url=url, max_chars=max_chars, terms=terms)


@mcp.tool()
def eurlex_search(keywords: list[str], in_force_only: bool = True, limit: int = 15) -> Any:
    """EU legal acts (regulations, directives, decisions, implementing/delegated acts) whose
    English title contains all keywords; CELEX, date, EUR-Lex link. Read them with fetch_url."""
    return _call("eurlex_search", keywords=keywords, in_force_only=in_force_only, limit=limit)


if __name__ == "__main__":
    mcp.run()
