"""The newsletter mail is built from text we did not write — LLM prose, RSS titles,
source URLs. None of it may reach the HTML unescaped, and only http(s) URLs may
become links (security review 2026-10-04; twin of frontend/src/lib/safeHref.ts)."""
from __future__ import annotations

import pipeline.newsletter_generator as m

REFS = {"TECH": [{
    "title": "<b>Bold</b> & \"quoted\" title",
    "slug": "s-1",
    "source_name": "<img src=x onerror=alert(1)>Outlet",
    "source_url": 'javascript:alert(1)" onclick="x',
}]}


def _edition(**over):
    e = {"year": 2026, "week": 40, "total_signals": 3,
         "editorial": "Plain.", "vertical_summaries": {"TECH": "Moved."},
         "mega_trend_radar": [], "trend_refs": REFS}
    e.update(over)
    return e


def test_titles_and_outlet_names_are_escaped():
    out = m.generate_html(_edition())
    assert "<b>Bold</b>" not in out
    assert "&lt;b&gt;Bold&lt;/b&gt; &amp; \"quoted\" title" in out
    assert "<img src=x" not in out


def test_only_http_source_urls_become_links():
    out = m.generate_html(_edition())
    assert "javascript:" not in out
    assert 'onclick="x' not in out
    assert ">&lt;b&gt;Bold&lt;/b&gt;" in out      # listed as plain text, not a link
    good = {"TECH": [{"title": "T", "slug": "s", "source_name": "O",
                      "source_url": "https://outlet.example/a?b=1&c=2"}]}
    out = m.generate_html(_edition(trend_refs=good))
    assert 'href="https://outlet.example/a?b=1&amp;c=2"' in out


def test_editorial_markup_is_escaped_but_links_still_work():
    ed = ('Hidden <img src="https://evil.example/p.gif"> pixel and '
          '[Study](https://doi.org/10.1000/x) and [Bad](javascript:alert(1)).')
    out = m._md_links_to_html(ed, REFS)
    assert "<img" not in out
    assert "&lt;img src=&quot;https://evil.example/p.gif&quot;&gt;" in out or \
           '&lt;img src="https://evil.example/p.gif"&gt;' in out
    assert 'href="https://doi.org/10.1000/x"' in out
    assert "javascript:" not in out and "Bad" in out


def test_radar_names_are_escaped():
    out = m.generate_html(_edition(mega_trend_radar=[
        {"name_en": "<script>x</script>", "signal_count": "7", "momentum": "rising"}]))
    assert "<script>" not in out
    assert "&lt;script&gt;x&lt;/script&gt;" in out


def test_safe_href_mirrors_the_typescript_rule():
    ok = ("https://a.example/x", "http://a.example", "  https://a.example/p?q=1 ")
    bad = ("javascript:alert(1)", "data:text/html,x", "//a.example/x", "/trends/x",
           "https://a.example/\nx", "", None, "ftp://a.example")
    for u in ok:
        assert m._safe_href(u) == u.strip(), u
    for u in bad:
        assert m._safe_href(u) is None, u
