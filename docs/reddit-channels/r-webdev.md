# Reddit Post Draft: r/webdev

**Subreddit:** r/webdev (also suitable for r/javascript)

**Title:** I built a browser extension that shows trust scores for npm packages — trying to make supply chain risk visible before you install

**Body:**

After the event-stream incident, left-pad, and the constant stream of typosquatting attacks on npm, I started thinking about what it would look like to have trust signals visible *before* you `npm install` something.

**What it does**

Nerq is a trust scoring engine that indexes AI tools, packages, and developer assets. The part that's most relevant here: it has a browser extension that adds trust badges directly on npmjs.com package pages.

When you're browsing npm, you see a score next to the package based on:

- Maintainer history (how long active, how many packages, any known incidents)
- Dependency health (are the deps themselves maintained?)
- Update patterns (regular releases vs. abandoned)
- Community signals (downloads, stars, issues response time)
- Known vulnerability track record

It's not a replacement for `npm audit` — it's complementary. `npm audit` tells you about known CVEs. This tells you whether the package *looks like* something that's actively maintained and safe to depend on.

**Other dev integrations**

Beyond the browser extension:

- **GitHub App** — Scans pull requests for new or updated dependencies and comments with trust scores. Catches low-trust deps before they merge.
- **VS Code extension** — Shows inline trust scores in your `package.json`. Hover over a dependency, see its score and breakdown.
- **API** — If you want to integrate trust checks into CI/CD pipelines or custom tooling.

**Why I built it**

I maintain a few projects that pull in a lot of dependencies, and the due diligence process was always the same: check the GitHub repo, look at the last commit date, skim the issues, check download counts. That's a manual process that should be automated and surfaced where you already work.

The whole index covers 5M+ assets including AI models and agents, but the npm/developer tooling angle felt like the most practical starting point for this community.

Would love feedback from people who deal with dependency management day to day. What signals would you actually trust? What would make you install the extension vs. ignore it?

Site: https://nerq.ai
