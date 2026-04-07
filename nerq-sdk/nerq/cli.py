"""
nerq CLI — Trust verification from the command line.

Usage:
    nerq scan              Scan project dependencies
    nerq savings           Find cheaper LLM alternatives
    nerq check <package>   Check single package trust score
"""

import sys
import json
from urllib.request import Request, urlopen
from urllib.error import URLError

USER_AGENT = "NerqCLI/1.2.0"
API_BASE = "https://nerq.ai"


def cmd_check(args):
    """Check trust score for a single package."""
    if not args:
        print("Usage: nerq check <package-name>")
        print("Example: nerq check langchain")
        return 1

    target = args[0]
    print(f"\033[1mChecking trust score for: {target}\033[0m")
    print()

    try:
        req = Request(
            f"{API_BASE}/v1/preflight?target={target}",
            headers={"User-Agent": USER_AGENT},
        )
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read())
    except URLError as e:
        print(f"  Error: Could not reach nerq.ai — {e}")
        return 1
    except json.JSONDecodeError:
        print("  Error: Invalid response from API")
        return 1

    score = data.get("trust_score") or data.get("target_trust")
    grade = data.get("grade", "—")
    name = data.get("name") or data.get("target", target)

    if score is not None:
        # Color grade
        if grade.startswith("A"):
            color = "\033[32m"  # green
        elif grade.startswith("B"):
            color = "\033[34m"  # blue
        elif grade.startswith("C"):
            color = "\033[33m"  # yellow
        else:
            color = "\033[31m"  # red

        print(f"  {name}")
        print(f"  Trust Score: {color}\033[1m{score} ({grade})\033[0m")
        print()

        components = data.get("trust_components") or data.get("components", {})
        if components:
            print("  Components:")
            for k, v in components.items():
                print(f"    {k:20s} {v}")
            print()

        report_url = data.get("report_url", f"https://nerq.ai/is-{target}-safe")
        print(f"  Full report: {report_url}")
    else:
        print(f"  No trust data found for '{target}'")
        print(f"  Try: https://nerq.ai/is-{target}-safe")

    return 0


def cmd_scan(args):
    """Scan project dependencies."""
    import os
    from pathlib import Path

    dep_files = []
    for name in ["requirements.txt", "package.json", "pyproject.toml", "Pipfile"]:
        if os.path.exists(name):
            dep_files.append(name)

    if not dep_files:
        print("No dependency files found in current directory.")
        return 1

    print(f"\033[1mScanning {len(dep_files)} dependency file(s)...\033[0m")
    print()

    all_deps = []
    for f in dep_files:
        content = Path(f).read_text(errors="ignore")
        if "requirements" in f:
            import re
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                match = re.match(r"^([a-zA-Z0-9_.-]+)", line)
                if match:
                    all_deps.append(match.group(1))
        elif f == "package.json":
            try:
                pkg = json.loads(content)
                for section in ["dependencies", "devDependencies"]:
                    if section in pkg:
                        all_deps.extend(pkg[section].keys())
            except json.JSONDecodeError:
                pass

    # Deduplicate
    seen = set()
    unique_deps = []
    for d in all_deps:
        if d.lower() not in seen:
            seen.add(d.lower())
            unique_deps.append(d)

    print(f"  Found {len(unique_deps)} dependencies")
    print()

    results = []
    for dep in unique_deps:
        try:
            req = Request(
                f"{API_BASE}/v1/preflight?target={dep}",
                headers={"User-Agent": USER_AGENT},
            )
            resp = urlopen(req, timeout=10)
            data = json.loads(resp.read())
            score = data.get("trust_score") or data.get("target_trust")
            grade = data.get("grade", "—")
            results.append((dep, score, grade))
        except Exception:
            results.append((dep, None, "—"))

    # Print results table
    print(f"  {'Package':30s} {'Score':>6s} {'Grade':>6s}")
    print(f"  {'─' * 30} {'─' * 6} {'─' * 6}")
    for name, score, grade in results:
        score_str = str(score) if score is not None else "N/A"
        if grade.startswith("A"):
            emoji = "✅"
        elif grade.startswith("B"):
            emoji = "🟢"
        elif grade.startswith("C"):
            emoji = "⚠️"
        elif grade in ("—", "N/A"):
            emoji = "❓"
        else:
            emoji = "🔴"
        print(f"  {emoji} {name:28s} {score_str:>6s} {grade:>6s}")

    return 0


def cmd_savings(args):
    """Run LLM cost savings analysis."""
    from nerq.savings import run_savings

    estimate = None
    verbose = False
    i = 0
    while i < len(args):
        if args[i] == "--estimate" and i + 1 < len(args):
            try:
                estimate = int(args[i + 1])
            except ValueError:
                print(f"Invalid estimate value: {args[i + 1]}")
                return 1
            i += 2
        elif args[i] == "--verbose" or args[i] == "-v":
            verbose = True
            i += 1
        else:
            i += 1

    run_savings(directory=".", calls_per_day=estimate, verbose=verbose)
    return 0


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print("\033[1mnerq\033[0m — Trust verification for AI agents")
        print()
        print("Usage:")
        print("  nerq scan                    Scan project dependencies for trust scores")
        print("  nerq savings                 Find cheaper LLM alternatives")
        print("  nerq savings --estimate N    Estimate costs for N calls/day")
        print("  nerq check <package>         Check a single package trust score")
        print()
        print("Options:")
        print("  -h, --help    Show this help")
        print("  --version     Show version")
        print()
        print("Learn more: https://nerq.ai/cli")
        return 0

    if args[0] == "--version":
        from nerq import __version__
        print(f"nerq {__version__}")
        return 0

    cmd = args[0]
    cmd_args = args[1:]

    commands = {
        "scan": cmd_scan,
        "savings": cmd_savings,
        "check": cmd_check,
    }

    if cmd in commands:
        return commands[cmd](cmd_args)
    else:
        print(f"Unknown command: {cmd}")
        print("Run 'nerq --help' for usage.")
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
