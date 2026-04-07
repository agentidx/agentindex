#!/usr/bin/env node
// nerq-check — Trust scores for any software
// Usage: npx nerq-check express
// Usage: npx nerq-check express react lodash

const args = process.argv.slice(2);
if (args.length === 0) {
  console.log("nerq-check — Trust scores for any software");
  console.log("Usage: npx nerq-check <package> [package2] [package3]");
  console.log("Example: npx nerq-check express react lodash");
  console.log("Docs: https://nerq.ai/nerq/docs");
  process.exit(1);
}

async function check(name) {
  try {
    const res = await fetch(
      `https://nerq.ai/v1/preflight?target=${encodeURIComponent(name)}`
    );
    const data = await res.json();
    const score = data.trust_score ?? data.score ?? "?";
    const grade = data.grade ?? "?";
    const risk = data.risk_level ?? (score >= 70 ? "low" : score >= 40 ? "medium" : "high");
    const icon = score >= 70 ? "\u2713" : score >= 40 ? "\u26A0" : "\u2717";
    console.log(`${icon} ${name}: ${score}/100 (${grade}) — ${risk}`);
    if (score < 40) {
      console.log(`  \u2192 Consider alternatives: https://nerq.ai/alternatives/${name}`);
    }
    return { name, score, grade, risk };
  } catch (e) {
    console.log(`? ${name}: check failed (${e.message})`);
    return { name, score: null, error: e.message };
  }
}

(async () => {
  const results = [];
  for (const name of args) {
    results.push(await check(name));
  }
  const failed = results.filter((r) => r.score !== null && r.score < 40);
  if (failed.length > 0) {
    console.log(`\n${failed.length} package(s) below trust threshold.`);
    console.log("Full reports: https://nerq.ai/safe/{name}");
    process.exit(1);
  }
})();
