# Holistic Quality Recovery Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` for implementation, retaining one developer for code ownership and fresh reviewers at the defined gates. Steps use checkbox (`- [ ]`) syntax. This document prepares the work; it does not record implementation approval or authorize publication.

**Goal:** Raise Optimal Challenge from the independently assessed 62.05/100 to at least 95/100 under the unchanged fourteen-dimension rubric, targeting 96/100 for margin and pursuing 100 only where evidence supports every dimension.

**Architecture:** Preserve the skills-only plugin and small, conditional router. Repair existing tooling, organize its internal responsibilities behind compatible entry points, establish a verifiable local recording/evaluation workflow, and collect real host evidence. Keep durable policy, mutable project status, sanitized review summaries, private/raw results, and distributable artifacts separate.

**Tech Stack:** Python 3.12 standard-library runtime tooling; existing `unittest`, JSON Schema and YAML development validation; Markdown policy; existing Codex/Claude manifests; pinned development dependencies; repository CI.

**Spec:** [Independent assessment](../../reviews/2026-09-29-independent-assessment.md), the user's 29 September 2026 request for at least 95/100 and investigation of 100/100, and the still-applicable constraints in [the existing design](../specs/2026-09-26-agent-team-optimisation-design.md). This plan addresses the broader assessment and continues unfinished acceptance work; it does not restart completed Tasks 1â€“9.

## Global constraints

- Keep the assessment's fourteen dimensions and weights unchanged. Do not obtain a higher score by dropping weak areas, redefining support, changing weights, lowering acceptance margins, or substituting test counts for behavior.
- Repository cleanliness remains **20%** of the score and includes discoverability, authoritative artifact identities, lifecycle placement, and contributor handover.
- Preserve default `mode=auto`, `profile=balanced`, existing public entry points, authority precedence, and the quiet direct fast path. `SKILL.md` remains at or below **350 body words**, explicitly linking every lazy runtime reference.
- Preserve current `1.2.0` candidate metadata until a deliberate release-version decision; change all version-bearing consumers together through `config/project.json`.
- Add no cloud service, MCP server, authentication platform, automatic self-modifying hook, or provider budget controller to earn points. Unsupported capabilities remain explicitly unsupported or unverified.
- Use Python **3.12** and retain `jsonschema==4.25.1`, `PyYAML==6.0.2` until an independently justified dependency update. Pin/hash transitive development dependencies for reproducibility.
- Keep `docs/PROJECT-STATE.md` as the only mutable project checkpoint. Preserve historical baselines and review records; never rewrite their failures as successes.
- Raw host results and private state remain ignored/local. Only sanitized summaries and verifiable identity references enter Git. Require redaction before retaining or publishing evidence.
- Missing host access, model read-back, counters, independent grading, or inconclusive confidence intervals remain visible blockers to the affected score or claim.
- Current project state blocks commit/push before Task 10. Execution must first resolve the checkpoint/CI policy: this plan recommends permitting **local candidate commits and a dedicated validation-branch push after structural checks** so immutable subjects and hosted CI can be tested, while keeping `main` push/release publication blocked until all release gates pass. Do not assume that amendment is approved merely because this plan exists, and never move an existing published tag. Without validation-branch authorization, hosted CI remains unverified; do not create a circular gate by claiming it passed locally.

## Score targets and evidence

Scores below are targets, not awarded points. The final reviewer calculates the actual score on the exact reviewed subject.

