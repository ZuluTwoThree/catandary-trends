"""Tests for the Trend-Radar customer layer and briefing selection."""

import os
import tempfile

import pytest

# Override DB path before importing db modules
os.environ["DATABASE_PATH"] = os.path.join(tempfile.gettempdir(), "catandary_radar_test.db")

from pipeline import radar_db
from pipeline.briefing_generator import render_briefing_html, select_briefing_content
from pipeline.db import get_connection, init_db, insert_raw_entry, insert_trend, upsert_source

from datetime import datetime, timezone


@pytest.fixture(autouse=True)
def clean_db():
    init_db()
    radar_db.init_radar_schema()
    with get_connection() as conn:
        for table in ("radar_briefings", "radar_customers", "trends", "raw_entries", "sources"):
            conn.execute(f"DELETE FROM {table}")
    yield
    with get_connection() as conn:
        for table in ("radar_briefings", "radar_customers", "trends", "raw_entries", "sources"):
            conn.execute(f"DELETE FROM {table}")


def make_trend(slug: str, vertical: str = "TECH", title_de: str = "Testtrend",
               score: float = 0.8, status: str = "published",
               verticals: list[str] | None = None) -> int:
    sid = upsert_source("TestSource", "https://example.com/feed", "trade_media", vertical)
    eid = insert_raw_entry(sid, f"https://example.com/{slug}", title_de, "excerpt")
    trend_id = insert_trend(eid, {
        "title_en": f"EN {title_de}",
        "title_de": title_de,
        "slug": slug,
        "summary_en": "summary en",
        "summary_de": "Zusammenfassung de",
        "verticals": verticals or [vertical],
        "primary_vertical": vertical,
        "pestel": ["T"],
        "tags": ["test"],
        "trend_signal_type": "research",
        "trend_score": score,
        "confidence": 0.9,
        "source_url": f"https://example.com/{slug}",
        "source_name": "TestSource",
    })
    if status == "published":
        with get_connection() as conn:
            conn.execute(
                "UPDATE trends SET status='published', published_at=datetime('now') WHERE id=?",
                (trend_id,),
            )
    return trend_id


class TestCustomerCrud:
    def test_insert_and_get(self):
        c = radar_db.insert_customer("Acme", "a@acme.de", "solo", ["TECH"], keywords=["ki"])
        assert c["id"] > 0
        assert c["mrr_eur"] == 249
        assert len(c["token"]) >= 32
        fetched = radar_db.get_customer_by_token(c["token"])
        assert fetched["name"] == "Acme"
        assert fetched["verticals"] == ["TECH"]

    def test_tier_limits_enforced(self):
        with pytest.raises(ValueError, match="max 2 verticals"):
            radar_db.insert_customer("X", "x@x.de", "solo", ["TECH", "FOOD", "ECO"])
        with pytest.raises(ValueError, match="max 10 watchlist"):
            radar_db.insert_customer("X", "x@x.de", "solo", ["TECH"],
                                     keywords=[f"k{i}" for i in range(11)])
        with pytest.raises(ValueError, match="invalid verticals"):
            radar_db.insert_customer("X", "x@x.de", "pro", ["SPACE"])
        with pytest.raises(ValueError, match="at least one vertical"):
            radar_db.insert_customer("X", "x@x.de", "pro", [])

    def test_trial_has_zero_mrr_and_pro_limits(self):
        c = radar_db.insert_customer("T", "t@t.de", "trial",
                                     ["TECH", "FOOD", "HEALTH"], keywords=["a"] * 25)
        assert c["mrr_eur"] == 0

    def test_update_revalidates_limits(self):
        c = radar_db.insert_customer("Acme", "a@acme.de", "pro",
                                     ["TECH", "FOOD", "ECO"])
        with pytest.raises(ValueError, match="max 2 verticals"):
            radar_db.update_customer(c["id"], tier="solo")
        updated = radar_db.update_customer(c["id"], verticals=["TECH"], tier="solo")
        assert updated["tier"] == "solo"
        assert updated["mrr_eur"] == 249

    def test_update_rejects_unknown_fields(self):
        c = radar_db.insert_customer("Acme", "a@acme.de", "solo", ["TECH"])
        with pytest.raises(ValueError, match="unknown fields"):
            radar_db.update_customer(c["id"], evil="1")

    def test_agency_mandate_limit(self):
        agency = radar_db.insert_customer("Agentur", "a@ag.de", "agency", ["TECH"])
        for i in range(3):
            m = radar_db.insert_customer(f"Mandant {i}", f"m{i}@x.de", "pro",
                                         ["FOOD"], parent_id=agency["id"])
            assert m["mrr_eur"] == 0  # included in agency price
        with pytest.raises(ValueError, match="max 3 active mandates"):
            radar_db.insert_customer("Mandant 4", "m4@x.de", "pro", ["FOOD"],
                                     parent_id=agency["id"])

    def test_mandate_requires_agency_parent(self):
        solo = radar_db.insert_customer("Solo", "s@s.de", "solo", ["TECH"])
        with pytest.raises(ValueError, match="agency-tier"):
            radar_db.insert_customer("M", "m@m.de", "pro", ["FOOD"], parent_id=solo["id"])

    def test_token_rotation(self):
        c = radar_db.insert_customer("Acme", "a@acme.de", "solo", ["TECH"])
        new_token = radar_db.rotate_token(c["id"])
        assert new_token != c["token"]
        assert radar_db.get_customer_by_token(c["token"]) is None
        assert radar_db.get_customer_by_token(new_token)["id"] == c["id"]

    def test_mrr_summary(self):
        radar_db.insert_customer("A", "a@a.de", "solo", ["TECH"])
        radar_db.insert_customer("B", "b@b.de", "pro", ["TECH"])
        c = radar_db.insert_customer("C", "c@c.de", "agency", ["TECH"])
        radar_db.update_customer(c["id"], status="cancelled")
        summary = radar_db.get_mrr_summary()
        assert summary["total_mrr"] == 249 + 490
        assert summary["active_customers"] == 2


