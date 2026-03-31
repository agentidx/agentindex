#!/usr/bin/env python3
"""
ZARQ Vitality Score Rankings Page
==================================
Mounts /vitality on zarq.ai — ranks all scored tokens by Vitality Score.

Usage:
  from agentindex.crypto.zarq_vitality_page import mount_vitality_page
  mount_vitality_page(app)
"""

import json
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# Reuse standard ZARQ design components
from agentindex.crypto.zarq_risk_pages import ZARQ_CSS, ZARQ_NAV, ZARQ_FOOTER

_VITALITY_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "vitality_cache.json"
)

# In-memory cache with TTL
_cache = {"html": None, "ts": 0}
_CACHE_TTL = 300  # 5 minutes


def mount_vitality_page(app: FastAPI):
    """Mount the /vitality ranking page."""

    @app.get("/vitality", response_class=HTMLResponse)
    async def vitality_rankings_page():
        import time
        now = time.time()
        if _cache["html"] and (now - _cache["ts"]) < _CACHE_TTL:
            return HTMLResponse(content=_cache["html"])

        html = _render_vitality_page()
        _cache["html"] = html
        _cache["ts"] = now
        return HTMLResponse(content=html)

    # /vitality/methodology is mounted via crypto_seo_pages.mount_vitality_methodology_page


def _load_vitality_data():
    """Load vitality scores from JSON cache file."""
    try:
        with open(_VITALITY_CACHE_PATH, "r") as f:
            data = json.load(f)
        scores = data.get("scores", [])
        # Sort by vitality_score descending
        scores.sort(key=lambda x: x.get("vitality_score") or 0, reverse=True)
        return scores
    except Exception:
        return []


