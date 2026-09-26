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
    if selected_profile in PROFILE_WEIGHTS and "objective_weights" not in prepared:
        prepared["objective_weights"] = PROFILE_WEIGHTS[selected_profile]
    elif selected_profile == "custom" and "objective_weights" not in prepared:
        prepared["objective_weights"] = PROFILE_WEIGHTS["balanced"]
    return merge_known(config, prepared)


def load_effective_config(
    root: Path,
    task_override: Mapping[str, Any] | None = None,
    detected_host_max: int | None = None,
) -> dict[str, Any]:
    """Load built-ins, committed config, ignored local config, then task overrides."""
    root = Path(root)
    config: dict[str, Any] = deepcopy(BUILT_IN_DEFAULTS)
    for path in [
        root / "config" / "orchestration.json",
        root / ".optimal-challenge" / "orchestration.local.json",
    ]:
        if path.is_file():
            config = _merge_layer(config, _read_object(path))
    if task_override is not None:
        if not isinstance(task_override, Mapping):
            raise TypeError("task_override must be a mapping or None")
        config = _merge_layer(config, task_override)

    errors = validate_config(config, detected_host_max=detected_host_max)
    if errors:
        raise ValueError("Invalid orchestration configuration:\n- " + "\n- ".join(errors))
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

    root = object_at("$", config)
    if root is None:
        return errors

    if root.get("schema_version") != 1:
        errors.append("$.schema_version: must be 1")
    if root.get("mode") not in {"inline-only", "auto", "team-requested"}:
        errors.append("$.mode: must be inline-only, auto, or team-requested")
    profile = root.get("profile")
    if profile not in {"economy", "balanced", "quality", "custom"}:
        errors.append("$.profile: must be economy, balanced, quality, or custom")

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
        if profile in PROFILE_WEIGHTS and dict(weights) != PROFILE_WEIGHTS[profile]:
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
        if team.get("capability_class") not in {"economy", "standard", "reasoning", "frontier"}:
            errors.append("$.team_limits.capability_class: unsupported capability class")

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
        if verification.get("default_depth") not in {"self-check", "targeted", "independent"}:
            errors.append("$.verification.default_depth: unsupported verification depth")
        margin = verification.get("review_margin")
        if not _is_int(margin) or not 1 <= margin <= 27:
            errors.append("$.verification.review_margin: must be an integer from 1 to 27")
        for key in ["mandatory_independent_review", "compensating_oracle_requires_user_acceptance"]:
            if not isinstance(verification.get(key), bool):
                errors.append(f"$.verification.{key}: must be a boolean")

    persistence = object_at("$.persistence_privacy", root.get("persistence_privacy"))
    if persistence is not None:
        if persistence.get("runtime_state") not in {"none", "local", "provider"}:
            errors.append("$.persistence_privacy.runtime_state: must be none, local, or provider")
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
        units = {"credits", "tokens", "seconds", "currency", "tool_calls", "model_calls"}
        if unit is not None and unit not in units:
            errors.append("$.budget.unit: unsupported unit")
        if limit is not None and (not _is_number(limit) or limit <= 0):
            errors.append("$.budget.limit: must be null or a positive number")
        if (unit is None) != (limit is None):
            errors.append("$.budget.unit: unit and limit must either both be set or both be null")
        if measurement not in {"unavailable", "estimated", "observed"}:
            errors.append("$.budget.measurement: must be unavailable, estimated, or observed")
        if enforcement not in {"advisory", "local_enforced", "provider_enforced"}:
            errors.append("$.budget.enforcement: unsupported enforcement mode")
        if source is not None and (not isinstance(source, str) or not source.strip()):
            errors.append("$.budget.measurement_source: must be null or a non-empty string")
        if enforcement in {"local_enforced", "provider_enforced"}:
            if measurement != "observed":
                errors.append("$.budget.enforcement: enforced limits require observed measurement")
            if not isinstance(source, str) or not source.strip():
                errors.append("$.budget.measurement_source: enforced limits require a verified source")
        if soft is not None and (not _is_number(soft) or soft <= 0):
            errors.append("$.budget.soft_threshold: must be null or a positive number")
        if soft is not None and limit is None:
            errors.append("$.budget.soft_threshold: requires a configured limit")
        if _is_number(soft) and _is_number(limit) and soft > limit:
            errors.append("$.budget.soft_threshold: must not exceed the limit")

    return errors
