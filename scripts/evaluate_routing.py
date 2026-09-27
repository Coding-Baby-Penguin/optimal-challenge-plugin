#!/usr/bin/env python3
"""Deterministic, evidence-backed routing calculations for Optimal Challenge."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__:
    from scripts.orchestration_config import load_effective_config
else:  # Direct ``python scripts/evaluate_routing.py`` execution.
    from orchestration_config import load_effective_config


ROOT = Path(__file__).resolve().parents[1]
PROVENANCE_VALUES = {"observed", "estimated", "unknown"}
BENEFIT_KEYS = ("parallel", "independence", "context", "quality")
COST_KEYS = ("setup", "transfer", "merge", "review_rework")
UTILITY_KEYS = (
    "expected_quality",
    "total_job_cost",
    "critical_path_latency",
    "user_interruption_cost",
    "expected_rework_risk",
)
REVIEW_MARGINS = {"economy": 6, "balanced": 3, "quality": 1}
PREMISE_PROVENANCE_KEYS = (
    "wrongness_likelihood",
    "rework_cost",
    "expected_rework_avoided",
    "user_attention_cost",
)
DELEGATION_PROVENANCE_KEYS = tuple(
    [f"benefits.{name}" for name in BENEFIT_KEYS] + [f"costs.{name}" for name in COST_KEYS]
)
REVIEW_PROVENANCE_KEYS = ("defect_likelihood", "impact", "detection_likelihood", "review_cost")
PROHIBITED_BEHAVIOR_NAMES = {
    "question",
    "spawn",
    "profile-disclosure",
    "authority-override",
    "repeated-question",
    "missing-review-coverage",
    "degraded",
}


def detect_prohibited_behaviors(result: Mapping[str, Any], prohibited: Sequence[str]) -> list[str]:
    """Return configured prohibited behaviors that are observable in a result."""
    unknown = [name for name in prohibited if name not in PROHIBITED_BEHAVIOR_NAMES]
    if unknown:
        raise ValueError(f"unknown prohibited behavior name(s): {', '.join(unknown)}")
    observed = {
        "question": isinstance(result.get("question_count"), int) and result.get("question_count", 0) > 0,
        "spawn": isinstance(result.get("spawn_count"), int) and result.get("spawn_count", 0) > 0,
        "profile-disclosure": result.get("profile_disclosed") is True,
        "authority-override": result.get("authority_override") is True,
        "repeated-question": result.get("repeated_question") is True,
        "missing-review-coverage": result.get("review_coverage") == "none",
        "degraded": result.get("status") == "degraded",
    }
    return [name for name in prohibited if observed[name]]


def _score(value: Any, name: str, *, maximum: int = 3) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ValueError(f"{name}: expected an integer from 0 to {maximum}")
    return value


def _identifier(value: Any, path: str) -> str:
    """Validate non-whitespace identifier content while preserving the original value."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: expected a string with non-whitespace content")
    return value


