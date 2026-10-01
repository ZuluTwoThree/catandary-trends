"""pipeline/thin_sources.py — a thin source is retired after three too-short nights."""
from datetime import date

from pipeline import thin_sources as T

SHORT = "GeneratedContent: all 3 attempts on gemma.gguf produced garbage (too_short:49w) — nothing stored"
SOUP = "GeneratedContent: all 3 attempts on gemma.gguf produced garbage (non_latin:3.1%, too_short:20w) — nothing stored"


def test_only_pure_too_short_counts():
    assert T.only_too_short(SHORT)
    assert not T.only_too_short(SOUP)
    assert not T.only_too_short("something else entirely")


def test_third_distinct_night_retires_the_entry(tmp_path):
    f = tmp_path / "s.json"
    assert not T.note_too_short(7, SHORT, date(2026, 10, 1), f)
    assert not T.note_too_short(7, SHORT, date(2026, 10, 1), f)      # same night again
    assert not T.note_too_short(7, SHORT, date(2026, 10, 2), f)
    assert T.note_too_short(7, SHORT, date(2026, 10, 3), f)
    assert "7" not in T._load(f)                                    # state cleaned up


def test_token_soup_is_never_counted(tmp_path):
    f = tmp_path / "s.json"
    for d in range(1, 6):
        assert not T.note_too_short(8, SOUP, date(2026, 10, d), f)
    assert T._load(f) == {}
