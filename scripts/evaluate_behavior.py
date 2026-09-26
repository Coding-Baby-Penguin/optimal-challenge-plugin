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
from collections import Counter, defaultdict
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


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_sha256(value: Any) -> bool:
    return _is_text(value) and len(value) == SHA256_LENGTH and all(char in "0123456789abcdef" for char in value)


def _manifest_digest(manifest: Mapping[str, Any]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
    }
    for field in sorted(required - set(manifest)):
        errors.append(f"manifest.{field} is required")
    for group in ("prompt_hashes", "fixture_hashes"):
        values = _mapping(manifest.get(group))
        if not values:
            errors.append(f"manifest.{group} must be a non-empty object")
        elif any(not _is_sha256(value) for value in values.values()):
            errors.append(f"manifest.{group} values must be lowercase SHA-256 hashes")
    if not _is_sha256(manifest.get("config_sha256")):
        errors.append("manifest.config_sha256 must be a lowercase SHA-256 hash")
    for field in ("host", "surface", "model", "reasoning", "profile", "evaluator_version", "rubric_version"):
        if not _is_text(manifest.get(field)):
            errors.append(f"manifest.{field} must be a non-empty string")
    tools = _sequence(manifest.get("tool_set"))
    if not tools or any(not _is_text(tool) for tool in tools) or len(set(tools)) != len(tools):
        errors.append("manifest.tool_set must contain unique non-empty strings")
    minimum = manifest.get("minimum_run_count")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 5:
        errors.append("manifest.minimum_run_count must be an integer of at least 5")
    randomization = _mapping(manifest.get("randomization"))
    if not randomization or not _is_text(randomization.get("method")) or not isinstance(randomization.get("seed"), int):
        errors.append("manifest.randomization requires method and integer seed")
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


