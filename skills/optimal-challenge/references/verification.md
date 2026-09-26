# Verification Contracts

Verification must prove the material claim, not merely consume effort.

| Work | Typical evidence |
|---|---|
| Current fact | Current authoritative source |
| Research | Independent source convergence + contradiction check |
| Calculation | Recalculation/invariant/sanity check |
| Code change | Targeted behavior + relevant suite/build/lint as warranted |
| Bug fix | Original symptom/repro + regression proof + relevant suite |
| Data/spreadsheet | Formula/schema/totals/outliers/sensitivity as warranted |
| File analysis | Exact source grounding |
| Strategy/recommendation | Constraints, assumptions, alternatives, uncertainty |
| External action | Read-back/confirmation from destination |

## Oracle quality
Passing tests are evidence only for what they cover. For meaningful changes, ask what the current tests fail to prove. Expand verification only across plausible impact boundaries.

## Risk adjustment
Increase verification for security/auth, payments, persistence/schema, public APIs, concurrency, destructive operations, and weak existing test oracles. Do not apply heavyweight verification to trivial prose/formatting changes.

## Selective independent review

Use direct deterministic verification for reversible mechanical work with a strong oracle. Use one targeted fresh review for material judgment or integration when its value clears the active margin. Security, financial, destructive, externally published, or materially consequential weak-oracle work requires mandatory independent review when available; contested research needs source verification rather than generic prose review.

```text
ReviewValue = P(defect) * Impact(defect) * P(review detects defect) - ReviewCost
```

Score each factor 0-3 with cited evidence: 0 absent, 1 unlikely/local/weak/small, 2 plausible/material/distinct, and 3 repeated-or-novel/severe/strong/dominant. Economy requires net value at least 6, Balanced 3, Quality 1, and Custom its validated 1-27 margin. Optional review requires known evidence and an available reviewer; mandatory review overrides the profile.

The independent reviewer receives authoritative inputs and success criteria without inheriting the implementer's conclusions as facts. When mandatory independent review is unavailable, mark the work `Blocked` before the consequential side effect. It may be `Degraded` only when a named compensating oracle provides meaningful coverage and the user explicitly accepts the limitation. Never silently waive or universally require review.

## Completion
Do not claim completion until fresh evidence supports the claim. Report weak or partial oracles explicitly instead of converting them into confidence.
