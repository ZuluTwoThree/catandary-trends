"""Lizenz je Artikel schlägt den Host-Vorbehalt (#97, Wege B+C, 2026-09-09).

Eine CC-BY-Lizenz ist eine Erlaubnis; der TDM-Vorbehalt aus §44b Abs. 3 sperrt
nur die Schranke, die ein lizenzierter Zugriff nicht braucht. Zusätzlich der
Compliance-Fix vom selben Tag: robots und TDM wurden nur gegen die ANGEFRAGTE
URL geprüft, sodass ein DOI-Link (doi.org -> nature.com) den site-weiten
Vorbehalt von nature.com umging und 12.000 Zeichen gespeichert wurden.

Alles gemockt (httpx.MockTransport), kein Host wird kontaktiert.
"""
from __future__ import annotations

import httpx
import pytest

from pipeline import article_fetcher as af
from pipeline import open_license as ol

BODY = "<html><head></head><body><article><p>" + ("Ein belastbarer Absatz. " * 60) + "</p></article></body></html>"
TDMREP = '[{"location": "/", "tdm-reservation": 1}]'


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(af, "PER_HOST_DELAY", 0.0)
    monkeypatch.setattr(af, "TDM_RESPECT", True)
    monkeypatch.setattr(af, "TDMREP_CACHE_PATH", tmp_path / "tdmrep_cache.json")
    monkeypatch.setattr(af, "_tdmrep_cache", None)
    monkeypatch.setattr(af, "_robots", {"doi.org": None, "publisher.example": None})
    monkeypatch.setattr(af, "_last_hit", {})
    yield


def _client(redirect_to: str | None = None) -> httpx.Client:
    """doi.org/x leitet auf den Verlag um, der eine site-weite tdmrep.json führt."""
    def handler(request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if path == "/.well-known/tdmrep.json":
            return httpx.Response(200 if host == "publisher.example" else 404, text=TDMREP)
        if host == "doi.org" and redirect_to:
            return httpx.Response(302, headers={"Location": redirect_to})
        return httpx.Response(200, text=BODY)
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True,
                        headers={"User-Agent": af.UA})


class TestRedirectIsRechecked:
    def test_doi_redirect_into_a_reserved_host_is_refused(self):
        c = _client(redirect_to="https://publisher.example/articles/x")
        res = af.fetch_fulltext_result("https://doi.org/10.1000/x", client=c)
        assert res.text is None
        assert res.tdm_reserved, res.reason

    def test_direct_request_to_the_reserved_host_still_refused(self):
        res = af.fetch_fulltext_result("https://publisher.example/articles/x", client=_client())
        assert res.text is None and res.tdm_reserved

    def test_unredirected_open_host_is_unaffected(self):
        res = af.fetch_fulltext_result("https://doi.org/10.1000/x", client=_client())
        assert res.text and len(res.text) > 400


class TestOpenLicenceOverride:
    def test_licence_lifts_the_host_reservation(self):
        c = _client(redirect_to="https://publisher.example/articles/x")
        res = af.fetch_fulltext_result("https://doi.org/10.1000/x", client=c, open_licence="cc-by")
        assert res.text and len(res.text) > 400, res.reason

    def test_licence_does_not_lift_robots(self, monkeypatch):
        """robots.txt ist die Zugriffspolitik der Seite, kein Rechtevorbehalt."""
        monkeypatch.setattr(af, "_robots_ok", lambda url: False)
        res = af.fetch_fulltext_result("https://publisher.example/articles/x",
                                       client=_client(), open_licence="cc-by")
        assert res.text is None and res.reason == "robots"


class TestLicenceClassification:
    @pytest.mark.parametrize("lic", ["cc-by", "CC-BY-4.0", "cc-by-sa", "cc0", "public-domain"])
    def test_open(self, lic):
        assert ol.is_open_licence(lic)

    @pytest.mark.parametrize("lic", ["cc-by-nc", "cc-by-nd", "cc-by-nc-nd", "", None, "all-rights-reserved"])
    def test_not_open(self, lic):
        assert not ol.is_open_licence(lic)


class TestResolverHelpers:
    def test_doi_from_nature_url(self):
        assert ol.doi_from_url("https://www.nature.com/articles/s41586-026-1") == "10.1038/s41586-026-1"

    def test_doi_from_generic_doi_path(self):
        assert ol.doi_from_url("https://x.example/doi/full/10.1080/1754.2026.1") == "10.1080/1754.2026.1"

    def test_no_doi_in_plain_url(self):
        assert ol.doi_from_url("https://www.thelancet.com/journals/lancet/article/PIIS01.../fulltext") is None

    def test_feed_prefix_is_stripped(self):
        assert ol.clean_title("[Articles] Robotic knee") == "Robotic knee"

    def test_data_repositories_rank_last(self):
        work = {"best_oa_location": {"pdf_url": "https://zenodo.org/record/1.pdf"},
                "primary_location": {"landing_page_url": "https://publisher.example/a"},
                "locations": []}
        assert ol._rank_locations(work) == ("https://publisher.example/a",
                                            "https://zenodo.org/record/1.pdf")

    def test_is_open_needs_both_licence_and_location(self):
        assert not ol.OpenWork(licence="cc-by").is_open
        assert not ol.OpenWork(oa_urls=("https://x/a",)).is_open
        assert ol.OpenWork(licence="cc-by", oa_urls=("https://x/a",)).is_open
