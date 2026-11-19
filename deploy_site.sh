#!/bin/sh
# Publish the whole site (landing /, results /dashboard, control panel /app) in one go.
# Run from anywhere: ./deploy_site.sh
set -e
cd "$(dirname "$0")"
.venv/bin/python export_site.py
./build_panel_deploy.sh
cd sprinto-panel
vercel deploy --prod --yes
vercel alias set sprinto-panel.vercel.app sprinto-signal-engine.vercel.app
echo "Live: https://sprinto-signal-engine.vercel.app"
