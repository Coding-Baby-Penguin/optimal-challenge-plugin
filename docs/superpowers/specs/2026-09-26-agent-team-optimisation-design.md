# Agent-team optimisation design

## Status

- **Release target:** Optimal Challenge 1.2.0
- **Design status:** Approved in conversation on 2026-09-26; awaiting review of this written specification
- **Implementation boundary:** Policy, schemas, templates, documentation, and validation only

## Purpose

Optimal Challenge 1.2.0 will improve the usefulness of agent teams without making additional agents the default. It will decide whether a premise needs validation, whether another worker is economically justified, whether an existing logical teammate should continue, and whether independent review adds enough information to justify its cost.

The release will preserve the plugin's lightweight architecture. `skills/optimal-challenge/SKILL.md` remains the small always-on router, while detailed team behavior stays in lazy-loaded references and templates. This release will not introduce a hosted orchestration service, provider API client, telemetry backend, live price table, or deterministic dollar-budget enforcement.

## Success criteria

The release is complete when:

1. Simple, stable, low-risk requests still take the direct fast path without team machinery.
2. Material assumptions are inspected or surfaced before expensive decomposition.
3. Delegation is based on expected benefit minus briefing, coordination, merge, review, and rework costs—not on available agent slots alone.
4. Multi-pass work can retain a logical teammate while choosing among resume, rehydrate, and fresh execution contexts.
5. Worker inputs and outputs use compact, provider-neutral capsules with explicit authority and escalation boundaries.
6. Economy, Balanced, and Quality profiles change resource and review policy without naming particular commercial models or embedding volatile prices.
7. Independent review is selected according to consequence, oracle strength, and expected detection value.
8. Codex/OpenAI and Claude policy adapters describe how their available orchestration primitives implement the same core semantics.
9. New structural and behavioral regression cases cover both desired routing and costly anti-patterns.
10. All required repository, package, adversarial, platform, documentation, secret, and archive checks pass before release publication.
11. Users can select invocation mode and resource profile for one request or persist a preference through one documented configuration path, without being prompted on the direct fast path.
12. Premise, delegation, review, and budget decisions expose their qualitative calculation inputs and decision reason instead of relying on unexplained intuition.

## Design principles

- Understand before multiplying work.
- Keep the coordinator responsible for the user's contract, assumptions, budget, task graph, integration, and final result.
- Treat every additional worker and reviewer as an investment that must earn its cost.
- Persist facts, decisions, evidence, and source pointers rather than transcripts.
- Preserve logical identity only when continuity has value; refresh execution context when history becomes baggage.
- Prefer safe reversible defaults and bundle unavoidable user decisions.
- Keep project truth in authoritative source, tests, decisions, and `docs/PROJECT-STATE.md`; runtime team state never overrides them.
- Report retries, skipped checks, fallbacks, partial results, and unfinished work through the existing failure-visibility contract.

## Scope

### Included in 1.2.0

- premise gate and enhanced question-bundle policy;
- explicit economic delegation and review gates;
- logical teammate identity and continuity policy;
- task, teammate, and return capsule templates;
- a non-authoritative, reconstructable team-registry schema;
- Economy, Balanced, and Quality resource profiles;
- provider-neutral capability classes;
- Codex/OpenAI and Claude policy adapters;
- routing evaluation data and validation coverage;
- manifest, configuration, README, project-state, submission, and release-package updates.

### Deferred

- executable multi-provider orchestration runtime;
- live provider API calls or native session adapters;
- enforced monetary budgets and rate-limit scheduling;
- provider pricing registry;
- usage telemetry, dashboards, and learned thresholds;
- broad swarm mode or peer-to-peer agent organisations;
- active hooks, MCP servers, monitors, or background services.

These deferred capabilities belong to a later release because prompt and policy files cannot reliably enforce atomic task claims, dollar caps, provider rate limits, or cost ledgers.

## Architecture

### Router

`skills/optimal-challenge/SKILL.md` will remain within its existing word budget. It will retain the direct fast path and add only the minimum triggers needed to reach the new lazy modules:

- load premise validation when an unresolved assumption could cause material rework;
- load team orchestration and cost-quality routing for genuine multi-workstream work or proposed delegation;
- load team continuity when a logical worker may be reused across related assignments;
- retain the existing failure-visibility trigger whenever errors, warnings, retries, fallbacks, or incomplete work appear.

Every new reference file must be explicitly linked from `SKILL.md`; orphan references remain a validation failure.

### Premise gate

The premise gate is entered only after the router rejects the stable, single-step, low-risk direct fast path. Direct requests do not incur premise scoring, profile disclosure, or decision bookkeeping.

Before decomposition, the coordinator records or infers:

- goal and observable success criteria;
- known constraints and authoritative evidence;
- material assumptions and unknowns;
- reversible defaults;
- irreversible or high-rework decisions.

The coordinator first investigates questions that tools, repository state, or existing decisions can answer cheaply. It asks the user only when an unresolved choice has material rework risk and no safe reversible default. Currently knowable user-only decisions are presented as one question bundle with recommendations, impact, and next steps.

