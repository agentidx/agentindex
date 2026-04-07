#!/usr/bin/env python3
"""
Apply Trust Score Agent Page Edits to seo_pages.py
Uses line-based replacements to avoid quote nesting issues.

Run: python3 apply_agent_page_edits.py
"""
import shutil, sys

FILE = "/Users/anstudio/agentindex/agentindex/seo_pages.py"

# Backup
shutil.copy2(FILE, FILE + ".bak")
print("Backup created:", FILE + ".bak")

with open(FILE, 'r') as f:
    lines = f.readlines()

original_count = len(lines)
edits = 0

# == EDIT 1a: SQL QUERY - add trust columns to SELECT ==
for i, line in enumerate(lines):
    if "first_indexed, last_crawled, compliance_score, eu_risk_class" in line and i+1 < len(lines) and "FROM agents" in lines[i+1]:
        lines[i] = line.replace(
            "first_indexed, last_crawled, compliance_score, eu_risk_class",
            "first_indexed, last_crawled, compliance_score, eu_risk_class,\n                       trust_score_v2, trust_grade, trust_risk_level, trust_dimensions"
        )
        edits += 1
        print("Edit 1a: Added trust columns to SELECT")
        break

# == EDIT 1b: SQL QUERY - add trust columns to dict zip ==
for i, line in enumerate(lines):
    if "'first_indexed','last_crawled','compliance_score','eu_risk_class'], agent))" in line:
        lines[i] = line.replace(
            "'first_indexed','last_crawled','compliance_score','eu_risk_class'], agent))",
            "'first_indexed','last_crawled','compliance_score','eu_risk_class',\n                         'trust_score_v2','trust_grade','trust_risk_level','trust_dimensions'], agent))"
        )
        edits += 1
        print("Edit 1b: Added trust columns to dict zip")
        break

# == EDIT 5: HELPER FUNCTIONS (before _render_agent_page) ==
helper_code = '''
def _trust_grade_color(grade):
    """Return color for trust grade badge."""
    return {
        'A+': '#22c55e', 'A': '#22c55e',
        'B': '#3b82f6',
        'C': '#eab308',
        'D': '#f97316',
        'E': '#ef4444', 'F': '#ef4444',
    }.get(grade, '#6b7280')

def _trust_display(a):
    """Return 'A+ (87/100)' or 'pending' for inline text."""
    ts = a.get('trust_score_v2')
    tg = a.get('trust_grade')
    if ts is not None and tg:
        return f"{tg} ({ts:.0f}/100)"
    return "pending assessment"

def _render_trust_score_block(a):
    """Render the Trust Score visual block for agent pages."""
    ts = a.get('trust_score_v2')
    tg = a.get('trust_grade', '')
    tr = a.get('trust_risk_level', '')
    dims = a.get('trust_dimensions') or {}
    if isinstance(dims, str):
        import json as _j
        try: dims = _j.loads(dims)
        except: dims = {}

    if ts is None:
        return '<div class="section" style="border-left:4px solid #6b7280"><p style="color:#9898b0">Trust Score: pending assessment</p></div>'

    color = _trust_grade_color(tg)
    pct = max(0, min(100, ts))

    dim_labels = [
        ('Security', dims.get('security', 0), '&#x1f6e1;'),
        ('Compliance', dims.get('compliance', 0), '&#x2696;'),
        ('Maintenance', dims.get('maintenance', 0), '&#x1f527;'),
        ('Popularity', dims.get('popularity', 0), '&#x2b50;'),
        ('Ecosystem', dims.get('ecosystem', 0), '&#x1f517;'),
    ]

    dim_html = ''
    for label, val, icon in dim_labels:
        v = int(val) if val else 0
        bar_color = '#22c55e' if v >= 70 else '#3b82f6' if v >= 50 else '#eab308' if v >= 30 else '#ef4444'
        dim_html += f'<div style="display:flex;align-items:center;gap:8px;margin:6px 0">'
        dim_html += f'<span style="width:110px;font-size:13px;color:#9898b0">{icon} {label}</span>'
        dim_html += f'<div style="flex:1;height:8px;background:#1a1a26;border-radius:4px;overflow:hidden">'
        dim_html += f'<div style="width:{v}%;height:100%;background:{bar_color};border-radius:4px"></div></div>'
        dim_html += f'<span style="width:32px;font-size:13px;color:#e8e8f0;text-align:right;font-weight:600">{v}</span></div>'

    risk_label = {'low': 'Low Risk', 'medium': 'Medium Risk', 'high': 'High Risk', 'critical': 'Critical'}.get(tr, tr)
    risk_color = {'low': '#22c55e', 'medium': '#eab308', 'high': '#f97316', 'critical': '#ef4444'}.get(tr, '#6b7280')

    return (
        f'<div class="section" style="border-left:4px solid {color}">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;margin-bottom:16px">'
        f'<div>'
        f'<div style="font-size:13px;color:#9898b0;margin-bottom:4px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em">Nerq Trust Score</div>'
        f'<div style="display:flex;align-items:baseline;gap:10px">'
        f'<span style="font-size:42px;font-weight:800;color:{color};line-height:1">{tg}</span>'
        f'<span style="font-size:22px;color:#e8e8f0;font-weight:600">{ts:.0f}<span style="font-size:14px;color:#71717a">/100</span></span>'
        f'</div></div>'
        f'<div style="text-align:right">'
        f'<span style="background:{risk_color}22;color:{risk_color};padding:6px 14px;border-radius:20px;font-size:13px;font-weight:600;border:1px solid {risk_color}44">{risk_label}</span>'
        f'</div></div>'
        f'<div style="background:#0a0a0f;border-radius:8px;padding:16px">{dim_html}</div>'
        f'<div style="margin-top:12px;font-size:12px;color:#71717a">'
        f'Score based on 5 dimensions: security practices, multi-jurisdiction compliance, maintenance activity, community trust, and ecosystem compatibility. '
        f'<a href="/methodology" style="color:#4af0c0">Learn more</a></div></div>'
    )

'''