def validate_run_bundle(bundle: Mapping[str, Any], manifest: Mapping[str, Any]) -> list[str]:
    """Return actionable errors for a recorded arm, failing closed on drift."""

    errors = _manifest_errors(manifest)
    if not isinstance(bundle, Mapping):
        return errors + ["bundle must be an object"]
    arm_id = bundle.get("arm_id")
    expected_arm = _arm(manifest, arm_id)
    if expected_arm is None:
        errors.append("bundle.arm_id is not defined by manifest arms")
    for field in PINNED_FIELDS:
        if bundle.get(field) != manifest.get(field):
            errors.append(f"bundle.{field} differs from the pinned manifest")
    if not _is_sha256(bundle.get("manifest_sha256")):
        errors.append("bundle.manifest_sha256 must be a lowercase SHA-256 hash")
    elif bundle.get("manifest_sha256") != _manifest_digest(manifest):
        errors.append("bundle.manifest_sha256 does not identify the supplied manifest")

    selected_subject = _mapping(bundle.get("subject"))
    if selected_subject is None:
        errors.append("bundle.subject is required")
    elif expected_arm is not None:
        if selected_subject.get("arm_id") != arm_id:
            errors.append("bundle.subject.arm_id must match bundle.arm_id")
        for field in IDENTITY_FIELDS:
            if selected_subject.get(field) != expected_arm.get(field):
                errors.append(f"bundle.subject {field} does not match pinned plugin identity")
        if selected_subject.get("policy_overrides") != expected_arm.get("policy_overrides"):
            errors.append("bundle.subject arm policy does not match the pinned ablation")
        if bundle.get("arm_policy") != expected_arm.get("policy_overrides"):
            errors.append("bundle.arm_policy does not match the pinned arm policy")
        if not _is_sha256(selected_subject.get("archive_sha256")):
            errors.append("bundle.subject archive must be a lowercase SHA-256 hash")
        expected_read_back = _mapping(expected_arm.get("installed_plugin_read_back"))
        read_back = _mapping(selected_subject.get("installed_plugin_read_back"))
        if read_back is None:
            errors.append("bundle.subject installed plugin read-back is required")
        elif expected_read_back is not None:
            for field in ("name", "version", "cachebuster", "archive_sha256"):
                if read_back.get(field) != expected_read_back.get(field):
                    label = "plugin version" if field == "version" else field
                    errors.append(f"bundle.subject installed {label} read-back mismatch")

    isolation = _mapping(bundle.get("isolation"))
    if isolation is None:
        errors.append("bundle.isolation is required")
    else:
        for field, label in (
            ("fresh_task", "task"),
            ("cache_cleared", "cache"),
            ("fresh_registry", "registry"),
            ("fresh_ledger", "ledger"),
        ):
            if isolation.get(field) is not True:
                errors.append(f"bundle isolation {label} requirement failed")
        if isolation.get("prior_arm_state_detected") is not False:
            errors.append("bundle isolation ledger/cache prior-arm state leakage detected")
        if isolation.get("config_fingerprint") != manifest.get("config_sha256"):
            errors.append("bundle isolation config fingerprint mismatch")
        for field in ("registry_fingerprint", "ledger_fingerprint"):
            if not _is_text(isolation.get(field)):
                errors.append(f"bundle.isolation.{field} is required")

    runs = _sequence(bundle.get("runs"))
    if runs is None:
        errors.append("bundle.runs must be an array")
        runs = ()
    minimum = manifest.get("minimum_run_count")
    if isinstance(minimum, int) and len(runs) < minimum:
        errors.append(f"bundle.runs does not meet minimum run count {minimum}")
    if bundle.get("run_count") != len(runs):
        errors.append("bundle.run_count must equal the recorded run count")
    execution_order = _sequence(bundle.get("execution_order"))
    if execution_order is None or list(execution_order) != list(range(1, len(runs) + 1)):
        errors.append("bundle.execution_order must enumerate every recorded run exactly once")

    run_ids: list[Any] = []
    replicate_keys: list[tuple[str, int]] = []
    run_kinds_by_scenario: dict[str, list[str]] = defaultdict(list)
    for index, run_value in enumerate(runs):
        path = f"bundle.runs[{index}]"
        record = _mapping(run_value)
        if record is None:
            errors.append(f"{path} must be an object")
            continue
        run_id = record.get("run_id")
        if not _is_text(run_id):
            errors.append(f"{path}.run_id must be a non-empty string")
        else:
            run_ids.append(run_id)
        replicate_id = record.get("replicate_id")
        if not isinstance(replicate_id, int) or isinstance(replicate_id, bool) or replicate_id < 0:
            errors.append(f"{path}.replicate_id must be a non-negative integer")
        elif _is_text(record.get("scenario_id")):
            replicate_keys.append((str(record["scenario_id"]), replicate_id))
        for field in ("scenario_id", "category", "expected_route", "observed_route"):
            if not _is_text(record.get(field)):
                errors.append(f"{path}.{field} must be a non-empty string")
        run_kind = record.get("run_kind")
        if run_kind not in {"deterministic", "stochastic"}:
            errors.append(f"{path}.run_kind must be deterministic or stochastic")
        elif _is_text(record.get("scenario_id")):
            run_kinds_by_scenario[str(record["scenario_id"])].append(run_kind)
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
        behavior_failed = record.get("passed") is False
        if record.get("observed_route") != record.get("expected_route") and not behavior_failed:
            errors.append(f"{path} route does not match acceptance contract")
        proxies = _mapping(record.get("proxies"))
        if proxies is None:
            errors.append(f"{path}.proxies must be an object")
        else:
            for field in ("model_calls", "spawn_count", "tool_calls", "question_count"):
                value = proxies.get(field)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    errors.append(f"{path}.proxies.{field} must be a non-negative integer")
            if proxies.get("spawn_count") != record.get("expected_spawn_count") and not behavior_failed:
                errors.append(f"{path} spawn count does not match acceptance contract")
            if proxies.get("question_count") != record.get("expected_question_count") and not behavior_failed:
                errors.append(f"{path} question count does not match acceptance contract")
        prohibited = _sequence(record.get("prohibited_behaviors"))
        observed = _sequence(record.get("observed_behaviors"))
        if (
            prohibited is None
            or observed is None
            or any(not _is_text(item) for item in prohibited)
            or any(not _is_text(item) for item in observed)
        ):
            errors.append(f"{path} prohibited and observed behaviors must be arrays of non-empty strings")
        else:
            violations = sorted(set(prohibited) & set(observed))
            if violations and not behavior_failed:
                errors.append(f"{path} prohibited behavior observed: {', '.join(violations)}")
        evidence = _sequence(record.get("evidence_refs"))
        if not evidence or any(not _is_text(item) for item in evidence):
            errors.append(f"{path} evidence refs must contain at least one reference")
        for metric in ("cost", "latency", "critical_path"):
            _validate_measurement(record.get(metric), f"{path}.{metric}", errors)
        for field in ("unnecessary_spawn", "premise_reset", "repeated_settled_question"):
            if not isinstance(record.get(field), bool):
                errors.append(f"{path}.{field} must be boolean")
    counts = Counter(run_ids)
    if any(count > 1 for count in counts.values()):
        errors.append("bundle.runs contains duplicate run_id values")
    if len(set(replicate_keys)) != len(replicate_keys):
        errors.append("bundle.runs contains duplicate scenario/replicate identities")
    if isinstance(minimum, int):
        for scenario_id, kinds in sorted(run_kinds_by_scenario.items()):
            if len(set(kinds)) != 1:
                errors.append(f"bundle scenario {scenario_id} mixes deterministic and stochastic runs")
            elif kinds[0] == "stochastic" and len(kinds) < minimum:
                errors.append(
                    f"bundle requires at least {minimum} runs per stochastic scenario; {scenario_id} has {len(kinds)}"
                )
            elif kinds[0] == "deterministic" and len(kinds) != 1:
                errors.append(f"bundle deterministic scenario {scenario_id} must run exactly once")
    return errors