| Dimension | Weight | Baseline /10 | Target /10 | Evidence needed | Tasks |
|---|---:|---:|---:|---|---|
| Purpose and usefulness | 6% | 8.0 | 9.5 | Useful outcomes on coding, analysis, and artifact tasks; no avoidable workflow ceremony | 8â€“10 |
| User control and interaction | 6% | 7.5 | 9.5 | Direct work stays quiet; exact-count conflicts, question bundles, settled decisions and overrides behave correctly | 1, 8â€“10 |
| Demonstrated host behavior | 12% | 3.0 | 9.5 | Authentic isolated runs, held-out tasks, independent grades, passing confidence-qualified comparisons | 6â€“10 |
| Correctness and robustness | 12% | 6.5 | 9.5 | Original defect regressions, malformed-input coverage and valid-state invariants pass | 2â€“4 |
| Architecture and maintainability | 6% | 6.5 | 9.5 | Focused tooling modules, compatible entry points, clear ownership and successful migration | 5 |
| Security and privacy | 7% | 7.5 | 9.5 | Defined trusted recorder/caller boundaries, safe evidence reads, redaction, secret and artifact checks | 3, 6â€“8 |
| Test quality and evidence strength | 7% | 7.5 | 9.5 | Behavioral regressions, independent evidence, mutations and holdouts; structural success cannot forge acceptance | 1â€“4, 6â€“10 |
| Performance and cost efficiency | 4% | 5.0 | 9.5 | Observed whole-job usage and latency; setup, review, retries and tools included; supported benefit | 8â€“10 |
| Failure visibility and recovery | 3% | 5.5 | 9.5 | Corruption, timeout, cancellation, unknown usage and late results yield controlled, actionable outcomes | 3, 8â€“10 |
| Platform integration | 3% | 4.5 | 9.5 | Meaningful Codex/Claude positive acceptance and tested limitations; no support inferred for API/SDK surfaces | 7â€“10 |
| Installation and reproducibility | 3% | 6.0 | 9.5 | Clean Windows/Linux developer setup; actual supported-host install/upgrade read-back; deterministic checks | 4, 7â€“9 |
| Packaging and release discipline | 5% | 6.5 | 9.5 | One immutable identity per arm, verified installed bytes, reproducible archive and current evidence | 7, 10 |
| Documentation and handover | 6% | 6.5 | 9.5 | Fresh contributor finds owners, runs checks and makes a safe change using only repository documentation | 5, 10 |
| Repository cleanliness | **20%** | **6.5** | **10.0** | No ambiguous active subjects, orphan artifacts, misleading stale instructions, broken links or unexplained file placement | 1, 5, 7, 10 |

Target arithmetic: thirteen dimensions at 9.5 and cleanliness at 10 give **96.0/100**. The release threshold is an actual independently awarded **95.0/100**, with no dimension below 9.0, no unresolved material defect, and all mandatory acceptance gates passed. Even perfect cleanliness alone raises the current score only to **69.05/100**.

Unavailable cost telemetry cannot be replaced by a price guess or renamed proxy. If a host or evidence limitation prevents the target, report the attainable score and remaining gap rather than claiming 95. A limited support claim may be honest, but does not automatically earn a higher platform score.

## File placement and ownership

Use existing platform-discovery paths and `tests/validation/`. New folders have a distinct lifecycle, not decorative symmetry.

| Placement | Responsibility |
|---|---|
| `docs/reviews/2026-09-29-independent-assessment.md` | Historical baseline assessment; unchanged scores and evidence |
| `docs/superpowers/plans/2026-09-29-holistic-quality-recovery.md` | This execution plan and task checkboxes |
| `config/quality-rubric.json` | Frozen weights, baseline, scoring anchors and required evidence |
| `config/goal-context-contract.md` | Stable goal/context/claim guarantees, separately reviewed and pinned |
| `docs/PROJECT-STATE.md` | Mutable current phase, blockers, evidence pointers and next action |
| `docs/README.md`, `docs/CONTRIBUTING.md`, `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md` | Concise navigation, contributor workflow, ownership/interfaces, release changes |
| `docs/maintenance/folder-plan.md` | Migration map, consumers, lifecycle rules and rollback |
| `scripts/optimal_challenge/` | Focused internal tooling; existing `scripts/*.py` remain compatibility/CLI facades |
| `scripts/check_quality.py`, `.github/workflows/quality.yml`, `requirements-dev.lock` | One check runner, least-privilege CI and hash-pinned developer environment |
| `scripts/evaluation_evidence.py`, `scripts/record_acceptance.py`, `scripts/verify_subject.py` | Evidence verification, actual-host recording, immutable subject/install read-back |
| `tests/fixtures/evaluation/`, `tests/validation/` | Sanitized adversarial fixtures and regression tests |
| `tests/results/<evaluation-id>/`, `.optimal-challenge/`, `tmp/quality/`, `dist/` | Ignored raw runs, reconstructable runtime state, temporary output and built archives |
| `docs/reviews/<review-id>.md`, `tests/baselines/v1.1.json` | Sanitized independent conclusions and explicitly identified baseline summary |