for i, line in enumerate(lines):
    if line.strip() == "def _render_agent_page(a, jurisdictions, related):":
        lines[i] = helper_code + line
        edits += 1
        print("Edit 5: Helper functions inserted before _render_agent_page")
        break

# == EDIT 2: Trust Score block before Agent Header ==
for i, line in enumerate(lines):
    if "<!-- Agent Header -->" in line:
        lines[i] = "<!-- Trust Score -->\n{_render_trust_score_block(a)}\n\n" + line
        edits += 1
        print("Edit 2: Trust Score block added before Agent Header")
        break

# == EDIT 3: AI-Citable Summary ==
for i, line in enumerate(lines):
    if 'rated <strong>{compliance_score_text}</strong> on the Nerq Weighted Global Compliance Score' in line:
        p_start = i - 1
        while p_start > 0 and '<p style="font-size:16px' not in lines[p_start]:
            p_start -= 1
        p_end = i + 1
        while p_end < len(lines) and '</p>' not in lines[p_end]:
            p_end += 1

        new_para = [
            '<p style="font-size:16px;line-height:1.7;color:#e8e8f0"><strong>{name}</strong> is a {agent_type} \n',
            "{f'with {stars:,} stars ' if stars else ''}sourced from {source}, \n",
            'with a <strong>Nerq Trust Score of {_trust_display(a)}</strong> \n',
            'and a compliance score of <strong>{compliance_score_text}</strong> across {total_j} jurisdictions. \n',
            'It is classified as <strong>{risk_class.upper()}</strong> risk, \n',
            'with {high_count} high-risk classification{"s" if high_count != 1 else ""} \n',
            'and {minimal_count} minimal-risk classification{"s" if minimal_count != 1 else ""}. \n',
            "Assessed by <a href=\"https://nerq.ai\">Nerq</a>, the world's largest AI agent trust database \n",
            'covering {_agent_count_text()} AI agents across 52 global jurisdictions.</p>\n',
        ]
        lines[p_start:p_end+1] = new_para
        edits += 1
        print("Edit 3: AI-Citable Summary updated with Trust Score")
        break

