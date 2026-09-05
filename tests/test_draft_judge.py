"""Release gates + judge plumbing (owner order 2026-08-22).

The Haiku backlog run proved judges approve past defects the gates catch
(297 grounding, 3 truncation of 7,798 approvals) — so the gates are the safety
property of every release path, backlog and nightly alike.
"""
import json

import pytest

from pipeline.draft_judge import release_gates, publish_draft, divert_garbled
from pipeline.db import get_connection, init_db, upsert_source

# Bodies must clear the garbage detector's 60-word floor (#11, 2026-09-05).
PAD = (" Analysts describe the change as gradual rather than abrupt, noting that "
       "procurement teams, lenders and regulators are each adjusting their own "
       "expectations at a different pace, so the overall picture remains mixed "
       "and any conclusion about the wider market should be read with care, "
       "since the underlying evidence is still being assembled and reviewed, "
       "and several of the firms involved have declined to comment so far.")


class TestReleaseGates:
    def test_grounded_complete_body_passes(self):
        ok, reason = release_gates(
            "T", "Revenue rose to $5 billion in 2026." + PAD, "Source title",
            "The company reported revenue of $5 billion for 2026.", None, None)
        assert ok, reason

    def test_garbled_body_is_blocked(self):
        """The 2026-09-05 soup: the judge would call it broken_text, the gate
        must stop it regardless of what the judge says."""
        ok, reason = release_gates(
            "T", ": writing writing市/address : writing M M M M M       仪器(",
            "S", "Slow breathing raises heart-rate variability.", None, None)
        assert not ok and reason.startswith("garbled:")

    def test_cjk_leak_is_blocked_against_the_source(self):
        body = ("The extension of the race through the decade represents more than a "
                "simple续约; it marks a strategic pivot in how sports rights are sold." + PAD)
        ok, reason = release_gates("T", body, "S", "The race was extended.", None, None)
        assert not ok and "script_leak" in reason

    def test_truncated_body_is_blocked(self):
        # long enough to pass the garbage floor, but cut off mid-sentence
        ok, reason = release_gates("T", "Revenue rose" + PAD.rstrip("."), "S", "src", None, None)
        assert not ok and reason == "truncated"

    def test_empty_body_is_blocked(self):
        ok, reason = release_gates("T", "  ", "S", "src", None, None)
        assert not ok and reason == "empty_body"

    def test_fabricated_figure_is_blocked(self):
        """The judge may have approved it — the gate must still stop it."""
        ok, reason = release_gates(
            "T", "The market grew by 47% last year." + PAD, "S",
            "The market grew strongly last year.", None, None)
        assert not ok and reason.startswith("ungrounded")

    def test_invented_first_name_is_blocked(self):
        ok, reason = release_gates(
            "T", "Henkel CEO Markus Knobel said margins improved." + PAD, "Henkel",
            "Henkel-Chef Knobel: Margen verbessert.", None, None)
        assert not ok and reason == "ungrounded_name:Markus Knobel"

    def test_extraction_evidence_grounds_the_body(self):
        """Figures the extraction captured count as source material — same
        assembly as the auto-publish gate (source_from_parts)."""
        ext = json.dumps({"key_figures": ["47%"]})
        ok, reason = release_gates(
            "T", "The market grew by 47% last year." + PAD, "S",
            "The market grew strongly.", None, ext)
        assert ok, reason


