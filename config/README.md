# Project configuration

This folder is the canonical home for project-owned, shareable configuration. `project.json` supplies maintenance metadata used by validation and packaging workflows so names, versions, paths, and commands are not repeated in scripts.

Tool-required manifests remain at the repository root or their mandated discovery paths. Validation checks them against `project.json` to catch drift.

## Deterministic release packaging

Run `python scripts/package_release.py` to build the archive named by
`paths.package`. The packager selects files using `packaging.excludes`, writes
members in sorted POSIX-path order with a fixed 1980-01-01 timestamp and
regular-file `0644` permissions, then reopens the ZIP and compares every
selected byte with source. It rejects symlinks, missing members, unexpected
members, duplicate members, unsafe paths, and changed bytes. A successful run
prints the file count and SHA-256; `dist/` remains ignored and is never staged.

The exclusion list removes Git and agent-local state, generated archives,
caches, planning documents, and local/raw evaluation results. Portable,
Codex, and Claude manifests; runtime skills and templates; committed schemas
and defaults; public documentation/legal/support files; validators; sanitized
evaluation fixtures; and distributable validation tests remain in the archive.
Fresh-host acceptance remains `UNVERIFIED` until Task 10 records isolated runs;
an archive hash proves artifact identity, not host-model behavior.
The shipped evaluation manifest cannot embed its own SHA-256 without changing
the archive it identifies. Task 9 therefore reports the deterministic hash as
external build evidence and keeps candidate arms explicitly provisional. Task
10 pins and verifies the installed subject during isolated host runs; packaging
must not rewrite provisional identity into a false verified claim.

## Precedence

Orchestration policy has one access path: call
`scripts.orchestration_config.load_effective_config(...)`. From highest to
lowest authority, effective settings come from system/developer/host/repository
instructions, safety and permission constraints, explicit current-request
constraints, `.optimal-challenge/orchestration.local.json`, committed
`orchestration.json`, and built-in defaults. The Python loader applies the last
three machine-readable layers; callers remain responsible for higher-authority
instructions and pass current-request settings as `task_override`.

`orchestration.schema.json` validates the complete effective configuration.
The local file uses the same key tree but may omit unchanged keys because the
loader merges it into a complete configuration before validation. Unknown
keys fail. Built-ins are validated first; the committed, local, and task
layers are each merged and validated before the next layer is read, so a
higher-precedence value cannot hide an invalid lower layer. The existing
`.optimal-challenge/` ignore rule covers `orchestration.local.json` and all
reconstructable runtime state.

Never store passwords, tokens, private keys, or live credentials here. Commit only sanitized examples and document the type, purpose, default, and allowed values of every setting.

## Orchestration settings

| Key | Committed default | Allowed values and purpose |
|---|---:|---|
| `schema_version` | `1` | Configuration contract version; only `1` is accepted. |
| `mode` | `auto` | `inline-only`, `auto`, or `team-requested`. Direct fast-path work remains quiet. |
| `profile` | `balanced` | `economy`, `balanced`, `quality`, or `custom`. Selecting a named profile without explicit weights loads its documented weights. |
| `objective_weights.quality` | `0.45` | Number from 0 to 1. Balanced utility weight; Economy is `0.35`, Quality is `0.50`. |
| `objective_weights.cost` | `0.20` | Number from 0 to 1. Economy is `0.35`, Quality is `0.10`. |
| `objective_weights.latency` | `0.10` | Number from 0 to 1. Economy is `0.10`, Quality is `0.05`. |
| `objective_weights.attention` | `0.10` | Number from 0 to 1 for every named profile. |
| `objective_weights.rework` | `0.15` | Number from 0 to 1. Economy is `0.10`, Quality is `0.25`. |

The five objective weights must sum to 1. Applying a named profile atomically
loads its fixed weights and delegation margin: Economy uses `3`, Balanced uses
`1`, and Quality uses `1`. Custom begins with Balanced weights and margin `1`
unless the same layer supplies normalized weights or a margin from 1 to 12.
This reset prevents values selected by a lower-precedence profile from leaking
into the active profile.

