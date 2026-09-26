from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.evaluate_routing import (
    compare_routes,
    detect_prohibited_behaviors,
    score_delegation,
    score_premise,
    score_review,
    validate_manifest,
)
from scripts.orchestration_config import load_effective_config


ROOT = Path(__file__).resolve().parents[2]


def evidence(*ids: str) -> list[str]:
    return list(ids or ("evidence:fixture",))


def premise_case(**overrides):
    case = {
        "id": "premise-base",
        "wrongness_likelihood": 2,
        "rework_cost": 2,
        "expected_rework_avoided": 4,
        "user_attention_cost": 1,
        "changes_work_graph": True,
        "irreversible": False,
        "cheap_investigation": False,
        "safe_reversible_default": False,
        "decision_id": "decision:auth-owner",
        "settled_decision_ids": [],
        "contradiction_evidence_ids": [],
        "evidence_ids": evidence("source:user-request"),
        "provenance": "observed",
    }
    case.update(overrides)
    return case


def delegation_case(**overrides):
    case = {
        "id": "delegation-base",
        "benefits": {"parallel": 2, "independence": 0, "context": 1, "quality": 1},
        "costs": {"setup": 1, "transfer": 0, "merge": 0, "review_rework": 0},
        "observable_done_condition": True,
        "fits_job_envelope": True,
        "available_specialist_slots": 3,
        "platform_available": True,
        "authority_allows": True,
        "evidence_ids": evidence("plan:dependency-graph"),
        "provenance": "estimated",
    }
    case.update(overrides)
    return case


def review_case(**overrides):
    case = {
        "id": "review-base",
        "defect_likelihood": 2,
        "impact": 2,
        "detection_likelihood": 2,
        "review_cost": 2,
        "independent_review_available": True,
        "mandatory_independent_review": False,
        "consequential_weak_oracle": False,
        "compensating_oracle": None,
        "user_accepts_compensating_oracle": False,
        "evidence_ids": evidence("tests:targeted"),
        "provenance": "estimated",
    }
    case.update(overrides)
    return case


def route(route_id: str, **overrides):
    candidate = {
        "id": route_id,
        "route": route_id,
        "expected_quality": 2,
        "total_job_cost": 1,
        "critical_path_latency": 1,
        "user_interruption_cost": 0,
        "expected_rework_risk": 1,
        "mandatory_gates_passed": True,
        "independence": route_id != "inline",
        "evidence_ids": evidence(f"estimate:{route_id}"),
        "provenance": "estimated",
    }
    candidate.update(overrides)
    return candidate


