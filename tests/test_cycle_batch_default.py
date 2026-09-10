"""Der Cycle soll an einem normalen Tag in EINEM Lauf durchgehen
(Owner-Vorgabe 2026-09-10).

Mit dem alten Default 600 sprang run 2 an jedem Tag an (Cycle-Logs 02.–09.09.)
und kostete jedes Mal einen zweiten kompletten Stage-8-Pass — Reclassify läuft
über ALLE Drafts, ~28 min, für dasselbe Ergebnis.

Gemessener Anfall in die Pipeline: 1.509–1.619/Tag mit 474 Quellen, 3.565 am
10.09. mit 560 Quellen (davon ~1.107 Einmaleffekt der 53 erstmals ziehenden
Quellen). Stationär ~2.460 — 3000 deckt das mit gut 20 % Luft.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WRAPPER = Path(__file__).parent.parent / "scripts" / "full_cycle_cron.sh"
CRONTAB = Path(__file__).parent.parent / "deploy" / "crontab.txt"


@pytest.fixture(scope="module")
def wrapper() -> str:
    return WRAPPER.read_text()


class TestDefault:
    def test_default_is_three_thousand(self, wrapper):
        m = re.search(r'CYCLE_BATCH="\$\{CYCLE_BATCH:-(\d+)\}"', wrapper)
        assert m and m.group(1) == "3000", "Default deckt den gemessenen Tagesanfall nicht"

    def test_it_covers_the_measured_steady_state(self, wrapper):
        m = re.search(r'CYCLE_BATCH="\$\{CYCLE_BATCH:-(\d+)\}"', wrapper)
        assert int(m.group(1)) >= 2460, "unter dem gemessenen Anfall springt run 2 wieder an"

    def test_the_override_still_works(self, wrapper):
        """Eine einzelne Nacht muss weiter anhebbar sein (Crontab-Zeile)."""
        assert "${CYCLE_BATCH:-" in wrapper

    def test_the_reasoning_is_written_down(self, wrapper):
        assert "run 2" in wrapper and "Stage-8" in wrapper


class TestCrontabHasNoLeftoverOverride:
    def test_no_one_off_override_remains(self):
        """Der 5000er-Wert vom 10.09. war fuer EINE Nacht gedacht."""
        for text in (CRONTAB.read_text(),):
            line = next((l for l in text.splitlines()
                         if "full_cycle_cron.sh" in l and not l.strip().startswith("#")), "")
            assert "CYCLE_BATCH=" not in line, line
