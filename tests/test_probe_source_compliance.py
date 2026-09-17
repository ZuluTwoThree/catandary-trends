"""scripts/probe_source_compliance.py (#97 WP1): every tdm_status case against
mocked HTTP (httpx.MockTransport — no host is contacted), feed-discovery for
domain inputs, licence detection, and the line-based sources.yaml patcher
(order + comments preserved, fulltext switched off on reserved/blocked)."""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import httpx
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pipeline import article_fetcher as af   # noqa: E402
import probe_source_compliance as psc         # noqa: E402

FEED = "https://pub.example/feed.xml"
ARTICLE = "https://pub.example/news/1"
RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Pub</title>
<item><title>Old</title><link>https://pub.example/news/0</link><pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate></item>
<item><title>New</title><link>{article}</link><pubDate>Tue, 01 Sep 2026 10:00:00 GMT</pubDate></item>
</channel></rss>""".format(article=ARTICLE)
HTML_OK = "<html><head><title>x</title></head><body><p>hello</p></body></html>"
HTML_HEADERS = {"content-type": "text/html; charset=utf-8"}
FEED_HEADERS = {"content-type": "application/rss+xml", "etag": '"abc"'}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(af, "PER_HOST_DELAY", 0.0)
    monkeypatch.setattr(af, "TDMREP_CACHE_PATH", tmp_path / "tdmrep_cache.json")
    monkeypatch.setattr(af, "_tdmrep_cache", None)
    monkeypatch.setattr(af, "_last_hit", {})
    monkeypatch.setattr(psc, "_TDMREP_HOST_LOCKS", {})


def _client(routes: dict, calls: list | None = None) -> httpx.Client:
    """routes: url → (status, headers, body) | Exception instance."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if calls is not None:
            calls.append(url)
        spec = routes.get(url)
        if spec is None:
            return httpx.Response(404, text="nope")
        if isinstance(spec, Exception):
            raise spec
        status, headers, body = spec
        return httpx.Response(status, headers=headers, text=body)
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True,
                        headers={"User-Agent": psc.UA})


def _routes(article=(200, HTML_HEADERS, HTML_OK), feed=(200, FEED_HEADERS, RSS),
            robots=(200, {}, "User-agent: *\nDisallow: /private\n"), tdmrep=None):
    r = {FEED: feed, ARTICLE: article, "https://pub.example/robots.txt": robots}
    if tdmrep is not None:
        r["https://pub.example/.well-known/tdmrep.json"] = tdmrep
    return r


def _probe(routes, entry=None, calls=None):
    entry = entry or {"input": FEED, "name": "Pub"}
    return psc.probe_sources([entry], client=_client(routes, calls), workers=2, delay=0.0)[0]


# ------------------------------------------------------------------ status

