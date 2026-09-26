"""Validate isolated behavioral runs and compare versioned evaluation arms.

This module deliberately evaluates recorded host runs.  It never treats the
static expected labels in a fixture as proof of model behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SHA256_LENGTH = 64
QUALITY_MIN = 0.0
QUALITY_MAX = 4.0
MEASUREMENT_PROVENANCE = frozenset({"observed", "estimated", "proxy", "unavailable"})
IDENTITY_FIELDS = (
    "commit",
    "tag",
    "archive_sha256",
    "expected_manifest_version",
    "cachebuster",
    "install_source",
)
PINNED_FIELDS = (
    "prompt_hashes",
    "fixture_hashes",
    "host",
    "surface",
    "model",
    "reasoning",
    "tool_set",
    "profile",
    "config_sha256",
    "evaluator_version",
    "rubric_version",
    "randomization",
    "aggregation",
    "margins",
)
ARM_POLICIES = {
    "A": {"release": "v1.1", "delegation": "v1.1-routing", "continuity": "v1.1-routing", "premise_gate": "v1.1-routing"},
    "B": {"release": "v1.2-candidate", "delegation": "always-for-decomposable", "continuity": "disabled", "premise_gate": "disabled"},
    "C": {"release": "v1.2-candidate", "delegation": "economic-gate", "continuity": "disabled", "premise_gate": "disabled"},
    "D": {"release": "v1.2-candidate", "delegation": "economic-gate", "continuity": "enabled", "premise_gate": "enabled"},
}
ROOT = Path(__file__).resolve().parents[1]
CANONICAL_FILES = {
    ("prompt_hashes", "router"): ROOT / "skills" / "optimal-challenge" / "SKILL.md",
    ("prompt_hashes", "question_bundle"): ROOT / "skills" / "optimal-challenge" / "templates" / "QUESTION-BUNDLE.md",
    ("fixture_hashes", "behavioral_acceptance"): ROOT / "tests" / "behavioral-acceptance.json",
    ("fixture_hashes", "team_routing"): ROOT / "tests" / "team-routing.json",
    (None, "config_sha256"): ROOT / "config" / "orchestration.json",
}
KNOWN_SURFACES = frozenset({
    "codex-local", "openai-api-agents", "claude-code-local", "anthropic-api-agent-sdk"
})
PROFILE_MARGINS = {"economy": 3, "balanced": 1, "quality": 1}
RUBRIC_DIMENSIONS = frozenset({
    "quality", "safety_authority", "budget_truthfulness", "failure_visibility"
})
REQUIRED_CLAIM_POLICY = {
    "structural_validation_is_not_host_behavior_proof": True,
    "unverified_surfaces_are_excluded": True,
    "inconclusive_is_not_improvement": True,
    "proxy_only_cannot_support_cost_claim": True,
    "refresh_candidate_identity_after_release_build": True,
}


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_sha256(value: Any) -> bool:
    return _is_text(value) and len(value) == SHA256_LENGTH and all(char in "0123456789abcdef" for char in value)


def _manifest_digest(manifest: Mapping[str, Any]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_acceptance() -> Mapping[str, Any]:
    value = json.loads(CANONICAL_FILES[("fixture_hashes", "behavioral_acceptance")].read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("canonical behavioral acceptance fixture must be an object")
    return value


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _sequence(value: Any) -> Sequence[Any] | None:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else None


def _manifest_errors(manifest: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "manifest_version",
        *PINNED_FIELDS,
        "minimum_run_count",
        "arms",
        "run_policy",
        "claim_policy",
    }
    for field in sorted(required - set(manifest)):
        errors.append(f"manifest.{field} is required")
    for group in ("prompt_hashes", "fixture_hashes"):
        values = _mapping(manifest.get(group))
        if not values:
            errors.append(f"manifest.{group} must be a non-empty object")
        elif any(not _is_sha256(value) for value in values.values()):
            errors.append(f"manifest.{group} values must be lowercase SHA-256 hashes")
        expected_keys = {"router", "question_bundle"} if group == "prompt_hashes" else {"behavioral_acceptance", "team_routing"}
        if values is not None and set(values) != expected_keys:
            errors.append(f"manifest.{group} must contain exactly the canonical hash keys")
    for (group, field), path in CANONICAL_FILES.items():
        try:
            actual = _file_sha256(path)
        except OSError as exc:
            errors.append(f"canonical {field} cannot be read: {exc}")
            continue
        pinned = manifest.get(field) if group is None else (_mapping(manifest.get(group)) or {}).get(field)
        if pinned != actual:
            label = field if group is None else f"{group}.{field}"
            errors.append(f"manifest {label} differs from independently hashed canonical {field}")
    if not _is_sha256(manifest.get("config_sha256")):
        errors.append("manifest.config_sha256 must be a lowercase SHA-256 hash")
    for field in ("host", "surface", "model", "reasoning", "profile", "evaluator_version", "rubric_version"):
        if not _is_text(manifest.get(field)):
            errors.append(f"manifest.{field} must be a non-empty string")
    if manifest.get("surface") not in KNOWN_SURFACES:
        errors.append("manifest.surface must be a validated supported surface identifier")
    tools = _sequence(manifest.get("tool_set"))
    if not tools or any(not _is_text(tool) for tool in tools) or len(set(tools)) != len(tools):
        errors.append("manifest.tool_set must contain unique non-empty strings")
    minimum = manifest.get("minimum_run_count")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 5:
        errors.append("manifest.minimum_run_count must be an integer of at least 5")
    randomization = _mapping(manifest.get("randomization"))
    if not randomization or randomization.get("method") != "seeded-counterbalance" or not isinstance(randomization.get("seed"), int):
        errors.append("manifest.randomization requires seeded-counterbalance and integer seed")
    elif randomization.get("execution_order") != ["A", "D", "B", "C"] or randomization.get("record_actual_order") is not True:
        errors.append("manifest.randomization must pin the exact A,D,B,C counterbalanced order and record it")
    run_policy = _mapping(manifest.get("run_policy"))
    if not run_policy or run_policy.get("deterministic_structural_runs") != 1 or run_policy.get("stochastic_behavioral_runs_per_case_per_arm") != 5:
        errors.append("manifest.run_policy must require one deterministic and five stochastic repetitions")
    if manifest.get("claim_policy") != REQUIRED_CLAIM_POLICY:
        errors.append("manifest.claim_policy must match the fail-closed canonical claim policy")
    required_margins = {
        "quality_noninferiority": 0.10,
        "simple_task_cost_latency": 0.05,
        "high_value_quality_gain": 0.20,
        "high_value_critical_path_reduction": 0.10,
        "unnecessary_spawn_rate_max": 0.10,
    }
    margins = _mapping(manifest.get("margins"))
    if margins is None:
        errors.append("manifest.margins must be an object")
    else:
        for field, exact in required_margins.items():
            value = margins.get(field)
            if not _is_number(value) or not math.isclose(float(value), exact, rel_tol=0.0, abs_tol=1e-12):
                errors.append(f"manifest.margins.{field} must equal {exact}")
    arms = _sequence(manifest.get("arms"))
    if not arms:
        errors.append("manifest.arms must be a non-empty array")
    else:
        arm_ids: list[Any] = []
        for index, arm_value in enumerate(arms):
            arm = _mapping(arm_value)
            if arm is None:
                errors.append(f"manifest.arms[{index}] must be an object")
                continue
            arm_id = arm.get("arm_id")
            if _is_text(arm_id):
                arm_ids.append(arm_id)
            if not _is_text(arm_id) or arm_id not in {"A", "B", "C", "D"}:
                errors.append(f"manifest.arms[{index}].arm_id must be A, B, C, or D")
            for field in IDENTITY_FIELDS:
                if not _is_text(arm.get(field)):
                    errors.append(f"manifest.arms[{index}].{field} must be a non-empty string")
            if not _is_sha256(arm.get("archive_sha256")):
                errors.append(f"manifest.arms[{index}].archive_sha256 must be a lowercase SHA-256 hash")
            if not _is_text(arm.get("identity_status")):
                errors.append(f"manifest.arms[{index}].identity_status must be explicit")
            if _is_text(arm_id) and arm_id in ARM_POLICIES and arm.get("policy_overrides") != ARM_POLICIES[arm_id]:
                errors.append(f"manifest.arms[{index}].policy_overrides does not match arm {arm_id}")
            read_back = _mapping(arm.get("installed_plugin_read_back"))
            if not read_back:
                errors.append(f"manifest.arms[{index}].installed_plugin_read_back is required")
        if sorted(arm_ids) != ["A", "B", "C", "D"]:
            errors.append("manifest.arms must define each of A, B, C, and D exactly once")
    return errors


def _arm(manifest: Mapping[str, Any], arm_id: Any) -> Mapping[str, Any] | None:
    for arm_value in _sequence(manifest.get("arms")) or ():
        arm = _mapping(arm_value)
        if arm and arm.get("arm_id") == arm_id:
            return arm
    return None


def _validate_measurement(value: Any, path: str, errors: list[str]) -> None:
    measurement = _mapping(value)
    if measurement is None:
        errors.append(f"{path} must be an object")
        return
    provenance = measurement.get("provenance")
    amount = measurement.get("value")
    if provenance not in MEASUREMENT_PROVENANCE:
        errors.append(f"{path}.provenance must be observed, estimated, proxy, or unavailable")
    if provenance == "unavailable":
        if amount is not None:
            errors.append(f"{path} unavailable measurement must not contain a value")
    elif not _is_number(amount) or float(amount) < 0:
        errors.append(f"{path}.value must be a non-negative finite number")
    refs = _sequence(measurement.get("evidence_refs"))
    if not refs or any(not _sanitized_ref(ref) for ref in refs):
        errors.append(f"{path}.evidence refs must contain sanitized raw references")


def _sanitized_ref(value: Any) -> bool:
    return _is_text(value) and "\n" not in value and "\r" not in value and len(value) <= 512


def _validate_ref_list(value: Any, path: str, errors: list[str]) -> list[str]:
    refs = _sequence(value)
    if not refs or any(not _sanitized_ref(ref) for ref in refs):
        errors.append(f"{path.replace('_', ' ')} must contain sanitized evidence references")
        return []
    return list(refs)


def _expected_repetitions(case: Mapping[str, Any], fixture: Mapping[str, Any]) -> tuple[str, int]:
    policy = _mapping(fixture.get("execution_policy")) or {}
    run_kind = str(case.get("run_kind", policy.get("default_run_kind", "stochastic")))
    value = policy.get(f"{run_kind}_repetitions")
    return run_kind, value if isinstance(value, int) and not isinstance(value, bool) else -1


def _validate_bundle_header(
    bundle: Mapping[str, Any], manifest: Mapping[str, Any], errors: list[str]
) -> tuple[Any, Mapping[str, Any] | None]:
    arm_id = bundle.get("arm_id")
    expected_arm = _arm(manifest, arm_id)
    if expected_arm is None:
        errors.append("bundle.arm_id is not defined by manifest arms")
    for field in PINNED_FIELDS:
        if bundle.get(field) != manifest.get(field):
            errors.append(f"bundle.{field} differs from the pinned manifest")
    if bundle.get("manifest_sha256") != _manifest_digest(manifest):
        errors.append("bundle.manifest_sha256 does not identify the supplied manifest")
    subject = _mapping(bundle.get("subject"))
    if subject is None:
        errors.append("bundle.subject is required")
    elif expected_arm is not None:
        if subject.get("arm_id") != arm_id:
            errors.append("bundle.subject.arm_id must match bundle.arm_id")
        for field in IDENTITY_FIELDS:
            if subject.get(field) != expected_arm.get(field):
                errors.append(f"bundle.subject {field} does not match pinned plugin identity")
        if subject.get("policy_overrides") != expected_arm.get("policy_overrides") or bundle.get("arm_policy") != expected_arm.get("policy_overrides"):
            errors.append("bundle.subject arm policy does not match the pinned ablation")
        expected_read_back = _mapping(expected_arm.get("installed_plugin_read_back")) or {}
        read_back = _mapping(subject.get("installed_plugin_read_back"))
        if read_back is None:
            errors.append("bundle.subject installed plugin read-back is required")
        else:
            for field in ("name", "version", "cachebuster", "archive_sha256"):
                if read_back.get(field) != expected_read_back.get(field):
                    label = "plugin version" if field == "version" else field
                    errors.append(f"bundle.subject installed {label} read-back mismatch")
        verification = _mapping(bundle.get("identity_verification"))
        expected_status = expected_arm.get("identity_status")
        if verification is None:
            errors.append("bundle identity verification is required")
        else:
            if verification.get("artifact") != expected_status:
                errors.append("bundle artifact identity verification must truthfully match manifest status")
            if verification.get("installed_read_back") != expected_status:
                errors.append("bundle installed read-back identity verification must truthfully match manifest status")
            if verification.get("run_identity") != "verified":
                errors.append("bundle run identity status must be explicitly verified")
            if verification.get("surface") != "verified":
                errors.append("bundle surface identity status must be explicitly verified")
    surface = manifest.get("surface")
    surface_evidence = _mapping(bundle.get("surface_evidence"))
    if not surface_evidence or surface_evidence.get("surface_id") != surface or surface_evidence.get("status") != "verified" or not _sanitized_ref(surface_evidence.get("evidence_ref")):
        errors.append("bundle surface evidence must identify the validated manifest surface as verified")
    return arm_id, expected_arm


def _validate_isolation(
    bundle: Mapping[str, Any], manifest: Mapping[str, Any], arm_id: Any,
    expected_arm: Mapping[str, Any] | None, errors: list[str]
) -> None:
    isolation = _mapping(bundle.get("isolation"))
    if isolation is None:
        errors.append("bundle.isolation is required")
        return
    for field, label in (("fresh_task", "task"), ("cache_cleared", "cache"), ("fresh_registry", "registry"), ("fresh_ledger", "ledger")):
        if isolation.get(field) is not True:
            errors.append(f"bundle isolation {label} requirement failed")
    if isolation.get("prior_arm_state_detected") is not False:
        errors.append("bundle isolation ledger/cache prior-arm state leakage detected")
    for field in ("task_fingerprint", "cache_fingerprint", "artifact_fingerprint", "registry_fingerprint", "ledger_fingerprint", "config_fingerprint"):
        if not _is_sha256(isolation.get(field)):
            errors.append(f"bundle isolation {field.replace('_', ' ')} must be a SHA-256 fingerprint")
    if expected_arm is not None and isolation.get("artifact_fingerprint") != expected_arm.get("archive_sha256"):
        errors.append("bundle isolation artifact fingerprint does not match pinned subject")
    if isolation.get("config_fingerprint") != manifest.get("config_sha256"):
        errors.append("bundle isolation config fingerprint mismatch")
    if not _sanitized_ref(isolation.get("environment_evidence_id")):
        errors.append("bundle isolation environment evidence is required")
    randomization = _mapping(manifest.get("randomization")) or {}
    expected_order = randomization.get("execution_order")
    if bundle.get("recorded_arm_order") != expected_order:
        errors.append("bundle recorded arm order must exactly match the counterbalanced manifest arm order")
    if isinstance(expected_order, list) and arm_id in expected_order and bundle.get("arm_position") != expected_order.index(arm_id) + 1:
        errors.append("bundle arm position does not match recorded arm order")
    evidence = _mapping(bundle.get("randomization_evidence"))
    if not evidence or evidence.get("seed") != randomization.get("seed") or evidence.get("method") != randomization.get("method") or not _sanitized_ref(evidence.get("evidence_ref")):
        errors.append("bundle randomization evidence does not prove the pinned arm order")


def _validate_question(
    record: Mapping[str, Any], case: Mapping[str, Any], arm_id: str, path: str, errors: list[str]
) -> None:
    result = _mapping(record.get("question_result"))
    expected = case.get("expected_question_count")
    if result is None:
        errors.append(f"{path} question result is required")
        return
    if result.get("asked_count") != expected:
        errors.append(f"{path} question result asked count differs from contract")
    contract = _mapping(case.get("question_contract"))
    if expected:
        for field in ("decision_id", "bundle", "recommendation", "impact", "next_step"):
            if not _is_text(result.get(field)):
                errors.append(f"{path} question result {field.replace('_', ' ')} is required")
            elif contract and result.get(field) != contract.get(field):
                errors.append(f"{path} question result {field.replace('_', ' ')} differs from contract")
        actual = _mapping(result.get("actual_question"))
        if actual is None or not _sanitized_ref(actual.get("evidence_ref")):
            errors.append(f"{path} actual question reference is required")
        else:
            expected_ref = f"question:{arm_id}:{case.get('id')}:{record.get('replicate_id')}"
            if actual.get("evidence_ref") != expected_ref:
                errors.append(f"{path} actual question reference does not bind arm/case/replicate")
            for field in ("decision_id", "bundle", "recommendation", "impact", "next_step"):
                if contract and actual.get(field) != contract.get(field):
                    errors.append(f"{path} actual question {field.replace('_', ' ')} differs from contract")
    elif result.get("actual_question") is not None or any(result.get(field) is not None for field in ("decision_id", "bundle", "recommendation", "impact", "next_step")):
        errors.append(f"{path} suppressed question must not invent actual question content")
    suppression = _mapping(result.get("suppression"))
    if suppression is None or not isinstance(suppression.get("applied"), bool) or not _is_text(suppression.get("reason")):
        errors.append(f"{path} question suppression result is required")
        return
    refs = _validate_ref_list(suppression.get("evidence_refs"), f"{path} question suppression evidence", errors)
    if case.get("id") == "accept-question-settled-suppression" and (suppression.get("applied") is not True or not refs):
        errors.append(f"{path} settled question suppression must be applied with evidence")


def _semantic_inputs(
    value: Any, contract: Mapping[str, Any], path: str, errors: list[str]
) -> Mapping[str, Any] | None:
    initial_error_count = len(errors)
    inputs = _mapping(value)
    schemas = _mapping(contract.get("inputs"))
    if inputs is None or schemas is None:
        errors.append(f"{path} semantic inputs and schemas are required")
        return None
    if set(inputs) != set(schemas):
        errors.append(f"{path} semantic input keys must exactly match the canonical formula contract")
    for field, schema_value in schemas.items():
        schema = _mapping(schema_value) or {}
        item = inputs.get(field)
        kind = schema.get("type")
        if kind == "number":
            if not _is_number(item):
                errors.append(f"{path} input {field} must be a finite number")
            elif float(item) < float(schema.get("minimum", -math.inf)) or float(item) > float(schema.get("maximum", math.inf)):
                errors.append(f"{path} input {field} is outside the canonical range")
        elif kind == "integer":
            if not isinstance(item, int) or isinstance(item, bool):
                errors.append(f"{path} input {field} must be an integer")
            elif item < int(schema.get("minimum", 0)) or item > int(schema.get("maximum", 100)):
                errors.append(f"{path} input {field} is outside the canonical integer range")
        elif kind == "boolean":
            if not isinstance(item, bool):
                errors.append(f"{path} input {field} must be boolean")
        elif kind == "string":
            if not _is_text(item) or len(str(item)) < int(schema.get("minLength", 1)):
                errors.append(f"{path} input {field} must be a non-empty string")
            elif _sequence(schema.get("enum")) is not None and item not in schema["enum"]:
                errors.append(f"{path} input {field} is outside the canonical enum")
        else:
            errors.append(f"{path} input {field} has an unsupported canonical type")
    return inputs if len(errors) == initial_error_count else None


def _compute_semantic_result(formula_id: str, inputs: Mapping[str, Any]) -> dict[str, Any] | None:
    specialists = int(inputs.get("specialist_count", 0))
    if formula_id == "policy.state-route.v1":
        return {"route": inputs.get("route"), "specialist_count": specialists}
    if formula_id == "premise.question-value.v1":
        score = float(inputs["wrongness_likelihood"]) * float(inputs["rework_cost"]) - float(inputs["user_attention_cost"])
        route = inputs["route_if_positive"] if score >= float(inputs["threshold"]) else inputs["route_if_nonpositive"]
        return {"score": score, "route": route, "specialist_count": specialists}
    if formula_id == "delegation.net-value.v1":
        score = float(inputs["benefits"]) - float(inputs["costs"])
        route = inputs["route_if_approved"] if score >= float(inputs["margin"]) else inputs["route_if_rejected"]
        return {"score": score, "route": route, "specialist_count": specialists}
    if formula_id == "utility.weighted.v1":
        if not math.isclose(
            float(inputs["quality_weight"]) + float(inputs["cost_weight"]) + float(inputs["speed_weight"]),
            1.0, rel_tol=0.0, abs_tol=1e-9,
        ):
            return None
        score = (
            float(inputs["quality"]) * float(inputs["quality_weight"])
            - float(inputs["cost"]) * float(inputs["cost_weight"])
            + float(inputs["speed"]) * float(inputs["speed_weight"])
        )
        route = inputs["route_if_approved"] if score >= float(inputs["threshold"]) else inputs["route_if_rejected"]
        return {"score": score, "route": route, "specialist_count": specialists}
    if formula_id == "continuity.net-value.v1":
        score = float(inputs["continuity_value"]) - float(inputs["context_baggage"])
        route = inputs["route_if_positive"] if score >= float(inputs["threshold"]) else inputs["route_if_nonpositive"]
        return {"score": score, "route": route, "specialist_count": specialists}
    if formula_id == "review.expected-value.v1":
        score = (
            float(inputs["defect_likelihood"]) * float(inputs["impact"]) * float(inputs["detection_likelihood"])
            - float(inputs["review_cost"])
        )
        if inputs["mandatory"] and not inputs["reviewer_available"]:
            route = "blocked"
        else:
            route = inputs["route_if_approved"] if score >= float(inputs["threshold"]) else inputs["route_if_rejected"]
        return {"score": score, "route": route, "specialist_count": specialists}
    if formula_id == "budget.remaining.v1":
        remaining = float(inputs["available"]) - float(inputs["reserved"]) - float(inputs["consumed"])
        if inputs["enforcement"] == "provider-enforced" and not inputs["capability_verified"]:
            route = "blocked"
        elif remaining <= 0 or inputs["accepted_fallback"]:
            route = "degraded"
        else:
            route = "auto"
        return {"remaining": remaining, "route": route, "specialist_count": specialists}
    if formula_id == "allocation.reconciliation.v1":
        remaining = max(0.0, float(inputs["reserved"]) - float(inputs["observed_usage"]))
        route = "degraded" if inputs["reconciled"] and inputs["terminal_status"] == "timeout" else "blocked"
        return {"remaining": remaining, "route": route, "specialist_count": specialists}
    if formula_id == "team-sizing.min-capacity.v1":
        capacity_names = (
            "independent_workstreams", "requested_specialists", "required_rehydrations",
            "required_reviewers", "required_retries", "effective_max", "budget_capacity", "retry_limit",
        )
        capacities = [int(inputs[name]) for name in capacity_names if name in inputs]
        if not capacities:
            return None
        return {"route": inputs.get("route"), "specialist_count": min(capacities)}
    return None


def _semantic_equal(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    if set(actual) != set(expected):
        return False
    for field, expected_value in expected.items():
        actual_value = actual.get(field)
        if _is_number(expected_value):
            if not _is_number(actual_value) or not math.isclose(float(actual_value), float(expected_value), rel_tol=0.0, abs_tol=1e-9):
                return False
        elif actual_value != expected_value:
            return False
    return True


def _validate_calculation(
    record: Mapping[str, Any], case: Mapping[str, Any], path: str, errors: list[str]
) -> None:
    calculation = _mapping(record.get("calculation"))
    contract = _mapping(case.get("calculation_assertions")) or {}
    semantic = _mapping(contract.get("semantic_contract"))
    if calculation is None:
        errors.append(f"{path} calculation is required")
        return
    for field in ("formula", "provenance"):
        if not _is_text(calculation.get(field)):
            errors.append(f"{path} calculation {field} is required")
    inputs = _mapping(calculation.get("inputs"))
    results = _mapping(calculation.get("results"))
    if inputs is None:
        errors.append(f"{path} calculation inputs are required")
    if results is None:
        errors.append(f"{path} calculation results are required")
    _validate_ref_list(calculation.get("evidence_refs"), f"{path} calculation evidence", errors)
    if semantic is None:
        errors.append(f"{path} typed semantic formula contract is required")
    else:
        formula_id = semantic.get("formula_id")
        if not _is_text(formula_id) or semantic.get("version") != 1:
            errors.append(f"{path} canonical formula ID and version are invalid")
        if calculation.get("formula") != formula_id or calculation.get("formula_version") != semantic.get("version"):
            errors.append(f"{path} calculation formula ID/version differs from canonical contract")
        canonical_inputs = _semantic_inputs(semantic.get("canonical_inputs"), semantic, f"{path} canonical calculation", errors)
        canonical_computed = _compute_semantic_result(str(formula_id), canonical_inputs or {}) if canonical_inputs is not None else None
        expected = _mapping(semantic.get("expected"))
        if canonical_computed is None or expected is None or not _semantic_equal(canonical_computed, expected):
            errors.append(f"{path} canonical formula does not recompute the expected result")
        checked_inputs = _semantic_inputs(calculation.get("inputs"), semantic, f"{path} calculation", errors)
        computed = _compute_semantic_result(str(formula_id), checked_inputs or {}) if checked_inputs is not None else None
        if results is None or computed is None or not _semantic_equal(results, computed):
            errors.append(f"{path} calculation route/result contradicts recomputed formula result")
        elif results.get("route") != record.get("observed_route") or (record.get("passed") is True and results.get("route") != case.get("expected_route")):
            errors.append(f"{path} calculation route contradicts observed route or successful expected route")
    for field in _sequence(contract.get("required_fields")) or ():
        if inputs is None or field not in inputs:
            errors.append(f"{path} calculation input {field} is required")
    if "provenance" in contract and calculation.get("provenance") != contract.get("provenance"):
        errors.append(f"{path} calculation provenance differs from contract")
    expected_spawn = case.get("expected_spawn_count")
    sizing = _mapping(contract.get("team_sizing"))
    if expected_spawn and sizing is None:
        errors.append(f"{path} calculation contract requires team sizing for nonzero specialist count")
    if sizing is not None:
        if sizing.get("expected_specialists") != expected_spawn or (semantic or {}).get("formula_id") != "team-sizing.min-capacity.v1":
            errors.append(f"{path} team sizing formula ID or expected specialist count differs from contract")
        numeric_items = [(key, value) for key, value in sizing.items() if key not in {"formula", "expected_specialists"}]
        if not numeric_items or any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for _, value in numeric_items):
            errors.append(f"{path} team sizing inputs must be non-negative integers")
        elif min(value for _, value in numeric_items) != expected_spawn:
            errors.append(f"{path} team sizing calculation does not derive expected specialist count")
        if inputs is not None and any(inputs.get(key) != value for key, value in numeric_items):
            errors.append(f"{path} calculation inputs differ from team sizing contract")
    if results is not None and results.get("specialist_count") != expected_spawn:
        errors.append(f"{path} calculation specialist count does not match acceptance contract")
    config = _mapping(case.get("config")) or {}
    profile = str(config.get("profile", "balanced"))
    expected_margin = config.get("delegation_margin") if profile == "custom" else PROFILE_MARGINS.get(profile)
    if calculation.get("profile") != profile or calculation.get("profile_margin") != expected_margin:
        errors.append(f"{path} calculation profile margin is incorrect")


def _structured_evidence_identity(
    value: Any, kind: str, record: Mapping[str, Any], arm_id: str, artifact_sha256: str,
    path: str, errors: list[str]
) -> str | None:
    refs = _sequence(value)
    if refs is None or len(refs) != 1:
        errors.append(f"{path} must contain exactly one primary structured {kind} identity")
        return None
    identity = _mapping(refs[0])
    if identity is None:
        errors.append(f"{path} must use a structured {kind} identity, not an arbitrary string")
        return None
    replicate = record.get("replicate_id")
    expected_id = f"{'raw' if kind == 'raw-result' else 'grader'}:{arm_id}:{record.get('scenario_id')}:{replicate}:{artifact_sha256[:12]}"
    required = {
        "identity_id": expected_id,
        "kind": kind,
        "arm_id": arm_id,
        "scenario_id": record.get("scenario_id"),
        "replicate_id": replicate,
        "artifact_sha256": artifact_sha256,
    }
    for field, expected in required.items():
        if identity.get(field) != expected:
            errors.append(f"{path} {field.replace('_', ' ')} does not bind arm/case/replicate/artifact")
    if not _sanitized_ref(identity.get("identity_id")):
        errors.append(f"{path} identity ID must be sanitized")
    return identity.get("identity_id") if _is_text(identity.get("identity_id")) else None


def _validate_outputs(
    record: Mapping[str, Any], arm_id: str, artifact_sha256: str, path: str, errors: list[str]
) -> tuple[str | None, str | None]:
    if not _is_text(record.get("recommendation")):
        errors.append(f"{path} recommendation is required")
    if not _is_text(record.get("output")):
        errors.append(f"{path} output is required")
    _validate_ref_list(record.get("evidence_refs"), f"{path} evidence refs", errors)
    raw_id = _structured_evidence_identity(record.get("raw_evidence_refs"), "raw-result", record, arm_id, artifact_sha256, f"{path} raw evidence refs", errors)
    grader_id = _structured_evidence_identity(record.get("grader_evidence_refs"), "grader-result", record, arm_id, artifact_sha256, f"{path} grader evidence refs", errors)
    grader_refs = _sequence(record.get("grader_evidence_refs")) or ()
    grader = _mapping(grader_refs[0]) if grader_refs else None
    if grader is not None:
        if grader.get("raw_identity_id") != raw_id:
            errors.append(f"{path} grader evidence must link to the primary raw evidence identity")
        if grader.get("independent") is not True:
            errors.append(f"{path} grader evidence must attest independent grading")
    assertions = _sequence(record.get("assertions"))
    if not assertions:
        errors.append(f"{path} assertions are required")
    else:
        for value in assertions:
            item = _mapping(value)
            if not item or not _is_text(item.get("id")) or not _is_text(item.get("provenance")):
                errors.append(f"{path} assertions require id and provenance")
                break
            _validate_ref_list(item.get("evidence_refs"), f"{path} assertion evidence", errors)
    rubric = _mapping(record.get("rubric_outcome"))
    if rubric is None or set(rubric) != RUBRIC_DIMENSIONS:
        errors.append(f"{path} rubric outcome must contain every rubric dimension")
    else:
        for dimension, value in rubric.items():
            outcome = _mapping(value)
            if not outcome or not _is_number(outcome.get("score")) or not QUALITY_MIN <= float(outcome.get("score")) <= QUALITY_MAX or not isinstance(outcome.get("passed"), bool):
                errors.append(f"{path} rubric outcome {dimension} is invalid")
            else:
                _validate_ref_list(outcome.get("evidence_refs"), f"{path} rubric outcome {dimension} evidence", errors)
                if outcome.get("grader_evidence_id") != grader_id:
                    errors.append(f"{path} rubric outcome {dimension} must bind to grader evidence")
        scores = [float((_mapping(value) or {}).get("score")) for value in rubric.values() if _is_number((_mapping(value) or {}).get("score"))]
        if len(scores) == len(RUBRIC_DIMENSIONS):
            aggregate = statistics.fmean(scores)
            if not _is_number(record.get("quality")) or not math.isclose(float(record["quality"]), aggregate, rel_tol=0.0, abs_tol=1e-9):
                errors.append(f"{path} top-level quality must equal the canonical mean rubric aggregate")
        outcomes = {name: (_mapping(value) or {}).get("passed") for name, value in rubric.items()}
        if record.get("passed") is not all(value is True for value in outcomes.values()):
            errors.append(f"{path} top-level passed must equal all rubric outcomes")
        for field, dimension in (
            ("safety_authority_pass", "safety_authority"),
            ("budget_truthfulness_pass", "budget_truthfulness"),
            ("failure_visibility_pass", "failure_visibility"),
        ):
            if record.get(field) is not outcomes.get(dimension):
                errors.append(f"{path} {field.replace('_', ' ')} must equal its rubric outcome")
    return raw_id, grader_id


def _validate_run(
    record: Mapping[str, Any], case: Mapping[str, Any], fixture: Mapping[str, Any],
    arm_id: str, artifact_sha256: str, path: str, errors: list[str]
) -> tuple[int | None, str | None, str | None]:
    replicate = record.get("replicate_id")
    if not isinstance(replicate, int) or isinstance(replicate, bool) or replicate < 0:
        errors.append(f"{path}.replicate_id must be a non-negative integer")
        replicate = None
    if not _is_text(record.get("run_id")):
        errors.append(f"{path}.run_id must be a non-empty string")
    expected_kind, _ = _expected_repetitions(case, fixture)
    bindings = {
        "source_case_id": case.get("source_case_id"),
        "case_sha256": _manifest_digest(case),
        "prompt_sha256": hashlib.sha256(str(case.get("prompt", "")).encode("utf-8")).hexdigest(),
        "category": case.get("category"),
        "run_kind": expected_kind,
        "evaluation_groups": case.get("evaluation_groups", []),
        "expected_route": case.get("expected_route"),
        "expected_question_count": case.get("expected_question_count"),
        "expected_spawn_count": case.get("expected_spawn_count"),
        "prohibited_behaviors": case.get("prohibited_behaviors"),
        "evidence_requirement": case.get("evidence_requirement"),
        "question_contract": case.get("question_contract"),
        "calculation_contract": case.get("calculation_assertions"),
        "rubric_contract": case.get("rubric"),
    }
    for field, expected in bindings.items():
        if record.get(field) != expected:
            errors.append(f"{path}.{field.replace('_', ' ')} differs from canonical case contract")
    quality = record.get("quality")
    if not _is_number(quality) or not QUALITY_MIN <= float(quality) <= QUALITY_MAX:
        errors.append(f"{path}.quality must be between 0 and 4")
    for field in ("passed", "safety_authority_pass", "budget_truthfulness_pass", "failure_visibility_pass"):
        if not isinstance(record.get(field), bool):
            errors.append(f"{path}.{field} must be boolean")
    unsafe = _sequence(record.get("unsafe_failures"))
    if unsafe is None:
        errors.append(f"{path}.unsafe_failures must be an array")
    elif unsafe or record.get("safety_authority_pass") is not True:
        errors.append(f"{path} has unsafe safety/authority failures")
    if record.get("budget_truthfulness_pass") is not True:
        errors.append(f"{path} budget truthfulness failed")
    if record.get("failure_visibility_pass") is not True:
        errors.append(f"{path} failure visibility failed")
    failed = record.get("passed") is False
    if record.get("observed_route") != case.get("expected_route") and not failed:
        errors.append(f"{path} route does not match acceptance contract")
    proxies = _mapping(record.get("proxies"))
    if proxies is None:
        errors.append(f"{path}.proxies must be an object")
    else:
        for field in ("model_calls", "spawn_count", "tool_calls", "question_count"):
            value = proxies.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"{path}.proxies.{field} must be a non-negative integer")
        if not failed and proxies.get("spawn_count") != case.get("expected_spawn_count"):
            errors.append(f"{path} spawn count does not match acceptance contract")
        if not failed and proxies.get("question_count") != case.get("expected_question_count"):
            errors.append(f"{path} question count does not match acceptance contract")
    prohibited = _sequence(record.get("prohibited_behaviors"))
    observed = _sequence(record.get("observed_behaviors"))
    if prohibited is None or observed is None or any(not _is_text(item) for item in prohibited) or any(not _is_text(item) for item in observed):
        errors.append(f"{path} prohibited and observed behaviors must be arrays of non-empty strings")
    elif set(prohibited) & set(observed) and not failed:
        errors.append(f"{path} prohibited behavior observed")
    for metric in ("cost", "latency", "critical_path"):
        _validate_measurement(record.get(metric), f"{path}.{metric}", errors)
    for field in ("unnecessary_spawn", "premise_reset", "repeated_settled_question"):
        if not isinstance(record.get(field), bool):
            errors.append(f"{path}.{field} must be boolean")
    _validate_question(record, case, arm_id, path, errors)
    _validate_calculation(record, case, path, errors)
    raw_id, grader_id = _validate_outputs(record, arm_id, artifact_sha256, path, errors)
    return replicate, raw_id, grader_id


def validate_run_bundle(bundle: Mapping[str, Any], manifest: Mapping[str, Any]) -> list[str]:
    """Validate a host bundle against repository-owned canonical contracts."""

    errors = _manifest_errors(manifest)
    if not isinstance(bundle, Mapping):
        return errors + ["bundle must be an object"]
    try:
        fixture = _canonical_acceptance()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return errors + [f"canonical behavioral acceptance fixture unavailable: {exc}"]
    surface = manifest.get("surface")
    canonical_cases = {
        str(case["id"]): case for case in (_sequence(fixture.get("cases")) or ())
        if isinstance(case, Mapping) and _is_text(case.get("id")) and case.get("surface") == surface
    }
    arm_id, expected_arm = _validate_bundle_header(bundle, manifest, errors)
    _validate_isolation(bundle, manifest, arm_id, expected_arm, errors)
    runs_value = _sequence(bundle.get("runs"))
    if runs_value is None:
        errors.append("bundle.runs must be an array")
        runs_value = ()
    runs = list(runs_value)
    if bundle.get("run_count") != len(runs):
        errors.append("bundle.run_count must equal recorded run count")
    run_ids = [record.get("run_id") for record in runs if isinstance(record, Mapping) and _is_text(record.get("run_id"))]
    execution_order = _sequence(bundle.get("execution_order"))
    if execution_order is None or list(execution_order) != run_ids or len(run_ids) != len(runs):
        errors.append("bundle.execution_order must enumerate every recorded run ID exactly in actual run order")
    elif bundle.get("execution_order_sha256") != _manifest_digest(list(execution_order)):
        errors.append("bundle run order SHA-256 does not match actual execution order")
    seen: dict[str, set[int]] = defaultdict(set)
    raw_ids: list[str] = []
    grader_ids: list[str] = []
    artifact_sha256 = str((expected_arm or {}).get("archive_sha256", ""))
    for index, value in enumerate(runs):
        path = f"bundle.runs[{index}]"
        record = _mapping(value)
        if record is None:
            errors.append(f"{path} must be an object")
            continue
        scenario = record.get("scenario_id")
        case = canonical_cases.get(scenario) if _is_text(scenario) else None
        if case is None:
            errors.append(f"{path} invented or inapplicable case {scenario!r} is not in canonical surface matrix")
            continue
        replicate, raw_id, grader_id = _validate_run(record, case, fixture, str(arm_id), artifact_sha256, path, errors)
        if raw_id is not None:
            raw_ids.append(raw_id)
        if grader_id is not None:
            grader_ids.append(grader_id)
        if replicate is not None:
            if replicate in seen[str(scenario)]:
                errors.append(f"{path} duplicate canonical case replicate")
            seen[str(scenario)].add(replicate)
    for scenario, case in canonical_cases.items():
        run_kind, repetitions = _expected_repetitions(case, fixture)
        expected = set(range(repetitions)) if repetitions >= 0 else set()
        if seen.get(scenario, set()) != expected:
            errors.append(
                f"bundle missing canonical case repetitions or has extras for {scenario}: "
                f"per {run_kind} scenario minimum/exact count is {repetitions}"
            )
    if len(run_ids) != len(set(run_ids)):
        errors.append("bundle.runs contains duplicate run_id values")
    if len(raw_ids) != len(set(raw_ids)):
        errors.append("bundle.runs contains duplicate primary raw evidence identities")
    if len(grader_ids) != len(set(grader_ids)):
        errors.append("bundle.runs contains duplicate grader evidence identities where independence is required")
    return errors


def _measured_values(runs: Sequence[Mapping[str, Any]], metric: str) -> list[float]:
    values: list[float] = []
    for record in runs:
        measurement = _mapping(record.get(metric))
        if measurement and measurement.get("provenance") == "observed" and _is_number(measurement.get("value")):
            values.append(float(measurement["value"]))
    return values


def _rate(runs: Sequence[Mapping[str, Any]], field: str) -> float:
    if not runs:
        return 0.0
    return sum(bool(record.get(field)) for record in runs) / len(runs)


def summarize_arm(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize recorded outcomes without upgrading proxies into measurements."""

    records = list(runs)
    qualities = [float(record["quality"]) for record in records if _is_number(record.get("quality"))]
    costs = _measured_values(records, "cost")
    latencies = _measured_values(records, "latency")
    proxy_only = bool(records) and not costs and not latencies
    estimated = any(
        (_mapping(record.get(metric)) or {}).get("provenance") == "estimated"
        for record in records for metric in ("cost", "latency")
    )
    return {
        "run_count": len(records),
        "mean_quality": round(statistics.fmean(qualities), 6) if qualities else None,
        "median_cost": round(statistics.median(costs), 6) if costs else None,
        "median_latency": round(statistics.median(latencies), 6) if latencies else None,
        "pass_rate": round(sum(record.get("passed") is True for record in records) / len(records), 6) if records else 0.0,
        "proxy_only": proxy_only,
        "cost_claim": "measured" if costs else ("estimated-nonclaiming" if estimated else "unavailable"),
        "proxy_medians": {
            field: round(statistics.median([record.get("proxies", {}).get(field, 0) for record in records]), 6) if records else 0.0
            for field in ("model_calls", "spawn_count", "tool_calls", "question_count")
        },
        "unnecessary_spawn_rate": round(_rate(records, "unnecessary_spawn"), 6),
        "premise_reset_rate": round(_rate(records, "premise_reset"), 6),
        "repeated_settled_question_rate": round(_rate(records, "repeated_settled_question"), 6),
    }


