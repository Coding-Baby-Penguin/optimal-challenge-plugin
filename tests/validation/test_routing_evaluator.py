from __future__ import annotations

import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.evaluate_routing import compare_routes, score_delegation, score_premise, score_review
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
        "contradictory_evidence_ids": [],
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
                contradictory_evidence_ids=["source:new-contract"],
            )
        )
        self.assertEqual(result["route"], "ask")
        self.assertIn("source:new-contract", result["evidence_ids"])

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

    def test_out_of_range_or_unexplained_utility_factor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "expected_quality"):
            compare_routes([route("inline", expected_quality=4)], self.config)
        with self.assertRaisesRegex(ValueError, "evidence_ids"):
            compare_routes([route("inline", evidence_ids=[])], self.config)


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
                for behavior in fixture["prohibited_behaviors"]:
                    self.assertNotIn(behavior, result.get("behaviors", []))

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
