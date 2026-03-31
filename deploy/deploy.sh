#!/bin/bash
# Catandary Trends – Deployment Script for Hetzner VPS
set -e

DEPLOY_DIR="/opt/catandary-trends"

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

# Restart services
echo "[4/5] Restarting services..."
pm2 restart ecosystem.config.js --update-env

# Create log directory
mkdir -p logs

echo "[5/5] Deployment complete!"
echo ""
echo "Status:"
pm2 status
echo ""
echo "Logs: pm2 logs catandary-trends"