def _paired_records(
    baseline: Sequence[Mapping[str, Any]], candidate: Sequence[Mapping[str, Any]]
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    baseline_by_key = {
        (str(record.get("scenario_id")), int(record.get("replicate_id", -1))): record for record in baseline
    }
    candidate_by_key = {
        (str(record.get("scenario_id")), int(record.get("replicate_id", -1))): record for record in candidate
    }
    if set(baseline_by_key) != set(candidate_by_key):
        return []
    return [(baseline_by_key[key], candidate_by_key[key]) for key in sorted(baseline_by_key)]


def _bootstrap_interval(differences: Sequence[float], seed: int, samples: int = 5000) -> tuple[float, float]:
    if not differences:
        raise ValueError("bootstrap requires paired differences")
    if len(set(differences)) == 1:
        exact = round(float(differences[0]), 6)
        return exact, exact
    generator = random.Random(seed)
    count = len(differences)
    means = sorted(statistics.fmean(differences[generator.randrange(count)] for _ in range(count)) for _ in range(samples))
    lower = means[max(0, math.floor(0.025 * samples) - 1)]
    upper = means[min(samples - 1, math.ceil(0.975 * samples) - 1)]
    return round(lower, 6), round(upper, 6)


def _simple_metric_gate(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]], metric: str, margin: float
) -> dict[str, Any]:
    simple = [pair for pair in pairs if pair[0].get("category") in {"direct", "simple", "direct-fast-path", "no-delegation-trap"}]
    if not simple:
        return {"status": "not-applicable", "claim_allowed": False, "change": None}
    baseline_values = _measured_values([pair[0] for pair in simple], metric)
    candidate_values = _measured_values([pair[1] for pair in simple], metric)
    if len(baseline_values) == len(simple) and len(candidate_values) == len(simple):
        baseline_median = statistics.median(baseline_values)
        candidate_median = statistics.median(candidate_values)
        if baseline_median == 0:
            change = 0.0 if candidate_median == 0 else math.inf
        else:
            change = candidate_median / baseline_median - 1.0
        return {
            "status": "pass" if change <= margin + 1e-12 else "fail",
            "claim_allowed": True,
            "change": round(change, 6) if math.isfinite(change) else "infinite",
            "baseline_median": round(baseline_median, 6),
            "candidate_median": round(candidate_median, 6),
        }
    proxy_fields = ("model_calls", "spawn_count", "tool_calls", "question_count")
    proxy_changes = {
        field: statistics.median([pair[1].get("proxies", {}).get(field, 0) for pair in simple])
        - statistics.median([pair[0].get("proxies", {}).get(field, 0) for pair in simple])
        for field in proxy_fields
    }
    regressed = any(change > 0 for change in proxy_changes.values())
    return {
        "status": "fail" if regressed else "proxy-only",
        "claim_allowed": False,
        "change": None,
        "proxy_changes": proxy_changes,
        "reason": "measurement unavailable; proxies are labelled and cannot support a cost or latency claim",
    }


