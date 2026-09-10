"""Aufbewahrungsfrist für geholten Volltext (Owner-Entscheidung 2026-09-10).

§44b Abs. 2 S. 2 UrhG: „Die Vervielfältigungen sind zu löschen, sobald sie für
das Text und Data Mining nicht mehr erforderlich sind." Die Norm nennt **keine
Frist**, sie bindet sie an den Zweck. Dokumentierter Zweck ist seit dem
10.09.2026 die längsschnittliche Trendanalyse (Lead-Time Forschung → Patent →
Funding → Markt läuft über Jahre) — daher 60 Monate statt 14 Tage.

Der Wächter hält dreierlei fest: die Frist ist endlich (keine Abschaltung), sie
ist im Code begründet, und Cron und Skript sagen dasselbe.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import purge_raw_content as prc

ROOT = Path(__file__).parent.parent


class TestWindow:
    def test_sixty_months(self):
        assert prc.DEFAULT_DAYS == 1825

    def test_the_window_is_finite(self):
        """Kein 0 und kein None — die Löschpflicht bleibt bestehen."""
        assert isinstance(prc.DEFAULT_DAYS, int) and prc.DEFAULT_DAYS > 0

    def test_the_purpose_is_written_down(self):
        doc = prc.__doc__ or ""
        assert "44b" in doc
        assert "Trendanalyse" in doc, "der TDM-Zweck muss im Modulkopf stehen"

    def test_reserved_sources_stay_excluded_in_the_docstring(self):
        assert "TDM-Vorbehalt" in (prc.__doc__ or "")


class TestCronAgrees:
    def _cron(self) -> str:
        return (ROOT / "deploy" / "crontab.txt").read_text()

    def test_cron_uses_the_same_window(self):
        line = next(l for l in self._cron().splitlines()
                    if "purge_raw_content.py" in l and not l.strip().startswith("#"))
        assert "--days 1825" in line, line

    def test_cron_still_applies(self):
        line = next(l for l in self._cron().splitlines()
                    if "purge_raw_content.py" in l and not l.strip().startswith("#"))
        assert "--apply" in line, "ohne --apply löscht der Cron nichts"

    def test_no_stale_fourteen_day_mentions(self):
        """Doku-Drift: die alte Frist darf nirgends mehr als geltend dastehen."""
        for name in ("CLAUDE.md", "deploy/crontab.txt", "docs/owner_manual.md"):
            text = (ROOT / name).read_text()
            assert not re.search(r"--days 14\b", text), f"{name} nennt noch die alte Frist"
