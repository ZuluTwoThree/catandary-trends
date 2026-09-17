"""Per-host throttle overrides (2026-09-17).

Project Syndicate answered 37 of 52 article requests with 429 at the regular
1 request/s, so a host may carry its own spacing. The regular rate stays the
default for everyone else.
"""
from __future__ import annotations

import time

from pipeline import article_fetcher as af


def test_default_rate_for_unknown_host():
    assert af.host_delay("example.org") == af.PER_HOST_DELAY


def test_project_syndicate_is_slower_than_default():
    assert af.host_delay("www.project-syndicate.org") > af.PER_HOST_DELAY


def test_throttle_honours_host_override(monkeypatch):
    monkeypatch.setattr(af, "HOST_DELAYS", {"slow.example": 0.3})
    monkeypatch.setattr(af, "PER_HOST_DELAY", 0.0)
    monkeypatch.setattr(af, "_last_hit", {})
    af._throttle("slow.example")
    t0 = time.time()
    af._throttle("slow.example")
    assert time.time() - t0 >= 0.25
    t1 = time.time()
    af._throttle("fast.example")
    af._throttle("fast.example")
    assert time.time() - t1 < 0.2
