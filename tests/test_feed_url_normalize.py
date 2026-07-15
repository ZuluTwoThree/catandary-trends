"""Entry-link normalization (#48) — broken source links are a product defect.

Every case here is a real URL taken from the corpus, not a hypothetical.
"""
from pipeline.feed_poller import normalize_entry_url

FEED = "https://hbr.org/feed"
WR_FEED = "https://www.foodnavigator.com/rss"


def test_host_undefined_is_rejected():
    """William Reed feeds splice a JS `undefined` where the path belongs; the
    host does not exist and the path is gone, so the link can never resolve."""
    for u in ("https://www.nutraingredients.comundefined?utm_source=RSS_Feed",
              "https://www.foodnavigator-usa.comundefined?utm_medium=RSS",
              "https://www.foodnavigator.comundefined"):
        assert normalize_entry_url(u, WR_FEED) is None


def test_undefined_in_path_is_kept():
    """Guard against over-eager filtering: these are working links where
    'undefined' is a real word in the slug. A substring filter would kill them."""
    keep = [
        "https://www.designboom.com/architecture/bus-architecture-undefined-playground-05-15-2016/",
        "https://www.designboom.com/design/george-duan-project-undefined-ceramic-cooking-system-02-28-2019/",
        "https://semiengineering.com/intermittent-undefined-state-fault-in-rrams/",
    ]
    for u in keep:
        assert normalize_entry_url(u, "https://www.designboom.com/feed/") == u


def test_site_relative_is_resolved():
    """HBR emits paths without a host — 20 published articles carried these."""
    got = normalize_entry_url("/2026/07/you-outsourced-the-ai-but-you-still-own-the-risk", FEED)
    assert got == "https://hbr.org/2026/07/you-outsourced-the-ai-but-you-still-own-the-risk"


def test_protocol_relative_is_resolved():
    assert normalize_entry_url("//example.com/a/b", FEED) == "https://example.com/a/b"


def test_host_only_is_rejected():
    """A homepage link is not a source reference — it points at unrelated
    content by the next poll."""
    assert normalize_entry_url("https://www.example.com", FEED) is None
    assert normalize_entry_url("https://www.example.com/", FEED) is None


def test_empty_and_junk():
    assert normalize_entry_url(None, FEED) is None
    assert normalize_entry_url("", FEED) is None
    assert normalize_entry_url("   ", FEED) is None
    assert normalize_entry_url("javascript:void(0)", FEED) is None


def test_normal_url_untouched():
    u = "https://www.fooddive.com/news/some-article/12345/"
    assert normalize_entry_url(u, "https://www.fooddive.com/feeds/news/") == u
