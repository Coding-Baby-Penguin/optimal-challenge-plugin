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
