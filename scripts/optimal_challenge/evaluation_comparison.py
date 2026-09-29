"""Compare isolated behavioral arms under fixed acceptance margins."""
from __future__ import annotations
import math
import statistics
from collections.abc import Mapping, Sequence
from typing import Any
from .evaluation_contracts import _arm, _mapping, _sequence, _is_text, validate_run_bundle
from .evaluation_statistics import (
    summarize_arm, _paired_records, _bootstrap_interval, _simple_metric_gate,
    _high_value_gate, _invalid_comparison, _rate,
)

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
        metric: _simple_metric_gate(
            pairs,
            metric,
            float(margins["simple_task_cost_latency"]),
            seed + index + 10,
        )
        for index, metric in enumerate(("cost", "latency"))
    }
    high_value = _high_value_gate(
        pairs,
        float(margins["high_value_quality_gain"]),
        float(margins["high_value_critical_path_reduction"]),
        quality_status == "pass",
        seed + 20,
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
    statistical_inconclusive = any(value["status"] == "inconclusive" for value in simple.values()) or high_value["status"] == "inconclusive"
    if not (_bundle_verified(baseline, manifest) and _bundle_verified(candidate, manifest)):
        status = "unverified"
    elif failure:
        status = "fail"
    elif quality_status == "inconclusive" or statistical_inconclusive:
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
