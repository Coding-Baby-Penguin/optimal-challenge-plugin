# Codex and OpenAI Capability Adapter

Use this module only after the router needs a host capability. Repository state remains authoritative; a documented capability is not proof that the active host exposes it.

## Resolution contract

Resolve one capability with `scripts/capability_matrix.py`. Matching live detection for the exact surface and version outranks an unexpired acceptance run, which outranks this static policy declaration. Missing provenance, wrong surface, wrong version, expired evidence, conflicting observations, or detector failure resolves to `unknown`. A present but invalid higher-priority record cannot be hidden by lower-priority evidence.

`unknown` uses the listed Required fallback, the same safe route used when a capability is unsupported. Report the mismatch and resulting route; do not rewrite this matrix silently. Product subscription credits and API billing are separate measurement surfaces and must never be combined or treated as interchangeable.

Support level values are `policy-only`, `observed`, and `unsupported`. These rows are policy-only until an executable adapter and matching acceptance run establish otherwise.

## Capability matrix

| Surface ID | Capability | Support level | Detector | Evidence ref | Verified version | Verified at | Expires at | Required fallback |
|---|---|---|---|---|---|---|---|---|
| codex-local | Native resume | policy-only | Host resume-handle probe | policy:codex-local/native-resume | active Codex host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Rehydrate from durable capsule |
| codex-local | Pause/cancel | policy-only | Host stop-primitive probe | policy:codex-local/pause-cancel | active Codex host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Block new work; record running work unfinished |
| codex-local | Usage measurement | policy-only | Host usage-counter probe | policy:codex-local/usage | active Codex host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Advisory accounting |
| codex-local | Local enforcement | policy-only | Local stop-and-counter probe | policy:codex-local/local-enforcement | active Codex host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Advisory ceiling before next discretionary operation |
| codex-local | Provider enforcement | policy-only | Provider stop-and-counter probe | policy:codex-local/provider-enforcement | active Codex host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Advisory ceiling before next discretionary operation |
| codex-local | Persistence/privacy | policy-only | Workspace persistence probe | policy:codex-local/persistence-privacy | active Codex host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Persist only approved durable state or block |
| codex-local | Parallel execution | policy-only | Specialist-slot probe | policy:codex-local/parallel | active Codex host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Inline execution |
| codex-local | Tracing | policy-only | Trace-export probe | policy:codex-local/tracing | active Codex host version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Local evidence references only |
| openai-api-agents | Native resume | policy-only | Executable adapter probe | policy:openai-api-agents/native-resume | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Rehydrate from durable capsule |
| openai-api-agents | Pause/cancel | policy-only | Executable adapter probe | policy:openai-api-agents/pause-cancel | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Block new work; record running work unfinished |
| openai-api-agents | Usage measurement | policy-only | Executable usage-response probe | policy:openai-api-agents/usage | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Advisory accounting |
| openai-api-agents | Local enforcement | policy-only | Executable local-controller probe | policy:openai-api-agents/local-enforcement | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Advisory ceiling before next discretionary operation |
| openai-api-agents | Provider enforcement | policy-only | Executable provider-limit probe | policy:openai-api-agents/provider-enforcement | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Advisory ceiling before next discretionary operation |
| openai-api-agents | Persistence/privacy | policy-only | Executable storage-policy probe | policy:openai-api-agents/persistence-privacy | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Persist only approved durable state or block |
| openai-api-agents | Parallel execution | policy-only | Executable concurrency probe | policy:openai-api-agents/parallel | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Inline execution |
| openai-api-agents | Tracing | policy-only | Executable trace probe | policy:openai-api-agents/tracing | configured SDK and API version | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | Local evidence references only |

## Local operating guidance

- Prefer filesystem, repository instructions, tests, and git history over conversational reconstruction.
- Use fresh contexts after durable checkpoints; reconstruct from authoritative state and capsules.
- Keep caches and temporary agent state gitignored unless humans benefit from them.
- Use specialists only past the delegation gate and give each an explicit scope and resource allocation.
- Never infer OpenAI API or Agents SDK executable support from Codex plugin documentation.
