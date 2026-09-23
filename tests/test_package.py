from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "optimal-challenge"


class PackageIndependentReview(unittest.TestCase):
    def test_manifests_agree(self):
        paths = [ROOT / "plugin.json", ROOT / ".codex-plugin/plugin.json", ROOT / ".claude-plugin/plugin.json"]
        manifests = [json.loads(p.read_text()) for p in paths]
        self.assertEqual({m["name"] for m in manifests}, {"optimal-challenge"})
        self.assertEqual({m["version"] for m in manifests}, {"1.1.0"})

    def test_skill_is_small_and_trigger_focused(self):
        text = (SKILL_DIR / "SKILL.md").read_text()
        body = text.split("---", 2)[-1]
        words = re.findall(r"\b[\w'-]+\b", body)
        self.assertLessEqual(len(words), 350)
        self.assertIn("description: Use when", text)
        self.assertNotIn("1% chance", text.lower())

    def test_all_skill_reference_links_exist(self):
        text = (SKILL_DIR / "SKILL.md").read_text()
        refs = set(re.findall(r"references/([A-Za-z0-9_.-]+\.md)", text))
        self.assertGreaterEqual(len(refs), 8)
        for ref in refs:
            self.assertTrue((SKILL_DIR / "references" / ref).is_file(), ref)

    def test_router_is_always_on_and_reuses_existing_plans(self):
        text = (SKILL_DIR / "SKILL.md").read_text().lower()
        for phrase in [
            "handling any request",
            "never invoke `superpowers:using-superpowers`",
            "reuse an applicable approved plan",
            "thread length alone never justifies planning",
        ]:
            self.assertIn(phrase, text)

        agent = (SKILL_DIR / "agents" / "openai.yaml").read_text().lower()
        self.assertIn("allow_implicit_invocation: true", agent)

    def test_no_active_hooks_ship(self):
        self.assertFalse((ROOT / "hooks" / "hooks.json").exists())

    def test_delegation_policy_blocks_recursive_planning(self):
        text = (SKILL_DIR / "references" / "delegation-budget.md").read_text().lower()
        self.assertIn("parent is process authority", text)
        self.assertIn("do not independently re-run", text)
        self.assertIn("needs_capability", text)

    def test_preference_policy_cannot_override_truth_or_safety(self):
        text = (SKILL_DIR / "references" / "preference-model.md").read_text().lower()
        self.assertIn("correctness/safety", text)
        self.assertIn("never expand permissions", text)
        self.assertIn("sensitive personal traits", text)

    def test_evolution_is_bounded_and_reversible(self):
        text = (SKILL_DIR / "references" / "evolution-policy.md").read_text().lower()
        self.assertIn("rollback", text)
        self.assertIn("never autonomously expand privileges", text)
        self.assertIn("split", text)
        self.assertIn("prune", text)
        self.assertIn("retire", text)

    def test_codebase_paradoxes_are_guarded(self):
        text = (SKILL_DIR / "references" / "reality-model.md").read_text().lower()
        for phrase in [
            "available context will be used reliably",
            "retrieved code includes every relevant dependency",
            "passing tests prove the requested behavior",
            "more agents, retrieval, or verification monotonically improves quality",
        ]:
            self.assertIn(phrase, text)

    def test_context_state_does_not_become_append_only_chat_clone(self):
        text = (SKILL_DIR / "references" / "context-management.md").read_text().lower()
        self.assertIn("rewrite, do not append forever", text)
        self.assertIn("minimum sufficient context", text)

    def test_scenario_matrix_has_positive_negative_and_pressure_cases(self):
        scenarios = json.loads((ROOT / "tests" / "scenarios.json").read_text())
        ids = {s["id"] for s in scenarios}
        for required in ["direct-01", "direct-04", "plan-01", "plan-02", "skill-01", "agent-03", "evolution-02", "hook-02", "stagnation-01", "security-01"]:
            self.assertIn(required, ids)
        self.assertGreaterEqual(len(scenarios), 25)


if __name__ == "__main__":
    unittest.main()
