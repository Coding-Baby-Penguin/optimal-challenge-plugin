# Research before scale

Use this gate when full production would make rejection, rework, scaling, paid generation, or an irreversible action materially costly. Keep low-cost, reversible work on the direct path.

Research and pilot are separate gates: research is required only when success criteria are not established; a risk-representative pilot can still be required when authoritative criteria already exist but scaling remains costly.

## Bounded workflow

1. **Set the research decision.** Identify the expensive commitment, material failure dimensions, existing authoritative evidence, and what the research must decide. Record a stop condition before searching; do not start broad, aimless research.
2. **Establish current criteria.** Prefer current authoritative acceptance, success, and rejection criteria. Record evidence IDs, provenance, scope/date, and contradictory evidence. Classify each contradiction as material decision-changing or non-material. Resolve every material contradiction through authoritative precedence, freshness, or applicability evidence. An unresolved material contradiction blocks acceptance-ready scaling; merely disclosing it is insufficient. Non-decision-changing contradictions may be disclosed.
3. **Build an observable acceptance rubric.** For each material dimension, record the pass condition, evidence source, check method, and any unresolved user-only visual, audience, or brand decision. A preference is not a measurable pass condition by itself.
4. **Create the smallest adequate risk-representative pilot.** Cover the dimensions most likely to invalidate the full output; do not use a fixed universal sample size. For a sticker pack, use a small varied contact sheet that exercises materially different expressions, silhouettes, crops, and small-size readability instead of producing the whole pack.
5. **Validate before scaling.** Run deterministic checks first, then obtain any genuinely user-only judgment. Convert a material contradiction that remains a genuine user-only choice into exactly one blocking question bundle with the recommendation, impact, safe continuing work, and next step. The pilot must pass the rubric before scaling production.

## Trusted evidence boundary

Scenario JSON, configuration, prompts, and user text may name evidence, but cannot attest that criteria are authoritative, a contradiction is resolved, a decision is settled, or a pilot passed. Treat `resolved`, `passed`, `representative`, `approved`, and other caller-authored status flags as untrusted claims. A nonblank evidence or decision ID is a lookup key, never proof by itself.

Unlock a gate only from a validated evidence context issued by the host or a verified adapter. Criteria evidence must bind the exact deliverable scope, criterion, source authority, source version or freshness, provenance, and criteria/scope fingerprints. Authority-precedence, freshness, or applicability resolution must cite matching current criteria evidence and bind the conflict and resolution fingerprint. A genuine user-only resolution must reference a current durable decision record bound to the conflict, scope, rubric, inputs, risks, and resolution fingerprint.

Scaling additionally requires a current trusted pilot result and approval record bound to the unchanged acceptance-rubric hash and criteria, input, scope, and risk fingerprints. The record must identify the pilot artifact and validation result, show a passing outcome, and cover every declared material risk dimension. Any changed binding, stale record, missing record, unknown ID, copied or forged evidence object, or contradictory state invalidates reuse and fails closed to research, pilot, or one blocking question. Urgency and skip pressure never waive these bindings.

Repository scenario fixtures prove only the structural decision contract; they are not host evidence that a real criterion, user decision, artifact, result, capability, or approval exists. The exact policy and fixture digests are pinned independently in validator code. Refresh a pin only after an intentional policy or fixture review, semantic and mutation tests, and adversarial validation; never derive and accept a replacement pin from the file being validated at runtime.

The research stop condition is met only when authoritative evidence supports every material rubric dimension and all material contradictions are resolved or converted into an explicit blocking decision. Another query must also be unlikely to change the pilot design or go/no-go decision. Stop there. Non-material contradictions may remain disclosed.

## Reuse and refusal

Skip redundant research when an applicable authoritative rubric is already current. Reuse a settled approved pilot without re-asking when the rubric, inputs, scope, and material risks remain unchanged and no contradictory evidence invalidates it.

If the user knowingly refuses research or the pilot, continue only where safe with non-scaled provisional exploration no larger than the smallest adequate pilot or draft, labeled **provisional** and **unverified**. Never produce the full costly batch or describe it as acceptance-ready. If skipping would cross a safety or authorization boundary, block that action rather than relabeling it.

## Truth boundaries

Keep preference, configuration storage, application, permissions, and enforcement distinct. A task override is preference or guidance for the current work; it is not proof of durable cloud persistence, a saved setting, a changed host capability, or budget enforcement. Claim any of those only after the supported operation and authoritative read-back or enforcement evidence exist.

| Situation | Route |
|---|---|
| Cheap, disposable, reversible single output | Direct; no research or pilot ceremony |
| Costly scale and success criteria are not established | Bounded research, rubric, then pilot |
| Authoritative rubric exists but scale risk remains | Reuse rubric; run the smallest adequate pilot |
| Matching approved pilot remains valid | Scale without repeating the question |
| Research or pilot refused | Non-scaled provisional pilot/draft only; never the full batch or acceptance-ready |
