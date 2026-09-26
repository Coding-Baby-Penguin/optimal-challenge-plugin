# Claude Code and Anthropic Capability Adapter

Use this module only after the router needs a host capability. Repository state remains authoritative; a documented capability is not proof that the active host exposes it.

## Resolution contract

Resolve one capability with `scripts/capability_matrix.py`. Matching live detection for the exact surface and version outranks an unexpired acceptance run, which outranks this static policy declaration. Missing provenance, wrong surface, wrong version, expired evidence, conflicting observations, or detector failure resolves to `unknown`. A present but invalid higher-priority record cannot be hidden by lower-priority evidence.

`unknown` uses the listed Required fallback, the same safe route used when a capability is unsupported. Report the mismatch and resulting route; do not rewrite this matrix silently. Product subscription credits and API billing are separate measurement surfaces and must never be combined or treated as interchangeable.

Support level values are `policy-only`, `observed`, and `unsupported`. These rows are policy-only until an executable adapter and matching acceptance run establish otherwise.

## Capability matrix

| Surface ID | Capability | Support level | Detector | Evidence ref | Verified version | Verified at | Expires at | Required fallback |
|---|---|---|---|---|---|---|---|---|
| claude-code-local | Native resume | policy-only | Host resume-handle probe | policy:claude-code-local/native-resume | active Claude Code host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Rehydrate from durable capsule |
| claude-code-local | Pause/cancel | policy-only | Host stop-primitive probe | policy:claude-code-local/pause-cancel | active Claude Code host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Block new work; record running work unfinished |
| claude-code-local | Usage measurement | policy-only | Host usage-counter probe | policy:claude-code-local/usage | active Claude Code host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Advisory accounting |
| claude-code-local | Local enforcement | policy-only | Local stop-and-counter probe | policy:claude-code-local/local-enforcement | active Claude Code host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Advisory ceiling before next discretionary operation |
| claude-code-local | Provider enforcement | policy-only | Provider stop-and-counter probe | policy:claude-code-local/provider-enforcement | active Claude Code host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Advisory ceiling before next discretionary operation |
| claude-code-local | Persistence/privacy | policy-only | Workspace persistence probe | policy:claude-code-local/persistence-privacy | active Claude Code host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Persist only approved durable state or block |
| claude-code-local | Parallel execution | policy-only | Specialist-slot probe | policy:claude-code-local/parallel | active Claude Code host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Inline execution |
| claude-code-local | Tracing | policy-only | Trace-export probe | policy:claude-code-local/tracing | active Claude Code host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Local evidence references only |
| anthropic-api-agent-sdk | Native resume | policy-only | Executable adapter probe | policy:anthropic-api-agent-sdk/native-resume | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Rehydrate from durable capsule |
| anthropic-api-agent-sdk | Pause/cancel | policy-only | Executable adapter probe | policy:anthropic-api-agent-sdk/pause-cancel | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Block new work; record running work unfinished |
| anthropic-api-agent-sdk | Usage measurement | policy-only | Executable usage-response probe | policy:anthropic-api-agent-sdk/usage | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Advisory accounting |
| anthropic-api-agent-sdk | Local enforcement | policy-only | Executable local-controller probe | policy:anthropic-api-agent-sdk/local-enforcement | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Advisory ceiling before next discretionary operation |
| anthropic-api-agent-sdk | Provider enforcement | policy-only | Executable provider-limit probe | policy:anthropic-api-agent-sdk/provider-enforcement | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Advisory ceiling before next discretionary operation |
| anthropic-api-agent-sdk | Persistence/privacy | policy-only | Executable storage-policy probe | policy:anthropic-api-agent-sdk/persistence-privacy | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Persist only approved durable state or block |
| anthropic-api-agent-sdk | Parallel execution | policy-only | Executable concurrency probe | policy:anthropic-api-agent-sdk/parallel | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Inline execution |
| anthropic-api-agent-sdk | Tracing | policy-only | Executable trace probe | policy:anthropic-api-agent-sdk/tracing | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Local evidence references only |

## Local operating guidance

- Prefer local filesystem, source, tests, and git for durable truth.
- Keep simple, sequential, single-file, or shared-context work in the coordinator unless delegation clears the economic gate.
- Fresh contexts can be preferable to compaction when state is checkpointed to authoritative files.
- Add deterministic hooks only when earned and check for overlapping triggers across sources.
- Never infer Anthropic API or Agent SDK executable support from Claude Code plugin documentation.
