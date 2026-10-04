"""TDM reservation check in the full-text fetcher (compliance review 2026-09-02).

§44b UrhG allows the full-text copy for text and data mining only while the
rights holder has not reserved it in machine-readable form. The fetcher must
therefore stop BEFORE storing the article whenever it sees a TDMRep header/meta,
a `noai` robots directive, or a matching /.well-known/tdmrep.json rule — and
must keep working from the feed teaser alone in that case.

All HTTP is mocked (httpx.MockTransport); no host is contacted.
"""
import json
import time

import httpx
import pytest

import pipeline.article_fetcher as af

HOST = "publisher.test"
ARTICLE = f"https://{HOST}/news/story-1"
BODY_TEXT = ("Regulators approved the new fermentation line on Tuesday. " * 40)
PAGE = f"<html><head><title>x</title></head><body><article><p>{BODY_TEXT}</p></article></body></html>"


def _page(meta: str = "") -> str:
    return PAGE.replace("<head>", f"<head>{meta}")


@pytest.fixture(autouse=True)
def isolated_fetcher(tmp_path, monkeypatch):
    """No sleeps, no robots.txt request, fresh tdmrep cache in a temp file."""
    monkeypatch.setattr(af, "PER_HOST_DELAY", 0.0)
    monkeypatch.setattr(af, "TDM_RESPECT", True)
    monkeypatch.setattr(af, "TDMREP_CACHE_PATH", tmp_path / "tdmrep_cache.json")
    monkeypatch.setattr(af, "_tdmrep_cache", None)
    monkeypatch.setattr(af, "_robots", {HOST: None})   # no robots.txt (4xx) → allowed
    monkeypatch.setattr(af, "_last_hit", {})
    yield


def _client(routes: dict, calls: list | None = None) -> httpx.Client:
    """routes: path → (status, headers, body). Unlisted paths 404."""
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url.path)
        status, headers, body = routes.get(request.url.path, (404, {}, ""))
        return httpx.Response(status, headers=headers, text=body)
    return httpx.Client(transport=httpx.MockTransport(handler),
                        headers={"User-Agent": af.UA})


# --- signal detectors ---------------------------------------------------------

class TestSignalDetectors:
    def test_header_tdm_reservation(self):
        assert af.tdm_reservation_in_headers({"TDM-Reservation": "1"})
        assert af.tdm_reservation_in_headers({"tdm-reservation": " 1 "})
        assert af.tdm_reservation_in_headers({"TDM-Reservation": "0"}) is None
        assert af.tdm_reservation_in_headers({}) is None

    def test_header_x_robots_noai(self):
        assert af.tdm_reservation_in_headers({"X-Robots-Tag": "noai, noimageai"})
        assert af.tdm_reservation_in_headers({"X-Robots-Tag": "noindex, nofollow"}) is None

    def test_meta_tdm_reservation_any_attribute_order(self):
        assert af.tdm_reservation_in_html(_page('<meta name="tdm-reservation" content="1">'))
        assert af.tdm_reservation_in_html(_page("<meta content='1' name='TDM-Reservation'>"))
        assert af.tdm_reservation_in_html(_page('<meta name="tdm-reservation" content="0">')) is None

    def test_meta_robots_noai_variants(self):
        assert af.tdm_reservation_in_html(_page('<meta name="robots" content="index, noai">'))
        assert af.tdm_reservation_in_html(_page('<meta name="ROBOTS" content="noimageai">'))
        assert af.tdm_reservation_in_html(_page('<meta name="robots" content="index, follow">')) is None
        # bot-specific directives for other crawlers are not our reservation
        assert af.tdm_reservation_in_html(_page('<meta name="GPTBot" content="noindex">')) is None

    def test_meta_outside_head_scan_window_is_ignored(self):
        page = "<html><head></head><body>" + ("x" * (af._HEAD_SCAN_CHARS + 10)) + \
               '<meta name="tdm-reservation" content="1"></body></html>'
        assert af.tdm_reservation_in_html(page) is None

    def test_tdmrep_rules_first_match_wins(self):
        rules = [{"location": "/news/*", "tdm-reservation": 1},
                 {"location": "/", "tdm-reservation": 0}]
        assert af.tdm_reservation_in_tdmrep(ARTICLE, rules)
        assert af.tdm_reservation_in_tdmrep(f"https://{HOST}/blog/x", rules) is None
        # specific "open" rule before a generic reservation
        rules = [{"location": "/open/", "tdm-reservation": 0},
                 {"location": "/", "tdm-reservation": 1}]
        assert af.tdm_reservation_in_tdmrep(f"https://{HOST}/open/x", rules) is None
        assert af.tdm_reservation_in_tdmrep(ARTICLE, rules)

    def test_tdmrep_rules_tolerate_garbage(self):
        assert af.tdm_reservation_in_tdmrep(ARTICLE, None) is None
        assert af.tdm_reservation_in_tdmrep(ARTICLE, []) is None
        assert af.tdm_reservation_in_tdmrep(ARTICLE, [{"tdm-reservation": 1}]) is None  # no location
        assert af.tdm_reservation_in_tdmrep(ARTICLE, [{"location": "news", "tdm-reservation": "1"}])


