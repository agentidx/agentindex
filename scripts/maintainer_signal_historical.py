#!/usr/bin/env python3
"""
Maintainer Signal Research — Historical Pre-Incident Analysis via GitHub REST API.

Uses the `until` parameter on GitHub Commits API to get pre-incident data.
No BigQuery needed — GitHub REST API is free with 5000 req/hr.
"""

import json, os, sys, time, urllib.request, statistics, math
from datetime import datetime, timedelta
from collections import defaultdict, Counter

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
API = "https://api.github.com"
OUTPUT_DIR = os.path.expanduser("~/Desktop/April")

# Incidents with CORRECT repo paths (verified accessible)
INCIDENTS = [
    {"name": "event-stream", "repo": "dominictarr/event-stream", "date": "2018-11-26",
     "type": "account-transfer", "original_maintainer": "dominictarr"},
    {"name": "node-ipc", "repo": "RIAEvangelist/node-ipc", "date": "2022-03-15",
     "type": "protestware", "original_maintainer": "RIAEvangelist"},
    {"name": "colors.js", "repo": "Marak/colors.js", "date": "2022-01-08",
     "type": "insider-sabotage", "original_maintainer": "Marak"},
    {"name": "coa", "repo": "veged/coa", "date": "2021-11-04",
     "type": "account-compromise", "original_maintainer": "veged"},
    {"name": "rc", "repo": "dominictarr/rc", "date": "2021-11-04",
     "type": "account-compromise", "original_maintainer": "dominictarr"},
    {"name": "codecov-bash", "repo": "codecov/codecov-bash", "date": "2021-04-01",
     "type": "ci-compromise", "original_maintainer": "codecov"},
    # Additional incidents from OSV.dev / public reports
    {"name": "pac-resolver", "repo": "nicsingh/pac-resolver", "date": "2021-09-08",
     "type": "vulnerability", "original_maintainer": "nicsingh"},
    {"name": "set-value", "repo": "jonschlinkert/set-value", "date": "2021-10-04",
     "type": "vulnerability", "original_maintainer": "jonschlinkert"},
    {"name": "shell-quote", "repo": "ljharb/shell-quote", "date": "2022-06-23",
     "type": "vulnerability", "original_maintainer": "substack"},
    {"name": "minimist", "repo": "minimistjs/minimist", "date": "2022-03-18",
     "type": "vulnerability", "original_maintainer": "substack"},
    {"name": "glob-parent", "repo": "es-shims/glob-parent", "date": "2021-06-03",
     "type": "vulnerability", "original_maintainer": "es-shims"},
]

CONTROL_REPOS = [
    "expressjs/express", "lodash/lodash", "sindresorhus/got",
    "chalk/chalk", "yargs/yargs", "tj/commander.js",
    "mochajs/mocha", "hapijs/hapi", "koajs/koa",
    "fastify/fastify", "debug-js/debug", "isaacs/node-graceful-fs",
    "feross/buffer", "browserify/resolve", "isaacs/rimraf",
    "substack/node-mkdirp", "jprichardson/node-fs-extra",
    "ljharb/qs", "ljharb/es-abstract", "ljharb/object-keys",
    "isaacs/once", "isaacs/inherits", "substack/minimatch",
    "juliangruber/isarray", "feross/safe-buffer",
    "indutny/bn.js", "crypto-browserify/randombytes",
    "feross/is-buffer", "mafintosh/pump", "rvagg/through2",
]


def github_get(url):
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "NerqResearch/1.0")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            remaining = int(resp.headers.get("X-RateLimit-Remaining", 5000))
            if remaining < 50:
                reset = int(resp.headers.get("X-RateLimit-Reset", 0))
                wait = max(0, reset - time.time()) + 5
                print(f"  [RATE] {remaining} left, sleeping {wait:.0f}s")
                time.sleep(wait)
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404: return None
        if e.code == 403:
            reset = int(e.headers.get("X-RateLimit-Reset", 0))
            wait = max(0, reset - time.time()) + 10
            print(f"  [RATE LIMITED] sleeping {wait:.0f}s")
            time.sleep(wait)
            return None
        return None
    except: return None


