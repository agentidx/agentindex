#!/bin/bash
# Prepare template repos for GitHub push
# Usage: bash scripts/prepare_templates.sh

set -e

TEMPLATES_DIR="$(dirname "$0")/../templates"
ORG="agentic-index"

for template in langchain-agent-template crewai-agent-template mcp-server-template autogen-agent-template; do
    dir="$TEMPLATES_DIR/$template"
    if [ ! -d "$dir" ]; then
        echo "Skipping $template — directory not found"
        continue
    fi

    echo "Preparing $template..."

    cd "$dir"

    # Init git if needed
    if [ ! -d .git ]; then
        git init -b main
    fi

    # Add all files
    git add -A
    git commit -m "Initial template with Nerq trust verification" 2>/dev/null || true

    echo "  Ready: $dir"
    echo "  Push:  gh repo create $ORG/$template --public --source=. --push"
    echo ""
done

echo "All templates prepared."
echo ""
echo "To push all:"
echo "  for t in langchain-agent-template crewai-agent-template mcp-server-template autogen-agent-template; do"
echo "    cd $TEMPLATES_DIR/\$t && gh repo create $ORG/\$t --public --source=. --push"
echo "  done"
