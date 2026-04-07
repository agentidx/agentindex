#!/usr/bin/env python3
"""nerq — AI agent trust verification CLI

Usage:
    nerq check <agent>         Check an agent's trust score
    nerq scan <file>           Scan requirements.txt or package.json
    nerq recommend <task>      Get agent recommendations for a task
    nerq compare <a> <b>       Compare two agents
"""

import argparse
import json
import re
import sys
import urllib.request
import urllib.parse

API = "https://nerq.ai"

C = {
    "r": "\033[91m", "g": "\033[92m", "y": "\033[93m",
    "b": "\033[94m", "w": "\033[97m", "d": "\033[90m",
    "B": "\033[1m", "0": "\033[0m",
}


def _get(path):
    url = f"{API}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "nerq-cli/1.0"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def _score_color(score):
    if score is None: return C["d"]
    if score >= 80: return C["g"]
    if score >= 60: return C["y"]
    return C["r"]


def check(agent):
    data = _get(f"/v1/preflight?target={urllib.parse.quote(agent)}")
    score = data.get("trust_score", "N/A")
    grade = data.get("grade", "?")
    rec = data.get("recommendation", "UNKNOWN")
    cves = data.get("security", {}).get("known_cves", 0)
    lic = data.get("security", {}).get("license", "Unknown")
    category = data.get("category", "—")
    sc = _score_color(score if isinstance(score, (int, float)) else None)

    w = 52
    print(f"{C['B']}╭{'─' * w}╮{C['0']}")
    print(f"{C['B']}│{C['0']} {C['w']}{agent:<{w-1}}{C['0']}{C['B']}│{C['0']}")
    print(f"{C['B']}├{'─' * w}┤{C['0']}")

    line1 = f"Trust Score: {sc}{score}/100 ({grade}){C['0']}"
    # Calculate visible length (without ANSI codes)
    vis_len = len(f"Trust Score: {score}/100 ({grade})")
    pad1 = w - 1 - vis_len
    print(f"{C['B']}│{C['0']} {line1}{' ' * max(0, pad1)}{C['B']}│{C['0']}")

    rec_color = C["g"] if rec == "PROCEED" else C["y"] if rec == "CAUTION" else C["r"]
    line2 = f"Recommendation: {rec_color}{rec}{C['0']}"
    vis_len2 = len(f"Recommendation: {rec}")
    pad2 = w - 1 - vis_len2
    print(f"{C['B']}│{C['0']} {line2}{' ' * max(0, pad2)}{C['B']}│{C['0']}")

    cve_color = C["r"] if cves > 0 else C["g"]
    cve_str = f"CVEs: {cve_color}{cves}{C['0']} | License: {lic}"
    vis_len3 = len(f"CVEs: {cves} | License: {lic}")
    pad3 = w - 1 - vis_len3
    print(f"{C['B']}│{C['0']} {cve_str}{' ' * max(0, pad3)}{C['B']}│{C['0']}")

    cat_str = f"Category: {category}"
    pad4 = w - 1 - len(cat_str)
    print(f"{C['B']}│{C['0']} {cat_str}{' ' * max(0, pad4)}{C['B']}│{C['0']}")

    print(f"{C['B']}╰{'─' * w}╯{C['0']}")
    print(f"{C['d']}  Report: https://nerq.ai/safe/{agent.lower().replace('/', '').replace(' ', '-')}{C['0']}")


def scan(filepath):
    deps = []
    with open(filepath) as f:
        content = f.read()

    if filepath.endswith(".json"):
        pkg = json.loads(content)
        for section in ("dependencies", "devDependencies"):
            deps.extend(pkg.get(section, {}).keys())
    else:
        for line in content.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                name = re.split(r"[>=<!\[;]", line)[0].strip()
                if name:
                    deps.append(name)

    if not deps:
        print("No dependencies found.")
        return

    print(f"\n{C['B']}Nerq Trust Scan — {filepath}{C['0']}")
    print(f"Checking {len(deps)} dependencies...\n")

    passed = 0
    warned = 0
    failed = 0

    for dep in sorted(set(deps)):
        try:
            data = _get(f"/v1/preflight?target={urllib.parse.quote(dep)}")
            score = data.get("trust_score")
            grade = data.get("grade", "?")
            cves = data.get("security", {}).get("known_cves", 0)
            has_critical = data.get("security", {}).get("has_critical_cve", False)

            if has_critical:
                icon = f"{C['r']}CRIT{C['0']}"
                failed += 1
            elif score and score < 60:
                icon = f"{C['y']}WARN{C['0']}"
                warned += 1
            else:
                icon = f"{C['g']} OK {C['0']}"
                passed += 1

            score_str = f"{score}/100" if score else "N/A"
            cve_str = f" [{cves} CVE]" if cves > 0 else ""
            print(f"  [{icon}] {dep}: {score_str} ({grade}){cve_str}")
        except Exception:
            print(f"  [{C['d']}SKIP{C['0']}] {dep}: could not check")

    print(f"\n{C['B']}Results:{C['0']} {C['g']}{passed} passed{C['0']}, {C['y']}{warned} warned{C['0']}, {C['r']}{failed} critical{C['0']}")


def recommend(task):
    data = _get(f"/v1/recommend?task={urllib.parse.quote(task)}")
    agents = data.get("recommendations", [])

    print(f"\n{C['B']}Recommendations for: {task}{C['0']}\n")
    for i, a in enumerate(agents[:5], 1):
        name = a.get("name", "?")
        score = a.get("trust_score", 0)
        sc = _score_color(score)
        why = a.get("why", "")
        print(f"  {i}. {C['w']}{name}{C['0']} — {sc}{score}/100{C['0']}")
        if why:
            print(f"     {C['d']}{why}{C['0']}")
    print()


def compare(a, b):
    data = _get(f"/v1/compare/{urllib.parse.quote(a)}/vs/{urllib.parse.quote(b)}")

    print(f"\n{C['B']}{a} vs {b}{C['0']}\n")
    for side in ("agent_a", "agent_b"):
        d = data.get(side, {})
        name = d.get("name", "?")
        score = d.get("trust_score", 0)
        sc = _score_color(score)
        print(f"  {C['w']}{name}{C['0']}: {sc}{score}/100{C['0']} ({d.get('grade', '?')})")

    winner = data.get("winner")
    if winner:
        print(f"\n  {C['g']}Winner: {winner}{C['0']}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="nerq — AI agent trust verification CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  nerq check langchain\n  nerq scan requirements.txt\n  nerq recommend 'code review'\n  nerq compare cursor continue-dev"
    )
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="Check an agent's trust score")
    p_check.add_argument("agent", help="Agent name to check")

    p_scan = sub.add_parser("scan", help="Scan dependencies file")
    p_scan.add_argument("file", help="Path to requirements.txt or package.json")

    p_rec = sub.add_parser("recommend", help="Get agent recommendations")
    p_rec.add_argument("task", help="Task description")

    p_cmp = sub.add_parser("compare", help="Compare two agents")
    p_cmp.add_argument("agent_a", help="First agent")
    p_cmp.add_argument("agent_b", help="Second agent")

    args = parser.parse_args()

    if args.command == "check":
        check(args.agent)
    elif args.command == "scan":
        scan(args.file)
    elif args.command == "recommend":
        recommend(args.task)
    elif args.command == "compare":
        compare(args.agent_a, args.agent_b)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
