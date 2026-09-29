# Cost-quality routing

Choose the least expensive route expected to finish efficiently. Availability alone is not value.

## Delegation value

```text
D(t) = B_parallel + B_independence + B_context + B_quality
       - (C_setup + C_transfer + C_merge + C_review_rework)
```

Score each factor 0-3 with cited `observed`, `estimated`, or `unknown` provenance: 0 absent/negligible; 1 minor; 2 material; 3 decisive benefit or dominant cost. A strong benefit is any benefit scored 2 or 3.

Delegate only when economics are known, value is positive and meets the margin, a strong benefit exists, the done condition is observable, authority and platform permit it, and the reservation fits. Economy requires `D(t) >= 3`; Balanced and Quality require `D(t) >= 1`; Custom uses its validated 1-12 margin. `team-requested` reduces Economy to 1 but never permits zero-value spawning; it changes Custom only when its explicit override is enabled. Never delegate merely because a slot is available. Keep tightly coupled, overlapping-edit, and same-context work inline.

An explicit exact count follows the authority rules in team orchestration and records the calculation even when it overrides the margin. Insufficient evidence stays inline. Ties stay inline unless independence is mandatory.

## Profiles and capability

- **Economy:** stronger inline bias, smaller teams, lower capability, deterministic checks, minimal optional review.
- **Balanced:** default; positive-value delegation and targeted review.
- **Quality:** stronger capability and broader review for consequential or weak-oracle work, with the same gates and stop-loss.
- **Custom:** validated weights, margin, concurrency, capability, review, privacy, and budget semantics; never weakens authority or truthfulness.

Use provider-neutral capability classes `economy`, `standard`, `reasoning`, and `frontier`. A retry must add information, context, capability, or strength; never repeat an unchanged hypothesis.

## Whole-job utility

```text
Utility = lambda_quality(ExpectedQuality)
          - lambda_cost(TotalJobCost)
          - lambda_latency(CriticalPathLatency)
          - lambda_attention(UserInterruptionCost)
          - lambda_rework(ExpectedReworkRisk)

TotalJobCost = input + cache_write + cache_read + output + tools
               + coordination + verification + retry
```

Normalize every factor to 0-3. Named `(quality, cost, latency, attention, rework)` weights are Economy `(0.35, 0.35, 0.10, 0.10, 0.10)`, Balanced `(0.45, 0.20, 0.10, 0.10, 0.15)`, and Quality `(0.50, 0.10, 0.05, 0.10, 0.25)`; Custom weights sum to 1. In this evaluation-only C arm, the candidate premise/research gate is omitted; utility selects among routes only after authority, safety, economic delegation, allocation, and review gates pass. Unknown inputs make utility explanatory only. Record factors, evidence, provenance, threshold, margin, chosen route, and reason; use `scripts/evaluate_routing.py` to check the arithmetic.