class PremiseCalculationTests(unittest.TestCase):
    def test_formula_and_material_question_boundary(self):
        result = score_premise(premise_case())

        self.assertEqual(result["factors"]["premise_risk"], 4)
        self.assertEqual(result["factors"]["question_value"], 3)
        self.assertEqual(result["threshold"], {"premise_risk": 4, "question_value_gt": 0})
        self.assertEqual(result["route"], "ask")

    def test_discoverable_fact_is_investigated_even_at_high_risk(self):
        result = score_premise(premise_case(wrongness_likelihood=3, rework_cost=3, expected_rework_avoided=9, cheap_investigation=True))
        self.assertEqual(result["route"], "investigate")

    def test_reversible_low_risk_choice_defaults(self):
        result = score_premise(
            premise_case(
                wrongness_likelihood=1,
                rework_cost=2,
                expected_rework_avoided=2,
                safe_reversible_default=True,
                changes_work_graph=False,
            )
        )
        self.assertEqual(result["route"], "default")

    def test_settled_decision_is_not_reasked_without_contradiction(self):
        result = score_premise(premise_case(settled_decision_ids=["decision:auth-owner"]))
        self.assertEqual(result["route"], "reuse-settled")
        self.assertFalse(result["ask_user"])
        self.assertEqual(result["decision_id"], "decision:auth-owner")

    def test_contradictory_evidence_invalidates_settled_decision(self):
        result = score_premise(
            premise_case(
                settled_decision_ids=["decision:auth-owner"],
                contradiction_evidence_ids=["source:new-contract"],
            )
        )
        self.assertEqual(result["route"], "ask")
        self.assertIn("source:new-contract", result["evidence_ids"])
        self.assertEqual(result["invalidated_decision_id"], "decision:auth-owner")
        self.assertEqual(result["contradiction_evidence_ids"], ["source:new-contract"])
        self.assertIn("decision:auth-owner", result["reason"])
        self.assertIn("source:new-contract", result["reason"])

    def test_direct_fast_path_has_no_scoring_or_profile_chatter(self):
        result = score_premise({"id": "direct", "direct_fast_path": True})
        self.assertEqual(result["route"], "direct")
        self.assertEqual(result["factors"], {})
        self.assertFalse(result["profile_disclosed"])
        self.assertIsNone(result["decision_id"])

    def test_invalid_or_unexplained_premise_score_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "wrongness_likelihood"):
            score_premise(premise_case(wrongness_likelihood=4))
        with self.assertRaisesRegex(ValueError, "evidence_ids"):
            score_premise(premise_case(evidence_ids=[]))
        with self.assertRaisesRegex(ValueError, "cannot exceed premise_risk"):
            score_premise(premise_case(expected_rework_avoided=5))
        with self.assertRaisesRegex(ValueError, "decision_id"):
            score_premise(premise_case(decision_id=""))


class DelegationCalculationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_effective_config(ROOT)

    def test_benefit_minus_cost_and_profile_margins(self):
        expected = {"economy": "delegate", "balanced": "delegate", "quality": "delegate", "custom": "inline"}
        for profile, expected_route in expected.items():
            with self.subTest(profile=profile):
                override = {"profile": profile}
                if profile == "custom":
                    override["team_limits"] = {"delegation_margin": 4}
                config = load_effective_config(ROOT, task_override=override)
                result = score_delegation(delegation_case(), config)
                self.assertEqual(result["factors"]["delegation_value"], 3)
                self.assertEqual(result["route"], expected_route)

    def test_margin_requires_strong_benefit_done_condition_and_envelope(self):
        weak = delegation_case(
            benefits={"parallel": 1, "independence": 1, "context": 1, "quality": 1},
            costs={"setup": 1, "transfer": 0, "merge": 0, "review_rework": 0},
        )
        self.assertEqual(score_delegation(weak, self.config)["route"], "inline")
        self.assertEqual(score_delegation(delegation_case(observable_done_condition=False), self.config)["route"], "inline")
        self.assertEqual(score_delegation(delegation_case(fits_job_envelope=False), self.config)["route"], "inline")

    def test_inline_only_and_exact_zero_stay_inline(self):
        inline = load_effective_config(ROOT, task_override={"mode": "inline-only"})
        exact_zero = load_effective_config(ROOT, task_override={"team_limits": {"exact_specialists": 0}})
        self.assertEqual(score_delegation(delegation_case(), inline)["route"], "inline")
        self.assertEqual(score_delegation(delegation_case(), exact_zero)["route"], "inline")

    def test_team_requested_economy_lowers_margin_but_never_spawns_at_zero(self):
        config = load_effective_config(ROOT, task_override={"mode": "team-requested", "profile": "economy"})
        positive = delegation_case(
            benefits={"parallel": 2, "independence": 0, "context": 0, "quality": 0},
            costs={"setup": 1, "transfer": 0, "merge": 0, "review_rework": 0},
        )
        zero = deepcopy(positive)
        zero["costs"]["setup"] = 2
        self.assertEqual(score_delegation(positive, config)["margin"], 1)
        self.assertEqual(score_delegation(positive, config)["route"], "delegate")
        self.assertEqual(score_delegation(zero, config)["route"], "inline")

    def test_custom_margin_override_is_explicit(self):
        blocked = load_effective_config(
            ROOT,
            task_override={"mode": "team-requested", "profile": "custom", "team_limits": {"delegation_margin": 4}},
        )
        allowed = load_effective_config(
            ROOT,
            task_override={
                "mode": "team-requested",
                "profile": "custom",
                "team_limits": {"delegation_margin": 4, "allow_mode_margin_override": True},
            },
        )
        self.assertEqual(score_delegation(delegation_case(), blocked)["margin"], 4)
        self.assertEqual(score_delegation(delegation_case(), blocked)["route"], "inline")
        self.assertEqual(score_delegation(delegation_case(), allowed)["margin"], 1)
        self.assertEqual(score_delegation(delegation_case(), allowed)["route"], "delegate")

    def test_exact_one_overrides_economics_within_authority(self):
        config = load_effective_config(ROOT, task_override={"team_limits": {"exact_specialists": 1}})
        uneconomic = delegation_case(
            benefits={"parallel": 0, "independence": 0, "context": 0, "quality": 0},
            costs={"setup": 3, "transfer": 3, "merge": 3, "review_rework": 3},
        )
        result = score_delegation(uneconomic, config)
        self.assertEqual(result["route"], "delegate")
        self.assertEqual(result["specialist_count"], 1)
        self.assertEqual(result["factors"]["delegation_value"], -12)

    def test_exact_above_normal_cap_requires_slots_and_envelope(self):
        config = load_effective_config(
            ROOT,
            task_override={"team_limits": {"exact_specialists": 5, "max_active_specialists": 3}},
            detected_host_max=8,
        )
        available = score_delegation(delegation_case(available_specialist_slots=5), config)
        unavailable = score_delegation(delegation_case(available_specialist_slots=4), config)
        no_envelope = score_delegation(delegation_case(available_specialist_slots=5, fits_job_envelope=False), config)
        self.assertEqual(available["route"], "delegate")
        self.assertEqual(available["specialist_count"], 5)
        self.assertEqual(unavailable["route"], "ask-resolution")
        self.assertEqual(unavailable["specialist_count"], 0)
        self.assertEqual(no_envelope["route"], "ask-resolution")
        self.assertEqual(no_envelope["specialist_count"], 0)

    def test_exact_request_does_not_override_observable_done_condition(self):
        config = load_effective_config(ROOT, task_override={"team_limits": {"exact_specialists": 1}})

        result = score_delegation(delegation_case(observable_done_condition=False), config)

        self.assertEqual(result["route"], "ask-resolution")
        self.assertEqual(result["question_count"], 1)

    def test_incompatible_explicit_controls_ask_once(self):
        config = load_effective_config(
            ROOT,
            task_override={"mode": "inline-only", "team_limits": {"exact_specialists": 2}},
        )
        result = score_delegation(delegation_case(), config)
        self.assertEqual(result["route"], "ask-resolution")
        self.assertEqual(result["question_count"], 1)
        self.assertEqual(result["specialist_count"], 0)

    def test_invalid_or_unexplained_delegation_factor_is_rejected(self):
        case = delegation_case()
        case["benefits"]["quality"] = -1
        with self.assertRaisesRegex(ValueError, "benefits.quality"):
            score_delegation(case, self.config)
        with self.assertRaisesRegex(ValueError, "evidence_ids"):
            score_delegation(delegation_case(evidence_ids=[]), self.config)


