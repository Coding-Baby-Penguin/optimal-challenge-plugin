from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "optimal-challenge"
REFERENCES = SKILL / "references"
TEMPLATES = SKILL / "templates"


class GoalAndContextContracts(unittest.TestCase):
    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_task_capsule_has_compact_machine_readable_goal_anchor(self):
        task = yaml.safe_load(self.read(TEMPLATES / "task-capsule.yaml"))

        self.assertIn("goal_id", task, "existing goal_id compatibility must remain")
        self.assertIsInstance(task["goal_id"], str)
        anchor = task["goal_anchor"]
        self.assertEqual(
            set(anchor),
            {
                "root_outcome",
                "success_criteria",
                "non_goals",
                "current_phase",
                "contribution_to_goal",
                "stop_condition",
                "minimum_evidence",
            },
        )
        for field in ("root_outcome", "current_phase", "contribution_to_goal", "stop_condition"):
            self.assertIsInstance(anchor[field], str, field)
        for field in ("success_criteria", "non_goals", "minimum_evidence"):
            self.assertIsInstance(anchor[field], list, field)

    def test_context_policy_defines_observable_relevance_filter_and_drift_checkpoint(self):
        text = self.read(REFERENCES / "context-management.md").lower()

        self.assertIn("context size is a cost, not a quality signal", text)
        relevance = re.search(
            r"## relevance filter(?P<body>.*?)(?=\n## )",
            text,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(relevance)
        body = relevance.group("body")
        for observable in (
            "root goal or current subgoal",
            "material constraint or decision",
            "next action",
            "success verification",
            "recovery from a known failure",
        ):
            self.assertIn(observable, body)
        for disposition in ("pointer", "cold", "archive"):
            self.assertIn(disposition, body)

        checkpoint = re.search(
            r"## goal-drift checkpoint(?P<body>.*?)(?=\n## )",
            text,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(checkpoint)
        body = checkpoint.group("body")
        self.assertRegex(body, r"before .*research.*delegation.*replanning.*review")
        for field in (
            "success criterion advanced",
            "output or decision",
            "smallest adequate action",
            "stop condition",
            "consequence of skipping",
        ):
            self.assertIn(field, body)
        self.assertIn("prune", body)
        self.assertIn("root goal", body)

    def test_handoff_policy_preserves_root_goal_and_returns_only_relevant_delta(self):
        continuity = self.read(REFERENCES / "continuity-collaboration.md").lower()
        team = self.read(REFERENCES / "team-continuity.md").lower()

        for text in (continuity, team):
            self.assertIn("root goal", text)
            self.assertIn("explicit user decision", text)
            self.assertIn("cannot redefine", text)
            self.assertIn("goal-relevant delta", text)

    def test_project_state_template_has_one_compact_goal_contract(self):
        text = self.read(TEMPLATES / "PROJECT-STATE.md").lower()
        required_fields = (
            "north star / root goal:",
            "success criteria:",
            "non-goals:",
            "current phase:",
            "goal contribution:",
            "working set:",
            "next concrete action:",
        )
        for field in required_fields:
            self.assertEqual(text.count(field), 1, field)
        self.assertIn("root goal changes only after an explicit user decision", text)
        self.assertIn("pointers", text)

    def test_current_project_state_records_north_star_without_erasing_release_truth(self):
        text = self.read(ROOT / "docs" / "PROJECT-STATE.md").lower()

        self.assertIn("accepted, high-quality result", text)
        self.assertIn("tokens", text)
        self.assertIn("smallest adequate workflow", text)
        self.assertIn("no mcp", text)
        self.assertIn("no security", text)
        self.assertIn("no universal workflow ceremony", text)
        self.assertIn("context pruning", text)
        self.assertIn("fresh-host behavioral acceptance", text)
        self.assertIn("unverified", text)
        self.assertNotIn("fresh-host behavioral acceptance is verified", text)

    def test_scenario_matrix_covers_drift_pruning_without_burdening_direct_work(self):
        scenarios = {
            item["id"]: item
            for item in json.loads(self.read(ROOT / "tests" / "scenarios.json"))
        }
        expected = {
            "context-noisy-reviewer-01": (
                "prune-mcp-security-tangent-and-return-to-root-goal",
                {"context-management", "continuity-collaboration"},
            ),
            "context-minimal-capsule-01": (
                "send-minimal-goal-anchored-fresh-specialist-capsule",
                {"context-management", "team-continuity"},
            ),
            "context-phase-change-01": (
                "refresh-working-set-for-phase-without-changing-root-goal",
                {"context-management", "continuity-collaboration"},
            ),
            "direct-goal-lightweight-01": (
                "direct-without-goal-management-ceremony",
                set(),
            ),
        }
        for scenario_id, (outcome, modules) in expected.items():
            self.assertIn(scenario_id, scenarios)
            self.assertEqual(scenarios[scenario_id]["expect"], outcome)
            self.assertEqual(set(scenarios[scenario_id]["modules"]), modules)


if __name__ == "__main__":
    unittest.main()
