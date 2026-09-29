# Optimal Challenge

<p align="center">
  <img src="assets/logo.png" alt="Optimal Challenge penguin routing icon" width="180">
</p>

A lightweight always-on routing skill/plugin. It handles simple requests directly, reuses applicable plans in continued threads, and loads specialist workflows only when their expected value justifies the context and compute cost.

## Design goals

- **Goal first:** infer success criteria and ask only when ambiguity materially changes the outcome.
- **Lazy loading:** `SKILL.md` is a small router; detailed modules live in `references/` and load only when triggered.
- **Context discipline:** preserve the root goal, prune context that cannot change a decision or verification, and use durable pointers instead of long-chat replay.
- **Parent-controlled delegation:** workers receive capability leases and do not re-run parent planning by default.
- **Reality checks for codebases:** do not equate context/retrieval/tests with complete system understanding.
- **Proportional evidence:** verification depth follows risk and oracle strength.
- **Adaptive, not bloated:** repeated patterns may become preferences, instructions, specialist skills, hooks, or tooling; one-off events do not.
- **Platform-aware storage:** exploit filesystem/git in local repo environments and durable project/cloud storage in chat-oriented environments.

## Choose how it runs

The default is `mode=auto`, `profile=balanced`. Stable, single-step, low-risk requests stay inline and silent: no profile question, premise score, or team bookkeeping appears. You can set one request in plain language, for example:

> For this task: team-requested, Quality profile, exactly 2 specialists, with a 40,000-token advisory ceiling.

| Invocation | Meaning |
|---|---|
| `inline-only` | Use no specialists. A conflicting mandatory independent-review requirement produces one resolution question, never a silent spawn. |
| `auto` | Delegate only when the evidence-backed benefit clears the active profile margin and allocation is available. |
| `team-requested` | Prefer a useful team, but still challenge wasteful, unsafe, unavailable, or unfunded work. |
| `exact specialists=N` | Request `N` additional workers beyond the coordinator, from 0 through `min(32, detected_host_max)`. A count that cannot be satisfied is reported, not silently changed. |

An ambiguous request such as "a team of three" is resolved from clear context or with one material count question. If the request also says `inline-only`, the plugin asks one concise resolution question. Persistent user-controlled overrides belong in the ignored `.optimal-challenge/orchestration.local.json`; committed repository defaults live in [`config/orchestration.json`](config/orchestration.json). Current-request constraints outrank both.

## Profiles and routing calculations

Profiles tune tradeoffs; they never override correctness, safety, privacy, explicit authority, or mandatory verification.

| Profile | Quality | Cost | Latency | Attention | Rework | Delegation margin | Optional-review margin |
|---|---:|---:|---:|---:|---:|---:|---:|
| Economy | 0.35 | 0.35 | 0.10 | 0.10 | 0.10 | 3 | 6 |
| Balanced | 0.45 | 0.20 | 0.10 | 0.10 | 0.15 | 1 | 3 |
| Quality | 0.50 | 0.10 | 0.05 | 0.10 | 0.25 | 1 | 1 |
| Custom | normalized user weights | | | | | 1–12 | 1–27 |

Delegation uses `D(t) = benefits − costs`, where benefits cover expected quality, parallelism, context containment, and verification, while costs cover coordination, contention, integration, and failure risk. It proceeds only when `D(t)` clears the profile margin; ties stay inline. Route comparison normalizes quality, whole-job cost, latency, user attention, and expected rework. Whole-job cost includes input, cache write/read, output, and tool use; unavailable measurements remain `unknown` and cannot support a cost-saving claim.

## Better questions, not more questions

The premise gate runs only after the direct fast path is rejected. It records `PremiseRisk = WrongnessLikelihoodRating × ReworkCost` and `QuestionValue = ExpectedReworkAvoided − UserAttentionCost`. The plugin investigates cheap facts first, uses a safe reversible default when possible, and asks only when risk is at least 4, question value is positive, and the answer changes the work graph or an irreversible choice.

