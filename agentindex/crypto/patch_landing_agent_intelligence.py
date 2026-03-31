#!/usr/bin/env python3
"""
Uppdaterar zarq_landing.html med:
1. Agent Intelligence live-box (efter ALERT_PROOF_BOX-sektionen)
2. Capability #8: Agent Intelligence
3. Nav-länk: Agent Intelligence
4. AI-Citable summary-uppdatering

Kör: python3 patch_landing_agent_intelligence.py
"""
import re

LANDING = "/Users/anstudio/agentindex/agentindex/crypto/templates/zarq_landing.html"

with open(LANDING, "r") as f:
    html = f.read()

# ─── 1. Agent Intelligence Live Box ──────────────────────────────────────────
# Lägg in efter track-record-sektionen (efter </section> som har track-record)

AGENT_BOX = '''
<!-- AGENT INTELLIGENCE LIVE BOX -->
<section style="max-width:var(--wide);margin:0 auto;padding:0 40px 48px">
  <div style="border:1px solid var(--gray-200);padding:32px 36px">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px;flex-wrap:wrap;gap:16px">
      <div>
        <div style="font-family:var(--mono);font-size:11px;letter-spacing:0.15em;text-transform:uppercase;color:var(--warm);margin-bottom:8px">Agent Intelligence — Live</div>
        <div style="font-family:var(--serif);font-size:26px;color:var(--black);line-height:1.2" id="ai-headline">47,119 AI agents tracked across 9 chains</div>
      </div>
      <div style="display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:11px;color:#16a34a;border:1px solid rgba(22,163,74,0.3);padding:4px 12px">
        <span style="width:6px;height:6px;background:#16a34a;border-radius:50%;display:inline-block;animation:pulse 2s infinite"></span>
        LIVE
      </div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--gray-200);border:1px solid var(--gray-200);margin-bottom:24px" id="ai-stats-grid">
      <div style="background:var(--white);padding:20px 24px">
        <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500);margin-bottom:4px">Capital at Crash Risk</div>
        <div style="font-family:var(--serif);font-size:32px;color:#dc2626" id="ai-crash-mcap">$517M</div>
        <div style="font-family:var(--mono);font-size:11px;color:var(--gray-400)">crash probability &gt;50%</div>
      </div>
      <div style="background:var(--white);padding:20px 24px">
        <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500);margin-bottom:4px">Structural Collapse</div>
        <div style="font-family:var(--serif);font-size:32px;color:#dc2626" id="ai-collapse">12 agents</div>
        <div style="font-family:var(--mono);font-size:11px;color:var(--gray-400)">$344M exposed · 90% crash prob</div>
      </div>
      <div style="background:var(--white);padding:20px 24px">
        <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500);margin-bottom:4px">Base Chain Risk</div>
        <div style="font-family:var(--serif);font-size:32px;color:#d97706" id="ai-base">19,442 agents</div>
        <div style="font-family:var(--mono);font-size:11px;color:var(--gray-400)">$1.92B · concentration risk 10/10</div>
      </div>
    </div>
    <div style="font-family:var(--mono);font-size:12px;color:var(--gray-600);line-height:1.8;max-width:680px;margin-bottom:20px" id="ai-finding">
      <strong style="color:var(--black)">Latest finding:</strong> Agent <em>pippin</em> (Virtuals) holds $344.6M in PIPPIN token, currently rated CRITICAL with 90% crash probability and structural_weakness=3 — the highest possible collapse signal.
    </div>
    <a href="/agent-intelligence" style="font-family:var(--mono);font-size:11px;letter-spacing:0.05em;color:var(--warm);text-decoration:none">Full Agent Intelligence report &rarr;</a>
  </div>
</section>

<script>
// Live refresh av agent intelligence data
async function refreshAgentIntelligence() {
  try {
    const [collapseRes, chainRes] = await Promise.all([
      fetch('/v1/agents/structural-collapse'),
      fetch('/v1/agents/chain-concentration-risk')
    ]);
    const collapse = await collapseRes.json();
    const chains = await chainRes.json();

    const total = chains.global?.total_agents || 47119;
    const collapseMcap = collapse.total_mcap_exposed_usd || 0;
    const collapseCount = collapse.total_agents_in_structural_collapse || 0;
    const baseChain = chains.chains?.find(c => c.chain === 'base');

    document.getElementById('ai-headline').textContent =
      `${total.toLocaleString()} AI agents tracked — ${collapseCount} in Structural Collapse`;

    const mcapM = (collapseMcap / 1e6).toFixed(0);
    document.getElementById('ai-collapse').textContent = `${collapseCount} agents`;
    document.querySelector('#ai-stats-grid div:nth-child(2) div:nth-child(3)').textContent =
      `$${mcapM}M exposed`;

    if (baseChain) {
      document.getElementById('ai-base').textContent =
        `${baseChain.total_agents.toLocaleString()} agents`;
    }
  } catch(e) { /* Keep static fallback */ }
}
refreshAgentIntelligence();
</script>
'''