class ReviewCalculationTests(unittest.TestCase):
    def test_product_minus_cost_and_profile_thresholds(self):
        for profile, expected_route in {"economy": "self-check", "balanced": "independent-review", "quality": "independent-review"}.items():
            with self.subTest(profile=profile):
                config = load_effective_config(ROOT, task_override={"profile": profile})
                result = score_review(review_case(defect_likelihood=1, impact=2, detection_likelihood=2, review_cost=1), config)
                self.assertEqual(result["factors"]["review_value"], 3)
                self.assertEqual(result["route"], expected_route)

    def test_custom_review_margin_is_honored(self):
        config = load_effective_config(ROOT, task_override={"profile": "custom", "verification": {"review_margin": 9}})
        self.assertEqual(score_review(review_case(), config)["route"], "self-check")

    def test_user_mandated_review_overrides_calculation(self):
        config = load_effective_config(ROOT)
        result = score_review(review_case(defect_likelihood=0, impact=0, detection_likelihood=0, review_cost=3, mandatory_independent_review=True), config)
        self.assertEqual(result["route"], "independent-review")

    def test_mandatory_review_unavailable_blocks_or_requires_accepted_compensation(self):
        config = load_effective_config(ROOT)
        blocked = score_review(review_case(mandatory_independent_review=True, independent_review_available=False), config)
        degraded = score_review(
            review_case(
                mandatory_independent_review=True,
                independent_review_available=False,
                compensating_oracle="deterministic:signed-artifact",
                user_accepts_compensating_oracle=True,
            ),
            config,
        )
        self.assertEqual(blocked["route"], "blocked")
        self.assertEqual(degraded["route"], "degraded-compensating-oracle")

    def test_invalid_or_unexplained_review_factor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "impact"):
            score_review(review_case(impact=4), load_effective_config(ROOT))
        with self.assertRaisesRegex(ValueError, "evidence_ids"):
            score_review(review_case(evidence_ids=[]), load_effective_config(ROOT))


class UtilityCalculationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_effective_config(ROOT)

    def test_normalized_weighted_utility_selects_greatest_route(self):
        result = compare_routes(
            [
                route("inline", expected_quality=1, total_job_cost=1, expected_rework_risk=2),
                route("specialist", expected_quality=3, total_job_cost=2, expected_rework_risk=1),
            ],
            self.config,
        )
        self.assertEqual(result["route"], "specialist")
        self.assertAlmostEqual(result["utilities"]["inline"], -0.15)
        self.assertAlmostEqual(result["utilities"]["specialist"], 0.70)

    def test_inline_wins_exact_utility_tie(self):
        result = compare_routes([route("specialist"), route("inline")], self.config)
        self.assertEqual(result["route"], "inline")

    def test_mandatory_independence_breaks_tie_away_from_inline(self):
        result = compare_routes(
            [route("inline"), route("fresh-review", independence=True)],
            self.config,
            independence_mandatory=True,
        )
        self.assertEqual(result["route"], "fresh-review")

    def test_failed_gate_and_unknown_inputs_cannot_win(self):
        result = compare_routes(
            [
                route("inline", expected_quality=1),
                route("unsafe", expected_quality=3, mandatory_gates_passed=False),
                route("unknown", expected_quality=3, provenance="unknown"),
            ],
            self.config,
        )
        self.assertEqual(result["route"], "inline")
        self.assertIn("unsafe", result["ineligible_routes"])
        self.assertIn("unknown", result["ineligible_routes"])

    def test_no_eligible_route_blocks_without_selecting_inline(self):
        result = compare_routes(
            [
                route("inline", mandatory_gates_passed=False),
                route("worker", provenance="unknown"),
            ],
            self.config,
        )
        self.assertEqual(result["route"], "blocked")
        self.assertIsNone(result["selected_route_id"])

    def test_mandatory_independence_blocks_without_eligible_independent_route(self):
        result = compare_routes(
            [route("inline"), route("worker", independence=True, mandatory_gates_passed=False)],
            self.config,
            independence_mandatory=True,
        )
        self.assertEqual(result["route"], "blocked")
        self.assertIsNone(result["selected_route_id"])

    def test_non_inline_tie_requires_inline_instead_of_arbitrary_worker(self):
        result = compare_routes([route("worker-a"), route("worker-b")], self.config)
        self.assertEqual(result["route"], "inline-required")
        self.assertIsNone(result["selected_route_id"])

    def test_worker_named_inline_is_not_treated_as_inline_route(self):
        disguised = route("inline", route="worker")
        result = compare_routes([disguised, route("worker-b")], self.config)
        self.assertEqual(result["route"], "inline-required")
        self.assertIsNone(result["selected_route_id"])

    def test_out_of_range_or_unexplained_utility_factor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "expected_quality"):
            compare_routes([route("inline", expected_quality=4)], self.config)
        with self.assertRaisesRegex(ValueError, "evidence_ids"):
            compare_routes([route("inline", evidence_ids=[])], self.config)


