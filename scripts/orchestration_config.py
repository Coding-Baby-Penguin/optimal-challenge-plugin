#!/usr/bin/env python3
"""Load and validate provider-neutral orchestration policy configuration."""
from __future__ import annotations

import json
import math
import weakref
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


_CONFIG_CONTEXT_ISSUER = object()
_ISSUED_CONFIG_CONTEXTS: dict[int, weakref.ReferenceType[VerifiedCapabilityContext]] = {}
# No current host adapter has demonstrated an executable budget stop handle.
# Add a surface here only with an audited implementation and exact-version test.
_OBSERVED_ENFORCEMENT_ADAPTERS: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True, weakref_slot=True)
class VerifiedCapabilityContext:
    """Trusted, time-bounded adapter evidence kept outside user configuration."""

    surface: str
    version: str
    provenance: str
    evidence_ref: str
    verified_at: datetime
    expires_at: datetime
    observed_usage: bool
    local_stop_primitive: bool
    provider_stop_primitive: bool
    _attestation: object | None = field(default=None, repr=False, compare=False)


def issue_config_capability_context(
    *, surface: str, version: str, usage_evidence: Any, enforcement_evidence: Any,
    usage_policy: Mapping[str, Any], enforcement_policy: Mapping[str, Any], now: datetime,
) -> VerifiedCapabilityContext:
    """Bridge issued exact-surface resolver evidence into the config loader.

    A JSON claim or a caller-created context cannot authorize enforced limits.
    Real adapter support must be observed; no stop primitive is inferred here.
    """
    from scripts.optimal_challenge.capability_evidence import (
        EnforcementProof, TrustedCapabilityEvidence, UsageCounterProof,
    )
    from scripts.optimal_challenge.capability_resolution import resolve_capability

    if not isinstance(usage_evidence, TrustedCapabilityEvidence) or not isinstance(enforcement_evidence, TrustedCapabilityEvidence):
        raise ValueError("issued adapter evidence is required for both usage and enforcement")
    if usage_evidence.capability != "usage_measurement" or enforcement_evidence.capability not in {"local_enforcement", "provider_enforcement"}:
        raise ValueError("usage and enforcement capability proofs are required")
    if not isinstance(usage_evidence.proof, UsageCounterProof) or not isinstance(enforcement_evidence.proof, EnforcementProof):
        raise ValueError("typed usage counter and stop primitive proofs are required")
    usage = resolve_capability(surface, usage_evidence, None, usage_policy, now)
    stop = resolve_capability(surface, enforcement_evidence, None, enforcement_policy, now)
    if any(result.get("support_level") != "observed" or result.get("verified_version") != version or result.get("surface") != surface
           for result in (usage, stop)):
        raise ValueError("exact-surface observed resolver support is required")
    if usage_evidence.proof.observed is not True or enforcement_evidence.proof.usage_counter != usage_evidence.proof:
        raise ValueError("stop proof must use the same observed usage counter")
    if surface not in _OBSERVED_ENFORCEMENT_ADAPTERS:
        raise ValueError("no observed executable stop adapter exists for this surface; use advisory enforcement")
    context = VerifiedCapabilityContext(
        surface=surface, version=version, provenance=usage_evidence.provenance,
        evidence_ref=f"{usage_evidence.evidence_ref}|{enforcement_evidence.evidence_ref}",
        verified_at=max(usage_evidence.verified_at, enforcement_evidence.verified_at),
        expires_at=min(usage_evidence.expires_at, enforcement_evidence.expires_at),
        observed_usage=True,
        local_stop_primitive=enforcement_evidence.capability == "local_enforcement",
        provider_stop_primitive=enforcement_evidence.capability == "provider_enforcement",
        _attestation=_CONFIG_CONTEXT_ISSUER,
    )
    _ISSUED_CONFIG_CONTEXTS[id(context)] = weakref.ref(context)
    return context

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
    capability_context: VerifiedCapabilityContext | None,
    expected_surface: str | None,
    expected_version: str | None,
    now: datetime | None,
) -> dict[str, Any]:
    candidate = deepcopy(dict(config))
    errors = validate_config(
        candidate,
        detected_host_max=detected_host_max,
        capability_context=capability_context,
        expected_surface=expected_surface,
        expected_version=expected_version,
        now=now,
    )
    if errors:
        raise ValueError(f"Invalid orchestration configuration from {source}:\n- " + "\n- ".join(errors))
    return candidate


