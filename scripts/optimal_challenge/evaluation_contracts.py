"""Manifest, identity, evidence, and recorded-run contracts.

Recorded host runs are required; static expected labels do not prove behavior.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from .evaluation_semantics import PROFILE_WEIGHTS, REVIEW_MARGINS, _compute_semantic_result


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
ROOT = Path(__file__).resolve().parents[2]
CANONICAL_FILES = {
    ("prompt_hashes", "router"): ROOT / "skills" / "optimal-challenge" / "SKILL.md",
    ("prompt_hashes", "question_bundle"): ROOT / "skills" / "optimal-challenge" / "templates" / "QUESTION-BUNDLE.md",
    ("fixture_hashes", "behavioral_acceptance"): ROOT / "tests" / "behavioral-acceptance.json",
    ("fixture_hashes", "team_routing"): ROOT / "tests" / "team-routing.json",
    (None, "config_sha256"): ROOT / "config" / "orchestration.json",
}
APPROVED_BEHAVIORAL_FIXTURE_VERSION = 2
APPROVED_BEHAVIORAL_FIXTURE_SHA256 = "a4dea28161fc5a593fda9ee9af5686750c337fae849daaf4262fd15ff5fb290e"
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
    if not isinstance(value,(int,float)) or isinstance(value,bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


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
        if field == "behavioral_acceptance" and actual != APPROVED_BEHAVIORAL_FIXTURE_SHA256:
            errors.append(
                "canonical behavioral_acceptance differs from the independently approved behavioral fixture "
                f"v{APPROVED_BEHAVIORAL_FIXTURE_VERSION}"
            )
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
        elif kind == "nullable_integer":
            if item is not None and (not isinstance(item, int) or isinstance(item, bool)):
                errors.append(f"{path} input {field} must be null or an integer")
            elif item is not None and (item < int(schema.get("minimum", 0)) or item > int(schema.get("maximum", 100))):
                errors.append(f"{path} input {field} is outside the canonical integer range")
        elif kind == "nullable_number":
            if item is not None and not _is_number(item):
                errors.append(f"{path} input {field} must be null or a finite number")
            elif item is not None and (float(item) < float(schema.get("minimum", -math.inf)) or float(item) > float(schema.get("maximum", math.inf))):
                errors.append(f"{path} input {field} is outside the canonical range")
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
        if calculation.get("inputs") != semantic.get("canonical_inputs"):
            errors.append(f"{path} calculation inputs must exactly match canonical per-case inputs")
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
    if semantic is not None and _mapping(semantic.get("expected")) is not None:
        if semantic["expected"].get("specialist_count") != expected_spawn:
            errors.append(f"{path} semantic specialist count differs from acceptance contract")
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
    arm_contract = (_mapping(case.get("arm_expectations")) or {}).get(arm_id, {})
    route_required = arm_contract.get("route_required", True)
    if route_required and record.get("observed_route") != case.get("expected_route") and not failed:
        errors.append(f"{path} route does not match acceptance contract")
    proxies = _mapping(record.get("proxies"))
    if proxies is None:
        errors.append(f"{path}.proxies must be an object")
    else:
        for field in ("model_calls", "spawn_count", "tool_calls", "question_count"):
            value = proxies.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"{path}.proxies.{field} must be a non-negative integer")
        if route_required and not failed and proxies.get("spawn_count") != case.get("expected_spawn_count"):
            errors.append(f"{path} spawn count does not match acceptance contract")
        if route_required and not failed and proxies.get("question_count") != case.get("expected_question_count"):
            errors.append(f"{path} question count does not match acceptance contract")
    prohibited = _sequence(record.get("prohibited_behaviors"))
    observed = _sequence(record.get("observed_behaviors"))
    if prohibited is None or observed is None or any(not _is_text(item) for item in prohibited) or any(not _is_text(item) for item in observed):
        errors.append(f"{path} prohibited and observed behaviors must be arrays of non-empty strings")
    elif route_required and set(prohibited) & set(observed) and not failed:
        errors.append(f"{path} prohibited behavior observed")
    for metric in ("cost", "latency", "critical_path"):
        _validate_measurement(record.get(metric), f"{path}.{metric}", errors)
    for field in ("unnecessary_spawn", "premise_reset", "repeated_settled_question"):
        if not isinstance(record.get(field), bool):
            errors.append(f"{path}.{field} must be boolean")
    if route_required:
        _validate_question(record, case, arm_id, path, errors)
    if arm_contract.get("semantic_required", True):
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
