# Optimal Challenge 1.1.0

<p align="center">
  <img src="assets/logo.png" alt="Optimal Challenge penguin routing icon" width="180">
</p>

A lightweight always-on routing skill/plugin. It handles simple requests directly, reuses applicable plans in continued threads, and loads specialist workflows only when their expected value justifies the context and compute cost.

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
This repository contains a local Codex marketplace at `.agents/plugins/marketplace.json`. From PowerShell, add this repository as the marketplace and install its plugin:

```powershell
codex plugin marketplace add D:\Projects\Plugins\optimal-challenge-plugin
codex plugin add optimal-challenge@optimal-challenge-local
```

For another checkout, replace the path in the first command with that checkout's root. Start a new Codex task after installation so it loads the skill. The root `plugin.json` and `.codex-plugin/plugin.json` describe the plugin; `.agents/plugins/marketplace.json` is the manifest required by `codex plugin marketplace add`.

#### Skill selection

Codex does not provide a numeric skill-priority setting. It selects skills from their names and descriptions. Optimal Challenge is intentionally automatic for every request. Its fast path handles simple tasks directly without loading references or additional process skills. For continued work, it reuses an applicable approved plan instead of invoking brainstorming or planning again.

If another installed skill activates on every request, disable that specific skill in `~/.codex/config.toml` using its installed `SKILL.md` path:

```toml
[[skills.config]]
path = "C:/path/to/competing-skill/SKILL.md"
enabled = false
```

Keep this plugin enabled:

```toml
[plugins."optimal-challenge@optimal-challenge-local"]
enabled = true
```

Restart Codex after changing the configuration. To force this workflow for one request, invoke `$optimal-challenge:optimal-challenge` explicitly.

### Claude Code
Claude Code supports loading a plugin directory or ZIP for local testing:

```bash
claude --plugin-dir ./optimal-challenge
# or supported Claude Code versions:
claude --plugin-dir ./optimal-challenge-plugin-1.1.0.zip
```

The skill appears under the plugin namespace. Implicit model invocation remains enabled so it can assess every request and route only meaningful complexity.

## Validate

```bash
python scripts/validate.py
python -m unittest -v tests.test_package
```

The validator checks manifest consistency, skill frontmatter, reference integrity, word/description budgets, path safety, scenario coverage, and that no active hooks ship in v1.1.

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