class TestTrendSelection:
    def test_top_trends_filters_vertical_and_status(self):
        make_trend("t1", "TECH", score=0.9)
        make_trend("t2", "FOOD", score=0.95)
        make_trend("t3", "TECH", score=0.5, status="draft")
        trends = radar_db.get_top_trends(["TECH"], since="2020-01-01")
        slugs = [t["slug"] for t in trends]
        assert slugs == ["t1"]

    def test_cross_vertical_trend_appears_for_secondary_vertical(self):
        make_trend("cross", "TECH", verticals=["TECH", "HEALTH"])
        trends = radar_db.get_top_trends(["HEALTH"], since="2020-01-01")
        assert [t["slug"] for t in trends] == ["cross"]

    def test_top_trends_ordering_and_exclude(self):
        t1 = make_trend("a", "TECH", score=0.6)
        make_trend("b", "TECH", score=0.9)
        trends = radar_db.get_top_trends(["TECH"], since="2020-01-01")
        assert [t["slug"] for t in trends] == ["b", "a"]
        trends = radar_db.get_top_trends(["TECH"], since="2020-01-01", exclude_ids=[t1])
        assert [t["slug"] for t in trends] == ["b"]

    def test_watchlist_like_fallback(self):
        # fresh test DB has no trends_fts table -> LIKE fallback path
        make_trend("q1", "TECH", title_de="Quantencomputer Durchbruch")
        make_trend("q2", "FOOD", title_de="Fermentation im Trend")
        hits = radar_db.search_watchlist(["Quantencomputer"], since="2020-01-01")
        assert "Quantencomputer" in hits
        assert hits["Quantencomputer"][0]["slug"] == "q1"
        assert radar_db.search_watchlist(["Blockchain"], since="2020-01-01") == {}


class TestBriefing:
    def _customer(self):
        return radar_db.insert_customer(
            "Acme", "a@acme.de", "pro", ["TECH"],
            keywords=["Quantencomputer"], contact_name="Dr. Test",
            brand_name="Acme Radar", brand_color="#123456",
        )

    def test_select_briefing_content_dedupes_watchlist(self):
        make_trend("q1", "TECH", title_de="Quantencomputer Durchbruch", score=0.9)
        make_trend("t2", "TECH", title_de="Anderes Signal", score=0.8)
        customer = self._customer()
        top, hits = select_briefing_content(customer, since="2020-01-01")
        assert [t["slug"] for t in hits["Quantencomputer"]] == ["q1"]
        # watchlist hit must not repeat in top trends
        assert "q1" not in [t["slug"] for t in top]
        assert "t2" in [t["slug"] for t in top]

    def test_render_briefing_html_white_label(self):
        make_trend("q1", "TECH", title_de="Quantencomputer Durchbruch")
        customer = self._customer()
        top, hits = select_briefing_content(customer, since="2020-01-01")
        subject, html = render_briefing_html(
            customer, top, hits, "2026-W24", datetime(2026, 6, 8, tzinfo=timezone.utc)
        )
        assert "Acme Radar" in subject
        assert "KW 24" in subject
        assert "#123456" in html
        assert "Quantencomputer Durchbruch" in html
        assert "Dr. Test" in html
        assert customer["token"] in html  # portal link
        assert "Originalquelle" in html

    def test_briefing_archive_upsert(self):
        customer = self._customer()
        b1 = radar_db.insert_briefing(customer["id"], "2026-W24", "s1", "<html>1</html>", [1], {})
        b2 = radar_db.insert_briefing(customer["id"], "2026-W24", "s2", "<html>2</html>", [1, 2], {"kw": [3]})
        briefings = radar_db.get_briefings(customer["id"])
        assert len(briefings) == 1
        assert briefings[0]["subject"] == "s2"
        assert radar_db.get_briefing(b2 or b1)["html"] == "<html>2</html>"

    def test_briefing_html_escapes_content(self):
        make_trend("x1", "TECH", title_de='<script>alert("x")</script>')
        customer = self._customer()
        top, hits = select_briefing_content(customer, since="2020-01-01")
        _, html = render_briefing_html(
            customer, top, hits, "2026-W24", datetime(2026, 6, 8, tzinfo=timezone.utc)
        )
        assert "<script>alert" not in html
