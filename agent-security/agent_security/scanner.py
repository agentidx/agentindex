"""Scan dependency files for AI agent trust scores."""

import json
import re
import urllib.request
import urllib.parse
from pathlib import Path

API_URL = "https://nerq.ai"


def parse_requirements(filepath):
    """Parse requirements.txt and return list of package names."""
    packages = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # Strip version specifiers
            name = re.split(r"[>=<!\[;]", line)[0].strip()
            if name:
                packages.append(name)
    return packages


def parse_package_json(filepath):
    """Parse package.json and return list of dependency names."""
    with open(filepath) as f:
        data = json.load(f)
    deps = list(data.get("dependencies", {}).keys())
    deps += list(data.get("devDependencies", {}).keys())
    return deps


def parse_pyproject(filepath):
    """Parse pyproject.toml for dependencies (basic parser)."""
    packages = []
    in_deps = False
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line.startswith("dependencies") and "=" in line:
                in_deps = True
                continue
            if in_deps:
                if line == "]":
                    in_deps = False
                    continue
                # Extract package name from "package>=1.0"
                match = re.match(r'"([a-zA-Z0-9_-]+)', line)
                if match:
                    packages.append(match.group(1))
    return packages


def detect_and_parse(filepath):
    """Auto-detect file type and parse dependencies."""
    p = Path(filepath)
    name = p.name.lower()

    if name == "requirements.txt" or name.endswith(".txt"):
        return parse_requirements(filepath)
    elif name == "package.json":
        return parse_package_json(filepath)
    elif name == "pyproject.toml":
        return parse_pyproject(filepath)
    else:
        # Try requirements.txt format as fallback
        return parse_requirements(filepath)


def check_trust(package_name, api_url=None):
    """Check trust score for a single package."""
    base = api_url or API_URL
    url = f"{base}/v1/preflight?target={urllib.parse.quote(package_name)}"
    try:
        data = json.loads(urllib.request.urlopen(url, timeout=15).read())
        return {
            "name": package_name,
            "trust_score": data.get("target_trust"),
            "grade": data.get("target_grade"),
            "recommendation": data.get("recommendation"),
            "cve_count": data.get("security", {}).get("cve_count", 0),
            "license": data.get("security", {}).get("license"),
            "alternatives": data.get("alternatives", []),
            "error": None,
        }
    except Exception as e:
        return {
            "name": package_name,
            "trust_score": None,
            "grade": None,
            "recommendation": None,
            "cve_count": 0,
            "license": None,
            "alternatives": [],
            "error": str(e),
        }


def scan_file(filepath, api_url=None):
    """Scan a dependency file and return trust results for all packages."""
    packages = detect_and_parse(filepath)
    results = []
    for pkg in packages:
        result = check_trust(pkg, api_url)
        results.append(result)
    return results