class TestStatus:
    def test_ok_source(self):
        calls: list[str] = []
        r = _probe(_routes(), calls=calls)
        assert r["tdm_status"] == "ok"
        assert r["fulltext_ok"] is True
        assert r["feed_entries"] == 2 and r["feed_newest"] == "2026-09-01"
        assert r["article_url"] == ARTICLE and r["article_http"] == 200
        assert r["conditional_get"] == "etag"
        assert r["robots_feed"] == "allow" and r["robots_article"] == "allow"
        # feed + tdmrep.json + article = 3 own requests (robots.txt once per host, uncounted)
        assert r["requests"] == 3
        assert calls.count("https://pub.example/robots.txt") == 1

    def test_reserved_by_header(self):
        r = _probe(_routes(article=(200, {**HTML_HEADERS, "TDM-Reservation": "1"}, HTML_OK)))
        assert r["tdm_status"] == "reserved"
        assert "tdm-reservation" in r["reason"]
        assert r["fulltext_ok"] is False

    def test_reserved_by_meta(self):
        page = '<html><head><meta content="1" name="tdm-reservation"></head><body>x</body></html>'
        r = _probe(_routes(article=(200, HTML_HEADERS, page)))
        assert r["tdm_status"] == "reserved" and "meta tdm-reservation" in r["reason"]

    def test_reserved_by_noai(self):
        page = '<html><head><meta name="robots" content="index, noai, noimageai"></head></html>'
        r = _probe(_routes(article=(200, HTML_HEADERS, page)))
        assert r["tdm_status"] == "reserved" and "noai" in r["reason"]

    def test_reserved_by_tdmrep_json_skips_article(self):
        calls: list[str] = []
        rules = '[{"location": "/news/*", "tdm-reservation": 1}]'
        r = _probe(_routes(tdmrep=(200, {"content-type": "application/json"}, rules)), calls=calls)
        assert r["tdm_status"] == "reserved" and "tdmrep.json" in r["reason"]
        assert ARTICLE not in calls
        assert r["article_http"] is None

    def test_reserved_by_feed_header(self):
        r = _probe(_routes(feed=(200, {**FEED_HEADERS, "TDM-Reservation": "1"}, RSS)))
        assert r["tdm_status"] == "reserved" and r["reason"].startswith("feed ")

    @pytest.mark.parametrize("code", [401, 403, 429])
    def test_blocked_article(self, code):
        r = _probe(_routes(article=(code, HTML_HEADERS, "denied")))
        assert r["tdm_status"] == "blocked"
        assert f"article HTTP {code}" in r["reason"]
        assert r["fulltext_ok"] is False

    def test_blocked_feed_403(self):
        r = _probe(_routes(feed=(403, {}, "denied")))
        assert r["tdm_status"] == "blocked" and "feed HTTP 403" in r["reason"]
        assert r["fulltext_ok"] is None          # article unverified: no auto-off (Variety 2026-09-04)

    def test_robots_disallows_feed_only(self):
        """A feed-level robots rule is a polling question (idw case): status
        blocked, but the article-level verdict stays clean."""
        r = _probe(_routes(robots=(200, {}, "User-agent: *\nDisallow: /feed.xml\n")))
        assert r["tdm_status"] == "blocked" and "feed URL" in r["reason"]
        assert r["robots_feed"] == "disallow" and r["robots_article"] == "allow"
        assert r["fulltext_ok"] is True

    def test_robots_disallows_article_for_our_bot(self):
        calls: list[str] = []
        robots = "User-agent: *\nDisallow:\n\nUser-agent: CatandaryTrendsBot\nDisallow: /news/\n"
        r = _probe(_routes(robots=(200, {}, robots)), calls=calls)
        assert r["tdm_status"] == "blocked" and "article URL" in r["reason"]
        assert ARTICLE not in calls
        assert r["fulltext_ok"] is False

    def test_feed_error_http_404(self):
        r = _probe({"https://pub.example/robots.txt": (200, {}, "")})
        assert r["tdm_status"] == "feed_error" and "404" in r["reason"]

    def test_feed_error_no_entries(self):
        r = _probe(_routes(feed=(200, FEED_HEADERS, "<rss><channel><title>x</title></channel></rss>")))
        assert r["tdm_status"] == "feed_error" and "no entries" in r["reason"]

    def test_feed_error_article_timeout_is_unverified_not_blocked(self):
        r = _probe(_routes(article=httpx.ReadTimeout("slow")))
        assert r["tdm_status"] == "feed_error"
        assert "unreachable" in r["reason"] and "ReadTimeout" in r["reason"]
        assert r["fulltext_ok"] is None          # unverified — never switches fulltext off

    def test_feed_error_article_5xx(self):
        r = _probe(_routes(article=(503, {}, "down")))
        assert r["tdm_status"] == "feed_error" and "503" in r["reason"]

    def test_robots_unreadable_counts_as_allowed(self):
        routes = _routes()
        routes["https://pub.example/robots.txt"] = httpx.ConnectError("boom")
        r = _probe(routes)
        assert r["tdm_status"] == "ok" and r["robots_feed"] == "unreadable"