The premise gate uses normative ordinal scores in this policy release. They make routing consistent but do not imply measured probabilities, currency, or empirical precision.

For each unresolved premise, the coordinator applies:

```text
PremiseRisk = WrongnessLikelihoodRating × ReworkCost(wrong)
QuestionValue = ExpectedReworkAvoided - UserAttentionCost
```

When measured probabilities and costs are unavailable, each factor uses these anchored ordinal scores rather than invented percentages or currency:

| Factor | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| `WrongnessLikelihoodRating` | authoritative evidence establishes the chosen assumption | unlikely; one weak assumption | plausible alternatives remain | conflicting evidence or uncertainty is so high that no default is defensible |
| `ReworkCost` | no downstream change | local reversible edit | multi-step or multi-file redo | architecture, irreversible action, or broad parallel waste |
| `UserAttentionCost` | no interruption | one quick low-context choice | context switch or several related choices | sensitive decision, external coordination, or slow response |

`PremiseRisk` is the 0-to-9 product. `ExpectedReworkAvoided` uses an independently justified 0-to-9 score: 0 means the answer prevents no work; 1–3 prevents a local reversible edit; 4–6 prevents multi-step, multi-file, or one-worker rework; and 7–9 prevents architectural, irreversible, or broad parallel waste. It cannot exceed `PremiseRisk`. `QuestionValue` subtracts user-attention cost. A user question is blocking only when `PremiseRisk >= 4`, `QuestionValue > 0`, the answer changes the work graph or an irreversible decision, and no cheap investigation or safe reversible default resolves it. Lower scores are investigated or defaulted without pausing. The decision record captures factor ratings, evidence, chosen default or question ID, and why proceeding is cheaper than asking—or vice versa.

Boundary examples are normative: a discoverable repository fact is investigated even when risk is high; a reversible file-format choice with risk below 4 is defaulted and recorded; user-owned versus service-owned authentication is asked before decomposition when its risk is at least 4 and it changes the architecture.

Material answers receive stable decision IDs in authoritative durable state. Resume and rehydrate capsules carry only the relevant IDs. The coordinator never re-asks a settled decision unless new contradictory evidence invalidates it, and must explain that evidence. A later question bundle is limited to newly discovered user-only blockers and must not repeat choices knowable at the first pause.

### Economic delegation gate

A candidate work package is delegated only when expected benefits exceed total coordination cost. Benefits include parallel critical-path progress, independent evidence, specialist capability, useful context isolation, and expected quality uplift. Costs include worker setup, context transfer, merge effort, review, retries, and overlapping edits.

The decision calculation is:

```text
D(t) = B_parallel + B_independence + B_context + B_quality
       - (C_setup + C_transfer + C_merge + C_review_rework)
```

Each delegation factor uses this common evidence-backed scale:

| Score | Benefit anchor | Cost anchor |
|---|---|---|
| 0 | absent | absent or negligible |
| 1 | minor convenience; no critical-path or quality change | small briefing or merge overhead |
| 2 | material latency, independence, isolation, or specialist gain | material context, coordination, review, or overlap cost |
| 3 | decisive critical-path, safety, domain, or quality gain | dominant cost, conflicting edits, or likely rework |

A **strong benefit** is any benefit scored 2 or 3. Required delegation margins are Economy `D(t) >= 3`, Balanced `D(t) >= 1`, and Quality `D(t) >= 1`; Custom accepts an integer margin from 1 to 12. `team-requested` lowers the Economy margin to 1 but never permits zero/negative-value spawning; it does not alter a Custom margin unless the user's Custom configuration explicitly sets `allow_mode_margin_override: true`. Delegate only when the margin is met, at least one benefit is strong, the work package has an observable done condition, and its reservation fits the active job envelope. If routes tie or evidence is insufficient, stay inline. The task capsule records component ratings, cited evidence, required margin, and route; expected-route fixtures fail when the arithmetic and route disagree.

An explicit exact specialist count or independent-agent instruction differs from the `team-requested` preference: it overrides the delegation margin, strong-benefit requirement, and normal three-specialist cap after one optional cost warning. Exact count means workers in addition to the coordinator: zero is `inline-only`, one is one specialist plus the coordinator, and counts above the normal cap are permitted only when slots and the stated envelope exist. The schema accepts integers from 0 to 32; the effective maximum is `min(32, detected_host_max)`. Ambiguous natural language such as “a team of three” is resolved from context or, when it changes cost materially, by one concise question. Exact count never overrides safety, permissions, platform availability, mutually incompatible explicit constraints, or the stated job envelope. If slots or envelope cannot accommodate it, the coordinator asks for one expansion, wait, or route decision rather than silently reducing the count. The economic calculation is still recorded so the user can see the trade-off.

The default decision rules are:

