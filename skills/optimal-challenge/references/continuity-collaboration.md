# Continuity and Collaboration

Load this module for multi-pass work, a likely quota or session boundary, multiple user decisions, reusable code/configuration output, or project initialization.

## Checkpoint and resume

Create or refresh the canonical project-state file at a meaningful milestone, before a known quota/session boundary, before a phase or agent handoff, and whenever completed work may otherwise be lost. Use `templates/PROJECT-STATE.md`; in a local repository, default to the tracked `docs/PROJECT-STATE.md` unless project instructions name another durable location.

This single file combines current state and the development path using Now / Next / Later. It is a compact restart contract, not a transcript. Record completed and verified work, changed artifacts, unresolved risks, pending decisions, and one exact next action. Never record secrets or create parallel checkpoint, roadmap, or state files. On resume, read it plus authoritative source files, confirm that the recorded state still matches reality, then continue without replaying completed work or recreating a valid plan.

## Question bundle

After the cheapest useful investigation, collect every currently knowable user decision before pausing. Use one numbered question bundle based on `templates/QUESTION-BUNDLE.md`. Each item states the decision, viable choices, recommended default, why it matters, and what it blocks. Separate required decisions from optional preferences.

Follow the bundle with next steps: what happens if the defaults are accepted, how answers change the route, and any safe work that can continue meanwhile. New evidence may justify a later bundle; do not drip questions that could have been identified together.

## Reusable snippets

When producing code, commands, configuration, or prompts intended for reuse, use the contract in `templates/REUSABLE-SNIPPET.md`:

- expose environment-specific values as named inputs or options;
- keep the core operation separate from integrations and side effects;
- state assumptions, adaptation points, and a verification command or check;
- use safe placeholders instead of real credentials, tokens, account IDs, or personal paths;
- avoid hard-coded project details unless the user explicitly asks for a fixed one-off artifact.

Prefer a small complete example with clear seams over several near-duplicates.

## Safe repository start

When initializing a project, define `.gitignore` before creating generated or private files. Start with secret/env files, credentials and private keys, local agent state, logs, caches, dependencies, build output, editor metadata, and OS noise; then add stack-specific entries. Keep sanitized example files shareable with explicit negation rules.

Before the first commit, inspect `git status` and scan the staged set for secrets. A `.gitignore` is preventive, not retroactive: if a sensitive file is already tracked, stop and remove it from tracking or history using a risk-appropriate workflow.