Before implementation, apply the folder plan's consumer checklist to imports, CLI commands, manifests, configuration paths, packaging, CI, tests and Markdown links. Exclude raw evidence and internal review/plan history from distributable ZIPs while retaining contributor documentation where useful. Do not delete valid historical artifacts to make the tree look clean.

## Review focus

1. Non-finite numbers and malformed JSON-derived nested shapes must fail safely without fabricating usable budget or state. Owned by Tasks 2â€“3.
2. Unknown usage, pending mandatory review and corrupt recovery must not release or consume protected capacity incorrectly. Owned by Task 3.
3. A synthetic bundle, missing raw result, copied receipt, changed artifact, or self-declared grader must not become verified host acceptance. Owned by Tasks 6â€“8.
4. Changed fixtures, stale installed skills, leaked cross-arm state and incompatible host versions must invalidate runs rather than contaminate comparisons. Owned by Tasks 1, 7â€“9.
5. A routine checkpoint edit or fresh contributor's small change must not require undocumented pin repairs, hidden local paths, or historical chat knowledge. Owned by Tasks 4â€“5 and 10.

## Task 1 â€” Freeze scoring and audit acceptance semantics

**Files:** Create `config/quality-rubric.json`, `tests/validation/test_quality_rubric.py`; inspect/modify `tests/behavioral-acceptance.json`, `tests/team-routing.json`, `tests/evaluation-manifest.json` and the evaluator's intentional approval pins when a reviewed correction requires it.

**Interfaces:** The rubric is data with the fourteen stable dimension IDs, weight, baseline score, anchors and evidence checklist. Behavioral fixtures continue using their existing semantic contract schema; any correction receives a new fixture/rubric identity and invalidates old comparisons.

- [x] Encode the assessment exactly: weights sum to 100; baseline recomputes to 62.05; target recomputes to 96.0. `test_quality_rubric.py` must reject missing dimensions, changed weights and unsupported awarded claims.
- [x] Resolve `accept-direct-no-delegation-trap`: its prompt explicitly requests five agents while its canonical calculation omits an exact count and expects inline. Keep separate cases for optional agent suggestions, an exact count that fits, and an exact count that exceeds host capacity. Derive expectations from authoritative policy, not a preferred score.
- [x] Audit every case's prompt, configuration, expected route and arm purpose. Establish whether each case is a universal safety/control requirement, candidate-only feature, or comparative task. Baseline and ablation arms must not be failed merely for lacking a candidate-only feature; safety cannot be exempted. Freeze this classification before running any subjects.
- [x] Run `python scripts/validate.py`, `python scripts/evaluate_routing.py tests/team-routing.json` and targeted behavioral tests. Independently review semantic corrections before updating approval pins. Preserve the old fixture identity in the baseline record.

**Done:** Fixed score contract and coherent evaluation protocol, with no score obtained from relabeling an invalid run.

## Task 2 â€” Repair numeric budget validation

**Files:** Modify `scripts/orchestration_config.py`, `tests/validation/test_orchestration_config.py`, and schema/config documentation only where the finite-value contract needs clarification.

**Interfaces:** Preserve `load_effective_config(...) -> dict` and `validate_config(...) -> list[str]`; use their existing controlled validation failure behavior.

- [x] Add failing tests `test_rejects_nonfinite_budget_values` and `test_rejects_nonfinite_values_in_each_precedence_layer`. Assert rejection for NaN, positive/negative infinity, overflow-decoded JSON (`1e309`), both limit and threshold, boolean-as-number, and malformed numeric fields.
- [x] Run `python -m unittest tests.validation.test_orchestration_config -v`; reproduce the NaN/infinity failures before repair.
- [x] Require finite numeric values before comparisons. Preserve valid positive finite limits, `null` defaults, thresholds equal to the limit and profile precedence. Do not silently replace bad values.
- [x] Run the targeted tests and integrated validator; retain a finite-boundary example in the defect closure record.

**Done:** No configuration path accepts a non-finite ceiling or threshold.

## Task 3 â€” Make recovery safe and reserve obligations executable

**Files:** Modify `scripts/orchestration_state.py`, `config/allocation-ledger.schema.json`, orchestration fixtures, `tests/validation/test_orchestration_state.py`, and `references/team-orchestration.md`/`team-continuity.md` when needed.

