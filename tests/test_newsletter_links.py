"""Where a newsletter link points (#71 follow-up, owner decision 2026-08-12).

The newsletter's promise is that a cited signal leads to the outlet that
reported it — not to our own summary of it. That has to hold regardless of
whether catandary.de already serves /trends, and it must not depend on the
stored edition, which deliberately keeps relative links for the website's
archive view.
"""
import importlib

import pytest


def _mod(monkeypatch, site_live: bool):
    """Re-import the generator with PUBLIC_SITE_LIVE set as requested."""
    monkeypatch.setenv("PUBLIC_SITE_LIVE", "1" if site_live else "0")
    import pipeline.newsletter_generator as m
    return importlib.reload(m)


REFS = {
    "TECH": [{
        "title": "Nvidia opens its interconnect",
        "slug": "nvidia-opens-its-interconnect-123",
        "source_name": "The Register",
        "source_url": "https://www.theregister.com/nvidia-nvlink",
    }],
}


class TestCitationLinks:
    def test_cited_signal_links_to_the_source(self, monkeypatch):
        m = _mod(monkeypatch, site_live=False)
        html = m._md_links_to_html(
            "[Nvidia opens its interconnect](/trends/nvidia-opens-its-interconnect-123)", REFS)
        assert 'href="https://www.theregister.com/nvidia-nvlink"' in html
        assert "catandary.de" not in html

    def test_still_the_source_once_the_site_is_live(self, monkeypatch):
        """Not a workaround for the dark site — it is the product rule."""
        m = _mod(monkeypatch, site_live=True)
        html = m._md_links_to_html(
            "[Nvidia opens its interconnect](/trends/nvidia-opens-its-interconnect-123)", REFS)
        assert 'href="https://www.theregister.com/nvidia-nvlink"' in html


class TestSiteLinks:
    def test_mega_link_is_plain_text_while_the_site_is_dark(self, monkeypatch):
        m = _mod(monkeypatch, site_live=False)
        html = m._md_links_to_html("[Clean Energy Transition](/trends/mega)", REFS)
        assert "<a" not in html          # a guaranteed 404 is worse than no link
        assert "Clean Energy Transition" in html

    def test_mega_link_returns_when_the_site_is_live(self, monkeypatch):
        m = _mod(monkeypatch, site_live=True)
        html = m._md_links_to_html("[Clean Energy Transition](/trends/mega)", REFS)
        assert 'href="https://catandary.de/trends/mega"' in html

    def test_uncited_signal_is_not_invented_into_a_source_link(self, monkeypatch):
        """A slug missing from trend_refs has no known source — it must not
        silently borrow another signal's URL."""
        m = _mod(monkeypatch, site_live=False)
        html = m._md_links_to_html("[Something else](/trends/unknown-slug-999)", REFS)
        assert "<a" not in html
        assert "Something else" in html


class TestPassThrough:
    def test_absolute_urls_are_left_alone(self, monkeypatch):
        m = _mod(monkeypatch, site_live=False)
        html = m._md_links_to_html("[Study](https://doi.org/10.1000/x)", REFS)
        assert 'href="https://doi.org/10.1000/x"' in html

    def test_text_without_links_is_unchanged(self, monkeypatch):
        m = _mod(monkeypatch, site_live=False)
        assert m._md_links_to_html("No links here.", REFS) == "No links here."


class TestRenderedEmail:
    def test_body_cites_sources_and_avoids_dead_site_links(self, monkeypatch):
        m = _mod(monkeypatch, site_live=False)
        edition = {
            "year": 2026, "week": 32, "total_signals": 10,
            "editorial": "[Nvidia opens its interconnect](/trends/nvidia-opens-its-interconnect-123) led the week.",
            "vertical_summaries": {"TECH": "Hardware moved."},
            "mega_trend_radar": [], "trend_refs": REFS,
        }
        html = m.generate_html(edition)
        assert "https://www.theregister.com/nvidia-nvlink" in html
        assert "/trends/nvidia-opens-its-interconnect-123" not in html
        # the CTA falls back to the landing page, which does answer
        assert 'href="https://catandary.de"' in html
        assert 'href="https://catandary.de/trends"' not in html


def test_preheader_shows_prose_not_markdown(monkeypatch):
    """The inbox preview line is built from the editorial. Stripping only HTML
    left the raw "[Title](/trends/slug)" syntax visible to every reader."""
    m = _mod(monkeypatch, site_live=False)
    html = m.generate_html({
        "year": 2026, "week": 32, "total_signals": 10,
        "editorial": "[Nvidia opens its interconnect](/trends/nvidia-opens-its-interconnect-123) led the week.",
        "vertical_summaries": {}, "mega_trend_radar": [], "trend_refs": REFS,
    })
    preheader = html.split('opacity: 0; color:')[1].split('>')[1].split('</div>')[0]
    assert preheader.startswith("Nvidia opens its interconnect led the week.")
    assert "[" not in preheader and "](" not in preheader