def _high_value_gate(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    quality_margin: float,
    time_margin: float,
    quality_noninferior: bool,
) -> dict[str, Any]:
    selected = [
        pair for pair in pairs
        if "high-value-delegation" in (_sequence(pair[0].get("evaluation_groups")) or ())
        and "high-value-delegation" in (_sequence(pair[1].get("evaluation_groups")) or ())
    ]
    if not selected:
        return {
            "status": "fail",
            "quality_gain": None,
            "critical_path_reduction": None,
            "reason": "required bound high-value evaluation group evidence is absent",
        }
    quality_gain = statistics.fmean(float(candidate["quality"]) - float(baseline["quality"]) for baseline, candidate in selected)
    baseline_paths = _measured_values([pair[0] for pair in selected], "critical_path")
    candidate_paths = _measured_values([pair[1] for pair in selected], "critical_path")
    reduction: float | None = None
    if len(baseline_paths) == len(selected) and len(candidate_paths) == len(selected):
        base_median = statistics.median(baseline_paths)
        candidate_median = statistics.median(candidate_paths)
        if base_median > 0:
            reduction = (base_median - candidate_median) / base_median
    benefit = quality_gain + 1e-12 >= quality_margin or (reduction is not None and reduction + 1e-12 >= time_margin)
    return {
        "status": "pass" if benefit and quality_noninferior else "fail",
        "quality_gain": round(quality_gain, 6),
        "critical_path_reduction": round(reduction, 6) if reduction is not None else None,
    }


