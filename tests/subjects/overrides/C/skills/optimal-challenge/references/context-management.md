# Context Management

Treat conversation history as disposable working memory, not canonical project state.

## Working-set rule
Each pass receives the minimum sufficient context for its task: goal, relevant constraints, current state, necessary decisions/evidence, capability lease, and return contract.

For team work in this evaluation-only C arm, carry stable decision IDs and source pointers through task capsules. Use fresh independent workers for each assignment; do not invoke `team-continuity.md`, resume or rehydrate a logical teammate, or carry full transcripts to simulate identity. Keep any disposable work registry subordinate to authoritative source, tests, and project state.

Context size is a cost, not a quality signal. More history can increase distraction and hallucination without improving the decision.

## Relevance filter
Retain an item in the active working set only when it can change at least one observable:

- the root goal or current subgoal;
- a material constraint or decision;
- the next action;
- success verification; or
- recovery from a known failure.

Otherwise replace it with a source pointer, classify it as **COLD** when it may matter later, or move raw detail to **ARCHIVE**. Do not forward completed investigation, abandoned approaches, duplicated evidence, or full transcripts merely because they exist.

## Goal-drift checkpoint
Before costly research, delegation, replanning, or review, record the compact answers to:

- **Success criterion advanced:** which root-goal criterion changes?
- **Output or decision:** what concrete result will this action produce?
- **Smallest adequate action:** can a cheaper bounded action answer it?
- **Stop condition:** what evidence ends the work?
- **Consequence of skipping:** what material risk remains if it is omitted?

If the action cannot connect to the root goal and a success criterion, prune it. A technically excellent tangent is still waste when it advances the wrong outcome. Cheap, reversible direct work remains direct; do not add goal-management ceremony where the checkpoint would cost more than the task.

## Temperature tiers
- **HOT:** current task and immediate evidence; load now.
- **WARM:** goal, constraints, current state, relevant decisions; cheap to reload.
- **COLD:** completed tasks, older research, superseded details; reference only.
- **ARCHIVE:** raw transcripts, logs, dumps; load only for investigation.

## State discipline
Persist only information future passes may need. Prefer pointers to source, tests, commits, files, or decision IDs over copied content.

Recommended logical state:
- `PROJECT-STATE`: goal, success criteria, current verified status, completed work, Now / Next / Later development path, blockers, pending decisions, evidence, and next action. Rewrite, do not append forever.
- `DECISIONS`: concise durable decisions with IDs when decision history must outlive the current project state.
- `PATTERNS`: repeated friction/candidates only.
- `PREFERENCES`: scoped operational preferences only.
- `EVOLUTION`: skill-change candidates; never normal runtime context.

## Reset decision
Continue when context is clean and task-local. Checkpoint then compact around meaningful milestones. Prefer fresh context when changing phases, performing independent review, recovering from noisy/dead-end exploration, or when old state is confusing current decisions.

Before any reset or phase change, flush the single canonical project-state file, preserve the root goal, and rebuild the HOT/WARM working set for the new phase. Do not create separate checkpoint, roadmap, or state files. After reset, rehydrate from authoritative state and source, not from a narrative retelling.

## Plan continuity
Treat an applicable approved plan as WARM state. Locate it before invoking brainstorming or planning, confirm that its goal and constraints still match, then resume its next unfinished step. Do not recreate a plan because the thread is long, compacted, or resumed. Replan only when the existing plan is absent, materially invalidated, incomplete at a decision boundary, or explicitly rejected by the user.