When input is genuinely required, all currently knowable user-only blockers appear in one bundle with a recommended default, impact, safe work that can continue, and next steps. Material answers receive stable decision IDs; a settled decision is not asked again unless new contradictory evidence is cited. Mode, profile, and budget are not exposed merely for configuration theatre.

### Research before scale

When rejection, paid generation, or broad rework makes a batch materially costly, the plugin establishes current authoritative acceptance criteria before production. It converts those findings into an observable rubric, resolves material contradictions, and validates the smallest adequate risk-representative pilot before scaling. Existing current rubrics skip redundant research, and settled representative pilot approval is reused without re-asking only when trusted records bind the unchanged rubric, inputs, scope, and risks. Caller-authored `passed`, `resolved`, or nonblank ID fields are never proof.

Refusing research or a pilot permits only non-scaled provisional exploration no larger than that pilot or draft, never the full costly batch or an acceptance-ready claim. Task overrides remain guidance; they do not prove durable cloud persistence or budget enforcement.

## Budget assignment and truthfulness

Budget fields always name their unit (`tokens`, `credits`, time, currency, tool calls, or model calls), limit, measurement (`observed`, `estimated`, or `unavailable`), source, and enforcement (`advisory`, `local_enforced`, or `provider_enforced`). Units are never converted without a verified mapping.

The allocation ledger can reserve coordinator, worker, tool, retry, integration, and mandatory-review capacity. It preserves `available + reserved + funded_consumed = ceiling`; over-ceiling use is tracked separately as unfunded consumption, never turned into false availability. At a soft threshold, optional parallelism or optional review is reduced before mandatory verification.

The committed default is advisory. An advisory ceiling stops the next discretionary operation but does not automatically prevent provider spend, cancel running work, or prove the exact remaining balance. Local/provider enforcement is claimed only when the exact host surface and version supply fresh trusted observed usage plus the matching stop primitive. If mandatory enforcement is unavailable, the result is `Blocked` before spend or one route/limit decision; accepting advisory operation is explicitly `Degraded`.

## Continuity and selective review

Each specialist has a logical identity separate from a provider session. The coordinator chooses among native resume, rehydrating the same logical role from a compact capsule, or a fresh independent worker. Every handoff preserves the user-controlled root goal, states the local contribution and stop condition, and returns only the goal-relevant delta. Source, tests, explicit decisions, and [`docs/PROJECT-STATE.md`](docs/PROJECT-STATE.md) outrank registry or conversation memory. Disposable registry/ledger state stays under ignored `.optimal-challenge/`; raw transcripts, secrets, and sensitive traits do not enter committed capsules.

Review is selective: `ReviewValue = P(defect) × Impact × P(review detects defect) − ReviewCost`. Strong deterministic oracles handle reversible mechanical work; a fresh reviewer handles material judgment when value clears the profile margin. Consequential weak-oracle work can require independent review. If that reviewer is unavailable, the plugin reports `Blocked`, or `Degraded` only after an accepted named compensating oracle—never silent self-approval.

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
10. **Visible failures:** required work cannot silently degrade into success; failures, partial results, skipped checks, retries, fallbacks, and unfinished background work retain evidence, impact, and a concrete recovery action.

The detailed runtime contracts live in the lazily loaded files under `skills/optimal-challenge/references/`. The templates are optional until their trigger occurs; they are not loaded into every simple request.

### Folder planning behavior

There is no universal best tree. The planner first identifies ecosystem conventions and tool discovery rules, then classifies source, tests, validation, fixtures, scripts, documentation, generated files, private state, and distributables. A non-trivial reorganization uses `templates/FOLDER-PLAN.md` so every move has a reason, migration map, path-consumer checklist, verification, and rollback.

This repository applies that rule by keeping its package-validation suite under `tests/validation/`. Small projects remain shallow when their ecosystem expects it; folders are introduced only for tool discovery, a distinct lifecycle or boundary, or concrete near-term expansion.

