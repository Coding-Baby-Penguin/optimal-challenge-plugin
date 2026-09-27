from __future__ import annotations

from copy import deepcopy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import adversarial_review, evaluate_research_gate


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tests" / "research-gate.json"
POLICY = ROOT / "skills" / "optimal-challenge" / "references" / "high-cost-research.md"


class ResearchGateSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {
            case["id"]: case
            for case in json.loads(MANIFEST.read_text(encoding="utf-8"))
        }

    def result(self, case_id: str):
        return evaluate_research_gate.evaluate_case(self.cases[case_id])

    def test_costly_sticker_and_paid_batches_cannot_scale_before_research_and_pilot(self):
        for case_id in ("sticker-urgent-skip", "paid-images-120"):
            with self.subTest(case_id=case_id):
                result = self.result(case_id)
                self.assertIn(result["route"], {"research", "blocked-question"})
                self.assertIn("full-scale", result["prohibited_claims"])
                self.assertIn("acceptance-ready", result["prohibited_claims"])

    def test_cheap_single_draft_stays_direct(self):
        result = self.result("cheap-single-draft")
        self.assertEqual(result["route"], "direct")
        self.assertFalse(result["research_stop_met"])

    def test_authoritative_local_or_user_rubric_skips_research_but_not_pilot(self):
        for case_id in ("local-authoritative-rubric", "user-approved-rubric"):
            with self.subTest(case_id=case_id):
                result = self.result(case_id)
                self.assertEqual(result["route"], "pilot")
                self.assertTrue(result["research_stop_met"])
                self.assertNotIn("web-research-required", result["reasons"])

    def test_settled_representative_pilot_scales_without_reasking(self):
        result = self.result("approved-representative-pilot")
        self.assertEqual(result["route"], "scale")
        self.assertTrue(result["research_stop_met"])
        self.assertNotIn("question-bundle", result["required_artifacts"])

    def test_material_conflict_blocks_or_asks_once_while_nonmaterial_conflict_does_not(self):
        unresolved = self.result("material-authority-conflict")
        self.assertEqual(unresolved["route"], "research")
        self.assertFalse(unresolved["research_stop_met"])

        user_only = self.result("material-user-only-conflict")
        self.assertEqual(user_only["route"], "blocked-question")
        self.assertTrue(user_only["research_stop_met"])
        self.assertEqual(user_only["required_artifacts"].count("question-bundle"), 1)

        nonmaterial = self.result("nonmaterial-conflict")
        self.assertEqual(nonmaterial["route"], "pilot")
        self.assertTrue(nonmaterial["research_stop_met"])
        self.assertIn("disclose-nonmaterial-contradiction", nonmaterial["reasons"])

    def test_refusal_is_bounded_to_provisional_pilot_never_full_batch(self):
        result = self.result("refuse-research-and-pilot")
        self.assertEqual(result["route"], "provisional-pilot")
        self.assertEqual(result["maximum_output"], "smallest-adequate-pilot")
        self.assertIn("full-scale", result["prohibited_claims"])
        self.assertIn("acceptance-ready", result["prohibited_claims"])

    def test_task_override_cannot_prove_persistence_or_budget_enforcement(self):
        result = self.result("false-settings-claims")
        self.assertIn("durable-cloud-persistence", result["prohibited_claims"])
        self.assertIn("budget-enforcement", result["prohibited_claims"])

        case = deepcopy(self.cases["cheap-single-draft"])
        case["task_override_only"] = True
        case["claims_requested"] = ["durable-cloud-persistence", "budget-enforcement"]
        result = evaluate_research_gate.evaluate_case(case)
        self.assertEqual(result["route"], "direct")
        self.assertIn("durable-cloud-persistence", result["prohibited_claims"])
        self.assertIn("budget-enforcement", result["prohibited_claims"])

    def test_malformed_or_unknown_material_state_fails_closed(self):
        case = deepcopy(self.cases["approved-representative-pilot"])
        case["costly_scale"] = "yes"
        result = evaluate_research_gate.evaluate_case(case)
        self.assertEqual(result["route"], "blocked-question")
        self.assertIn("malformed-input", result["reasons"])

        case = deepcopy(self.cases["approved-representative-pilot"])
        case["question_bundle"] = {
            "recommendation": "irrelevant",
            "impact": "irrelevant",
            "safe_work": "irrelevant",
            "next_step": "irrelevant",
        }
        result = evaluate_research_gate.evaluate_case(case)
        self.assertEqual(result["route"], "blocked-question")
        self.assertIn("malformed-input", result["reasons"])

        case = deepcopy(self.cases["approved-representative-pilot"])
        case["unknown_material_state"] = True
        result = evaluate_research_gate.evaluate_case(case)
        self.assertEqual(result["route"], "blocked-question")
        self.assertIn("malformed-input", result["reasons"])

    def test_manifest_validator_recomputes_routes_and_rejects_permissive_evaluator(self):
        self.assertEqual(evaluate_research_gate.validate_manifest(MANIFEST), len(self.cases))

        def permissive(_case):
            return {
                "route": "scale",
                "research_stop_met": True,
                "maximum_output": "full-scale",
                "reasons": [],
                "required_artifacts": [],
                "prohibited_claims": [],
            }

        with self.assertRaisesRegex(ValueError, "mismatch"):
            evaluate_research_gate.validate_manifest(MANIFEST, evaluator=permissive)

    def test_cli_validates_scenario_contract(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "evaluate_research_gate.py"), str(MANIFEST)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"RESEARCH GATE VALIDATION PASSED ({len(self.cases)} cases)", result.stdout)


class ResearchGateAdversarialValidation(unittest.TestCase):
    def test_adversarial_validator_rejects_permissive_evaluator(self):
        policy = POLICY.read_text(encoding="utf-8")

        def permissive(_case):
            return {
                "route": "scale",
                "research_stop_met": True,
                "maximum_output": "full-scale",
                "reasons": [],
                "required_artifacts": [],
                "prohibited_claims": [],
            }

        issues = adversarial_review.research_gate_issues(
            {"high-cost-research.md": policy}, evaluator=permissive
        )
        self.assertIn("research gate", " ".join(issues).lower())

    def test_adversarial_validator_rejects_exposed_material_conflict_loophole(self):
        policy = POLICY.read_text(encoding="utf-8") + (
            "\nMaterial decision-changing contradictions may be resolved or exposed before scaling.\n"
        )
        issues = adversarial_review.research_gate_issues({"high-cost-research.md": policy})
        self.assertIn("resolved or exposed", " ".join(issues).lower())

    def test_integrated_validator_requires_research_contract(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Research-before-scale: PASSED", result.stdout)


if __name__ == "__main__":
    unittest.main()
