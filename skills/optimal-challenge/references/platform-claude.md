# Claude Code Adapter

Use only when operating in Claude Code or an equivalent local agent harness.

- Prefer local filesystem/source and git for durable code truth.
- Current Claude models can over-delegate when subagents are available; explicitly keep simple, sequential, single-file, or shared-context work in the main agent.
- Fresh contexts can be preferable to compaction when state is checkpointed to files/tests/git.
- Skills are loaded progressively; avoid force-loading optional references.
- Plugin hooks accumulate across sources, so add only earned deterministic hooks and watch duplicate/overlapping triggers.
- Keep model-specific tuning here rather than in the platform-neutral router.
