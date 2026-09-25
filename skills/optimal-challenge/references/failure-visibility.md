# Failure Visibility

Use this contract when a command, tool, test, build, deployment, background task, retry, or fallback returns a nonzero exit code, warning, timeout, incomplete result, skipped check, or contradictory evidence.

## Completion rule

Report success only after every required operation reaches an observed successful terminal state and its output is verified at the appropriate boundary. A started process is not a completed process. Exit code `0` is not sufficient when output reports skipped, failed, or partial work. Required checks fail closed; an unavailable required check makes the result blocked, partial, or degraded rather than successful.

Optional checks may warn without failing the whole task, but the warning and its impact remain visible.

## Outcome states

| State | Meaning |
|---|---|
| Succeeded | Required operations and verification completed with positive evidence. |
| Failed | A required operation reached an unsuccessful terminal state. |
| Partial | Some requested outputs succeeded and others did not. |
| Blocked | A required operation could not run or reach a terminal state. |
| Degraded | A fallback, skipped check, or reduced-capability path produced a usable but limited result. |

## Required failure report

Every failed, partial, blocked, or degraded result contains:

- **Status:** one outcome state; never `Succeeded` with an unresolved required failure.
- **Failed operation:** the exact command, phase, artifact, or check that did not complete.
- **Evidence:** exit code, error summary, failed count, timeout, or missing completion signal. Redact secrets.
- **Impact:** what is unavailable, unverified, stale, or unsafe to rely on.
- **Retry or fallback:** attempts made, their result, and whether a fallback changed fidelity or coverage.
- **Next action:** one concrete recovery or verification step and the resume point.

## Execution safeguards

- Inspect exit code, standard output, and standard error; do not infer success from optimistic text alone.
- Preserve the primary error when cleanup also fails, and report both.
- Bound retries. Record final exhaustion instead of hiding earlier attempts behind the last response.
- Label fallbacks as degraded until they receive the original required verification.
- Track asynchronous and delegated work until a terminal state, explicit cancellation, or a recorded blocker.
- Validate artifact contents and remote state when existence alone is a weak oracle.
- Put unresolved failures, evidence, and the recovery action in `PROJECT-STATE.md` before quota or session boundaries.

## Red flags

- “Most checks passed” while one required check failed.
- “Probably environmental” without a successful controlled rerun.
- “Warning only” when the warning says verification was skipped.
- “Uploaded,” “started,” or “queued” presented as completed.
- A fallback reported as equivalent without comparing fidelity and coverage.

## Example

```text
Status: Partial
Failed operation: Remote release verification
Evidence: Upload transferred 43 files; verifier timed out and exited 1
Impact: Remote contents are not confirmed, so release completion is unverified
Retry or fallback: One retry timed out; no fallback used
Next action: Query the remote revision, compare it with the local commit, then resume publication
```
