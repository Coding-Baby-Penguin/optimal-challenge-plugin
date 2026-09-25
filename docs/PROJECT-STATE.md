# Project state

- **Goal:** Maintain a lightweight routing plugin with reliable continuity, visible failures, reusable output, safe configuration, folder planning, and current user documentation.
- **Success criteria:** Runtime policies are lazy-loadable, repository structure and configuration are validated, all tests pass, and another work pass can resume without chat history.
- **Last updated:** 2026-09-25
- **Current verified state:** Configuration governance, README maintenance, unified project state, visible failure reporting, continuity templates, question bundling, reusable snippets, secure ignore defaults, adaptive folder planning, and separate Codex and Claude marketplace catalogs are implemented.
- **Completed:** Required failures, partial results, skipped checks, retries, fallbacks, and unfinished background work now use an explicit outcome and recovery contract; unresolved failures persist across resume boundaries.
- **Changed artifacts:** `skills/optimal-challenge/references/failure-visibility.md`, `skills/optimal-challenge/templates/FAILURE-REPORT.md`, `skills/optimal-challenge/templates/PROJECT-STATE.md`, `skills/optimal-challenge/SKILL.md`, `README.md`, `scripts/validate.py`, `tests/scenarios.json`, `tests/validation/test_package.py`, and this state file.

## Development path

- **Now:** The failure-visibility contract is implemented and covered by structural and pressure scenarios.
- **Next:** Reinstall or update the plugin and verify failure reporting in a fresh Codex or Claude task.
- **Later:** Add model-level behavioral evaluations when the host provides a repeatable evaluation runner.

## Continuity

- **Workflow convention:** After all required testing and validation pass, commit and push completed repository changes unless the user explicitly says not to.
- **Blockers:** None currently known.
- **Unresolved failures:** None in the repository validation run; host-level behavioral confirmation remains a separate acceptance step.
- **Pending decisions:** A future release may bump the plugin version when behavior changes; this compatibility catalog keeps version `1.1.0` because plugin behavior is unchanged.
- **Verification evidence:** 25 unit validations and 49 structural behavior scenarios pass. Five fresh pressure samples consistently reported status, failed operation, evidence, impact, retry/fallback state, and a concrete next action. Package, adversarial, and Claude marketplace validation pass.
- **Next concrete action:** Run the full validators, then test one failed command and one skipped required check in a fresh installed task.
- **Resume command or entry point:** `git status --short` followed by `python -m unittest -v tests.validation.test_package`
