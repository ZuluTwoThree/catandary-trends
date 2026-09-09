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


class TestDryRun:
    """`--dry-run` zählt, ohne zu schreiben (#97, 2026-09-09).

    Vor einer Nacht, in der viele neue Quellen zum ersten Mal ziehen, will man
    die Menge kennen — ohne Quellen-Zeilen anzulegen, Einträge einzufügen oder
    `last_fetched` zu setzen.
    """

    def _cfg(self, **extra):
        return {"sources": [{"name": "Dry Source", "feed_url": "https://d.example/rss",
                             "type": "trade_media", **extra}]}

    def _entries(self, urls):
        return [{"url": u, "title": "T", "excerpt": "E",
                 "published_date": "2026-09-09T00:00:00"} for u in urls]

    def _patch(self, monkeypatch, known=(), urls=()):
        from pipeline import feed_poller as fp
        wrote = []
        monkeypatch.setattr(fp, "upsert_source", lambda *a, **k: wrote.append("upsert") or 1)
        monkeypatch.setattr(fp, "insert_raw_entry", lambda **k: wrote.append("insert") or 1)
        monkeypatch.setattr(fp, "update_source_last_fetched", lambda sid: wrote.append("touch"))
        monkeypatch.setattr(fp, "known_entry_urls", lambda u: set(known))
        monkeypatch.setattr(fp, "fetch_source", lambda *a, **k: self._entries(urls))
        return fp, wrote

    def test_counts_new_and_writes_nothing(self, monkeypatch):
        fp, wrote = self._patch(monkeypatch, known={"https://d.example/a"},
                                urls=["https://d.example/a", "https://d.example/b"])
        stats = fp.poll_vertical_sources("FOOD", self._cfg(), dry_run=True)
        assert stats["fetched"] == 2 and stats["new"] == 1 and stats["duplicate"] == 1
        assert wrote == [], "a dry run must not touch the database"

    def test_intra_feed_duplicates_count_once(self, monkeypatch):
        """UNIQUE(url) lets a repeated link through only once in a real poll."""
        fp, _ = self._patch(monkeypatch, urls=["https://d.example/x", "https://d.example/x"])
        stats = fp.poll_vertical_sources("FOOD", self._cfg(), dry_run=True)
        assert stats["new"] == 1 and stats["duplicate"] == 1

    def test_signal_only_sources_are_reported_apart(self, monkeypatch):
        fp, _ = self._patch(monkeypatch, urls=["https://d.example/s"])
        stats = fp.poll_vertical_sources("FOOD", self._cfg(llm_pipeline=False), dry_run=True)
        assert stats["new"] == 1 and stats["new_signal_only"] == 1

    def test_article_sources_do_not_count_as_signal(self, monkeypatch):
        fp, _ = self._patch(monkeypatch, urls=["https://d.example/s"])
        stats = fp.poll_vertical_sources("FOOD", self._cfg(), dry_run=True)
        assert stats["new"] == 1 and stats["new_signal_only"] == 0

    def test_real_poll_still_writes(self, monkeypatch):
        fp, wrote = self._patch(monkeypatch, urls=["https://d.example/a"])
        fp.poll_vertical_sources("FOOD", self._cfg(), dry_run=False)
        assert wrote == ["upsert", "insert", "touch"]

    def test_cli_flag_is_passed_through(self, monkeypatch):
        from pipeline import feed_poller as fp
        seen = {}
        monkeypatch.setattr(fp, "run_poll", lambda v, dry_run=False: seen.update(v=v, dry=dry_run))
        fp.main(["--dry-run", "FOOD"])
        assert seen == {"v": ["FOOD"], "dry": True}

    def test_cli_without_verticals_polls_everything(self, monkeypatch):
        from pipeline import feed_poller as fp
        seen = {}
        monkeypatch.setattr(fp, "run_poll", lambda v, dry_run=False: seen.update(v=v, dry=dry_run))
        fp.main([])
        assert seen == {"v": None, "dry": False}
