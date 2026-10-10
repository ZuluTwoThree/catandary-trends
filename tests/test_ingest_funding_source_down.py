"""Förder-Ingester: tote Quellen brechen ab statt Stunden zu kosten (Owner 2026-10-10)."""
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ingest_funding as f  # noqa: E402


class DeadClient:
    calls = 0

    def get(self, url, params=None, timeout=None):
        DeadClient.calls += 1
        raise httpx.ConnectTimeout("timed out")


class OkClient:
    def get(self, url, params=None, timeout=None):
        return httpx.Response(200, json={"results": []}, request=httpx.Request("GET", url))


def test_dead_host_raises_after_streak(monkeypatch):
    monkeypatch.setattr(f.time, "sleep", lambda s: None)
    monkeypatch.setattr(f, "_FAIL_STREAK", {})
    monkeypatch.setattr(f, "DEAD_AFTER", 5)
    DeadClient.calls = 0
    with pytest.raises(f.SourceDown):
        for _ in range(10):                       # mehrere Anfragen wie mehrere Suchbegriffe
            f._get_json(DeadClient(), "https://api.example.org/x", tries=6)
    assert DeadClient.calls == 5                  # nicht 10 × 6


def test_one_answer_resets_the_streak(monkeypatch):
    monkeypatch.setattr(f.time, "sleep", lambda s: None)
    monkeypatch.setattr(f, "_FAIL_STREAK", {"api.example.org": 4})
    monkeypatch.setattr(f, "DEAD_AFTER", 5)
    assert f._get_json(OkClient(), "https://api.example.org/x") == {"results": []}
    assert f._FAIL_STREAK["api.example.org"] == 0


def test_main_returns_3_and_keeps_other_backends(monkeypatch, capsys):
    ran = []

    def ok(since, limit, dry):
        ran.append("ok")
        return {"seen": 1, "inserted": 1, "duplicates": 0, "skipped": 0}

    def dead(since, limit, dry):
        raise f.SourceDown("api.openaire.eu: 8 network errors in a row")

    monkeypatch.setattr(f, "BACKENDS", {"nsf": ok, "openaire": dead, "nih": ok})
    monkeypatch.setattr(f, "DEFAULT_ALL", ["nsf", "openaire", "nih"])
    monkeypatch.setattr(sys, "argv", ["ingest_funding.py", "--backend", "all", "--dry-run"])
    assert f.main() == 3
    assert ran == ["ok", "ok"]
    assert "SOURCE DOWN: openaire" in capsys.readouterr().out
