"""MCP-Server „catandary-corpus" — der Catandary-Korpus als Werkzeuge für Claude Code /
Claude Desktop (Owner 2026-10-04, Plan `docs/plan_field_research_2026-10-04.md`).

Läuft in der Recherche-venv (`~/venvs/catandary-research`, MCP-SDK) und importiert
KEINEN Pipeline-Code: er startet den Korpus-Dienst (`pipeline/corpus_service.py`) mit
der Python der Main-venv dieses Worktrees als Kindprozess (freier Port, Einmal-Token,
endet mit uns) und reicht jeden Werkzeugaufruf per HTTP weiter.

Start (stdio): `bash tools/research/run_mcp.sh` — so steht es in `.mcp.json`.
Start (HTTP, für Open WebUI, Owner 06.10.): `run_mcp.sh --http [--port 8096]` — Streamable
HTTP unter `http://127.0.0.1:8096/mcp`, nur Loopback, jede Anfrage braucht
`Authorization: Bearer <Token>` aus `~/.config/catandary/corpus_mcp.token` (0600, wird beim
ersten Start erzeugt). Unit: `deploy/systemd/catandary-corpus-mcp.service`.
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
        "Read-only access to the Catandary trend corpus. Four tiers of dated signals: science "
        "(research corpus, 47.7M OpenAlex works, 2010+), patent (18.7M patents with citation graph, "
        "1990+), funding (grants, financing rounds, SEC Form D) and market (trade press, press "
        "releases, brand newsrooms; broad only since 2026 — older market data is thin). "
        "WORKFLOW: (1) map vocabulary with research_facets and term_counts; phrase searches catch "
        "off-topic fields (e.g. 'electrolyzed water' is mostly energy catalysis, 'single cell "
        "protein' mostly proteomics), so scope science with subfields/fields, patents with cpc "
        "prefixes and market/funding with vertical; (2) measure with field_probe / tir_block; "
        "(3) read sources (search_research, search_patents, search_signals → get_signal, "
        "fetch_url) before stating what they say; (4) BEFORE your final answer call "
        "verify_report with the full text and fix everything it flags. "
        "RULES: every number, DOI, CELEX or patent number must come from a tool result in this "
        "session — never from memory; never claim a tool call you did not make; counts are corpus "
        "measurements (shares of a tier), not market statistics; K is a relative improvement "
        "rate, not a forecast; published Catandary articles are machine-written — cite the source "
        "behind them. Web fetches go through a compliant fetcher (CatandaryTrendsBot, robots.txt, "
        "TDM reservations): a page without text was refused for a reason."),
)


@mcp.tool()
def research_facets(query: str, since_year: int | None = 2010, limit: int = 15) -> Any:
    """WHERE do the research hits of a phrase land? Hit counts per OpenAlex subfield and field
    plus the top topics. Use this FIRST for any science question: it shows whether a phrase
    means what you think (e.g. 'electrolyzed water': Biotechnology 242, Plant Science 86,
    Renewable Energy 79 … Food Science 55). Pick the relevant subfields/fields and pass them to
    search_research / term_counts. Phrase rules as in search_research. Fast (≈1 s)."""
    return _call("research_facets", query=query, since_year=since_year, limit=limit)


@mcp.tool()
def term_counts(terms: list[str], since_year: int = 1990, subfields: list[str] | None = None,
                fields: list[str] | None = None, cpc: list[str] | None = None,
                vertical: str | None = None) -> Any:
    """Hits per search phrase and tier (science, patent, funding, market) — how much does the
    corpus hold on a term? Each term is an exact phrase. Scope per tier to avoid counting
    off-topic hits: science by OpenAlex `subfields`/`fields` (names from research_facets, e.g.
    ["Food Science"]), patents by CPC prefixes `cpc` (e.g. ["A23", "A01N", "C02F1/46"]),
    market/funding by `vertical` (FOOD TECH HEALTH ECO DESIGN FASHION BIZ LIFESTYLE). Unscoped
    counts can be dominated by unrelated fields — say which scope you used. Science starts 2010."""
    return _call("term_counts", terms=terms, since_year=since_year, subfields=subfields, fields=fields,
                 cpc=cpc, vertical=vertical)


@mcp.tool()
def search_research(query: str, since_year: int | None = None, order: str = "cited", limit: int = 20,
                    subfields: list[str] | None = None, fields: list[str] | None = None) -> Any:
    """Research works (OpenAlex, 47.7M, 2010+): full-text search over title + abstract. Returns
    DOI, title, year, citations, FWCI, topic/subfield and the abstract start. A multi-word query
    without quotes/OR/- is an exact phrase; avoid long OR lists (they time out) — use
    subfields/fields instead (see research_facets). order: cited (foundations) | recent (newest).
    Cite ONLY works returned here, with the DOI exactly as returned; read the abstract before
    describing a work. Not for patents or press (use search_patents / search_signals)."""
    return _call("search_research", query=query, since_year=since_year, order=order, limit=limit,
                 subfields=subfields, fields=fields)


@mcp.tool()
def search_patents(query: str, since: str | None = None, limit: int = 20, cpc: list[str] | None = None) -> Any:
    """Patents (title + abstract index, 1990+), newest first, with publication number,
    assignees, abstract start and Espacenet link. Phrase rules as search_research. `cpc` limits
    to CPC prefixes (e.g. ["A23"] food, ["A23L3/32"] preservation by electric current) — check
    that returned titles fit the topic before using a class as an anchor. For counts per year,
    assignees and take-off use field_probe instead of counting results here."""
    return _call("search_patents", query=query, since=since, limit=limit, cpc=cpc)


@mcp.tool()
def search_signals(query: str, mode: str = "both", tier: str | None = None, vertical: str | None = None,
                   since: str | None = None, until: str | None = None, limit: int = 20) -> Any:
    """Corpus signals across all tiers (press, research, patents, funding) by text, meaning or
    both (rank fusion). mode: text | meaning | both. tier: science | patent | funding | market.
    vertical: FOOD TECH HEALTH ECO DESIGN FASHION BIZ LIFESTYLE. since/until: YYYY[-MM[-DD]].
    'meaning' finds related wording but also loose matches — check each hit's relevance and
    drop unrelated ones explicitly (the market tier returns many near-misses for niche topics).
    Use get_signal to read a hit before stating what it says. limit <= 50."""
    return _call("search_signals", query=query, mode=mode, tier=tier, vertical=vertical,
                 since=since, until=until, limit=limit)


@mcp.tool()
def get_signal(signal_id: int, max_chars: int = 4000) -> Any:
    """One signal with its source text (full text if fetched compliantly, else the teaser),
    taxonomy, entities and source link. Read this before describing a signal. The Catandary
    article text is machine-written — quote and cite the source, not the article.
    max_chars caps the texts (200..20000)."""
    return _call("get_signal", signal_id=signal_id, max_chars=max_chars)


@mcp.tool()
def field_list(customer: str | None = None) -> Any:
    """Customer files (fields/*.yaml) with their fields: search terms, CPC anchors, written
    sections. Use before field_week / field_sheet to get valid customer and field names."""
    return _call("field_list", customer=customer)


@mcp.tool()
def field_week(customer: str, week_date: str | None = None) -> Any:
    """Field Watch weekly measurement for all fields of a customer file: week vs. median of the
    four prior weeks per tier, 12 quarters on a fixed source panel, top signals, actors, nests.
    week_date: any date in the week (default: last week). Takes about a minute and blocks the
    service meanwhile. Only for configured customer fields (field_list)."""
    return _call("field_week", customer=customer, week_date=week_date)


@mcp.tool()
def field_sheet(customer: str, field: str) -> Any:
    """Full Trajectory Sheet measurement of one configured field: yearly series per tier since
    1990, take-off, assignees, CPC subclasses, landmark patents, most-cited works, maturity
    block. Takes minutes and blocks the service meanwhile. For an ad-hoc topic use field_probe."""
    return _call("field_sheet", customer=customer, field=field)


@mcp.tool()
def field_probe(phrase: str, terms: list[str] | None = None, cpc: list[str] | None = None) -> Any:
    """Field probe for an ad-hoc topic (the free first page of a sheet): yearly hits per tier,
    take-off year per tier (first year ≥ 15 % of the peak), top assignees (5 years), and — with
    CPC anchors — the maturity block (K, cycle time). Terms are phrases and are NOT
    subject-scoped: check research_facets first and say if a phrase is ambiguous. Without
    `cpc` the maturity block stays empty. Anchors are your choice: confirm them with
    search_patents(cpc=…) and report which you used."""
    return _call("field_probe", phrase=phrase, terms=terms, cpc=cpc)


@mcp.tool()
def tir_block(cpc: list[str]) -> Any:
    """Maturity block for CPC anchors from the patent citation graph: technology improvement
    rate K per year (relative development between fields, NOT a growth forecast and NOT a
    filing rate), cycle time, centrality. Report K with its year and the anchors used."""
    return _call("tir_block", cpc=cpc)


@mcp.tool()
def emerging_nests(scope: str = "global", limit: int = 20) -> Any:
    """Emerging-signal nests (dense, young pockets of signals) from the latest pre-computed run
    of a scope: global, vertical:FOOD, tier:science, domain:<key>. Each nest has a name,
    first-appearance per tier, age and its weaknesses (sources, largest source share). A finder,
    not a verdict; runs are recomputed on demand only, so state the run date."""
    return _call("emerging_nests", scope=scope, limit=limit)


@mcp.tool()
def web_search(query: str, count: int = 8, domains: list[str] | None = None) -> Any:
    """Web search (Brave, SearXNG fallback) returning titles, URLs and snippets. Snippets are
    not evidence: fetch_url a page before using its content. `domains` restricts to these
    hosts. Use for regulation, very recent events and facts the corpus lacks."""
    return _call("web_search", query=query, count=count, domains=domains)


@mcp.tool()
def fetch_url(url: str, max_chars: int = 4000, terms: list[str] | None = None) -> Any:
    """Fetch a public page compliantly (CatandaryTrendsBot, robots.txt, TDM reservation). No
    text if the site reserves TDM or blocks bots — the reason is returned; do not work around
    it. Legal texts (EUR-Lex via Cellar, gesetze-im-internet.de, …) are cut article-wise
    around `terms`. Only state what a legal act says after fetching it here."""
    return _call("fetch_url", url=url, max_chars=max_chars, terms=terms)


@mcp.tool()
def eurlex_search(keywords: list[str], in_force_only: bool = True, limit: int = 15) -> Any:
    """EU legal acts (regulations, directives, decisions, implementing/delegated acts) whose
    English title contains ALL keywords; returns CELEX, date, type, title and EUR-Lex link.
    A title is not the content: read the act with fetch_url before describing obligations,
    scopes or product types."""
    return _call("eurlex_search", keywords=keywords, in_force_only=in_force_only, limit=limit)


@mcp.tool()
def verify_report(text: str, window_minutes: int = 240, check_external: bool = True) -> Any:
    """Check a draft answer or report BEFORE you present it. Deterministic, no model: extracts
    DOIs, CELEX numbers, patent numbers and figures from `text` and compares them with the tool
    results of this session (last `window_minutes`), the corpus, Crossref and EUR-Lex/Cellar.
    Flags: DOI/CELEX/patent not found or with a different title, tools mentioned in the text
    but never called, figures that appear in no tool result. Remove or correct everything
    flagged, then present the corrected text. Pass the full text (max 300,000 characters)."""
    return _call("verify_report", text=text, window_minutes=window_minutes, check_external=check_external)


TOKEN_FILE = Path(os.environ.get("CORPUS_MCP_TOKEN_FILE", Path.home() / ".config/catandary/corpus_mcp.token"))


def http_token(path: Path = TOKEN_FILE) -> str:
    """Token für den HTTP-Betrieb lesen; fehlt die Datei, eine neue mit 0600 anlegen."""
    if path.exists():
        tok = path.read_text(encoding="utf-8").strip()
        if len(tok) >= 24:
            return tok
    path.parent.mkdir(parents=True, exist_ok=True)
    tok = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(tok + "\n")
    return tok


class BearerAuth:
    """ASGI-Hülle: HTTP-Anfragen nur mit `Authorization: Bearer <token>`; Lifespan läuft durch."""

    def __init__(self, app, token: str):
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            got = dict(scope.get("headers") or []).get(b"authorization", b"")
            if not secrets.compare_digest(got, self.expected):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
                return
        await self.app(scope, receive, send)


def serve_http(port: int) -> None:
    import uvicorn
    mcp.settings.host, mcp.settings.port = "127.0.0.1", port
    app = BearerAuth(mcp.streamable_http_app(), http_token())
    _start_service()                      # Korpus-Dienst sofort, nicht erst beim ersten Aufruf
    print(f"catandary-corpus MCP: http://127.0.0.1:{port}{mcp.settings.streamable_http_path} "
          f"(Bearer-Token in {TOKEN_FILE})", file=sys.stderr, flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    if "--http" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8096
        serve_http(port)
    else:
        mcp.run()