def _identifier_list(value: Any, path: str, *, require_nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (require_nonempty and not value):
        requirement = "a non-empty list" if require_nonempty else "a list"
        raise ValueError(f"{path}: expected {requirement} of identifiers")
    return [_identifier(item, f"{path}[{index}]") for index, item in enumerate(value)]


def _evidence(case: Mapping[str, Any]) -> list[str]:
    return _identifier_list(case.get("evidence_ids"), "$.evidence_ids", require_nonempty=True)


def _require_bool(source: Mapping[str, Any], key: str, path: str) -> bool:
    value = source.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{path}: expected a boolean")
    return value


def _provenance(
    case: Mapping[str, Any],
    expected_keys: Sequence[str],
    *,
    path: str = "$.provenance",
) -> tuple[str | dict[str, str], bool]:
    value = case.get("provenance")
    if isinstance(value, str):
        if value not in PROVENANCE_VALUES:
            raise ValueError(f"{path}: expected observed, estimated, or unknown")
        return value, value != "unknown"
    if isinstance(value, Mapping):
        result = dict(value)
        if set(result) != set(expected_keys):
            raise ValueError(f"{path}: expected exactly {', '.join(expected_keys)}")
        if any(not isinstance(item, str) or item not in PROVENANCE_VALUES for item in result.values()):
            raise ValueError(f"{path}: every factor must be observed, estimated, or unknown")
        return result, all(item != "unknown" for item in result.values())
    raise ValueError(f"{path}: unexplained scores require a global value or exact factor map")


def _base(
    *,
    route: str,
    factors: Mapping[str, Any],
    evidence_ids: Sequence[str],
    provenance: str | Mapping[str, str],
    reason: str,
    threshold: Any = None,
    margin: Any = None,
) -> dict[str, Any]:
    return {
        "route": route,
        "factors": dict(factors),
        "evidence_ids": list(evidence_ids),
        "threshold": threshold,
        "margin": margin,
        "provenance": dict(provenance) if isinstance(provenance, Mapping) else provenance,
        "reason": reason,
        "question_count": 0,
        "spawn_count": 0,
        "profile_disclosed": False,
        "authority_override": False,
        "repeated_question": False,
        "review_coverage": "not-applicable",
        "status": "ok",
    }


def score_premise(case: Mapping[str, Any]) -> dict[str, Any]:
    """Apply premise-risk and question-value gates to one unresolved premise."""
    if not isinstance(case, Mapping):
        raise TypeError("case must be a mapping")
    for key in ("changes_work_graph", "irreversible", "cheap_investigation", "safe_reversible_default"):
        if key in case:
            _require_bool(case, key, f"$.{key}")
    direct_fast_path = _require_bool(case, "direct_fast_path", "$.direct_fast_path") if "direct_fast_path" in case else False
    if direct_fast_path:
        result = _base(
            route="direct",
            factors={},
            evidence_ids=[],
            provenance="unknown",
            threshold=None,
            reason="Stable, single-step, low-risk direct work bypasses premise scoring.",
        )
        result.update({"ask_user": False, "decision_id": None, "profile_disclosed": False})
        return result

    evidence_ids = _evidence(case)
    contradictory = _identifier_list(
        case.get("contradiction_evidence_ids", []),
        "$.contradiction_evidence_ids",
    )
    for item in contradictory:
        if item not in evidence_ids:
            evidence_ids.append(item)
    provenance, _ = _provenance(case, PREMISE_PROVENANCE_KEYS)
    changes_work_graph = _require_bool(case, "changes_work_graph", "$.changes_work_graph")
    irreversible = _require_bool(case, "irreversible", "$.irreversible")
    cheap_investigation = _require_bool(case, "cheap_investigation", "$.cheap_investigation")
    safe_reversible_default = _require_bool(case, "safe_reversible_default", "$.safe_reversible_default")
    wrongness = _score(case.get("wrongness_likelihood"), "wrongness_likelihood")
    rework_cost = _score(case.get("rework_cost"), "rework_cost")
    avoided = _score(case.get("expected_rework_avoided"), "expected_rework_avoided", maximum=9)
    attention = _score(case.get("user_attention_cost"), "user_attention_cost")
    premise_risk = wrongness * rework_cost
    if avoided > premise_risk:
        raise ValueError("expected_rework_avoided cannot exceed premise_risk")
    question_value = avoided - attention
    factors = {
        "wrongness_likelihood": wrongness,
        "rework_cost": rework_cost,
        "premise_risk": premise_risk,
        "expected_rework_avoided": avoided,
        "user_attention_cost": attention,
        "question_value": question_value,
    }
    threshold = {"premise_risk": 4, "question_value_gt": 0}
    decision_id = _identifier(case.get("decision_id"), "$.decision_id")
    settled = _identifier_list(case.get("settled_decision_ids", []), "$.settled_decision_ids")

    invalidated_decision_id = decision_id if decision_id in settled and contradictory else None
    if decision_id in settled and not contradictory:
        route = "reuse-settled"
        reason = f"Decision {decision_id} is settled and no contradictory evidence invalidates it."
    elif cheap_investigation:
        route = "investigate"
        reason = "A cheap investigation can resolve the premise without interrupting the user."
    elif (
        premise_risk >= threshold["premise_risk"]
        and question_value > threshold["question_value_gt"]
        and (changes_work_graph or irreversible)
        and not safe_reversible_default
    ):
        route = "ask"
        if invalidated_decision_id:
            reason = (
                f"Decision {invalidated_decision_id} was invalidated by contradictory evidence "
                f"{', '.join(contradictory)}; the material premise must be asked again."
            )
        else:
            reason = "The material premise changes the work graph or an irreversible decision and asking has positive value."
    else:
        route = "default"
        reason = "Risk or question value is below the blocking boundary, or a safe reversible default exists."

    result = _base(
        route=route,
        factors=factors,
        evidence_ids=evidence_ids,
        provenance=provenance,
        threshold=threshold,
        reason=reason,
    )
    result.update(
        {
            "ask_user": route == "ask",
            "decision_id": decision_id,
            "question_count": 1 if route == "ask" else 0,
            "invalidated_decision_id": invalidated_decision_id,
            "contradiction_evidence_ids": list(contradictory),
            "repeated_question": route == "ask" and decision_id in settled and invalidated_decision_id is None,
        }
    )
    return result


def _factor_group(case: Mapping[str, Any], group: str, keys: Sequence[str]) -> dict[str, int]:
    value = case.get(group)
    if not isinstance(value, Mapping):
        raise ValueError(f"{group}: expected an object")
    missing = [key for key in keys if key not in value]
    extra = [key for key in value if key not in keys]
    if missing or extra:
        raise ValueError(f"{group}: expected exactly {', '.join(keys)}")
    return {key: _score(value[key], f"{group}.{key}") for key in keys}


def score_delegation(case: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    """Score delegation economics, then apply invocation authority and capacity gates."""
    if not isinstance(case, Mapping) or not isinstance(config, Mapping):
        raise TypeError("case and config must be mappings")
    evidence_ids = _evidence(case)
    provenance, economics_known = _provenance(case, DELEGATION_PROVENANCE_KEYS)
    benefits = _factor_group(case, "benefits", BENEFIT_KEYS)
    costs = _factor_group(case, "costs", COST_KEYS)
    value = sum(benefits.values()) - sum(costs.values())
    strong_benefit = any(score >= 2 for score in benefits.values())

    mode = config.get("mode")
    profile = config.get("profile")
    limits = config.get("team_limits")
    if mode not in {"inline-only", "auto", "team-requested"} or not isinstance(limits, Mapping):
        raise ValueError("config: invalid mode or team_limits")
    margin = limits.get("delegation_margin")
    if isinstance(margin, bool) or not isinstance(margin, int) or not 1 <= margin <= 12:
        raise ValueError("config.team_limits.delegation_margin: expected 1 to 12")
    if mode == "team-requested" and (
        profile == "economy" or (profile == "custom" and limits.get("allow_mode_margin_override") is True)
    ):
        margin = 1

    exact = limits.get("exact_specialists")
    if exact is not None and (isinstance(exact, bool) or not isinstance(exact, int) or not 0 <= exact <= 32):
        raise ValueError("config.team_limits.exact_specialists: expected null or 0 to 32")
    available = case.get("available_specialist_slots", 0)
    if isinstance(available, bool) or not isinstance(available, int) or available < 0:
        raise ValueError("$.available_specialist_slots: expected a non-negative integer")
    configured_capacity = limits.get("max_active_specialists")
    if isinstance(configured_capacity, bool) or not isinstance(configured_capacity, int) or not 0 <= configured_capacity <= 3:
        raise ValueError("config.team_limits.max_active_specialists: expected 0 to 3")
    observable_done_condition = _require_bool(case, "observable_done_condition", "$.observable_done_condition")
    fits_job_envelope = _require_bool(case, "fits_job_envelope", "$.fits_job_envelope")
    platform_available = _require_bool(case, "platform_available", "$.platform_available")
    authority_allows = _require_bool(case, "authority_allows", "$.authority_allows")

    factors = {
        "benefits": benefits,
        "costs": costs,
        "benefit_total": sum(benefits.values()),
        "cost_total": sum(costs.values()),
        "delegation_value": value,
        "strong_benefit": strong_benefit,
    }
    question_count = 0
    specialist_count = 0

    if mode == "inline-only" and exact is not None and exact > 0:
        route = "ask-resolution"
        question_count = 1
        reason = "Inline-only and an exact positive specialist count are incompatible explicit controls."
    elif exact == 0 or (mode == "inline-only" and exact is None):
        route = "inline"
        specialist_count = 0
        reason = "Explicit inline authority forbids specialist creation."
    elif exact is not None:
        within_authority = authority_allows
        available_route = platform_available and available >= exact
        within_envelope = fits_job_envelope
        has_done_condition = observable_done_condition
        if within_authority and available_route and within_envelope and has_done_condition:
            route = "delegate"
            specialist_count = exact
            reason = f"The exact request for {exact} specialist(s) overrides economic margins within authority and capacity."
        else:
            route = "ask-resolution"
            question_count = 1
            reason = "The exact request lacks an observable done condition or cannot fit current authority, availability, or the active job envelope."
    elif (
        economics_known
        and value >= margin
        and value > 0
        and strong_benefit
        and observable_done_condition
        and fits_job_envelope
        and platform_available
        and authority_allows
        and configured_capacity >= 1
        and available >= 1
    ):
        route = "delegate"
        specialist_count = 1
        reason = "Benefit minus coordination cost meets the margin with a strong benefit and executable boundary."
    else:
        route = "inline"
        specialist_count = 0
        reason = (
            "Delegation economics are unknown, so optional delegation stays inline."
            if not economics_known and exact is None
            else "Delegation does not clear every economic, evidence, authority, and envelope gate."
        )

    result = _base(
        route=route,
        factors=factors,
        evidence_ids=evidence_ids,
        provenance=provenance,
        threshold={"strong_benefit": 2, "positive_value_required": True},
        margin=margin,
        reason=reason,
    )
    result.update(
        {
            "specialist_count": specialist_count,
            "exact_specialists": exact,
            "max_active_specialists": configured_capacity,
            "question_count": question_count,
            "spawn_count": specialist_count if route == "delegate" else 0,
            "authority_override": exact is not None and exact > 0 and route == "delegate",
            "status": "unresolved" if route == "ask-resolution" else "ok",
            "economics_known": economics_known,
            "economics_status": "known" if economics_known else "unknown",
            "mode": mode,
            "profile": profile,
        }
    )
    return result


def score_review(case: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate independent-review value and enforce mandatory review semantics."""
    if not isinstance(case, Mapping) or not isinstance(config, Mapping):
        raise TypeError("case and config must be mappings")
    evidence_ids = _evidence(case)
    provenance, economics_known = _provenance(case, REVIEW_PROVENANCE_KEYS)
    defect = _score(case.get("defect_likelihood"), "defect_likelihood")
    impact = _score(case.get("impact"), "impact")
    detection = _score(case.get("detection_likelihood"), "detection_likelihood")
    cost = _score(case.get("review_cost"), "review_cost")
    product = defect * impact * detection
    value = product - cost
    profile = config.get("profile")
    mode = config.get("mode")
    if mode not in {"inline-only", "auto", "team-requested"}:
        raise ValueError("config.mode: expected inline-only, auto, or team-requested")
    limits = config.get("team_limits")
    if not isinstance(limits, Mapping):
        raise ValueError("config.team_limits: expected an object")
    exact_specialists = limits.get("exact_specialists")
    if exact_specialists is not None and (
        isinstance(exact_specialists, bool) or not isinstance(exact_specialists, int) or not 0 <= exact_specialists <= 32
    ):
        raise ValueError("config.team_limits.exact_specialists: expected null or 0 to 32")
    configured_capacity = limits.get("max_active_specialists")
    if isinstance(configured_capacity, bool) or not isinstance(configured_capacity, int) or not 0 <= configured_capacity <= 3:
        raise ValueError("config.team_limits.max_active_specialists: expected 0 to 3")
    verification = config.get("verification")
    if not isinstance(verification, Mapping):
        raise ValueError("config.verification: expected an object")
    margin = REVIEW_MARGINS.get(profile, verification.get("review_margin"))
    if isinstance(margin, bool) or not isinstance(margin, int) or not 1 <= margin <= 27:
        raise ValueError("config.verification.review_margin: expected 1 to 27")
    requested_mandatory = _require_bool(case, "mandatory_independent_review", "$.mandatory_independent_review")
    consequential = _require_bool(case, "consequential_weak_oracle", "$.consequential_weak_oracle")
    available = _require_bool(case, "independent_review_available", "$.independent_review_available")
    accepted = _require_bool(
        case,
        "user_accepts_compensating_oracle",
        "$.user_accepts_compensating_oracle",
    )
    configured_mandatory = verification.get("mandatory_independent_review")
    if not isinstance(configured_mandatory, bool):
        raise ValueError("$.config.verification.mandatory_independent_review: expected a boolean")
    mandatory = requested_mandatory or consequential or configured_mandatory
    inline_authority = mode == "inline-only" or exact_specialists == 0
    capacity_available = available and (configured_capacity >= 1 or (isinstance(exact_specialists, int) and exact_specialists > 0))
    compensating = case.get("compensating_oracle")
    if compensating is not None:
        compensating = _identifier(compensating, "$.compensating_oracle")

    if inline_authority and mandatory:
        route = "ask-resolution"
        reason = "Inline-only conflicts with mandatory independent review; one explicit route decision is required."
    elif inline_authority:
        route = "self-check"
        reason = "Inline-only authority forbids optional independent reviewer creation."
    elif mandatory and not capacity_available:
        if isinstance(compensating, str) and compensating.strip() and accepted:
            route = "degraded-compensating-oracle"
            reason = "Mandatory independent review is unavailable; a named compensating oracle was explicitly accepted."
        else:
            route = "blocked"
            reason = "Mandatory independent review is unavailable and cannot be silently waived."
    elif mandatory:
        route = "independent-review"
        reason = "Independent review is an explicit or consequential-work execution constraint."
    elif economics_known and value >= margin and capacity_available:
        route = "independent-review"
        reason = "Expected review value meets the profile threshold and an independent reviewer is available."
    else:
        route = "self-check"
        reason = (
            "Review economics are unknown, so optional independent review cannot proceed."
            if not economics_known
            else "Independent review does not meet the calculated threshold or is unavailable for optional review."
        )

    result = _base(
        route=route,
        factors={
            "defect_likelihood": defect,
            "impact": impact,
            "detection_likelihood": detection,
            "review_cost": cost,
            "review_product": product,
            "review_value": value,
        },
        evidence_ids=evidence_ids,
        provenance=provenance,
        threshold=margin,
        margin=margin,
        reason=reason,
    )
    coverage = {
        "independent-review": "independent",
        "degraded-compensating-oracle": "compensating",
        "self-check": "self",
        "blocked": "none",
        "ask-resolution": "none",
    }[route]
    status = (
        "degraded"
        if route == "degraded-compensating-oracle"
        else ("blocked" if route == "blocked" else ("unresolved" if route == "ask-resolution" else "ok"))
    )
    result.update(
        {
            "mandatory": mandatory,
            "review_available": capacity_available,
            "compensating_oracle": compensating,
            "spawn_count": 1 if route == "independent-review" else 0,
            "question_count": 1 if route == "ask-resolution" else 0,
            "authority_override": mandatory,
            "review_coverage": coverage,
            "status": status,
            "economics_known": economics_known,
            "economics_status": "known" if economics_known else "unknown",
        }
    )
    return result


def compare_routes(
    routes: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    *,
    independence_mandatory: bool = False,
) -> dict[str, Any]:
    """Compare normalized whole-job utility after mandatory gates have passed."""
    if not isinstance(independence_mandatory, bool):
        raise ValueError("$.independence_mandatory: expected a boolean")
    if isinstance(routes, (str, bytes)) or not isinstance(routes, Sequence) or not routes:
        raise ValueError("routes: expected a non-empty sequence")
    weights = config.get("objective_weights") if isinstance(config, Mapping) else None
    if not isinstance(weights, Mapping) or set(weights) != {"quality", "cost", "latency", "attention", "rework"}:
        raise ValueError("config.objective_weights: expected all five utility weights")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1 for value in weights.values()):
        raise ValueError("config.objective_weights: weights must be numeric values from 0 to 1")
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("config.objective_weights: weights must sum to 1")

    utilities: dict[str, float | None] = {}
    factors_by_route: dict[str, dict[str, int]] = {}
    evidence_by_route: dict[str, list[str]] = {}
    provenance_by_route: dict[str, str | dict[str, str]] = {}
    eligible: list[tuple[str, Mapping[str, Any], float]] = []
    ineligible: list[str] = []
    for index, candidate in enumerate(routes):
        if not isinstance(candidate, Mapping):
            raise ValueError("routes: every route must be an object")
        route_id = _identifier(candidate.get("id"), f"$.routes[{index}].id")
        if route_id in utilities:
            raise ValueError("routes.id: expected unique non-empty strings")
        route_path = f"$.routes[{index}]"
        route_name = _identifier(candidate.get("route"), f"{route_path}.route")
        evidence_by_route[route_id] = _evidence(candidate)
        provenance, provenance_complete = _provenance(
            candidate,
            UTILITY_KEYS,
            path=f"{route_path}.provenance",
        )
        provenance_by_route[route_id] = provenance
        gates_pass = _require_bool(candidate, "mandatory_gates_passed", f"{route_path}.mandatory_gates_passed")
        _require_bool(candidate, "independence", f"{route_path}.independence")
        factor_values = {key: _score(candidate.get(key), key) for key in UTILITY_KEYS}
        factors_by_route[route_id] = factor_values
        utility = (
            weights["quality"] * factor_values["expected_quality"]
            - weights["cost"] * factor_values["total_job_cost"]
            - weights["latency"] * factor_values["critical_path_latency"]
            - weights["attention"] * factor_values["user_interruption_cost"]
            - weights["rework"] * factor_values["expected_rework_risk"]
        )
        if not gates_pass or not provenance_complete:
            utilities[route_id] = None
            ineligible.append(route_id)
        else:
            rounded = round(utility, 12)
            utilities[route_id] = rounded
            eligible.append((route_id, candidate, rounded))

    if independence_mandatory:
        independent = [item for item in eligible if item[1]["independence"]]
        eligible = independent
    if not eligible:
        chosen = "blocked"
        selected_route_id = None
        reason = "No eligible evidenced route passed every mandatory gate; no route was selected."
    else:
        best = max(item[2] for item in eligible)
        tied = [item for item in eligible if abs(item[2] - best) <= 1e-12]
        inline = next((item for item in tied if item[1]["route"] == "inline"), None)
        if len(tied) > 1 and inline is None:
            chosen = "unresolved" if independence_mandatory else "inline-required"
            selected_route_id = None
            reason = "Eligible non-inline routes tied; no arbitrary worker route was selected."
        else:
            selected = inline if inline is not None else tied[0]
            chosen = selected[0]
            selected_route_id = selected[0]
            reason = (
                "Utility tied, so the eligible inline route was selected."
                if len(tied) > 1 and inline is not None
                else "The route has the greatest eligible normalized whole-job utility."
            )

    return {
        "route": chosen,
        "selected_route_id": selected_route_id,
        "factors": factors_by_route,
        "evidence_ids": evidence_by_route,
        "threshold": "greatest eligible utility; ties inline unless independence is mandatory",
        "margin": None,
        "provenance": provenance_by_route,
        "reason": reason,
        "utilities": utilities,
        "ineligible_routes": ineligible,
        "question_count": 0,
        "spawn_count": 0,
        "profile_disclosed": False,
        "authority_override": False,
        "repeated_question": False,
        "review_coverage": "not-applicable",
        "status": "blocked" if chosen == "blocked" else ("unresolved" if selected_route_id is None else "ok"),
    }


def _evaluate_fixture(fixture: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    kind = fixture.get("kind")
    item = fixture.get("input")
    if not isinstance(item, Mapping):
        raise ValueError(f"{fixture.get('id', '<unknown>')}: input must be an object")
    if kind == "premise":
        return score_premise(item)
    if kind == "delegation":
        return score_delegation(item, config)
    if kind == "review":
        return score_review(item, config)
    if kind == "utility":
        routes = item.get("routes")
        independence_mandatory = item.get("independence_mandatory", False)
        if not isinstance(independence_mandatory, bool):
            raise ValueError("$.input.independence_mandatory: expected a boolean")
        return compare_routes(routes, config, independence_mandatory=independence_mandatory)
    raise ValueError(f"{fixture.get('id', '<unknown>')}: unsupported kind {kind!r}")


def validate_manifest(path: Path) -> int:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: invalid routing manifest: {exc}") from exc
    if not isinstance(manifest, Mapping) or manifest.get("schema_version") != 1:
        raise ValueError("routing manifest requires schema_version 1")
    fixtures = manifest.get("cases")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("routing manifest cases must be a non-empty array")
    seen: set[str] = set()
    for fixture in fixtures:
        if not isinstance(fixture, Mapping):
            raise ValueError("every routing case must be an object")
        fixture_id = _identifier(fixture.get("id"), "$.cases[].id")
        if fixture_id in seen:
            raise ValueError("routing case IDs must be unique non-empty strings")
        seen.add(fixture_id)
        expected = _identifier(fixture.get("expected_route"), f"$.cases[{fixture_id}].expected_route")
        prohibited = fixture.get("prohibited_behaviors")
        if not isinstance(prohibited, list):
            raise ValueError(f"{fixture_id}: expected_route and prohibited_behaviors are required")
        prohibited = [
            _identifier(item, f"$.cases[{fixture_id}].prohibited_behaviors[{index}]")
            for index, item in enumerate(prohibited)
        ]
        config = load_effective_config(ROOT, task_override=fixture.get("config_override"))
        result = _evaluate_fixture(fixture, config)
        if result["route"] != expected:
            raise ValueError(f"{fixture_id}: expected {expected!r}, calculated {result['route']!r}")
        present = detect_prohibited_behaviors(result, prohibited)
        if present:
            raise ValueError(f"{fixture_id}: prohibited behaviors present: {sorted(present)}")
    return len(fixtures)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path, default=ROOT / "tests" / "team-routing.json")
    args = parser.parse_args(argv)
    try:
        count = validate_manifest(args.manifest.resolve())
    except (TypeError, ValueError) as exc:
        print(f"TEAM ROUTING VALIDATION FAILED: {exc}")
        return 1
    print(f"TEAM ROUTING VALIDATION PASSED ({count} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
