"""
Benchmark Report Page — nerq.ai/report/benchmark
Shows "With Nerq vs Without Nerq" comparison with statistical significance.
Reads results from docs/benchmark-results.json.
"""

import json
import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from agentindex.nerq_design import nerq_page

router_benchmark = APIRouter(tags=["report"])

_RESULTS_PATH = os.path.join(
    os.path.expanduser("~"), "agentindex", "docs", "benchmark-results.json"
)


def _load_results() -> dict | None:
    try:
        with open(_RESULTS_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _fmt(v, suffix="", decimals=1):
    if v is None:
        return "\u2014"
    return f"{v:.{decimals}f}{suffix}"


@router_benchmark.get("/report/benchmark", response_class=HTMLResponse)
def benchmark_report():
    data = _load_results()

    if not data:
        body = """
<h1>Benchmark: With Nerq vs Without Nerq</h1>
<p class="desc">Benchmark data is being generated. Check back shortly.</p>
<p><a href="/reports">All reports</a></p>
"""
        return nerq_page(
            "Benchmark \u2014 Nerq",
            body,
            description="With Nerq vs Without Nerq benchmark results.",
            canonical="https://nerq.ai/report/benchmark",
        )

    cfg = data.get("config", {})
    wo_raw = data.get("without_nerq", {})
    wi_raw = data.get("with_nerq", {})
    wo = wo_raw.get("aggregate", wo_raw)
    wi = wi_raw.get("aggregate", wi_raw)

    n_iter = cfg.get("num_iterations", cfg.get("num_runs", 100))
    pool_size = cfg.get("pool_size", 50)
    n_high = cfg.get("high_trust_count", 15)
    n_med = cfg.get("medium_trust_count", 15)
    n_low = cfg.get("low_trust_count", 10)
    n_dead = cfg.get("not_found_count", 10)

    # Failure rate
    wo_fr = wo.get("failure_rate_mean", wo.get("avg_failure_rate", 0))
    wi_fr = wi.get("failure_rate_mean", wi.get("avg_failure_rate", 0))
    wo_fr_sd = wo.get("failure_rate_stdev", 0)
    wi_fr_sd = wi.get("failure_rate_stdev", 0)
    wo_fr_ci_lo = wo.get("failure_rate_ci_lower", wo_fr)
    wo_fr_ci_hi = wo.get("failure_rate_ci_upper", wo_fr)
    wi_fr_ci_lo = wi.get("failure_rate_ci_lower", wi_fr)
    wi_fr_ci_hi = wi.get("failure_rate_ci_upper", wi_fr)

    # Trust score
    wo_tr = wo.get("trust_mean", wo.get("avg_trust", 0))
    wi_tr = wi.get("trust_mean", wi.get("avg_trust", 0))
    wo_tr_sd = wo.get("trust_stdev", 0)
    wi_tr_sd = wi.get("trust_stdev", 0)
    wo_tr_ci_lo = wo.get("trust_ci_lower", wo_tr)
    wo_tr_ci_hi = wo.get("trust_ci_upper", wo_tr)
    wi_tr_ci_lo = wi.get("trust_ci_lower", wi_tr)
    wi_tr_ci_hi = wi.get("trust_ci_upper", wi_tr)

    # Statistical tests
    stats = data.get("statistical_tests", {})
    fr_test = stats.get("failure_rate", stats.get("failure_rate_z_test", {}))
    tr_test = stats.get("trust_score", {})
    fr_p = fr_test.get("p_value")
    tr_p = tr_test.get("p_value")
    fr_t = fr_test.get("t_statistic", fr_test.get("z_score"))
    tr_t = tr_test.get("t_statistic")
    fr_sig = fr_test.get("significant_at_005", False)
    tr_sig = tr_test.get("significant_at_005", False)

    # Improvement calculations
    improvement_failure = ""
    if wo_fr > 0:
        reduction = ((wo_fr - wi_fr) / wo_fr) * 100
        improvement_failure = f' <span style="color:#059669;font-weight:600">({reduction:.0f}% reduction)</span>'

    improvement_trust = ""
    if wi_tr > wo_tr:
        delta = wi_tr - wo_tr
        improvement_trust = f' <span style="color:#059669;font-weight:600">(+{delta:.1f})</span>'

    # Significance badges
    def sig_badge(is_sig, p_val):
        if p_val is None:
            return '<span style="color:#6b7280">N/A</span>'
        if is_sig:
            return f'<span style="color:#059669;font-weight:600">p={p_val:.6f} (significant)</span>'
        return f'<span style="color:#dc2626">p={p_val:.6f} (not significant)</span>'

    body = f"""
<div class="breadcrumb"><a href="/">nerq</a> &rsaquo; <a href="/reports">reports</a> &rsaquo; benchmark</div>

<h1>With Nerq vs Without Nerq</h1>
<p class="desc" style="margin-bottom:24px">
N={n_iter} iterations per scenario. Pool of {pool_size} agents
({n_high} high-trust + {n_med} medium-trust + {n_low} low-trust + {n_dead} dead/not-found).
Each iteration selects 5 tools.
</p>

<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin:24px 0">
<div style="background:#fef2f2;padding:16px;border:1px solid #fecaca;text-align:center">
<div style="font-size:2rem;font-weight:700;color:#dc2626">{wo_fr:.1f}%</div>
<div style="font-size:13px;color:#6b7280">Failure rate without Nerq</div>
<div style="font-size:11px;color:#9ca3af">&plusmn;{wo_fr_sd:.1f}% SD</div>
</div>
<div style="background:#f0fdf4;padding:16px;border:1px solid #bbf7d0;text-align:center">
<div style="font-size:2rem;font-weight:700;color:#059669">{wi_fr:.1f}%</div>
<div style="font-size:13px;color:#6b7280">Failure rate with Nerq</div>
<div style="font-size:11px;color:#9ca3af">&plusmn;{wi_fr_sd:.1f}% SD</div>
</div>
<div style="background:#f0f9ff;padding:16px;border:1px solid #bae6fd;text-align:center">
<div style="font-size:2rem;font-weight:700;color:#0284c7">{wi_tr:.1f}</div>
<div style="font-size:13px;color:#6b7280">Avg trust (with Nerq)</div>
<div style="font-size:11px;color:#9ca3af">&plusmn;{wi_tr_sd:.1f} SD</div>
</div>
</div>

<h2>Results (N={n_iter} iterations)</h2>
<table>
<thead>
<tr><th>Metric</th><th>Without Nerq</th><th>With Nerq</th><th>Improvement</th></tr>
</thead>
<tbody>
<tr>
<td>Failure rate (mean &plusmn; SD)</td>
<td style="color:#dc2626;font-weight:600">{wo_fr:.1f} &plusmn; {wo_fr_sd:.1f}%</td>
<td style="color:#059669;font-weight:600">{wi_fr:.1f} &plusmn; {wi_fr_sd:.1f}%</td>
<td>{improvement_failure or '\u2014'}</td>
</tr>
<tr>
<td>Failure rate 95% CI</td>
<td>[{wo_fr_ci_lo:.1f}, {wo_fr_ci_hi:.1f}]%</td>
<td>[{wi_fr_ci_lo:.1f}, {wi_fr_ci_hi:.1f}]%</td>
<td>\u2014</td>
</tr>
<tr>
<td>Avg trust (mean &plusmn; SD)</td>
<td>{wo_tr:.1f} &plusmn; {wo_tr_sd:.1f}</td>
<td>{wi_tr:.1f} &plusmn; {wi_tr_sd:.1f}</td>
<td>{improvement_trust or '\u2014'}</td>
</tr>
<tr>
<td>Trust score 95% CI</td>
<td>[{wo_tr_ci_lo:.1f}, {wo_tr_ci_hi:.1f}]</td>
<td>[{wi_tr_ci_lo:.1f}, {wi_tr_ci_hi:.1f}]</td>
<td>\u2014</td>
</tr>
<tr>
<td>Wasted API calls</td>
<td>{_fmt(wo.get('avg_wasted_calls'))}</td>
<td>{_fmt(wi.get('avg_wasted_calls'))}</td>
<td>\u2014</td>
</tr>
<tr>
<td>Total API time</td>
<td>{_fmt((wo.get('avg_total_time_s') or 0) * 1000, 'ms', 0)}</td>
<td>{_fmt((wi.get('avg_total_time_s') or 0) * 1000, 'ms', 0)}</td>
<td>\u2014</td>
</tr>
</tbody>
</table>

<h2>Statistical Significance</h2>
<table>
<thead>
<tr><th>Test</th><th>Failure Rate</th><th>Trust Score</th></tr>
</thead>
<tbody>
<tr>
<td>Test type</td>
<td>Welch's t-test</td>
<td>Welch's t-test</td>
</tr>
<tr>
<td>t-statistic</td>
<td>{_fmt(fr_t, decimals=4) if fr_t else '\u2014'}</td>
<td>{_fmt(tr_t, decimals=4) if tr_t else '\u2014'}</td>
</tr>
<tr>
<td>p-value</td>
<td>{sig_badge(fr_sig, fr_p)}</td>
<td>{sig_badge(tr_sig, tr_p)}</td>
</tr>
<tr>
<td>Significant at 95%</td>
<td style="font-weight:600;color:{'#059669' if fr_sig else '#dc2626'}">{'Yes' if fr_sig else 'No'}</td>
<td style="font-weight:600;color:{'#059669' if tr_sig else '#dc2626'}">{'Yes' if tr_sig else 'No'}</td>
</tr>
</tbody>
</table>

<h2>Methodology</h2>
<p style="font-size:14px;line-height:1.7">
The pool contains {pool_size} real agents from the Nerq index:
{n_high} with trust &gt; 70,
{n_med} with trust 40&ndash;69,
{n_low} with trust &lt; 40,
and {n_dead} names that don&rsquo;t exist in the index.
Each iteration randomly selects 5 tools. This is repeated {n_iter} times per scenario.
</p>
<p style="font-size:14px;line-height:1.7">
<strong>Without Nerq:</strong> Randomly pick 5 tools, call <code>/v1/agent/kya/{{name}}</code> for each.
Tools with trust &lt; 40 or not found count as failures.
</p>
<p style="font-size:14px;line-height:1.7">
<strong>With Nerq:</strong> Call <code>/v1/preflight</code> on all {pool_size} candidates.
Filter to <code>PROCEED</code> recommendations. Sort by trust descending. Pick top 5.
</p>
<p style="font-size:14px;line-height:1.7">
Statistical significance is assessed using Welch&rsquo;s two-sample t-test
(unequal variances) with a threshold of p &lt; 0.05.
</p>

<h2>Reproduce</h2>
<pre>python -m agentindex.nerq_benchmark_test</pre>

<p style="font-size:13px;color:#6b7280;margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb">
Data from the <a href="/v1/agent/stats">Nerq index</a>.
<a href="/nerq/docs#preflight">Preflight API</a> &middot;
<a href="/docs/langchain">LangChain integration</a> &middot;
<a href="/reports">All reports</a>
</p>
"""
    return nerq_page(
        "Benchmark: With Nerq vs Without Nerq",
        body,
        description=f"N={n_iter} benchmark comparing agent tool selection with and without Nerq. Statistical significance via Welch's t-test.",
        canonical="https://nerq.ai/report/benchmark",
    )
