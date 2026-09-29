# Agent-Team Optimisation Implementation Plan

> **Historical, superseded plan.** Use the current [holistic quality recovery plan](2026-09-29-holistic-quality-recovery.md) and [project state](../../PROJECT-STATE.md) for active work. The artifact pins, authority order, subagent instruction and checkboxes below describe the earlier plan and are not current execution guidance; the historical body is preserved for audit.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release Optimal Challenge 1.2.0 as a lightweight, testable policy plugin that chooses when and how to use agent teams, budgets, questions, continuity, and independent review.

**Architecture:** Keep `SKILL.md` as the small always-on router and place detailed behavior in lazy policy modules. Add dependency-free Python configuration, scoring, state-validation, packaging, and evaluation helpers so the research calculations and safety contracts are machine-checkable without turning the plugin into a hosted orchestration service.

**Tech Stack:** Markdown/YAML policy and templates, JSON/JSON Schema configuration, Python 3 standard library, `unittest`, Codex and Claude plugin manifests.

**Spec:** `docs/superpowers/specs/2026-09-26-agent-team-optimisation-design.md`

## Global Constraints

- Release version is `1.2.0`; all version-bearing manifests and package paths must agree with `config/project.json`.
- `skills/optimal-challenge/SKILL.md` remains at or below 350 body words and must explicitly link every lazy reference module.
- Default execution is `mode=auto`, `profile=balanced`; the direct fast path shows no profile question or bookkeeping.
- Configuration precedence is system/developer/host/repository authority, current-request constraints, `.optimal-challenge/orchestration.local.json`, `config/orchestration.json`, then built-in defaults.
- No provider model names, volatile prices, credentials, active hooks, MCP servers, monitors, or background services are added.
- Advisory limits must never be presented as enforced; measurement and enforcement remain separate.
- `docs/PROJECT-STATE.md` remains canonical project state; team registry and allocation ledger remain reconstructable and gitignored.
- Exact specialists are additional workers beyond the coordinator; effective maximum is `min(32, detected_host_max)`.
- Every required check fails closed or reports `Failed`, `Partial`, `Blocked`, or `Degraded` with evidence and a recovery action.
- The implementation requires an independent score of at least 9.0/10 with no unresolved high-severity finding before release.

## Review Focus

- Conflicting invocation controls (`inline-only` plus exact specialists) must produce one resolution question, not a silent override; Task 2 owns the test.
- Estimated or unavailable usage must never create false available capacity after timeout, retry, or late reconciliation; Task 3 owns the mutation-sequence tests.
- A settled premise decision must survive resume/rehydrate and never be re-asked without contradictory evidence; Tasks 2 and 5 own the tests.
- Stale, wrong-surface, or conflicting capability evidence must fail closed to `unknown` and an explicit fallback; Task 6 owns the test.
- Baseline/candidate evaluation must reject wrong artifacts, cache leakage, changed fixtures, or insufficient statistical evidence; Task 7 owns the test.

---

### Task 1: Central Orchestration Configuration

**Files:**
- Create: `config/orchestration.schema.json`
- Create: `config/orchestration.json`
- Create: `scripts/orchestration_config.py`
- Create: `tests/validation/test_orchestration_config.py`
- Modify: `config/README.md`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `load_effective_config(root: Path, task_override: Mapping[str, Any] | None = None, detected_host_max: int | None = None) -> dict[str, Any]`
- Produces: `validate_config(config: Mapping[str, Any], detected_host_max: int | None = None) -> list[str]`
- Produces: `merge_known(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]`

- [ ] **Step 1: Write failing configuration tests**

Add tests named `test_balanced_auto_defaults_are_quiet`, `test_task_override_beats_local_and_committed`, `test_unknown_key_fails`, `test_invalid_measurement_enforcement_pair_fails`, `test_custom_weights_sum_to_one`, `test_custom_margin_override_defaults_false`, and `test_exact_specialists_uses_minimum_host_limit`. Assert the exact modes, profiles, bounds, and precedence from the spec.

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `python -m unittest -v tests.validation.test_orchestration_config`

Expected: FAIL because `scripts.orchestration_config` and the configuration files do not exist.

- [ ] **Step 3: Add the schema and committed Balanced/auto instance**