**Interfaces:** Preserve `validate_orchestration_state(registry, ledger) -> list[str]`, `apply_ledger_event(ledger, event) -> dict`, and `recover_state(registry, ledger, evidence) -> tuple[dict, dict, list[str]]`. A recovery result cannot be dispatched unless it passes state validation; insufficient authoritative identity/evidence yields a controlled blocked result/reason, not invented usable state.

- [x] Add failing regressions for `trust=None`, list-valued logical IDs, nested-list evidence references, wrong-type roots/collections, missing snapshot fields and malformed replay evidence. Assert no incidental `AttributeError`/`TypeError`, no input mutation, visible reasons, and no unsafe reclaimed reservation.
- [x] Move guarded shape validation ahead of attribute access, hashing and replay. Exercise verified-snapshot recovery, irrecoverable corruption, replay conflict, timeout, late result and failed cleanup. Keep primary errors visible.
- [x] Resolve reserves explicitly: retain `reserves` as planning requirements and satisfy them with real protected reservation events (`coordinator`, `integration`, and `review` for mandatory review) before worker dispatch. Add `prepare_dispatch(registry: Mapping[str, Any], ledger: Mapping[str, Any], worker_event: Mapping[str, Any]) -> tuple[dict, dict]`, raising a descriptive `ValueError` before mutation on insufficient capacity or invalid state. Coordinator-owned holds remain independent of worker reservations. Do not subtract the same capacity twice or imply arbitrary legacy calls are protected.
- [x] Add the assessment's ceiling-100 example: coordinator/integration/review holds of 10 each plus worker 40 leave at most 30 available; another worker request for 60 is rejected by the supported dispatch path. Test unknown usage, authorized release and retry transitions against the same invariant.
- [x] Run state/config/template tests and `scripts/validate_orchestration.py` with the updated valid fixtures. A bounded JSON-shape mutation corpus must return errors or controlled blocked recovery, never usable corrupt state.

**Done:** Original corrupt-state reproductions are closed and the documented dispatch route protects required capacity.

## Task 4 â€” Separate stable guarantees from status and automate checks

**Files:** Create `config/goal-context-contract.md`, `scripts/check_quality.py`, `requirements-dev.lock`, `.github/workflows/quality.yml`; modify `tests/goal-context-policy-pins.json`, `tests/validation/test_goal_context_contracts.py`, `config/README.md`, `.gitignore`, packaging configuration and relevant policy links.

**Interfaces:** `python scripts/check_quality.py --mode structural --output tmp/quality/summary.json` runs required local checks and emits explicit structural/host statuses. `--mode release --evidence-root <path>` additionally requires verified current acceptance. Structural success never implies release success.

- [x] Add regression coverage proving benign phase/date/status updates do not require policy-hash approval, while weakened goal preservation, authority, checkpoint exemptions and claim guarantees still fail their stable contract. Remove only the whole mutable-state hash coupling after reviewing the replacement; preserve anti-false-acceptance checks through verifiable evidence.
- [x] Move invariant guarantees to the stable contract, update pins deliberately, and retain useful state fields/source evidence pointers in the mutable checkpoint. Test the assessment's benign last-updated-date edit and original malicious mutations.
- [x] Create a Python 3.12 clean-environment bootstrap procedure using hash-pinned direct/transitive dependencies; the quality runner checks prerequisites and provides an actionable blocked outcome instead of attempting ACL repairs or hiding missing checks.
- [ ] Run the same structural command in clean Windows and Ubuntu CI on the authorized validation branch with minimal repository permissions and verified pinned action identities. Include unit/negative tests, schema/manifest/link validation, packaging identity and targeted secret checks. No private host evidence or credentials in CI logs. If the proposed branch-push policy is not approved, retain local checks and mark hosted CI blocked.

**Done:** One documented local/CI gate; routine status updates remain cheap; policy weakening remains guarded. CI is actually observed passing on the authorized validation branch, not credited solely because YAML exists.

## Task 5 â€” Refactor responsibilities and prove handover cleanliness

