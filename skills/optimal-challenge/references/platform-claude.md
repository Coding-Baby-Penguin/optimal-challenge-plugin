# Claude Code and Anthropic Capability Adapter

Use this module only after the router needs a host capability. Repository state remains authoritative; a documented capability is not proof that the active host exposes it.

## Resolution contract

Resolve one capability with `scripts/capability_matrix.py`. Runtime claims must arrive as the closed `TrustedCapabilityEvidence` adapter type with the capability-specific proof type. Generic mappings, user-authored claims, and arbitrary detector or evidence namespaces resolve to `unknown`.

The adapter factory adds a process-local attestation that ordinary construction and serialization cannot recreate. It is an in-process capability boundary, not a cryptographic signature and not protection against hostile code already executing inside the resolver module. Prefixes such as `adapter:` or `live:` are metadata only; they never establish trust by themselves.

For local surfaces, matching live detection for the exact surface and version outranks an unexpired acceptance run, which outranks this static policy declaration. Anthropic API/Agent SDK support becomes `observed` only with both executable live adapter evidence and a current matching acceptance run. Either item alone, or disagreement between them, fails closed.

Missing provenance, wrong surface, wrong version, expired evidence, conflicting observations, or detector failure resolves to `unknown`. A present but invalid higher-priority record cannot be hidden by lower-priority evidence. `unknown` uses the canonical Fallback token, the same safe route used for unsupported behavior. Report the reason and route; do not rewrite this matrix silently.

Product subscription credits and API billing are separate measurement surfaces and must never be combined. Usage measurement requires an observed counter proof. Local or provider enforcement additionally requires a linked matching stop primitive for the same exact surface and version. `unavailable` is an explicit non-matchable version classification, not a wildcard.

## Capability matrix

| Surface ID | Capability | Support level | Detector | Evidence ref | Verified version | Verified at | Expires at | Measurement surface | Fallback | Fallback explanation |
|---|---|---|---|---|---|---|---|---|---|---|
| claude-code-local | Native resume | policy-only | policy:host-resume-probe | policy:claude-code-local/native-resume | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | rehydrate | Rebuild from the durable teammate capsule. |
| claude-code-local | Pause/cancel | policy-only | policy:host-stop-probe | policy:claude-code-local/pause-cancel | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | blocked | Start no new work and record running work unfinished. |
| claude-code-local | Usage measurement | policy-only | policy:host-usage-probe | policy:claude-code-local/usage-measurement | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | claude-product-usage | advisory | Label usage unavailable or estimated; do not claim enforcement. |
| claude-code-local | Local enforcement | policy-only | policy:local-stop-counter-probe | policy:claude-code-local/local-enforcement | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | claude-product-usage | advisory | Stop before the next discretionary operation. |
| claude-code-local | Provider enforcement | policy-only | policy:provider-stop-counter-probe | policy:claude-code-local/provider-enforcement | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | claude-product-usage | advisory | Stop before the next discretionary operation. |
| claude-code-local | Persistence/privacy | policy-only | policy:workspace-boundary-probe | policy:claude-code-local/persistence-privacy | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | blocked | Persist only approved durable state or request a safe route. |
| claude-code-local | Parallel execution | policy-only | policy:specialist-slot-probe | policy:claude-code-local/parallel-execution | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | inline | Continue without specialists. |
| claude-code-local | Tracing | policy-only | policy:trace-export-probe | policy:claude-code-local/tracing | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | advisory | Retain only local evidence references and disclose the limitation. |
| anthropic-api-agent-sdk | Native resume | policy-only | policy:executable-adapter-probe | policy:anthropic-api-agent-sdk/native-resume | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | rehydrate | Rebuild from the durable teammate capsule. |
| anthropic-api-agent-sdk | Pause/cancel | policy-only | policy:executable-stop-probe | policy:anthropic-api-agent-sdk/pause-cancel | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | blocked | Start no new work and record running work unfinished. |
| anthropic-api-agent-sdk | Usage measurement | policy-only | policy:executable-usage-probe | policy:anthropic-api-agent-sdk/usage-measurement | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | anthropic-api-billing | advisory | Label usage unavailable or estimated; do not claim enforcement. |
| anthropic-api-agent-sdk | Local enforcement | policy-only | policy:executable-local-controller-probe | policy:anthropic-api-agent-sdk/local-enforcement | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | anthropic-api-billing | advisory | Stop before the next discretionary operation. |
| anthropic-api-agent-sdk | Provider enforcement | policy-only | policy:executable-provider-limit-probe | policy:anthropic-api-agent-sdk/provider-enforcement | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | anthropic-api-billing | advisory | Stop before the next discretionary operation. |
| anthropic-api-agent-sdk | Persistence/privacy | policy-only | policy:executable-storage-probe | policy:anthropic-api-agent-sdk/persistence-privacy | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | blocked | Persist only approved durable state or request a safe route. |
| anthropic-api-agent-sdk | Parallel execution | policy-only | policy:executable-concurrency-probe | policy:anthropic-api-agent-sdk/parallel-execution | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | inline | Continue without specialists. |
| anthropic-api-agent-sdk | Tracing | policy-only | policy:executable-trace-probe | policy:anthropic-api-agent-sdk/tracing | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | advisory | Retain only local evidence references and disclose the limitation. |

## Local operating guidance

- Prefer local filesystem, source, tests, and git for durable truth.
- Keep simple, sequential, single-file, or shared-context work in the coordinator unless delegation clears the economic gate.
- Fresh contexts can be preferable to compaction when state is checkpointed to authoritative files.
- Add deterministic hooks only when earned and check for overlapping triggers across sources.
- Never infer Anthropic API or Agent SDK executable support from Claude Code plugin documentation.