def load_effective_config(
    root: Path,
    task_override: Mapping[str, Any] | None = None,
    detected_host_max: int | None = None,
    *,
    capability_context: VerifiedCapabilityContext | None = None,
    expected_surface: str | None = None,
    expected_version: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Load built-ins, committed config, ignored local config, then task overrides."""
    root = Path(root)
    validation_context = (capability_context, expected_surface, expected_version, now)
    config = _validated_candidate(
        BUILT_IN_DEFAULTS,
        "built-in defaults",
        detected_host_max,
        *validation_context,
    )
    for path, source in [
        (root / "config" / "orchestration.json", "config/orchestration.json"),
        (
            root / ".optimal-challenge" / "orchestration.local.json",
            ".optimal-challenge/orchestration.local.json",
        ),
    ]:
        if path.is_file():
            candidate = _merge_layer(config, _read_object(path))
            config = _validated_candidate(candidate, source, detected_host_max, *validation_context)
    if task_override is not None:
        if not isinstance(task_override, Mapping):
            raise TypeError("task_override must be a mapping or None")
        candidate = _merge_layer(config, task_override)
        config = _validated_candidate(candidate, "task_override", detected_host_max, *validation_context)
    return config


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and (isinstance(value, int) or math.isfinite(value))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _capability_context_errors(
    context: VerifiedCapabilityContext | None,
    enforcement: str,
    expected_surface: str | None,
    expected_version: str | None,
    now: datetime | None,
) -> list[str]:
    path = "$context.capabilities"
    if (not isinstance(context, VerifiedCapabilityContext)
            or context._attestation is not _CONFIG_CONTEXT_ISSUER
            or id(context) not in _ISSUED_CONFIG_CONTEXTS
            or _ISSUED_CONFIG_CONTEXTS[id(context)]() is not context):
        return [f"{path}: enforced limits require trusted adapter capability context"]

    errors: list[str] = []
    if not isinstance(expected_surface, str) or not expected_surface.strip():
        errors.append(f"{path}.expected_surface: enforced limits require the exact active surface")
    elif context.surface != expected_surface:
        errors.append(f"{path}.surface: {context.surface!r} does not match {expected_surface!r}")
    if not isinstance(expected_version, str) or not expected_version.strip():
        errors.append(f"{path}.expected_version: enforced limits require the exact active version")
    elif context.version != expected_version:
        errors.append(f"{path}.version: {context.version!r} does not match {expected_version!r}")
    if not isinstance(context.provenance, str) or context.provenance not in {
        "live_detection",
        "acceptance_run",
    }:
        errors.append(f"{path}.provenance: must be live_detection or acceptance_run")
    if not isinstance(context.evidence_ref, str) or not context.evidence_ref.strip():
        errors.append(f"{path}.evidence_ref: must cite non-empty trusted evidence")

    checked_at = now if now is not None else datetime.now(timezone.utc)
    datetimes = {
        "verified_at": context.verified_at,
        "expires_at": context.expires_at,
        "now": checked_at,
    }
    aware = True
    for name, value in datetimes.items():
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            errors.append(f"{path}.{name}: must be a timezone-aware datetime")
            aware = False
    if aware:
        if context.expires_at <= context.verified_at:
            errors.append(f"{path}.expires_at: must be later than verified_at")
        if context.verified_at > checked_at:
            errors.append(f"{path}.verified_at: cannot be in the future")
        if context.expires_at <= checked_at:
            errors.append(f"{path}.expires_at: capability evidence is expired")

    if context.observed_usage is not True:
        errors.append(f"{path}.observed_usage: enforced limits require observed usage")
    if enforcement == "local_enforced" and context.local_stop_primitive is not True:
        errors.append(f"{path}.local_stop_primitive: local stop primitive is not verified")
    if enforcement == "provider_enforced" and context.provider_stop_primitive is not True:
        errors.append(f"{path}.provider_stop_primitive: provider stop primitive is not verified")
    return errors


def validate_config(
    config: Mapping[str, Any],
    detected_host_max: int | None = None,
    *,
    capability_context: VerifiedCapabilityContext | None = None,
    expected_surface: str | None = None,
    expected_version: str | None = None,
    now: datetime | None = None,
) -> list[str]:
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
        if enforcement_valid and enforcement in {"local_enforced", "provider_enforced"}:
            if measurement != "observed":
                errors.append("$.budget.enforcement: enforced limits require observed measurement")
            if not isinstance(source, str) or not source.strip():
                errors.append("$.budget.measurement_source: enforced limits require a verified source")
            errors.extend(
                _capability_context_errors(
                    capability_context,
                    enforcement,
                    expected_surface,
                    expected_version,
                    now,
                )
            )
        if soft is not None and (not _is_number(soft) or soft <= 0):
            errors.append("$.budget.soft_threshold: must be null or a positive number")
        if soft is not None and limit is None:
            errors.append("$.budget.soft_threshold: requires a configured limit")
        if _is_number(soft) and _is_number(limit) and soft > limit:
            errors.append("$.budget.soft_threshold: must not exceed the limit")

    return errors
