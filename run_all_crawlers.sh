#!/bin/bash
# Universal Software Trust Crawler — Run all registries
# Usage: ./run_all_crawlers.sh [limit_per_registry]
# Default: 5000 packages per registry

cd ~/agentindex
source venv/bin/activate

LIMIT=${1:-5000}
echo "=== Universal Crawl — $LIMIT per registry ==="
echo "Started: $(date)"
echo ""

echo "$(date) | npm ($LIMIT packages)..."
python3 -m agentindex.crawlers.npm_crawler $LIMIT 2>&1 | tee logs/crawl_npm.log | tail -3
echo ""

echo "$(date) | PyPI ($LIMIT packages)..."
python3 -m agentindex.crawlers.pypi_crawler $LIMIT 2>&1 | tee logs/crawl_pypi.log | tail -3
echo ""

echo "$(date) | Crates.io ($LIMIT packages)..."
python3 -m agentindex.crawlers.crates_crawler $LIMIT 2>&1 | tee logs/crawl_crates.log | tail -3
echo ""

echo "$(date) | RubyGems ($LIMIT packages)..."
python3 -m agentindex.crawlers.rubygems_crawler $LIMIT 2>&1 | tee logs/crawl_gems.log | tail -3
echo ""

echo "$(date) | VS Code ($LIMIT extensions)..."
python3 -m agentindex.crawlers.vscode_crawler $LIMIT 2>&1 | tee logs/crawl_vscode.log | tail -3
echo ""

echo "$(date) | Packagist ($LIMIT packages)..."
python3 -m agentindex.crawlers.packagist_crawler $LIMIT 2>&1 | tee logs/crawl_packagist.log | tail -3
echo ""

echo "$(date) | NuGet ($LIMIT packages)..."
python3 -m agentindex.crawlers.nuget_crawler $LIMIT 2>&1 | tee logs/crawl_nuget.log | tail -3
echo ""

echo "$(date) | Go modules..."
python3 -m agentindex.crawlers.go_crawler 100 2>&1 | tee logs/crawl_go.log | tail -3
echo ""

echo "$(date) | Chrome extensions..."
python3 -m agentindex.crawlers.chrome_crawler 30 2>&1 | tee logs/crawl_chrome.log | tail -3
echo ""

echo "=== Results ==="
python3 -c "
import sys; sys.path.insert(0, '.')
from agentindex.db.models import get_session
from sqlalchemy import text
s = get_session()
rows = s.execute(text('SELECT registry, COUNT(*), ROUND(AVG(trust_score)::numeric, 1) FROM software_registry GROUP BY registry ORDER BY COUNT(*) DESC')).fetchall()
total = 0
for r in rows:
    print(f'  {r[0]:12s}: {r[1]:6d} packages (avg trust: {r[2]})')
    total += r[1]
print(f'  TOTAL:       {total:6d} packages')
s.close()
"

echo ""
echo "=== Submitting to IndexNow ==="
python3 agentindex/auto_indexnow.py 2>&1 | tail -5

echo ""
echo "Done: $(date)"
