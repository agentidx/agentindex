#!/usr/bin/env node
"use strict";

const readline = require("readline");
const path = require("path");
const { scaffold } = require("../src/scaffold");

const args = process.argv.slice(2);

const FRAMEWORKS = ["langchain", "crewai", "autogen", "llamaindex", "custom"];

function ask(rl, question, defaultVal) {
  return new Promise((resolve) => {
    const suffix = defaultVal ? ` (${defaultVal})` : "";
    rl.question(`  ${question}${suffix}: `, (answer) => {
      resolve(answer.trim() || defaultVal || "");
    });
  });
}

function askYN(rl, question, defaultVal = true) {
  return new Promise((resolve) => {
    const hint = defaultVal ? "(Y/n)" : "(y/N)";
    rl.question(`  ${question} ${hint}: `, (answer) => {
      const a = answer.trim().toLowerCase();
      if (!a) return resolve(defaultVal);
      resolve(a === "y" || a === "yes");
    });
  });
}

function askChoice(rl, question, choices) {
  return new Promise((resolve) => {
    console.log(`  ${question}`);
    choices.forEach((c, i) => console.log(`    ${i + 1}. ${c}`));
    rl.question("  Choice (number): ", (answer) => {
      const idx = parseInt(answer) - 1;
      resolve(choices[idx] || choices[0]);
    });
  });
}

async function main() {
  const projectName = args[0];

  if (!projectName || projectName === "--help" || projectName === "-h") {
    console.log(`
create-nerq-agent — Scaffold a trust-verified AI agent project.

Usage:
  npx create-nerq-agent <project-name>
  npx create-nerq-agent my-agent --framework langchain --skip-prompts

Options:
  --framework <name>   Framework: langchain, crewai, autogen, llamaindex, custom
  --skip-prompts       Use defaults, no interactive prompts
  --no-badge           Skip Nerq trust badge
  --no-ci              Skip GitHub Action
  --no-trust           Skip trust verification setup
`);
    return;
  }

  const skipPrompts = args.includes("--skip-prompts");
  const flagFramework = args[args.indexOf("--framework") + 1];

  let config;

  if (skipPrompts) {
    config = {
      name: projectName,
      framework: flagFramework || "langchain",
      description: "AI agent project",
      includeTrust: !args.includes("--no-trust"),
      includeBadge: !args.includes("--no-badge"),
      includeCI: !args.includes("--no-ci"),
    };
  } else {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

    console.log("\n  create-nerq-agent\n");

    const framework = await askChoice(rl, "Framework:", FRAMEWORKS);
    const description = await ask(rl, "What will your agent do?", "AI agent");
    const includeTrust = await askYN(rl, "Include Nerq trust verification?", true);
    const includeCI = await askYN(rl, "Include GitHub Action for trust checking?", true);
    const includeBadge = await askYN(rl, "Include Nerq badge in README?", true);

    rl.close();

    config = {
      name: projectName,
      framework,
      description,
      includeTrust,
      includeBadge,
      includeCI,
    };
  }

  console.log(`\n  Creating ${config.name} with ${config.framework}...\n`);
  scaffold(config);
  console.log(`\n  Done! Your agent is ready at ./${config.name}/`);
  console.log(`\n  Next steps:`);
  console.log(`    cd ${config.name}`);
  console.log(`    pip install -r requirements.txt`);
  console.log(`    python src/agent.py\n`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
