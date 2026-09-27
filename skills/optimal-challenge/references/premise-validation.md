# Premise validation

Enter this gate only after the router rejects stable, single-step, low-risk direct work. Direct work gets no premise score, profile disclosure, or decision bookkeeping.

## Establish the brief

Before decomposition, capture the goal and observable success criteria, constraints and authoritative evidence, material assumptions, reversible defaults, and irreversible or high-rework choices. Investigate facts available from tools, repository state, or settled decisions before asking the user.

When production at scale would make rejection, paid generation, or rework materially costly, use [research before scale](high-cost-research.md) to establish acceptance criteria and validate a representative pilot before scaling.

For each unresolved material premise, record evidence and evidence provenance, then calculate:

```text
PremiseRisk = WrongnessLikelihoodRating * ReworkCost
QuestionValue = ExpectedReworkAvoided - UserAttentionCost
```

Use ordinal policy scores, not invented probability or currency:

| Score | WrongnessLikelihoodRating | ReworkCost | UserAttentionCost |
|---|---|---|---|
| 0 | authoritative evidence settles it | none | none |
| 1 | unlikely alternative | local reversible edit | quick low-context choice |
| 2 | plausible alternatives | multi-step or multi-file redo | context switch or related choices |
| 3 | conflicting evidence; no defensible default | architecture, irreversible action, or broad waste | sensitive or externally coordinated choice |

`PremiseRisk` ranges from 0 to 9. Independently justify `ExpectedReworkAvoided` from 0 to 9 and never score it above `PremiseRisk`: 1-3 avoids local rework, 4-6 avoids multi-step or one-worker rework, and 7-9 avoids architectural, irreversible, or broad parallel waste.

## Investigate, default, or ask

Ask only when `PremiseRisk >= 4`, `QuestionValue > 0`, the answer changes the work graph or an irreversible choice, and neither cheap investigation nor a safe reversible default resolves it. Otherwise investigate or record the reversible default and continue.

When asking, use one question bundle (`templates/QUESTION-BUNDLE.md`) containing every currently knowable user-only blocker, a recommended default, impact, and next steps. Keep optional preferences non-blocking and identify safe work that can continue. Do not ask for mode, profile, or budget merely to expose configuration.

Give every material answer a stable decision ID in authoritative durable state. Never re-ask a settled decision unless new contradictory evidence invalidates it; cite that evidence and the invalidated decision ID. A later bundle contains only newly discovered blockers.

The record includes factor ratings, provenance, evidence IDs, threshold, chosen default or question ID, and a plain-language decision reason. Use `scripts/evaluate_routing.py` for deterministic calculation checks.
