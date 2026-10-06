#!/usr/bin/env bash
# Startet den MCP-Server catandary-corpus aus der Recherche-venv: stdio (Claude Code, .mcp.json)
# oder mit --http [--port N] als Streamable HTTP auf 127.0.0.1 für Open WebUI (Bearer-Token).
# Aufbau der venv: scripts/setup_research_venv.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
exec "${RESEARCH_VENV:-$HOME/venvs/catandary-research}/bin/python" tools/research/mcp_server.py "$@"
