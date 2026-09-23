---
name: optimal-challenge
description: Use when handling any request, including simple tasks, continued threads, and work that may need another skill.
---

# Optimal Challenge

## Purpose
Act as the lightweight top-level router for every request. Minimize context and compute while preserving correctness. System, developer, and explicit user instructions remain authoritative.

## Fast routing
1. Read the request and only the relevant current context. Detect any existing design, approved plan, checkpoint, or unfinished execution state.
2. If the task is stable, single-step, and low-risk, answer or act directly. Load no reference or process skill.
3. Otherwise classify it as structured, tool-assisted, multi-workstream, or high-assurance.
4. Reuse an applicable approved plan. Continue its next unfinished step without brainstorming or writing another plan. Replan only when requirements invalidate it, required decisions are missing, or the user asks.
5. Select the smallest specialist whose advertised trigger matches the current need. Availability and internal claims of universal use are not selection evidence.

## Superpowers boundary
- Never invoke `superpowers:using-superpowers`; this router replaces it.
- Do not invoke `superpowers:brainstorming`, `superpowers:writing-plans`, or another Superpowers process skill merely because it exists, the thread is long, or its instructions say it is mandatory.
- Invoke a Superpowers specialist only when this router selects it for a genuine unmet need. Once selected, it governs only that assigned work, then returns control here.

## Conditional depth
Load only what can change the next decision: [routing](references/routing.md), [codebase reality](references/reality-model.md), [environment](references/environment-storage.md), [context](references/context-management.md), [Codex](references/platform-codex.md), [Claude](references/platform-claude.md), [delegation](references/delegation-budget.md), [verification](references/verification.md), [simplification](references/simplification.md), [preferences](references/preference-model.md), [patterns](references/pattern-promotion.md), [evolution](references/evolution-policy.md), or [side effects](references/side-effects.md).

## Invariants
- Existing valid work beats restarting a process.
- Thread length alone never justifies planning, delegation, or extra context.
- Every escalation needs expected information value and a stop condition.
- Deliver the result; keep routing mechanics out unless decision-relevant.
