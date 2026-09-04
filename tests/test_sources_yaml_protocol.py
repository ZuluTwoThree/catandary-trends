"""The real sources.yaml after the #97 protocol-field seeding (2026-09-04):
still loads through pipeline.config.load_sources, every active RSS source
carries tdm_checked/tdm_status with valid values, the loaders/pollers that
read it ignore the new fields, and the compliance invariants hold."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pipeline.config import load_sources, source_relevance_min   # noqa: E402
from pipeline.article_fetcher import fulltext_source_names        # noqa: E402
from probe_source_compliance import iter_active_sources           # noqa: E402
from source_quality_report import iter_configured_feeds           # noqa: E402

STATUSES = {"ok", "reserved", "blocked", "feed_error"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _all_rss_entries(cfg: dict) -> list[dict]:
    out = []
    for _v, groups in (cfg.get("verticals") or {}).items():
        for key in ("sources", "science"):
            out += [s for s in groups.get(key) or [] if isinstance(s, dict)]
    for _g, entries in (cfg.get("cross_industry") or {}).items():
        out += [s for s in entries or [] if isinstance(s, dict)]
    return out


def test_sources_yaml_loads_and_every_active_source_is_stamped():
    cfg = load_sources()
    entries = _all_rss_entries(cfg)
    assert len(entries) > 200
    for s in entries:
        assert s.get("name") and s.get("feed_url"), s
        if s.get("active") is False:
            continue
        assert DATE.match(str(s.get("tdm_checked", ""))), f"{s['name']}: tdm_checked missing/invalid"
        assert s.get("tdm_status") in STATUSES, f"{s['name']}: tdm_status {s.get('tdm_status')!r}"


def test_fulltext_never_on_a_reserved_source():
    """A machine-readable TDM reservation takes §44b away — no stored full text."""
    for s in _all_rss_entries(load_sources()):
        if s.get("active") is False:
            continue
        if s.get("tdm_status") == "reserved":
            assert not s.get("fulltext"), f"{s['name']} is reserved but fulltext: true"


def test_existing_loaders_ignore_the_protocol_fields():
    cfg = load_sources()
    feeds = iter_configured_feeds()
    assert len(feeds) == len(_all_rss_entries(cfg))
    assert all(set(f) == {"name", "feed_url", "vertical", "type", "lead_time_tier"} for f in feeds)
    assert isinstance(source_relevance_min(), dict)
    assert fulltext_source_names() <= {s["name"] for s in _all_rss_entries(cfg)}
    active = iter_active_sources(cfg)
    assert all(e["prev_status"] in STATUSES for e in active)