def _measured_values(runs: Sequence[Mapping[str, Any]], metric: str) -> list[float]:
    values: list[float] = []
    for record in runs:
        measurement = _mapping(record.get(metric))
        if measurement and measurement.get("provenance") in {"observed", "estimated"} and _is_number(measurement.get("value")):
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
    return {
        "run_count": len(records),
        "mean_quality": round(statistics.fmean(qualities), 6) if qualities else None,
        "median_cost": round(statistics.median(costs), 6) if costs else None,
        "median_latency": round(statistics.median(latencies), 6) if latencies else None,
        "pass_rate": round(sum(record.get("passed") is True for record in records) / len(records), 6) if records else 0.0,
        "proxy_only": proxy_only,
        "cost_claim": "unavailable" if not costs else "measured",
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
    selected = [pair for pair in pairs if pair[0].get("category") == "high-value-delegation"]
    if not selected:
        return {"status": "not-applicable", "quality_gain": None, "critical_path_reduction": None}
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


def compare_arms(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare isolated arms using the manifest's exact release margins."""

    errors = [f"baseline: {error}" for error in validate_run_bundle(baseline, manifest)]
    errors.extend(f"candidate: {error}" for error in validate_run_bundle(candidate, manifest))
    if baseline.get("arm_id") == candidate.get("arm_id"):
        errors.append("comparison requires distinct baseline and candidate arms")
    baseline_isolation = _mapping(baseline.get("isolation")) or {}
    candidate_isolation = _mapping(candidate.get("isolation")) or {}
    for field in ("registry_fingerprint", "ledger_fingerprint"):
        if baseline_isolation.get(field) == candidate_isolation.get(field):
            errors.append(f"cross-arm {field.replace('_fingerprint', '')} leakage detected")
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
    if failure:
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
    if result["status"] == "inconclusive":
        print("BEHAVIORAL EVALUATION INCONCLUSIVE")
        return 2
    print("BEHAVIORAL EVALUATION FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
