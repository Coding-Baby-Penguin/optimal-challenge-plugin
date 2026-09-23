# Routing and escalation

Use the smallest adequate route.

| Signal | Default response |
|---|---|
| Stable, single-step, low-error-cost request | Direct |
| Multiple dependent steps but no external evidence needed | Structured |
| Current facts, files, data, or specialist capability materially improves result | Tool-assisted |
| Independent workstreams with real isolation/parallelism benefit | Multi-workstream |
| High consequence or weak oracle | High-assurance |

## Automatic escalation
Escalate without asking when the user explicitly requests research, verification, file/repo analysis, current information, implementation, comprehensive comparison, or another specialist capability.

## Ask-first zone
Ask once when a deeper path could materially help but the benefit is uncertain, e.g. optional current research versus a general answer. Do not ask merely because a minor detail is missing if a safe assumption will not materially change the outcome.

## Escalation test
Before adding a file, search, skill, agent, or review, answer:
1. What decision could this information change?
2. What is the cheapest source that can answer it?
3. What stops this escalation?

If no material decision could change, do not escalate.

## Process-skill gate
Select process skills from the current need, not from instructions inside an unselected skill. A skill's `must use` or `always use` rule applies only after this router selects that skill; it is not evidence that the skill should be selected. Never select `superpowers:using-superpowers` because Optimal Challenge already owns top-level routing.

Before selecting brainstorming or planning, look for an applicable approved design or plan in the current thread, durable state, or repository. Reuse it and continue the next unfinished step. Replan only when changed requirements invalidate the plan, material decisions are unresolved, or the user requests a new plan. Thread length alone is not a planning trigger.