Define closed JSON objects for mode, profile, objective weights, team limits, premise gate, verification, persistence/privacy, and budget `{unit, limit, measurement, enforcement, measurement_source, soft_threshold}`. Allow `exact_specialists` from 0 to 32, `delegation_margin` from 1 to 12, and `allow_mode_margin_override: false`.

- [ ] **Step 4: Implement the dependency-free loader and validator**

`load_effective_config` loads built-ins, `config/orchestration.json`, optional ignored `.optimal-challenge/orchestration.local.json`, then task overrides. `validate_config` returns actionable path-qualified errors and applies dynamic host bounds and cross-field combinations that JSON Schema cannot express.

- [ ] **Step 5: Document the single access path and ignore the local override**

Add `.optimal-challenge/orchestration.local.json` coverage to `.gitignore` through the existing `.optimal-challenge/` rule documentation. In `config/README.md`, document every key, source, default, allowed value, precedence, and advisory/enforced distinction.

- [ ] **Step 6: Run the focused tests**

Run: `python -m unittest -v tests.validation.test_orchestration_config`

Expected: all configuration tests PASS.

- [ ] **Step 7: Commit**

```powershell
git add config/orchestration.schema.json config/orchestration.json config/README.md .gitignore scripts/orchestration_config.py tests/validation/test_orchestration_config.py
git commit -m "Add orchestration configuration contract"
```

### Task 2: Premise, Delegation, Review, and Utility Calculations

**Files:**
- Create: `scripts/evaluate_routing.py`
- Create: `tests/team-routing.json`
- Create: `tests/validation/test_routing_evaluator.py`

**Interfaces:**
- Consumes: `load_effective_config(...)` from Task 1
- Produces: `score_premise(case: Mapping[str, Any]) -> dict[str, Any]`
- Produces: `score_delegation(case: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]`
- Produces: `score_review(case: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]`
- Produces: `compare_routes(routes: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> dict[str, Any]`
- Produces: CLI `python scripts/evaluate_routing.py [tests/team-routing.json]`

- [ ] **Step 1: Write failing calculation tests**

Cover premise risk `WrongnessLikelihoodRating × ReworkCost`, `ExpectedReworkAvoided - UserAttentionCost`, investigate/default/ask boundaries, delegation benefit-minus-cost arithmetic, Economy/Balanced/Quality/Custom margins, review value/product/cost thresholds, normalized utility weights, and inline tie-breaking.

- [ ] **Step 2: Add failing authority and UX tests**

Add cases for `inline-only`, `auto`, `team-requested`, exact specialists 0/1/above-cap, Custom margin override on/off, mutually incompatible explicit controls, user-mandated independent review, settled decision IDs, contradictory new evidence, and no profile chatter on direct requests.

- [ ] **Step 3: Run the evaluator tests and verify failure**

Run: `python -m unittest -v tests.validation.test_routing_evaluator`

Expected: FAIL because the evaluator is absent.

- [ ] **Step 4: Implement the four pure decision functions**

Each result contains `route`, factor values, cited evidence IDs, threshold/margin, `observed|estimated|unknown` provenance, and a human-readable reason. Reject out-of-range or unexplained scores. Exact-agent constraints retain the calculation but override economic margins only within authority, availability, and envelope rules.

- [ ] **Step 5: Add two-sided and boundary scenarios**

Populate `tests/team-routing.json` with fixed IDs for no-delegation traps, high-value delegation, premise traps, continuity decisions, review availability, exact-agent requests, and question-repeat suppression. Every case declares expected route and prohibited behaviors.

- [ ] **Step 6: Run the focused evaluator gate**

Run: `python -m unittest -v tests.validation.test_routing_evaluator`

Run: `python scripts/evaluate_routing.py tests/team-routing.json`

Expected: tests PASS and CLI prints `TEAM ROUTING VALIDATION PASSED` with the case count.

- [ ] **Step 7: Commit**

```powershell
git add scripts/evaluate_routing.py tests/team-routing.json tests/validation/test_routing_evaluator.py
git commit -m "Add testable routing calculations"
```

### Task 3: Team Registry and Allocation Ledger

