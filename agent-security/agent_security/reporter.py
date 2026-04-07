"""Format scan results for terminal output."""

import sys


def _color(text, code):
    """Apply ANSI color if stdout is a terminal."""
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def green(text): return _color(text, "32")
def yellow(text): return _color(text, "33")
def red(text): return _color(text, "31")
def bold(text): return _color(text, "1")
def dim(text): return _color(text, "2")


def format_scan_report(results, filepath):
    """Format scan results as a terminal report."""
    lines = []
    lines.append(f"\n{bold('agent-security')} scan: {filepath}")
    lines.append(f"Scanned {len(results)} dependencies\n")

    trusted = 0
    warnings = 0
    critical = 0
    not_found = 0

    for r in results:
        name = r["name"]
        trust = r["trust_score"]
        grade = r["grade"] or "?"
        rec = r["recommendation"] or "UNKNOWN"
        cves = r["cve_count"]
        lic = r["license"] or "unknown"
        error = r["error"]

        if error:
            not_found += 1
            lines.append(f"  {dim('?')}  {name}: {dim('not found in index')}")
            continue

        trust_str = f"{int(trust)}" if trust is not None else "?"
        cve_str = f", {cves} CVE(s)" if cves else ""
        lic_str = f", {lic}" if lic and lic != "unknown" else ""

        if rec == "ALLOW" or (trust is not None and trust >= 70):
            trusted += 1
            icon = green("OK")
            detail = f"Trust {trust_str} ({grade}){cve_str}{lic_str}"
            lines.append(f"  {icon}  {name}: {detail}")
        elif rec == "DENY" or (trust is not None and trust < 40):
            critical += 1
            icon = red("!!")
            detail = f"Trust {trust_str} ({grade}){cve_str}{lic_str}"
            lines.append(f"  {icon}  {red(name)}: {detail}")
        else:
            warnings += 1
            icon = yellow("!!")
            detail = f"Trust {trust_str} ({grade}){cve_str}{lic_str}"
            lines.append(f"  {icon}  {yellow(name)}: {detail}")

    lines.append("")
    summary_parts = []
    if trusted:
        summary_parts.append(green(f"{trusted} trusted"))
    if warnings:
        summary_parts.append(yellow(f"{warnings} warning(s)"))
    if critical:
        summary_parts.append(red(f"{critical} critical"))
    if not_found:
        summary_parts.append(dim(f"{not_found} not found"))
    lines.append(f"Summary: {', '.join(summary_parts)}")

    if critical > 0:
        lines.append(f"\nRun '{bold('agent-security fix ' + filepath)}' for improvement recommendations.")

    return "\n".join(lines)


def format_fix_report(results):
    """Format fix recommendations."""
    lines = []
    lines.append(f"\n{bold('agent-security')} fix recommendations:\n")

    problematic = [r for r in results if r["trust_score"] is not None and r["trust_score"] < 60]

    if not problematic:
        lines.append("  All dependencies look good. No fixes needed.")
        return "\n".join(lines)

    for r in problematic:
        trust = int(r["trust_score"]) if r["trust_score"] else "?"
        lines.append(f"  {bold(r['name'])} (Trust: {trust}):")

        if r["cve_count"]:
            lines.append(f"    -> {r['cve_count']} known CVE(s) — check for updates")

        alts = r.get("alternatives", [])
        if alts:
            alt = alts[0]
            alt_name = alt.get("name", "?")
            alt_trust = int(alt.get("trust_score", 0))
            lines.append(f"    -> Alternative: {green(alt_name)} (Trust: {alt_trust})")
        else:
            lines.append(f"    -> No direct alternative found. Review manually.")

        lines.append("")

    return "\n".join(lines)


def generate_badge_markdown(project_name="my-project"):
    """Generate Nerq trust badge markdown."""
    return f"[![Nerq Trust](https://nerq.ai/v1/badge/{project_name})](https://nerq.ai/safe/{project_name})"


def generate_github_action():
    """Generate GitHub Action YAML for trust checking."""
    return """name: Agent Security Check
on: [push, pull_request]

jobs:
  trust-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install agent-security
      - run: agent-security scan requirements.txt --ci
"""
