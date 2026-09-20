# Codebase Reality Model

Load only for non-trivial existing-codebase work.

## Do not assume
- Available context will be used reliably.
- Retrieved code includes every relevant dependency.
- A structural graph captures runtime behavior.
- Repository guidance is current.
- Passing tests prove the requested behavior.
- Local correctness implies system correctness.
- More agents, retrieval, or verification monotonically improves quality.

## Cheap preflight
Start with the task target, repo instructions, tree, dependency manifests, nearby tests, and direct definitions/references. Expand only when material uncertainty remains.

## Dependency envelope
For the intended change, consider only relevant:
- definitions consumed;
- callers/consumers;
- shared state;
- configuration/DI/routing;
- persistence/schema/cache;
- tests and invariants;
- runtime/external boundaries.

## Hybrid discovery
Use the least expensive combination required:
- lexical: exact names, grep/regex;
- semantic: concept similarity;
- structural: symbols, imports, calls, ownership;
- configuration: manifests, routes, DI, schemas;
- dynamic: tests, traces, logs, runtime behavior.

## Countermeasure check
Every mitigation has a blind spot. State only the material pair:
`strategy -> expected benefit -> known blind spot -> compensating check`.

## Stop condition
Stop exploration when goal-relevant files and impact boundaries are sufficiently known and remaining uncertainty cannot materially alter the implementation or verification plan.
