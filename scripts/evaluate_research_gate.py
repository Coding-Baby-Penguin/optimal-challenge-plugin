#!/usr/bin/env python3
"""Fail-closed research-before-scale contract with identity-attested evidence."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
import weakref


ROUTES = {"direct", "research", "pilot", "scale", "blocked-question", "provisional-pilot"}
CLAIMS = {"acceptance-ready", "full-scale", "durable-cloud-persistence", "budget-enforcement"}
RESULT_KEYS = {"route", "research_stop_met", "maximum_output", "reasons", "required_artifacts", "prohibited_claims"}
EXPECTED_KEYS = RESULT_KEYS - {"reasons"}
HASH_FIELDS = {"rubric_hash", "criteria_fingerprint", "input_fingerprint", "scope_fingerprint", "risk_fingerprint"}
CASE_KEYS = {
    "id", "description", "costly_scale", "pressure_to_skip", "deliverable_scope",
    *HASH_FIELDS, "material_risk_dimensions", "required_criterion_ids", "criteria_evidence_refs",
    "contradictions", "pilot_evidence_ref", "settled_decision_id", "refusal",
    "task_override_only", "capability_evidence", "claims_requested", "expected",
}
CONTRADICTION_KEYS = {
    "id", "material", "user_only", "resolution_fingerprint", "resolution_evidence_refs",
    "decision_id", "question_bundle",
}
REGISTRY_KEYS = {
    "schema_version", "registry_id", "provenance", "verified_at", "expires_at",
    "criteria_evidence", "resolution_evidence", "decision_records", "pilot_evidence",
}
# Independent code pin. Refresh only after fixture schema review and semantic tests.
EXPECTED_FIXTURE_SHA256 = "92ce28d7bbfc55abaf7661cc4e85cc4ca7ea2cde852f02cf0da8c81e00952902"
_ATTESTATION = object()
_ISSUED_CONTEXTS: dict[int, tuple[weakref.ReferenceType[Any], str]] = {}


@dataclass(frozen=True, slots=True, weakref_slot=True)
class TrustedResearchEvidenceContext:
    """Process-issued evidence context; serialized data alone cannot recreate trust."""

    registry_id: str
    provenance: str
    payload_json: str
    _attestation: object | None = None


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _context_digest(context: TrustedResearchEvidenceContext) -> str:
    return _sha(json.dumps({"registry_id": context.registry_id, "provenance": context.provenance, "payload_json": context.payload_json}, sort_keys=True, separators=(",", ":")))


def _register(context: TrustedResearchEvidenceContext) -> TrustedResearchEvidenceContext:
    identifier = id(context)
    _ISSUED_CONTEXTS[identifier] = (weakref.ref(context, lambda _ref, key=identifier: _ISSUED_CONTEXTS.pop(key, None)), _context_digest(context))
    return context


def _context_error(context: Any) -> str | None:
    if not isinstance(context, TrustedResearchEvidenceContext) or context._attestation is not _ATTESTATION:
        return "trusted-evidence-context-required"
    issued = _ISSUED_CONTEXTS.get(id(context))
    if issued is None or issued[0]() is not context:
        return "trusted-evidence-context-not-issued"
    if issued[1] != _context_digest(context):
        return "trusted-evidence-context-digest-mismatch"
    return None


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _hex64(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("evidence timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _current(record: Mapping[str, Any], now: datetime) -> bool:
    try:
        return _time(str(record["verified_at"])) <= now <= _time(str(record["expires_at"])) and record.get("status", "current") == "current"
    except (KeyError, TypeError, ValueError):
        return False


def _validate_registry(payload: Any) -> None:
    if not isinstance(payload, Mapping) or set(payload) != REGISTRY_KEYS:
        raise ValueError("trusted evidence registry schema mismatch")
    if payload["schema_version"] != 1 or payload["provenance"] != "structural-fixture" or not _nonblank(payload["registry_id"]):
        raise ValueError("trusted evidence registry metadata mismatch")
    _time(payload["verified_at"]); _time(payload["expires_at"])
    for collection in ("criteria_evidence", "resolution_evidence", "decision_records", "pilot_evidence"):
        records = payload[collection]
        if not isinstance(records, list) or any(not isinstance(item, Mapping) for item in records):
            raise ValueError(f"trusted evidence registry {collection} must be a record list")
        ids = [item.get("id") for item in records]
        if any(not _nonblank(item) for item in ids) or len(ids) != len(set(ids)):
            raise ValueError(f"trusted evidence registry {collection} has invalid IDs")


def load_fixture_evidence_context(path: Path) -> TrustedResearchEvidenceContext:
    raw = path.read_bytes()
    normalized = raw.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
    if hashlib.sha256(normalized).hexdigest() != EXPECTED_FIXTURE_SHA256:
        raise ValueError("trusted evidence fixture digest does not match independent code pin")
    payload = json.loads(normalized.decode("utf-8"))
    _validate_registry(payload)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _register(TrustedResearchEvidenceContext(payload["registry_id"], payload["provenance"], canonical, _ATTESTATION))


def _case_errors(case: Any, *, include_expected: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(case, Mapping):
        return ["$ must be an object"]
    unknown, missing = set(case) - CASE_KEYS, CASE_KEYS - set(case)
    if unknown: errors.append(f"$ has unknown keys: {sorted(unknown)}")
    if missing: errors.append(f"$ is missing keys: {sorted(missing)}")
    if errors: return errors
    for field in ("id", "description", "deliverable_scope"):
        if not _nonblank(case[field]): errors.append(f"$.{field} must be non-empty")
    for field in ("costly_scale", "pressure_to_skip", "task_override_only"):
        if type(case[field]) is not bool: errors.append(f"$.{field} must be boolean")
    for field in HASH_FIELDS:
        if not _hex64(case[field]): errors.append(f"$.{field} must be a lowercase SHA-256")
    for field in ("material_risk_dimensions", "required_criterion_ids", "criteria_evidence_refs"):
        value = case[field]
        if not isinstance(value, list) or any(not _nonblank(item) for item in value) or len(value) != len(set(value)):
            errors.append(f"$.{field} must be a unique list of non-empty strings")
    if case["costly_scale"] and not case["material_risk_dimensions"]:
        errors.append("$.material_risk_dimensions required for costly scale")
    contradictions = case["contradictions"]
    if not isinstance(contradictions, list): errors.append("$.contradictions must be a list")
    else:
        for index, item in enumerate(contradictions):
            path = f"$.contradictions[{index}]"
            if not isinstance(item, Mapping) or set(item) != CONTRADICTION_KEYS:
                errors.append(f"{path} has invalid shape"); continue
            if not _nonblank(item["id"]) or type(item["material"]) is not bool or type(item["user_only"]) is not bool:
                errors.append(f"{path} identity/classification invalid")
            if not _hex64(item["resolution_fingerprint"]): errors.append(f"{path}.resolution_fingerprint invalid")
            if not isinstance(item["resolution_evidence_refs"], list): errors.append(f"{path}.resolution_evidence_refs must be list")
            if item["decision_id"] is not None and not _nonblank(item["decision_id"]): errors.append(f"{path}.decision_id invalid")
            if item["user_only"] and item["resolution_evidence_refs"]: errors.append(f"{path} user-only conflict cannot use authority resolution evidence")
            if not item["user_only"] and item["decision_id"] is not None: errors.append(f"{path} authority conflict cannot use a user decision")
            bundle = item["question_bundle"]
            if bundle is not None and (not isinstance(bundle, Mapping) or set(bundle) != {"recommendation", "impact", "safe_work", "next_step"} or any(not _nonblank(v) for v in bundle.values())):
                errors.append(f"{path}.question_bundle invalid")
            if bundle is not None and (not item["material"] or not item["user_only"] or item["decision_id"] is not None):
                errors.append(f"{path}.question_bundle conflicts with resolved/nonblocking state")
    for field in ("pilot_evidence_ref", "settled_decision_id"):
        if case[field] is not None and not _nonblank(case[field]): errors.append(f"$.{field} invalid")
    for field, keys in (("refusal", {"research", "pilot"}), ("capability_evidence", {"durable_cloud_persistence", "budget_enforcement"})):
        value = case[field]
        if not isinstance(value, Mapping) or set(value) != keys or any(type(value[key]) is not bool for key in keys): errors.append(f"$.{field} invalid")
    if not isinstance(case["claims_requested"], list) or any(item not in CLAIMS for item in case["claims_requested"]): errors.append("$.claims_requested invalid")
    if include_expected:
        expected = case["expected"]
        if not isinstance(expected, Mapping) or set(expected) != EXPECTED_KEYS: errors.append("$.expected invalid")
    return errors


def _result(route: str, stop: bool, maximum: str, reasons: list[str], artifacts: list[str], prohibited: set[str]) -> dict[str, Any]:
    return {"route": route, "research_stop_met": stop, "maximum_output": maximum, "reasons": reasons, "required_artifacts": artifacts, "prohibited_claims": sorted(prohibited)}


def _malformed(reasons: list[str]) -> dict[str, Any]:
    return _result("blocked-question", False, "preparatory-only", ["malformed-input", *reasons], ["corrected-research-gate-input"], {"acceptance-ready", "full-scale"})


def _bindings_match(record: Mapping[str, Any], case: Mapping[str, Any]) -> bool:
    return record.get("deliverable_scope") == case["deliverable_scope"] and all(record.get(field) == case[field] for field in HASH_FIELDS)


def evaluate_case(case: Any, evidence_context: TrustedResearchEvidenceContext | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    errors = _case_errors(case)
    if errors: return _malformed(errors)
    assert isinstance(case, Mapping)
    prohibited = {"acceptance-ready", "full-scale"} if case["costly_scale"] else set()
    claims, capabilities = set(case["claims_requested"]), case["capability_evidence"]
    if "durable-cloud-persistence" in claims and (case["task_override_only"] or not capabilities["durable_cloud_persistence"]): prohibited.add("durable-cloud-persistence")
    if "budget-enforcement" in claims and (case["task_override_only"] or not capabilities["budget_enforcement"]): prohibited.add("budget-enforcement")
    if not case["costly_scale"]:
        return _result("direct", False, "requested-output", ["low-cost-reversible-direct"], [], prohibited)
    context_error = _context_error(evidence_context)
    if context_error: return _malformed([context_error])
    assert isinstance(evidence_context, TrustedResearchEvidenceContext)
    registry = json.loads(evidence_context.payload_json)
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reasons = ["skip-pressure-does-not-waive-gate"] if case["pressure_to_skip"] else []
    if case["refusal"]["research"] or case["refusal"]["pilot"]:
        return _result("provisional-pilot", False, "smallest-adequate-pilot", reasons + ["refusal-bounds-output-to-provisional-pilot"], ["provisional-label"], prohibited)

    criteria_by_id = {item["id"]: item for item in registry["criteria_evidence"]}
    valid_criteria = []
    for ref in case["criteria_evidence_refs"]:
        item = criteria_by_id.get(ref)
        if item and _current(item, current_time) and item.get("deliverable_scope") == case["deliverable_scope"] and item.get("criteria_fingerprint") == case["criteria_fingerprint"] and item.get("scope_fingerprint") == case["scope_fingerprint"] and _nonblank(item.get("source_authority")) and _nonblank(item.get("source_version")) and _nonblank(item.get("provenance")):
            valid_criteria.append(item)
    if set(case["required_criterion_ids"]) - {item.get("criterion_id") for item in valid_criteria}:
        return _result("research", False, "preparatory-only", reasons + ["trusted-current-criteria-required"], ["acceptance-rubric"], prohibited)

    resolutions = {item["id"]: item for item in registry["resolution_evidence"]}
    decisions = {item["id"]: item for item in registry["decision_records"]}
    disclosed = False
    unresolved_user_only: list[Mapping[str, Any]] = []
    for conflict in case["contradictions"]:
        if not conflict["material"]:
            disclosed = True; continue
        if conflict["user_only"]:
            decision = decisions.get(conflict["decision_id"])
            valid = bool(decision and decision.get("kind") == "conflict-resolution" and decision.get("conflict_id") == conflict["id"] and decision.get("resolution_fingerprint") == conflict["resolution_fingerprint"] and _current(decision, current_time) and _bindings_match(decision, case))
            if not valid:
                if conflict["decision_id"] is not None: return _result("blocked-question", False, "preparatory-only", reasons + ["untrusted-or-mismatched-decision-record"], ["trusted-decision-record"], prohibited)
                unresolved_user_only.append(conflict)
        else:
            valid = False
            for ref in conflict["resolution_evidence_refs"]:
                record = resolutions.get(ref)
                if record and record.get("conflict_id") == conflict["id"] and record.get("resolution_fingerprint") == conflict["resolution_fingerprint"] and record.get("method") in {"authority-precedence", "freshness", "applicability"} and _current(record, current_time) and _bindings_match(record, case) and set(record.get("criteria_evidence_refs", [])) <= {item["id"] for item in valid_criteria}:
                    valid = True
            if not valid:
                return _result("research", False, "preparatory-only", reasons + ["material-contradiction-requires-trusted-resolution"], ["acceptance-rubric"], prohibited)
    if unresolved_user_only:
        bundles = [item["question_bundle"] for item in unresolved_user_only if item["question_bundle"] is not None]
        if len(bundles) != 1:
            return _malformed(["material user-only conflicts require exactly one combined question bundle"])
        return _result("blocked-question", True, "preparatory-only", reasons + ["material-conflict-converted-to-blocking-user-decision"], ["question-bundle"], prohibited)
    if disclosed: reasons.append("disclose-nonmaterial-contradiction")

    if case["pilot_evidence_ref"] is None:
        return _result("pilot", True, "smallest-adequate-pilot", reasons + ["risk-representative-pilot-required"], ["risk-representative-pilot"], prohibited)
    pilots = {item["id"]: item for item in registry["pilot_evidence"]}
    pilot, decision = pilots.get(case["pilot_evidence_ref"]), decisions.get(case["settled_decision_id"])
    valid_decision = bool(decision and decision.get("kind") == "pilot-approval" and _current(decision, current_time) and _bindings_match(decision, case))
    valid_pilot = bool(pilot and valid_decision and pilot.get("decision_id") == case["settled_decision_id"] and _current(pilot, current_time) and _bindings_match(pilot, case) and pilot.get("validation_outcome") == "passed" and _nonblank(pilot.get("artifact_id")) and _nonblank(pilot.get("result_id")) and set(case["material_risk_dimensions"]) <= set(pilot.get("covered_risk_dimensions", [])))
    if not valid_pilot:
        return _result("pilot", True, "smallest-adequate-pilot", reasons + ["trusted-bound-pilot-evidence-required"], ["risk-representative-pilot"], prohibited)
    return _result("scale", True, "full-scale", reasons + ["trusted-bound-representative-pilot-passed"], [], prohibited - {"acceptance-ready", "full-scale"})


def validate_manifest(path: Path, *, evidence_context: TrustedResearchEvidenceContext, evaluator: Callable[..., Mapping[str, Any]] = evaluate_case) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload: raise ValueError("research-gate manifest must be a non-empty list")
    ids: set[str] = set()
    for index, case in enumerate(payload):
        errors = _case_errors(case, include_expected=True)
        if errors: raise ValueError(f"case {index}: {'; '.join(errors)}")
        if case["id"] in ids: raise ValueError(f"case {index}: duplicate id {case['id']}")
        ids.add(case["id"])
        actual = evaluator(case, evidence_context)
        if not isinstance(actual, Mapping) or set(actual) != RESULT_KEYS: raise ValueError(f"case {case['id']}: evaluator returned invalid contract")
        for field in EXPECTED_KEYS:
            if actual[field] != case["expected"][field]: raise ValueError(f"case {case['id']}: {field} mismatch: expected {case['expected'][field]!r}, got {actual[field]!r}")
    return len(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path, default=Path("tests/research-gate.json"))
    parser.add_argument("--evidence-registry", type=Path, default=Path("tests/fixtures/research/trusted-evidence.json"))
    args = parser.parse_args(argv)
    try:
        context = load_fixture_evidence_context(args.evidence_registry)
        count = validate_manifest(args.manifest, evidence_context=context)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"RESEARCH GATE VALIDATION FAILED: {exc}"); return 1
    print(f"RESEARCH GATE VALIDATION PASSED ({count} STRUCTURAL FIXTURE cases; NOT HOST EVIDENCE)"); return 0


if __name__ == "__main__":
    sys.exit(main())
