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


def _score(value: Any, name: str, *, maximum: int = 3) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ValueError(f"{name}: expected an integer from 0 to {maximum}")
    return value


def _evidence(case: Mapping[str, Any]) -> list[str]:
    value = case.get("evidence_ids")
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError("evidence_ids: unexplained scores require one or more non-empty evidence IDs")
    return list(value)


def _provenance(case: Mapping[str, Any]) -> str | dict[str, str]:
    value = case.get("provenance")
    if isinstance(value, str):
        if value not in PROVENANCE_VALUES:
            raise ValueError("provenance: expected observed, estimated, or unknown")
        return value
    if isinstance(value, Mapping) and value:
        result = dict(value)
        if any(item not in PROVENANCE_VALUES for item in result.values()):
            raise ValueError("provenance: every factor must be observed, estimated, or unknown")
        return result
    raise ValueError("provenance: unexplained scores require observed, estimated, or unknown provenance")


def _base(
    *,
    route: str,
    factors: Mapping[str, Any],
    evidence_ids: Sequence[str],
    provenance: str | Mapping[str, str],
    reason: str,
    threshold: Any = None,
    margin: Any = None,
    behaviors: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "route": route,
        "factors": dict(factors),
        "evidence_ids": list(evidence_ids),
        "threshold": threshold,
        "margin": margin,
        "provenance": dict(provenance) if isinstance(provenance, Mapping) else provenance,
        "reason": reason,
        "behaviors": list(behaviors),
    }


def score_premise(case: Mapping[str, Any]) -> dict[str, Any]:
    """Apply premise-risk and question-value gates to one unresolved premise."""
    if not isinstance(case, Mapping):
        raise TypeError("case must be a mapping")
    if case.get("direct_fast_path") is True:
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
    contradictory = case.get("contradictory_evidence_ids", [])
    if not isinstance(contradictory, list) or any(not isinstance(item, str) or not item for item in contradictory):
        raise ValueError("contradictory_evidence_ids: expected a list of non-empty strings")
    for item in contradictory:
        if item not in evidence_ids:
            evidence_ids.append(item)
    provenance = _provenance(case)
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
    decision_id = case.get("decision_id")
    if not isinstance(decision_id, str) or not decision_id.strip():
        raise ValueError("decision_id: premise decisions require a stable non-empty string ID")
    settled = case.get("settled_decision_ids", [])
    if not isinstance(settled, list) or any(not isinstance(item, str) or not item for item in settled):
        raise ValueError("settled_decision_ids: expected a list of non-empty strings")

    if decision_id and decision_id in settled and not contradictory:
        route = "reuse-settled"
        reason = f"Decision {decision_id} is settled and no contradictory evidence invalidates it."
    elif case.get("cheap_investigation") is True:
        route = "investigate"
        reason = "A cheap investigation can resolve the premise without interrupting the user."
    elif (
        premise_risk >= threshold["premise_risk"]
        and question_value > threshold["question_value_gt"]
        and (case.get("changes_work_graph") is True or case.get("irreversible") is True)
        and case.get("safe_reversible_default") is not True
    ):
        route = "ask"
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
            "profile_disclosed": False,
            "contradictory_evidence_ids": list(contradictory),
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
    provenance = _provenance(case)
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
        raise ValueError("available_specialist_slots: expected a non-negative integer")

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
        within_authority = case.get("authority_allows") is True
        available_route = case.get("platform_available") is True and available >= exact
        within_envelope = case.get("fits_job_envelope") is True
        has_done_condition = case.get("observable_done_condition") is True
        if within_authority and available_route and within_envelope and has_done_condition:
            route = "delegate"
            specialist_count = exact
            reason = f"The exact request for {exact} specialist(s) overrides economic margins within authority and capacity."
        else:
            route = "ask-resolution"
            question_count = 1
            reason = "The exact request lacks an observable done condition or cannot fit current authority, availability, or the active job envelope."
    elif (
        value >= margin
        and value > 0
        and strong_benefit
        and case.get("observable_done_condition") is True
        and case.get("fits_job_envelope") is True
        and case.get("platform_available") is True
        and case.get("authority_allows") is True
        and available >= 1
    ):
        route = "delegate"
        specialist_count = 1
        reason = "Benefit minus coordination cost meets the margin with a strong benefit and executable boundary."
    else:
        route = "inline"
        specialist_count = 0
        reason = "Delegation does not clear every economic, evidence, authority, and envelope gate."

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
            "question_count": question_count,
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
    provenance = _provenance(case)
    defect = _score(case.get("defect_likelihood"), "defect_likelihood")
    impact = _score(case.get("impact"), "impact")
    detection = _score(case.get("detection_likelihood"), "detection_likelihood")
    cost = _score(case.get("review_cost"), "review_cost")
    product = defect * impact * detection
    value = product - cost
    profile = config.get("profile")
    verification = config.get("verification")
    if not isinstance(verification, Mapping):
        raise ValueError("config.verification: expected an object")
    margin = REVIEW_MARGINS.get(profile, verification.get("review_margin"))
    if isinstance(margin, bool) or not isinstance(margin, int) or not 1 <= margin <= 27:
        raise ValueError("config.verification.review_margin: expected 1 to 27")
    mandatory = bool(
        case.get("mandatory_independent_review")
        or case.get("consequential_weak_oracle")
        or verification.get("mandatory_independent_review")
    )
    available = case.get("independent_review_available") is True
    compensating = case.get("compensating_oracle")
    accepted = case.get("user_accepts_compensating_oracle") is True

    if mandatory and not available:
        if isinstance(compensating, str) and compensating.strip() and accepted:
            route = "degraded-compensating-oracle"
            reason = "Mandatory independent review is unavailable; a named compensating oracle was explicitly accepted."
        else:
            route = "blocked"
            reason = "Mandatory independent review is unavailable and cannot be silently waived."
    elif mandatory:
        route = "independent-review"
        reason = "Independent review is an explicit or consequential-work execution constraint."
    elif value >= margin and available:
        route = "independent-review"
        reason = "Expected review value meets the profile threshold and an independent reviewer is available."
    else:
        route = "self-check"
        reason = "Independent review does not meet the calculated threshold or is unavailable for optional review."

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
    result.update({"mandatory": mandatory, "review_available": available, "compensating_oracle": compensating})
    return result