| Key | Default | Allowed values and purpose |
|---|---:|---|
| `team_limits.max_active_specialists` | `3` | Integer 0 to 3; the normal active-specialist cap, excluding the coordinator. |
| `team_limits.exact_specialists` | `null` | `null` or integer 0 to 32. An explicit count is additionally bounded by `min(32, detected_host_max)`. |
| `team_limits.delegation_margin` | `1` | Economy requires `3`; Balanced and Quality require `1`; Custom accepts integer 1 to 12. |
| `team_limits.allow_mode_margin_override` | `false` | Boolean. Custom does not let `team-requested` reduce its margin unless explicitly enabled. |
| `team_limits.retry_limit` | `1` | Integer 0 to 12; retries still require new information or capability. |
| `team_limits.capability_class` | `standard` | `economy`, `standard`, `reasoning`, or `frontier`; provider-neutral only. |
| `premise_gate.enabled` | `true` | Boolean master switch for non-direct premise checks. |
| `premise_gate.apply_to_direct_fast_path` | `false` | Boolean; keep `false` to preserve quiet stable, single-step, low-risk work. |
| `premise_gate.risk_threshold` | `4` | Integer 0 to 9; minimum risk product for a blocking user question. |
| `premise_gate.question_value_threshold` | `0` | Integer -3 to 9; question value must be greater than this threshold. |
| `premise_gate.investigate_first` | `true` | Boolean; resolve cheaply knowable facts before asking. |
| `premise_gate.use_reversible_defaults` | `true` | Boolean; proceed with recorded safe defaults when allowed. |
| `verification.default_depth` | `targeted` | `self-check`, `targeted`, or `independent`. Mandatory consequence rules still outrank this default. |
| `verification.review_margin` | `3` | Integer 1 to 27; Balanced review-value margin. |
| `verification.mandatory_independent_review` | `false` | Boolean task-wide override; consequence-based mandatory review remains in force. |
| `verification.compensating_oracle_requires_user_acceptance` | `true` | Boolean; unavailable mandatory review is not silently waived. |
| `persistence_privacy.runtime_state` | `local` | `none`, `local`, or `provider`; does not itself activate provider retention. |
| `persistence_privacy.state_directory` | `.optimal-challenge` | Non-empty path for disposable local state. |
| `persistence_privacy.persist_transcripts` | `false` | Boolean; transcripts are excluded by default. |
| `persistence_privacy.persist_sensitive_data` | `false` | Boolean; credentials, sensitive traits, and raw private data remain excluded. |

### Budget truthfulness

| Key | Default | Allowed values and purpose |
|---|---:|---|
| `budget.unit` | `null` | `null`, `credits`, `tokens`, `seconds`, `currency`, `tool_calls`, or `model_calls`. Units are never converted without a verified mapping. |
| `budget.limit` | `null` | `null` or a positive number in the configured unit. Unit and limit are set or cleared together. |
| `budget.measurement` | `unavailable` | `unavailable`, `estimated`, or `observed`. |
| `budget.enforcement` | `advisory` | `advisory`, `local_enforced`, or `provider_enforced`. |
| `budget.measurement_source` | `null` | `null` or a non-empty description of the authoritative counter. |
| `budget.soft_threshold` | `null` | `null` or a positive value no greater than `limit`; optional work is reduced at this point. |

Any measurement may support an advisory ceiling. `local_enforced` and
`provider_enforced` require `observed` measurement, a non-empty
`measurement_source`, and a separate trusted `VerifiedCapabilityContext`.
Capability evidence is intentionally absent from committed, local, and task
configuration; an `adapter_capabilities` key is rejected as unknown and cannot
authorize enforcement.

The host or Task 6 capability resolver supplies `capability_context` directly
to `load_effective_config` or `validate_config`, together with
`expected_surface` and `expected_version`. The frozen context contains exact
`surface`, `version`, `provenance`, `evidence_ref`, timezone-aware
`verified_at` and `expires_at`, `observed_usage`, and booleans for the local and
provider stop primitives. Provenance is `live_detection` or `acceptance_run`.
Validation requires an exact surface/version match, non-empty evidence,
current unexpired timestamps, observed usage, and the stop primitive matching
the configured enforcement mode. Missing or mismatched trusted context fails
closed. Therefore the defaults are advisory and do not promise automatic
prevention, exact remaining spend, or cancellation of running work.

Example one-request override:

```python
load_effective_config(root, task_override={"mode": "team-requested", "profile": "quality"})
```

## Development schema validation

Runtime configuration code uses only the Python standard library. Tests use
the pinned Draft 2020-12 and PyYAML implementations in `requirements-dev.txt`.
Use Python 3.12 (including Codex's bundled Python 3.12) so pinned binary wheels
are available. On PowerShell, install them outside the repository and expose
only that temporary target to the test process:

```powershell
$validationDeps = Join-Path $env:TEMP 'optimal-challenge-validation-deps'
$python312 = '<path-to-python-3.12>' # Codex's bundled Python 3.12 is suitable.
& $python312 -m pip install --disable-pip-version-check --target $validationDeps -r requirements-dev.txt
$env:PYTHONPATH = $validationDeps
& $python312 -m unittest discover -v
```

## Deliberately retained literals

- Plugin and marketplace manifests repeat the name, version, repository, schemas, source, and skills path because their platforms require self-contained metadata; validation compares each copy with `project.json`.
- Publisher, policy, and support URLs remain in manifests and user documents where they are public metadata rather than deploy-varying configuration.
- Fake paths and placeholders in documentation remain local to their examples and must never contain machine-specific or secret values.
- Release-history text under `submission/` records the release it describes and is not runtime configuration.
