"""Der Mega-Vorschlagsraum darf nicht von Formularsätzen beherrscht werden
(#97, 2026-09-09).

Eingebettet wird `title + excerpt[:500]`. Bei Förderbescheiden ("X wins $600k
SBIR Phase II award", "HOLONIX SRL secures EUR 620k Horizon 2020 grant")
dominiert die SATZFORM das Thema — der Clusterer findet dann Vorlagen statt
Trends. Gemessen am 09.09.: 35.748 von 60.000 gezogenen Signalen waren
`source_type='api'`, und beide „NEW"-Vorschläge des Laufs waren reine
Förderbescheid-Cluster.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts import propose_mega_trends as pmt


class TestDefaultExclusion:
    def test_api_is_excluded_by_default(self):
        assert pmt.DEFAULT_EXCLUDE_SOURCE_TYPES == ("api",)

    def test_signature_carries_the_default(self):
        import inspect
        sig = inspect.signature(pmt.load_signals)
        assert sig.parameters["exclude_source_types"].default is pmt.DEFAULT_EXCLUDE_SOURCE_TYPES


class TestQueryShape:
    """Reines SQL-Argument-Prüfen — kein DB-Zugriff nötig."""

    def _capture(self, monkeypatch, **kw):
        seen = {}

        class _Cur:
            def fetchall(self):
                return []

        class _Conn:
            def execute(self, sql, params=None):
                seen["sql"], seen["params"] = sql, list(params or [])
                return _Cur()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        monkeypatch.setattr(pmt, "get_connection", lambda: _Conn())
        pmt.load_signals("signal", 10, **kw)
        return seen

    def test_default_run_filters_api_sources(self, monkeypatch):
        seen = self._capture(monkeypatch)
        assert "source_type IN" in seen["sql"]
        assert "api" in seen["params"]

    def test_empty_exclusion_leaves_the_pool_untouched(self, monkeypatch):
        seen = self._capture(monkeypatch, exclude_source_types=())
        assert "source_type IN" not in seen["sql"]
        assert "api" not in seen["params"]

    def test_several_types_can_be_excluded(self, monkeypatch):
        seen = self._capture(monkeypatch, exclude_source_types=("api", "radar"))
        assert seen["params"].count("api") == 1 and "radar" in seen["params"]

    def test_status_filter_still_applies(self, monkeypatch):
        seen = self._capture(monkeypatch)
        assert "t.status IN" in seen["sql"] and "signal" in seen["params"]