**Files:**
- Create: `config/team-registry.schema.json`
- Create: `config/allocation-ledger.schema.json`
- Create: `scripts/orchestration_state.py`
- Create: `scripts/validate_orchestration.py`
- Create: `tests/validation/test_orchestration_state.py`
- Create: `tests/fixtures/orchestration/`

**Interfaces:**
- Consumes: configuration semantics from Task 1
- Produces: `apply_ledger_event(ledger: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]`
- Produces: `recover_state(registry: Mapping[str, Any], ledger: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], list[str]]`
- Produces: `validate_orchestration_state(registry: Mapping[str, Any], ledger: Mapping[str, Any]) -> list[str]`
- Produces: CLI `python scripts/validate_orchestration.py --registry <path> --ledger <path>`

- [ ] **Step 1: Write failing schema and cross-record tests**

Test logical-ID/key equality, unique assignments, trust evidence references, shared transaction/snapshot versions, registry-to-reservation integrity, capability/enforcement compatibility, and quarantine of corrupt or stale entries.

- [ ] **Step 2: Write failing ledger mutation-sequence tests**

Test start, complete, cancel, failed, timeout, retry start/complete, late observed report, estimated reconciliation, unavailable usage, funded reservation overrun, unfunded whole-job overrun, reconciliation failure, advisory reset, torn snapshot, and concurrent reservations.

- [ ] **Step 3: Run the state tests and verify failure**

Run: `python -m unittest -v tests.validation.test_orchestration_state`

Expected: FAIL because schemas and state helpers are absent.

- [ ] **Step 4: Add closed registry and ledger schemas**

Use the exact states and balance fields from the spec. Require non-negative amounts, version/transaction fields, evidence pointers, measurement/enforcement provenance, terminal evidence, and reset/reconciliation history.

- [ ] **Step 5: Implement immutable ledger transitions**

`apply_ledger_event` returns a new ledger, increments transaction/reconciliation versions, preserves `available + reserved + funded_consumed = ceiling`, records `funded_reservation_overrun` as a subset of funded consumption, and records beyond-ceiling use only as `unfunded_consumed` with degraded/blocked status.

- [ ] **Step 6: Implement cross-record validation and recovery**

`recover_state` accepts only hash/version-verified last-known-good state and idempotent evidence replay. Missing evidence returns unknown balances and blocks new reservations; it never invents availability from source files or a stale registry.

- [ ] **Step 7: Run state validation**

Run: `python -m unittest -v tests.validation.test_orchestration_state`

Expected: all mutation and corruption tests PASS.

- [ ] **Step 8: Commit**

```powershell
git add config/team-registry.schema.json config/allocation-ledger.schema.json scripts/orchestration_state.py scripts/validate_orchestration.py tests/fixtures/orchestration tests/validation/test_orchestration_state.py
git commit -m "Add team state and allocation ledger contracts"
```

### Task 4: Team and Capsule Templates

**Files:**
- Create: `skills/optimal-challenge/templates/TEAM-CHARTER.md`
- Create: `skills/optimal-challenge/templates/TEAMMATE-CAPSULE.yaml`
- Create: `skills/optimal-challenge/templates/RETURN-CAPSULE.yaml`
- Modify: `skills/optimal-challenge/templates/task-capsule.yaml`
- Modify: `skills/optimal-challenge/templates/QUESTION-BUNDLE.md`
- Modify: `skills/optimal-challenge/templates/PROJECT-STATE.md`
- Create: `tests/validation/test_team_templates.py`

**Interfaces:**
- Consumes: field names from Tasks 1–3
- Produces: stable template fields consumed by the runtime policy and validators in later tasks

- [ ] **Step 1: Write failing template-contract tests**

Assert required fields for charter ownership/budget/interruptions; teammate identity/continuity/evidence/trust; task premise/profile/capability/allocations/authority/escalation; return status/changes/evidence/decisions/risks/needs/usage; question decision IDs/reversible defaults; and project-state unresolved assignments.

- [ ] **Step 2: Run the template tests and verify failure**

Run: `python -m unittest -v tests.validation.test_team_templates`

Expected: FAIL on missing new templates and fields.

- [ ] **Step 3: Add the minimal templates**

Keep each below 10 KB. Use safe empty values and fake placeholders only; prohibit secrets, transcripts, and unverified beliefs. Make `NEEDS_CAPABILITY`, `NEEDS_DECISION`, `complete`, `partial`, `blocked`, `degraded`, and `failed` explicit return statuses.

