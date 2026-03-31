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
