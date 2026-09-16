"""Sitemap-Archiv: die reinen Funktionen. Kein Netz, keine DB."""

import importlib.util
import os
import sys
import urllib.robotparser

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "ingest_sitemap_archive", os.path.join(_ROOT, "scripts", "ingest_sitemap_archive.py"))
SA = importlib.util.module_from_spec(_spec)
sys.modules["ingest_sitemap_archive"] = SA
_spec.loader.exec_module(SA)


class FakeClient:
    """Liefert vorbereitete Antworten statt Netz."""

    def __init__(self, pages):
        self.pages = pages
        self.asked = []

    def get(self, url):
        self.asked.append(url)
        body = self.pages.get(url)
        if body is None:
            raise RuntimeError("404")

        class R:
            status_code = 200
            content = body.encode()
            text = body

            def raise_for_status(self):
                pass
        return R()


def _rp(text):
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(text.splitlines())
    return rp


INDEX = """<?xml version="1.0"?><sitemapindex>
 <sitemap><loc>https://x.example/post-sitemap.xml</loc></sitemap>
 <sitemap><loc>https://x.example/wp-json-sitemap.xml</loc></sitemap>
</sitemapindex>"""

POSTS = """<?xml version="1.0"?><urlset>
 <url><loc>https://x.example/alt</loc><lastmod>2014-05-01</lastmod></url>
 <url><loc>https://x.example/mittel</loc><lastmod>2019-07-01</lastmod></url>
 <url><loc>https://x.example/neu</loc><lastmod>2026-09-01</lastmod></url>
 <url><loc>https://x.example/ohne-datum</loc></url>
</urlset>"""


def test_it_follows_a_sitemap_index_and_keeps_the_dates():
    c = FakeClient({"https://x.example/sitemap_index.xml": INDEX,
                    "https://x.example/post-sitemap.xml": POSTS,
                    "https://x.example/wp-json-sitemap.xml": POSTS})
    SA.DELAY = 0
    urls, skipped = SA.walk_sitemaps(["https://x.example/sitemap_index.xml"], None,
                                     "CatandaryTrendsBot", c)
    assert ("https://x.example/alt", "2014-05-01") in urls
    assert ("https://x.example/ohne-datum", None) in urls
    assert skipped == []


def test_a_sitemap_that_robots_forbids_is_never_fetched():
    """Der ganze Punkt des Werkzeugs: es umgeht keine Sperre, es nutzt die
    Tuer, die robots.txt selbst offen laesst."""
    rp = _rp("User-agent: *\nDisallow: /wp-json-sitemap.xml\n")
    c = FakeClient({"https://x.example/sitemap_index.xml": INDEX,
                    "https://x.example/post-sitemap.xml": POSTS,
                    "https://x.example/wp-json-sitemap.xml": POSTS})
    SA.DELAY = 0
    urls, skipped = SA.walk_sitemaps(["https://x.example/sitemap_index.xml"], rp,
                                     "CatandaryTrendsBot", c)
    assert "https://x.example/wp-json-sitemap.xml" in skipped
    assert "https://x.example/wp-json-sitemap.xml" not in c.asked
    assert len(urls) == 4          # nur die erlaubte Sitemap


def test_the_time_window_is_inclusive_at_the_start_and_exclusive_at_the_end():
    assert SA.in_window("2014-05-01", "2014-01", "2015-01") is True
    assert SA.in_window("2015-01-02", "2014-01", "2015-01") is False
    assert SA.in_window("2013-12-31", "2014-01", "2015-01") is False


def test_a_url_without_lastmod_stays_in_the_window():
    """Sonst verlieren wir stillschweigend die aeltesten Seiten vieler Sitemaps,
    die genau dort oft kein lastmod tragen."""
    assert SA.in_window(None, "2020-01", "2021-01") is True


def test_titles_come_from_the_slug_and_stay_readable():
    assert SA.title_from_url("https://x.example/lab-grown-milk") == "Lab grown milk"
    assert SA.title_from_url("https://x.example/a/b/some_post.html") == "Some post"
    assert SA.title_from_url("https://x.example/") == "https://x.example/"


def test_gzipped_sitemaps_are_unpacked():
    import gzip

    class GzClient(FakeClient):
        def get(self, url):
            class R:
                status_code = 200
                content = gzip.compress(POSTS.encode())
                text = ""

                def raise_for_status(self):
                    pass
            return R()
    assert "<urlset" in SA.fetch_xml("https://x.example/s.xml.gz", GzClient({}))


def test_robots_sitemap_lines_are_read_as_the_invitation_they_are():
    c = FakeClient({"https://x.example/robots.txt":
                    "User-agent: *\nDisallow: /wp-json/\nSitemap: https://x.example/sitemap_index.xml\n"})
    assert SA.sitemaps_from_robots("x.example", c) == ["https://x.example/sitemap_index.xml"]
