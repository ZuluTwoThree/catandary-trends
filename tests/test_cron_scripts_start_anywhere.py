"""Die Python-Crons muessen aus JEDEM Arbeitsverzeichnis starten (#104 Stufe 2,
Vorfall 2026-09-12): die Crontab ruft backup_db.py ohne `cd` auf, und der
Laufprotokoll-Import `from pipeline.ops_events import record` warf einen
ModuleNotFoundError — das Backup der Nacht fiel aus. Seitdem: Repo-Root im
Pfad (backup_db) und der Import als Option (ImportError → nullcontext), denn
das Protokoll ist Beiwerk, der Job nicht.

Der Test startet jedes Skript mit --help aus einem fremden Verzeichnis, mit
einem leeren PYTHONPATH und OHNE Datenbank (DATABASE_URL leer, SQLite-Pfad in
tmp) — genau die Umgebung der Crontab, nur ohne Nebenwirkungen."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = ["backup_db", "purge_raw_content", "resolve_open_licence", "discovery_loop",
           "monthly_source_check", "check_source_links", "dossier_worker", "research_pulse"]


@pytest.mark.parametrize("name", SCRIPTS)
def test_script_help_works_from_a_foreign_cwd(name: str, tmp_path: Path):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)}
    env.update({"DATABASE_URL": "", "DATABASE_PATH": str(tmp_path / "t.db"), "OPS_EVENT_ID": ""})
    r = subprocess.run([sys.executable, str(REPO / "scripts" / f"{name}.py"), "--help"],
                       cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"{name}: rc={r.returncode}\n{r.stderr[-800:]}"
    assert "ModuleNotFoundError" not in r.stderr
