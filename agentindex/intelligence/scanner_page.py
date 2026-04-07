"""
Scanner landing page — /scan-project
Paste deps or enter a GitHub repo URL. Free scan, no signup.
"""

from fastapi import Request
from fastapi.responses import HTMLResponse

from agentindex.nerq_design import nerq_page


def mount_scanner_page(app):
    """Mount the scanner landing page on the FastAPI app."""

    @app.get("/scan-project", response_class=HTMLResponse)
    async def scanner_page(request: Request):
        body = _build_page()
        return HTMLResponse(
            nerq_page(
                title="AI Project Scanner — nerq",
                body=body,
                description="Paste your requirements.txt, package.json, or repo URL. Free AI project trust scan, no signup.",
                canonical="https://nerq.ai/scan-project",
            )
        )


SCANNER_JS = """
<script>
(function(){
  const resultsDiv = document.getElementById('scan-results');
  const statsDiv = document.getElementById('scan-stats');

  // ── Grade colors ──
  function gradeClass(grade) {
    if (!grade) return 'pill-gray';
    const g = grade.toUpperCase();
    if (g.startsWith('A')) return 'pill-green';
    if (g.startsWith('B')) return 'pill-yellow';
    return 'pill-red';
  }

  function scoreColor(score) {
    if (score == null) return '#6b7280';
    if (score >= 70) return '#065f46';
    if (score >= 40) return '#92400e';
    return '#991b1b';
  }

  function scoreBg(score) {
    if (score == null) return '#f9fafb';
    if (score >= 70) return '#ecfdf5';
    if (score >= 40) return '#fffbeb';
    return '#fef2f2';
  }

  // ── Parse deps from textarea ──
  function parseDeps(text) {
    const lines = text.split(/\\n/).map(l => l.trim()).filter(l => l && !l.startsWith('#') && !l.startsWith('//'));
    const deps = [];

    // Try JSON parse (package.json / pyproject.toml deps)
    try {
      const obj = JSON.parse(text);
      // package.json
      if (obj.dependencies) Object.keys(obj.dependencies).forEach(d => deps.push(d));
      if (obj.devDependencies) Object.keys(obj.devDependencies).forEach(d => deps.push(d));
      if (deps.length > 0) return deps;
    } catch(e) {}

    // requirements.txt style
    for (const line of lines) {
      // skip options like --index-url
      if (line.startsWith('-')) continue;
      // strip version specifiers, extras, comments
      const name = line.split(/[>=<!\\[;#\\s]/)[0].trim();
      if (name) deps.push(name);
    }
    return deps;
  }

  // ── Render results ──
  function renderResults(data) {
    if (!data) { resultsDiv.innerHTML = '<p style="color:#991b1b">No results returned.</p>'; return; }

    let html = '';

    // Project grade
    if (data.project_grade || data.health_grade) {
      const grade = data.project_grade || data.health_grade || '?';
      html += '<div class="card" style="text-align:center;margin:20px 0">';
      html += '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">Project Health Grade</div>';
      html += '<span class="pill ' + gradeClass(grade) + '" style="font-size:2rem;padding:8px 24px">' + grade + '</span>';
      if (data.summary) html += '<p class="desc" style="margin-top:12px">' + data.summary + '</p>';
      html += '</div>';
    }

    // Dependency table
    const deps = data.dependencies || data.packages || data.results || [];
    if (deps.length > 0) {
      html += '<table><thead><tr><th>Package</th><th>Version</th><th>Trust Score</th><th>Grade</th><th>Issues</th></tr></thead><tbody>';
      for (const d of deps) {
        const name = d.name || d.package || d.package_name || '?';
        const version = d.version || d.latest_version || '-';
        const score = d.trust_score != null ? d.trust_score : null;
        const grade = d.grade || d.trust_grade || '-';
        const issues = d.issues || d.warnings || [];
        const issueStr = Array.isArray(issues) ? issues.join(', ') : (issues || '-');

        html += '<tr>';
        html += '<td><code>' + name + '</code></td>';
        html += '<td>' + version + '</td>';
        html += '<td style="color:' + scoreColor(score) + ';background:' + scoreBg(score) + ';font-weight:600;font-family:ui-monospace,monospace">' + (score != null ? score : '-') + '</td>';
        html += '<td><span class="pill ' + gradeClass(grade) + '">' + grade + '</span></td>';
        html += '<td style="font-size:13px;color:#6b7280">' + issueStr + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
    }

    if (!html) html = '<p class="desc">Scan complete. No dependencies found.</p>';
    resultsDiv.innerHTML = html;
  }

  // ── Scan via deps ──
  window.scanDeps = async function() {
    const text = document.getElementById('deps-input').value.trim();
    if (!text) return;
    const deps = parseDeps(text);
    if (deps.length === 0) { resultsDiv.innerHTML = '<p class="desc">No dependencies detected. Check the format.</p>'; return; }

    resultsDiv.innerHTML = '<p style="color:#6b7280">Scanning ' + deps.length + ' dependencies...</p>';
    try {
      const resp = await fetch('/v1/scan-project', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({packages: deps})
      });
      const data = await resp.json();
      renderResults(data);
    } catch(e) {
      resultsDiv.innerHTML = '<p style="color:#991b1b">Scan failed: ' + e.message + '</p>';
    }
  };

  // ── Scan via GitHub repo ──
  window.scanRepo = async function() {
    const raw = document.getElementById('repo-input').value.trim();
    if (!raw) return;

    // Normalize: accept full URL or owner/repo
    let slug = raw;
    const ghMatch = raw.match(/github\\.com\\/([^/]+\\/[^/\\s?#]+)/);
    if (ghMatch) slug = ghMatch[1].replace(/\\.git$/, '');
    // Remove leading slash
    slug = slug.replace(/^\\//, '');

    if (!slug.includes('/')) { resultsDiv.innerHTML = '<p class="desc">Enter a valid repo: owner/repo</p>'; return; }

    resultsDiv.innerHTML = '<p style="color:#6b7280">Looking up ' + slug + '...</p>';

    // Try existing report first
    try {
      const check = await fetch('/report/' + slug + '.json');
      if (check.ok) {
        window.location.href = '/report/' + slug;
        return;
      }
    } catch(e) {}

    // Fall back to scan
    try {
      const resp = await fetch('/v1/scan-project', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({github_repo: slug})
      });
      const data = await resp.json();
      renderResults(data);
    } catch(e) {
      resultsDiv.innerHTML = '<p style="color:#991b1b">Scan failed: ' + e.message + '</p>';
    }
  };

  // ── Load stats ──
  async function loadStats() {
    try {
      const resp = await fetch('/v1/scan-stats');
      if (!resp.ok) return;
      const s = await resp.json();

      let html = '';

      // Stat row
      html += '<div class="stat-row">';
      if (s.total_scanned != null) html += '<div class="stat-item"><div class="num">' + s.total_scanned.toLocaleString() + '</div><div class="label">projects scanned</div></div>';
      if (s.critical_pct != null) html += '<div class="stat-item"><div class="num">' + s.critical_pct + '%</div><div class="label">with critical vulns</div></div>';
      if (s.scanned_this_week != null) html += '<div class="stat-item"><div class="num">' + s.scanned_this_week.toLocaleString() + '</div><div class="label">scanned this week</div></div>';
      html += '</div>';

      // Grade distribution
      if (s.grade_distribution) {
        const grades = s.grade_distribution;
        const total = Object.values(grades).reduce((a,b) => a + b, 0) || 1;
        html += '<div style="margin:16px 0"><div style="font-size:13px;color:#6b7280;margin-bottom:6px">Grade distribution</div>';
        html += '<div style="display:flex;height:24px;overflow:hidden">';
        const colors = {A:'#065f46',B:'#92400e',C:'#991b1b',D:'#7f1d1d',F:'#450a0a'};
        const bgs = {A:'#ecfdf5',B:'#fffbeb',C:'#fef2f2',D:'#fef2f2',F:'#fef2f2'};
        for (const [g, count] of Object.entries(grades)) {
          const pct = ((count / total) * 100).toFixed(1);
          if (pct > 0) {
            html += '<div style="width:' + pct + '%;background:' + (bgs[g[0]] || '#f5f5f5') + ';color:' + (colors[g[0]] || '#6b7280') + ';display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;border-right:1px solid #fff">' + g + ' ' + pct + '%</div>';
          }
        }
        html += '</div></div>';
      }

      // Recent scans
      if (s.recent_scans && s.recent_scans.length > 0) {
        html += '<div style="margin-top:20px"><h3>Recent scans</h3><table><thead><tr><th>Repo</th><th>Grade</th><th>Trust Score</th></tr></thead><tbody>';
        for (const r of s.recent_scans.slice(0, 10)) {
          const name = r.name || r.repo || '?';
          const grade = r.grade || '-';
          const score = r.trust_score != null ? r.trust_score : '-';
          html += '<tr><td><a href="/report/' + name + '"><code>' + name + '</code></a></td><td><span class="pill ' + gradeClass(grade) + '">' + grade + '</span></td><td>' + score + '</td></tr>';
        }
        html += '</tbody></table></div>';
      }

      // Top healthiest
      if (s.top_healthy && s.top_healthy.length > 0) {
        html += '<div style="margin-top:20px"><h3>Top healthiest projects</h3>';
        for (const r of s.top_healthy.slice(0, 5)) {
          const name = r.name || r.repo || '?';
          const grade = r.grade || 'A';
          html += '<div style="display:inline-block;margin:4px 8px 4px 0"><a href="/report/' + name + '"><span class="pill pill-green">' + name + ' &mdash; ' + grade + '</span></a></div>';
        }
        html += '</div>';
      }

      statsDiv.innerHTML = html;
    } catch(e) {
      // Stats are optional, fail silently
    }
  }

  // Enter key support
  document.getElementById('deps-input').addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && e.ctrlKey) window.scanDeps();
  });
  document.getElementById('repo-input').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') window.scanRepo();
  });

  loadStats();
})();
</script>
"""