- [ ] **Step 4: Run template tests**

Run: `python -m unittest -v tests.validation.test_team_templates`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/optimal-challenge/templates tests/validation/test_team_templates.py
git commit -m "Add agent-team capsule templates"
```

### Task 5: Runtime Policy and Router Integration

**Files:**
- Create: `skills/optimal-challenge/references/premise-validation.md`
- Create: `skills/optimal-challenge/references/team-orchestration.md`
- Create: `skills/optimal-challenge/references/team-continuity.md`
- Create: `skills/optimal-challenge/references/cost-quality-routing.md`
- Modify: `skills/optimal-challenge/references/delegation-budget.md`
- Modify: `skills/optimal-challenge/references/verification.md`
- Modify: `skills/optimal-challenge/references/context-management.md`
- Modify: `skills/optimal-challenge/references/continuity-collaboration.md`
- Modify: `skills/optimal-challenge/SKILL.md`
- Modify: `tests/scenarios.json`
- Modify: `tests/validation/test_package.py`

**Interfaces:**
- Consumes: calculation names, configuration paths, template fields, and state contracts from Tasks 1–4
- Produces: lazy policy modules addressable from the router

- [ ] **Step 1: Add failing policy-presence and anti-pattern tests**

Assert router links all four new modules, remains at most 350 words, enters the premise gate only after rejecting direct work, preserves explicit authority, and loads team policies only for real multi-workstream/delegation decisions.

- [ ] **Step 2: Add failing behavioral scenario coverage**

Extend `tests/scenarios.json` with investigate/default/ask premise cases, inline/auto/team-requested/exact-specialist cases, resume/rehydrate/fresh cases, mandatory-review-unavailable behavior, advisory ceiling exhaustion, and settled-question replay.

- [ ] **Step 3: Run current tests and verify the intended failures**

Run: `python -m unittest -v tests.validation.test_package`

Expected: FAIL because new references and policy phrases are absent.

- [ ] **Step 4: Write focused lazy modules**

Move formulas, anchors, margins, authority rules, allocation behavior, prompt-layer stability, and interruption rules into the four new modules. Extend existing modules rather than duplicating failure visibility, checkpointing, or verification contracts.

- [ ] **Step 5: Update the small router**

Add only trigger-level links and preserve the direct path, approved-plan reuse, failure-visibility trigger, Superpowers boundary, and 350-word limit.

- [ ] **Step 6: Run the package and adversarial gates**

Run: `python scripts/validate.py`

Run: `python -m unittest -v tests.validation.test_package`

Run: `python scripts/adversarial_review.py`

Expected: all PASS; all reference files are explicitly linked and no unconditional team machinery appears in `SKILL.md`.

- [ ] **Step 7: Commit**

```powershell
git add skills/optimal-challenge/SKILL.md skills/optimal-challenge/references tests/scenarios.json tests/validation/test_package.py
git commit -m "Add agent-team routing policy"
```

### Task 6: Platform Capability Matrices

**Files:**
- Modify: `skills/optimal-challenge/references/platform-codex.md`
- Modify: `skills/optimal-challenge/references/platform-claude.md`
- Create: `scripts/capability_matrix.py`
- Create: `tests/validation/test_capability_matrix.py`

**Interfaces:**
- Consumes: host limits from Task 1 and failure states from Task 5
- Produces: `resolve_capability(surface: str, live: Mapping[str, Any] | None, acceptance: Mapping[str, Any] | None, policy: Mapping[str, Any], now: datetime) -> dict[str, Any]`

- [ ] **Step 1: Write failing capability precedence tests**

Cover matching live evidence, unexpired acceptance evidence, policy-only fallback, wrong surface/version, expiry, missing provenance, conflicting observations, detector failure, and explicit unsupported behavior.

- [ ] **Step 2: Run the capability tests and verify failure**

Run: `python -m unittest -v tests.validation.test_capability_matrix`

Expected: FAIL because resolver is absent.

- [ ] **Step 3: Implement fail-closed resolution**

Return support level, evidence source, expiry, and required fallback. Unknown uses the same inline/rehydrate/advisory/blocked fallback as unsupported. Do not infer API/SDK executable support from plugin documentation.

- [ ] **Step 4: Expand both platform references**

Publish separate rows for Codex local/plugin, OpenAI API/Agents policy mapping, Claude Code/plugin, and Anthropic API/Agent SDK policy mapping. Include resume, pause/cancel, measurement, enforcement, persistence/privacy, parallelism, and tracing.

- [ ] **Step 5: Run tests**

Run: `python -m unittest -v tests.validation.test_capability_matrix`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add skills/optimal-challenge/references/platform-codex.md skills/optimal-challenge/references/platform-claude.md scripts/capability_matrix.py tests/validation/test_capability_matrix.py
git commit -m "Add evidence-aware platform capabilities"
```