- keep obvious, tightly coupled, small, or same-context work inline;
- never delegate merely because a slot is available;
- avoid parallel edits to the same surface unless ownership is explicitly partitioned;
- prefer an existing matching teammate when relevant state is still useful and independence is not required;
- create a fresh teammate when independent judgment, conflicting responsibilities, different capabilities, or contaminated context justify it;
- cap the normal active team at the coordinator plus three specialists.

Nested delegation remains denied unless the coordinator explicitly grants it in a capability lease.

An explicit user instruction requiring multiple agents or independent review is an execution constraint, not a suggestion to override silently. The coordinator honors it within safety, permissions, platform availability, and the user's stated budget. When the requested route appears materially wasteful, the coordinator may give one concise cost warning or recommend a cheaper route, but proceeds with the explicit constraint unless the user changes it. A request asking whether agents would help is routing advice and uses the economic gate normally.

### Logical teammate continuity

A logical teammate has a stable role identity, responsibility boundary, capability class, relevant state references, assignment history, and lightweight trust evidence. A logical teammate is not the same thing as a retained full conversation.

For each assignment, the coordinator chooses:

- **Resume:** retain the native execution context when the next task is a direct continuation and compact rehydration would lose costly local exploration.
- **Rehydrate:** start a clean execution context with a compact teammate capsule when role continuity matters but earlier conversation history is noisy, oversized, or unnecessary.
- **Fresh:** use a new identity and context when independence is required, responsibilities conflict, or the previous context may bias the result.

The team registry is disposable runtime state. In local repositories its default location is under `.optimal-challenge/`, which is already ignored. Durable facts and decisions are promoted to `docs/PROJECT-STATE.md` or the existing decision ledger; registry content never becomes authoritative project truth.

### Resource profiles and capability classes

The release exposes four user-facing profiles:

- **Economy:** strongest bias toward inline execution, smaller teams, lower capability classes, deterministic verification, and minimal independent review.
- **Balanced:** default profile; permits delegation and targeted review when expected value is positive.
- **Quality:** permits stronger capability classes and broader independent review for consequential or weak-oracle work, while retaining delegation and stop-loss gates.
- **Custom:** permits explicit limits for concurrency, capability classes, review depth, persistence/privacy, interruption policy, and supported budget semantics without weakening safety or truthfulness.

Provider-neutral capability classes are `economy`, `standard`, `reasoning`, and `frontier`, with an optional fast-service modifier. Platform modules map these classes to capabilities available in the current host. The plugin will not hard-code provider model names, prices, or subscription-credit conversions.

The routing rule is the least expensive capability expected to finish efficiently, not the lowest nominal token price. A retry must add information, capability, context, or model strength.

### User controls and precedence

Default behavior is `mode=auto` with `profile=balanced`; it requires no setup and adds no profile message or question to the direct fast path. Supported invocation modes are:

- **inline-only:** do not create specialists unless a safety or explicit independent-review requirement makes the request impossible as stated; explain that conflict rather than silently spawning;
- **auto:** apply premise, delegation, budget, and review gates;
- **team-requested:** actively seek valuable team decomposition while retaining safety, permission, availability, budget, and positive-value constraints.

Users may select Economy, Balanced, Quality, or Custom for one request. Precedence is: system instructions; developer and host instructions; applicable repository instructions; safety and permission constraints within those authorities; explicit current-request constraints; gitignored local project preference; committed project configuration; then the Balanced/auto built-in default. Higher authority always wins. Within one request, an explicit mandatory independent-review or exact-specialist constraint outranks a general mode preference. Mutually impossible same-priority constraints—such as “inline only” and “use two independent specialists”—produce one concise resolution question rather than a silent choice. Invalid or unsupported values fail visibly and fall back only with an explicit degraded notice and safe default.

Committed project defaults live in `config/orchestration.json`, validated by `config/orchestration.schema.json`. Gitignored per-project overrides live in `.optimal-challenge/orchestration.local.json` and use the same shape. One documented policy loader applies the precedence chain; platform adapters must not invent separate settings. The README will show one-sentence task-level examples and both persistent configuration paths. Profile or mode is surfaced only when it materially changes routing, when a user selection cannot be honored, or when the user asks; routine direct work remains quiet.

### Selective verification

Review depth is based on consequence and oracle strength:

- reversible mechanical work with strong deterministic tests receives worker self-checks and direct verification;
- moderate-judgment or multi-file integration may receive one targeted fresh review;
- security, financial, destructive, externally published, or materially consequential weak-oracle work requires independent review when the host can provide it;
- contested research receives source verification rather than generic prose review;
- repeated failure triggers a fresh diagnostic pass, stronger capability, targeted replan, or user escalation—not an unchanged retry loop.

An independent reviewer must receive authoritative inputs and success criteria without inheriting the implementation worker's conclusions as facts.

The review gate applies:

```text
ReviewValue = P(defect) × Impact(defect) × P(review detects defect)
              - ReviewCost
```

The factors use separate anchors:

