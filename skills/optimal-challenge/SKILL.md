---
name: optimal-challenge
description: Use when a request has material uncertainty, multiple dependent steps, meaningful cost of error, competing approaches, long-running context, or could substantially benefit from choosing among skills, tools, research, files, agents, or external capabilities.
---

# Optimal Challenge

## Core rule
Maximize useful quality per unit of context and compute. Do not escalate merely because a capability exists.

## Runtime loop
1. **Goal:** infer outcome, success condition, and hard constraints. Ask only when unresolved ambiguity can materially change the result.
2. **Triage:** if the task is simple, answer directly. If enhanced handling is clearly valuable, proceed. If its value is genuinely uncertain, ask whether the user wants the deeper path. Load `references/routing.md` only when the boundary itself needs guidance.
3. **Reality:** for non-trivial codebase work, load `references/reality-model.md` before planning.
4. **Environment:** when persistence, files, or long-running work matter, load `references/environment-storage.md` and `references/context-management.md`; load `references/platform-codex.md` or `references/platform-claude.md` only for platform-specific tuning.
5. **Route:** choose the smallest adequate specialist capability. Do not reproduce a specialist workflow here.
6. **Delegate carefully:** if agents are considered, load `references/delegation-budget.md`. The parent owns planning; workers get narrow capability leases.
7. **Verify proportionally:** load `references/verification.md` when correctness needs evidence.
8. **Simplify:** after creating or changing something, use `references/simplification.md` when simplification could materially improve it.
9. **Deliver:** lead with the result. Keep orchestration details out unless they are decision-relevant.
10. **Learn cheaply:** record only durable state or meaningful recurrence. Load `references/preference-model.md`, `references/pattern-promotion.md`, or `references/evolution-policy.md` only when their triggers occur.

## Invariants
- Prefer evidence over assumption and references over copied context.
- Every escalation needs expected information value and a stop condition.
- Preferences optimize defaults, never truth, safety, explicit requirements, or project isolation.
- Skills/hooks are promoted from repeated evidence, not one-off events.
- External/destructive actions follow `references/side-effects.md`.
