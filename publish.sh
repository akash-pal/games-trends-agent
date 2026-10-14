#!/usr/bin/env bash
# Weekly: run the pipeline locally (needs Ollama), then push site/ so Cloudflare Pages redeploys.
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] && source .venv/bin/activate
python run.py "$@"
git add site
if git diff --cached --quiet; then
  echo "Nothing new to publish."
else
  git commit -m "Trends for $(date -u +%Y-%m-%d)"
  git push
fi
