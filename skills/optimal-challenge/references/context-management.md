# Context Management

Treat conversation history as disposable working memory, not canonical project state.

## Working-set rule
Each pass receives the minimum sufficient context for its task: goal, relevant constraints, current state, necessary decisions/evidence, capability lease, and return contract.

## Temperature tiers
- **HOT:** current task and immediate evidence; load now.
- **WARM:** goal, constraints, current state, relevant decisions; cheap to reload.
- **COLD:** completed tasks, older research, superseded details; reference only.
- **ARCHIVE:** raw transcripts, logs, dumps; load only for investigation.

## State discipline
Persist only information future passes may need. Prefer pointers to source, tests, commits, files, or decision IDs over copied content.

Recommended logical state:
- `CHARTER`: goal, success criteria, invariants.
- `STATE`: current phase, verified status, blockers, next action. Rewrite, do not append forever.
- `DECISIONS`: concise durable decisions with IDs.
- `PATTERNS`: repeated friction/candidates only.
- `PREFERENCES`: scoped operational preferences only.
- `EVOLUTION`: skill-change candidates; never normal runtime context.

## Reset decision
Continue when context is clean and task-local. Checkpoint then compact around meaningful milestones. Prefer fresh context when changing phases, performing independent review, recovering from noisy/dead-end exploration, or when old state is confusing current decisions.

Before any reset, flush durable state. After reset, rehydrate from authoritative state and source, not from a narrative retelling.

## Plan continuity
Treat an applicable approved plan as WARM state. Locate it before invoking brainstorming or planning, confirm that its goal and constraints still match, then resume its next unfinished step. Do not recreate a plan because the thread is long, compacted, or resumed. Replan only when the existing plan is absent, materially invalidated, incomplete at a decision boundary, or explicitly rejected by the user.
