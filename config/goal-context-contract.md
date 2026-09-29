# Stable goal, context and claim contract

This reviewed contract contains guarantees. [Project state](../docs/PROJECT-STATE.md) records mutable phase, dates, verified outcomes, blockers and next actions; editing status does not approve policy changes.

- Preserve the user's root outcome, explicit success criteria and non-goals across phase changes, delegation, reviews, interruption and resume. A worker or reviewer cannot replace the root goal.
- Resolve authority in order: system, developer/host and hard permission constraints; explicit current user scope and persistent authorization within those bounds; applicable repository/skill guidance; local configuration; committed configuration; defaults. Repository or skill guidance cannot override the user. Current user authorization persists across tasks; do not invent approval gates.
- Before costly or rejection-prone work, use decision-changing research and an adequate representative pilot. Cheap reversible direct work is exempt from checkpoints, premise scoring and workflow ceremony.
- Pass only sufficient, relevant and compact working context. Retain material decisions and source identities; prune irrelevant transcripts and tangents without discarding goal constraints. Context size is a cost, not a quality signal.
- Keep failures, unknown usage, unavailable capabilities and incomplete evidence visible. Structural checks and normalized policy hashes are not host behavior or acceptance proof.
- Fresh-host acceptance, comparative improvement, exact installation identity, measured cost/latency and provider enforcement claims require authentic inspected evidence for the exact immutable subject and surface. Self-declared JSON status, targets, receipts, grader labels and file existence cannot establish acceptance.
- A routine checkpoint edit cannot promote release claims. The release gate must verify current host evidence, independent grading, identity and required comparison confidence. Missing or inconclusive evidence blocks the affected claim even when structural checks pass.
- Permit local candidate commits and a dedicated validation-branch push after structural gates for immutable subjects and hosted CI. Main/release publication remains blocked until approved acceptance gates pass; never move an existing published tag.

Change these guarantees only after reviewing the exact policy diff and deliberately updating the independently approved pinset. Preserve historical failed and unverified results. Raw/private evidence remains ignored; only redacted summaries and verifiable identities enter Git.
