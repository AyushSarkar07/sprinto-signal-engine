#!/bin/sh
# Assemble sprinto-panel/: the public control panel for Vercel (public sandbox mode, see app.py).
# Vercel detects the Flask app in app.py. Includes code + a read-only snapshot of results. Never includes .env, credentials, caches or logs.
set -e
cd "$(dirname "$0")"
rm -rf sprinto-panel && mkdir -p sprinto-panel/snapshot
cp app.py config.py export_site.py main.py sprinto-panel/
cp -R src prompts data sprinto-panel/
for d in state review revenue company_reports; do [ -d "output/$d" ] && cp -R "output/$d" sprinto-panel/snapshot/; done
for f in decision_ledger.json pipeline_summary.csv pipeline_report.md; do [ -f "output/$f" ] && cp "output/$f" sprinto-panel/snapshot/; done
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
