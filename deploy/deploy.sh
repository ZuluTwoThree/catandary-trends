#!/bin/bash
# Catandary Trends – Deployment-Skript für die Next-App-Instanz (:3001), die als
# systemd user unit läuft (deploy/systemd/catandary-frontend.service; seit #38
# systemd statt PM2). Stand 2026-09-02: es gibt keinen VPS — dieses Skript
# aktualisiert die lokale Workstation-Instanz aus `main`. Die öffentliche Website
# wird per statischem Export aufs Hetzner-Webhosting publiziert
# (docs/launch/09_launch_plan_2026-09-02.md), nicht über dieses Skript.
set -e

# Muss zum WorkingDirectory der Unit passen (<DEPLOY_DIR>/frontend); per Env übersteuerbar.
DEPLOY_DIR="${DEPLOY_DIR:-/home/dirk/projects/catandary-trends}"

echo "=== Catandary Trends Deployment ==="

cd "$DEPLOY_DIR"

# Pull latest
echo "[1/5] Pulling latest changes..."
git pull origin main

# Python dependencies
echo "[2/5] Installing Python dependencies..."
source .venv/bin/activate
pip install -r requirements.txt --quiet

# Frontend build
echo "[3/5] Building frontend..."
cd frontend
npm ci --production=false
npx next build
cd ..

# Restart services (systemd user unit; Autostart via Linger)
echo "[4/5] Restarting services..."
systemctl --user restart catandary-frontend

# Create log directory
mkdir -p logs

echo "[5/5] Deployment complete!"
echo ""
echo "Status:"
systemctl --user status catandary-frontend --no-pager
echo ""
echo "Logs: journalctl --user -u catandary-frontend -f"