**Files:** Create `docs/maintenance/folder-plan.md`, contributor/navigation/architecture/changelog documents, `scripts/optimal_challenge/__init__.py`, focused ledger/state-validation/recovery, capability-evidence/resolution and evaluation-contract/semantic/statistics/comparison modules. Modify existing script facades, import consumers, tests and packaging paths.

**Interfaces:** Existing CLI commands and public functions/classes remain compatible. Capability proof classes are imported as the same class identities, not copied/redefined. Internal tests import their explicit owning module; facades do not accumulate undocumented private exports.

- [ ] Write the exact move/consumer/rollback map before moving code. Partition `orchestration_state.py` into ledger mutation, state validation and recovery; split `evaluate_behavior.py` into bundle contracts, semantic calculations, statistics and comparison; separate capability issuance/evidence from resolution. Keep small existing modules intact.
- [ ] Preserve behavior through fixture outputs, replay/mutation invariants, CLI exit statuses and both CLI/library import paths. Run full discovery after each domain migration. Use reviewable changes; avoid cosmetic rewrites and splitting solely to meet a line count.
- [ ] Add a short `docs/README.md` entry map and contributor instructions for environment setup, one check command, ownership, pin updates, safe publication and recovery. Define lifecycle placement for historical plans, reviews, raw runs, local state and archives; search/update all moved paths and links.
- [ ] Run a fresh-context handover trial: using repository docs alone, a contributor finds relevant owners within 10 minutes, runs structural checks within 30 minutes excluding a documented network outage, and makes/verifies a small change within 60 minutes. Record confusion and fix the docs. Do not pre-teach the trial through chat history.

**Done:** No stale/orphan path consumers or unexplained active artifacts; documented module boundaries and measured contributor usability. Large functions require a clear responsibility justification or decomposition.

## Task 6 â€” Establish the trusted recording and grading boundary

**Files:** Create `scripts/evaluation_evidence.py`, `scripts/record_acceptance.py`, `tests/validation/test_evaluation_evidence.py`, sanitized fixtures, and `docs/maintenance/acceptance-runbook.md`; modify behavioral evaluation and capability-to-configuration integration.

**Interfaces:** Define a frozen `VerifiedEvaluationContext` carrying the exact manifest/receipt digests, verified artifact identities, provenance, issuance time and reviewed recorder identity; its trusted issuance path is separate from bundle JSON. Add `verify_run_evidence(bundle: Mapping[str, Any], manifest: Mapping[str, Any], evidence_root: Path, recorder_receipt: Mapping[str, Any]) -> tuple[VerifiedEvaluationContext | None, list[str]]`. Extend the existing `compare_arms(...) -> dict` with the keyword-only `evidence_context: VerifiedEvaluationContext | None = None`; structural inspection cannot award verified acceptance without independent valid context. The recorder captures actual host task/version/install/counter/tool evidence; it never fabricates a model output or grade.

- [ ] Reproduce synthetic internally consistent bundles returning improvement; add regressions requiring missing, altered, out-of-root, cross-arm, duplicate and synthetic-only raw/grader artifacts to remain unverified. Validate file bytes against recorded hashes and exact run identities before comparing grades.
- [ ] Record receipts separately from scored JSON. Require host/version/model/reasoning/install read-back, disposable state identity, terminal completion, raw-result identity and independent grading provenance. An independent review validates the recorder and receipt origin before its context can unlock claims. Document the trusted-caller/local-files assumption; do not describe hashes as proof against hostile same-process code.
- [ ] Require the real capability resolver-to-loader path to supply observed exact-surface evidence; reject user-created claims and unsupported enforcement requests at that integration boundary. If no real stop primitive exists, keep enforcement advisory and disclose the limitation.
- [ ] Exercise the recorder on one actual disposable host task and inspect its raw artifact/receipt/grade end to end. Retention is opt-in to approved local paths with redaction; cancellation, failed runs and grading disagreement remain explicit. A reviewed importer may be used when host automation is unavailable, but imported status strings alone never establish trust.

**Done:** Structural bundle consistency and verified observed host behavior are separate executable outcomes; the synthetic reproduction cannot earn acceptance.

## Task 7 â€” Reconcile immutable subjects and installed bytes

**Files:** Create `scripts/verify_subject.py`, `tests/validation/test_subject_identity.py` and `docs/maintenance/subject-identities.md`; modify `tests/evaluation-manifest.json`, baseline summary, packaging/install documentation and sanitized subject manifests.