# == EDIT 4: Schema.org additionalProperty ==
for i, line in enumerate(lines):
    if 'schema["additionalProperty"] = [' in line:
        end = i + 1
        while end < len(lines) and '    ]' not in lines[end]:
            end += 1

        new_schema = [
            "    # Trust Score dimensions\n",
            "    trust_dims = a.get('trust_dimensions') or {}\n",
            "    if isinstance(trust_dims, str):\n",
            "        try:\n",
            "            trust_dims = json.loads(trust_dims)\n",
            "        except:\n",
            "            trust_dims = {}\n",
            "\n",
            '    schema["additionalProperty"] = [\n',
            "        {\"@type\": \"PropertyValue\", \"name\": \"trustScore\", \"value\": a.get('trust_score_v2') if a.get('trust_score_v2') is not None else \"pending\"},\n",
            "        {\"@type\": \"PropertyValue\", \"name\": \"trustGrade\", \"value\": a.get('trust_grade', 'pending')},\n",
            "        {\"@type\": \"PropertyValue\", \"name\": \"securityScore\", \"value\": trust_dims.get('security', 'pending')},\n",
            '        {"@type": "PropertyValue", "name": "complianceScore", "value": compliance_score if compliance_score is not None else "pending"},\n',
            "        {\"@type\": \"PropertyValue\", \"name\": \"maintenanceScore\", \"value\": trust_dims.get('maintenance', 'pending')},\n",
            "        {\"@type\": \"PropertyValue\", \"name\": \"popularityScore\", \"value\": trust_dims.get('popularity', 'pending')},\n",
            "        {\"@type\": \"PropertyValue\", \"name\": \"ecosystemScore\", \"value\": trust_dims.get('ecosystem', 'pending')},\n",
            '        {"@type": "PropertyValue", "name": "riskClass", "value": risk_class},\n',
            '        {"@type": "PropertyValue", "name": "jurisdictionsAssessed", "value": len(jurisdictions)},\n',
            '        {"@type": "PropertyValue", "name": "highRiskJurisdictions", "value": high_count},\n',
            '        {"@type": "PropertyValue", "name": "dataSource", "value": "Nerq.ai"},\n',
            '        {"@type": "PropertyValue", "name": "lastAssessed", "value": _dt.utcnow().strftime("%Y-%m-%d")}\n',
            "    ]\n",
        ]
        lines[i:end+1] = new_schema
        edits += 1
        print("Edit 4: Schema.org structured data updated")
        break

# == EDIT 6: FAQ "safe to use" answer ==
for i, line in enumerate(lines):
    if "According to Nerq's assessment across {total_j} jurisdictions" in line:
        lines[i] = line.replace(
            "According to Nerq's assessment across {total_j} jurisdictions, {name} is classified as {risk_class} risk with a compliance score of {compliance_score_text}.",
            "According to Nerq's assessment, {name} has a Trust Score of {_trust_display(a)} based on security, compliance, maintenance, popularity, and ecosystem analysis. It is classified as {risk_class} risk with a compliance score of {compliance_score_text} across {total_j} jurisdictions."
        )
        edits += 1
        print("Edit 6: FAQ answer updated with Trust Score")
        break

# == SAVE ==
print(f"\nEdits applied: {edits}/7 (1a+1b+2+3+4+5+6)")

if edits >= 6:
    with open(FILE, 'w') as f:
        f.writelines(lines)
    new_count = len(lines)
    print(f"File saved! {original_count} -> {new_count} lines")
    print(f"Backup at: {FILE}.bak")
    print(f"\nTo undo: cp '{FILE}.bak' '{FILE}'")
else:
    with open(FILE + ".partial", 'w') as f:
        f.writelines(lines)
    print(f"Only {edits} edits matched. File NOT saved.")
    print(f"Partial result at: {FILE}.partial")
