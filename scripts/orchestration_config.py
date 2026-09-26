#!/usr/bin/env python3
"""Load and validate provider-neutral orchestration policy configuration."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping


PROFILE_WEIGHTS: dict[str, dict[str, float]] = {
    "economy": {"quality": 0.35, "cost": 0.35, "latency": 0.10, "attention": 0.10, "rework": 0.10},
    "balanced": {"quality": 0.45, "cost": 0.20, "latency": 0.10, "attention": 0.10, "rework": 0.15},
    "quality": {"quality": 0.50, "cost": 0.10, "latency": 0.05, "attention": 0.10, "rework": 0.25},
}
PROFILE_DELEGATION_MARGINS: dict[str, int] = {
    "economy": 3,
    "balanced": 1,
    "quality": 1,
    "custom": 1,
}

BUILT_IN_DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "mode": "auto",
    "profile": "balanced",
    "objective_weights": PROFILE_WEIGHTS["balanced"],
    "team_limits": {
        "max_active_specialists": 3,
        "exact_specialists": None,
        "delegation_margin": 1,
        "allow_mode_margin_override": False,
        "retry_limit": 1,
        "capability_class": "standard",
    },
    "premise_gate": {
        "enabled": True,
        "apply_to_direct_fast_path": False,
        "risk_threshold": 4,
        "question_value_threshold": 0,
        "investigate_first": True,
        "use_reversible_defaults": True,
    },
    "verification": {
        "default_depth": "targeted",
        "review_margin": 3,
        "mandatory_independent_review": False,
        "compensating_oracle_requires_user_acceptance": True,
    },
    "persistence_privacy": {
        "runtime_state": "local",
        "state_directory": ".optimal-challenge",
        "persist_transcripts": False,
        "persist_sensitive_data": False,
    },
    "budget": {
        "unit": None,
        "limit": None,
        "measurement": "unavailable",
        "enforcement": "advisory",
        "measurement_source": None,
        "soft_threshold": None,
        "adapter_capabilities": {
            "observed_measurement": {"verified": False, "evidence_id": None},
            "local_stop": {"verified": False, "evidence_id": None},
            "provider_stop": {"verified": False, "evidence_id": None},
        },
    },
}

_ALLOWED_KEYS: dict[str, set[str]] = {
    "$": set(BUILT_IN_DEFAULTS),
    "$.objective_weights": {"quality", "cost", "latency", "attention", "rework"},
    "$.team_limits": set(BUILT_IN_DEFAULTS["team_limits"]),
    "$.premise_gate": set(BUILT_IN_DEFAULTS["premise_gate"]),
    "$.verification": set(BUILT_IN_DEFAULTS["verification"]),
    "$.persistence_privacy": set(BUILT_IN_DEFAULTS["persistence_privacy"]),
    "$.budget": set(BUILT_IN_DEFAULTS["budget"]),
    "$.budget.adapter_capabilities": {"observed_measurement", "local_stop", "provider_stop"},
    "$.budget.adapter_capabilities.observed_measurement": {"verified", "evidence_id"},
    "$.budget.adapter_capabilities.local_stop": {"verified", "evidence_id"},
    "$.budget.adapter_capabilities.provider_stop": {"verified", "evidence_id"},
}


def _merge_known(base: Mapping[str, Any], override: Mapping[str, Any], path: str) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in override.items():
        key_path = f"{path}.{key}"
        if key not in base:
            raise ValueError(f"{key_path}: unknown configuration key")
        base_value = base[key]
        if isinstance(base_value, Mapping):
            if not isinstance(value, Mapping):
                raise ValueError(f"{key_path}: expected an object")
            result[key] = _merge_known(base_value, value, key_path)
        else:
            result[key] = deepcopy(value)
    return result


def merge_known(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge an override, rejecting keys absent from the base shape."""
    if not isinstance(base, Mapping) or not isinstance(override, Mapping):
        raise TypeError("base and override must be mappings")
    return _merge_known(base, override, "$")