# --- fetch behaviour ----------------------------------------------------------

class TestFetchHonoursReservation:
    def test_clean_page_is_stored(self):
        with _client({"/news/story-1": (200, {}, PAGE)}) as c:
            res = af.fetch_fulltext_result(ARTICLE, client=c)
        assert res.text and "fermentation" in res.text
        assert res.reason is None and not res.tdm_reserved

    def test_header_reservation_blocks_storage(self):
        with _client({"/news/story-1": (200, {"TDM-Reservation": "1"}, PAGE)}) as c:
            res = af.fetch_fulltext_result(ARTICLE, client=c)
        assert res.text is None and res.tdm_reserved
        assert "tdm-reservation" in res.reason
        assert af.fetch_fulltext(ARTICLE, client=c) is None

    def test_meta_reservation_blocks_storage(self):
        page = _page('<meta name="tdm-reservation" content="1">')
        with _client({"/news/story-1": (200, {}, page)}) as c:
            res = af.fetch_fulltext_result(ARTICLE, client=c)
        assert res.text is None and res.tdm_reserved

    def test_noai_meta_blocks_storage(self):
        page = _page('<meta name="robots" content="index, noai">')
        with _client({"/news/story-1": (200, {}, page)}) as c:
            assert af.fetch_fulltext_result(ARTICLE, client=c).tdm_reserved

    def test_well_known_reservation_prevents_article_request(self):
        calls: list[str] = []
        rules = json.dumps([{"location": "/", "tdm-reservation": 1}])
        with _client({"/.well-known/tdmrep.json": (200, {}, rules),
                      "/news/story-1": (200, {}, PAGE)}, calls) as c:
            res = af.fetch_fulltext_result(ARTICLE, client=c)
        assert res.tdm_reserved and "tdmrep.json" in res.reason
        assert "/news/story-1" not in calls          # never fetched the reserved page

    def test_well_known_is_asked_once_per_host_per_day(self):
        calls: list[str] = []
        routes = {"/.well-known/tdmrep.json": (404, {}, ""), "/news/story-1": (200, {}, PAGE)}
        with _client(routes, calls) as c:
            for _ in range(3):
                assert af.fetch_fulltext_result(ARTICLE, client=c).text
        assert calls.count("/.well-known/tdmrep.json") == 1
        # cache is persisted and carries the negative result
        cached = json.loads(af.TDMREP_CACHE_PATH.read_text())
        assert cached[HOST]["rules"] is None
        # a new process reads the file instead of asking again
        af._tdmrep_cache = None
        with _client(routes, calls) as c:
            assert af.fetch_fulltext_result(ARTICLE, client=c).text
        assert calls.count("/.well-known/tdmrep.json") == 1

    def test_well_known_is_refreshed_after_ttl(self):
        calls: list[str] = []
        routes = {"/.well-known/tdmrep.json": (404, {}, "")}
        with _client(routes, calls) as c:
            af.tdmrep_rules(HOST, client=c, now=time.time() - af.TDMREP_TTL_SECONDS - 5)
            af.tdmrep_rules(HOST, client=c)
        assert calls.count("/.well-known/tdmrep.json") == 2

    def test_tdm_respect_off_stores_despite_reservation(self, monkeypatch):
        monkeypatch.setattr(af, "TDM_RESPECT", False)
        calls: list[str] = []
        rules = json.dumps([{"location": "/", "tdm-reservation": 1}])
        with _client({"/.well-known/tdmrep.json": (200, {}, rules),
                      "/news/story-1": (200, {"TDM-Reservation": "1"}, PAGE)}, calls) as c:
            res = af.fetch_fulltext_result(ARTICLE, client=c)
        assert res.text and not res.tdm_reserved
        assert "/.well-known/tdmrep.json" not in calls

    def test_robots_still_checked_first(self, monkeypatch):
        monkeypatch.setattr(af, "_robots_ok", lambda url: False)
        calls: list[str] = []
        with _client({"/news/story-1": (200, {}, PAGE)}, calls) as c:
            res = af.fetch_fulltext_result(ARTICLE, client=c)
        assert res.reason == "robots" and not calls