| Score | `P(defect)` | `Impact` | `P(detection)` | `ReviewCost` |
|---|---|---|---|---|
| 0 | deterministic evidence rules out the defect class | no meaningful consequence | no independent oracle can detect it | negligible automated check |
| 1 | unlikely; simple proven pattern | local and reversible | weak or correlated signal | small context/check cost |
| 2 | plausible; judgment or integration involved | material multi-file or user-visible consequence | distinct evidence likely detects it | material independent pass |
| 3 | repeated failure, novelty, or weak implementation oracle | security, financial, destructive, public, or irreversible consequence | strong independent or deterministic oracle | dominant specialist/context cost |

The product is 0 to 27 before subtracting the 0-to-3 cost. Economy requires net value at least 6, Balanced at least 3, and Quality at least 1; Custom accepts 1 to 27. Explicit review and security, financial, destructive, externally published, or materially consequential weak-oracle work remain mandatory regardless of profile. Non-consequential weak-oracle work uses the calculated gate and reports the limitation without automatically blocking. The coordinator records ratings, evidence, oracle strength, allocation, required margin, and route. Universal review and unexplained omission of mandatory review are both regression failures.

When mandatory independent review is unavailable, the work is `Blocked` before the consequential side effect. It may be `Degraded` only when a named compensating oracle provides meaningful coverage and the user explicitly accepts that limitation; otherwise lack of a reviewer is not silently waived.

### Whole-job utility and cost accounting

The coordinator optimizes the job rather than an isolated model call:

```text
Utility = λquality(ExpectedQuality)
          - λcost(TotalJobCost)
          - λlatency(CriticalPathLatency)
          - λattention(UserInterruptionCost)
          - λrework(ExpectedReworkRisk)

TotalJobCost = input + cache_write + cache_read + output + tools
               + coordination + verification + retry
```

Every route factor is normalized to 0-to-3 before weighting: quality ranges from 0 (success criteria not expected to be met) to 3 (strong evidence of full completion), while cost, latency, attention, and rework range from 0 (negligible) to 3 (dominant). Default weights `(quality, cost, latency, attention, rework)` are Economy `(0.35, 0.35, 0.10, 0.10, 0.10)`, Balanced `(0.45, 0.20, 0.10, 0.10, 0.15)`, and Quality `(0.50, 0.10, 0.05, 0.10, 0.25)`; Custom weights must each be 0 to 1 and sum to 1. The route with greatest utility wins only after mandatory authority, safety, premise, delegation-margin, allocation, and review gates pass. A utility tie stays inline unless independence is mandatory. When inputs cannot be normalized with evidence, utility is explanatory only and cannot override those deterministic gates. Fields are marked observed, estimated, or unknown. A later telemetry-capable runtime may replace estimates with observed values without changing these semantics.

## Components and file changes

### New lazy reference modules

- `skills/optimal-challenge/references/premise-validation.md`
- `skills/optimal-challenge/references/team-orchestration.md`
- `skills/optimal-challenge/references/team-continuity.md`
- `skills/optimal-challenge/references/cost-quality-routing.md`

Existing `delegation-budget.md`, `verification.md`, `platform-codex.md`, `platform-claude.md`, `continuity-collaboration.md`, and `context-management.md` will be extended instead of duplicated. The existing platform filenames remain stable to avoid needless link migration; their content will explain provider-specific mappings.

### New and extended templates

- `TEAM-CHARTER.md`: activated only when the delegation gate creates a real team;
- `TEAMMATE-CAPSULE.yaml`: logical identity, role, relevant durable references, continuity choice, and bounded trust evidence;
- `task-capsule.yaml`: extended with premise references, profile, capability class, retry allowance, authority, and structured escalation;
- `RETURN-CAPSULE.yaml`: status, changes, evidence, decisions, assumptions, risks, needs, and optional observed usage;
- `QUESTION-BUNDLE.md`: extended to distinguish material premises, reversible defaults, and budget/profile decisions;
- `PROJECT-STATE.md`: a small section for durable team decisions and unresolved assignments, without copying the runtime registry.

Capsules must not contain secrets, complete transcripts, or unverified worker beliefs presented as project facts.

Profile and budget choices enter **Required decisions** only when an active ceiling is reached, the requested route cannot fit the active limit, or the choice materially changes irreversible work. Otherwise the coordinator uses the active/default profile and may expose a one-line optional override without pausing. Question quality tests must measure question count, redundant-question rate, premise resets, recommendation clarity, and whether safe work continued while optional preferences were unanswered.

### Configuration schemas

`config/orchestration.schema.json` will validate the committed `config/orchestration.json` instance and any ignored `.optimal-challenge/orchestration.local.json` override loaded through the single access path documented in `config/README.md`. It will include:

- profile selection;
- objective weights as optional qualitative policy inputs;
- invocation mode and Economy, Balanced, Quality, and Custom profile selection;
- `exact_specialists` with a schema range of 0 to 32 and a runtime limit from the detected host maximum, Custom `delegation_margin` from 1 to 12, and `allow_mode_margin_override` defaulting to false;
- budget `unit`, `limit`, `measurement`, `enforcement`, `measurement_source`, and `soft_threshold` fields;
- `measurement` values `unavailable`, `estimated`, or `observed`;
- `enforcement` values `advisory`, `local_enforced`, or `provider_enforced`, with enforced values permitted only when the adapter confirms an observed counter and a matching stop primitive;
- maximum active specialists and retry limits;
- delegation, continuity, premise, and verification policy;
- provider-neutral capability classes;
- persistence and privacy controls.

