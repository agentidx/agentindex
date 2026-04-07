"use strict";

const fs = require("fs");
const path = require("path");

function scaffold(config) {
  const dir = path.resolve(config.name);
  mkdirp(dir);
  mkdirp(path.join(dir, "src"));

  // requirements.txt
  const deps = frameworkDeps(config.framework);
  if (config.includeTrust) deps.push("nerq>=1.2.0");
  writeFile(path.join(dir, "requirements.txt"), deps.join("\n") + "\n");

  // src/agent.py
  writeFile(path.join(dir, "src", "agent.py"), agentTemplate(config));

  // src/tools.py
  if (config.includeTrust) {
    writeFile(path.join(dir, "src", "tools.py"), toolsTemplate(config));
  }

  // README.md
  writeFile(path.join(dir, "README.md"), readmeTemplate(config));

  // .well-known/agent.json
  mkdirp(path.join(dir, ".well-known"));
  writeFile(path.join(dir, ".well-known", "agent.json"), agentJsonTemplate(config));

  // llms.txt
  writeFile(path.join(dir, "llms.txt"), llmsTxtTemplate(config));

  // nerq.config.json
  if (config.includeTrust) {
    writeFile(path.join(dir, "nerq.config.json"), JSON.stringify({
      min_trust: 60,
      auto_resolve: true,
      api_url: "https://nerq.ai",
    }, null, 2) + "\n");
  }

  // .github/workflows/trust-check.yml
  if (config.includeCI) {
    mkdirp(path.join(dir, ".github", "workflows"));
    writeFile(path.join(dir, ".github", "workflows", "trust-check.yml"), ciTemplate(config));
  }

  // LICENSE
  writeFile(path.join(dir, "LICENSE"), licenseTemplate());

  console.log(`  Created ${countFiles(dir)} files`);
}

function frameworkDeps(framework) {
  switch (framework) {
    case "langchain": return ["langchain>=0.2.0", "langchain-openai>=0.1.0"];
    case "crewai": return ["crewai>=0.30.0"];
    case "autogen": return ["pyautogen>=0.2.0"];
    case "llamaindex": return ["llama-index>=0.10.0"];
    default: return ["openai>=1.0.0"];
  }
}

function agentTemplate(config) {
  const fw = config.framework;
  if (fw === "langchain") {
    return `"""${config.description}"""

from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.prompts import ChatPromptTemplate
${config.includeTrust ? "from tools import discover_tools\n" : ""}

def main():
    llm = ChatOpenAI(model="gpt-4o-mini")
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. ${config.description}"),
        ("human", "{input}"),
    ])
${config.includeTrust ? `
    # Dynamically discover trusted tools via Nerq
    tools = discover_tools("${config.description}")
` : "    tools = []"}
    agent = create_openai_functions_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools)
    result = executor.invoke({"input": "Hello, what can you do?"})
    print(result["output"])


if __name__ == "__main__":
    main()
`;
  }

  if (fw === "crewai") {
    return `"""${config.description}"""

from crewai import Agent, Task, Crew
${config.includeTrust ? "from tools import discover_tools\n" : ""}

def main():
${config.includeTrust ? `    tools = discover_tools("${config.description}")\n` : ""}
    agent = Agent(
        role="${config.name}",
        goal="${config.description}",
        backstory="An AI agent built with trust verification.",
${config.includeTrust ? "        tools=tools,\n" : ""}    )

    task = Task(
        description="${config.description}",
        agent=agent,
        expected_output="A helpful response",
    )

    crew = Crew(agents=[agent], tasks=[task])
    result = crew.kickoff()
    print(result)


if __name__ == "__main__":
    main()
`;
  }

  // Default / custom
  return `"""${config.description}"""

import openai
${config.includeTrust ? "from tools import discover_tools\n" : ""}

def main():
${config.includeTrust ? `    # Dynamically discover trusted tools via Nerq
    tools = discover_tools("${config.description}")
    print(f"Discovered {len(tools)} trusted tools")
` : ""}
    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant. ${config.description}"},
            {"role": "user", "content": "Hello, what can you do?"},
        ],
    )
    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()
`;
}

