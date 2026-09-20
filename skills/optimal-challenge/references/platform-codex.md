# Codex Adapter

Use only when operating in Codex or an equivalent durable local/repository environment.

- Prefer filesystem, repo instructions, tests, and git history over conversational reconstruction.
- Keep reusable cross-repo skills in the supported user skill location; keep repo-specific skills/instructions with the repository.
- Use fresh contexts freely after durable checkpoints; reconstruct from source/state/git.
- Keep caches and temporary agent state gitignored unless humans benefit from them.
- Treat hooks as deterministic enforcement and keep their trigger/cost surface small.
- Use subagents only past the delegation break-even gate; give each an explicit skill/tool budget.
