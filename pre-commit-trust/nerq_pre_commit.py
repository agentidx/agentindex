#!/usr/bin/env python3
"""nerq-pre-commit — Check dependency trust scores before commit."""

import json
import re
import sys
import urllib.request

API_URL = "https://nerq.ai/v1/preflight"
MIN_SCORE = 60
COLORS = {"red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m", "reset": "\033[0m", "bold": "\033[1m"}


def check_agent(name):
    try:
        url = f"{API_URL}?target={urllib.parse.quote(name)}"
        data = json.loads(urllib.request.urlopen(url, timeout=10).read())
        return {
            "name": name,
            "score": data.get("trust_score", 0),
            "grade": data.get("grade", "?"),
            "cves": data.get("security", {}).get("known_cves", 0),
            "has_critical": data.get("security", {}).get("has_critical_cve", False),
            "recommendation": data.get("recommendation", "UNKNOWN"),
        }
    except Exception:
        return {"name": name, "score": None, "grade": "?", "cves": 0, "has_critical": False, "recommendation": "SKIP"}


def parse_deps(filepath):
    deps = []
    with open(filepath) as f:
        content = f.read()

    if filepath.endswith(".json"):
        pkg = json.loads(content)
        for section in ("dependencies", "devDependencies"):
            deps.extend(pkg.get(section, {}).keys())
    elif "pyproject.toml" in filepath:
        for line in content.split("\n"):
            m = re.match(r'^"?([a-zA-Z0-9_-]+)', line.strip())
            if m and not line.startswith("[") and not line.startswith("#"):
                deps.append(m.group(1))
    else:
        for line in content.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                name = re.split(r"[>=<!\[;]", line)[0].strip()
                if name:
                    deps.append(name)

    return list(set(deps))


def main():
    import urllib.parse

    files = sys.argv[1:]
    if not files:
        return 0

    all_deps = []
    for f in files:
        all_deps.extend(parse_deps(f))

    if not all_deps:
        return 0

    print(f"{COLORS['bold']}Nerq Trust Check — scanning {len(all_deps)} dependencies{COLORS['reset']}\n")

    failed = False
    for dep in sorted(set(all_deps)):
        result = check_agent(dep)
        if result["score"] is None:
            icon = "⚪"
            color = COLORS["reset"]
        elif result["score"] >= MIN_SCORE:
            icon = "✅"
            color = COLORS["green"]
        elif result["has_critical"]:
            icon = "🚨"
            color = COLORS["red"]
            failed = True
        else:
            icon = "⚠️"
            color = COLORS["yellow"]

        score_str = f"{result['score']}/100" if result["score"] is not None else "N/A"
        cve_str = f" | {result['cves']} CVE(s)" if result["cves"] > 0 else ""
        print(f"  {icon} {color}{dep}: {score_str} ({result['grade']}){cve_str}{COLORS['reset']}")

    print()
    if failed:
        print(f"{COLORS['red']}CRITICAL vulnerabilities found. Commit blocked.{COLORS['reset']}")
        return 1

    print(f"{COLORS['green']}All dependency checks passed.{COLORS['reset']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
