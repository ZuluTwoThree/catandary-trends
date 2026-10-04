"""Tests des gptr-Workers — laufen NUR in der Recherche-venv:

    ~/venvs/catandary-research/bin/python -m pytest -q tools/research/tests

In der Main-venv (CI, `python -m pytest`) wird die Datei übersprungen (kein gpt_researcher).
Geprüft wird, dass gpt-researcher unter dem Starter keine Seite selbst holt und keine
Verbindung außerhalb der Erlaubnisliste aufbaut.
"""
import asyncio
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("gpt_researcher")

from tools.research import gptr_run  # noqa: E402

TOKEN = "t" * 24
CALLS: list = []


class FakeService(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        CALLS.append(("GET", self.path))
        # einer mit Text, einer ohne — der ohne darf nie gekratzt werden
        self._send([{"url": "https://a.example/x", "raw_content": "Alpha text " * 30},
                    {"url": "https://b.example/y", "raw_content": ""}])

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        CALLS.append(("POST", self.path, self.headers.get("X-Corpus-Token"), body))
        self._send([{"url": u, "raw_content": "fetched " + u, "image_urls": [], "title": ""}
                    for u in body.get("urls", []) if "ok" in u])


@pytest.fixture(scope="module")
def service():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeService)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    gptr_run.install_egress_guard([])
    gptr_run.configure_env({"service": {"url": url, "token": TOKEN}, "scope": "web", "domains": ["eur-lex.europa.eu"]})
    gptr_run.patch_gptr(url, TOKEN)
    yield url
    srv.shutdown()


def test_dns_outside_allowlist_is_blocked(service):
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("example.com", 443)
    assert "dns:example.com" in gptr_run.EGRESS_BLOCKED


def test_connect_to_public_ip_is_blocked(service):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(OSError):
        s.connect(("93.184.216.34", 80))
    s.close()
    assert "connect:93.184.216.34" in gptr_run.EGRESS_BLOCKED


def test_requests_library_cannot_reach_the_web(service):
    import requests
    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get("https://www.example.org/", timeout=5)


def test_config_is_pinned(service):
    from gpt_researcher.config import Config
    cfg = Config()
    assert [r for r in cfg.retrievers] == ["custom"]
    assert cfg.user_agent.startswith("CatandaryTrendsBot/")
    assert cfg.context_filter == "keyword"
    assert cfg.image_generation_enabled is False
    assert cfg.mcp_strategy == "disabled"


def test_scraper_and_document_loader_fail_closed(service):
    from gpt_researcher.document.online_document import OnlineDocumentLoader
    from gpt_researcher.scraper import Scraper
    from gpt_researcher.utils.workers import WorkerPool
    with pytest.raises(RuntimeError, match="disabled"):
        asyncio.run(Scraper(["https://x.example"], "ua", "bs", WorkerPool(1)).run())
    with pytest.raises(RuntimeError, match="disabled"):
        asyncio.run(OnlineDocumentLoader(["https://x.example/doc.pdf"]).load())


def test_browse_urls_goes_through_the_service(service):
    from gpt_researcher.skills.browser import BrowserManager

    class R:
        verbose = False
        sources = []

        def add_research_sources(self, s):
            self.sources.extend(s)

    bm = BrowserManager.__new__(BrowserManager)
    bm.researcher = R()
    out = asyncio.run(bm.browse_urls(["https://ok.example/1", "https://blocked.example/2"]))
    assert [d["url"] for d in out] == ["https://ok.example/1"]
    post = [c for c in CALLS if c[0] == "POST"][-1]
    assert post[1] == "/gptr/fetch" and post[2] == TOKEN


def test_custom_retriever_hits_the_service_with_token_and_scope(service):
    from gpt_researcher.retrievers.custom.custom import CustomRetriever
    res = CustomRetriever("novel food").search()
    assert res[0]["url"] == "https://a.example/x"
    get = [c for c in CALLS if c[0] == "GET"][-1][1]
    assert "token=" + TOKEN in get and "scope=web" in get and "eur-lex.europa.eu" in get


def test_trim_context_respects_budget():
    ctx = ["one two three " * 100, "four " * 500, "five " * 10]
    out = gptr_run.trim_context(ctx, 400)
    assert sum(len(c.split()) for c in out) <= 401
    assert out[0].startswith("one")