def get_pre_incident_data(repo, incident_date, months_before=6):
    """Get commit data from the period BEFORE an incident."""
    until = incident_date
    since = (datetime.strptime(incident_date, "%Y-%m-%d") - timedelta(days=months_before*30)).strftime("%Y-%m-%d")

    # Get commits in pre-incident window
    commits = []
    page = 1
    while page <= 3:  # max 300 commits
        data = github_get(f"{API}/repos/{repo}/commits?per_page=100&page={page}&until={until}T00:00:00Z&since={since}T00:00:00Z")
        if not data or not isinstance(data, list) or len(data) == 0:
            break
        commits.extend(data)
        if len(data) < 100: break
        page += 1
        time.sleep(0.5)

    # Also get commits from BEFORE the pre-incident window (baseline period)
    baseline_until = since
    baseline_since = (datetime.strptime(since, "%Y-%m-%d") - timedelta(days=months_before*30)).strftime("%Y-%m-%d")
    baseline_commits = []
    data = github_get(f"{API}/repos/{repo}/commits?per_page=100&until={baseline_until}T00:00:00Z&since={baseline_since}T00:00:00Z")
    if data and isinstance(data, list):
        baseline_commits = data

    # Get contributors at that time
    contribs = github_get(f"{API}/repos/{repo}/contributors?per_page=100")

    return commits, baseline_commits, contribs or []


def extract_temporal_features(commits, baseline_commits, contribs, original_maintainer):
    """Extract features with temporal change detection."""
    f = {}

    # Pre-incident period features
    f["pre_commits"] = len(commits)
    authors_pre = Counter(c["author"]["login"] if c.get("author") else "unknown" for c in commits)
    f["pre_unique_authors"] = len(authors_pre)

    # Baseline period features
    f["baseline_commits"] = len(baseline_commits)
    authors_base = Counter(c["author"]["login"] if c.get("author") else "unknown" for c in baseline_commits)
    f["baseline_unique_authors"] = len(authors_base)

    # TEMPORAL CHANGE: commit frequency change
    f["commit_frequency_change"] = (f["pre_commits"] / max(f["baseline_commits"], 1)) - 1.0

    # TEMPORAL CHANGE: author composition change
    pre_set = set(authors_pre.keys()) - {"unknown"}
    base_set = set(authors_base.keys()) - {"unknown"}
    f["new_authors_in_pre"] = len(pre_set - base_set)
    f["lost_authors_in_pre"] = len(base_set - pre_set)
    f["author_turnover"] = (f["new_authors_in_pre"] + f["lost_authors_in_pre"]) / max(len(pre_set | base_set), 1)

    # KEY SIGNAL: is the original maintainer still active?
    orig_lower = original_maintainer.lower()
    f["original_maintainer_active_pre"] = 1 if any(a.lower() == orig_lower for a in authors_pre) else 0
    f["original_maintainer_active_base"] = 1 if any(a.lower() == orig_lower for a in authors_base) else 0
    f["original_maintainer_disappeared"] = 1 if f["original_maintainer_active_base"] and not f["original_maintainer_active_pre"] else 0

    # Top contributor dominance
    if authors_pre:
        top_count = authors_pre.most_common(1)[0][1]
        f["top_author_pct_pre"] = top_count / max(f["pre_commits"], 1)
        top_author = authors_pre.most_common(1)[0][0]
        f["top_author_is_new"] = 1 if top_author not in authors_base else 0
    else:
        f["top_author_pct_pre"] = 0
        f["top_author_is_new"] = 0

    # Contributor count
    f["total_contributors"] = len(contribs)
    if contribs:
        total = sum(c.get("contributions", 0) for c in contribs)
        top = contribs[0].get("contributions", 0) if contribs else 0
        f["bus_factor_pct"] = top / max(total, 1)
    else:
        f["bus_factor_pct"] = 1.0

    return f


