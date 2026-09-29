"""Typed normative formula diagnostics for behavioral case contracts."""
from __future__ import annotations
import math
from collections.abc import Mapping
from typing import Any
PROFILE_WEIGHTS = {
    "economy": {"quality": 0.35, "cost": 0.35, "latency": 0.10, "attention": 0.10, "rework": 0.10},
    "balanced": {"quality": 0.45, "cost": 0.20, "latency": 0.10, "attention": 0.10, "rework": 0.15},
    "quality": {"quality": 0.50, "cost": 0.10, "latency": 0.05, "attention": 0.10, "rework": 0.25},
}
REVIEW_MARGINS = {"economy": 6, "balanced": 3, "quality": 1}


def _compute_semantic_result(formula_id: str, inputs: Mapping[str, Any]) -> dict[str, Any] | None:
    specialists = int(inputs.get("specialist_count", 0))
    if formula_id == "policy.state-route.v1":
        routes = {
            "direct-fast-path": "direct",
            "inline-only": "inline",
            "incompatible-inline-and-exact": "resolution-question",
            "ambiguous-material-team-count": "resolution-question",
        }
        route = routes.get(str(inputs.get("policy_state")))
        return {"route": route, "specialist_count": specialists} if route else None
    if formula_id == "premise.gate.v1":
        premise_risk = int(inputs["wrongness_likelihood"]) * int(inputs["rework_cost"])
        avoided = int(inputs["expected_rework_avoided"])
        if avoided > premise_risk:
            return None
        question_value = avoided - int(inputs["user_attention_cost"])
        if inputs["settled_decision"] and not inputs["contradictory_evidence"]:
            route = "resume"
        elif inputs["cheap_investigation"]:
            route = "investigate"
        elif (
            premise_risk >= int(inputs["premise_risk_threshold"])
            and question_value > int(inputs["question_value_threshold"])
            and (inputs["changes_work_graph"] or inputs["irreversible"])
            and not inputs["safe_reversible_default"]
        ):
            route = "ask"
        else:
            route = "default"
        return {"premise_risk": premise_risk, "question_value": question_value, "route": route, "specialist_count": specialists}
    if formula_id == "delegation.gate.v1":
        benefits = [int(inputs[f"benefit_{name}"]) for name in ("parallel", "independence", "context", "quality")]
        costs = [int(inputs[f"cost_{name}"]) for name in ("setup", "transfer", "merge", "review_rework")]
        value = sum(benefits) - sum(costs)
        approved = (
            inputs["mode"] != "inline-only" and value > 0 and value >= int(inputs["margin"])
            and max(benefits) >= 2 and inputs["observable_done_condition"]
            and inputs["fits_job_envelope"] and inputs["platform_available"] and inputs["authority_allows"]
            and int(inputs["available_specialist_slots"]) >= 1
        )
        route = "delegate" if approved else "inline"
        return {"delegation_value": value, "route": route, "specialist_count": 1 if approved else 0}
    if formula_id == "utility.whole-job.v1":
        weights = {name: float(inputs[f"weight_{name}"]) for name in ("quality", "cost", "latency", "attention", "rework")}
        if weights != PROFILE_WEIGHTS.get(inputs["profile"]) or inputs["utility_tie_policy"] != "inline-unless-independence-mandatory":
            return None
        score = (
            weights["quality"] * int(inputs["expected_quality"])
            - weights["cost"] * int(inputs["total_job_cost"])
            - weights["latency"] * int(inputs["critical_path_latency"])
            - weights["attention"] * int(inputs["user_interruption_cost"])
            - weights["rework"] * int(inputs["expected_rework_risk"])
        )
        route = inputs["selected_route"] if inputs["mandatory_gates_passed"] else "blocked"
        return {"utility": score, "route": route, "specialist_count": specialists}
    if formula_id == "continuity.policy.v1":
        if inputs["independence_required"] or inputs["responsibility_conflict"]:
            route = "fresh"
        elif inputs["previous_attempt_failed"] and not inputs["new_evidence_or_hypothesis"]:
            route = "blocked"
        elif (
            inputs["native_handle_current"] and inputs["direct_continuation"]
            and inputs["costly_local_exploration_needed"] and inputs["registry_valid"]
            and inputs["capability_verified"]
        ):
            route = "resume"
        elif inputs["role_continuity_matters"] and inputs["capsule_sufficient"]:
            route = "rehydrate"
        else:
            route = "blocked"
        return {"route": route, "specialist_count": 1 if route in {"fresh", "rehydrate"} else 0}
    if formula_id == "review.gate.v1":
        product = int(inputs["defect_likelihood"]) * int(inputs["impact"]) * int(inputs["detection_likelihood"])
        value = product - int(inputs["review_cost"])
        approved_threshold = REVIEW_MARGINS.get(inputs["profile"])
        if approved_threshold != inputs["threshold"]:
            return None
        mandatory = inputs["mandatory"] or inputs["consequential_weak_oracle"]
        if mandatory and not inputs["reviewer_available"]:
            route = "blocked" if not inputs["accepted_compensating_oracle"] else "degraded"
        elif mandatory or (value >= approved_threshold and inputs["reviewer_available"]):
            route = "fresh"
        else:
            route = "inline"
        return {"review_product": product, "review_value": value, "route": route, "specialist_count": specialists}
    if formula_id == "budget.gate.v1":
        if not math.isclose(float(inputs["available"]) + float(inputs["reserved"]) + float(inputs["funded_consumed"]), float(inputs["ceiling"]), abs_tol=1e-9):
            return None
        if not math.isclose(float(inputs["total_consumed"]), float(inputs["funded_consumed"]) + float(inputs["unfunded_consumed"]), abs_tol=1e-9):
            return None
        enforcement_capable = (
            inputs["measurement"] == "observed" and inputs["observed_counter_verified"]
            and inputs["matching_stop_primitive_verified"]
        )
        if inputs["mandatory_enforcement"] and (inputs["enforcement"] == "advisory" or not enforcement_capable):
            route = "blocked"
        elif float(inputs["available"]) <= 0 or inputs["accepted_advisory_fallback"]:
            route = "degraded"
        else:
            route = "auto"
        return {"remaining": float(inputs["available"]), "route": route, "specialist_count": specialists}
    if formula_id == "allocation.reconciliation.v1":
        if not math.isclose(
            float(inputs["initial_reserved"]) + float(inputs["funded_reservation_overrun"]),
            float(inputs["active_reserved"]) + float(inputs["funded_consumed"]) + float(inputs["released_unused"]),
            abs_tol=1e-9,
        ):
            return None
        route = "degraded" if inputs["terminal_status"] == "timeout" else ("auto" if inputs["reconciliation_succeeded"] else "blocked")
        return {"active_reserved": inputs["active_reserved"], "funded_consumed": inputs["funded_consumed"], "released_unused": inputs["released_unused"], "route": route, "specialist_count": specialists}
    if formula_id == "team-sizing.policy.v1":
        gates = all(inputs[name] for name in ("authority_allows", "platform_available", "fits_job_envelope", "observable_done_condition"))
        exact = inputs["exact_specialists"]
        effective_host_max = min(32, int(inputs["detected_host_max"]))
        if exact == 0:
            return {"route": "inline", "specialist_count": 0}
        if exact is not None:
            fits = gates and exact <= effective_host_max and exact <= int(inputs["available_slots"]) and exact <= int(inputs["budget_capacity"])
            return {"route": "delegate" if fits else "resolution-question", "specialist_count": int(exact) if fits else 0}
        benefits = [int(inputs[f"benefit_{name}"]) for name in ("parallel", "independence", "context", "quality")]
        costs = [int(inputs[f"cost_{name}"]) for name in ("setup", "transfer", "merge", "review_rework")]
        value = sum(benefits) - sum(costs)
        count = min(int(inputs["independent_workstreams"]), int(inputs["max_active_specialists"]), effective_host_max, int(inputs["available_slots"]), int(inputs["budget_capacity"]))
        approved = gates and value > 0 and value >= int(inputs["delegation_margin"]) and max(benefits) >= 2 and count > 0
        return {"route": "delegate" if approved else "inline", "specialist_count": count if approved else 0}
    return None
