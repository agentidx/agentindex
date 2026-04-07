"""CLI entry point for agent-security."""

import sys
from agent_security.scanner import scan_file, detect_and_parse, check_trust
from agent_security.reporter import (
    format_scan_report, format_fix_report, generate_badge_markdown,
    generate_github_action, bold
)


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h", "help"):
        print_help()
        return

    command = args[0]
    api_url = None

    # Extract --api-url flag if present
    for i, arg in enumerate(args):
        if arg == "--api-url" and i + 1 < len(args):
            api_url = args[i + 1]
            args = args[:i] + args[i + 2:]
            break

    if command == "scan":
        if len(args) < 2:
            print("Usage: agent-security scan <requirements.txt|package.json|pyproject.toml>")
            sys.exit(1)
        filepath = args[1]
        ci_mode = "--ci" in args

        print(f"Scanning {filepath}...")
        results = scan_file(filepath, api_url)
        print(format_scan_report(results, filepath))

        if ci_mode:
            critical = sum(1 for r in results if r["trust_score"] is not None and r["trust_score"] < 40)
            if critical > 0:
                sys.exit(1)

    elif command == "fix":
        if len(args) < 2:
            print("Usage: agent-security fix <requirements.txt|package.json|pyproject.toml>")
            sys.exit(1)
        filepath = args[1]
        results = scan_file(filepath, api_url)
        print(format_fix_report(results))

    elif command == "badge":
        name = args[1] if len(args) > 1 else "my-project"
        print(f"\nAdd this to your README:\n")
        print(f"  {generate_badge_markdown(name)}\n")

    elif command == "ci":
        print(f"\nAdd this to .github/workflows/trust-check.yml:\n")
        print(generate_github_action())

    elif command == "check":
        if len(args) < 2:
            print("Usage: agent-security check <package-name>")
            sys.exit(1)
        name = args[1]
        result = check_trust(name, api_url)
        if result["error"]:
            print(f"  {name}: not found ({result['error']})")
        else:
            trust = int(result["trust_score"]) if result["trust_score"] else "?"
            grade = result["grade"] or "?"
            print(f"  {name}: Trust {trust} ({grade}) — {result['recommendation']}")
            if result["cve_count"]:
                print(f"  CVEs: {result['cve_count']}")
            if result["license"]:
                print(f"  License: {result['license']}")

    else:
        print(f"Unknown command: {command}")
        print_help()
        sys.exit(1)


def print_help():
    print("""
agent-security — Know if your AI dependencies are safe. One command.

Commands:
  scan <file>     Scan dependencies for trust scores and CVEs
  fix <file>      Show fix recommendations for problematic dependencies
  check <name>    Check trust for a single package
  badge [name]    Generate Nerq trust badge markdown
  ci              Generate GitHub Action YAML for CI integration

Supported files:
  requirements.txt, package.json, pyproject.toml

Options:
  --ci            Exit with code 1 if critical issues found (for CI)
  --api-url URL   Override Nerq API URL

Examples:
  agent-security scan requirements.txt
  agent-security fix package.json
  agent-security check langchain
  agent-security badge my-project
  agent-security ci

Powered by nerq.ai — the trust layer for AI agents.
""")


if __name__ == "__main__":
    main()