Unknown properties will fail schema validation. Defaults will be documented in `config/README.md`. Secrets and live provider identifiers remain outside committed configuration.

Valid measurement/enforcement combinations are: any measurement with `advisory`, and `observed` only with `local_enforced` or `provider_enforced`. The plugin never labels a limit hard, claims exact remaining monetary spend, or promises automatic stopping unless the current host exposes verified usage and a matching enforcing primitive. An advisory ledger may calculate remaining reserved units, but labels the value estimated or unknown whenever its measurement is not observed. Without enforcement capabilities, the value is an **advisory ceiling**. Product credits, tokens, elapsed time, and estimated list-price currency remain distinct units and are never converted without a verified mapping.

The user supplies an explicit job ceiling when desired; otherwise profiles supply qualitative routing limits rather than an invented monetary cap. The coordinator alone allocates the job envelope and reserves capacity for integration and required verification. Total cost includes coordinator work, workers, context transfer, tools, reviews, and retries. Each task capsule receives a worker allocation and separate retry/review allowance. Workers cannot transfer, expand, or borrow allocations; unused allocation returns to the coordinator, and reallocation requires a recorded coordinator decision.

`config/allocation-ledger.schema.json` defines the runtime ledger stored at `.optimal-challenge/allocation-ledger.json`. It records schema/reconciliation/snapshot versions, transaction IDs, unit and ceiling, measurement/enforcement status and source, coordinator/integration/mandatory-review reserves, assignment reservation IDs, worker/tool/retry/review allocations, `funded_consumed`, `funded_reservation_overrun`, `unfunded_consumed`, released amounts, terminal evidence, and reset/reconciliation history. All balance fields are non-negative. For a bounded ledger, `available + reserved + funded_consumed = ceiling` and `total_consumed = funded_consumed + unfunded_consumed`. `funded_reservation_overrun` records consumption above an assignment's initial reservation that was covered from job-level `available`; it is a diagnostic subset of `funded_consumed`, not an extra balance bucket. `unfunded_consumed` alone represents whole-job consumption beyond the ceiling and immediately produces a visible `Degraded` or `Blocked` state. Per reservation, `initial_reserved + funded_reservation_overrun = active_reserved + funded_consumed + released_unused`. Released capacity returns to `available` and is not a fourth balance bucket.

The transition contract is:

| Event | Observed usage | Estimated usage | Unavailable usage |
|---|---|---|---|
| start | atomically reserve maximum before launch when enforced; otherwise record reservation before launch | record maximum advisory reservation before launch | record maximum advisory reservation before launch |
| complete | move observed amount to `funded_consumed`; release remainder | move labelled estimate to `funded_consumed`; release remainder subject to later reconciliation | conservatively move the full reservation to `funded_consumed` |
| confirmed cancel | move observed use to `funded_consumed` and release known remainder | move estimate to `funded_consumed` and release only evidenced remainder | retain reservation until reconciliation or explicit advisory reset |
| missing terminal event | retain reservation and mark assignment `unknown` | retain reservation and mark assignment `unknown` | retain reservation and mark assignment `unknown` |
| failed or timed out | move evidenced use to `funded_consumed`; release only confirmed remainder; mark `failed` or `unknown` | move estimate to `funded_consumed`; release evidenced remainder; timeout without terminal evidence stays `unknown` | retain reservation unless failure confirms no further use; otherwise mark `unknown` |
| retry start | create a new transaction from the task's retry reserve; never mutate the failed attempt's consumption | same, labelled advisory | same, retaining prior unknown reservation |
| retry complete | apply normal completion transition to the retry transaction | apply estimated completion and reconcile later | conservatively consume retry reservation |
| late observed report | reconcile delta and increment version; excess above the assignment reservation moves job `available` to `funded_consumed` and `funded_reservation_overrun`, then any amount beyond the job ceiling becomes `unfunded_consumed` | replace estimate with the same funded/unfunded classification; release any surplus | replace conservative charge when evidence permits and record adjustment |
| reconciliation failure | preserve prior balances and versions; mark ledger degraded and require targeted recovery | same | same |

An explicit advisory reset requires a reason, user/coordinator authority, preserved prior values, a new transaction and reconciliation version, and a degraded accuracy marker; it cannot manufacture a claim of observed remaining capacity. Registry and ledger writes share a transaction ID and snapshot version so cross-file validation can detect torn updates. On a torn or corrupt ledger write, the coordinator quarantines the current ledger, restores only a hash- and version-verified last-known-good snapshot, and replays idempotent task, return, reservation, and terminal evidence. If that evidence is incomplete, balances become unknown/degraded and new reservations are blocked; project source and verified artifacts remain authoritative, but they cannot be used to invent available capacity. Concurrent assignments reserve before dispatch. This ledger is descriptive/advisory in the policy release unless the adapter declares local or provider enforcement; atomic enforcement remains deferred when the host lacks an enforcing primitive.

