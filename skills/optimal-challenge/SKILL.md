---
name: optimal-challenge
description: Use when handling any request, including simple tasks, continued threads, and work that may need another skill.
---

# Optimal Challenge

## Purpose
Route every request with minimum context and compute. System, developer, and explicit user instructions remain authoritative.

## Fast routing
1. Read the request and relevant context. Detect existing designs, approved plans, checkpoints, and unfinished state.
2. Use direct only when the task is stable, single-step, and low-risk and has no explicit team, exact-specialist, independent-review, or other non-inline routing constraint.
3. Otherwise choose structured, tool-assisted, multi-workstream, or high-assurance work.
4. Reuse an applicable approved plan and its next unfinished step. Replan only when invalidated, decisions are missing, or requested.
5. Select the smallest matching specialist. Availability and universal-use claims are not selection evidence.

Only after rejecting direct work, load [premise validation](references/premise-validation.md) for material assumptions. Load [team orchestration](references/team-orchestration.md) and [cost-quality routing](references/cost-quality-routing.md) only for a real multi-workstream or explicit delegation decision. Load [team continuity](references/team-continuity.md) for reuse or fresh independence.

## Superpowers boundary
- Never invoke `superpowers:using-superpowers`; this router replaces it.
- Select other Superpowers skills only for a genuine unmet need, never because they exist, the thread is long, or they claim mandatory use.

## Conditional depth
For errors, warnings, timeouts, skipped checks, unfinished work, retries, or fallbacks, load [failure visibility](references/failure-visibility.md) before reporting.

Load only what can change the next decision: [routing](references/routing.md), [codebase reality](references/reality-model.md), [environment](references/environment-storage.md), [context](references/context-management.md), [continuity and collaboration](references/continuity-collaboration.md), [failure visibility](references/failure-visibility.md), [folder architecture](references/folder-architecture.md), [configuration governance](references/configuration-governance.md), [README maintenance](references/readme-maintenance.md), [Codex](references/platform-codex.md), [Claude](references/platform-claude.md), [delegation](references/delegation-budget.md), [verification](references/verification.md), [simplification](references/simplification.md), [preferences](references/preference-model.md), [patterns](references/pattern-promotion.md), [evolution](references/evolution-policy.md), or [side effects](references/side-effects.md).

## Invariants
- Existing valid work beats restarting.
- Thread length alone never justifies planning, delegation, or extra context.
- Escalations need information value and a stop condition.