def _render_vitality_page():
    scores = _load_vitality_data()
    total = len(scores)

    # Build table rows
    rows_html = []
    for rank, s in enumerate(scores, 1):
        token_id = s.get("token_id", "")
        name = s.get("name") or token_id.replace("-", " ").title()
        symbol = (s.get("symbol") or "").upper()
        vs = s.get("vitality_score") or 0
        grade = s.get("vitality_grade") or "?"
        ts = s.get("trust_score")
        confidence = s.get("confidence") or 0

        grade_color = {
            "S": "#7c3aed", "A": "#16a34a", "B": "#2563eb",
            "C": "#ca8a04", "D": "#ea580c", "F": "#dc2626",
        }.get(grade, "#78716c")

        trust_display = f"{ts:.1f}" if ts is not None else "&mdash;"

        rows_html.append(
            f'<tr class="vrow" data-grade="{grade}">'
            f'<td style="font-family:var(--mono);color:var(--gray-500);text-align:right;padding-right:16px">{rank}</td>'
            f'<td><a href="/token/{token_id}" style="color:var(--gray-800);text-decoration:none;font-weight:500">{name}</a></td>'
            f'<td style="font-family:var(--mono);color:var(--gray-500);font-size:13px">{symbol}</td>'
            f'<td style="font-family:var(--mono);font-weight:600;color:var(--black)">{vs:.1f}</td>'
            f'<td><span style="display:inline-block;padding:2px 10px;border-radius:4px;font-family:var(--mono);font-size:12px;font-weight:600;color:#fff;background:{grade_color}">{grade}</span></td>'
            f'<td style="font-family:var(--mono);color:var(--gray-600)">{trust_display}</td>'
            f'<td style="font-family:var(--mono);color:var(--gray-500);font-size:13px">{confidence}%</td>'
            f'</tr>'
        )

    table_rows = "\n".join(rows_html)

    # Grade distribution for subtitle
    grade_counts = {}
    for s in scores:
        g = s.get("vitality_grade") or "?"
        grade_counts[g] = grade_counts.get(g, 0) + 1

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Best Crypto to Invest In 2026 — Ranked by Ecosystem Quality | ZARQ</title>
<meta name="description" content="Which crypto has the strongest ecosystem? ZARQ Vitality Score ranks {total:,} tokens by ecosystem quality across five dimensions: ecosystem gravity, capital commitment, coordination efficiency, stress resilience, and organic momentum. Data-driven, updated daily.">
<meta name="robots" content="index, follow">
<link rel="canonical" href="https://zarq.ai/vitality">
<meta property="og:title" content="Best Crypto to Invest In 2026 — Ranked by Ecosystem Quality">
<meta property="og:description" content="Which crypto has the strongest ecosystem? {total:,} tokens ranked by ecosystem quality. Five-dimensional vitality analysis updated daily.">
<meta property="og:url" content="https://zarq.ai/vitality">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;500;600&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
{ZARQ_CSS}
<style>
.vitality-hero {{
  padding: 140px 40px 60px;
  max-width: var(--wide);
  margin: 0 auto;
}}
.vitality-hero h1 {{
  font-family: var(--serif);
  font-size: 2.8rem;
  font-weight: 400;
  color: var(--black);
  margin-bottom: 12px;
}}
.vitality-hero .subtitle {{
  font-family: var(--sans);
  font-size: 1.05rem;
  color: var(--gray-500);
  margin-bottom: 32px;
}}
.filter-bar {{
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 32px;
}}
.filter-btn {{
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.05em;
  padding: 6px 16px;
  border: 1px solid var(--gray-200);
  background: var(--white);
  color: var(--gray-600);
  cursor: pointer;
  transition: all 0.2s;
}}
.filter-btn:hover {{
  border-color: var(--warm);
  color: var(--black);
}}
.filter-btn.active {{
  background: var(--warm);
  color: var(--white);
  border-color: var(--warm);
}}
.vitality-table-wrap {{
  max-width: var(--wide);
  margin: 0 auto;
  padding: 0 40px 80px;
  overflow-x: auto;
}}
table {{
  width: 100%;
  border-collapse: collapse;
}}
thead th {{
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gray-500);
  text-align: left;
  padding: 12px 8px;
  border-bottom: 2px solid var(--gray-200);
  white-space: nowrap;
}}
thead th:first-child {{
  text-align: right;
  padding-right: 16px;
}}
tbody tr {{
  border-bottom: 1px solid var(--gray-100);
  transition: background 0.15s;
}}
tbody tr:hover {{
  background: var(--warm-light);
}}
tbody td {{
  padding: 10px 8px;
  font-size: 14px;
}}
.count-badge {{
  font-family: var(--mono);
  font-size: 12px;
  color: var(--warm);
  background: var(--warm-light);
  padding: 2px 8px;
  border-radius: 4px;
  margin-left: 8px;
}}
@media (max-width: 768px) {{
  .vitality-hero {{ padding: 100px 20px 40px; }}
  .vitality-hero h1 {{ font-size: 1.8rem; }}
  .vitality-table-wrap {{ padding: 0 12px 60px; }}
  tbody td, thead th {{ font-size: 12px; padding: 8px 4px; }}
}}
</style>
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "WebPage",
  "name": "Best Crypto to Invest In 2026 — Ranked by Ecosystem Quality",
  "description": "Ecosystem health scores for {total:,} crypto tokens across five dimensions.",
  "url": "https://zarq.ai/vitality",
  "publisher": {{
    "@type": "Organization",
    "name": "ZARQ",
    "url": "https://zarq.ai"
  }}
}}
</script>
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {{
      "@type": "Question",
      "name": "Which crypto has the strongest ecosystem?",
      "acceptedAnswer": {{
        "@type": "Answer",
        "text": "According to ZARQ's Vitality Score, Ethereum currently has the strongest ecosystem among major L1 chains, scoring highest on Ecosystem Gravity (protocol density, TVL, stablecoin presence) and Coordination Efficiency (category diversity, audit coverage). Rankings are updated daily across {total:,} tokens."
      }}
    }},
    {{
      "@type": "Question",
      "name": "What is the best crypto to buy based on fundamentals?",
      "acceptedAnswer": {{
        "@type": "Answer",
        "text": "The ZARQ Vitality Score measures crypto ecosystem fundamentals across 5 dimensions: Ecosystem Gravity, Capital Commitment, Coordination Efficiency, Stress Resilience, and Organic Momentum. Tokens scoring Grade A or S have the strongest ecosystems. Backtested across 3 time windows, high-Vitality tokens showed +44% less drawdown during the Jul 2025 crash (p=0.0008). This is not financial advice."
      }}
    }},
    {{
      "@type": "Question",
      "name": "How to evaluate crypto ecosystem quality?",
      "acceptedAnswer": {{
        "@type": "Answer",
        "text": "ZARQ evaluates crypto ecosystem quality through the Vitality Score — a composite of 5 weighted dimensions: Ecosystem Gravity (20%, protocol density and TVL), Capital Commitment (20%, TVL retention and yield density), Coordination Efficiency (15%, category diversity and audit rates), Stress Resilience (25%, NDD stability and crash probability), and Organic Momentum (20%, growth trends). Each dimension uses on-chain and market data, not opinion. See zarq.ai/vitality/methodology for full details."
      }}
    }}
  ]
}}
</script>
</head>
<body>
{ZARQ_NAV}