**Interfaces:** `verify_subject(subject_manifest: Mapping[str, Any], source_root: Path, archive: Path, installed_root: Path) -> tuple[dict | None, list[str]]` returns verified identity evidence or errors; separate immutable subject identity from the run manifest so neither embeds its own archive hash.

- [ ] Resolve the checkpoint/validation-branch/publication policy described above before creating new candidate commits or pushing validation code. Verify current remote/tag state read-only; preserve published history. Select one existing immutable v1.1 source/archive combination, or rebuild from one explicitly pinned historical commit. Keep the four baseline mismatches recorded rather than retroactively blessing them.
- [ ] Build A/B/C/D from frozen source commits/trees and reviewed policy overrides, giving every arm its own archive identity and cachebuster. Preserve canonical deterministic ZIP generation; include base commit, exact source identity, manifest version, member hashes, archive hash and installed read-back.
- [ ] In isolated host installations, verify critical policy file bytes against each archive, including the router/context/continuity files that differed in this assessment. Test stale cache, wrong version, source drift, partial install and uninstall/rollback behavior. Do not alter the user's normal installation without execution authorization.
- [ ] Refresh provisional B/C/D evaluation identities only after verification. Run packaging, identity tests and the recorder preflight; no real behavior from a stale cache is accepted.

**Done:** A single documented, byte-verifiable identity per subject and installation; no self-hash cycle or ambiguous active baseline.

## Task 8 â€” Pilot live behavior and measurement

**Files:** Use the frozen acceptance fixtures and recorder; create ignored `tests/results/<pilot-id>/` and a sanitized review summary. Update capability evidence only where actually observed.

**Interfaces:** Real recorder output feeds evidence verification and the existing evaluator. No universal expected route is imposed on candidate-only ablation features.

- [ ] First run six risk-representative cases once per A/B/C/D arm: direct response, exact-count/conflict handling, settled decision, corrupt-state recovery, unavailable enforcement, and useful independent work. This **24-run pilot** validates setup and evidence, not stochastic acceptance. Do not weaken the full matrix to match the pilot.
- [ ] Check exact identity/isolation, task usefulness, independent grading and complete whole-job accounting. Measure tokens or another supported native usage unit and wall time including setup, delegation, tools, retries, merge and review. User attention and call counts are separately labelled observations/proxies.
- [ ] Stop immediately for wrong artifacts, privacy exposure, invented enforcement, lost authority or an invalid recorder. Fix the cause and restart only affected invalid runs. Counterbalance order and separate fixture, grader and subject changes.
- [ ] For unavailable telemetry/surfaces, report the exact limitation and impact on attainable scores. No conversion from subscription-limit percentages to per-task tokens or money; no inferred API billing.

**Done:** A demonstrated recording/measurement path and safe behavior on the highest-risk cases, allowing informed cost/latency estimates for the full matrix.

## Task 9 â€” Complete confidence-qualified acceptance and holdouts

**Files:** Existing fixture/manifests, ignored result bundles, reviewed capability records and sanitized comparison summaries. Add a separately frozen holdout manifest for coding, analysis and artifact work before running subjects.

- [ ] Calculate run count from the audited manifest before launching. The current thirty cases are all stochastic: five repetitions Ã— four arms gives **600 runs across all listed surfaces**, including **540 Codex runs**. Meaningful positive Claude coverage must be added/frozen; its cost is additional. Unavailable surfaces stay explicitly unverified, never silently skipped as passed.
- [ ] Run deterministic cases once and stochastic cases at least five times per arm. Use fresh tasks, installed identity read-back, disposable state, identical allowed configuration and recorded/counterbalanced order. Independent graders see outputs and criteria without being told which result should score better.
- [ ] Preserve existing comparison thresholds: quality non-inferiority margin **0.10** on the 0â€“4 scale; simple-task observed median cost/latency increase no more than **5%**; useful delegation quality gain at least **0.20** or critical-path reduction at least **10%**, with quality non-inferiority; unnecessary-spawn rate at most **10%**; zero new safety/authority violations. Apply the existing **95% confidence** requirement.
- [ ] Validate novel goal/context and research gates on independently authored holdouts and realistic tasks, not only prompts resembling training fixtures. Test direct-response accuracy, partial tool failure, quota interruption, stale decisions, and malicious instructions inside untrusted content. Correct original symptoms before claiming their closure.
- [ ] If results are inconclusive, extend only a predeclared sample batch within an agreed advisory execution envelope or report the block. Do not discard valid bad runs, tune thresholds after seeing outcomes, or run indefinitely to chase significance.

