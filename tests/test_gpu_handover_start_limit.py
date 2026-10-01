"""A deliberate llama-server start clears systemd's start limit first (01.10.2026).

The unit allows 4 starts in 15 minutes against crash loops; a short run 2 with four
planned model swaps hit it, the fifth start was refused and the draft judge was skipped.
Every deliberate start therefore runs `reset-failed` immediately before `start`."""
from pipeline import gpu_handover as G


def test_unit_start_resets_the_start_limit_before_starting(monkeypatch):
    calls = []
    monkeypatch.setattr(G, "_run", lambda cmd, timeout=0: calls.append(cmd))
    G.unit_start()
    assert calls == [["systemctl", "--user", "reset-failed", G.LLAMA_UNIT],
                     ["systemctl", "--user", "start", G.LLAMA_UNIT]]


def test_the_cron_scripts_reset_before_every_start():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "scripts"
    for name in ("scheduled_cycle.sh", "weekly_ingesters.sh", "weekly_newsletter_publish.sh",
                 "resume_cycle.sh"):
        lines = (root / name).read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith("systemctl --user start llama-server.service"):
                assert "reset-failed llama-server.service" in lines[i - 1], (name, i + 1)
