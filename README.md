# Optimal Challenge 1.0.0

A lightweight meta-routing skill/plugin for difficult AI work. It chooses the smallest adequate workflow, keeps working context bounded, controls subagent skill/tool budgets, uses risk-matched verification, and records repeating patterns/preferences without making ordinary turns pay for an always-on adaptation engine.

## Design goals

- **Goal first:** infer success criteria and ask only when ambiguity materially changes the outcome.
- **Lazy loading:** `SKILL.md` is a small router; detailed modules live in `references/` and load only when triggered.
- **Context discipline:** use minimum sufficient working sets and durable state instead of long-chat replay.
- **Parent-controlled delegation:** workers receive capability leases and do not re-run parent planning by default.
- **Reality checks for codebases:** do not equate context/retrieval/tests with complete system understanding.
- **Proportional evidence:** verification depth follows risk and oracle strength.
- **Adaptive, not bloated:** repeated patterns may become preferences, instructions, specialist skills, hooks, or tooling; one-off events do not.
- **Platform-aware storage:** exploit filesystem/git in local repo environments and durable project/cloud storage in chat-oriented environments.

## Package layout

```text
optimal-challenge/
├── plugin.json                     portable Agent Plugins manifest
├── .codex-plugin/plugin.json       Codex compatibility manifest
├── .claude-plugin/plugin.json      Claude Code manifest
├── skills/optimal-challenge/
│   ├── SKILL.md                    small runtime router
│   ├── references/                 lazily loaded policy modules
│   └── templates/                  optional durable-state/capsule templates
├── scripts/validate.py             dependency-free package validator
└── tests/
    ├── scenarios.json              trigger/anti-trigger evaluation matrix
    └── test_package.py             independent structural/policy checks
```

## Install / test

### OpenAI / Codex-compatible plugin
Use the ZIP/package through the plugin loading mechanism supported by your Codex/ChatGPT environment. The bundle contains both the current portable root `plugin.json` and `.codex-plugin/plugin.json` compatibility manifest.

### Claude Code
Claude Code supports loading a plugin directory or ZIP for local testing:

```bash
claude --plugin-dir ./optimal-challenge
# or supported Claude Code versions:
claude --plugin-dir ./optimal-challenge-plugin-1.0.0.zip
```

The skill appears under the plugin namespace. Implicit model invocation remains enabled so difficult matching requests may route through it automatically.

## Validate

```bash
python scripts/validate.py
python -m unittest -v tests.test_package
```

The validator checks manifest consistency, skill frontmatter, reference integrity, word/description budgets, path safety, scenario coverage, and that no active hooks ship in v1.0.

## Adaptation and self-improvement

Normal tasks should write at most a tiny experience delta when the host/workflow supports durable state. The adaptation references are intentionally dormant until repeated evidence accumulates.

A skill improvement may be evaluated autonomously, but **actual self-modification requires a writable versioned skill/plugin workspace**. An installed/hosted immutable ZIP cannot safely rewrite itself; in that environment the workflow records an evolution candidate for the next packaging/deployment cycle instead of pretending a change was deployed.

No active hooks are included in v1.0. This is intentional: hooks are promoted only after a deterministic recurring pattern proves their per-trigger cost worthwhile.

## Suggested state placement

Use the templates only when persistent multi-pass work needs them. Do not load all state files into every task.

- Local repo/Codex: materialize state in an appropriate repo-local or user-local durable area; keep agent-only caches ignored by git.
- Cloud/project chat: store only durable project state in project/cloud files; treat individual chats as disposable working contexts.

## Verification note

The included automated tests verify package structure and policy invariants. Behavioral skill triggering ultimately depends on the host model, installed specialist skills, and available tools, so `tests/scenarios.json` is also included as a regression suite for model-level evaluation in Codex/Claude when available.
