"""Ein geöffneter Eintrag zeigt Beleg UND Einordnung (2026-09-10).

Vorher schlossen sie sich aus: bei einem veröffentlichten Trend sah das Modell
nur unseren geschriebenen Text und nie den Originalwortlaut — obwohl der bei
92 % der veröffentlichten Einträge in der DB liegt (85.924 von 93.790). Zitieren
soll es aus der Quelle, einordnen darf es mit unserem Text; also braucht es
beides, getrennt beschriftet.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.corpus_research as cr

ROW = {
    "status": "published", "title_en": "T", "body_en": "Unsere Einordnung.",
    "summary_en": "S", "source_name": "Outlet", "source_url": "https://o.example/a",
    "excerpt": "Originalwortlaut der Quelle.", "raw_content": None,
}


def _open(monkeypatch, **over):
    row = {**ROW, **over}

    class _Cur:
        def fetchone(self):
            return row

    class _Conn:
        def execute(self, *a, **k):
            return _Cur()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cr, "get_connection", lambda: _Conn())
    return cr.open_item(1)


class TestPublished:
    def test_both_blocks_are_present(self, monkeypatch):
        out = _open(monkeypatch)
        assert "Unsere Einordnung." in out
        assert "Originalwortlaut der Quelle." in out

    def test_blocks_are_labelled_apart(self, monkeypatch):
        out = _open(monkeypatch)
        assert "[Catandary article" in out and "[Source excerpt" in out
        assert out.index("[Catandary article") < out.index("[Source excerpt")

    def test_the_source_block_says_where_to_quote_from(self, monkeypatch):
        assert "quote from HERE" in _open(monkeypatch)

    def test_full_text_wins_over_the_teaser(self, monkeypatch):
        out = _open(monkeypatch, raw_content="Der ganze Artikeltext.")
        assert "Der ganze Artikeltext." in out
        assert "Originalwortlaut der Quelle." not in out

    def test_missing_excerpt_leaves_the_article_alone(self, monkeypatch):
        out = _open(monkeypatch, excerpt=None)
        assert "Unsere Einordnung." in out and "[Source excerpt" not in out


class TestSignal:
    def test_signal_shows_the_source_only(self, monkeypatch):
        out = _open(monkeypatch, status="signal")
        assert "Originalwortlaut der Quelle." in out
        assert "Raw signal" in out
        assert "[Catandary article" not in out

    def test_signal_without_text_says_so(self, monkeypatch):
        out = _open(monkeypatch, status="signal", excerpt=None, raw_content=None)
        assert "only its title is known" in out


class TestCleanSourceText:
    def test_tags_and_entities_go(self):
        raw = '<p class="wp">Airlines scrambled &#8212; the U.K.&#8217;s system <a href="x">failed</a>.</p>'
        got = cr.clean_source_text(raw)
        assert got == "Airlines scrambled — the U.K.’s system failed."

    def test_blank_line_runs_collapse(self):
        assert cr.clean_source_text("A</p>\n\n\n\n<p>B") == "A\n\nB"

    def test_empty_stays_empty(self):
        assert cr.clean_source_text("") == "" and cr.clean_source_text(None) == ""

    def test_wording_is_not_altered(self):
        """Der Auszug muss zitierfähig bleiben."""
        assert cr.clean_source_text("Exactly 2,000 flights were cancelled.") == \
            "Exactly 2,000 flights were cancelled."
