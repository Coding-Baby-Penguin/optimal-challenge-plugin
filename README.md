# Optimal Challenge

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

## Core runtime improvements

These behaviors belong to the plugin. The repository files document, template, and test them so they remain available across releases.

1. **Knowledge retention:** this README explains the plugin for users, while the unified project-state file retains only the verified state needed by the next work pass.
2. **Checkpoint and resume:** before quota/session boundaries or major handoffs, the plugin refreshes the restart contract from `templates/PROJECT-STATE.md`; resumption verifies reality and continues the exact next action.
3. **Question bundle:** after useful investigation, all currently knowable user decisions are presented together with recommended defaults, impact, blockers, and next steps.
4. **Reusable snippets:** code, commands, configuration, and prompts expose inputs, assumptions, adaptation points, and verification rather than hiding project-specific values in hard-coded examples.
5. **Safe-by-default .gitignore:** new projects establish ignore rules before private or generated files are created, and the first staged set is inspected because ignore rules do not protect files already tracked.
6. **Folder planning:** before creating or moving a meaningful set of files, the plugin follows ecosystem conventions, proposes a tree and placement rules, records a migration map, updates path consumers, and verifies discovery, tests, builds, and packaging.
7. **Configuration governance:** hard-code audits classify invariants, deploy-varying values, secrets, fixtures, and examples; project-owned configuration lives under `config/` behind one documented access path.
8. **Maintained README:** installation, configuration, usage, paths, commands, and release details are updated and verified in the same change that alters them.
9. **Unified project state:** `docs/PROJECT-STATE.md` is the single source for current verified state and the Now / Next / Later development path.

The detailed runtime contracts live in the lazily loaded files under `skills/optimal-challenge/references/`. The templates are optional until their trigger occurs; they are not loaded into every simple request.

### Folder planning behavior

There is no universal best tree. The planner first identifies ecosystem conventions and tool discovery rules, then classifies source, tests, validation, fixtures, scripts, documentation, generated files, private state, and distributables. A non-trivial reorganization uses `templates/FOLDER-PLAN.md` so every move has a reason, migration map, path-consumer checklist, verification, and rollback.

This repository applies that rule by keeping its package-validation suite under `tests/validation/`. Small projects remain shallow when their ecosystem expects it; folders are introduced only for tool discovery, a distinct lifecycle or boundary, or concrete near-term expansion.

## Package layout

```text
optimal-challenge/
├── plugin.json                     portable Agent Plugins manifest
├── config/                         canonical project-owned configuration
├── docs/PROJECT-STATE.md           current state and development path
├── .codex-plugin/plugin.json       Codex compatibility manifest
├── .claude-plugin/plugin.json      Claude Code manifest
├── skills/optimal-challenge/
│   ├── SKILL.md                    small runtime router
│   ├── references/                 lazily loaded policy modules
│   └── templates/                  checkpoint, question, snippet, state, and capsule templates
├── scripts/validate.py             dependency-free package validator
└── tests/
    ├── scenarios.json              trigger/anti-trigger evaluation matrix
    └── validation/
        └── test_package.py         independent structural/policy checks
```

## Install / test

### OpenAI / Codex-compatible plugin
This repository contains a local Codex marketplace at `.agents/plugins/marketplace.json`. From PowerShell, set the checkout path once, then add the marketplace and install its plugin:

```powershell
$repoPath = "C:\path\to\optimal-challenge-plugin"
codex plugin marketplace add $repoPath
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
# For supported Claude Code versions, substitute the packaged release version:
claude --plugin-dir ./optimal-challenge-plugin-<version>.zip
```

The skill appears under the plugin namespace. Implicit model invocation remains enabled so it can assess every request and route only meaningful complexity.

## Validate

```bash
python scripts/validate.py
python -m unittest -v tests.validation.test_package
```

The validator checks manifest consistency, skill frontmatter, reference integrity, word/description budgets, path safety, scenario coverage, and that no active hooks ship in v1.1.

## Configuration

Project-maintenance values are defined once in [`config/project.json`](config/project.json) and documented in [`config/README.md`](config/README.md). Platform-required manifests remain in their required locations and are validated against that central configuration. Real secrets never belong in committed configuration.

## Adaptation and self-improvement

Normal tasks should write at most a tiny experience delta when the host/workflow supports durable state. The adaptation references are intentionally dormant until repeated evidence accumulates.

A skill improvement may be evaluated autonomously, but **actual self-modification requires a writable versioned skill/plugin workspace**. An installed/hosted immutable ZIP cannot safely rewrite itself; in that environment the workflow records an evolution candidate for the next packaging/deployment cycle instead of pretending a change was deployed.

No active hooks are included in v1.1. This is intentional: hooks are promoted only after a deterministic recurring pattern proves their per-trigger cost worthwhile.

## Suggested state placement

Use the templates only when persistent multi-pass work needs them. Do not load all state files into every task.

- Local repo/Codex: keep current state and the development path together in [`docs/PROJECT-STATE.md`](docs/PROJECT-STATE.md). Rewrite it at meaningful milestones; do not create parallel checkpoint or roadmap files.
- Cloud/project chat: store only durable project state in project/cloud files; treat individual chats as disposable working contexts.

On resume, compare the project-state file with the source tree and current version-control state before acting. Source and tests remain authoritative if recorded state has become stale.

## Verification note

The included automated tests verify package structure and policy invariants. Behavioral skill triggering ultimately depends on the host model, installed specialist skills, and available tools, so `tests/scenarios.json` is also included as a regression suite for model-level evaluation in Codex/Claude when available.