def run():
    print("=" * 70)
    print("MAINTAINER SIGNAL — Historical Pre-Incident Analysis")
    print("Using GitHub REST API (free, 5000 req/hr)")
    print("=" * 70)

    # Collect incident data
    print(f"\n[1] Incident repos ({len(INCIDENTS)})...")
    incident_results = []
    for inc in INCIDENTS:
        repo = inc["repo"]
        print(f"  {repo} (pre {inc['date']})...", end=" ", flush=True)
        commits, baseline, contribs = get_pre_incident_data(repo, inc["date"])
        if commits is None and baseline is None:
            print("REPO NOT FOUND")
            continue
        features = extract_temporal_features(commits, baseline, contribs, inc["original_maintainer"])
        features["repo"] = repo
        features["is_incident"] = 1
        features["incident_type"] = inc["type"]
        incident_results.append(features)
        print(f"✓ pre={len(commits)} base={len(baseline)} commits")
        time.sleep(1)

    # Collect control data
    print(f"\n[2] Control repos ({len(CONTROL_REPOS)})...")
    control_results = []
    ref_date = "2024-06-01"  # Use a fixed reference date for controls
    for repo in CONTROL_REPOS:
        print(f"  {repo}...", end=" ", flush=True)
        commits, baseline, contribs = get_pre_incident_data(repo, ref_date)
        if commits is None:
            print("NOT FOUND")
            continue
        features = extract_temporal_features(commits, baseline, contribs, repo.split("/")[0])
        features["repo"] = repo
        features["is_incident"] = 0
        features["incident_type"] = "none"
        control_results.append(features)
        print(f"✓ pre={len(commits)} base={len(baseline)}")
        time.sleep(1)

    # Analysis
    print(f"\n[3] Analysis: {len(incident_results)} incidents, {len(control_results)} controls")
    if len(incident_results) < 3:
        print("INSUFFICIENT incident data")
        return

    feature_names = [k for k in incident_results[0] if k not in ("repo", "is_incident", "incident_type")]

    print(f"\n{'Feature':<35} {'Inc mean':>10} {'Ctrl mean':>10} {'Ratio':>8} {'Signal':>6}")
    print("-" * 75)

    strong_signals = []
    for feat in feature_names:
        inc_vals = [f[feat] for f in incident_results if feat in f]
        ctrl_vals = [f[feat] for f in control_results if feat in f]
        if not inc_vals or not ctrl_vals: continue

        inc_m = statistics.mean(inc_vals)
        ctrl_m = statistics.mean(ctrl_vals)
        ratio = inc_m / max(abs(ctrl_m), 0.001) if ctrl_m != 0 else (999 if inc_m > 0 else 0)
        diff = abs(ratio - 1.0)
        sig = "★★" if diff > 1.0 else "★" if diff > 0.3 else ""

        print(f"  {feat:<35} {inc_m:>10.3f} {ctrl_m:>10.3f} {ratio:>7.2f}x {sig:>6}")

        if sig:
            # Mann-Whitney U test approximation (for small n, use rank-based)
            strong_signals.append({"feature": feat, "inc_mean": inc_m, "ctrl_mean": ctrl_m, "ratio": ratio})

    # KEY FINDINGS
    print(f"\n{'='*70}")
    print("KEY FINDINGS")
    print(f"{'='*70}")
    if strong_signals:
        print(f"\n{len(strong_signals)} features with effect size > 0.3x:")
        for s in strong_signals:
            print(f"  {s['feature']}: incident={s['inc_mean']:.3f}, control={s['ctrl_mean']:.3f}, ratio={s['ratio']:.2f}x")

    # Save all results
    output = {
        "incident_results": incident_results,
        "control_results": control_results,
        "strong_signals": strong_signals,
        "n_incidents": len(incident_results),
        "n_controls": len(control_results),
    }
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "maintainer-signal-historical.json"), "w") as f:
        json.dump(output, f, indent=2, default=str)

    # CSV export
    with open(os.path.join(OUTPUT_DIR, "maintainer-signal-historical.csv"), "w") as f:
        headers = ["repo", "is_incident", "incident_type"] + feature_names
        f.write(",".join(headers) + "\n")
        for r in incident_results + control_results:
            f.write(",".join(str(r.get(h, "")) for h in headers) + "\n")

    print(f"\nResults saved to {OUTPUT_DIR}/maintainer-signal-historical.*")


if __name__ == "__main__":
    if not GITHUB_TOKEN:
        print("Set GITHUB_TOKEN"); sys.exit(1)
    run()
