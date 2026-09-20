# Environment and Storage

Detect capabilities instead of assuming one persistence model.

## Environment probe
Determine only what matters to the task:
- durable filesystem available?
- git/version history available?
- project/cloud file store available?
- temporary compute storage only?
- connected storage/apps available?
- skills/hooks/subagents available?

## Storage contract
Persist information in the cheapest authoritative medium available; keep references in model context.

### Local repository / Codex-style workspace
Prefer source files + git as truth. Use repo instructions for stable conventions, repo/user skills for reusable workflows, and gitignored state/cache for agent-local working state. Prefer commit/diff references to chat summaries.

### Cloud project / Chat-style workspace
Prefer project instructions/files for durable project state, reusable cloud files/library for reusable artifacts where available, and chats as disposable reasoning sessions. A new chat should reconstruct from selected project state rather than replay the old transcript.

### Hybrid work
Keep code truth with the repository/version control and coordination/research/user-facing artifacts in durable cloud storage. Do not duplicate an entire repo into cloud context when targeted local reads are available.

## Ephemeral compute
Treat scratch disks, browser-computer files, temp directories, and uncertain runtime storage as cache. Promote anything that must survive into a known durable store before ending the pass.
