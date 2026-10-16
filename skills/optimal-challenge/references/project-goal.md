# Explicit local project-goal check

Use the target project's own instruction file, never Optimal's directory/CWD.
Resolve its Project ID, Project boundary and Goal relative to that instruction.
Goal JSON is a bounded contract in the existing goal.md, not a second state store.
Read prose/source corrections too; a validator cannot settle semantic conflicts.

Before substantive planning run `python -B scripts/project_goal.py` from this
plugin's source, with `--instruction <absolute target instruction>`;
`--project-id <its ID>`; `--target <absolute changed file/directory>`;
`--stage planning`; `--criterion <goal criterion>`; `--alignment in-scope`;
and `--contribution <short outcome-to-criterion explanation>`.
Use the JSON receipt's exact goal_sha256 as `--planned-hash` before delegation,
implementation and completion. Invoke the same command with the respective
`--stage delegation`, `--stage implementation`, or `--stage completion`.
Completion also needs `--artifact <readable actual evidence file>`.
Store receipts in the existing project's Codex/evidence task record; do not create
source-root logs. Multiple projects/files require separately bound checks.

The reviewer supplies alignment after comparing requested behavior/files and
acceptance to purpose/scope. Use `scope-change`, `conflict` or `unreviewed` to hold
the affected task. Drawio UI automation and AI Collab document-store expansion are
scope changes. A necessary regression for a promised bounded behavior is in scope.
Evidence readability/hash is not evidence sufficiency: inspect actual artifacts,
hosted rows and limitations. Unit counts/fixtures cannot fill hosted acceptance.
Owner corrections must be reconciled with sources before proceeding; do not blindly
follow stale prose or promote a draft. An unchanged valid goal has no age expiry.

## Native fallback when Python is unavailable

Read the target instruction and its actual goal directly. Record project/instruction
identity, target, stage, criterion, contribution, and the real goal hash using an
available native file-hash tool. Compare the planning hash at later stages and inspect
actual completion evidence. Wrong-project, missing, changed, draft or conflicting
goals hold the affected unconfirmed work for reconciliation. If the hash or goal
cannot be obtained, label it UNKNOWN and hold dependent claims/work; do not invent a
hash or call this PASS_LOCAL_CHECK, G1 acceptance, automatic enforcement or host-hook
coverage. Keep this receipt in existing task evidence, not a new global state store.

## CLI result and coverage

Exit 0 is PASS_LOCAL_CHECK; exit 2 is HOLD with a specific reason. Draft broader
visions outside the canonical confirmed narrow contract do not block that contract.
PARKED goals cannot activate through this command. Symlink/junction canonicalization
uses the actual filesystem; containment is by path components. No parent fallback.

Coverage: four stages of this explicitly invoked local CLI/instruction workflow.
Bypasses: direct shell/tool operations, agents ignoring instructions, installed cache,
ChatGPT and Claude host paths without a proven invoking hook. No automatic blocking,
host adoption, global enforcement or semantic intent detection is claimed.
Do not edit installed caches; use the existing scoped maintenance/reload route after
the source is reviewed. Ah Pip's ChatGPT maintenance responsibility remains separate.