class TestAggregators:
    def test_candidate_from_aggregator_is_rejected_without_request(self):
        calls: list[str] = []
        r = _probe({}, entry={"input": "https://www.techmeme.com/feed.xml", "name": None}, calls=calls)
        assert r["tdm_status"] == "rejected" and "techmeme.com" in r["reason"]
        assert calls == []

    def test_domain_input_from_aggregator_is_rejected(self):
        r = _probe({}, entry={"input": "news.google.com", "name": None})
        assert r["tdm_status"] == "rejected"

    def test_config_source_is_never_rejected(self):
        """hnrss.org/news.ycombinator.com-style sources the owner curated stay."""
        routes = _routes()
        r = _probe(routes, entry={"input": FEED, "feed_url": FEED, "name": "Pub", "from_config": True})
        assert r["tdm_status"] == "ok"

    def test_is_aggregator_matches_parent_domain(self):
        assert psc.is_aggregator("https://www.trendhunter.com/trends/x") == "trendhunter.com"
        assert psc.is_aggregator("feeds.feedly.com") == "feedly.com"
        assert psc.is_aggregator("https://blog.google/feed") is None
        assert psc.is_aggregator("https://example.com/rss") is None


# ---------------------------------------------------------------- licences

class TestLicense:
    def test_link_rel_license_cc_by(self):
        page = '<html><head><link rel="license" href="https://creativecommons.org/licenses/by/4.0/"></head></html>'
        r = _probe(_routes(article=(200, HTML_HEADERS, page)))
        assert r["license"] == "CC BY 4.0"
        assert r["license_hint"].startswith("link rel=license")

    def test_cc0_anchor(self):
        page = '<html><body><a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a></body></html>'
        r = _probe(_routes(article=(200, HTML_HEADERS, page)))
        assert r["license"] == "CC0 1.0"

    def test_text_only_is_a_hint_not_a_license(self):
        page = "<html><body><footer>Content available under the Open Government Licence v3.0</footer></body></html>"
        r = _probe(_routes(article=(200, HTML_HEADERS, page)))
        assert r["license"] is None
        assert r["license_hint"].startswith("text: Open Government Licen")

    def test_feed_license_element(self):
        rss = RSS.replace("<channel>", '<channel xmlns:creativeCommons="http://backend.userland.com/creativeCommonsRssModule">'
                          "<creativeCommons:license>https://creativecommons.org/licenses/by-sa/4.0/</creativeCommons:license>")
        rss = rss.replace('<rss version="2.0">', '<rss version="2.0" xmlns:creativeCommons="http://backend.userland.com/creativeCommonsRssModule">')
        r = _probe(_routes(feed=(200, FEED_HEADERS, rss)))
        assert r["license"] == "CC BY-SA 4.0"
        assert "feed license" in r["license_hint"]

    def test_clean_page_has_no_license(self):
        r = _probe(_routes())
        assert r["license"] is None and r["license_hint"] is None


# ------------------------------------------------------- domain discovery

class TestDiscovery:
    def test_domain_input_uses_link_rel_alternate(self):
        home = '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>'
        routes = _routes()
        routes["https://pub.example/"] = (200, HTML_HEADERS, home)
        r = _probe(routes, entry={"input": "pub.example", "name": None})
        assert r["feed_url"] == FEED and r["tdm_status"] == "ok"
        assert r["name"] == "pub.example"

    def test_domain_input_falls_back_to_feed_path(self):
        routes = _routes()
        routes["https://pub.example/"] = (200, HTML_HEADERS, HTML_OK)
        routes["https://pub.example/feed"] = routes.pop(FEED)
        r = _probe(routes, entry={"input": "https://pub.example/", "name": None})
        assert r["feed_url"] == "https://pub.example/feed" and r["tdm_status"] == "ok"

    def test_domain_without_feed_is_feed_error(self):
        routes = {"https://pub.example/robots.txt": (200, {}, ""), "https://pub.example/": (200, HTML_HEADERS, HTML_OK)}
        r = _probe(routes, entry={"input": "pub.example", "name": None})
        assert r["tdm_status"] == "feed_error" and "no feed found" in r["reason"]

    def test_looks_like_domain(self):
        assert psc.looks_like_domain("example.com")
        assert psc.looks_like_domain("https://example.com/")
        assert not psc.looks_like_domain("https://example.com/feed")
        assert not psc.looks_like_domain("example.com/rss.xml")