class TestBatchSkipsReserved:
    def test_reserved_entry_keeps_teaser_only(self, tmp_path, monkeypatch):
        """fetch_batch must not write raw_content for a reserved article and must
        still fill the clean one — the reserved entry keeps title + excerpt."""
        import pipeline.db as pdb
        db_path = tmp_path / "t.db"
        monkeypatch.setattr(pdb, "DATABASE_PATH", str(db_path))
        pdb.init_db()
        sid = pdb.upsert_source("Publisher", f"https://{HOST}/feed", "trade_media", "TECH")
        e_ok = pdb.insert_raw_entry(sid, ARTICLE, "Clean", "teaser", None)
        e_res = pdb.insert_raw_entry(sid, f"https://{HOST}/news/story-2", "Reserved", "teaser", None)
        monkeypatch.setattr(af, "fulltext_source_names", lambda: {"Publisher"})
        routes = {"/news/story-1": (200, {}, PAGE),
                  "/news/story-2": (200, {"TDM-Reservation": "1"}, PAGE)}

        def handler(request):
            status, headers, body = routes.get(request.url.path, (404, {}, ""))
            return httpx.Response(status, headers=headers, text=body)
        real_client = httpx.Client
        monkeypatch.setattr(af.httpx, "Client",
                            lambda **kw: real_client(transport=httpx.MockTransport(handler)))
        filled = af.fetch_batch(limit=10)
        assert filled == 1
        with pdb.get_connection() as conn:
            rows = {r["id"]: r["raw_content"] for r in
                    conn.execute("SELECT id, raw_content FROM raw_entries").fetchall()}
        assert rows[e_ok] and "fermentation" in rows[e_ok]
        assert rows[e_res] is None


class TestUserAgent:
    def test_default_identity_is_honest_and_shared(self):
        from pipeline import feed_poller
        assert af.DEFAULT_USER_AGENT == feed_poller.DEFAULT_USER_AGENT
        ua = af.DEFAULT_USER_AGENT
        assert ua.startswith("CatandaryTrendsBot/")
        assert "https://catandary.de/" in ua
        assert "@" not in ua            # V2 (2026-09-11): Kontakt auf der Seite, nicht in jedem Log
        assert "Mozilla" not in ua and "Chrome" not in ua
        assert "Mozilla" not in feed_poller.FALLBACK_UA

    def test_env_override(self, monkeypatch):
        import importlib
        monkeypatch.setenv("CRAWLER_USER_AGENT", "TestBot/0.1 (+https://example.test)")
        mod = importlib.reload(af)
        try:
            assert mod.UA == "TestBot/0.1 (+https://example.test)"
        finally:
            monkeypatch.delenv("CRAWLER_USER_AGENT")
            importlib.reload(af)
