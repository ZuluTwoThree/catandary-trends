"""scripts/discover_from_aggregators.py (#97 WP2 helper): every index against
fixture responses (httpx.MockTransport — no host is contacted), aggregation,
the active-source/aggregator filters, feed autodiscovery, the reddit
credential gate, and the --probe hand-over to probe_source_compliance."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pipeline import article_fetcher as af      # noqa: E402
import discover_from_aggregators as dfa          # noqa: E402
import probe_source_compliance as psc            # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "discover"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def handler(request: httpx.Request) -> httpx.Response:
    u = request.url
    url, path, q = str(u), u.path, parse_qs(u.query.decode() if isinstance(u.query, bytes) else u.query)
    host = u.host
    js = {"content-type": "application/json"}
    html = {"content-type": "text/html; charset=utf-8"}
    xml = {"content-type": "application/rss+xml"}
    if host == "hacker-news.firebaseio.com":
        name = path.rsplit("/", 1)[-1].replace(".json", "")
        f = FIX / (f"hn_{name}.json" if not name.isdigit() else f"hn_item_{name}.json")
        return httpx.Response(200, headers=js, text=f.read_text()) if f.exists() else httpx.Response(200, headers=js, text="null")
    if host == "en.wikipedia.org":
        page = "wiki_links_page2.json" if "gplcontinue" in q else "wiki_links_page1.json"
        return httpx.Response(200, headers=js, text=_fx(page))
    if host == "www.wikidata.org":
        ids = q.get("ids", [""])[0].split("|")
        ents = json.loads(_fx("wikidata_entities.json"))["entities"]
        return httpx.Response(200, headers=js, text=json.dumps({"entities": {i: ents[i] for i in ids if i in ents}}))
    if host == "idw-online.de":
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /*pdfnews\nDisallow: /*pressreleasesrss\n")
        if path == "/pages/de/pressreleasesrss":
            return httpx.Response(200, headers=xml, text=_fx("idw.rss"))
        if path == "/de/news1":
            return httpx.Response(200, headers=html, text=_fx("idw_news_1.html"))
        if path == "/de/news2":
            return httpx.Response(200, headers=html, text=_fx("idw_news_2.html"))
        if path == "/de/pdfnews3":
            raise AssertionError("robots-disallowed idw page must not be fetched")
    if host == "example-tech.com":
        if path == "/":
            return httpx.Response(200, headers=html, text=_fx("home_example-tech.html"))
        if path == "/feed.xml":
            return httpx.Response(200, headers=xml, text=_fx("feed_example-tech.xml"))
        if path == "/post/2":
            return httpx.Response(200, headers=html, text="<html><head></head><body>ok</body></html>")
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
    if host in ("dbu.de", "www.dbu.de"):
        if path == "/":
            return httpx.Response(200, headers=html, text="<html><head></head><body>no feed link</body></html>")
        if path == "/feed":
            return httpx.Response(200, headers=xml, text=_fx("feed_example-tech.xml").replace("example-tech.com", "www.dbu.de"))
    if host == "www.reddit.com" and path == "/api/v1/access_token":
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(200, headers=js, text='{"access_token": "tok", "token_type": "bearer"}')
    if host == "oauth.reddit.com":
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, headers=js, text=_fx("reddit_top.json"))
    return httpx.Response(404, text="not found")


@pytest.fixture()
def client():
    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True,
                      headers={"User-Agent": psc.UA}) as c:
        yield c


@pytest.fixture(autouse=True)
def fast(monkeypatch, tmp_path):
    monkeypatch.setattr(dfa, "HN_DELAY", 0.0)
    monkeypatch.setattr(psc, "PER_HOST_DELAY", 0.0)
    monkeypatch.setattr(af, "PER_HOST_DELAY", 0.0)
    monkeypatch.setattr(af, "TDMREP_CACHE_PATH", tmp_path / "tdmrep.json")
    monkeypatch.setattr(af, "_tdmrep_cache", None)
    monkeypatch.setattr(af, "_last_hit", {})
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)


def _quiet(_msg: str) -> None:
    pass


T0 = psc.HostThrottle(0.0)


# ---------------------------------------------------------------- indices

def test_hn_counts_story_hosts_once_per_id(client):
    hits = dfa.collect_hn(client, limit=10, throttle=T0, log=_quiet)
    hosts = [h["host"] for h in hits]
    assert hosts == ["example-tech.com", "example-tech.com", "news.ycombinator.com", "blog.google"]
    assert all(h["index"] == "hn" for h in hits)
    assert hits[0]["title"] == "Tech post one"


def test_wikipedia_follows_continuation_and_reads_p856(client):
    hits = dfa.collect_wikipedia(client, pages=(("en", "List of trade magazines"),), throttle=T0, log=_quiet)
    assert [(h["host"], h["title"]) for h in hits] == [("alpha-magazine.example", "Alpha Magazine"),
                                                       ("zeta.example", "Zeta Weekly")]
    assert hits[0]["index"] == "wikipedia:en:List of trade magazines"


def test_idw_reads_institution_link_and_honours_robots_on_pages(client):
    notes: list[str] = []
    hits = dfa.collect_idw(client, limit=10, throttle=T0, log=notes.append)
    assert [h["host"] for h in hits] == ["dbu.de"]
    assert hits[0]["example"] == "https://www.dbu.de/"
    assert any("robots.txt disallows the RSS path" in n for n in notes)


def test_reddit_skipped_without_credentials(client):
    notes: list[str] = []
    assert dfa.collect_reddit(client, throttle=T0, log=notes.append) is None
    assert "sources@catandary.de" in notes[0]


def test_reddit_with_credentials_uses_link_domains(client, monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
    hits = dfa.collect_reddit(client, subs=("technology",), throttle=T0, log=_quiet)
    assert [h["host"] for h in hits] == ["example-tech.com", "youtu.be"]   # self post dropped, youtu.be dropped later
    assert hits[0]["index"] == "reddit:r/technology"


# ------------------------------------------------------- aggregate/filter

def test_aggregate_and_filter():
    hits = [{"host": "a.example", "index": "hn", "example": "u1", "title": "t"},
            {"host": "a.example", "index": "wikipedia:en:L", "example": "u2", "title": "t"},
            {"host": "b.example", "index": "hn", "example": "u3", "title": "t"},
            {"host": "sub.active.example", "index": "hn", "example": "u4", "title": "t"},
            {"host": "feeds.feedburner.com", "index": "hn", "example": "u5", "title": "t"},
            {"host": "news.ycombinator.com", "index": "hn", "example": "u6", "title": "t"}]
    cands = dfa.aggregate(hits)
    assert [(c["host"], c["count"]) for c in cands][:2] == [("a.example", 2), ("b.example", 1)]
    assert cands[0]["indices"] == {"hn": 1, "wikipedia": 1}
    kept, dropped = dfa.filter_candidates(cands, {"active.example", "feeds.feedburner.com"})
    assert [c["host"] for c in kept] == ["a.example", "b.example"]
    assert dropped["sub.active.example"].startswith("active source domain")
    assert dropped["feeds.feedburner.com"] == "active source"
    assert dropped["news.ycombinator.com"].startswith("aggregator")


def test_multi_tenant_hosts_filter_by_exact_host_only():
    cands = dfa.aggregate([{"host": "other.substack.com", "index": "hn", "example": "", "title": ""}])
    kept, dropped = dfa.filter_candidates(cands, {"mine.substack.com"})
    assert [c["host"] for c in kept] == ["other.substack.com"]


def test_helpers():
    assert dfa.host_of("https://WWW.Example.COM:443/x") == "example.com"
    assert dfa.host_of("mailto:x") is None
    assert dfa.registered_domain("news.bbc.co.uk") == "bbc.co.uk"
    assert dfa.registered_domain("blogs.nvidia.com") == "nvidia.com"


# ---------------------------------------------------------- end to end

def test_run_autodiscovers_feeds_for_shortlist(client):
    out = dfa.run(["hn", "idw"], client, hn_limit=10, idw_limit=10, top=5,
                  active_hosts={"blog.google"}, log=_quiet)
    assert out["hits"] == 5
    by_host = {c["host"]: c for c in out["shortlist"]}
    assert set(by_host) == {"example-tech.com", "dbu.de"}
    assert by_host["example-tech.com"]["feed_url"] == "https://example-tech.com/feed.xml"   # <link rel=alternate>
    assert by_host["dbu.de"]["feed_url"] == "https://dbu.de/feed"                           # fallback path
    assert out["dropped"] == {"news.ycombinator.com": "aggregator/platform (news.ycombinator.com)",
                              "blog.google": "active source"}
    table = dfa.format_table(out["shortlist"])
    assert "example-tech.com" in table and "hn:2" in table


def test_main_probe_hands_candidates_to_the_compliance_probe(monkeypatch, capsys, tmp_path):
    real_client = httpx.Client
    monkeypatch.setattr(dfa.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), follow_redirects=True,
                                                 headers={"User-Agent": psc.UA}))
    monkeypatch.setattr(psc, "active_feed_hosts", lambda cfg=None: {"blog.google"})
    out_json = tmp_path / "d.json"
    rc = dfa.main(["--index", "hn", "--hn-limit", "10", "--probe", "--yaml", "--json", str(out_json)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "probe: ok=1" in printed
    assert "- name: example-tech.com\n  feed_url: https://example-tech.com/feed.xml" in printed
    assert "discovered_via: hn" in printed
    data = json.loads(out_json.read_text())
    assert data["probe"][0]["tdm_status"] == "ok"
    assert data["skipped"] == []
