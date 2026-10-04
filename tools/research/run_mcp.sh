#!/usr/bin/env bash
# Startet den MCP-Server catandary-corpus (stdio) aus der Recherche-venv.
# Aufbau der venv: scripts/setup_research_venv.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
exec "${RESEARCH_VENV:-$HOME/venvs/catandary-research}/bin/python" tools/research/mcp_server.py