# ----------------------------------------------------------- pure classify

def test_classify_precedence():
    base = {"feed_ok": True, "article_url": ARTICLE, "article_http": 200,
            "robots_feed": "allow", "robots_article": "allow"}
    assert psc.classify({**base})[0] == "ok"
    assert psc.classify({**base, "rejected": "msn.com"})[0] == "rejected"
    assert psc.classify({**base, "feed_tdm": "header tdm-reservation: 1", "feed_http": 403})[0] == "reserved"
    assert psc.classify({**base, "feed_http": 429})[0] == "blocked"
    assert psc.classify({**base, "tdm_signal": "meta", "article_http": 403})[0] == "reserved"
    assert psc.classify({**base, "robots_article": "disallow", "article_http": None})[0] == "blocked"
    assert psc.classify({**base, "article_http": None, "article_error": "ReadTimeout"})[0] == "feed_error"


# --------------------------------------------------------- sources.yaml IO

SAMPLE_YAML = textwrap.dedent("""\
    # header comment
    verticals:
      FOOD:
        sources:
        - name: Clean Pub
          fulltext: true
          feed_url: https://pub.example/feed.xml
          type: trade_media
          lead_time_tier: market
        - name: Reserved Pub
          relevance_min: 0.6   # capped
          fulltext: true
          feed_url: https://reserved.example/rss
          type: trade_media
          lead_time_tier: now
        # a comment between items
        - name: Stale Status
          feed_url: https://stale.example/rss
          tdm_checked: "2026-08-01"
          tdm_status: ok
          type: trade_media
          lead_time_tier: now
        - name: Inactive
          active: false  # dead
          feed_url: https://dead.example/rss
          type: trade_media
      BIZ:
        sources:
        - name: Clean Pub
          fulltext: true
          feed_url: https://pub.example/feed.xml
          type: trade_media
          lead_time_tier: market
    cross_industry:
      press_wires:
      - name: Wire
        feed_url: https://wire.example/rss
        type: press_wire
        lead_time_tier: market
        fulltext: true          # meant for distribution
      # trailing comment
      science:
      - name: Lab
        feed_url: https://lab.example/rss
        type: research
    radar:
      FOOD:
      - food industry innovation announcement
    """)


def _result(feed_url, status, reason="r", fulltext_ok=None, license=None, name="X"):
    return {"name": name, "feed_url": feed_url, "tdm_status": status, "reason": reason,
            "fulltext_ok": (status == "ok") if fulltext_ok is None else fulltext_ok,
            "license": license, "from_config": True}