`config/team-registry.schema.json` will define the reconstructable registry stored by default at `.optimal-challenge/team-registry.json`. It includes schema, snapshot, and transaction versions; run/coordinator IDs; unique logical teammate IDs; role and capability class; continuity mode; native handle with provider and expiry; working-set evidence references; trust counters backed by review evidence; active assignment IDs; and assignment states `reserved`, `running`, `complete`, `failed`, `cancelled`, or `unknown`. Stale or corrupt registries never override project truth: invalid entries are quarantined, active assignments become `unknown`, and the coordinator reconstructs from task/return capsules, source, tests, and `docs/PROJECT-STATE.md`. Conflicting logical IDs fail validation rather than merging histories.

`scripts/validate_orchestration.py` performs invariants JSON Schema cannot express: registry-key/logical-ID equality and global uniqueness; assignment-reference and ledger-reservation integrity; shared transaction/snapshot consistency; trust counters backed by cited review evidence; permitted registry and ledger state transitions; per-reservation and whole-ledger balance conservation; reconciliation-version monotonicity; capability/enforcement compatibility; and quarantine/reconstruction behavior. Structural tests supply valid, corrupt, stale, conflicting-ID, unknown-usage, over-ceiling, late-report, failed, timeout, retry, reconciliation-failure, reset, torn-snapshot, cancellation, and concurrent-reservation mutation sequences. `scripts/evaluate_routing.py` remains responsible for route calculations and behavioral case structure, not cross-record storage integrity.

`config/project.json` remains the canonical maintenance configuration and will gain paths for the orchestration instance and schema, team-registry and allocation-ledger schemas, team-routing and behavioral-acceptance scenarios, orchestration validator, and evaluator. Version and package paths will move to 1.2.0 in one coordinated change.

### Platform capability matrices

`platform-codex.md` and `platform-claude.md` will publish separate capability rows for Codex local/plugin execution, OpenAI API/Agents SDK policy mapping, Claude Code/plugin execution, and Anthropic API/Agent SDK policy mapping. Each row records surface ID, support level (`policy-only`, `observed`, or `unsupported`), detector and evidence reference, verified product/SDK version, timestamp, expiry, and fallback for native resume, cancellation/pause, usage measurement, local/provider budget enforcement, persistence/privacy controls, parallel execution, and tracing.

Capability resolution is fail-closed: matching live detection for the exact surface/version outranks unexpired acceptance evidence, which outranks the static policy-only declaration. Missing provenance, surface/version mismatch, expiry, conflicting observations, or detector failure resolves the capability to `unknown`; `unknown` uses the same inline, rehydrate, advisory, or blocked fallback as unsupported behavior until reverified. A mismatch is reported and updates the effective route without silently rewriting committed policy. API/SDK rows remain policy-only until an executable adapter and acceptance run exist. Product subscription credits and API billing are never treated as the same measurement surface.

### Evaluation data and script

`tests/team-routing.json` will hold focused two-sided cases for:

- premise investigation versus premature questioning;
- material question versus reversible default;
- inline execution versus profitable delegation;
- teammate resume versus rehydrate versus fresh review;
- useful parallelism versus overlapping-edit contention;
- deterministic verification versus independent review;
- capability escalation versus unchanged retry;
- Economy, Balanced, Quality, and Custom profile differences;
- explicit delegation requests that should still be challenged when wasteful;
- privacy-sensitive state that must not persist;
- default, task-level, and persistent invocation/profile overrides, invalid values, and precedence;
- measurement/enforcement combinations, including unavailable usage and advisory, local-enforced, and provider-enforced behavior;
- allocation among coordinator, worker, tool, retry, integration, and review reserves;
- question suppression after settled decision IDs and legitimate newly discovered blockers;
- Custom margin override enabled/disabled, exact-specialist zero/one/above-cap interpretation, and unavailable-slot handling;
- over-ceiling and unfunded consumption, failed/timeout/retry/reconciliation/reset transitions, and cross-file snapshot mismatch;
- stale, conflicting, wrong-surface, and detector-failure capability evidence;
- wrong plugin artifact, version, cachebuster, or contaminated-state baseline-arm detection.

`scripts/evaluate_routing.py` will validate scenario structure and deterministic policy invariants. Model-level semantic scoring remains a separate host acceptance step unless a repeatable evaluator is available; the script must not claim to prove host-model behavior by parsing expected labels alone.

## Data flow