**Done:** Verified comparative behavior and transparent cost/latency evidence on exercised surfaces; unavailable or inconclusive claims remain unawarded.

## Task 10 â€” Independent 95-point gate and optional 100-point finish

**Files:** Sanitized independent review under `docs/reviews/`, mutable project state, final contributor documentation, archive/installed identity evidence and release records after publication is authorized.

- [ ] Give a fresh reviewer the exact immutable subject, original assessment, frozen weights, closure reproductions, raw-evidence access appropriate to privacy, CI results and handover trial. The reviewer must justify every dimension independently; planned target scores are not pass evidence.
- [ ] Accept only **actual weighted score â‰¥95/100**, no dimension below **9.0**, no unresolved material findings, verified host acceptance, observed relevant metrics, clean tracked/ignored artifact inventory, working documentation links, reproducible archive/install identity and successful developer setup. Record residual limitations plainly.
- [ ] Reserve at most two bounded defect-fix/review cycles for this gate. Each repair identifies the finding, owner, failing reproduction, verification and affected evidence. If host access/evidence blocks progress, checkpoint the exact blocker and attainable score instead of declaring completion.
- [ ] For **100/100**, require 10/10 evidence in every dimension: repeat independent grading on unseen tasks, successful clean install/upgrade/recovery on supported host versions, a second fresh contributor handover trial, repeated benchmark consistency, and closure of every remaining justified deduction. Use a second independent final assessment of the same subject. Treat 100 as a review outcome, not a promise of zero future defects or guaranteed behavior from every model.
- [ ] Once all approved publication gates pass, update canonical state, commit/push under the resolved workflow convention, verify remote/source/archive identities and retain a readable release evidence index. Do not claim CI or remote release success before destination read-back.

**Done:** â‰¥95 is independently demonstrated, or the remaining blockers are precisely reported. A 100 claim exists only if both final evidence and independent reviewers support it.

## Dependency order, effort and stopping rules

Tasks 1â€“4 establish semantics, robustness and cheap checks; Task 5 cleans maintenance boundaries; Tasks 6â€“7 establish evidence and identity; Task 8 is the live pilot; Task 9 collects acceptance; Task 10 rescores and releases only after authorization/gates. Task 5 documentation and Task 6 design can overlap without conflicting write ownership, but use one retained implementation worker by default.

Suggested review gates are after Tasks 3â€“4 (correctness/truth boundaries), after Tasks 6â€“7 (recording/identity), and at Task 10 (whole product scoring). These are fresh independent reviews; routine mechanical checks remain deterministic.

Engineering effort is an estimate: several focused sessions for repairs/setup, several for maintainability/evidence tooling, followed by host-dependent pilot and benchmark batches. The observed 265-test suite took about 44 seconds in the assessment; this does not predict host-run duration or billing. Set the execution envelope from pilot measurements before full stochastic runs. No fixed token, money or completion-time guarantee is made by this plan.

At every gate, report completed tasks, failed/blocked checks, subject/evidence identities, actual measurements or their absence, and the exact next action. Update the single canonical checkpoint once Task 4 safely permits it. Keep this plan's task checkboxes current; create no second roadmap or mutable state file.

## Planning self-review

- The original confirmed defects, integration assurance gaps, reserves clarification, source/cache mismatch, baseline mismatch, documentation, CI, module size and mutable-pin burden each have an owning task.
- All fourteen weighted dimensions have explicit evidence; the 20% cleanliness weight is preserved.
- Host behavior, cost, platform capability and CI execution cannot be credited from source promises or a structural pass.
- Existing completed implementation is retained; policy corrections and newly frozen evaluation data do not rewrite historical baseline outcomes.
- The plan adds no new service or unrelated product scope. Long-lived code ownership and bounded independent review match the established workflow preference.
- Current publication restrictions and the local immutable-subject/checkpoint conflict are surfaced before execution, rather than silently bypassed.