### Task 7: Behavioral Evaluation and v1.1 Baseline

**Files:**
- Create: `tests/behavioral-acceptance.json`
- Create: `tests/evaluation-manifest.json`
- Create: `tests/baselines/v1.1.json`
- Create: `scripts/evaluate_behavior.py`
- Create: `tests/validation/test_behavioral_evaluation.py`

**Interfaces:**
- Consumes: scenario IDs and evaluator outputs from Task 2; capability surfaces from Task 6
- Produces: `validate_run_bundle(bundle: Mapping[str, Any], manifest: Mapping[str, Any]) -> list[str]`
- Produces: `summarize_arm(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]`
- Produces: `compare_arms(baseline: Mapping[str, Any], candidate: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]`
- Produces: CLI `python scripts/evaluate_behavior.py --manifest tests/evaluation-manifest.json --baseline <baseline-results.json> --candidate <candidate-results.json>`

- [ ] **Step 1: Write failing manifest and artifact-identity tests**

Require prompt/fixture hashes, host/surface, model/reasoning, tool set, profile/config, evaluator/rubric version, randomization, run count, aggregation, margins, commit/tag, archive SHA-256, manifest version, cachebuster, install source, and installed-plugin read-back.

- [ ] **Step 2: Write failing isolation and statistics tests**

Reject changed fixtures/evaluator, wrong plugin version, cache/config/registry leakage, insufficient runs, unsafe failures, inconclusive confidence intervals reported as improvement, and candidate regressions beyond the exact 0.10 quality, 5% simple-task, 0.20 quality-gain, and 10% critical-path margins.

- [ ] **Step 3: Run the behavioral-evaluation tests and verify failure**

Run: `python -m unittest -v tests.validation.test_behavioral_evaluation`

Expected: FAIL because the files and evaluator are absent.

- [ ] **Step 4: Implement bundle validation and comparison**

Use standard-library statistics and deterministic bootstrap sampling seeded from the manifest. Report run count, mean quality, median cost/latency, pass rate, 95% interval, proxy-only measurements, and `pass|fail|inconclusive`.

- [ ] **Step 5: Define acceptance and four-arm fixtures**

Add direct, premise, delegation, continuity, budget, review, capability-fallback, and failure cases. Define arms A (v1.1), B (always delegate), C (economic gate without continuity), and D (full 1.2 candidate). Arm B is evaluation-only.

- [ ] **Step 6: Pin the current v1.1 baseline subject**

Use commit `c3c379ab5429d1bfef3c145260247bc72f8844f9` as the v1.1 behavior baseline. Record the verified archive hash, cachebuster, installed version read-back, raw result IDs, and manifest hash only after running isolated fresh tasks; until then mark the baseline `unverified` and do not make comparative claims.

- [ ] **Step 7: Run structural evaluation tests**

Run: `python -m unittest -v tests.validation.test_behavioral_evaluation`

Expected: PASS for schemas/fixtures/comparison math; host behavioral results may remain explicitly unverified until Task 10.

- [ ] **Step 8: Commit**

```powershell
git add tests/behavioral-acceptance.json tests/evaluation-manifest.json tests/baselines/v1.1.json scripts/evaluate_behavior.py tests/validation/test_behavioral_evaluation.py
git commit -m "Add behavioral evaluation contracts"
```

### Task 8: Release Metadata, Documentation, and Integrated Validation

