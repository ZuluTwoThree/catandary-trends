"""Der tägliche Volltext-Vektor-Lauf ist der niederrangigste GPU-Job
(Owner-Frage 2026-09-11: warum nicht gleich 30.000?).

Die Antwort war: weil er als einziger GPU-Job **keinen Kollisionswächter**
hatte. Montags um 09:00 startet gleichzeitig `weekly_newsletter_publish.sh`,
und der Full Cycle kann an langen Nächten noch laufen. Bei 5.000 sind das
13 Minuten, bei 30.000 wären es 76 — und das Wartebudget des Newsletters liegt
bei 90. Mit Wächter davor ist die höhere Grenze unproblematisch.
"""
from __future__ import annotations

from pathlib import Path

import pytest

WRAPPER = Path(__file__).parent.parent / "scripts" / "embed_full_text_cron.sh"
CRONTAB = Path(__file__).parent.parent / "deploy" / "crontab.txt"


@pytest.fixture(scope="module")
def sh() -> str:
    return WRAPPER.read_text()


class TestGuard:
    def test_the_collision_guard_is_sourced(self, sh):
        assert "gpu_guard.sh" in sh and "gpu_guard_wait embed_full_text" in sh

    def test_a_blocked_run_skips_instead_of_forcing(self, sh):
        assert "exit 75" in sh, "bei belegter GPU aussteigen, nicht draengeln"

    def test_the_guard_is_skipped_when_the_remote_gpu_is_used(self, sh):
        """Läuft es auf bequiet, wird die lokale Karte gar nicht angefasst —
        warten wäre dann sinnlose Verzögerung."""
        assert "remote_gpu.available()" in sh
        assert "lokale Karte bleibt unberuehrt" in sh


class TestLimit:
    def test_default_covers_the_saturday_spike(self, sh):
        assert "EMBED_LIMIT:-30000" in sh, "muss den Samstag (~30.000) in einem Lauf schaffen"

    def test_the_limit_is_overridable(self, sh):
        assert "${EMBED_LIMIT:-" in sh


class TestCrontab:
    def test_cron_calls_the_guarded_wrapper(self):
        line = next(l for l in CRONTAB.read_text().splitlines()
                    if "embed_full_text" in l and not l.strip().startswith("#"))
        assert "embed_full_text_cron.sh" in line, line
        assert "embed_full_text_gpu.py" not in line, "der ungeschuetzte Direktaufruf ist raus"