class TestYamlPatch:
    def test_iter_active_sources(self, tmp_path):
        cfg = yaml.safe_load(SAMPLE_YAML)
        entries = psc.iter_active_sources(cfg)
        names = [e["name"] for e in entries]
        assert "Inactive" not in names
        assert names.count("Clean Pub") == 2          # listed under two verticals
        assert {e["vertical"] for e in entries if e["name"] in ("Wire", "Lab")} == {"CROSS"}
        stale = next(e for e in entries if e["name"] == "Stale Status")
        assert stale["prev_status"] == "ok" and stale["prev_checked"] == "2026-08-01"
        assert psc.active_feed_hosts(cfg) == {"pub.example", "reserved.example", "stale.example",
                                              "wire.example", "lab.example"}

    def test_patch_inserts_replaces_and_switches_fulltext_off(self, tmp_path):
        p = tmp_path / "sources.yaml"
        p.write_text(SAMPLE_YAML, encoding="utf-8")
        results = [
            _result("https://pub.example/feed.xml", "ok", license="CC BY 4.0", name="Clean Pub"),
            _result("https://reserved.example/rss", "reserved", "meta tdm-reservation: 1", name="Reserved Pub"),
            _result("https://stale.example/rss", "blocked", "article HTTP 403 for the bot UA", name="Stale Status"),
            _result("https://wire.example/rss", "blocked", "robots.txt disallows the feed URL",
                    fulltext_ok=True, name="Wire"),
            _result("https://lab.example/rss", "feed_error", "feed HTTP 500", name="Lab"),
            _result("https://unknown.example/rss", "ok", name="Unknown"),
        ]
        s = psc.write_protocol_fields(p, results, "2026-09-04")
        assert s["updated"] == 6                        # Clean Pub twice
        assert s["fulltext_off"] == ["Reserved Pub"]    # Wire keeps fulltext: feed-level robots only
        assert s["missing"] == ["https://unknown.example/rss"]
        text = p.read_text(encoding="utf-8")
        # comments + order preserved
        assert text.startswith("# header comment\n")
        assert "# a comment between items" in text and "# trailing comment" in text
        assert "relevance_min: 0.6   # capped" in text
        assert "fulltext: true          # meant for distribution" in text
        # protocol fields inserted at the end of the item, existing ones replaced in place
        clean = text.split("- name: Clean Pub")[1].split("- name:")[0]
        assert clean.rstrip().endswith('lead_time_tier: market\n      tdm_checked: "2026-09-04"\n'
                                       '      tdm_status: ok\n      license: CC BY 4.0')
        stale = text.split("- name: Stale Status")[1].split("- name:")[0]
        assert 'tdm_checked: "2026-09-04"\n      tdm_status: blocked   # article HTTP 403' in stale
        assert stale.count("tdm_status") == 1
        reserved = text.split("- name: Reserved Pub")[1].split("# a comment")[0]
        assert "fulltext: false   # meta tdm-reservation: 1 — Prüfung 2026-09-04" in reserved
        wire = text.split("- name: Wire")[1].split("# trailing")[0]
        assert "fulltext: true" in wire and "tdm_status: blocked   # robots.txt disallows the feed URL" in wire
        # still valid YAML, same sources, loaders unaffected
        cfg = yaml.safe_load(text)
        assert cfg["radar"]["FOOD"] == ["food industry innovation announcement"]
        assert psc._item_keys(cfg) == psc._item_keys(yaml.safe_load(SAMPLE_YAML))
        lab = cfg["cross_industry"]["science"][0]
        assert lab["tdm_status"] == "feed_error" and lab["tdm_checked"] == "2026-09-04"
        inactive = cfg["verticals"]["FOOD"]["sources"][3]
        assert "tdm_status" not in inactive

    def test_patch_is_idempotent(self, tmp_path):
        p = tmp_path / "sources.yaml"
        p.write_text(SAMPLE_YAML, encoding="utf-8")
        results = [_result("https://pub.example/feed.xml", "ok", name="Clean Pub")]
        psc.write_protocol_fields(p, results, "2026-09-04")
        first = p.read_text(encoding="utf-8")
        psc.write_protocol_fields(p, results, "2026-09-04")
        assert p.read_text(encoding="utf-8") == first
        assert first.count("tdm_checked") == 3          # 2× Clean Pub + the pre-existing Stale line

    def test_dry_run_does_not_write(self, tmp_path):
        p = tmp_path / "sources.yaml"
        p.write_text(SAMPLE_YAML, encoding="utf-8")
        s = psc.write_protocol_fields(p, [_result("https://lab.example/rss", "ok")], "2026-09-04", dry_run=True)
        assert p.read_text(encoding="utf-8") == SAMPLE_YAML
        assert "tdm_status: ok" in s["text"]

    def test_rejected_results_are_never_written(self, tmp_path):
        p = tmp_path / "sources.yaml"
        p.write_text(SAMPLE_YAML, encoding="utf-8")
        s = psc.write_protocol_fields(p, [_result("https://lab.example/rss", "rejected")], "2026-09-04")
        assert s["updated"] == 0 and p.read_text(encoding="utf-8") == SAMPLE_YAML


