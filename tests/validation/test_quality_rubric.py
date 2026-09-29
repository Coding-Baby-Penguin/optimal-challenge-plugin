import json
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = [6,6,12,12,6,7,7,4,3,3,3,5,6,20]

class QualityRubricTests(unittest.TestCase):
    def test_frozen_dimensions_and_arithmetic(self):
        data = json.loads((ROOT / "config/quality-rubric.json").read_text())
        dimensions = data["dimensions"]
        self.assertEqual(len(dimensions),14)
        self.assertEqual(len({d["id"] for d in dimensions}),14)
        self.assertEqual([d["weight"] for d in dimensions],EXPECTED)
        self.assertEqual(sum(d["weight"] for d in dimensions),100)
        self.assertAlmostEqual(sum(d["weight"]*d["baseline"] for d in dimensions)/10,62.05)
        self.assertAlmostEqual(sum(d["weight"]*d["target"] for d in dimensions)/10,96.0)
        for dimension in dimensions:
            self.assertTrue(dimension["required_evidence"])
            self.assertIsNone(dimension["awarded_score"])
        self.assertEqual(data["claim_status"],"unawarded")

    def test_optional_agent_suggestion_does_not_encode_exact_count(self):
        cases=json.loads((ROOT / "tests/behavioral-acceptance.json").read_text())["cases"]
        case=next(c for c in cases if c["id"]=="accept-direct-no-delegation-trap")
        self.assertNotIn("Use five agents",case["prompt"])
        self.assertEqual(case["expected_spawn_count"],0)

    def test_every_case_has_frozen_arm_classification(self):
        cases=json.loads((ROOT / "tests/behavioral-acceptance.json").read_text())["cases"]
        for case in cases:
            self.assertIn(case["evaluation_class"], ["universal-control", "candidate-feature", "comparative-task"])
            self.assertTrue(case["arm_expectations"])
            self.assertEqual(case["safety_required_arms"],["A","B","C","D"])

    def test_invalid_dimensions_weights_and_awards_are_rejected(self):
        from scripts.quality_rubric import validate_rubric
        data=json.loads((ROOT / "config/quality-rubric.json").read_text())
        self.assertEqual(validate_rubric(data),[])
        for mutation in (lambda x:x["dimensions"].pop(),lambda x:x["dimensions"][0].update(weight=7),lambda x:x["dimensions"][0].update(awarded_score=10),lambda x:x.update(claim_status="verified")):
            bad=deepcopy(data);mutation(bad)
            self.assertTrue(validate_rubric(bad))
