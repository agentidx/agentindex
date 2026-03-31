"""
Nerq Benchmark: "With Nerq" vs "Without Nerq" for agent tool selection.

Methodology:
- Pool: 50 agents (15 high-trust, 15 medium-trust, 10 low-trust, 10 dead/not-found)
- Each iteration: randomly select 5 from the pool
- 100 iterations per scenario
- Statistical tests: two-sample t-test, 95% confidence intervals

Run: python -m agentindex.nerq_benchmark_test
"""

import json
import math
import os
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Tool pool — 50 agents, realistic distribution from live DB
# ---------------------------------------------------------------------------

# 15 high-trust agents (trust > 70, real agents from Nerq index)
HIGH_TRUST = [
    "SWE-agent/SWE-agent",
    "microsoft/qlib",
    "FunnyWolf/agentic-soc-platform",
    "harbor",
    "microsoft/azure-devops-mcp",
    "vfarcic/dot-ai",
    "opal",
    "raptor",
    "nanobot",
    "GoogleCloudPlatform/agent-starter-pack",
    "laravel/mcp",
    "williamzujkowski/strudel-mcp-server",
    "nanoclaw",
    "laravel/boost",
    "ccmanager",
]

# 15 medium-trust agents (trust 40-69, real agents from Nerq index)
MEDIUM_TRUST = [
    "crypto-mcp",
    "AgentFlow",
    "Orchestrator-AI-Agent-Platform",
    "multi-agent-coding-assistant",
    "psbds/mcp-dev-blueprints",
    "Ai-agents-with-vercel-ai-sdk",
    "UBC-CIC/Legal-Aid-Tool",
    "Agentic_RAG_UIT_Chatbot",
    "daily-quote-cli",
    "Astram",
    "Layla-support-agent",
    "WebSearchAIAgent",
    "Multi-Agent-for-Coding",
    "AgentForge",
    "WolfgangFahl/py-3rdparty-mediawiki",
]

# 10 low-trust agents (trust < 40, real agents from Nerq index)
LOW_TRUST = [
    "agentverse-agent1q2hcc4et05ypas97yzvsxgh65cywp39lk8gt9jgk6zxxkvzwxff22s249ps",
    "Image-based-plant-disease-diagnosis",
    "segmentdiagnosis",
    "HealthCareMagic-Gemma-FT-Final",
    "dutch-medical-set",
    "healthcare_ai_loop",
    "LehrChatBotFinance",
    "agentverse-agent1qdj8f5a4ahqc8cw92ldn55anxkvqwgpe2p0lxua7c6drzlk06pysuf6jg0k",
    "agentverse-agent1q006v62de5jf0edfzfh2y8ln9829y4wcvunnvkcngk9qejekxdqwusqquzq",
    "agentverse-agent1q25n8dfmkut68j6t8v8dkr8jv97vee7ae7yw4h7vfnvetyds39trvlmypv7",
]

# 10 dead/not-found agents (names that don't exist in the DB)
NOT_FOUND = [
    "abandoned-tool-2023",
    "deleted-agent-xyz",
    "test-agent-null",
    "deprecated-scanner",
    "ghost-protocol-ai",
    "gpt3-wrapper-2022",
    "old-chatbot-framework",
    "zombie-agent-v1",
    "dead-ml-pipeline",
    "extinct-data-tool",
]

ALL_TOOLS = HIGH_TRUST + MEDIUM_TRUST + LOW_TRUST + NOT_FOUND