class TestOutput:
    def test_yaml_snippet(self):
        results = [
            {"name": "New Pub", "feed_url": FEED, "tdm_status": "ok", "reason": "fine", "license": "CC BY 4.0",
             "license_hint": "link rel=license …", "from_config": False, "discovered_via": "hn"},
            {"name": "Agg", "input": "https://techmeme.com/", "feed_url": None, "tdm_status": "rejected",
             "reason": "aggregator/platform domain (techmeme.com) — never a source", "from_config": False},
            {"name": "Cfg", "feed_url": "https://x.example/rss", "tdm_status": "blocked",
             "reason": "article HTTP 403 for the bot UA", "license": None, "license_hint": "text: CC BY",
             "from_config": True},
        ]
        out = psc.format_yaml(results, "2026-09-04")
        assert "- name: New Pub\n  feed_url: https://pub.example/feed.xml\n  type: trade_media" in out
        assert '  tdm_checked: "2026-09-04"\n  tdm_status: ok\n  license: CC BY 4.0' in out
        assert "  discovered_via: hn" in out
        assert "# REJECTED Agg: aggregator/platform domain (techmeme.com)" in out
        assert "  tdm_status: blocked   # article HTTP 403 for the bot UA\n  # license hint (unstructured): text: CC BY" in out
        assert "TODO WP3" not in out.split("- name: Cfg")[1]
        assert yaml.safe_load(out.split("- name: Cfg")[0])  # snippet parses

    def test_table_and_summary(self):
        results = [{"name": "A", "tdm_status": "ok", "feed_ok": True, "feed_entries": 3, "feed_newest": "2026-09-01",
                    "robots_feed": "allow", "robots_article": "disallow", "article_http": 200,
                    "conditional_get": "etag+last-modified", "reason": "x"},
                   {"name": "B", "tdm_status": "feed_error", "feed_http": 404, "reason": "feed HTTP 404"}]
        table = psc.format_table(results)
        assert "allow/DENY" in table and "HTTP 404" in table
        assert psc.summarize(results) == {"ok": 1, "feed_error": 1}

    def test_input_file(self, tmp_path):
        f = tmp_path / "c.txt"
        f.write_text("# comment\nhttps://a.example/feed  A Pub\nb.example\n\n", encoding="utf-8")
        assert psc.read_input_file(f) == [{"input": "https://a.example/feed", "name": "A Pub"},
                                          {"input": "b.example", "name": None}]


