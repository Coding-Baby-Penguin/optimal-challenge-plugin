# Codex and OpenAI Capability Adapter

Use this module only after the router needs a host capability. Repository state remains authoritative; a documented capability is not proof that the active host exposes it.

## Resolution contract

Resolve one capability with `scripts/capability_matrix.py`. Runtime claims must arrive as the closed `TrustedCapabilityEvidence` adapter type with the capability-specific proof type. Generic mappings, user-authored claims, and arbitrary detector or evidence namespaces resolve to `unknown`.

The adapter factory adds a process-local attestation that ordinary construction and serialization cannot recreate. Issuance binds the exact issued object identity and its payload digest in a weak-reference registry; copies or replacements are new objects and resolve to `unknown`, even when their fields are unchanged. Weak references remove expired entries and the identity check prevents stale object-ID reuse. This is an in-process capability boundary, not a cryptographic signature and not protection against hostile code already executing inside the resolver module. Prefixes such as `adapter:` or `live:` are metadata only; they never establish trust by themselves.

For local surfaces, matching live detection for the exact surface and version outranks an unexpired acceptance run, which outranks this static policy declaration. OpenAI API/Agents SDK support becomes `observed` only with both executable live adapter evidence and a current matching acceptance run. Either item alone, or disagreement between them, fails closed.

Missing provenance, wrong surface, wrong version, expired evidence, conflicting observations, or detector failure resolves to `unknown`. A present but invalid higher-priority record cannot be hidden by lower-priority evidence. `unknown` uses the canonical Fallback token, the same safe route used for unsupported behavior. Report the reason and route; do not rewrite this matrix silently.

Product subscription credits and API billing are separate measurement surfaces and must never be combined. Usage measurement requires an observed counter proof. Local or provider enforcement additionally requires a linked matching stop primitive for the same exact surface and version. `unavailable` is an explicit non-matchable version classification, not a wildcard.

## Capability matrix

| Surface ID | Capability | Support level | Detector | Evidence ref | Verified version | Verified at | Expires at | Measurement surface | Fallback | Fallback explanation |
|---|---|---|---|---|---|---|---|---|---|---|
| codex-local | Native resume | policy-only | policy:host-resume-probe | policy:codex-local/native-resume | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | rehydrate | Rebuild from the durable teammate capsule. |
| codex-local | Pause/cancel | policy-only | policy:host-stop-probe | policy:codex-local/pause-cancel | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | blocked | Start no new work and record running work unfinished. |
| codex-local | Usage measurement | policy-only | policy:host-usage-probe | policy:codex-local/usage-measurement | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | codex-product-usage | advisory | Label usage unavailable or estimated; do not claim enforcement. |
| codex-local | Local enforcement | policy-only | policy:local-stop-counter-probe | policy:codex-local/local-enforcement | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | codex-product-usage | advisory | Stop before the next discretionary operation. |
| codex-local | Provider enforcement | policy-only | policy:provider-stop-counter-probe | policy:codex-local/provider-enforcement | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | codex-product-usage | advisory | Stop before the next discretionary operation. |
| codex-local | Persistence/privacy | policy-only | policy:workspace-boundary-probe | policy:codex-local/persistence-privacy | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | blocked | Persist only approved durable state or request a safe route. |
| codex-local | Parallel execution | policy-only | policy:specialist-slot-probe | policy:codex-local/parallel-execution | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | inline | Continue without specialists. |
| codex-local | Tracing | policy-only | policy:trace-export-probe | policy:codex-local/tracing | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | advisory | Retain only local evidence references and disclose the limitation. |
| openai-api-agents | Native resume | policy-only | policy:executable-adapter-probe | policy:openai-api-agents/native-resume | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | rehydrate | Rebuild from the durable teammate capsule. |
| openai-api-agents | Pause/cancel | policy-only | policy:executable-stop-probe | policy:openai-api-agents/pause-cancel | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | blocked | Start no new work and record running work unfinished. |
| openai-api-agents | Usage measurement | policy-only | policy:executable-usage-probe | policy:openai-api-agents/usage-measurement | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | openai-api-billing | advisory | Label usage unavailable or estimated; do not claim enforcement. |
| openai-api-agents | Local enforcement | policy-only | policy:executable-local-controller-probe | policy:openai-api-agents/local-enforcement | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | openai-api-billing | advisory | Stop before the next discretionary operation. |
| openai-api-agents | Provider enforcement | policy-only | policy:executable-provider-limit-probe | policy:openai-api-agents/provider-enforcement | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | openai-api-billing | advisory | Stop before the next discretionary operation. |
| openai-api-agents | Persistence/privacy | policy-only | policy:executable-storage-probe | policy:openai-api-agents/persistence-privacy | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | blocked | Persist only approved durable state or request a safe route. |
| openai-api-agents | Parallel execution | policy-only | policy:executable-concurrency-probe | policy:openai-api-agents/parallel-execution | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | inline | Continue without specialists. |
| openai-api-agents | Tracing | policy-only | policy:executable-trace-probe | policy:openai-api-agents/tracing | unavailable | 2026-09-27T00:00:00Z | 2026-10-27T00:00:00Z | n/a | advisory | Retain only local evidence references and disclose the limitation. |

## Local operating guidance

- Prefer filesystem, repository instructions, tests, and git history over conversational reconstruction.
- Use fresh contexts after durable checkpoints; reconstruct from authoritative state and capsules.
- Keep caches and temporary agent state gitignored unless humans benefit from them.
- Use specialists only past the delegation gate and give each an explicit scope and resource allocation.
- Never infer OpenAI API or Agents SDK executable support from Codex plugin documentation.