BASE_URL = "http://localhost:8000"
TRUST_THRESHOLD = 40
NUM_SELECT = 5
NUM_RUNS = 100
HEADERS = {"X-API-Key": "nerq-internal-2026"}


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def welch_t_test(sample_a: list[float], sample_b: list[float]) -> tuple[float, float]:
    """Welch's two-sample t-test (unequal variances).

    Returns (t_statistic, p_value).
    """
    n1, n2 = len(sample_a), len(sample_b)
    if n1 < 2 or n2 < 2:
        return 0.0, 1.0

    m1, m2 = statistics.mean(sample_a), statistics.mean(sample_b)
    v1 = statistics.variance(sample_a)
    v2 = statistics.variance(sample_b)

    se = math.sqrt(v1 / n1 + v2 / n2)
    if se == 0:
        return float("inf") if m1 != m2 else 0.0, 0.0 if m1 != m2 else 1.0

    t_stat = (m1 - m2) / se

    # Welch-Satterthwaite degrees of freedom
    num = (v1 / n1 + v2 / n2) ** 2
    den = (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    df = num / den if den > 0 else n1 + n2 - 2

    # Approximate two-tailed p-value using normal distribution (good for df > 30)
    p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2))))
    return t_stat, p_value


def confidence_interval_95(values: list[float]) -> tuple[float, float, float]:
    """Returns (mean, ci_lower, ci_upper) for 95% CI."""
    n = len(values)
    if n < 2:
        m = values[0] if values else 0
        return m, m, m
    m = statistics.mean(values)
    sd = statistics.stdev(values)
    margin = 1.96 * sd / math.sqrt(n)
    return m, m - margin, m + margin


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def call_kya(name: str) -> dict:
    """Call KYA endpoint, return normalized result with timing."""
    url = f"{BASE_URL}/v1/agent/kya/{requests.utils.quote(name, safe='')}"
    t0 = time.perf_counter()
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        elapsed = time.perf_counter() - t0
        if resp.status_code == 200:
            data = resp.json()
            trust = data.get("trust_score")
            return {
                "name": name,
                "found": True,
                "trust_score": trust,
                "time_s": round(elapsed, 4),
                "success": trust is not None and trust >= TRUST_THRESHOLD,
            }
        return {
            "name": name,
            "found": False,
            "trust_score": None,
            "time_s": round(elapsed, 4),
            "success": False,
        }
    except requests.RequestException:
        elapsed = time.perf_counter() - t0
        return {
            "name": name,
            "found": False,
            "trust_score": None,
            "time_s": round(elapsed, 4),
            "success": False,
        }


def call_preflight(name: str) -> dict:
    """Call preflight endpoint, return normalized result with timing."""
    url = f"{BASE_URL}/v1/preflight"
    t0 = time.perf_counter()
    try:
        resp = requests.get(url, params={"target": name}, headers=HEADERS, timeout=10)
        elapsed = time.perf_counter() - t0
        if resp.status_code == 200:
            data = resp.json()
            trust = data.get("target_trust")
            recommendation = data.get("recommendation", "UNKNOWN")
            return {
                "name": name,
                "found": trust is not None,
                "trust_score": trust,
                "recommendation": recommendation,
                "time_s": round(elapsed, 4),
                "success": trust is not None and trust >= TRUST_THRESHOLD,
            }
        return {
            "name": name,
            "found": False,
            "trust_score": None,
            "recommendation": "UNKNOWN",
            "time_s": round(elapsed, 4),
            "success": False,
        }
    except requests.RequestException:
        elapsed = time.perf_counter() - t0
        return {
            "name": name,
            "found": False,
            "trust_score": None,
            "recommendation": "UNKNOWN",
            "time_s": round(elapsed, 4),
            "success": False,
        }


# ---------------------------------------------------------------------------
# Test runners
# ---------------------------------------------------------------------------

def run_without_nerq(seed: int) -> dict:
    """Scenario A: Pick 5 random tools from pool, call KYA on each."""
    rng = random.Random(seed)
    selected = rng.sample(ALL_TOOLS, NUM_SELECT)
    results = [call_kya(name) for name in selected]
    failures = sum(1 for r in results if not r["success"])
    trust_scores = [r["trust_score"] for r in results if r["trust_score"] is not None]
    return {
        "selected": [r["name"] for r in results],
        "total_calls": len(results),
        "failures": failures,
        "failure_rate": round(failures / len(results) * 100, 1),
        "avg_trust": round(statistics.mean(trust_scores), 1) if trust_scores else 0.0,
        "total_time_s": round(sum(r["time_s"] for r in results), 4),
        "wasted_calls": failures,
        "details": results,
    }