def compare_routes(
    routes: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    *,
    independence_mandatory: bool = False,
) -> dict[str, Any]:
    """Compare normalized whole-job utility after mandatory gates have passed."""
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
    for candidate in routes:
        if not isinstance(candidate, Mapping):
            raise ValueError("routes: every route must be an object")
        route_id = candidate.get("id")
        if not isinstance(route_id, str) or not route_id or route_id in utilities:
            raise ValueError("routes.id: expected unique non-empty strings")
        evidence_by_route[route_id] = _evidence(candidate)
        provenance = _provenance(candidate)
        provenance_by_route[route_id] = provenance
        factor_values = {key: _score(candidate.get(key), key) for key in UTILITY_KEYS}
        factors_by_route[route_id] = factor_values
        utility = (
            weights["quality"] * factor_values["expected_quality"]
            - weights["cost"] * factor_values["total_job_cost"]
            - weights["latency"] * factor_values["critical_path_latency"]
            - weights["attention"] * factor_values["user_interruption_cost"]
            - weights["rework"] * factor_values["expected_rework_risk"]
        )
        provenance_unknown = provenance == "unknown" or (
            isinstance(provenance, Mapping) and any(value == "unknown" for value in provenance.values())
        )
        gates_pass = candidate.get("mandatory_gates_passed") is True
        if not gates_pass or provenance_unknown:
            utilities[route_id] = None
            ineligible.append(route_id)
        else:
            rounded = round(utility, 12)
            utilities[route_id] = rounded
            eligible.append((route_id, candidate, rounded))

    if independence_mandatory:
        independent = [item for item in eligible if item[1].get("independence") is True]
        eligible = independent
    if not eligible:
        inline = next((item for item in routes if item.get("route") == "inline" or item.get("id") == "inline"), None)
        chosen = str(inline.get("id")) if inline is not None else "blocked"
        reason = "No evidenced route passed the mandatory gates; utility remains explanatory only."
    else:
        best = max(item[2] for item in eligible)
        tied = [item for item in eligible if abs(item[2] - best) <= 1e-12]
        inline = next((item for item in tied if item[1].get("route") == "inline" or item[0] == "inline"), None)
        selected = inline if inline is not None and not independence_mandatory else tied[0]
        chosen = selected[0]
        reason = (
            "Utility tied, so authority defaults to inline execution."
            if len(tied) > 1 and inline is not None and not independence_mandatory
            else "The route has the greatest eligible normalized whole-job utility."
        )

    return {
        "route": chosen,
        "factors": factors_by_route,
        "evidence_ids": evidence_by_route,
        "threshold": "greatest eligible utility; ties inline unless independence is mandatory",
        "margin": None,
        "provenance": provenance_by_route,
        "reason": reason,
        "utilities": utilities,
        "ineligible_routes": ineligible,
        "behaviors": [],
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
        return compare_routes(routes, config, independence_mandatory=bool(item.get("independence_mandatory")))
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
        fixture_id = fixture.get("id")
        if not isinstance(fixture_id, str) or not fixture_id or fixture_id in seen:
            raise ValueError("routing case IDs must be unique non-empty strings")
        seen.add(fixture_id)
        expected = fixture.get("expected_route")
        prohibited = fixture.get("prohibited_behaviors")
        if not isinstance(expected, str) or not isinstance(prohibited, list) or any(not isinstance(item, str) for item in prohibited):
            raise ValueError(f"{fixture_id}: expected_route and prohibited_behaviors are required")
        config = load_effective_config(ROOT, task_override=fixture.get("config_override"))
        result = _evaluate_fixture(fixture, config)
        if result["route"] != expected:
            raise ValueError(f"{fixture_id}: expected {expected!r}, calculated {result['route']!r}")
        present = set(result.get("behaviors", [])) & set(prohibited)
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
