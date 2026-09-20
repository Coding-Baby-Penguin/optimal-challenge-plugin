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

## Completion
Do not claim completion until fresh evidence supports the claim. Report weak or partial oracles explicitly instead of converting them into confidence.
