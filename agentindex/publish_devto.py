#!/usr/bin/env python3
"""Publish a markdown article with YAML frontmatter to Dev.to."""
import json
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("requests not installed")
    sys.exit(1)

DEVTO_KEY_PATH = Path.home() / ".config" / "nerq" / "devto_api_key"


def parse_frontmatter(text):
    """Extract YAML-ish frontmatter and body from markdown."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if v.startswith("[") and v.endswith("]"):
                v = [t.strip().strip('"').strip("'") for t in v[1:-1].split(",")]
            elif v.lower() == "true":
                v = True
            elif v.lower() == "false":
                v = False
            meta[k] = v
    return meta, m.group(2).strip()


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m agentindex.publish_devto <markdown-file>")
        sys.exit(1)

    filepath = Path(sys.argv[1])
    if not filepath.exists():
        print(f"File not found: {filepath}")
        sys.exit(1)

    if not DEVTO_KEY_PATH.exists():
        print("No Dev.to API key at ~/.config/nerq/devto_api_key")
        sys.exit(1)

    api_key = DEVTO_KEY_PATH.read_text().strip()
    text = filepath.read_text()
    meta, body = parse_frontmatter(text)

    title = meta.get("title", filepath.stem.replace("-", " ").title())
    tags = meta.get("tags", ["ai", "security"])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    payload = {
        "article": {
            "title": title,
            "body_markdown": body,
            "published": True,
            "tags": tags[:4],
        }
    }

    print(f"Publishing: {title}")
    print(f"Tags: {tags[:4]}")

    try:
        resp = requests.post(
            "https://dev.to/api/articles",
            json=payload,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            timeout=30,
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code in (200, 201):
            data = resp.json()
            print(f"Published: {data.get('url', 'N/A')}")
        else:
            print(f"Error: {resp.text[:500]}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