def _read_object(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: invalid configuration: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{path}: configuration root must be an object")
    return value


def _merge_layer(config: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    prepared = dict(override)
    selected_profile = prepared.get("profile")
    layer_base = config
    if isinstance(selected_profile, str) and selected_profile in PROFILE_DELEGATION_MARGINS:
        weights_profile = selected_profile if selected_profile in PROFILE_WEIGHTS else "balanced"
        layer_base = merge_known(
            config,
            {
                "objective_weights": PROFILE_WEIGHTS[weights_profile],
                "team_limits": {"delegation_margin": PROFILE_DELEGATION_MARGINS[selected_profile]},
            },
        )
    return merge_known(layer_base, prepared)


def _validated_candidate(
    config: Mapping[str, Any],
    source: str,
    detected_host_max: int | None,
) -> dict[str, Any]:
    candidate = deepcopy(dict(config))
    errors = validate_config(candidate, detected_host_max=detected_host_max)
    if errors:
        raise ValueError(f"Invalid orchestration configuration from {source}:\n- " + "\n- ".join(errors))
    return candidate


def load_effective_config(
    root: Path,
    task_override: Mapping[str, Any] | None = None,
    detected_host_max: int | None = None,
) -> dict[str, Any]:
    """Load built-ins, committed config, ignored local config, then task overrides."""
    root = Path(root)
    config = _validated_candidate(BUILT_IN_DEFAULTS, "built-in defaults", detected_host_max)
    for path, source in [
        (root / "config" / "orchestration.json", "config/orchestration.json"),
        (
            root / ".optimal-challenge" / "orchestration.local.json",
            ".optimal-challenge/orchestration.local.json",
        ),
    ]:
        if path.is_file():
            candidate = _merge_layer(config, _read_object(path))
            config = _validated_candidate(candidate, source, detected_host_max)
    if task_override is not None:
        if not isinstance(task_override, Mapping):
            raise TypeError("task_override must be a mapping or None")
        candidate = _merge_layer(config, task_override)
        config = _validated_candidate(candidate, "task_override", detected_host_max)
    return config


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_config(config: Mapping[str, Any], detected_host_max: int | None = None) -> list[str]:
    """Return path-qualified structural and cross-field validation errors."""
    errors: list[str] = []
    if not isinstance(config, Mapping):
        return ["$: expected an object"]

    def object_at(path: str, value: Any) -> Mapping[str, Any] | None:
        if not isinstance(value, Mapping):
            errors.append(f"{path}: expected an object")
            return None
        allowed = _ALLOWED_KEYS[path]
        for key in value:
            if key not in allowed:
                errors.append(f"{path}.{key}: unknown configuration key")
        for key in allowed:
            if key not in value:
                errors.append(f"{path}.{key}: required key is missing")
        return value

    def enum_at(path: str, value: Any, choices: tuple[str, ...], allow_none: bool = False) -> bool:
        if allow_none and value is None:
            return True
        allowed = ", ".join(choices)
        if not isinstance(value, str):
            errors.append(f"{path}: must be a string with one of these values: {allowed}")
            return False
        if value not in choices:
            errors.append(f"{path}: must be one of: {allowed}")
            return False
        return True

    root = object_at("$", config)
    if root is None:
        return errors

    if root.get("schema_version") != 1:
        errors.append("$.schema_version: must be 1")
    enum_at("$.mode", root.get("mode"), ("inline-only", "auto", "team-requested"))
    profile = root.get("profile")
    enum_at("$.profile", profile, ("economy", "balanced", "quality", "custom"))

    weights = object_at("$.objective_weights", root.get("objective_weights"))
    if weights is not None:
        numeric_weights: list[float] = []
        for key in _ALLOWED_KEYS["$.objective_weights"]:
            value = weights.get(key)
            if not _is_number(value) or not 0 <= value <= 1:
                errors.append(f"$.objective_weights.{key}: must be a number from 0 to 1")
            else:
                numeric_weights.append(float(value))
        if len(numeric_weights) == 5 and abs(sum(numeric_weights) - 1.0) > 1e-9:
            errors.append("$.objective_weights: weights must sum to 1")
        if isinstance(profile, str) and profile in PROFILE_WEIGHTS and dict(weights) != PROFILE_WEIGHTS[profile]:
            errors.append(f"$.objective_weights: {profile} profile must use its documented weights")

    team = object_at("$.team_limits", root.get("team_limits"))
    if team is not None:
        for key, low, high in [
            ("max_active_specialists", 0, 3),
            ("delegation_margin", 1, 12),
            ("retry_limit", 0, 12),
        ]:
            value = team.get(key)
            if not _is_int(value) or not low <= value <= high:
                errors.append(f"$.team_limits.{key}: must be an integer from {low} to {high}")
        exact = team.get("exact_specialists")
        if exact is not None and (not _is_int(exact) or not 0 <= exact <= 32):
            errors.append("$.team_limits.exact_specialists: must be null or an integer from 0 to 32")
        if detected_host_max is not None:
            if not _is_int(detected_host_max) or detected_host_max < 0:
                errors.append("$host.detected_host_max: must be a non-negative integer")
            elif _is_int(exact) and exact > min(32, detected_host_max):
                errors.append(
                    "$.team_limits.exact_specialists: "
                    f"requested {exact}, but the effective host maximum {min(32, detected_host_max)} applies"
                )
        if not isinstance(team.get("allow_mode_margin_override"), bool):
            errors.append("$.team_limits.allow_mode_margin_override: must be a boolean")
        enum_at(
            "$.team_limits.capability_class",
            team.get("capability_class"),
            ("economy", "standard", "reasoning", "frontier"),
        )
        if isinstance(profile, str) and profile in PROFILE_WEIGHTS:
            expected_margin = PROFILE_DELEGATION_MARGINS[profile]
            if team.get("delegation_margin") != expected_margin:
                errors.append(
                    "$.team_limits.delegation_margin: "
                    f"{profile} profile requires {expected_margin}"
                )

    premise = object_at("$.premise_gate", root.get("premise_gate"))
    if premise is not None:
        for key in ["enabled", "apply_to_direct_fast_path", "investigate_first", "use_reversible_defaults"]:
            if not isinstance(premise.get(key), bool):
                errors.append(f"$.premise_gate.{key}: must be a boolean")
        risk = premise.get("risk_threshold")
        if not _is_int(risk) or not 0 <= risk <= 9:
            errors.append("$.premise_gate.risk_threshold: must be an integer from 0 to 9")
        question = premise.get("question_value_threshold")
        if not _is_int(question) or not -3 <= question <= 9:
            errors.append("$.premise_gate.question_value_threshold: must be an integer from -3 to 9")

    verification = object_at("$.verification", root.get("verification"))
    if verification is not None:
        enum_at(
            "$.verification.default_depth",
            verification.get("default_depth"),
            ("self-check", "targeted", "independent"),
        )
        margin = verification.get("review_margin")
        if not _is_int(margin) or not 1 <= margin <= 27:
            errors.append("$.verification.review_margin: must be an integer from 1 to 27")
        for key in ["mandatory_independent_review", "compensating_oracle_requires_user_acceptance"]:
            if not isinstance(verification.get(key), bool):
                errors.append(f"$.verification.{key}: must be a boolean")

    persistence = object_at("$.persistence_privacy", root.get("persistence_privacy"))
    if persistence is not None:
        enum_at(
            "$.persistence_privacy.runtime_state",
            persistence.get("runtime_state"),
            ("none", "local", "provider"),
        )
        directory = persistence.get("state_directory")
        if not isinstance(directory, str) or not directory.strip():
            errors.append("$.persistence_privacy.state_directory: must be a non-empty string")
        for key in ["persist_transcripts", "persist_sensitive_data"]:
            if not isinstance(persistence.get(key), bool):
                errors.append(f"$.persistence_privacy.{key}: must be a boolean")

    budget = object_at("$.budget", root.get("budget"))
    if budget is not None:
        unit = budget.get("unit")
        limit = budget.get("limit")
        soft = budget.get("soft_threshold")
        measurement = budget.get("measurement")
        enforcement = budget.get("enforcement")
        source = budget.get("measurement_source")
        units = ("credits", "tokens", "seconds", "currency", "tool_calls", "model_calls")
        enum_at("$.budget.unit", unit, units, allow_none=True)
        if limit is not None and (not _is_number(limit) or limit <= 0):
            errors.append("$.budget.limit: must be null or a positive number")
        if (unit is None) != (limit is None):
            errors.append("$.budget.unit: unit and limit must either both be set or both be null")
        enum_at("$.budget.measurement", measurement, ("unavailable", "estimated", "observed"))
        enforcement_valid = enum_at(
            "$.budget.enforcement",
            enforcement,
            ("advisory", "local_enforced", "provider_enforced"),
        )
        if source is not None and (not isinstance(source, str) or not source.strip()):
            errors.append("$.budget.measurement_source: must be null or a non-empty string")
        adapter = object_at("$.budget.adapter_capabilities", budget.get("adapter_capabilities"))
        verified_capabilities: set[str] = set()
        if adapter is not None:
            for capability in ["observed_measurement", "local_stop", "provider_stop"]:
                capability_path = f"$.budget.adapter_capabilities.{capability}"
                record = object_at(capability_path, adapter.get(capability))
                if record is None:
                    continue
                verified = record.get("verified")
                evidence_id = record.get("evidence_id")
                if not isinstance(verified, bool):
                    errors.append(f"{capability_path}.verified: must be a boolean")
                if evidence_id is not None and (not isinstance(evidence_id, str) or not evidence_id.strip()):
                    errors.append(f"{capability_path}.evidence_id: must be null or a non-empty string")
                if verified is True:
                    if isinstance(evidence_id, str) and evidence_id.strip():
                        verified_capabilities.add(capability)
                    else:
                        errors.append(f"{capability_path}.evidence_id: verified capability requires evidence")
                elif verified is False and evidence_id is not None:
                    errors.append(f"{capability_path}.evidence_id: unverified capability must use null")

        if enforcement_valid and enforcement in {"local_enforced", "provider_enforced"}:
            if measurement != "observed":
                errors.append("$.budget.enforcement: enforced limits require observed measurement")
            if not isinstance(source, str) or not source.strip():
                errors.append("$.budget.measurement_source: enforced limits require a verified source")
            if "observed_measurement" not in verified_capabilities:
                errors.append(
                    "$.budget.adapter_capabilities.observed_measurement: "
                    "enforced limits require verified observed-measurement evidence"
                )
            stop_capability = "local_stop" if enforcement == "local_enforced" else "provider_stop"
            if stop_capability not in verified_capabilities:
                errors.append(
                    f"$.budget.adapter_capabilities.{stop_capability}: "
                    f"{enforcement} requires verified matching stop-primitive evidence"
                )
        if soft is not None and (not _is_number(soft) or soft <= 0):
            errors.append("$.budget.soft_threshold: must be null or a positive number")
        if soft is not None and limit is None:
            errors.append("$.budget.soft_threshold: requires a configured limit")
        if _is_number(soft) and _is_number(limit) and soft > limit:
            errors.append("$.budget.soft_threshold: must not exceed the limit")

    return errors