# Hitta rätt plats: efter track-record-sektionen, innan capabilities
# Sök efter "<!-- CAPABILITIES -->" och lägg in agent-boxen precis innan
if '<!-- CAPABILITIES -->' in html:
    html = html.replace('<!-- CAPABILITIES -->', AGENT_BOX + '\n<!-- CAPABILITIES -->')
    print("✅ Agent Intelligence live-box tillagd (före capabilities)")
else:
    print("⚠️  Kunde inte hitta <!-- CAPABILITIES --> — lägg till manuellt")

# ─── 2. Capability #8 ─────────────────────────────────────────────────────────
CAP_8 = '''    <div class="cap-item">
      <div class="cap-num">8</div>
      <div>
        <div class="cap-title"><a href="/agent-intelligence" style="color:inherit;text-decoration:none">Agent Intelligence</a></div>
        <div class="cap-text">The only platform that crosses 47,119 AI agents with institutional crypto risk data. We track which agents hold which tokens, flag exposure to Structural Collapse and CRITICAL-rated assets, and rank chains by AI-agent concentration risk. $517M in agent capital currently exposed to tokens with &gt;50% crash probability. Agent Exodus Index — detecting when agents leave before TVL collapses — launching Q3 2026.</div>
        <div class="cap-tag"><a href="/agent-intelligence" style="color:inherit;text-decoration:none">47,119 agents tracked &rarr;</a></div>
      </div>
    </div>
  </div>
</section>'''

# Hitta slutet av capabilities-listan och lägg in #8
if '<div class="cap-num">7</div>' in html:
    # Hitta </section> som avslutar capabilities och lägg in #8 innan
    html = re.sub(
        r'(        <div class="cap-tag">Free during beta</div>\n      </div>\n    </div>\n  </div>\n</section>)',
        r'        <div class="cap-tag">Free during beta</div>\n      </div>\n    </div>\n' + CAP_8,
        html
    )
    print("✅ Capability #8 (Agent Intelligence) tillagd")
else:
    print("⚠️  Kunde inte hitta capability #7 — lägg till #8 manuellt")

# ─── 3. Nav-länk ─────────────────────────────────────────────────────────────
OLD_NAV = '    <a href="/track-record">Track Record</a>
        <a href="/paper-trading">Paper Trading</a>'
NEW_NAV = '    <a href="/agent-intelligence">Agent Intelligence</a>\n    <a href="/track-record">Track Record</a>
        <a href="/paper-trading">Paper Trading</a>'

if OLD_NAV in html and 'agent-intelligence' not in html.split('<nav>')[1].split('</nav>')[0]:
    html = html.replace(OLD_NAV, NEW_NAV, 1)
    print("✅ Nav-länk tillagd")
else:
    print("ℹ️  Nav-länk redan finns eller kunde inte hittas")

# ─── 4. Spara ─────────────────────────────────────────────────────────────────
with open(LANDING, "w") as f:
    f.write(html)

print("\n✅ zarq_landing.html uppdaterad")
print("Kör om: launchctl stop com.nerq.api && launchctl start com.nerq.api")