class RoutingSafeguardTests(unittest.TestCase):
    def setUp(self):
        self.config = load_effective_config(ROOT)

    def test_scorer_specific_provenance_maps_require_exact_keys(self):
        premise_provenance = {
            "wrongness_likelihood": "observed",
            "rework_cost": "estimated",
            "expected_rework_avoided": "estimated",
            "user_attention_cost": "observed",
        }
        delegation_provenance = {
            **{f"benefits.{name}": "estimated" for name in ("parallel", "independence", "context", "quality")},
            **{f"costs.{name}": "estimated" for name in ("setup", "transfer", "merge", "review_rework")},
        }
        review_provenance = {
            "defect_likelihood": "estimated",
            "impact": "observed",
            "detection_likelihood": "estimated",
            "review_cost": "observed",
        }
        utility_provenance = {
            "expected_quality": "estimated",
            "total_job_cost": "observed",
            "critical_path_latency": "estimated",
            "user_interruption_cost": "observed",
            "expected_rework_risk": "estimated",
        }

        self.assertEqual(score_premise(premise_case(provenance=premise_provenance))["provenance"], premise_provenance)
        self.assertTrue(score_delegation(delegation_case(provenance=delegation_provenance), self.config)["economics_known"])
        self.assertTrue(score_review(review_case(provenance=review_provenance), self.config)["economics_known"])
        self.assertEqual(compare_routes([route("inline", provenance=utility_provenance)], self.config)["route"], "inline")

        for bad in (
            {"wrongness_likelihood": "observed"},
            {**premise_provenance, "surprise": "observed"},
            {**premise_provenance, "rework_cost": "measured"},
            {**premise_provenance, "rework_cost": []},
        ):
            with self.subTest(provenance=bad):
                with self.assertRaisesRegex(ValueError, r"\$\.provenance"):
                    score_premise(premise_case(provenance=bad))

    def test_unknown_economics_cannot_trigger_optional_delegation_or_review(self):
        delegated = score_delegation(delegation_case(provenance="unknown"), self.config)
        reviewed = score_review(review_case(provenance="unknown"), self.config)
        self.assertEqual(delegated["route"], "inline")
        self.assertFalse(delegated["economics_known"])
        self.assertEqual(reviewed["route"], "self-check")
        self.assertFalse(reviewed["economics_known"])

    def test_explicit_constraints_route_with_unknown_economics_but_report_unknown(self):
        exact = load_effective_config(ROOT, task_override={"team_limits": {"exact_specialists": 1}})
        delegated = score_delegation(delegation_case(provenance="unknown"), exact)
        reviewed = score_review(review_case(provenance="unknown", mandatory_independent_review=True), self.config)
        self.assertEqual(delegated["route"], "delegate")
        self.assertFalse(delegated["economics_known"])
        self.assertEqual(delegated["economics_status"], "unknown")
        self.assertEqual(reviewed["route"], "independent-review")
        self.assertFalse(reviewed["economics_known"])
        self.assertEqual(reviewed["economics_status"], "unknown")

    def test_utility_requires_complete_known_provenance(self):
        incomplete = {
            "expected_quality": "estimated",
            "total_job_cost": "observed",
        }
        with self.assertRaisesRegex(ValueError, r"\$\.routes\[0\]\.provenance"):
            compare_routes([route("inline", provenance=incomplete)], self.config)
        unknown = route(
            "inline",
            provenance={
                "expected_quality": "estimated",
                "total_job_cost": "observed",
                "critical_path_latency": "unknown",
                "user_interruption_cost": "observed",
                "expected_rework_risk": "estimated",
            },
        )
        result = compare_routes([unknown], self.config)
        self.assertEqual(result["route"], "blocked")
        self.assertIsNone(result["selected_route_id"])

    def test_case_and_route_controls_require_real_booleans(self):
        cases = [
            (lambda: score_premise(premise_case(changes_work_graph="true")), r"\$\.changes_work_graph"),
            (lambda: score_premise(premise_case(direct_fast_path="false")), r"\$\.direct_fast_path"),
            (lambda: score_premise({"direct_fast_path": True, "changes_work_graph": "yes"}), r"\$\.changes_work_graph"),
            (lambda: score_delegation(delegation_case(authority_allows=1), self.config), r"\$\.authority_allows"),
            (lambda: score_delegation(delegation_case(platform_available="yes"), self.config), r"\$\.platform_available"),
            (lambda: score_review(review_case(independent_review_available="yes"), self.config), r"\$\.independent_review_available"),
            (lambda: score_review(review_case(mandatory_independent_review=1), self.config), r"\$\.mandatory_independent_review"),
            (lambda: compare_routes([route("inline", mandatory_gates_passed="true")], self.config), r"\$\.routes\[0\]\.mandatory_gates_passed"),
            (lambda: compare_routes([route("inline", independence=0)], self.config), r"\$\.routes\[0\]\.independence"),
            (lambda: compare_routes([route("inline")], self.config, independence_mandatory="yes"), r"\$\.independence_mandatory"),
        ]
        for invoke, path in cases:
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, path):
                    invoke()

    def test_observable_behavior_detectors_are_not_vacuous(self):
        delegated = score_delegation(delegation_case(), self.config)
        settled = score_premise(premise_case(settled_decision_ids=["decision:auth-owner"]))
        degraded = score_review(
            review_case(
                mandatory_independent_review=True,
                independent_review_available=False,
                compensating_oracle="deterministic:signed-artifact",
                user_accepts_compensating_oracle=True,
            ),
            self.config,
        )
        self.assertEqual(delegated["spawn_count"], 1)
        self.assertEqual(detect_prohibited_behaviors(delegated, ["spawn"]), ["spawn"])
        self.assertFalse(settled["repeated_question"])
        self.assertEqual(detect_prohibited_behaviors(settled, ["question", "repeated-question"]), [])
        self.assertEqual(degraded["status"], "degraded")
        self.assertEqual(degraded["review_coverage"], "compensating")
        self.assertEqual(detect_prohibited_behaviors(degraded, ["degraded", "missing-review-coverage"]), ["degraded"])
        with self.assertRaisesRegex(ValueError, "unknown prohibited behavior"):
            detect_prohibited_behaviors(delegated, ["telepathy"])

    def test_manifest_rejects_real_prohibited_behavior_and_unknown_name(self):
        manifest = json.loads((ROOT / "tests" / "team-routing.json").read_text(encoding="utf-8"))
        delegated = next(item for item in manifest["cases"] if item["id"] == "delegation-high-value-independent-work")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "routing.json"
            failing = {"schema_version": 1, "cases": [deepcopy(delegated)]}
            failing["cases"][0]["prohibited_behaviors"] = ["spawn"]
            path.write_text(json.dumps(failing), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "prohibited behaviors present.*spawn"):
                validate_manifest(path)

            failing["cases"][0]["prohibited_behaviors"] = ["telepathy"]
            path.write_text(json.dumps(failing), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown prohibited behavior"):
                validate_manifest(path)

    def test_whitespace_only_decision_and_evidence_identifiers_are_rejected(self):
        invalid_cases = [
            (lambda: score_premise(premise_case(decision_id=" \t ")), "decision_id"),
            (lambda: score_premise(premise_case(evidence_ids=[" \t "])), "evidence_ids"),
            (lambda: score_premise(premise_case(settled_decision_ids=[" \t "])), "settled_decision_ids"),
            (
                lambda: score_premise(
                    premise_case(
                        settled_decision_ids=["decision:auth-owner"],
                        contradiction_evidence_ids=[" \t "],
                    )
                ),
                "contradiction_evidence_ids",
            ),
            (
                lambda: score_review(
                    review_case(
                        mandatory_independent_review=True,
                        independent_review_available=False,
                        compensating_oracle=" \t ",
                    ),
                    self.config,
                ),
                "compensating_oracle",
            ),
        ]
        for invoke, field in invalid_cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, field):
                    invoke()

    def test_whitespace_only_route_identifiers_are_rejected(self):
        with self.assertRaisesRegex(ValueError, r"\$\.routes\[0\]\.id"):
            compare_routes([route(" \t ")], self.config)
        with self.assertRaisesRegex(ValueError, r"\$\.routes\[0\]\.route"):
            compare_routes([route("valid", route=" \t ")], self.config)

    def test_whitespace_only_fixture_and_expected_route_identifiers_are_rejected(self):
        manifest = json.loads((ROOT / "tests" / "team-routing.json").read_text(encoding="utf-8"))
        fixture = deepcopy(manifest["cases"][0])
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "routing.json"
            fixture["id"] = " \t "
            path.write_text(json.dumps({"schema_version": 1, "cases": [fixture]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"\$\.cases\[\]\.id"):
                validate_manifest(path)

            fixture["id"] = "fixture:valid"
            fixture["expected_route"] = " \t "
            path.write_text(json.dumps({"schema_version": 1, "cases": [fixture]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expected_route"):
                validate_manifest(path)

    def test_valid_identifiers_preserve_original_whitespace(self):
        premise = score_premise(
            premise_case(
                decision_id=" decision:auth-owner ",
                evidence_ids=[" source:user-request "],
            )
        )
        utility = compare_routes([route(" route:inline ", route="inline")], self.config)
        self.assertEqual(premise["decision_id"], " decision:auth-owner ")
        self.assertEqual(premise["evidence_ids"], [" source:user-request "])
        self.assertEqual(utility["route"], " route:inline ")
        self.assertEqual(utility["selected_route_id"], " route:inline ")


class RoutingScenarioTests(unittest.TestCase):
    def test_fixture_cases_match_routes_and_prohibited_behaviors(self):
        manifest = json.loads((ROOT / "tests" / "team-routing.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertGreaterEqual(len(manifest["cases"]), 10)
        config = load_effective_config(ROOT)
        evaluators = {
            "premise": lambda item, effective: score_premise(item),
            "delegation": score_delegation,
            "review": score_review,
            "utility": lambda item, effective: compare_routes(item["routes"], effective, independence_mandatory=item.get("independence_mandatory", False)),
        }
        for fixture in manifest["cases"]:
            with self.subTest(case=fixture["id"]):
                effective = load_effective_config(ROOT, task_override=fixture.get("config_override"))
                result = evaluators[fixture["kind"]](fixture["input"], effective)
                self.assertEqual(result["route"], fixture["expected_route"])
                self.assertEqual(detect_prohibited_behaviors(result, fixture["prohibited_behaviors"]), [])

    def test_cli_reports_validated_case_count(self):
        manifest = json.loads((ROOT / "tests" / "team-routing.json").read_text(encoding="utf-8"))
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "evaluate_routing.py"), str(ROOT / "tests" / "team-routing.json")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn(f"TEAM ROUTING VALIDATION PASSED ({len(manifest['cases'])} cases)", completed.stdout)


if __name__ == "__main__":
    unittest.main()
