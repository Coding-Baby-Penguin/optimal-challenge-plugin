from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import replace
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import adversarial_review, evaluate_research_gate


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tests" / "research-gate.json"
REGISTRY = ROOT / "tests" / "fixtures" / "research" / "trusted-evidence.json"
POLICY = ROOT / "skills" / "optimal-challenge" / "references" / "high-cost-research.md"
EXPECTED_POLICY_SHA256 = "ed1e80822dc1de2f200235aa63f21894d0c7e63510b43c4aa9a77567de2ab02b"


class ResearchGateSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = evaluate_research_gate.load_fixture_evidence_context(REGISTRY)
        cls.cases = {case["id"]: case for case in json.loads(MANIFEST.read_text(encoding="utf-8"))}

    def result(self, case_id: str):
        return evaluate_research_gate.evaluate_case(self.cases[case_id], self.context)

    def test_costly_batches_research_while_cheap_draft_is_direct(self):
        for case_id in ("sticker-urgent-skip", "paid-images-120"):
            result = self.result(case_id)
            self.assertEqual(result["route"], "research")
            self.assertIn("full-scale", result["prohibited_claims"])
        self.assertEqual(self.result("cheap-single-draft")["route"], "direct")

    def test_authoritative_evidence_skips_research_but_still_requires_pilot(self):
        for case_id in ("local-authoritative-rubric", "user-approved-rubric"):
            self.assertEqual(self.result(case_id)["route"], "pilot")

    def test_exact_bound_approved_pilot_scales_without_reasking(self):
        result = self.result("approved-representative-pilot")
        self.assertEqual(result["route"], "scale")
        self.assertNotIn("question-bundle", result["required_artifacts"])

    def test_untrusted_flags_and_nonblank_ids_never_unlock_scale(self):
        case = deepcopy(self.cases["approved-representative-pilot"])
        case["pilot_passed"] = True
        self.assertEqual(evaluate_research_gate.evaluate_case(case, self.context)["route"], "blocked-question")
        case = deepcopy(self.cases["approved-representative-pilot"])
        case["pilot_evidence_ref"] = "forged-does-not-exist"
        case["settled_decision_id"] = "nonblank-is-not-proof"
        self.assertNotEqual(evaluate_research_gate.evaluate_case(case, self.context)["route"], "scale")

    def test_context_is_closed_identity_attested_and_copy_safe(self):
        case = self.cases["approved-representative-pilot"]
        self.assertEqual(evaluate_research_gate.evaluate_case(case, None)["route"], "blocked-question")
        for forged in (copy(self.context), replace(self.context), deepcopy(self.context)):
            self.assertEqual(evaluate_research_gate.evaluate_case(case, forged)["route"], "blocked-question")
        self.assertEqual(evaluate_research_gate.evaluate_case(case, self.context)["route"], "scale")

    def test_pilot_binding_mutations_invalidate_approval(self):
        fields = ("rubric_hash", "criteria_fingerprint", "input_fingerprint", "scope_fingerprint", "risk_fingerprint")
        for field in fields:
            case = deepcopy(self.cases["approved-representative-pilot"])
            case[field] = "f" * 64
            self.assertNotEqual(evaluate_research_gate.evaluate_case(case, self.context)["route"], "scale")
        case = deepcopy(self.cases["approved-representative-pilot"])
        case["material_risk_dimensions"].append("new-risk")
        self.assertNotEqual(evaluate_research_gate.evaluate_case(case, self.context)["route"], "scale")
        case = deepcopy(self.cases["approved-representative-pilot"])
        case["pilot_evidence_ref"] = "pilot-evidence-stale"
        self.assertNotEqual(evaluate_research_gate.evaluate_case(case, self.context)["route"], "scale")
        case = deepcopy(self.cases["approved-representative-pilot"])
        case["pilot_evidence_ref"] = None
        case["settled_decision_id"] = None
        self.assertEqual(evaluate_research_gate.evaluate_case(case, self.context)["route"], "pilot")

    def test_conflicts_require_bound_evidence_or_one_bundle(self):
        self.assertEqual(self.result("material-authority-conflict")["route"], "research")
        self.assertEqual(self.result("resolved-material-conflict")["route"], "pilot")
        blocked = self.result("material-user-only-conflict")
        self.assertEqual(blocked["route"], "blocked-question")
        self.assertEqual(blocked["required_artifacts"].count("question-bundle"), 1)
        self.assertEqual(self.result("resolved-user-only-conflict")["route"], "pilot")
        nonmaterial = self.result("nonmaterial-conflict")
        self.assertEqual(nonmaterial["route"], "pilot")
        self.assertIn("disclose-nonmaterial-contradiction", nonmaterial["reasons"])

    def test_resolution_flags_or_conflicting_state_fail_closed(self):
        case = deepcopy(self.cases["material-authority-conflict"])
        case["contradictions"][0]["resolved"] = True
        self.assertEqual(evaluate_research_gate.evaluate_case(case, self.context)["route"], "blocked-question")
        case = deepcopy(self.cases["resolved-user-only-conflict"])
        case["contradictions"][0]["user_only"] = False
        self.assertNotEqual(evaluate_research_gate.evaluate_case(case, self.context)["route"], "pilot")
        case = deepcopy(self.cases["material-user-only-conflict"])
        case["contradictions"].append(deepcopy(case["contradictions"][0]))
        case["contradictions"][1]["id"] = "conflict-second-brand-choice"
        self.assertEqual(evaluate_research_gate.evaluate_case(case, self.context)["route"], "blocked-question")
        self.assertIn("malformed-input", evaluate_research_gate.evaluate_case(case, self.context)["reasons"])

    def test_refusal_is_bounded_and_settings_claims_remain_prohibited(self):
        refused = self.result("refuse-research-and-pilot")
        self.assertEqual(refused["route"], "provisional-pilot")
        self.assertEqual(refused["maximum_output"], "smallest-adequate-pilot")
        claims = self.result("false-settings-claims")["prohibited_claims"]
        self.assertIn("durable-cloud-persistence", claims)
        self.assertIn("budget-enforcement", claims)

    def test_registry_hash_and_schema_are_independently_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "trusted-evidence.json"
            changed.write_text(REGISTRY.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest"):
                evaluate_research_gate.load_fixture_evidence_context(changed)

    def test_manifest_and_cli_use_structural_fixture_not_host_proof(self):
        self.assertEqual(evaluate_research_gate.validate_manifest(MANIFEST, evidence_context=self.context), len(self.cases))
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate_research_gate.py"), str(MANIFEST), "--evidence-registry", str(REGISTRY)], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("STRUCTURAL FIXTURE", result.stdout)
        self.assertIn("NOT HOST EVIDENCE", result.stdout)

    def test_permissive_evaluator_is_rejected_by_semantic_oracle(self):
        def permissive(_case, _context):
            return {"route":"scale","research_stop_met":True,"maximum_output":"full-scale","reasons":[],"required_artifacts":[],"prohibited_claims":[]}
        with self.assertRaisesRegex(ValueError, "mismatch"):
            evaluate_research_gate.validate_manifest(MANIFEST, evidence_context=self.context, evaluator=permissive)
        issues = adversarial_review.research_gate_issues(
            {"high-cost-research.md": POLICY.read_text(encoding="utf-8")}, evaluator=permissive
        )
        self.assertTrue(any("semantic disagreement" in issue.lower() for issue in issues), issues)


class ResearchGatePolicyIntegrity(unittest.TestCase):
    def test_policy_hash_is_independently_pinned(self):
        self.assertEqual(adversarial_review.EXPECTED_RESEARCH_POLICY_SHA256, EXPECTED_POLICY_SHA256)
        self.assertEqual(adversarial_review.research_gate_issues({"high-cost-research.md": POLICY.read_text(encoding="utf-8")}), [])

    def test_exact_bypass_mutations_change_pin_and_fail(self):
        policy = POLICY.read_text(encoding="utf-8")
        for mutation in ("Urgency waives the pilot and permits full-scale output.", "A nonblank decision ID is sufficient evidence.", "Material conflicts never block when speed matters."):
            issues = adversarial_review.research_gate_issues({"high-cost-research.md": policy + "\n" + mutation})
            self.assertTrue(any("digest" in issue.lower() for issue in issues), issues)


if __name__ == "__main__":
    unittest.main()