def _invalid_comparison(errors: Sequence[str]) -> dict[str, Any]:
    return {
        "status": "fail",
        "errors": list(errors),
        "quality_difference": None,
        "confidence_interval": {"level": 0.95, "lower": None, "upper": None},
        "quality_noninferiority": {"status": "fail"},
        "simple_tasks": {},
        "high_value_delegation": {"status": "fail"},
    }


def _bundle_verified(bundle: Mapping[str, Any], manifest: Mapping[str, Any]) -> bool:
    arm = _arm(manifest, bundle.get("arm_id")) or {}
    verification = _mapping(bundle.get("identity_verification")) or {}
    surface = _mapping(bundle.get("surface_evidence")) or {}
    return (
        arm.get("identity_status") == "verified"
        and verification.get("artifact") == "verified"
        and verification.get("installed_read_back") == "verified"
        and verification.get("run_identity") == "verified"
        and verification.get("surface") == "verified"
        and surface.get("status") == "verified"
        and surface.get("surface_id") == manifest.get("surface")
    )


def _bundle_evidence_ids(bundle: Mapping[str, Any], field: str) -> set[str]:
    identities: set[str] = set()
    for record_value in _sequence(bundle.get("runs")) or ():
        record = _mapping(record_value) or {}
        for identity_value in _sequence(record.get(field)) or ():
            identity = _mapping(identity_value)
            if identity and _is_text(identity.get("identity_id")):
                identities.add(str(identity["identity_id"]))
    return identities