def test_feed_403_retries_with_short_ua_token_like_the_poller():
    """pipeline.feed_poller retries a 403/406 feed once with the short token —
    the probe mirrors that (still honest, never a browser string)."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == FEED:
            seen.append(request.headers["user-agent"])
            if request.headers["user-agent"] == psc.FEED_FALLBACK_UA:
                return httpx.Response(200, headers=FEED_HEADERS, text=RSS)
            return httpx.Response(403, text="waf")
        if url == ARTICLE:
            return httpx.Response(200, headers=HTML_HEADERS, text=HTML_OK)
        return httpx.Response(404)
    client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": psc.UA})
    r = psc.probe_sources([{"input": FEED, "name": "Pub"}], client=client, workers=1, delay=0.0)[0]
    assert seen == [psc.UA, psc.FEED_FALLBACK_UA]
    assert r["tdm_status"] == "ok" and r["feed_ua_fallback"] is True


class TestRobotsRfc9309:
    """urllib.robotparser reads `*` literally; the probe evaluates the parsed
    rules itself: wildcards, `$` anchors, longest match, UA-specific groups."""

    @staticmethod
    def _rp(text: str):
        import urllib.robotparser
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(text.splitlines())
        return rp

    def test_wildcard_disallow_is_honoured(self):
        rp = self._rp("User-agent: *\nDisallow: /*pressreleasesrss\n")
        assert not psc.robots_allows(rp, psc.UA, "https://idw-online.de/pages/de/pressreleasesrss")
        assert psc.robots_allows(rp, psc.UA, "https://idw-online.de/de/news1")
        assert rp.can_fetch(psc.UA, "https://idw-online.de/pages/de/pressreleasesrss")  # urllib's blind spot

    def test_dollar_anchor(self):
        rp = self._rp("User-agent: *\nDisallow: /*.pdf$\n")
        assert not psc.robots_allows(rp, psc.UA, "https://x.example/a/b.pdf")
        assert psc.robots_allows(rp, psc.UA, "https://x.example/a/b.pdf?x=1")
        assert psc.robots_allows(rp, psc.UA, "https://x.example/a/b.pdfx")

    def test_query_rules_bite(self):
        """`?` in einer Regel wurde bis 2026-09-16 zu %3F kodiert, waehrend die
        URL-Seite ihren Query roh anhaengte — damit war JEDE query-basierte
        Regel wirkungslos. Gefunden bei der Pruefung von sciencealert.com, wo
        unser Pruefer die per robots gesperrte WordPress-Schnittstelle als
        erlaubt meldete."""
        rp = self._rp("User-agent: *\nDisallow: /?rest_route=\nDisallow: /*?utm_source=\n")
        assert not psc.robots_allows(rp, psc.UA, "https://x.example/?rest_route=/wp/v2/posts")
        assert not psc.robots_allows(rp, psc.UA, "https://x.example/artikel?utm_source=news")
        # ohne den Parameter bleibt dieselbe Seite erlaubt
        assert psc.robots_allows(rp, psc.UA, "https://x.example/artikel")
        assert psc.robots_allows(rp, psc.UA, "https://x.example/")

    def test_a_query_rule_does_not_block_a_different_parameter(self):
        rp = self._rp("User-agent: *\nDisallow: /*?s=\n")
        assert not psc.robots_allows(rp, psc.UA, "https://x.example/suche?s=trend")
        assert psc.robots_allows(rp, psc.UA, "https://x.example/suche?q=trend")

    def test_longest_match_wins_and_tie_allows(self):
        rp = self._rp("User-agent: *\nDisallow: /news/\nAllow: /news/public/\n")
        assert not psc.robots_allows(rp, psc.UA, "https://x.example/news/secret")
        assert psc.robots_allows(rp, psc.UA, "https://x.example/news/public/1")
        rp = self._rp("User-agent: *\nDisallow: /p\nAllow: /p\n")
        assert psc.robots_allows(rp, psc.UA, "https://x.example/page")

    def test_specific_group_beats_star(self):
        rp = self._rp("User-agent: *\nDisallow: /\n\nUser-agent: CatandaryTrendsBot\nAllow: /\n")
        assert psc.robots_allows(rp, psc.UA, "https://x.example/anything")
        rp = self._rp("User-agent: *\nDisallow:\n\nUser-agent: catandarytrendsbot\nDisallow: /news/\n")
        assert not psc.robots_allows(rp, psc.UA, "https://x.example/news/1")
        assert psc.robots_allows(rp, "OtherBot/1.0", "https://x.example/news/1")

    def test_empty_robots_allows_everything(self):
        assert psc.robots_allows(self._rp(""), psc.UA, "https://x.example/x")

    def test_percent_encoding_is_normalised(self):
        rp = self._rp("User-agent: *\nDisallow: /caf%C3%A9/\n")
        assert not psc.robots_allows(rp, psc.UA, "https://x.example/café/menu")


def test_robots_group_needs_exact_product_token():
    """RFC 9309: `User-agent: bot` must NOT apply to CatandaryTrendsBot (urllib's
    substring rule would); `User-Agent: catandarytrendsbot` (any case) does."""
    import urllib.robotparser
    rp = urllib.robotparser.RobotFileParser()
    rp.parse("User-agent: bot\nDisallow: /\n\nUser-agent: *\nAllow: /\n".splitlines())
    assert psc.robots_allows(rp, psc.UA, "https://x.example/a")
    assert not rp.can_fetch(psc.UA, "https://x.example/a")      # urllib's substring blind spot
    rp = urllib.robotparser.RobotFileParser()
    rp.parse("User-Agent: CATANDARYTRENDSBOT\nDisallow: /\n\nUser-agent: *\nAllow: /\n".splitlines())
    assert not psc.robots_allows(rp, psc.UA, "https://x.example/a")


def test_relative_article_link_is_resolved_against_the_site():
    rss = RSS.replace(ARTICLE, "/news/1").replace("<title>Pub</title>", "<title>Pub</title><link>https://pub.example/</link>")
    r = _probe(_routes(feed=(200, FEED_HEADERS, rss)))
    assert r["article_url"] == ARTICLE and r["tdm_status"] == "ok"


def test_aggregating_feed_type_api_skips_the_article_verdict():
    calls: list[str] = []
    r = _probe(_routes(article=(403, HTML_HEADERS, "denied")),
               entry={"input": FEED, "feed_url": FEED, "name": "HN", "from_config": True, "type": "api"},
               calls=calls)
    assert r["tdm_status"] == "ok" and "aggregating feed" in r["reason"]
    assert r["fulltext_ok"] is None and ARTICLE not in calls
    # the patcher must not touch fulltext for such a source
    import textwrap
    y = textwrap.dedent("""\
        verticals:
          TECH:
            sources:
            - name: HN
              fulltext: true
              feed_url: https://pub.example/feed.xml
              type: api
        """)
    import tempfile, pathlib
    p = pathlib.Path(tempfile.mkdtemp()) / "s.yaml"
    p.write_text(y, encoding="utf-8")
    s = psc.write_protocol_fields(p, [{**r, "from_config": True}], "2026-09-04")
    assert s["fulltext_off"] == [] and "fulltext: true" in p.read_text(encoding="utf-8")


def test_unknown_rel_license_link_is_a_hint_only():
    page = '<html><head><link rel="license" href="https://www.bund.de/DE/Services/Impressum/impressum.html"></head></html>'
    r = _probe(_routes(article=(200, HTML_HEADERS, page)))
    assert r["license"] is None and r["license_hint"].startswith("link rel=license https://www.bund.de")


def test_production_fetcher_uses_the_rfc_matcher(monkeypatch):
    """pipeline.article_fetcher._robots_ok must refuse a `Disallow: /*` page
    (Condé Nast pattern) — urllib's can_fetch would have let it through."""
    import urllib.robotparser
    rp = urllib.robotparser.RobotFileParser()
    rp.parse("User-agent: *\nDisallow: /*\nAllow: /*rss\n".splitlines())
    monkeypatch.setattr(af, "_robots", {"www.wired.com": rp})
    assert af._robots_ok("https://www.wired.com/feed/rss")
    assert not af._robots_ok("https://www.wired.com/story/some-article/")
    assert rp.can_fetch(af.UA, "https://www.wired.com/story/some-article/")   # the old blind spot