function toolsTemplate(config) {
  return `"""Dynamic tool discovery via Nerq.

Uses nerq.resolve() to find the best tools for any task at runtime.
Every tool is trust-verified before use.
"""

import nerq


def discover_tools(task_description, min_trust=60):
    """Find trusted tools for a task.

    Args:
        task_description: What you need to do
        min_trust: Minimum trust score (0-100)

    Returns:
        list of tool recommendations
    """
    try:
        result = nerq.resolve(task_description, min_trust=min_trust)
        if result:
            print(f"  Recommended: {result.get('name')} (Trust: {result.get('trust_score')})")
        return [result] if result else []
    except Exception as e:
        print(f"  Tool discovery failed: {e}")
        return []


def check_dependency(name):
    """Check if a dependency is trusted before importing it."""
    try:
        result = nerq.preflight(name)
        trust = result.get("target_trust", 0)
        rec = result.get("recommendation", "UNKNOWN")
        if rec == "DENY":
            raise RuntimeError(f"{name} has DENY trust recommendation (trust: {trust})")
        return result
    except Exception as e:
        print(f"  Warning: could not verify {name}: {e}")
        return None
`;
}

function readmeTemplate(config) {
  let badge = "";
  if (config.includeBadge) {
    badge = `[![Nerq Trust](https://nerq.ai/v1/badge/${config.name})](https://nerq.ai/safe/${config.name})\n\n`;
  }

  return `# ${config.name}

${badge}${config.description}

## Setup

\`\`\`bash
pip install -r requirements.txt
python src/agent.py
\`\`\`

## Framework

Built with ${config.framework}.${config.includeTrust ? " Uses [Nerq](https://nerq.ai) for dynamic tool discovery and trust verification." : ""}

## Trust Verification

${config.includeTrust ? `This project uses \`nerq.resolve()\` to dynamically discover trusted tools at runtime. Every tool is verified against Nerq's database of 204K+ agents before use.

To check your dependencies:
\`\`\`bash
pip install agent-security
agent-security scan requirements.txt
\`\`\`` : "Not configured."}

## License

MIT
`;
}

function agentJsonTemplate(config) {
  return JSON.stringify({
    name: config.name,
    description: config.description,
    url: `https://github.com/your-org/${config.name}`,
    version: "1.0.0",
    capabilities: { streaming: false },
    authentication: { schemes: ["none"] },
    defaultInputModes: ["text/plain"],
    defaultOutputModes: ["application/json"],
    skills: [{
      id: "main",
      name: config.name,
      description: config.description,
      tags: [config.framework, "ai", "agent"],
    }],
  }, null, 2) + "\n";
}

function llmsTxtTemplate(config) {
  return `# ${config.name}
# ${config.description}

> ${config.name} is an AI agent built with ${config.framework}.${config.includeTrust ? " It uses Nerq for trust verification and dynamic tool discovery." : ""}

## Capabilities
- ${config.description}

## API
- Framework: ${config.framework}
- Trust verification: ${config.includeTrust ? "enabled (nerq.ai)" : "not configured"}
`;
}

function ciTemplate(config) {
  return `name: Agent Security Check
on: [push, pull_request]

jobs:
  trust-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install agent-security
      - run: agent-security scan requirements.txt --ci
`;
}

function licenseTemplate() {
  return `MIT License

Copyright (c) ${new Date().getFullYear()}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
`;
}

function mkdirp(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function writeFile(filepath, content) {
  fs.writeFileSync(filepath, content);
  console.log(`  + ${path.relative(process.cwd(), filepath)}`);
}

function countFiles(dir) {
  let count = 0;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) count += countFiles(path.join(dir, entry.name));
    else count++;
  }
  return count;
}

module.exports = { scaffold };
