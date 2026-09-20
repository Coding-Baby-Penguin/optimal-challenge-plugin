# Simplification

Run after correctness is established when a created/changed artifact could materially benefit.

## Code
Prefer minimum complexity necessary to satisfy requirements. Look for unnecessary abstractions, duplicated logic, excessive indirection/configurability, dead code/imports, needless dependencies, overcomplicated branching, trivial wrappers, cleverness, or scope creep.

Optimize the requested diff, not the entire repository. Unrelated cleanup becomes a recommendation unless it directly reduces risk or complexity of the requested change.

After simplification, re-run the relevant verification contract.

## Output
Complex internal work may produce a short external answer. Lead with result, then material evidence/assumptions/action. Omit agent choreography, search narration, redundant summaries, and intermediate dead ends unless they affect the user's decision.
