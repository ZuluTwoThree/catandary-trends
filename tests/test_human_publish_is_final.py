"""Ein Publish von Hand ist endgültig (Owner-Regel 2026-09-22).

Anlass: das Namens-Gate beanstandete „Per Second" — herausgeschnitten aus
„Tokens Per Second (TPS)", also gar kein Personenname. Der Owner las den
Artikel neben der Quelle und gab ihn frei. Kein automatischer Lauf darf diese
Entscheidung danach wieder einkassieren; `reviewed_at` ist die Marke dafür.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestRecheckSweep:
    def test_the_sweep_skips_rows_a_human_decided(self):
        from scripts.recheck_published_grounding import row_filter
        assert row_filter(False) == "AND t.reviewed_at IS NULL "
        assert row_filter(True) == ""      # nur mit --include-reviewed

    def test_the_update_carries_the_same_guard(self):
        """Zweiter Riegel: selbst ein Treffer aus einem älteren Lauf holt eine
        inzwischen von Hand entschiedene Zeile nicht zurück."""
        src = (ROOT / "scripts" / "recheck_published_grounding.py").read_text()
        i = src.index("UPDATE trends SET status = 'review'")
        upd = src[i:i + 300]
        assert "reviewed_at IS NULL" in upd


class TestOtherAutomaticPasses:
    def test_the_review_agent_only_looks_at_undecided_drafts(self):
        src = (ROOT / "pipeline" / "review_agent.py").read_text()
        sql = re.search(r"sql = \((.*?)\)\n", src, re.S).group(1)
        assert "status = 'draft'" in sql and "reviewed_at IS NULL" in sql

    def test_publishing_from_the_desk_stamps_the_decision(self):
        """publishReviewed und der Ein-Klick-Fix setzen reviewed_at — ohne die
        Marke griffe die Regel oben ins Leere."""
        src = (ROOT / "frontend" / "src" / "lib" / "review.ts").read_text()
        block = src[src.index("export async function publishReviewed"):]
        assert "reviewed_at = NOW()" in block[:600]
        fix = src[src.index("export async function applyBodyFix"):]
        assert "reviewed_at = NOW()" in fix[:2000]

    def test_auto_publish_never_sees_a_published_row(self):
        """Stage 9 nimmt nur Drafts — eine veröffentlichte Zeile ist außer Reichweite."""
        src = (ROOT / "pipeline" / "auto_publisher.py").read_text()
        assert "get_trends(status='draft'" in src.replace('"', "'")
