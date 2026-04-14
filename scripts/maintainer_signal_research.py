#!/usr/bin/env python3
"""
Fas 2 DEL B: Maintainer-byte signal research for supply-chain prediction.

Tests hypothesis: maintainer activity changes before supply-chain incidents
are detectable in GitHub data.

Usage:
    python3 scripts/maintainer_signal_research.py
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
API = "https://api.github.com"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "maintainer-research")

# Known supply-chain incidents with GitHub repos
INCIDENTS = [
    {"name": "event-stream", "repo": "dominictarr/event-stream", "date": "2018-11-26",
     "type": "account-transfer", "desc": "Maintainer gave away package, new owner injected crypto-stealer"},
    {"name": "ua-parser-js", "repo": "nicsingh/ua-parser-js", "date": "2021-10-22",
     "type": "account-compromise", "desc": "Maintainer npm account hijacked, malware published"},
    {"name": "colors.js", "repo": "Marak/colors.js", "date": "2022-01-08",
     "type": "insider-sabotage", "desc": "Maintainer published infinite-loop version as protest"},
    {"name": "faker.js", "repo": "Marak/faker.js", "date": "2022-01-06",
     "type": "insider-sabotage", "desc": "Same maintainer, deleted repo content"},
    {"name": "node-ipc", "repo": "RIAEvangelist/node-ipc", "date": "2022-03-15",
     "type": "protestware", "desc": "Maintainer added geo-targeted file overwrite as protest"},
    {"name": "ctx", "repo": "fiber/ctx", "date": "2022-05-24",
     "type": "account-compromise", "desc": "PyPI package ctx hijacked to steal env vars"},
    {"name": "codecov", "repo": "codecov/codecov-bash", "date": "2021-04-01",
     "type": "ci-compromise", "desc": "Bash uploader modified to exfiltrate CI secrets"},
    {"name": "coa", "repo": "veged/coa", "date": "2021-11-04",
     "type": "account-compromise", "desc": "npm account hijacked, malware published"},
    {"name": "rc", "repo": "dominictarr/rc", "date": "2021-11-04",
     "type": "account-compromise", "desc": "Same maintainer as event-stream, npm account hijacked"},
    {"name": "vm2", "repo": "nicsingh/vm2", "date": "2023-04-17",
     "type": "vulnerability-chain", "desc": "Critical sandbox escape CVEs, eventually deprecated"},
    {"name": "polyfill-io", "repo": "nicsingh/polyfill-service", "date": "2024-06-25",
     "type": "domain-takeover", "desc": "CDN domain sold to Chinese entity, injected malware"},
    {"name": "lottie-player", "repo": "nicsingh/lottie-player", "date": "2024-10-30",
     "type": "account-compromise", "desc": "npm account hijacked, crypto drainer injected"},
    {"name": "peacenotwar", "repo": "RIAEvangelist/peacenotwar", "date": "2022-03-15",
     "type": "protestware", "desc": "Dependency of node-ipc, geo-targeted"},
]

# High-quality control repos (popular, well-maintained, no incidents)
CONTROL_REPOS = [
    "expressjs/express", "lodash/lodash", "facebook/react", "vuejs/vue",
    "angular/angular", "sveltejs/svelte", "vercel/next.js", "remix-run/remix",
    "fastify/fastify", "koajs/koa", "hapijs/hapi", "nestjs/nest",
    "axios/axios", "sindresorhus/got", "node-fetch/node-fetch",
    "chalk/chalk", "yargs/yargs", "tj/commander.js",
    "mochajs/mocha", "jestjs/jest", "avajs/ava",
    "prettier/prettier", "eslint/eslint", "webpack/webpack",
    "rollup/rollup", "vitejs/vite", "esbuild/esbuild",
    "sequelize/sequelize", "prisma/prisma", "typeorm/typeorm",
    "date-fns/date-fns", "moment/moment", "dayjs/dayjs",
]


def github_get(url):
    """Authenticated GitHub API GET."""
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "NerqResearch/1.0")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            remaining = resp.headers.get("X-RateLimit-Remaining", "?")
            if remaining != "?" and int(remaining) < 100:
                print(f"  [RATE] {remaining} remaining")
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code == 403:
            print(f"  [RATE LIMITED] sleeping 60s")
            time.sleep(60)
            return None
        print(f"  [HTTP {e.code}] {url}")
        return None
    except Exception as e:
        print(f"  [ERROR] {url}: {e}")
        return None


def get_contributors(repo):
    """Get contributor list with commit counts."""
    data = github_get(f"{API}/repos/{repo}/contributors?per_page=100")
    if not data:
        return []
    return [{"login": c.get("login",""), "contributions": c.get("contributions",0),
             "type": c.get("type","")} for c in data[:50]]


def get_recent_commits(repo, since_months=12):
    """Get recent commit metadata (not full diffs)."""
    since = (datetime.utcnow() - timedelta(days=since_months*30)).strftime("%Y-%m-%dT00:00:00Z")
    data = github_get(f"{API}/repos/{repo}/commits?since={since}&per_page=100")
    if not data:
        return []
    commits = []
    for c in data[:100]:
        author = c.get("author") or {}
        committer = c.get("committer") or {}
        commit_data = c.get("commit", {})
        commits.append({
            "sha": c.get("sha","")[:8],
            "date": commit_data.get("author",{}).get("date",""),
            "author_login": author.get("login",""),
            "committer_login": committer.get("login",""),
            "message": commit_data.get("message","")[:100],
            "author_id": author.get("id"),
        })
    return commits


def get_repo_info(repo):
    """Get basic repo info."""
    data = github_get(f"{API}/repos/{repo}")
    if not data:
        return None
    return {
        "full_name": data.get("full_name",""),
        "stars": data.get("stargazers_count",0),
        "forks": data.get("forks_count",0),
        "open_issues": data.get("open_issues_count",0),
        "created_at": data.get("created_at",""),
        "updated_at": data.get("updated_at",""),
        "pushed_at": data.get("pushed_at",""),
        "archived": data.get("archived", False),
        "owner_type": data.get("owner",{}).get("type",""),
    }


def extract_features(repo_info, contributors, commits):
    """Extract maintainer-signal features from GitHub data."""
    if not repo_info:
        return None

    f = {}

    # Basic repo features
    f["stars"] = repo_info.get("stars", 0)
    f["forks"] = repo_info.get("forks", 0)
    f["archived"] = 1 if repo_info.get("archived") else 0

    # Contributor features
    f["num_contributors"] = len(contributors)
    if contributors:
        top = contributors[0]["contributions"]
        total = sum(c["contributions"] for c in contributors)
        f["top_contributor_pct"] = top / max(total, 1)
        f["top_contributor_commits"] = top
        f["bus_factor"] = sum(1 for c in contributors if c["contributions"] > total * 0.1)
    else:
        f["top_contributor_pct"] = 1.0
        f["top_contributor_commits"] = 0
        f["bus_factor"] = 0

    # Commit features
    f["total_commits_12m"] = len(commits)
    if commits:
        # Unique authors
        authors = set(c["author_login"] for c in commits if c["author_login"])
        f["unique_authors_12m"] = len(authors)

        # Commit frequency (commits per month)
        dates = [c["date"][:10] for c in commits if c["date"]]
        if len(dates) >= 2:
            first = min(dates)
            last = max(dates)
            try:
                span = (datetime.strptime(last, "%Y-%m-%d") - datetime.strptime(first, "%Y-%m-%d")).days
                f["commits_per_month"] = len(commits) / max(span / 30, 1)
            except:
                f["commits_per_month"] = len(commits) / 12
        else:
            f["commits_per_month"] = len(commits) / 12

        # New contributor ratio (commits from authors not in top 5)
        top_5 = set(c["login"] for c in contributors[:5]) if contributors else set()
        new_author_commits = sum(1 for c in commits if c["author_login"] and c["author_login"] not in top_5)
        f["new_author_commit_ratio"] = new_author_commits / max(len(commits), 1)
    else:
        f["unique_authors_12m"] = 0
        f["commits_per_month"] = 0
        f["new_author_commit_ratio"] = 0

    return f


def run():
    os.makedirs(CACHE_DIR, exist_ok=True)

    print("=" * 70)
    print("MAINTAINER SIGNAL RESEARCH — Supply Chain Prediction")
    print("=" * 70)

    # Phase 1: Collect data for incident repos
    print(f"\n[1] Collecting data for {len(INCIDENTS)} incident repos...")
    incident_features = []
    for inc in INCIDENTS:
        repo = inc["repo"]
        print(f"  {repo}...", end=" ", flush=True)
        info = get_repo_info(repo)
        if not info:
            print("NOT FOUND (repo may be deleted/private)")
            inc["features"] = None
            inc["status"] = "not_found"
            continue
        contribs = get_contributors(repo)
        commits = get_recent_commits(repo)
        features = extract_features(info, contribs, commits)
        inc["features"] = features
        inc["contributors"] = len(contribs)
        inc["commits_found"] = len(commits)
        inc["status"] = "ok"
        if features:
            features["is_incident"] = 1
            features["repo"] = repo
            incident_features.append(features)
        print(f"✓ {len(contribs)} contributors, {len(commits)} commits")
        time.sleep(1)

    # Phase 2: Collect data for control repos
    print(f"\n[2] Collecting data for {len(CONTROL_REPOS)} control repos...")
    control_features = []
    for repo in CONTROL_REPOS:
        print(f"  {repo}...", end=" ", flush=True)
        info = get_repo_info(repo)
        if not info:
            print("NOT FOUND")
            continue
        contribs = get_contributors(repo)
        commits = get_recent_commits(repo)
        features = extract_features(info, contribs, commits)
        if features:
            features["is_incident"] = 0
            features["repo"] = repo
            control_features.append(features)
        print(f"✓ {len(contribs)} contributors, {len(commits)} commits")
        time.sleep(1)

    # Phase 3: Statistical comparison
    print(f"\n[3] Statistical analysis...")
    print(f"  Incident repos with data: {len(incident_features)}")
    print(f"  Control repos with data: {len(control_features)}")

    if len(incident_features) < 3 or len(control_features) < 10:
        print("  INSUFFICIENT DATA for meaningful analysis")
        return

    feature_names = [k for k in incident_features[0].keys()
                     if k not in ("is_incident", "repo")]

    print(f"\n{'Feature':<30} {'Incident mean':>15} {'Control mean':>15} {'Ratio':>8} {'Signal?':>8}")
    print("-" * 80)

    results = []
    for feat in feature_names:
        inc_vals = [f[feat] for f in incident_features if feat in f]
        ctrl_vals = [f[feat] for f in control_features if feat in f]

        if not inc_vals or not ctrl_vals:
            continue

        inc_mean = statistics.mean(inc_vals)
        ctrl_mean = statistics.mean(ctrl_vals)
        ratio = inc_mean / max(ctrl_mean, 0.001)

        # Simple effect size
        signal = "✓" if abs(ratio - 1.0) > 0.5 else "~" if abs(ratio - 1.0) > 0.2 else ""

        print(f"  {feat:<30} {inc_mean:>15.2f} {ctrl_mean:>15.2f} {ratio:>7.2f}x {signal:>8}")
        results.append({
            "feature": feat,
            "incident_mean": round(inc_mean, 3),
            "control_mean": round(ctrl_mean, 3),
            "ratio": round(ratio, 3),
            "n_incident": len(inc_vals),
            "n_control": len(ctrl_vals),
        })

    # Save results
    output = {
        "incidents": [{"name": i["name"], "repo": i["repo"], "type": i["type"],
                        "status": i.get("status",""), "features": i.get("features")}
                       for i in INCIDENTS],
        "control_count": len(control_features),
        "feature_comparison": results,
        "incident_features": incident_features,
        "control_features": control_features,
    }

    out_path = os.path.join(CACHE_DIR, "maintainer_signal_results.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")

    # Export CSV for Anders
    csv_path = os.path.expanduser("~/Desktop/April/maintainer-signal-features.csv")
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w") as f:
        all_feats = incident_features + control_features
        headers = ["repo", "is_incident"] + feature_names
        f.write(",".join(headers) + "\n")
        for feat_dict in all_feats:
            row = [str(feat_dict.get(h, "")) for h in headers]
            f.write(",".join(row) + "\n")
    print(f"CSV exported to {csv_path}")


if __name__ == "__main__":
    if not GITHUB_TOKEN:
        print("Set GITHUB_TOKEN env var first")
        sys.exit(1)
    run()