Maintainers can start at the [repository guide](docs/README.md) for owner maps, contribution checks, and evidence boundaries.

## Package layout

```text
optimal-challenge/
├── plugin.json                     portable Agent Plugins manifest
├── config/                         canonical project-owned configuration
├── docs/PROJECT-STATE.md           current state and development path
├── docs/README.md                  maintainer entry map
├── .codex-plugin/plugin.json       Codex compatibility manifest
├── .claude-plugin/
│   ├── plugin.json                 Claude Code plugin manifest
│   └── marketplace.json            Claude Code marketplace catalog
├── skills/optimal-challenge/
│   ├── SKILL.md                    small runtime router
│   ├── references/                 lazily loaded policy modules
│   └── templates/                  checkpoint, question, snippet, state, and capsule templates
├── scripts/
│   ├── validate.py                 integrated Task 1–7 structural gate
│   ├── evaluate_routing.py         executable premise/delegation/review calculations
│   ├── evaluate_research_gate.py   executable research/pilot/scale decisions
│   ├── validate_orchestration.py   registry/ledger schema and invariant gate
│   ├── capability_matrix.py        trusted surface capability resolution
│   ├── evaluate_behavior.py        recorded fresh-host run evaluator CLI
│   └── optimal_challenge/          focused state, capability, and evaluator owners
└── tests/
    ├── scenarios.json              structural trigger/anti-trigger matrix
    ├── research-gate.json          research-before-scale semantic cases
    ├── fixtures/research/          pinned structural evidence, not host proof
    ├── team-routing.json           deterministic routing cases
    ├── behavioral-acceptance.json  fresh-host acceptance contract
    ├── evaluation-manifest.json    pinned A/B/C/D evaluation identity
    └── validation/
        └── test_package.py         integrated package checks
```

## Install / test

### OpenAI / Codex-compatible plugin
This repository contains a local Codex marketplace at `.agents/plugins/marketplace.json`. From PowerShell, set the checkout path once, then add the marketplace and install its plugin:

For development, use an isolated host home and a clean extracted release archive as `$repoPath`. A marketplace install directly from a working checkout can copy ignored scratch files and `.git` into the plugin cache. The [contributor guide](docs/CONTRIBUTING.md) describes the archive and identity checks before release.

```powershell
$repoPath = "C:\path\to\optimal-challenge-plugin"
codex plugin marketplace add $repoPath
codex plugin add optimal-challenge@optimal-challenge-local
```

For another clean extraction, replace the path in the first command with that extraction's root. Start a new Codex task after installation so it loads the skill. The root `plugin.json` and `.codex-plugin/plugin.json` describe the plugin; `.agents/plugins/marketplace.json` is the manifest required by `codex plugin marketplace add`.

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
Add the GitHub-hosted marketplace, then install the plugin:

```text
/plugin marketplace add Coding-Baby-Penguin/optimal-challenge-plugin
/plugin install optimal-challenge@optimal-challenge-marketplace
```

The repository must contain both `.claude-plugin/marketplace.json` for marketplace discovery and `.claude-plugin/plugin.json` for the plugin itself. Claude Code also supports loading a plugin directory or ZIP for local testing:

```bash
claude --plugin-dir ./optimal-challenge
# For supported Claude Code versions, substitute the packaged release version:
claude --plugin-dir ./optimal-challenge-plugin-<version>.zip
```

The skill appears under the plugin namespace. Implicit model invocation remains enabled so it can assess every request and route only meaningful complexity.

## Upgrade and compatibility

To upgrade an existing Codex installation from the local checkout, update the checkout, then reinstall from the already configured marketplace:

```powershell
git pull
codex plugin add optimal-challenge@optimal-challenge-local
```

Do not re-add an already configured marketplace just to update this plugin. Start a new Codex task after reinstalling so the new skill and metadata load. During local development without a version change, use the plugin-creator cachebuster helper before the same `codex plugin add` command; replace one cachebuster rather than stacking suffixes.