1. The router takes the direct path for stable, single-step, low-risk work.
2. Otherwise the coordinator loads only the references needed for the current decision.
3. The premise gate resolves cheap unknowns and produces one decision bundle only when necessary.
4. The coordinator builds the minimum dependency graph required for the goal.
5. The coordinator compares expected utility and active allocation for inline execution, a resumed teammate, a rehydrated teammate, or a new specialist.
6. Each delegated assignment receives a task capsule and capability lease.
7. The worker returns a structured return capsule plus references to large artefacts.
8. The coordinator selects deterministic verification or a fresh targeted reviewer.
9. The coordinator integrates only verified facts, decisions, and artefacts.
10. Durable state is updated at a meaningful milestone or boundary; disposable team state remains reconstructable.
11. The final response reports the outcome and any failure, partial, degraded, or blocked state through the existing visibility contract.

## Authority and safety boundaries

- The coordinator remains the sole user-facing process authority unless the user explicitly requests a handoff.
- Workers cannot ask the user directly, expand scope, spawn descendants, change resource profiles, or acquire new permissions without an explicit lease.
- Profile selection never overrides correctness, safety, privacy, or the user's explicit constraints.
- Monetary or credit limits are advisory unless the current host verifies usage and exposes an enforcing primitive; only then may the adapter call them provider-enforced.
- Runtime state must have an explicit persistence mode and must not silently enable provider state retention.
- Sensitive personal traits, credentials, secrets, and raw private transcripts must not enter team memory or committed capsules.
- Source files, repository state, tests, and explicit decisions outrank a stale registry or teammate memory.
- Destructive and externally visible side effects continue to use the existing side-effect gate.

## Failure and recovery behavior

The existing `Succeeded`, `Failed`, `Partial`, `Blocked`, and `Degraded` states remain authoritative. Team-specific recovery adds:

- worker timeouts or missing terminal results remain unfinished, never complete;
- a malformed return capsule is rejected or normalized with the deficiency reported;
- conflicting worker outputs trigger source inspection or targeted adjudication;
- unavailable resume handles fall back to rehydration when sufficient durable state exists, otherwise become blocked or require re-discovery;
- budget/profile limits prevent new reservations at the relevant threshold; running assignments follow the ledger and host-specific pause/cancel rules below;
- retries stop when they repeat the same hypothesis without new evidence;
- unresolved assignments and exact resume actions are written to `docs/PROJECT-STATE.md` before a quota or session boundary.

Fallbacks remain degraded until compared against the authoritative source and subjected to the intended verification.

At a soft threshold, the coordinator reduces optional parallelism or review and replans while preserving mandatory verification. At a local- or provider-enforced cap, it starts no new spend and uses the host's pause or cancellation primitive where available. At an advisory ceiling, it stops before the next discretionary operation but never claims automatic prevention. Running work is paused or cancelled only when supported and safe; otherwise it is recorded as unfinished. Verified artifacts are preserved, every running assignment and usage source is recorded, and the user receives `Partial`, `Blocked`, or `Degraded` status with observed, estimated, or unknown usage plus one concrete expansion or resume decision.

## Validation strategy

Implementation must extend the current fail-closed checks rather than weaken them.

### Structural validation

- all new files exist at configured paths;
- every reference module is explicitly linked from `SKILL.md`;
- router and template size budgets remain enforced;
- orchestration configuration validates against its JSON Schema;
- capsules contain required fields and reject unknown or unsafe fields where appropriate;
- manifest names, versions, repository metadata, marketplace entries, and package paths agree with `config/project.json`;
- no active hooks, MCP servers, monitors, agents, or provider credentials are introduced.

### Policy regression validation

- existing fast-path, plan-reuse, failure-visibility, continuity, configuration, and folder-management scenarios continue to pass;
- new team-routing scenarios include positive, negative, pressure, and profile-differentiation cases;
- adversarial checks detect unconditional spawning, recursive delegation, universal review, provider/model literals in the core router, transcript persistence, and advisory budgets represented as enforceable;
- calculation tests cover factor bounds, positive-value thresholds, whole-job cost components, allocation conservation, explicit invocation authority, and decision records with evidence rather than unexplained numeric scores.

### Behavioral acceptance matrix

`tests/behavioral-acceptance.json` will define the minimum host-run matrix for every surface claimed as supported. It covers direct fast paths; investigate/default/ask premise boundaries; inline, auto, team-requested, exact-agent, and conflicting invocation controls; all four profiles; resume/rehydrate/fresh continuity; advisory and enforced budget fallbacks; mandatory and optional review; unavailable capabilities; and failure reporting. Each case records the host surface, configuration, expected route, prohibited behaviors, question count, spawn count, evidence requirement, and rubric result.

`tests/evaluation-manifest.json` pins the prompt/fixture hashes, host and product surface, model and reasoning settings, profile/configuration, tool set, evaluator and rubric version, randomization/execution order, minimum run count, aggregation, non-inferiority margins, and immutable subject identity for each arm: commit/tag, archive SHA-256, expected manifest version, cachebuster, and install source. `tests/baselines/v1.1.json` stores sanitized raw-result IDs/references, installed-plugin/version read-back evidence, and aggregate v1.1 outcomes with the same manifest hash. Deterministic structural cases run once; stochastic behavioral cases run at least five times per arm. Each arm starts in a clean task with fresh disposable registry/ledger state, identical allowed configuration, and read-back verification that the expected artifact is loaded. Execution order is recorded or counterbalanced. The candidate and baseline use unchanged fixtures and evaluator; changing either creates a new baseline rather than rewriting the comparison. Any artifact/version/cachebuster mismatch or cross-arm state/cache/configuration leakage invalidates the run.

