"""Unit tests for the source-router press-host guard (#4). Pure — no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.probe_source_apis import is_press_host, is_academic_src


def test_press_host_matched_by_substring():
    assert is_press_host("theconversation.com")
    assert is_press_host("www.sciencedaily.com")
    assert not is_press_host("nature.com")


def test_press_host_never_academic_even_when_tagged_science():
    # ScienceDaily / The Conversation tagged research must NOT route to ACADEMIC
    # (OpenAlex has no journal for them → 0 works). Fall through to WP/OTHER.
    src = {"type": "research", "group": "science"}
    assert is_academic_src(src, "sciencedaily.com") is False
    assert is_academic_src(src, "theconversation.com") is False


def test_real_journal_still_academic():
    assert is_academic_src({"type": "research"}, "nature.com") is True
    assert is_academic_src({"group": "science"}, "thelancet.com") is True
    assert is_academic_src({"type": "science"}, "example-unknown.org") is True


def test_plain_press_is_not_academic():
    assert is_academic_src({"type": "trade_media"}, "fooddive.com") is False
