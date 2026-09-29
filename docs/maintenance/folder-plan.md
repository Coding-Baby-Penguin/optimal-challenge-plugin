# Quality recovery move and lifecycle map

The public commands and imports under `scripts/` remain compatibility facades. Move only responsibilities that have separate owners; preserve test outputs and return codes through each migration. A failed migration rolls back its focused files to the preceding candidate commit, then reruns the full quality gate.

| Current owner | New owner | Consumers and checks | Rollback boundary |
|---|---|---|---|
| `scripts/orchestration_state.py` ledger events, accounting and hashing | `scripts/optimal_challenge/ledger.py` | `apply_ledger_event` facade; `validate_orchestration.py`, state tests, fixture replay | Restore ledger and facade together |
| Same file structural/cross-record validation | `scripts/optimal_challenge/state_validation.py` | `validate_orchestration_state` facade, schema files, recursive malformed corpus | Restore validation and facade together |
| Same file recovery and protected dispatch | `scripts/optimal_challenge/recovery.py` | `recover_state`/`prepare_dispatch` facades, continuity and dispatch policy | Restore recovery and facade together |
| `scripts/capability_matrix.py` proof classes and issuance registry | `scripts/optimal_challenge/capability_evidence.py` | Same class objects re-exported by facade, exact-surface capability tests | Restore proof owner and facade together |
| Same file support/fallback resolution | `scripts/optimal_challenge/capability_resolution.py` | `resolve_capability` facade, `validate_capability_contracts`, platform docs | Restore resolver and facade together |
| `scripts/evaluate_behavior.py` manifest/bundle contracts | `scripts/optimal_challenge/evaluation_contracts.py` | `validate_run_bundle` facade; canonical pins and fixture tests | Restore contracts and facade together |
| Same file typed semantic formulas | `scripts/optimal_challenge/evaluation_semantics.py` | Formula diagnostics and typed calculation regression tests | Restore semantics and facade together |
| Same file paired statistics | `scripts/optimal_challenge/evaluation_statistics.py` | 95% paired confidence and cost/latency tests | Restore statistics and facade together |
| Same file comparison/CLI | `scripts/optimal_challenge/evaluation_comparison.py` plus existing CLI facade | `compare_arms`, `python scripts/evaluate_behavior.py`, benchmark CLI exit tests | Restore comparison and facade together |

Consumers to check after every migration: both `from scripts...` library imports and `python scripts/*.py` standalone commands; `scripts/validate.py`, `scripts/validate_orchestration.py`, tests/validation imports and private formula diagnostic; `config/project.json` paths, Codex/Claude manifests, packaging selections, CI runner and relative Markdown links. Do not duplicate proof class definitions; a facade alias must preserve `is` identity. Keep small config/routing/research/package modules intact.

Placement: stable reviewed guarantees under `config/`; mutable checkpoint only `docs/PROJECT-STATE.md`; sanitized conclusions in `docs/reviews/`; historical plans in `docs/superpowers/`; raw task/grade/receipt data in ignored `tests/results/<evaluation-id>/`; local recovery state in ignored `.optimal-challenge/`; wheel/test scratch in ignored `tmp/quality/`; reproducible archives in ignored `dist/`. Package selection excludes historical reviews/plans and raw/local/scratch output, while keeping contributor guidance and runtime references. Inspect ignored inventory for private files before install; install from clean extracted immutable archives, because local worktree marketplace sources can copy ignored files.
