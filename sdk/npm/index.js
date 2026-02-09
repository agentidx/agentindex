/**
 * AgentIndex SDK
 * 
 * Find any AI agent by capability.
 * 
 * Usage:
 *   const { discover, getAgent, stats, configure } = require("@agentindex/sdk");
 *   
 *   const results = await discover("contract review");
 *   const results = await discover("code review", { minQuality: 0.7, protocols: ["mcp"] });
 *   const agent = await getAgent("uuid");
 *   const info = await stats();
 */

let endpoint = "http://localhost:8100/v1";
let apiKey = null;

function configure(options = {}) {
  if (options.endpoint) endpoint = options.endpoint.replace(/\/$/, "");
  if (options.apiKey) apiKey = options.apiKey;
}

async function _fetch(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;
  
  const response = await fetch(`${endpoint}${path}`, {
    ...options,
    headers: { ...headers, ...options.headers },
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(`AgentIndex API error ${response.status}: ${error.detail || response.statusText}`);
  }
  
  return response.json();
}

async function discover(need, options = {}) {
  const { category, protocols, minQuality = 0.0, maxResults = 10 } = options;
  
  const data = await _fetch("/discover", {
    method: "POST",
    body: JSON.stringify({
      need,
      category,
      protocols,
      min_quality: minQuality,
      max_results: maxResults,
    }),
  });
  
  return data.results;
}

async function getAgent(agentId) {
  const data = await _fetch(`/agent/${agentId}`);
  return data.agent;
}

async function stats() {
  return _fetch("/stats");
}

async function register(agentName, agentUrl) {
  return _fetch("/register", {
    method: "POST",
    body: JSON.stringify({ agent_name: agentName, agent_url: agentUrl }),
  });
}

module.exports = { discover, getAgent, stats, register, configure };
