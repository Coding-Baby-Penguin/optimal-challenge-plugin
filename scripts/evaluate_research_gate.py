#!/usr/bin/env python3
"""Evaluate the bounded research-before-scale decision contract."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
import json
from pathlib import Path
import sys
from typing import Any


ROUTES = {"direct", "research", "pilot", "scale", "blocked-question", "provisional-pilot"}
MAXIMUM_OUTPUTS = {"requested-output", "preparatory-only", "smallest-adequate-pilot", "full-scale"}
CLAIMS = {"acceptance-ready", "full-scale", "durable-cloud-persistence", "budget-enforcement"}
PILOT_STATUSES = {"not-required", "not-started", "failed", "passed", "settled-approved"}
RESOLUTIONS = {"authority-precedence", "freshness", "applicability", "user-only-decision"}
CASE_KEYS = {
    "id", "description", "costly_scale", "pressure_to_skip", "criteria", "contradictions",
    "question_bundle", "pilot", "refusal", "task_override_only", "capability_evidence",
    "claims_requested", "expected",
}
RESULT_KEYS = {
    "route", "research_stop_met", "maximum_output", "reasons", "required_artifacts",
    "prohibited_claims",
}
EXPECTED_KEYS = RESULT_KEYS - {"reasons"}


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _exact_keys(value: Any, keys: set[str], path: str, errors: list[str]) -> bool:
    if not isinstance(value, Mapping):
        errors.append(f"{path} must be an object")
        return False
    unknown = set(value) - keys
    missing = keys - set(value)
    if unknown:
        errors.append(f"{path} has unknown keys: {sorted(unknown)}")
    if missing:
        errors.append(f"{path} is missing keys: {sorted(missing)}")
    return not unknown and not missing


def _case_errors(case: Any, *, include_expected: bool = False) -> list[str]:
    errors: list[str] = []
    if not _exact_keys(case, CASE_KEYS, "$", errors):
        return errors
    assert isinstance(case, Mapping)
    for field in ("id", "description"):
        if not _nonblank(case[field]):
            errors.append(f"$.{field} must be a non-empty string")
    for field in ("costly_scale", "pressure_to_skip", "task_override_only"):
        if type(case[field]) is not bool:
            errors.append(f"$.{field} must be a boolean")

    criteria = case["criteria"]
    if _exact_keys(criteria, {"status", "source", "provenance", "current"}, "$.criteria", errors):
        assert isinstance(criteria, Mapping)
        if criteria["status"] not in {"missing", "authoritative"}:
            errors.append("$.criteria.status must be missing or authoritative")
        if criteria["source"] is not None and not _nonblank(criteria["source"]):
            errors.append("$.criteria.source must be null or a non-empty string")
        if criteria["provenance"] is not None and not _nonblank(criteria["provenance"]):
            errors.append("$.criteria.provenance must be null or a non-empty string")
        if criteria["current"] is not None and type(criteria["current"]) is not bool:
            errors.append("$.criteria.current must be null or a boolean")

    contradictions = case["contradictions"]
    if not isinstance(contradictions, list):
        errors.append("$.contradictions must be a list")
    else:
        seen: set[str] = set()
        for index, contradiction in enumerate(contradictions):
            path = f"$.contradictions[{index}]"
            if not _exact_keys(
                contradiction, {"id", "material", "resolved", "resolution", "user_only"}, path, errors
            ):
                continue
            assert isinstance(contradiction, Mapping)
            identifier = contradiction["id"]
            if not _nonblank(identifier):
                errors.append(f"{path}.id must be a non-empty string")
            elif identifier in seen:
                errors.append(f"{path}.id is duplicated")
            else:
                seen.add(identifier)
            for field in ("material", "resolved", "user_only"):
                if type(contradiction[field]) is not bool:
                    errors.append(f"{path}.{field} must be a boolean")
            resolution = contradiction["resolution"]
            if resolution is not None and resolution not in RESOLUTIONS:
                errors.append(f"{path}.resolution is unsupported")
            if contradiction["resolved"] and resolution not in {"authority-precedence", "freshness", "applicability"}:
                errors.append(f"{path} resolved contradictions need authoritative precedence, freshness, or applicability evidence")
            if not contradiction["resolved"] and contradiction["user_only"] and resolution != "user-only-decision":
                errors.append(f"{path} user-only contradictions must become an explicit decision")
            if not contradiction["resolved"] and not contradiction["user_only"] and resolution is not None:
                errors.append(f"{path} unresolved investigable contradiction cannot claim a resolution")
            if contradiction["user_only"] and not contradiction["material"]:
                errors.append(f"{path} non-material contradictions cannot block on the user")

    bundle = case["question_bundle"]
    if bundle is not None and _exact_keys(
        bundle, {"recommendation", "impact", "safe_work", "next_step"}, "$.question_bundle", errors
    ):
        assert isinstance(bundle, Mapping)
        for field in ("recommendation", "impact", "safe_work", "next_step"):
            if not _nonblank(bundle[field]):
                errors.append(f"$.question_bundle.{field} must be a non-empty string")
    unresolved_user_only = isinstance(contradictions, list) and any(
        isinstance(item, Mapping)
        and item.get("material") is True
        and item.get("resolved") is False
        and item.get("user_only") is True
        for item in contradictions
    )
    if unresolved_user_only and bundle is None:
        errors.append("$.question_bundle is required for a material user-only contradiction")
    if not unresolved_user_only and bundle is not None:
        errors.append("$.question_bundle is allowed only for a material user-only contradiction")

    pilot = case["pilot"]
    if _exact_keys(pilot, {"required", "status", "representative", "settled_decision_id"}, "$.pilot", errors):
        assert isinstance(pilot, Mapping)
        if type(pilot["required"]) is not bool or type(pilot["representative"]) is not bool:
            errors.append("$.pilot required and representative must be booleans")
        if pilot["status"] not in PILOT_STATUSES:
            errors.append("$.pilot.status is unsupported")
        if pilot["settled_decision_id"] is not None and not _nonblank(pilot["settled_decision_id"]):
            errors.append("$.pilot.settled_decision_id must be null or a non-empty string")
        if case["costly_scale"] is True and pilot["required"] is not True:
            errors.append("$.pilot.required must be true for costly scale")
        if pilot["status"] in {"passed", "settled-approved"} and pilot["representative"] is not True:
            errors.append("$.pilot passed status requires a representative pilot")
        if pilot["status"] == "settled-approved" and not _nonblank(pilot["settled_decision_id"]):
            errors.append("$.pilot settled-approved status requires a decision ID")
        if pilot["required"] is False and pilot["status"] != "not-required":
            errors.append("$.pilot non-required status must be not-required")

    for field, keys in (
        ("refusal", {"research", "pilot"}),
        ("capability_evidence", {"durable_cloud_persistence", "budget_enforcement"}),
    ):
        value = case[field]
        if _exact_keys(value, keys, f"$.{field}", errors):
            assert isinstance(value, Mapping)
            for key in keys:
                if type(value[key]) is not bool:
                    errors.append(f"$.{field}.{key} must be a boolean")

    claims = case["claims_requested"]
    if not isinstance(claims, list) or any(not isinstance(item, str) or item not in CLAIMS for item in claims):
        errors.append("$.claims_requested must contain only supported claim strings")
    elif len(claims) != len(set(claims)):
        errors.append("$.claims_requested contains duplicates")

    if include_expected:
        expected = case["expected"]
        if _exact_keys(expected, EXPECTED_KEYS, "$.expected", errors):
            assert isinstance(expected, Mapping)
            if expected["route"] not in ROUTES:
                errors.append("$.expected.route is unsupported")
            if type(expected["research_stop_met"]) is not bool:
                errors.append("$.expected.research_stop_met must be a boolean")
            if expected["maximum_output"] not in MAXIMUM_OUTPUTS:
                errors.append("$.expected.maximum_output is unsupported")
            for field in ("required_artifacts", "prohibited_claims"):
                values = expected[field]
                if not isinstance(values, list) or any(not _nonblank(value) for value in values):
                    errors.append(f"$.expected.{field} must be a list of non-empty strings")
            if isinstance(expected["prohibited_claims"], list) and any(
                value not in CLAIMS for value in expected["prohibited_claims"]
            ):
                errors.append("$.expected.prohibited_claims contains an unsupported claim")
    return errors


def _malformed(errors: list[str]) -> dict[str, Any]:
    return {
        "route": "blocked-question",
        "research_stop_met": False,
        "maximum_output": "preparatory-only",
        "reasons": ["malformed-input", *errors],
        "required_artifacts": ["corrected-research-gate-input"],
        "prohibited_claims": ["acceptance-ready", "full-scale"],
    }


def evaluate_case(case: Any) -> dict[str, Any]:
    errors = _case_errors(case)
    if errors:
        return _malformed(errors)
    assert isinstance(case, Mapping)
    claims = set(case["claims_requested"])
    evidence = case["capability_evidence"]
    prohibited = {"acceptance-ready", "full-scale"} if case["costly_scale"] else set()
    if "durable-cloud-persistence" in claims and (
        case["task_override_only"] or not evidence["durable_cloud_persistence"]
    ):
        prohibited.add("durable-cloud-persistence")
    if "budget-enforcement" in claims and (
        case["task_override_only"] or not evidence["budget_enforcement"]
    ):
        prohibited.add("budget-enforcement")
    if not case["costly_scale"]:
        return {
            "route": "direct", "research_stop_met": False, "maximum_output": "requested-output",
            "reasons": ["low-cost-reversible-direct"], "required_artifacts": [],
            "prohibited_claims": sorted(prohibited),
        }

    reasons: list[str] = []
    if case["pressure_to_skip"]:
        reasons.append("skip-pressure-does-not-waive-gate")
    if case["refusal"]["research"] or case["refusal"]["pilot"]:
        reasons.append("refusal-bounds-output-to-provisional-pilot")
        return {
            "route": "provisional-pilot", "research_stop_met": False,
            "maximum_output": "smallest-adequate-pilot", "reasons": reasons,
            "required_artifacts": ["provisional-label"], "prohibited_claims": sorted(prohibited),
        }

    contradictions = case["contradictions"]
    unresolved_material = [item for item in contradictions if item["material"] and not item["resolved"]]
    investigable = [item for item in unresolved_material if not item["user_only"]]
    user_only = [item for item in unresolved_material if item["user_only"]]
    if investigable:
        reasons.append("material-contradiction-requires-resolution")
        return {
            "route": "research", "research_stop_met": False, "maximum_output": "preparatory-only",
            "reasons": reasons, "required_artifacts": ["acceptance-rubric"],
            "prohibited_claims": sorted(prohibited),
        }
    if user_only:
        if case["question_bundle"] is None:
            return _malformed(["material user-only contradiction requires one complete question bundle"])
        reasons.append("material-contradiction-converted-to-blocking-user-decision")
        return {
            "route": "blocked-question", "research_stop_met": True, "maximum_output": "preparatory-only",
            "reasons": reasons, "required_artifacts": ["question-bundle"],
            "prohibited_claims": sorted(prohibited),
        }

    criteria = case["criteria"]
    criteria_ready = (
        criteria["status"] == "authoritative"
        and criteria["current"] is True
        and _nonblank(criteria["source"])
        and _nonblank(criteria["provenance"])
    )
    if not criteria_ready:
        reasons.append("web-research-required")
        return {
            "route": "research", "research_stop_met": False, "maximum_output": "preparatory-only",
            "reasons": reasons, "required_artifacts": ["acceptance-rubric"],
            "prohibited_claims": sorted(prohibited),
        }

    if any(not item["material"] and not item["resolved"] for item in contradictions):
        reasons.append("disclose-nonmaterial-contradiction")
    pilot = case["pilot"]
    if pilot["status"] in {"passed", "settled-approved"} and pilot["representative"]:
        reasons.append("representative-pilot-passed")
        return {
            "route": "scale", "research_stop_met": True, "maximum_output": "full-scale",
            "reasons": reasons, "required_artifacts": [],
            "prohibited_claims": sorted(prohibited - {"acceptance-ready", "full-scale"}),
        }
    reasons.append("risk-representative-pilot-required")
    return {
        "route": "pilot", "research_stop_met": True, "maximum_output": "smallest-adequate-pilot",
        "reasons": reasons, "required_artifacts": ["risk-representative-pilot"],
        "prohibited_claims": sorted(prohibited),
    }


def validate_manifest(
    path: Path, *, evaluator: Callable[[Any], Mapping[str, Any]] = evaluate_case
) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("research-gate manifest must be a non-empty list")
    identifiers: set[str] = set()
    for index, case in enumerate(payload):
        errors = _case_errors(case, include_expected=True)
        if errors:
            raise ValueError(f"case {index}: {'; '.join(errors)}")
        identifier = case["id"]
        if identifier in identifiers:
            raise ValueError(f"case {index}: duplicate id {identifier}")
        identifiers.add(identifier)
        actual = evaluator(case)
        if not isinstance(actual, Mapping) or set(actual) != RESULT_KEYS:
            raise ValueError(f"case {identifier}: evaluator returned an invalid result contract")
        expected = case["expected"]
        for field in EXPECTED_KEYS:
            if actual[field] != expected[field]:
                label = field.replace("_", " ")
                raise ValueError(
                    f"case {identifier}: {label} mismatch: expected {expected[field]!r}, got {actual[field]!r}"
                )
    return len(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path, default=Path("tests/research-gate.json"))
    args = parser.parse_args(argv)
    try:
        count = validate_manifest(args.manifest)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"RESEARCH GATE VALIDATION FAILED: {exc}")
        return 1
    print(f"RESEARCH GATE VALIDATION PASSED ({count} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
