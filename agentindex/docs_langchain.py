"""
LangChain Integration Docs — nerq.ai/docs/langchain
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from agentindex.nerq_design import nerq_page

router_docs_langchain = APIRouter(tags=["docs"])


@router_docs_langchain.get("/docs/langchain", response_class=HTMLResponse)
def langchain_docs():
    body = """
<div class="breadcrumb"><a href="/">nerq</a> &rsaquo; <a href="/nerq/docs">docs</a> &rsaquo; langchain</div>

<h1>nerq-langchain</h1>
<p class="desc">Trust-gate your LangChain agents. Preflight trust checks before every tool call.</p>

<h2 id="install">Installation</h2>
<pre>pip install nerq-langchain</pre>
<p class="desc">Dependencies: <code>langchain-core</code>, <code>requests</code>. Python 3.9+.</p>

<h2 id="trust-gate">trust_gate</h2>
<p class="desc">Wrap any LangChain agent with automatic preflight trust checks on every tool call.</p>

<pre>from nerq_langchain import trust_gate

agent = initialize_agent(tools, llm)
agent = trust_gate(agent, min_trust=60)
# Every tool call now gets a trust check</pre>

<p class="desc"><strong>What happens on each tool call:</strong></p>
<table>
<tr><th>recommendation</th><th>trust score</th><th>behavior</th></tr>
<tr><td><code>PROCEED</code></td><td>&ge; 70</td><td>Runs silently</td></tr>
<tr><td><code>CAUTION</code></td><td>40&ndash;69</td><td>Logs warning, proceeds</td></tr>
<tr><td><code>DENY</code></td><td>&lt; 40</td><td>Raises <code>TrustError</code></td></tr>
<tr><td><code>UNKNOWN</code></td><td>&mdash;</td><td>Proceeds with warning</td></tr>
<tr><td><em>API unreachable</em></td><td>&mdash;</td><td>Proceeds with warning (never blocks)</td></tr>
</table>

<pre>from nerq_langchain import trust_gate, TrustError

agent = trust_gate(agent, min_trust=70)
try:
    result = agent.run("Analyze this code")
except TrustError as e:
    print(f"Blocked: {e.tool_name} (trust={e.trust_score})")
    # e.tool_name, e.trust_score, e.recommendation</pre>

<h2 id="preflight">NerqPreflight tool</h2>
<p class="desc">LangChain tool that agents can use directly to check trust on any agent or tool.</p>

<pre>from nerq_langchain import NerqPreflight

tool = NerqPreflight()
print(tool.run("SWE-agent"))
# Nerq Preflight: SWE-agent
# Recommendation: PROCEED
# Trust Score: 92.5/100
# Grade: A+
# Verified: Yes
# Category: security
# This agent is trusted. Safe to interact.</pre>

<h2 id="search">NerqSearch tool</h2>
<p class="desc">Find the best agent for any task from 204K+ indexed agents.</p>

<pre>from nerq_langchain import NerqSearch

tool = NerqSearch()
print(tool.run("code review"))
# Nerq Search: 'code review' &mdash; 5 results
# 1. SWE-agent/SWE-agent &mdash; Trust: 92.5, Category: security
# 2. skill-code-review &mdash; Trust: 86.0, Category: coding
# ...</pre>

<h2 id="full-example">Full example</h2>
<pre>from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent, AgentType
from nerq_langchain import NerqPreflight, NerqSearch, trust_gate

llm = ChatOpenAI(model="gpt-4")
tools = [NerqPreflight(), NerqSearch()]
agent = initialize_agent(tools, llm, agent=AgentType.OPENAI_FUNCTIONS)

# Trust-gate: block tools with trust &lt; 60
agent = trust_gate(agent, min_trust=60)

result = agent.run("Is SWE-agent safe to use?")</pre>

<h2 id="langgraph">With LangGraph</h2>
<pre>from nerq_langchain import NerqPreflight, NerqSearch
from langgraph.prebuilt import create_react_agent

tools = [NerqPreflight(), NerqSearch()]
agent = create_react_agent(model, tools)</pre>

<h2 id="why">Why trust-gate your agents?</h2>
<p style="font-size:14px;line-height:1.7">
As AI agents delegate tasks to other agents, every interaction becomes a trust decision.
An agent accepting untrusted input or delegating to a compromised tool creates
a chain of liability. <code>trust_gate</code> adds a zero-config trust layer:
before any tool call executes, Nerq checks the tool's trust score across
204K indexed agents and makes a PROCEED/CAUTION/DENY decision in &lt;50ms.
No API key required. Graceful fallback if Nerq is unreachable.
</p>

<p style="font-size:14px;color:#6b7280;margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb">
<a href="https://pypi.org/project/nerq-langchain/">PyPI</a> &middot;
<a href="/nerq/docs#preflight">Preflight API</a> &middot;
<a href="/kya">KYA &mdash; Know Your Agent</a> &middot;
<a href="/nerq/docs">Full API Docs</a>
</p>
"""
    return nerq_page(
        "nerq-langchain &mdash; Trust-gate your agents",
        body,
        description="Trust-gate LangChain agents with Nerq preflight checks. 204K+ agents indexed.",
        canonical="https://nerq.ai/docs/langchain",
    )
"""
"""