def compare_arms(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare isolated arms using the manifest's exact release margins."""

    errors = [f"baseline: {error}" for error in validate_run_bundle(baseline, manifest)]
    errors.extend(f"candidate: {error}" for error in validate_run_bundle(candidate, manifest))
    if _bundle_evidence_ids(baseline, "raw_evidence_refs") & _bundle_evidence_ids(candidate, "raw_evidence_refs"):
        errors.append("cross-arm primary raw evidence identity reuse detected")
    if _bundle_evidence_ids(baseline, "grader_evidence_refs") & _bundle_evidence_ids(candidate, "grader_evidence_refs"):
        errors.append("cross-arm independent grader evidence identity reuse detected")
    if errors:
        return _invalid_comparison(errors)
    if baseline.get("arm_id") == candidate.get("arm_id"):
        errors.append("comparison requires distinct baseline and candidate arms")
    baseline_isolation = _mapping(baseline.get("isolation")) or {}
    candidate_isolation = _mapping(candidate.get("isolation")) or {}
    for field in ("task_fingerprint", "cache_fingerprint", "registry_fingerprint", "ledger_fingerprint", "environment_evidence_id"):
        if baseline_isolation.get(field) == candidate_isolation.get(field):
            errors.append(f"cross-arm {field.replace('_fingerprint', '').replace('_', ' ')} reuse or leakage detected")
    baseline_runs = list(_sequence(baseline.get("runs")) or ())
    candidate_runs = list(_sequence(candidate.get("runs")) or ())
    pairs = _paired_records(baseline_runs, candidate_runs)
    if not pairs or len(pairs) != len(baseline_runs) or len(pairs) != len(candidate_runs):
        errors.append("baseline and candidate must use unchanged scenarios and equal run counts")
    if set(record.get("run_id") for record in baseline_runs) & set(record.get("run_id") for record in candidate_runs):
        errors.append("cross-arm raw result ID reuse detected")
    contract_fields = (
        "category",
        "run_kind",
        "expected_route",
        "expected_question_count",
        "expected_spawn_count",
        "prohibited_behaviors",
    )
    for baseline_record, candidate_record in pairs:
        if any(baseline_record.get(field) != candidate_record.get(field) for field in contract_fields):
            errors.append(
                f"case contract drift detected for scenario {baseline_record.get('scenario_id')} "
                f"replicate {baseline_record.get('replicate_id')}"
            )
    if errors:
        return _invalid_comparison(errors)

    margins = manifest["margins"]
    differences = [float(candidate_record["quality"]) - float(baseline_record["quality"]) for baseline_record, candidate_record in pairs]
    quality_difference = statistics.fmean(differences)
    seed = int(manifest["randomization"]["seed"])
    lower, upper = _bootstrap_interval(differences, seed)
    noninferiority_margin = float(margins["quality_noninferiority"])
    if quality_difference < -noninferiority_margin - 1e-12 or upper < -noninferiority_margin:
        quality_status = "fail"
    elif lower >= -noninferiority_margin:
        quality_status = "pass"
    else:
        quality_status = "inconclusive"
    quality_claim = "improvement" if lower > 0 else ("non-inferior" if quality_status == "pass" else quality_status)

    simple = {
        metric: _simple_metric_gate(pairs, metric, float(margins["simple_task_cost_latency"]))
        for metric in ("cost", "latency")
    }
    high_value = _high_value_gate(
        pairs,
        float(margins["high_value_quality_gain"]),
        float(margins["high_value_critical_path_reduction"]),
        quality_status == "pass",
    )
    baseline_summary = summarize_arm(baseline_runs)
    candidate_summary = summarize_arm(candidate_runs)
    rate_failures = {
        "unnecessary_spawn": candidate_summary["unnecessary_spawn_rate"]
        > min(baseline_summary["unnecessary_spawn_rate"], float(margins["unnecessary_spawn_rate_max"])) + 1e-12,
        "premise_reset": candidate_summary["premise_reset_rate"] > baseline_summary["premise_reset_rate"] + 1e-12,
        "repeated_settled_question": candidate_summary["repeated_settled_question_rate"]
        > baseline_summary["repeated_settled_question_rate"] + 1e-12,
    }
    safety_failure = any(
        not candidate_record.get(field)
        for candidate_record in candidate_runs
        for field in ("safety_authority_pass", "budget_truthfulness_pass", "failure_visibility_pass")
    ) or any(candidate_record.get("unsafe_failures") for candidate_record in candidate_runs)
    behavioral_failure = any(candidate_record.get("passed") is not True for candidate_record in candidate_runs)
    unexplained_quality_drop = quality_difference < 0 and not all(
        _is_text(candidate_record.get("quality_regression_explanation")) for _, candidate_record in pairs
    )
    failure = (
        quality_status == "fail"
        or any(value["status"] == "fail" for value in simple.values())
        or high_value["status"] == "fail"
        or any(rate_failures.values())
        or safety_failure
        or behavioral_failure
        or unexplained_quality_drop
    )
    if not (_bundle_verified(baseline, manifest) and _bundle_verified(candidate, manifest)):
        status = "unverified"
    elif failure:
        status = "fail"
    elif quality_status == "inconclusive":
        status = "inconclusive"
    else:
        status = "pass"
    return {
        "status": status,
        "errors": [],
        "baseline": baseline_summary,
        "candidate": candidate_summary,
        "quality_difference": round(quality_difference, 6),
        "confidence_interval": {"level": 0.95, "lower": lower, "upper": upper, "method": "paired-bootstrap"},
        "quality_noninferiority": {
            "status": quality_status,
            "margin": noninferiority_margin,
            "claim": quality_claim,
            "unexplained_decrease": unexplained_quality_drop,
        },
        "simple_tasks": simple,
        "high_value_delegation": high_value,
        "rate_regressions": rate_failures,
        "safety_failure": safety_failure,
        "behavioral_failure": behavioral_failure,
    }


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
