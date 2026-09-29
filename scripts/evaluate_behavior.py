"""Validate isolated behavioral runs and compare versioned evaluation arms.

This entry point evaluates recorded host runs. Static expected labels never prove
model behavior.
"""
from __future__ import annotations
import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.optimal_challenge.evaluation_contracts import (
    APPROVED_BEHAVIORAL_FIXTURE_VERSION, APPROVED_BEHAVIORAL_FIXTURE_SHA256,
    CANONICAL_FILES, PROFILE_MARGINS, validate_run_bundle,
)
from scripts.optimal_challenge.evaluation_semantics import PROFILE_WEIGHTS, REVIEW_MARGINS
from scripts.optimal_challenge.evaluation_statistics import summarize_arm
from scripts.optimal_challenge.evaluation_comparison import compare_arms

def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = _load_json(args.manifest)
        baseline = _load_json(args.baseline)
        candidate = _load_json(args.candidate)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"BEHAVIORAL EVALUATION FAILED: {exc}")
        return 1
    if baseline.get("status") == "unverified" or candidate.get("status") == "unverified":
        print("BEHAVIORAL EVALUATION UNVERIFIED: fresh isolated host runs are required; no comparative claim is allowed")
        return 2
    result = compare_arms(baseline, candidate, manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] == "pass":
        print("BEHAVIORAL EVALUATION PASSED")
        return 0
    if result["status"] in {"inconclusive", "unverified"}:
        label = result["status"].upper()
        print(f"BEHAVIORAL EVALUATION {label}: no comparative release claim is allowed")
        return 2
    print("BEHAVIORAL EVALUATION FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
