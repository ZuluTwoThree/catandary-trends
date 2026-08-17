"""The watchdog that notices a cycle never finished.

Born from the 2026-08-17 power cut: the wrapper writes its exit code as its
last act, so a killed run leaves no line at all — and an absent line raised no
alarm. These tests pin the four verdicts and, just as importantly, the two ways
this watchdog could become useless: crying wolf at the weekend (it would be
filtered away by the time it mattered), or staying silent on a real abort.
"""
import importlib

import pytest


@pytest.fixture
def wd(tmp_path, monkeypatch):
    import scripts.cycle_watchdog as m
    m = importlib.reload(m)
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    # No cycle process alive unless a test says so.
    monkeypatch.setattr(m, "cycle_is_running", lambda: False)
    return m


def write_log(dirpath, stamp: str, body: str):
    p = dirpath / f"catandary-full-cycle-{stamp}-0400.log"
    p.write_text(body, encoding="utf-8")
    return p


START = "full_cycle_cron.sh start  2026-08-17T04:00:01+02:00\n"


class TestVerdicts:
    def test_clean_run_is_silent(self, wd, tmp_path):
        write_log(tmp_path, "20260817",
                  START + "full_cycle_cron.sh end  2026-08-17T06:52:46+02:00  (rc=0)\n")
        v = wd.inspect("20260817")
        assert v["ok"] is True and v["kind"] == "clean"

    def test_missing_end_line_is_an_abort(self, wd, tmp_path):
        """The exact 2026-08-17 signature: a start, then nothing."""
        write_log(tmp_path, "20260817", START + "----- launching scheduled_cycle -----\n")
        v = wd.inspect("20260817")
        assert v["ok"] is False and v["kind"] == "aborted"

    def test_nonzero_exit_code_is_reported(self, wd, tmp_path):
        write_log(tmp_path, "20260817",
                  START + "full_cycle_cron.sh end  2026-08-17T05:10:00+02:00  (rc=137)\n")
        v = wd.inspect("20260817")
        assert v["ok"] is False and v["kind"] == "failed"
        assert "137" in v["headline"]

    def test_a_slow_run_is_not_called_dead(self, wd, tmp_path, monkeypatch):
        """Still-running and cut-off both lack the end line, but they are
        different problems — reporting a slow run as an abort would send the
        owner to resume_cycle.sh while the cycle is still writing."""
        monkeypatch.setattr(wd, "cycle_is_running", lambda: True)
        write_log(tmp_path, "20260817", START)
        v = wd.inspect("20260817")
        assert v["kind"] == "running" and v["ok"] is False

    def test_no_log_on_a_weekday_is_an_alert(self, wd):
        v = wd.inspect("20260817")          # Monday, nothing written
        assert v["ok"] is False and v["kind"] == "missing"


class TestWeekend:
    """The cycle is Mon-Fri (crontab: 0 4 * * 1-5)."""

    @pytest.mark.parametrize("stamp,day", [("20260815", "Saturday"), ("20260816", "Sunday")])
    def test_missing_weekend_log_is_expected(self, wd, stamp, day):
        v = wd.inspect(stamp)
        assert v["ok"] is True, f"would raise a false alarm every {day}"
        assert v["kind"] == "weekend"

    def test_a_weekend_run_that_died_is_still_reported(self, wd, tmp_path):
        """The weekend rule excuses an ABSENT log, never a broken run — a
        manually started Saturday cycle that dies must still be flagged."""
        write_log(tmp_path, "20260815", START)
        v = wd.inspect("20260815")
        assert v["ok"] is False and v["kind"] == "aborted"


class TestMail:
    def test_alert_names_the_remedy_and_the_damage(self, wd, tmp_path, monkeypatch):
        monkeypatch.setattr(wd, "db_snapshot", lambda: ["created today: 858", "published: 0"])
        write_log(tmp_path, "20260817", START + "----- launching -----\n")
        subject, body_html, text = wd.build_mail(wd.inspect("20260817"), "20260817")
        assert "17.08.2026" in subject
        assert "resume_cycle.sh" in text          # what to do about it
        assert "created today: 858" in text       # what it cost
        assert "created today: 858" in body_html

    def test_unreachable_database_does_not_swallow_the_alert(self, wd, tmp_path, monkeypatch):
        """A database that is down is exactly when the alert matters most, so
        the snapshot degrades to a note instead of taking the mail with it."""
        import pipeline.db

        def boom(*a, **kw):
            raise RuntimeError("connection refused")
        monkeypatch.setattr(pipeline.db, "get_connection", boom)

        assert isinstance(wd.db_snapshot(), list)   # no raise

        write_log(tmp_path, "20260817", START + "----- launching -----\n")
        subject, body_html, text = wd.build_mail(wd.inspect("20260817"), "20260817")
        assert "stopped without finishing" in subject
        assert "unavailable" in text                # the gap is stated, not hidden