For Claude Code, update the installed marketplace plugin and restart Claude Code:

```bash
claude plugin update optimal-challenge@optimal-challenge-marketplace
```

The 1.1-to-1.2 compatibility contract is intentionally additive:

- Balanced remains the default when no profile is supplied.
- Existing consumers receive additive task-capsule.yaml fields with documented empty or conservative defaults; validation identifies custom consumers that reject the additions.
- The platform-codex.md and platform-claude.md filenames remain stable.
- `.optimal-challenge/` remains ignored and reconstructable; it is disposable runtime state, not project truth.
- `docs/PROJECT-STATE.md` remains the only canonical project state; upgrading creates no second checkpoint or roadmap.
- Fresh-host behavioral acceptance remains `UNVERIFIED` until isolated Task 10 runs pass. The version bump and repository tests do not establish observed host support or provider budget enforcement.

## Validate

```bash
python scripts/validate.py
python -m unittest discover -v
python scripts/adversarial_review.py
python scripts/evaluate_routing.py tests/team-routing.json
python scripts/evaluate_research_gate.py tests/research-gate.json --evidence-registry tests/fixtures/research/trusted-evidence.json
```

Use Python 3.12 and install pinned development-only schema dependencies from `requirements-dev.txt` into a disposable target as shown in [`config/README.md`](config/README.md). The integrated validator checks manifest consistency, routing calculations, valid orchestration state, capability contracts, behavioral fixture identity, skill/reference integrity, and the absence of active components. It reports fresh-host behavioral acceptance as `UNVERIFIED` until Task 10 supplies isolated recorded runs; structural success is not host-model proof.

## Configuration

Project-maintenance values are defined once in [`config/project.json`](config/project.json) and documented in [`config/README.md`](config/README.md). Platform-required manifests remain in their required locations and are validated against that central configuration. Real secrets never belong in committed configuration.

The supported one-line programmatic task override is:

```python
load_effective_config(root, task_override={"mode": "team-requested", "profile": "quality"})
```

Always use `load_effective_config(...)`; do not manually merge built-ins, committed defaults, the ignored local override, and the current request.

## Adaptation and self-improvement

Normal tasks should write at most a tiny experience delta when the host/workflow supports durable state. The adaptation references are intentionally dormant until repeated evidence accumulates.

A skill improvement may be evaluated autonomously, but **actual self-modification requires a writable versioned skill/plugin workspace**. An installed/hosted immutable ZIP cannot safely rewrite itself; in that environment the workflow records an evolution candidate for the next packaging/deployment cycle instead of pretending a change was deployed.

No active hooks, MCP servers, monitors, or background services are included in v1.2. This is intentional: active components are promoted only after a deterministic recurring pattern proves their per-trigger cost worthwhile.

## Suggested state placement

Use the templates only when persistent multi-pass work needs them. Do not load all state files into every task.

- Local repo/Codex: keep current state and the development path together in [`docs/PROJECT-STATE.md`](docs/PROJECT-STATE.md). Rewrite it at meaningful milestones; do not create parallel checkpoint or roadmap files.
- Cloud/project chat: store only durable project state in project/cloud files; treat individual chats as disposable working contexts.

On resume, compare the project-state file with the source tree and current version-control state before acting. Source and tests remain authoritative if recorded state has become stale.

## Verification note

The included automated tests verify package structure, formulas, state invariants, policy boundaries, and evaluation-data integrity. They do not prove that every host model will route identically or that a provider enforces an advisory ceiling. Codex local, OpenAI API/Agents SDK, Claude Code local, and Anthropic API/Agent SDK capabilities remain `policy-only` or `unsupported` until exact-surface/version evidence and fresh isolated acceptance runs exist.

Required failures use `Succeeded`, `Failed`, `Partial`, `Blocked`, or `Degraded`. A non-success result includes the failed operation, evidence, impact, retry/fallback state, and one recovery action. Exit code 0, a queued operation, or an upload acknowledgement alone is never completion evidence.
