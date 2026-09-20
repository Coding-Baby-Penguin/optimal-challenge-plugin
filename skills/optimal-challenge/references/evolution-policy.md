# Skill Evolution Policy

The adaptation engine is dormant during ordinary tasks. Wake it only when pattern evidence justifies evaluation.

## Separate loops
- **User adaptation:** improve defaults and interaction fit.
- **Skill evolution:** improve workflow success/cost/stability.
Never encode a temporary user preference as generic skill logic.

## Candidate change test
Before promotion, define:
1. observed repeated failure/opportunity;
2. proposed minimal change;
3. positive cases the change should improve;
4. negative/ordinary cases it must not harm;
5. quality, cost, stability, and user-effort metrics;
6. rollback path.

Changes should improve target behavior without unacceptable regressions or disproportionate context/compute cost.

## Mutation boundaries
Low-risk reversible routing/reference/context/default changes may be tested and promoted autonomously when the environment supports versioned rollback. Major workflow changes require stronger regression evidence.

Never autonomously expand privileges, weaken safeguards, approve destructive/external side effects, cross project/privacy isolation, infer/store sensitive traits, or redefine user goals.

## Prevent bloat
Evolution includes ADD, REFINE, SPLIT, MERGE, PRUNE, and RETIRE. When a specialist workflow grows substantial, split it from the router. Re-evaluate old scaffolding after model/platform changes rather than only adding instructions.
