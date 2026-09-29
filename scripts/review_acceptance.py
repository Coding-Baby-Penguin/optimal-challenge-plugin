#!/usr/bin/env python3
"""Explicit local review and comparison in one trusted Python process.

The operator must inspect native event bytes, grader independence and the audit
before typing the displayed digest. JSON status alone never approves a run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluation_evidence import (
    _strict_json, combine_verified_contexts, register_recorder_review,
    verify_run_evidence,
)
from scripts.evaluate_behavior import compare_arms


def _load(path: Path) -> Mapping[str, Any]:
    return _strict_json(path.read_bytes())


def _approval_digest(manifest, baseline, candidate, receipts, audit) -> str:
    payload = {"manifest": manifest, "baseline": baseline, "candidate": candidate,
               "receipts": receipts, "audit": audit}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def run_reviewed_comparison(
    manifest: Mapping[str, Any], baseline: Mapping[str, Any], candidate: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any]], audit: Mapping[str, Any], evidence_root: Path,
    *, reviewer_id: str, approval_digest: str,
) -> dict[str, Any]:
    """Issue both contexts only after an explicit review of this exact payload."""
    expected = _approval_digest(manifest, baseline, candidate, receipts, audit)
    if approval_digest != expected:
        return {"status": "blocked", "reasons": ["Exact reviewed input digest was not confirmed"]}
    contexts = []
    reasons = []
    for scored in (baseline, candidate):
        arm_id = scored.get("arm_id")
        receipt = receipts.get(arm_id)
        review = audit.get(arm_id)
        if not isinstance(receipt, Mapping) or not isinstance(review, Mapping):
            reasons.append(f"{arm_id}: receipt or native audit is missing")
            continue
        try:
            register_recorder_review(
                receipt, reviewer_id=reviewer_id,
                independent_graders=review["independent_graders"],
                native_audit=review["native_audit"],
            )
            context, errors = verify_run_evidence(scored, manifest, evidence_root, receipt)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            reasons.append(f"{arm_id}: review or verification failed: {type(exc).__name__}: {exc}")
            continue
        if errors:
            reasons.extend(f"{arm_id}: {error}" for error in errors)
        elif context is not None:
            contexts.append(context)
    if reasons or len(contexts) != 2:
        return {"status": "blocked", "reasons": reasons or ["two verified arm contexts are required"]}
    try:
        combined = combine_verified_contexts(*contexts)
    except ValueError as exc:
        return {"status": "blocked", "reasons": [str(exc)]}
    return compare_arms(baseline, candidate, manifest, evidence_context=combined)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "baseline", "candidate", "baseline-receipt", "candidate-receipt", "audit", "evidence-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    args = parser.parse_args(argv)
    try:
        manifest, baseline, candidate = _load(args.manifest), _load(args.baseline), _load(args.candidate)
        receipts = {
            baseline.get("arm_id"): _load(args.baseline_receipt),
            candidate.get("arm_id"): _load(args.candidate_receipt),
        }
        audit = _load(args.audit)
        if len(receipts) != 2:
            raise ValueError("distinct baseline and candidate arms are required")
        digest = _approval_digest(manifest, baseline, candidate, receipts, audit)
        print(f"Review the retained native bytes, extracted counters, grader roster and scored output before approval. Input digest: {digest}")
        approval = input("Type the complete input digest after independent review: ").strip()
        result = run_reviewed_comparison(manifest, baseline, candidate, receipts, audit, args.evidence_root,
                                         reviewer_id=args.reviewer_id, approval_digest=approval)
    except (OSError, ValueError, TypeError, EOFError, KeyboardInterrupt, json.JSONDecodeError) as exc:
        result = {"status": "blocked", "reasons": [f"Review could not complete: {type(exc).__name__}: {exc}"]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "pass" else 2 if result.get("status") in {"blocked", "unverified", "inconclusive"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
