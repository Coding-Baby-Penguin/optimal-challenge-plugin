# Project state

- **Goal:** Release Optimal Challenge 1.2.0 as a lightweight, testable policy plugin that chooses direct work or agent teams, improves material questions, accounts for allocations honestly, preserves logical continuity, and makes required failures visible.
- **Success criteria:** Invocation controls and four profiles are explicit; research calculations are executable; configuration, state, capability, and evaluation contracts fail closed; manifests and documentation agree; fresh-host claims are made only from isolated acceptance evidence.
- **Last updated:** 2026-09-27
- **Current verified state:** Tasks 1–9 and the Task 10 source corrections are implemented. Exact commit `ddb011c0915444d32670d5597db9e3bf3a0a6bfd` received a fresh independent 10.0/10 source review with no unresolved High finding. The complete local gate passes 237 tests without skips, but fresh-host behavioral acceptance remains `UNVERIFIED` and release completion is blocked.
- **Completed:** Orchestration configuration; premise/delegation/review/utility calculations; registry and allocation ledger; capsule templates; routing and continuity policy; fail-closed capability evidence; behavioral-evaluation contracts; 1.2.0 metadata and documentation; deterministic packaging; local/official/adversarial/security validation; source review corrections for invocation authority, zero-capacity review, and confidence-qualified acceptance.
- **Changed artifacts:** All approved Tasks 1–9 artifacts plus Task 10 corrections in `scripts/evaluate_routing.py`, `scripts/evaluate_behavior.py`, their regression tests, `tests/baselines/v1.1.json`, and this state file.

## Development path

- **Now:** Task 10 local, package, official-validator, security, and independent source-review gates pass; A/B/C/D fresh-arm preflights are recorded as `UNVERIFIED` without behavioral scores.
- **Next:** Reconcile the immutable v1.1 baseline identity, refresh B/C/D to the reviewed candidate identity, install each exact arm/cachebuster in genuinely fresh tasks, and record model/reasoning plus disposable registry/ledger fingerprints.
- **Later:** Run five stochastic repetitions per required case and deterministic cases once, evaluate non-inferiority/benefit confidence, then commit/push only if every required acceptance gate passes.

## Continuity

- **Workflow convention:** Commit and push only after every required Task 10 gate passes; an unverified or inconclusive host gate blocks release push.
- **Blockers:** Arm A archive SHA `51bab08ea52ead000c7b450b1040d4da87470bfafa210e6c46c9285b57bef7e1` exists, but four members differ from pinned commit `c3c379ab` and remote tag `v1.1.0` targets `b4510c8`. Arms B/C/D still pin provisional `93ff8725` / `3a54f2e4...` identities. During the invalid A/B/C/D preflights the installed cache was pre-fix commit `3dcf78c`; it was later refreshed to reviewed files with manifest `1.2.0+codex.20260927031000`, but that cannot retroactively validate those runs. Arm-specific cachebusters, exact fresh-task model/reasoning read-back, and disposable-state fingerprints remain absent.
- **Unresolved failures:** Fresh-host A/B/C/D behavioral acceptance is `UNVERIFIED`; no run bundle, aggregate, cost/latency claim, quality comparison, platform-support claim, or provider-enforcement claim is authorized. API/SDK rows remain policy-only or unsupported without exact dual evidence.
- **Pending decisions:** Choose or rebuild one immutable v1.1 baseline subject, then create/install verifiable B/C/D arm subjects. Until that evidence exists, Task 10 cannot complete and `git push origin main` must not run.
- **Verification evidence:** Python 3.12.14 with disposable `jsonschema==4.25.1` and `PyYAML==6.0.2` passed 237 tests without skips, integrated validation, adversarial review, 14 routing cases, orchestration validation, official plugin/skill validators, boundary-aware secret scanning, silent-failure scanning, and deterministic Python 3.12/3.14 packaging. The pre-evidence reviewed archive contained 88 files at SHA-256 `f4fe8cc3c1218609355a4509c9146479daa759de12ec05c877f4b4ae622b66e5`. Independent source review scored 10.0/10.
- **Next concrete action:** Reconcile arm A identity and install exact isolated A/B/C/D subjects before any behavioral score is recorded.
- **Resume command or entry point:** `git status --short` followed by `python scripts/validate.py`, `python -m unittest discover -q`, `python scripts/adversarial_review.py`, and `python scripts/package_release.py` with the pinned disposable development dependencies on `PYTHONPATH`.