class TestPublishDraft:
    @pytest.fixture(autouse=True)
    def _cleanup(self):
        """Other suites' fixtures delete raw_entries/sources but not trends —
        a leftover trends row of ours would fail their DELETE on the foreign
        key. Leave the shared SQLite test DB exactly as found."""
        yield
        with get_connection() as conn:
            conn.execute("DELETE FROM trends WHERE slug LIKE 'judge-%'")
            conn.execute("DELETE FROM raw_entries WHERE url LIKE 'https://example.com/j/%'")
            conn.execute("DELETE FROM sources WHERE feed_url = 'https://example.com/judge'")

    def _mk(self, status="draft"):
        init_db()
        sid = upsert_source("judge-test", "https://example.com/judge", "api", "BIZ")
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO raw_entries (source_id, url, title) VALUES (?, ?, ?)",
                (sid, f"https://example.com/j/{status}", "T"))
            row = conn.execute(
                "SELECT id FROM raw_entries WHERE url = ?",
                (f"https://example.com/j/{status}",)).fetchone()
            rid = row["id"] if hasattr(row, "keys") else row[0]
            conn.execute(
                "INSERT INTO trends (raw_entry_id, title_en, slug, source_url, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (rid, "T", f"judge-{status}", "https://example.com", status))
            row = conn.execute("SELECT id FROM trends WHERE slug = ?",
                               (f"judge-{status}",)).fetchone()
            return row["id"] if hasattr(row, "keys") else row[0]

    def test_release_is_guarded_on_draft_status(self):
        tid = self._mk("rejected")
        with get_connection() as conn:
            assert publish_draft(conn, tid, auto=True) is False

    def test_garbled_candidate_is_diverted_to_review_with_reason(self):
        """#11 (2026-09-05): soup never reaches the judge; it is parked in
        status 'review' with its reasons and stamped judged (not re-judged)."""
        tid = self._mk("draft")
        with get_connection() as conn:
            divert_garbled(conn, tid, ["non_latin_script:5.4%", "too_short:10w"])
            row = dict(conn.execute(
                "SELECT status, review_reason, judged_at FROM trends WHERE id = ?",
                (tid,)).fetchone())
        assert row["status"] == "review"
        assert row["review_reason"] == "garbled:non_latin_script:5.4%,too_short:10w"
        assert row["judged_at"] is not None

    def test_release_marks_review_time_and_auto_flag(self):
        tid = self._mk("draft")
        with get_connection() as conn:
            assert publish_draft(conn, tid, auto=True) is True
            row = dict(conn.execute(
                "SELECT status, auto_published, reviewed_at, published_at "
                "  FROM trends WHERE id = ?", (tid,)).fetchone())
        assert row["status"] == "published"
        assert row["reviewed_at"] is not None and row["published_at"] is not None


class TestJudgedAtStamp:
    """Every verdicted draft is stamped once (2026-08-25): without the stamp
    the judge re-judged the same held cohort nightly (oldest ids first) and
    fresh drafts never reached the 600-slot window."""

    @pytest.fixture(autouse=True)
    def _cleanup(self):
        yield
        with get_connection() as conn:
            conn.execute("DELETE FROM trends WHERE slug LIKE 'judge-%'")
            conn.execute("DELETE FROM raw_entries WHERE url LIKE 'https://example.com/j/%'")
            conn.execute("DELETE FROM sources WHERE feed_url = 'https://example.com/judge'")

    def _mk_draft(self):
        init_db()
        sid = upsert_source("judge-test", "https://example.com/judge", "api", "BIZ")
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO raw_entries (source_id, url, title) VALUES (?, ?, ?)",
                (sid, "https://example.com/j/stamp", "T"))
            rid = conn.execute("SELECT id FROM raw_entries WHERE url = ?",
                               ("https://example.com/j/stamp",)).fetchone()[0]
            conn.execute(
                "INSERT INTO trends (raw_entry_id, title_en, slug, source_url, status) "
                "VALUES (?, ?, ?, ?, 'draft')", (rid, "T", "judge-stamp", "https://example.com"))
            return conn.execute("SELECT id FROM trends WHERE slug = 'judge-stamp'").fetchone()[0]

    def _judged_at(self, tid):
        with get_connection() as conn:
            return conn.execute("SELECT judged_at FROM trends WHERE id = ?", (tid,)).fetchone()[0]

    def test_held_verdict_stamps_but_dry_run_does_not(self, tmp_path, monkeypatch):
        import pipeline.draft_judge as dj
        tid = self._mk_draft()
        cand = {"id": tid, "title_en": "T", "body_en": "A real body." + PAD, "confidence": 0.5,
                "source_name": "judge-test", "re_id": None, "re_url": None,
                "re_title": "T", "raw_content": "src", "excerpt": "src",
                "extraction_json": None}
        monkeypatch.setattr(dj, "STATS_PATH", tmp_path / "stats.json")
        monkeypatch.setattr(dj, "_fetch_candidates", lambda h, l: [dict(cand)])
        monkeypatch.setattr(dj, "judge_one", lambda d: dj.JudgeVerdict(
            publish=False, signal=False, category="no_signal", note=""))

        stats = dj.judge_recent_drafts(dry_run=True)
        assert stats["held"] == 1 and self._judged_at(tid) is None

        stats = dj.judge_recent_drafts(dry_run=False)
        assert stats["held"] == 1 and self._judged_at(tid) is not None

    def test_error_leaves_draft_unstamped_for_retry(self, tmp_path, monkeypatch):
        import pipeline.draft_judge as dj
        tid = self._mk_draft()
        cand = {"id": tid, "title_en": "T", "body_en": "A real body." + PAD, "confidence": 0.5,
                "source_name": "judge-test", "re_id": None, "re_url": None,
                "re_title": "T", "raw_content": "src", "excerpt": "src",
                "extraction_json": None}
        monkeypatch.setattr(dj, "STATS_PATH", tmp_path / "stats.json")
        monkeypatch.setattr(dj, "_fetch_candidates", lambda h, l: [dict(cand)])
        monkeypatch.setattr(dj, "judge_one", lambda d: None)
        stats = dj.judge_recent_drafts(dry_run=False)
        assert stats["errors"] == 1 and self._judged_at(tid) is None


class TestMailFreshness:
    def test_stale_or_dry_run_stats_are_ignored(self, tmp_path, monkeypatch):
        """A judge that did not run tonight must not appear in the mail as if
        it had — dry_run files and stale files both gate to None."""
        import scripts.review_notify as rn
        f = tmp_path / "draft_judge_last.json"
        monkeypatch.setattr(rn, "Path", lambda _: f)
        f.write_text(json.dumps({"date": "2026-08-22T02:00:00+00:00",
                                 "released": 5, "dry_run": True}))
        assert rn.judge_stats() is None
        f.write_text(json.dumps({"date": "2020-01-01T02:00:00+00:00",
                                 "released": 5}))
        assert rn.judge_stats() is None
