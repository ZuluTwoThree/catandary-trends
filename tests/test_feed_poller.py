"""Tests for feed poller."""

from pipeline.feed_poller import parse_published_date, get_entry_excerpt


class TestParsePublishedDate:
    def test_with_published_parsed(self):
        entry = {"published_parsed": (2026, 3, 15, 10, 30, 0, 0, 0, 0)}
        result = parse_published_date(entry)
        assert result is not None
        assert "2026-03-15" in result

    def test_with_updated_parsed(self):
        entry = {"updated_parsed": (2026, 3, 15, 10, 30, 0, 0, 0, 0)}
        result = parse_published_date(entry)
        assert result is not None

    def test_no_date(self):
        result = parse_published_date({})
        assert result is None

    def test_invalid_date(self):
        entry = {"published_parsed": None}
        result = parse_published_date(entry)
        assert result is None


class TestGetEntryExcerpt:
    def test_with_summary(self):
        entry = {"summary": "This is a summary"}
        assert get_entry_excerpt(entry) == "This is a summary"

    def test_with_content(self):
        entry = {"content": [{"value": "Content value"}]}
        assert get_entry_excerpt(entry) == "Content value"

    def test_empty(self):
        assert get_entry_excerpt({}) == ""

    def test_truncation(self):
        entry = {"summary": "x" * 3000}
        result = get_entry_excerpt(entry)
        assert len(result) <= 2000


class TestSourceFlagsFromYaml:
    """`store_excerpt: false` and `llm_pipeline: false` (#97, 2026-09-09).

    Signal mode for TDM-reserved sources: the feed is polled again, but only
    title/URL/date are stored (bibliographic metadata is not protected, the
    abstract in the teaser is) and the content cycle never sees the entries.
    """

    def _drive(self, monkeypatch, cfg_extra):
        from pipeline import feed_poller as fp
        seen = {"upsert": [], "insert": []}
        monkeypatch.setattr(fp, "upsert_source",
                            lambda *a, **k: seen["upsert"].append((a, k)) or 1)
        monkeypatch.setattr(fp, "insert_raw_entry",
                            lambda **k: seen["insert"].append(k) or 1)
        monkeypatch.setattr(fp, "update_source_last_fetched", lambda sid: None)
        monkeypatch.setattr(fp, "fetch_source", lambda *a, **k: [
            {"url": "https://j.example/a1", "title": "A paper",
             "excerpt": "Abstract text that must not be stored.",
             "published_date": "2026-09-09T00:00:00"}])
        cfg = {"sources": [{"name": "Reserved Journal",
                            "feed_url": "https://j.example/rss",
                            "type": "research", **cfg_extra}]}
        fp.poll_vertical_sources("FOOD", cfg)
        return seen

    def test_store_excerpt_false_drops_the_teaser(self, monkeypatch):
        seen = self._drive(monkeypatch, {"store_excerpt": False})
        assert seen["insert"][0]["excerpt"] is None
        assert seen["insert"][0]["title"] == "A paper"
        assert seen["insert"][0]["published_date"] == "2026-09-09T00:00:00"

    def test_default_keeps_the_teaser(self, monkeypatch):
        seen = self._drive(monkeypatch, {})
        assert seen["insert"][0]["excerpt"] == "Abstract text that must not be stored."

    def test_llm_pipeline_flag_reaches_upsert_source(self, monkeypatch):
        seen = self._drive(monkeypatch, {"llm_pipeline": False})
        assert seen["upsert"][0][1]["llm_pipeline"] is False

    def test_llm_pipeline_defaults_to_true(self, monkeypatch):
        seen = self._drive(monkeypatch, {})
        assert seen["upsert"][0][1]["llm_pipeline"] is True
