#!/usr/bin/env bash
# Baut die Recherche-venv (gpt-researcher + MCP-SDK) ausserhalb der Worktrees.
# Bewusst NICHT .venv: die ist ein Symlink auf die venv von main und damit sofort
# fuer alle Crons live (Owner-Regel). Idempotent.
set -euo pipefail
VENV="${RESEARCH_VENV:-$HOME/venvs/catandary-research}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$(dirname "$VENV")"
if [ ! -x "$VENV/bin/python" ]; then
  uv venv --python 3.12 "$VENV"
fi
VIRTUAL_ENV="$VENV" uv pip install --python "$VENV/bin/python" -r "$REPO/requirements-research.txt"
"$VENV/bin/python" -c "import gpt_researcher, mcp; print('ok', gpt_researcher.__file__)"
