"""Ein fehlgeschlagener Stage-Schritt ist kein sauberer Lauf.

Anlass 2026-09-23: Stage 11 (Review-Agent) stürzte in der ersten Zeile ab
(`NameError`), der Wrapper endete trotzdem mit rc=0, die Morgen-Mail sagte nur
beiläufig „agent: no fresh run" — und der Ausfall fiel erst auf, als der Owner
nachfragte. Der Wächter liest jetzt die Stage-Bilanz aus dem inneren Log.
"""
from __future__ import annotations

from datetime import date

import pytest

from scripts import cycle_watchdog as cw

CLEAN = "scheduled_cycle.sh end  2026-09-24T07:10:00+02:00  (rc1=0 rc2=0 rc3=0 agent=0)\n"
AGENT_BROKE = ("----- stage 11: review agent -----\nTraceback (most recent call last):\n"
               "NameError: name '_llama_unit_active' is not defined\n"
               "scheduled_cycle.sh end  2026-09-23T07:23:40+02:00  (rc1=0 rc2=0 rc3=0 agent=1)\n")
NOT_RUN = "scheduled_cycle.sh end  2026-09-24T07:10:00+02:00  (rc1=0 rc2=0 rc3=0 agent=-)\n"


@pytest.fixture
def logdir(tmp_path, monkeypatch):
    monkeypatch.setattr(cw, "LOG_DIR", tmp_path)
    return tmp_path


def _write(logdir, stamp: str, text: str):
    (logdir / f"catandary-scheduled-{stamp}-0245.log").write_text(text)


class TestInspectStages:
    def test_a_clean_stage_line_is_silence(self, logdir):
        _write(logdir, "20260924", CLEAN)
        v = cw.inspect_stages("20260924")
        assert v["ok"] and "clean" in v["headline"]

    def test_a_failed_stage_is_reported_by_name(self, logdir):
        _write(logdir, "20260923", AGENT_BROKE)
        v = cw.inspect_stages("20260923")
        assert not v["ok"]
        assert "review agent (stage 11) = 1" in v["headline"]
        assert "rc1=0 rc2=0 rc3=0 agent=1" in v["detail"]
        assert any("NameError" in ln for ln in v["tail"]), "der Fehler gehört in die Mail"

    def test_a_stage_that_did_not_run_is_not_a_failure(self, logdir):
        """agent=- heißt: die Stage war abgeschaltet oder übersprungen — das ist
        eine Entscheidung, kein Defekt."""
        _write(logdir, "20260924", NOT_RUN)
        assert cw.inspect_stages("20260924")["ok"]

    def test_other_stages_are_covered_too(self, logdir):
        _write(logdir, "20260924", "scheduled_cycle.sh end  x  (rc1=2 rc2=0 rc3=0 agent=0)\n")
        v = cw.inspect_stages("20260924")
        assert not v["ok"] and "LLM run 1 = 2" in v["headline"]

    def test_an_unfinished_run_is_left_to_the_cycle_check(self, logdir):
        _write(logdir, "20260924", "----- stage 6 progress -----\n")
        assert cw.inspect_stages("20260924")["ok"]

    def test_no_log_on_a_weekday_is_left_to_the_cycle_check(self, logdir, monkeypatch):
        assert cw.inspect_stages("20260924")["ok"]

    def test_the_watchdog_reports_it_alongside_the_other_checks(self, logdir, monkeypatch):
        """inspect_stages muss in der Problemliste von main() landen — sonst
        bleibt der Befund wieder in einer Logzeile stecken."""
        import inspect as _i
        src = _i.getsource(cw.main)
        assert "inspect_stages" in src and "stages_v" in src
        assert "problems = [v for v in (cycle_v, stages_v" in src