The evaluation manifest also defines the research report's four-arm ablation on the same fixtures: A is v1.1 routing; B always delegates decomposable work; C uses the economic delegation gate without logical teammate continuity; D uses the full economic gate, logical continuity, and premise gate. Arm B is evaluation-only and never a shipped default. The A/B/C/D comparison attributes whether gains come from delegation, the economic gate, or continuity/premise controls; the release still requires D to pass the baseline gates below.

Before behavior claims or release, the same matrix is sampled against v1.1 and the 1.2 candidate. Quality uses a fixed 0-to-4 task rubric and is non-inferior when the candidate mean is no more than 0.10 below baseline with no new safety/authority failure. “Materially worse” simple-task cost or latency means a median increase greater than 5% where observed measurement exists. Where cost measurement is unavailable, no cost claim is made and model-call, spawn, tool-call, and question counts act only as labelled proxies. High-value delegation must improve mean quality by at least 0.20 or reduce median critical-path time by at least 10% while remaining quality-non-inferior. Release gates are:

- 100% pass for safety, explicit-authority, budget-truthfulness, and failure-visibility cases;
- no team creation on the deterministic direct/no-delegation trap set;
- no repeated settled question in continuity replay cases;
- no unexplained decrease in task-quality rubric versus v1.1;
- simple-task observed cost and latency are not materially worse; unavailable measurements use non-increasing labelled proxies and cannot support a cost claim;
- high-value delegation cases demonstrate the defined quality or critical-path benefit;
- unnecessary-spawn rate no worse than v1.1 and at most 10% on the fixed evaluation set;
- premise-reset and redundant-question rates no worse than v1.1;
- every claimed platform capability has a passing supported case or an explicit unsupported/fallback result.

An unexplained regression is release-blocking. Reports include run count, median cost/latency, mean quality, raw pass rate, and a 95% bootstrap confidence interval for measured differences. If the interval or sample cannot support the required conclusion, the result is inconclusive rather than improvement and release claims are narrowed accordingly. Hosts that cannot be exercised remain explicitly unverified and are excluded from support claims rather than inferred from structural tests.

### Release validation

Before commit and push of implementation:

1. run unit and structural scenario tests;
2. run package and adversarial validators;
3. run Codex, Claude, and official skill/plugin validators available to the repository;
4. audit documentation links, commands, paths, versions, and schemas;
5. scan staged content for secrets and silent exception patterns;
6. build the 1.2.0 archive and compare its expected file set and contents with source;
7. verify Git commit, push, and remote hash;
8. refresh the local plugin through the supported cachebuster/reinstall flow;
9. run the behavioral acceptance matrix in fresh tasks for each available claimed host surface, compare it with the recorded v1.1 baseline, and report unavailable surfaces separately.

The written design and later implementation each require an independent review score of at least 9.0/10 with no unresolved high-severity finding. The fixed rubric assigns one point each for: fast-path preservation, premise/question UX, invocation control, delegation economics, budget truthfulness, allocation/exhaustion behavior, continuity/state authority, verification quality, cross-platform feasibility, and testability/failure visibility. Reviewers must cite evidence and cannot award partial credit merely because the specification promises future work. Revisions continue until the threshold is met or a genuine blocker is reported.

No release step may be reported as successful solely from an exit code, queued operation, upload acknowledgement, skipped check, or incomplete background task.

## Documentation and release changes

The README will explain the new premise, delegation, continuity, profile, and review behavior without presenting the plugin as an executable budget controller. Package layout and validation commands will be kept current.

The portable, Codex, and Claude plugin manifests and every marketplace entry whose schema supports a version will move together to 1.2.0 while preserving the developer name `Coding Baby Penguin` and repository URL. The Codex local marketplace catalog will retain its supported source-and-policy shape without an invented version field, and validation will confirm that it still points to this plugin. `submission/plugin-submission.md`, `docs/PROJECT-STATE.md`, and the distributable archive metadata will be updated in the same release change.

## Compatibility and migration

- Existing direct routing, approved-plan reuse, failure visibility, project-state, and capability-lease behavior remains valid.
- Existing users who do not select a profile receive Balanced behavior.
- Existing `task-capsule.yaml` consumers receive additive fields with documented defaults; validation will identify incompatible custom consumers.
- The platform module filenames remain stable.
- `.optimal-challenge/` remains ignored and becomes the default location for reconstructable local team state.
- No migration creates a second canonical state or roadmap file.

## Acceptance boundary

Repository validation proves package structure and policy invariants. It does not prove that every host model will route identically. Fresh-task behavioral checks are a separate acceptance layer: a surface is not claimed as behaviorally supported until its matrix passes, and unavailable surfaces remain explicitly unverified.