**Files:**
- Modify: `config/project.json`
- Modify: `plugin.json`
- Modify: `.codex-plugin/plugin.json`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `skills/optimal-challenge/agents/openai.yaml`
- Modify: `scripts/validate.py`
- Modify: `scripts/adversarial_review.py`
- Modify: `tests/validation/test_package.py`
- Modify: `README.md`
- Modify: `submission/plugin-submission.md`
- Modify: `docs/PROJECT-STATE.md`

**Interfaces:**
- Consumes: all paths, commands, policies, templates, schemas, and evaluators from Tasks 1–7
- Produces: canonical 1.2.0 metadata and one integrated validation entry point

- [ ] **Step 1: Add failing integrated path/version tests**

Require project-config paths for orchestration config/schema, registry/ledger schemas, routing/behavior scenarios, evaluators, and validators. Require version `1.2.0` everywhere supported; assert the Codex marketplace retains its supported versionless source/policy shape.

- [ ] **Step 2: Run package tests and verify failure**

Run: `python -m unittest -v tests.validation.test_package`

Expected: FAIL on missing 1.2.0 metadata and integrated paths.

- [ ] **Step 3: Update canonical configuration and manifests**

Bump portable, Codex, Claude, and Claude marketplace versions to `1.2.0`; preserve `Coding Baby Penguin`, repository/support URLs, and Codex marketplace policy fields. Update `agents/openai.yaml` and Codex listing text/default prompts to describe cost-aware team formation without implying automatic budget enforcement.

- [ ] **Step 4: Integrate all new validators**

Make `scripts/validate.py` call or import configuration, routing, orchestration-state, capability, and behavioral-structure validators. Extend adversarial checks for unconditional spawning/review, provider literals, transcript persistence, advisory-as-enforced claims, calculation/route disagreement, and orphan schemas/templates.

- [ ] **Step 5: Update user and submission documentation**

Document invocation modes, four profiles, one-line task overrides, persistent paths, premise/question behavior, budget honesty, logical teammate continuity, selective review, limitations, tests, package layout, and the policy/runtime boundary. Refresh project state to the exact next action and unresolved host acceptance status.

- [ ] **Step 6: Run the integrated repository gate**

Run: `python scripts/validate.py`

Run: `python -m unittest discover -v`

Run: `python scripts/adversarial_review.py`

Expected: all PASS with no skipped required checks.

- [ ] **Step 7: Commit**

```powershell
git add config/project.json plugin.json .codex-plugin/plugin.json .claude-plugin skills/optimal-challenge/agents/openai.yaml scripts/validate.py scripts/adversarial_review.py tests/validation/test_package.py README.md submission/plugin-submission.md docs/PROJECT-STATE.md
git commit -m "Prepare Optimal Challenge 1.2.0"
```

### Task 9: Deterministic Packaging and Source Comparison

**Files:**
- Create: `scripts/package_release.py`
- Create: `tests/validation/test_release_package.py`
- Modify: `config/project.json`
- Modify: `config/README.md`

**Interfaces:**
- Produces: `iter_package_files(root: Path, excludes: Sequence[str]) -> list[Path]`
- Produces: `build_archive(root: Path, output: Path, files: Sequence[Path]) -> str`
- Produces: `compare_archive(root: Path, archive: Path, files: Sequence[Path]) -> list[str]`
- Produces: CLI `python scripts/package_release.py`

- [ ] **Step 1: Write failing deterministic-package tests**

Use a temporary fixture tree to assert sorted POSIX archive paths, hidden manifest inclusion, configured exclusions, fixed ZIP timestamps/permissions, SHA-256 output, no symlinks, and byte-for-byte source/archive comparison.

- [ ] **Step 2: Run package tests and verify failure**

Run: `python -m unittest -v tests.validation.test_release_package`

Expected: FAIL because the packager is absent.

- [ ] **Step 3: Add package excludes and command to project configuration**

Exclude `.git/**`, `dist/**`, caches, ignored `.optimal-challenge/**`, `docs/superpowers/**`, and local/raw evaluation data while retaining plugin manifests, skills, templates, configuration schemas/defaults, README/legal/support files, validators, and distributable tests.

- [ ] **Step 4: Implement deterministic packaging and comparison**

Build `dist/optimal-challenge-plugin-1.2.0.zip`, reopen it, reject unexpected/missing/changed members, print file count and SHA-256, and exit nonzero on any mismatch.