def _build_page() -> str:
    return f"""
<h1>Is your AI project safe?</h1>
<p class="desc">Paste your requirements.txt, package.json, or repo URL. Free scan, no signup.</p>

<div class="card" style="margin-top:20px">
  <h3 style="margin:0 0 8px">Option 1 &mdash; Paste dependencies</h3>
  <p class="desc" style="margin:0 0 8px">requirements.txt, package.json, or pyproject.toml contents</p>
  <textarea id="deps-input" style="width:100%;height:200px;font-family:ui-monospace,'SF Mono','Cascadia Mono',monospace;font-size:13px;padding:12px;border:1px solid #e5e7eb;resize:vertical;outline:none;line-height:1.5" placeholder="langchain==0.2.0
openai>=1.30.0
chromadb
fastapi
pydantic-ai
mcp"></textarea>
  <div style="margin-top:8px;display:flex;justify-content:flex-end">
    <button onclick="scanDeps()" style="padding:10px 32px;background:#0d9488;color:#fff;border:none;font-size:14px;font-weight:600;cursor:pointer;font-family:system-ui,-apple-system,sans-serif">SCAN</button>
  </div>
</div>

<div class="card">
  <h3 style="margin:0 0 8px">Option 2 &mdash; GitHub repo</h3>
  <p class="desc" style="margin:0 0 8px">Enter a repo slug or full URL</p>
  <div class="search-box">
    <input id="repo-input" type="text" placeholder="langchain-ai/langchain" />
    <button onclick="scanRepo()">SCAN</button>
  </div>
</div>

<div id="scan-results" style="margin-top:20px"></div>

<div id="scan-stats" style="margin-top:40px;border-top:1px solid #e5e7eb;padding-top:20px"></div>

{SCANNER_JS}
"""