def test_feed_level_block_does_not_switch_fulltext_off(tmp_path):
    import textwrap
    p = tmp_path / "s.yaml"
    p.write_text(textwrap.dedent("""\
        verticals:
          TECH:
            sources:
            - name: Variety
              fulltext: true
              feed_url: https://pub.example/feed.xml
              type: trade_media
        """), encoding="utf-8")
    r = _probe(_routes(feed=(403, {}, "denied")), entry={"input": FEED, "feed_url": FEED, "name": "Variety", "from_config": True})
    s = psc.write_protocol_fields(p, [r], "2026-09-04")
    assert s["fulltext_off"] == []
    text = p.read_text(encoding="utf-8")
    assert "fulltext: true" in text and "tdm_status: blocked   # feed HTTP 403" in text


def test_feed_links_from_html_picks_footer_rss_links_only():
    """WP2 (2026-09-04): many German institutions/trade media link their feed
    only as a footer <a href>, not as <link rel="alternate">."""
    html = ('<a href="/feedback">fb</a><a href="https://www.example.de/presse/rss.xml">RSS</a>'
            '<a href="/aktuelles/feed/">Feed</a><a href="/logo.png?feed=1">img</a>'
            '<a href="mailto:rss@example.de">m</a><a href="/rss">rss</a><a href="/rss">dup</a>'
            '<a href="https://feedly.com/i/subscription/feed/x">feedly</a>')
    assert psc.feed_links_from_html(html, "https://example.de/") == [
        "https://www.example.de/presse/rss.xml", "https://example.de/aktuelles/feed/", "https://example.de/rss"]
    assert psc.feed_links_from_html("<a href='/rss'>" * 20, "https://x.de/", limit=1) == ["https://x.de/rss"]
