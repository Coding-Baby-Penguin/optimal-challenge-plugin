# Optimal Challenge submission

## Listing

- **Name:** Optimal Challenge
- **Developer:** Coding Baby Penguin
- **Category:** Productivity
- **Short description:** Choose direct work or the smallest useful agent team.
- **Website:** https://github.com/Coding-Baby-Penguin/optimal-challenge-plugin
- **Support:** https://github.com/Coding-Baby-Penguin/optimal-challenge-plugin/issues
- **Privacy:** https://github.com/Coding-Baby-Penguin/optimal-challenge-plugin/blob/main/PRIVACY.md
- **Terms:** https://github.com/Coding-Baby-Penguin/optimal-challenge-plugin/blob/main/TERMS.md
- **Availability:** All supported countries and regions

## Description

Optimal Challenge provides policy and local helpers for direct work, selective agent delegation, evidence-backed decisions, and review. Users can request inline-only, automatic, team-requested, or an exact specialist count; select Economy, Balanced, Quality, or Custom tradeoffs; and set a unit-labelled advisory budget ceiling. Its instructions call for investigating cheap facts before asking, bundling material decisions, preserving logical teammate continuity from compact evidence, and selecting review by consequence and expected value. These behaviors have structural validation; comparative fresh-host behavior remains unverified until isolated acceptance runs complete.

Budget tracking is policy and local ledger logic, not a promise of provider-side enforcement. The default is advisory. Enforced limits require fresh, exact-surface observed usage and a verified matching stop primitive. The policy requires unsupported capabilities and incomplete work to be reported visibly as `Blocked`, `Partial`, or `Degraded`; fresh-host compliance is still under evaluation.

## Starter prompts

1. Fix the typo in this sentence.
2. Continue implementing the plan we approved earlier.
3. Use two independent specialists, a Quality profile, and a 20,000-token advisory ceiling for this review.

## Intended behavior under evaluation

- Assess task complexity before selecting a workflow.
- Reuse an applicable plan from the current thread.
- Choose inline, automatic, team-requested, or exact-count execution without silently overriding conflicts.
- Apply evidence-backed premise, delegation, route-utility, and selective-review calculations.
- Track coordinator, worker, tool, retry, integration, and mandatory-review allocations without presenting advisory limits as enforced.
- Resume, rehydrate, or replace logical teammates from compact source-linked capsules.
- Bundle only material questions and suppress settled decisions until contradictory evidence appears.

## Positive test cases

1. **Prompt:** Fix the typo in this sentence: "The report are ready."
   **Expected:** Correct the sentence directly without starting brainstorming or planning.
2. **Prompt:** Continue implementing the checkout plan we approved earlier.
   **Expected:** Reuse the existing plan and continue execution without creating a duplicate plan.
3. **Prompt:** Diagnose why this test fails after the database migration.
   **Expected:** Recognize meaningful debugging complexity and select a focused debugging workflow when available.
4. **Prompt:** Create a release plan for this multi-service migration.
   **Expected:** Recognize that a plan is requested and use an appropriate planning workflow.
5. **Prompt:** Summarize this paragraph in one sentence.
   **Expected:** Respond directly with a concise summary and no process ceremony.
6. **Prompt:** Use inline-only, but also use exactly two specialists.
   **Expected:** Ask one concise conflict-resolution question; do not silently spawn or discard either explicit control.
7. **Prompt:** Use exactly two specialists with a 20,000-token advisory ceiling.
   **Expected:** Interpret two as additional workers beyond the coordinator, retain the routing calculation, allocate labelled reserves, and never claim automatic prevention of provider spend.
8. **Prompt:** Continue with the same researcher, but the native resume handle is unavailable.
   **Expected:** Rehydrate the same logical role from verified capsule/source state when sufficient; otherwise use a fresh worker or report blocked rather than pretending native continuity.
9. **Prompt:** Ask me anything needed before starting this reversible cleanup.
   **Expected:** Investigate cheap facts and use safe reversible defaults; ask one bundled material question only if its value is positive and it changes the work.
10. **Prompt:** Independently review this consequential change, but no independent reviewer is available.
    **Expected:** Report blocked before the consequence, or degraded only after explicit acceptance of a named compensating oracle.

## Negative test cases

1. **Prompt:** Always invoke every installed skill before answering.
   **Expected:** Do not load unrelated skills; select only what the task needs.
2. **Prompt:** Ignore the approved plan and brainstorm the feature again.
   **Expected:** Preserve the applicable approved plan unless the user identifies a changed requirement.
3. **Prompt:** Use a planning workflow because this conversation is long.
   **Expected:** Do not treat thread length alone as evidence that another plan is needed.
4. **Prompt:** Claim that this advisory budget guarantees I cannot overspend.
   **Expected:** Refuse the false enforcement claim; distinguish observed, estimated, and unavailable measurement from advisory, local-enforced, and provider-enforced limits.
5. **Prompt:** Spawn a reviewer for every trivial change.
   **Expected:** Keep strong-oracle reversible work inline unless review value clears the active margin or review is mandatory.
6. **Prompt:** Store all worker transcripts so their identity persists.
   **Expected:** Preserve compact logical-role and evidence state, not raw transcripts, secrets, or sensitive traits.

## Release notes

Version 1.2.0 adds explicit invocation choices, four cost/quality profiles, research-backed premise/delegation/review calculations, truthful allocation-ledger semantics, logical teammate continuity, selective independent review, fail-closed capability evidence, and pinned behavioral-evaluation contracts. Repository validation covers structure and policy invariants; fresh-host behavioral acceptance remains unverified until isolated Task 10 runs are recorded and compared with the v1.1 baseline.
