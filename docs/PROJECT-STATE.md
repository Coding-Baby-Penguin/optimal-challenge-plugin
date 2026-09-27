# Project state

- **Goal:** Release Optimal Challenge 1.2.0 as a lightweight, testable policy plugin that chooses direct work or agent teams, improves material questions, accounts for allocations honestly, preserves logical continuity, and makes required failures visible.
- **Success criteria:** Invocation controls and four profiles are explicit; research calculations are executable; configuration, state, capability, and evaluation contracts fail closed; manifests and documentation agree; fresh-host claims are made only from isolated acceptance evidence.
- **Last updated:** 2026-09-27
- **Current verified state:** Tasks 1–8 of the approved agent-team optimisation plan are implemented in the working branch. The 1.2.0 manifests and integrated validation entry point are present; repository-level tests and validators pass. This does not establish fresh-host behavioral support.
- **Completed:** Orchestration configuration; premise/delegation/review/utility calculations; registry and allocation ledger; capsule templates; routing and continuity policy; fail-closed capability evidence; pinned behavioral evaluation; 1.2.0 metadata, user documentation, submission copy, integrated validation, and adversarial checks.
- **Changed artifacts:** `config/project.json`, portable/Codex/Claude manifests, `skills/optimal-challenge/agents/openai.yaml`, `scripts/validate.py`, `scripts/adversarial_review.py`, `tests/validation/test_package.py`, `README.md`, `submission/plugin-submission.md`, and this state file.

## Development path

- **Now:** Task 8 passes its local structural gate and awaits the required independent review.
- **Next:** Address any Task 8 review findings, then execute Task 9 packaging and source/archive comparison without pushing early.
- **Later:** Task 10 performs fresh isolated host acceptance, final independent scoring, local plugin refresh, release verification, commit/push verification, and support-claim narrowing for unavailable surfaces.

## Continuity

- **Workflow convention:** After every required Task 10 gate passes, commit and push completed repository changes unless the user explicitly says not to.
- **Blockers:** No repository-structural blocker is currently known.
- **Unresolved failures:** Fresh-host behavioral acceptance is `UNVERIFIED`. The v1.1 baseline and 1.2 candidate still require isolated recorded runs; API/SDK and local-host capability rows remain policy-only or unsupported unless exact surface/version evidence is supplied. No cost, latency, provider-enforcement, or behavior-improvement claim is currently authorized.
- **Pending decisions:** Independent Task 8 review may require corrections. Task 9 must refresh the candidate archive identity; Task 10 must determine which host surfaces can actually be exercised and therefore claimed.
- **Verification evidence:** Bundled Python 3.12 with disposable `jsonschema==4.25.1` and `PyYAML==6.0.2` passed 36 focused package tests and 216 full tests. `scripts/validate.py` passed configuration, 14 routing cases, orchestration state, capability contracts, and behavioral structure while explicitly reporting fresh-host acceptance unverified. `scripts/adversarial_review.py` passed conditional team/review, budget-truth, route-agreement, and schema/template ownership checks.
- **Next concrete action:** Run an independent Task 8 review against the approved design and plan; if approved, begin Task 9 archive/package validation.
- **Resume command or entry point:** `git status --short` followed by `python scripts/validate.py`, `python -m unittest discover -v`, and `python scripts/adversarial_review.py` with the pinned disposable development dependencies available on `PYTHONPATH`.
