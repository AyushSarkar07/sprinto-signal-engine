#!/bin/sh
# Assemble sprinto-panel/: the whole public site for Vercel (public sandbox mode, see app.py):
# home at /, results dashboard at /dashboard, control panel at /app.
# Vercel detects the Flask app in app.py. Includes code + a read-only snapshot of results. Never includes .env, credentials, caches or logs.
set -e
cd "$(dirname "$0")"
rm -rf sprinto-panel && mkdir -p sprinto-panel/snapshot
cp app.py config.py export_site.py main.py sprinto-panel/
cp -R src prompts data sprinto-panel/
for d in state review revenue company_reports feedback; do [ -d "output/$d" ] && cp -R "output/$d" sprinto-panel/snapshot/; done
for f in decision_ledger.json pipeline_summary.csv pipeline_report.md runs.jsonl; do [ -f "output/$f" ] && cp "output/$f" sprinto-panel/snapshot/; done
# the results dashboard, served by app.py at /dashboard (the home page is drawn live by src/site_home.py)
mkdir -p sprinto-panel/site
cp sprinto-dashboard/index.html sprinto-panel/site/dashboard.html
find sprinto-panel -name "__pycache__" -type d -prune -exec rm -rf {} +
cat > sprinto-panel/requirements.txt <<'REQ'
requests>=2.31
beautifulsoup4>=4.12
anthropic>=0.70
pydantic>=2.6
python-dotenv>=1.0
tenacity>=8.2
flask>=3.0
REQ
cat > sprinto-panel/vercel.json <<'JSON'
{
  "functions": { "app.py": { "maxDuration": 300 } }
}
JSON
printf '.env\n.env.*\ncredentials/\n__pycache__/\n*.log\n' > sprinto-panel/.vercelignore
echo "sprinto-panel ready"
