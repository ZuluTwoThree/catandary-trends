"""/trends/ops/prompts liest den Katalog live aus dem Code — jeder Eintrag muss
laden, auf eine echte Datei zeigen und einen nicht-leeren Prompt tragen."""
import json
import subprocess
import sys
from pathlib import Path

from pipeline import prompt_catalog as pc

ROOT = Path(__file__).resolve().parent.parent


def test_every_entry_loads_and_points_at_source():
    entries = pc.build_catalog()
    assert len(entries) >= 14
    keys = [e.key for e in entries]
    assert len(keys) == len(set(keys))
    known_groups = {k for k, _t in pc.GROUPS}
    for e in entries:
        assert not e.error, f"{e.key}: {e.error}"
        assert e.group in known_groups, e.key
        assert len(e.system.strip()) > 100, e.key
        assert e.function and e.model and e.trigger, e.key
        assert e.file and (ROOT / e.file).exists(), f"{e.key}: {e.file}"
        assert e.line > 0, e.key


def test_json_cli_roundtrip():
    out = subprocess.run([sys.executable, "-m", "pipeline.prompt_catalog", "--json"],
                         cwd=ROOT, capture_output=True, text=True, timeout=120, check=True).stdout
    data = json.loads(out)
    assert {g["key"] for g in data["groups"]} >= {"feed", "newsletter", "ondemand"}
    assert "dossier" not in {g["key"] for g in data["groups"]}   # entfernt 2026-09-19
    assert any(e["key"] == "stage6-content" and e["user_template_kind"] == "source" for e in data["entries"])