<section class="vitality-hero">
  <h1>Best Crypto to Invest In 2026 — Ranked by Ecosystem Quality</h1>
  <p class="subtitle">Which tokens are most crash-resistant? {total:,} tokens ranked by backtested Vitality Score.</p>
  <div style="background:linear-gradient(135deg,rgba(194,149,107,0.08),rgba(194,149,107,0.15));border:1px solid rgba(194,149,107,0.3);padding:16px 24px;margin-bottom:28px;display:flex;align-items:center;gap:16px;flex-wrap:wrap">
    <span style="font-family:var(--mono);font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:var(--warm);background:rgba(194,149,107,0.15);padding:4px 10px;white-space:nowrap">Backtested</span>
    <span style="font-family:var(--sans);font-size:14px;color:var(--gray-700)">High-Vitality tokens lost <strong>44% less</strong> in the 2025&ndash;2026 crash (p&nbsp;&lt;&nbsp;0.001). <a href="/vitality/backtest" style="color:var(--warm)">See full results&nbsp;&rarr;</a></span>
  </div>
  <div class="filter-bar">
    <button class="filter-btn active" data-grade="all" onclick="filterGrade('all', this)">All<span class="count-badge">{total:,}</span></button>
    <button class="filter-btn" data-grade="S" onclick="filterGrade('S', this)" style="--badge-bg:#7c3aed">S<span class="count-badge">{grade_counts.get("S", 0):,}</span></button>
    <button class="filter-btn" data-grade="A" onclick="filterGrade('A', this)">A<span class="count-badge">{grade_counts.get("A", 0):,}</span></button>
    <button class="filter-btn" data-grade="B" onclick="filterGrade('B', this)">B<span class="count-badge">{grade_counts.get("B", 0):,}</span></button>
    <button class="filter-btn" data-grade="C" onclick="filterGrade('C', this)">C<span class="count-badge">{grade_counts.get("C", 0):,}</span></button>
    <button class="filter-btn" data-grade="D" onclick="filterGrade('D', this)">D<span class="count-badge">{grade_counts.get("D", 0):,}</span></button>
    <button class="filter-btn" data-grade="F" onclick="filterGrade('F', this)">F<span class="count-badge">{grade_counts.get("F", 0):,}</span></button>
  </div>
</section>

<div class="vitality-table-wrap">
<table>
<thead>
<tr>
  <th>Rank</th>
  <th>Token</th>
  <th>Symbol</th>
  <th>Vitality Score</th>
  <th>Grade</th>
  <th>Trust Score</th>
  <th>Confidence</th>
</tr>
</thead>
<tbody id="vtable">
{table_rows}
</tbody>
</table>
</div>

{ZARQ_FOOTER}

<script>
function filterGrade(grade, btn) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const rows = document.querySelectorAll('#vtable .vrow');
  let visibleRank = 0;
  rows.forEach(row => {{
    if (grade === 'all' || row.dataset.grade === grade) {{
      row.style.display = '';
      visibleRank++;
      row.children[0].textContent = visibleRank;
    }} else {{
      row.style.display = 'none';
    }}
  }});
}}
</script>
</body>
</html>"""
