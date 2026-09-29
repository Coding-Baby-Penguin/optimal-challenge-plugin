# Team orchestration

Create a team only after the direct and premise gates and the economic delegation gate select real separable work. The coordinator remains the sole user-facing process authority unless the user explicitly requests a handoff.

## Invocation and precedence

- `inline-only`: create no specialists. If mandatory independent review or another equal-authority constraint conflicts, ask one concise resolution question rather than spawning silently.
- `auto`: apply premise, delegation, allocation, continuity, and review gates.
- `team-requested`: actively seek valuable decomposition, but retain positive-value, safety, permission, availability, and envelope gates.
- An explicit exact specialist count is workers in addition to the coordinator. The configured range is 0 to 32 and the effective maximum is `min(32, detected_host_max)`. Zero means inline. A positive count overrides the economic margin, strong-benefit requirement, and normal three-specialist cap only within safety, permissions, host slots, an observable done condition, and the stated job envelope; warn once if materially wasteful. Resolve ambiguous wording such as "a team of three" from context or, when cost changes materially, with one concise question. If it cannot fit, ask one concise expansion, wait, or route question rather than reducing it silently.

Authority descends from system, developer/host and hard permission constraints; explicit current-request user scope and persistent authorization within those bounds; applicable repository/skill guidance; `.optimal-challenge/orchestration.local.json`; `config/orchestration.json`; then built-in `auto`/`balanced`. Repository or skill guidance cannot override the user. Mandatory independent review or an exact count outranks a general mode at the same request level. Invalid values fail visibly; any safe fallback is labelled degraded.

Mode or profile is surfaced only when it materially changes routing, cannot be honored, or the user asks. Routine direct work stays quiet.

Resolve machine-readable policy only with `load_effective_config` from `scripts/orchestration_config.py`; never manually merge precedence layers. Enforcement capability is a trusted external `VerifiedCapabilityContext` with exact surface/version, supported provenance and evidence, freshness, an observed counter, and the matching stop primitive. It cannot come from task, local, or committed configuration.

## Dispatch contract

Build the minimum dependency graph and partition write ownership. Activate `templates/TEAM-CHARTER.md` only for a selected team. Every assignment gets `templates/task-capsule.yaml`, an observable done condition, minimum evidence, authority flags, capability lease, allocation, stop condition, and return contract. Workers cannot ask the user, cannot expand scope, cannot spawn descendants, cannot change profile, and cannot acquire permissions unless the coordinator explicitly leases that capability. Returns use `templates/RETURN-CAPSULE.yaml`; malformed returns remain partial or failed, never silently complete.

Runtime state must conform to `config/team-registry.schema.json` and `config/allocation-ledger.schema.json`. Before dispatch, reservation, or reconciliation, validate the current and proposed registry/ledger pair with `scripts/validate_orchestration.py`; validation failure blocks mutation and dispatch. Never infer capacity from source files or a stale registry.

## Budget and allocation truth

Budget units remain distinct; never convert credits, tokens, time, calls, or currency without a verified mapping. Measurement is `observed`, `estimated`, or `unavailable`. Enforcement is `advisory` unless the trusted context above authorizes local or provider enforcement. Without it, call the limit an advisory ceiling and never promise automatic prevention or exact remaining spend.

When mandatory local or provider enforcement is unsupported, mismatched, stale, or unverifiable, the route is `Blocked` or asks one route/limit decision before any spend. Downgrade to advisory only after explicit user acceptance, and report the accepted limitation as `Degraded`; configuration alone never implies acceptance.

The coordinator reserves coordinator work, integration reserve, mandatory-review reserve, worker, tool, retry, and review capacity before dispatch. Workers cannot transfer, expand, or borrow allocations. Unused capacity returns only through a recorded coordinator transaction. Unknown usage conservatively retains its reservation; timeouts and missing terminal results stay unfinished. Unfunded consumption is visible `Degraded` or `Blocked`, not hidden by reconciliation.

The ledger's `reserves` fields are planning obligations; they do not themselves debit capacity. Use `prepare_dispatch(registry, ledger, worker_event)` before worker starts/retries. It validates both snapshots, creates coordinator-owned `coordinator`, `integration`, and `review` reservation events for unmet obligations, then dispatches atomically. Existing active holds and funded obligation consumption count once. Mandatory review capacity is specified by `reserves.mandatory_review`; retain that requirement until authoritative review/plan evidence changes it. Raw `apply_ledger_event` is a legacy mutation primitive and does not protect planning reserves.

For a ceiling of 100 with three reserves of 10 and a worker of 40, protected dispatch leaves 30 available. A further worker request for 60 fails before input mutation. Timeout/unknown usage retains the worker's hold; only authoritative terminal reconciliation releases its confirmed remainder. Coordinator-owned holds stay independent through release/retry. Invalid or unknown balances block dispatch with a visible reason.

At a soft threshold, remove optional parallelism or review and replan without dropping mandatory verification. At an enforced cap, start no new spend and use only a verified safe stop primitive. At an advisory ceiling, stop before the next discretionary operation. Record running assignments, measurement source, observed/estimated/unknown usage, and the exact resume or expansion decision through failure visibility.