- [ ] **Step 5: Run focused and full package validation**

Run: `python -m unittest -v tests.validation.test_release_package`

Run: `python scripts/package_release.py`

Run: `python scripts/validate.py`

Expected: tests PASS, archive comparison PASS, and a SHA-256 is printed.

- [ ] **Step 6: Commit package tooling, not ignored output**

```powershell
git add scripts/package_release.py tests/validation/test_release_package.py config/project.json config/README.md
git commit -m "Add deterministic release packaging"
```

### Task 10: Independent Review, Official Validation, Installation, and Host Acceptance

**Files:**
- Modify as findings require: files from Tasks 1–9
- Modify after real runs: `tests/baselines/v1.1.json`
- Modify: `docs/PROJECT-STATE.md`

**Interfaces:**
- Consumes: complete 1.2.0 candidate and behavioral matrix
- Produces: independently reviewed source, verified release archive, installed local candidate, and explicit host acceptance status

- [ ] **Step 1: Run every local validation command from a clean tree**

Run: `python scripts/validate.py`

Run: `python -m unittest discover -v`

Run: `python scripts/adversarial_review.py`

Run: `python scripts/evaluate_routing.py tests/team-routing.json`

Run: `python scripts/package_release.py`

Expected: every required command PASS; no skipped, partial, or degraded result is called success.

- [ ] **Step 2: Run official plugin and skill validators**

Run:

```powershell
python C:\Users\rawwi\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py .
python C:\Users\rawwi\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/optimal-challenge
```

If dependencies are unavailable, install them only into a temporary target and record the environment; do not weaken or skip the gate.

- [ ] **Step 3: Run staged secret and silent-failure scans**

Stage the intended source set, scan token/private-key patterns with boundary-aware expressions, scan authored Python for swallowed exceptions and unconditional success exits, and inspect `git diff --cached --check` plus the staged file list.

- [ ] **Step 4: Obtain a fresh independent implementation review**

Score the implementation against the spec's fixed 10-point rubric. Resolve every high-severity finding and repeat until the exact reviewed revision is at least 9.0/10.

- [ ] **Step 5: Commit the reviewed implementation**

```powershell
git commit -m "Release Optimal Challenge 1.2.0"
```

- [ ] **Step 6: Reinstall through the supported local marketplace flow**

Run:

```powershell
python C:\Users\rawwi\.codex\skills\.system\plugin-creator\scripts\read_marketplace_name.py --marketplace-path .agents/plugins/marketplace.json
python C:\Users\rawwi\.codex\skills\.system\plugin-creator\scripts\update_plugin_cachebuster.py .
codex plugin add optimal-challenge@optimal-challenge-local
codex plugin list
```

Require the marketplace helper to print `optimal-challenge-local` before constructing the add command. Verify installed-plugin read-back. Restore the canonical `.codex-plugin/plugin.json` version with `apply_patch`, rerun manifest validation, and verify the source tree matches the reviewed commit except for intentionally recorded baseline evidence.

- [ ] **Step 7: Run isolated host behavioral arms**

Run v1.1 A and 1.2 B/C/D arms in clean fresh tasks with pinned artifacts and counterbalanced order. Persist sanitized raw result IDs and aggregates, reject contaminated/wrong-version runs, then run `python scripts/evaluate_behavior.py --manifest tests/evaluation-manifest.json --baseline <baseline-results.json> --candidate <candidate-results.json>`. If a surface cannot be exercised, mark it unverified and remove the corresponding support claim.

- [ ] **Step 8: Refresh final evidence and package after acceptance changes**

Update `tests/baselines/v1.1.json` and `docs/PROJECT-STATE.md`, rerun the complete local/official/secret/package gate, rebuild the archive, and obtain a final independent review if any source behavior changed.

- [ ] **Step 9: Commit acceptance evidence and push**

```powershell
git add tests/baselines/v1.1.json docs/PROJECT-STATE.md
git commit -m "Record 1.2.0 acceptance evidence"
git push origin main
```

Verify `git status --short --branch`, `git rev-parse HEAD`, and `git ls-remote origin refs/heads/main` agree. Do not claim an OpenAI portal submission or GitHub release unless those separate external actions are explicitly authorized and verified.