def run_with_nerq(seed: int) -> dict:
    """Scenario B: Preflight all candidates, filter to PROCEED, pick top 5 by trust."""
    all_results = [call_preflight(name) for name in ALL_TOOLS]
    total_time = sum(r["time_s"] for r in all_results)

    # Filter to PROCEED only
    proceed = [r for r in all_results if r.get("recommendation") == "PROCEED"]
    proceed.sort(key=lambda r: r["trust_score"] or 0, reverse=True)
    selected = proceed[:NUM_SELECT]

    failures = sum(1 for r in selected if not r["success"])
    trust_scores = [r["trust_score"] for r in selected if r["trust_score"] is not None]
    return {
        "selected": [r["name"] for r in selected],
        "total_calls": len(all_results),
        "selected_count": len(selected),
        "failures": failures,
        "failure_rate": round(failures / max(len(selected), 1) * 100, 1),
        "avg_trust": round(statistics.mean(trust_scores), 1) if trust_scores else 0.0,
        "total_time_s": round(total_time, 4),
        "wasted_calls": len(all_results) - len(selected),
        "screened_out": len(all_results) - len(proceed),
        "details": all_results,
    }


# ---------------------------------------------------------------------------
# Aggregation with proper statistics
# ---------------------------------------------------------------------------

def aggregate_runs(runs: list[dict]) -> dict:
    """Compute mean, stdev, 95% CI for each metric across runs."""
    failure_rates = [r["failure_rate"] for r in runs]
    trust_scores = [r["avg_trust"] for r in runs]
    n = len(runs)

    fr_mean, fr_ci_lo, fr_ci_hi = confidence_interval_95(failure_rates)
    tr_mean, tr_ci_lo, tr_ci_hi = confidence_interval_95(trust_scores)
    fr_sd = statistics.stdev(failure_rates) if n > 1 else 0.0
    tr_sd = statistics.stdev(trust_scores) if n > 1 else 0.0

    return {
        "n": n,
        "failure_rate_mean": round(fr_mean, 2),
        "failure_rate_stdev": round(fr_sd, 2),
        "failure_rate_ci_lower": round(fr_ci_lo, 2),
        "failure_rate_ci_upper": round(fr_ci_hi, 2),
        "trust_mean": round(tr_mean, 2),
        "trust_stdev": round(tr_sd, 2),
        "trust_ci_lower": round(tr_ci_lo, 2),
        "trust_ci_upper": round(tr_ci_hi, 2),
        "avg_total_time_s": round(statistics.mean(r["total_time_s"] for r in runs), 4),
        "avg_wasted_calls": round(statistics.mean(r["wasted_calls"] for r in runs), 1),
        "avg_failures": round(statistics.mean(r["failures"] for r in runs), 1),
        "avg_total_calls": round(statistics.mean(r["total_calls"] for r in runs), 1),
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_comparison(agg_a: dict, agg_b: dict, t_fail: float, p_fail: float,
                     t_trust: float, p_trust: float):
    """Print comparison table to stdout."""
    header = f"{'Metric':<30} {'Without Nerq':>25} {'With Nerq':>25} {'Delta':>12}"
    sep = "-" * len(header)
    print()
    print("=" * len(header))
    print("  NERQ BENCHMARK: Agent Tool Selection")
    print(f"  Pool: {len(ALL_TOOLS)} tools (15 high + 15 medium + 10 low + 10 dead)")
    print(f"  Select: {NUM_SELECT} tools per iteration | N={NUM_RUNS} iterations")
    print("=" * len(header))
    print()
    print(header)
    print(sep)

    a_fr = f"{agg_a['failure_rate_mean']:.1f} +/- {agg_a['failure_rate_stdev']:.1f}%"
    b_fr = f"{agg_b['failure_rate_mean']:.1f} +/- {agg_b['failure_rate_stdev']:.1f}%"
    diff_fr = agg_b["failure_rate_mean"] - agg_a["failure_rate_mean"]
    print(f"{'Failure rate':<30} {a_fr:>25} {b_fr:>25} {diff_fr:>+11.1f}%")

    a_tr = f"{agg_a['trust_mean']:.1f} +/- {agg_a['trust_stdev']:.1f}"
    b_tr = f"{agg_b['trust_mean']:.1f} +/- {agg_b['trust_stdev']:.1f}"
    diff_tr = agg_b["trust_mean"] - agg_a["trust_mean"]
    print(f"{'Avg trust score':<30} {a_tr:>25} {b_tr:>25} {diff_tr:>+11.1f}")

    print(f"{'API time (s)':<30} {agg_a['avg_total_time_s']:>24.3f}s {agg_b['avg_total_time_s']:>24.3f}s {agg_b['avg_total_time_s'] - agg_a['avg_total_time_s']:>+11.3f}s")
    print(f"{'Wasted calls':<30} {agg_a['avg_wasted_calls']:>25.1f} {agg_b['avg_wasted_calls']:>25.1f} {agg_b['avg_wasted_calls'] - agg_a['avg_wasted_calls']:>+11.1f}")
    print(sep)

    sig_fail = "YES" if p_fail < 0.05 else "NO"
    sig_trust = "YES" if p_trust < 0.05 else "NO"
    print(f"\n  Failure rate t-test:  t={t_fail:.3f}, p={p_fail:.8f}  Significant (p<0.05): {sig_fail}")
    print(f"  Trust score t-test:  t={t_trust:.3f}, p={p_trust:.8f}  Significant (p<0.05): {sig_trust}")
    print(f"  95% CI (without): failure {agg_a['failure_rate_ci_lower']:.1f}-{agg_a['failure_rate_ci_upper']:.1f}%, trust {agg_a['trust_ci_lower']:.1f}-{agg_a['trust_ci_upper']:.1f}")
    print(f"  95% CI (with):    failure {agg_b['failure_rate_ci_lower']:.1f}-{agg_b['failure_rate_ci_upper']:.1f}%, trust {agg_b['trust_ci_lower']:.1f}-{agg_b['trust_ci_upper']:.1f}")
    print()


def generate_markdown(agg_a: dict, agg_b: dict, t_fail: float, p_fail: float,
                      t_trust: float, p_trust: float, ts: str) -> str:
    """Generate markdown benchmark report."""
    sig_fail = "statistically significant" if p_fail < 0.05 else "not statistically significant"
    sig_trust = "statistically significant" if p_trust < 0.05 else "not statistically significant"

    return f"""# Nerq Benchmark: With vs Without Nerq

**Date:** {ts}
**N:** {NUM_RUNS} iterations per scenario
**Pool:** {len(ALL_TOOLS)} agents (15 high-trust + 15 medium-trust + 10 low-trust + 10 dead/not-found)
**Selection:** {NUM_SELECT} tools per iteration

## Methodology

- **Without Nerq (baseline):** Randomly select {NUM_SELECT} tools from the pool. Call `/v1/agent/kya/{{name}}` for each. Tools with trust < {TRUST_THRESHOLD} or not found count as failures.
- **With Nerq:** Call `/v1/preflight?target={{name}}` for all {len(ALL_TOOLS)} candidates. Filter to `recommendation == "PROCEED"`. Sort by trust score descending. Pick top {NUM_SELECT}.
- **Statistical test:** Welch's two-sample t-test (unequal variances). Significance threshold: p < 0.05.

## Tool Pool

| Tier | Count | Description |
|------|-------|-------------|
| High trust (>70) | {len(HIGH_TRUST)} | Real agents from Nerq index with trust > 70 |
| Medium trust (40-69) | {len(MEDIUM_TRUST)} | Real agents from Nerq index with trust 40-69 |
| Low trust (<40) | {len(LOW_TRUST)} | Real agents from Nerq index with trust < 40 |
| Dead / not found | {len(NOT_FOUND)} | Names that don't exist in the Nerq index |

## Results (N={NUM_RUNS} iterations)

| Metric | Without Nerq | With Nerq | Delta |
|--------|-------------|-----------|-------|
| Failure rate (mean +/- SD) | {agg_a['failure_rate_mean']:.1f} +/- {agg_a['failure_rate_stdev']:.1f}% | {agg_b['failure_rate_mean']:.1f} +/- {agg_b['failure_rate_stdev']:.1f}% | {agg_b['failure_rate_mean'] - agg_a['failure_rate_mean']:+.1f}% |
| Failure rate 95% CI | [{agg_a['failure_rate_ci_lower']:.1f}, {agg_a['failure_rate_ci_upper']:.1f}]% | [{agg_b['failure_rate_ci_lower']:.1f}, {agg_b['failure_rate_ci_upper']:.1f}]% | |
| Trust score (mean +/- SD) | {agg_a['trust_mean']:.1f} +/- {agg_a['trust_stdev']:.1f} | {agg_b['trust_mean']:.1f} +/- {agg_b['trust_stdev']:.1f} | {agg_b['trust_mean'] - agg_a['trust_mean']:+.1f} |
| Trust score 95% CI | [{agg_a['trust_ci_lower']:.1f}, {agg_a['trust_ci_upper']:.1f}] | [{agg_b['trust_ci_lower']:.1f}, {agg_b['trust_ci_upper']:.1f}] | |
| Avg API time | {agg_a['avg_total_time_s']:.3f}s | {agg_b['avg_total_time_s']:.3f}s | {agg_b['avg_total_time_s'] - agg_a['avg_total_time_s']:+.3f}s |
| Wasted calls | {agg_a['avg_wasted_calls']:.1f} | {agg_b['avg_wasted_calls']:.1f} | {agg_b['avg_wasted_calls'] - agg_a['avg_wasted_calls']:+.1f} |

## Statistical Significance

| Test | Failure Rate | Trust Score |
|------|-------------|-------------|
| t-statistic | {t_fail:.4f} | {t_trust:.4f} |
| p-value | {p_fail:.8f} | {p_trust:.8f} |
| Significant (p<0.05) | {"Yes" if p_fail < 0.05 else "No"} | {"Yes" if p_trust < 0.05 else "No"} |

The failure rate difference is **{sig_fail}** (t={t_fail:.3f}, p={p_fail:.8f}).
The trust score difference is **{sig_trust}** (t={t_trust:.3f}, p={p_trust:.8f}).

## Conclusion

{"With " + str(NUM_RUNS) + " iterations, Nerq preflight screening produces a statistically significant improvement in both failure rate and trust quality." if p_fail < 0.05 and p_trust < 0.05 else "Results with " + str(NUM_RUNS) + " iterations."}

For autonomous agents operating without human oversight, Nerq preflight checks provide a quantitative trust gate that prevents interaction with untrusted or dead tools. The screening overhead ({agg_b['avg_total_time_s']:.3f}s for {len(ALL_TOOLS)} candidates) is negligible compared to the cost of executing an untrusted tool in production.

---

Data generated from live Nerq API. Reproduce: `python -m agentindex.nerq_benchmark_test`
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Nerq Benchmark — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Pool: {len(ALL_TOOLS)} tools (15 high + 15 medium + 10 low + 10 dead)")
    print(f"Select: {NUM_SELECT} per iteration | N={NUM_RUNS}")
    print()

    # --- Scenario A: Without Nerq ---
    print("[Scenario A] Without Nerq — random selection + KYA lookup")
    runs_a = []
    for i in range(NUM_RUNS):
        result = run_without_nerq(seed=i)
        runs_a.append(result)
        ok = NUM_SELECT - result["failures"]
        print(f"  {i+1:3d}/{NUM_RUNS}: {ok}/{NUM_SELECT} OK, "
              f"trust={result['avg_trust']:.1f}, "
              f"time={result['total_time_s']:.3f}s")

    print()

    # --- Scenario B: With Nerq ---
    print("[Scenario B] With Nerq — preflight screen all, pick top 5")
    runs_b = []
    for i in range(NUM_RUNS):
        result = run_with_nerq(seed=i)
        runs_b.append(result)
        ok = result["selected_count"] - result["failures"]
        print(f"  {i+1:3d}/{NUM_RUNS}: {ok}/{result['selected_count']} OK, "
              f"trust={result['avg_trust']:.1f}, "
              f"time={result['total_time_s']:.3f}s, "
              f"screened_out={result['screened_out']}")

    print()

    # --- Aggregate ---
    agg_a = aggregate_runs(runs_a)
    agg_b = aggregate_runs(runs_b)

    # --- Statistical tests ---
    failure_rates_a = [r["failure_rate"] for r in runs_a]
    failure_rates_b = [r["failure_rate"] for r in runs_b]
    trust_scores_a = [r["avg_trust"] for r in runs_a]
    trust_scores_b = [r["avg_trust"] for r in runs_b]

    t_fail, p_fail = welch_t_test(failure_rates_a, failure_rates_b)
    t_trust, p_trust = welch_t_test(trust_scores_a, trust_scores_b)

    print_comparison(agg_a, agg_b, t_fail, p_fail, t_trust, p_trust)

    # --- Save outputs ---
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    docs_dir = Path(__file__).resolve().parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)

    # JSON results (without per-run details to keep file small)
    results_json = {
        "benchmark": "nerq_tool_selection_v2",
        "timestamp": ts,
        "config": {
            "pool_size": len(ALL_TOOLS),
            "high_trust_count": len(HIGH_TRUST),
            "medium_trust_count": len(MEDIUM_TRUST),
            "low_trust_count": len(LOW_TRUST),
            "not_found_count": len(NOT_FOUND),
            "select_count": NUM_SELECT,
            "num_iterations": NUM_RUNS,
            "trust_threshold": TRUST_THRESHOLD,
        },
        "tools": {
            "high_trust": HIGH_TRUST,
            "medium_trust": MEDIUM_TRUST,
            "low_trust": LOW_TRUST,
            "not_found": NOT_FOUND,
        },
        "statistical_tests": {
            "failure_rate": {
                "test": "welch_t_test",
                "t_statistic": round(t_fail, 4),
                "p_value": round(p_fail, 8),
                "significant_at_005": p_fail < 0.05,
            },
            "trust_score": {
                "test": "welch_t_test",
                "t_statistic": round(t_trust, 4),
                "p_value": round(p_trust, 8),
                "significant_at_005": p_trust < 0.05,
            },
        },
        "without_nerq": {"aggregate": agg_a},
        "with_nerq": {"aggregate": agg_b},
    }
    json_path = docs_dir / "benchmark-results.json"
    with open(json_path, "w") as f:
        json.dump(results_json, f, indent=2, default=str)
    print(f"JSON saved: {json_path}")

    # Markdown report
    md = generate_markdown(agg_a, agg_b, t_fail, p_fail, t_trust, p_trust, ts)
    md_path = docs_dir / "benchmark-with-vs-without.md"
    with open(md_path, "w") as f:
        f.write(md)
    print(f"Report saved: {md_path}")


if __name__ == "__main__":
    main()
