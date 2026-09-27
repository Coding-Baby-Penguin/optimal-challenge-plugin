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

    def assert_context_policy_contract(self, text: str) -> None:
        text = text.lower()
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
        self.assertNotRegex(
            text,
            r"(?mi)^(?:always\s+)?(?:skip|bypass|omit)\s+(?:the\s+)?goal-drift checkpoint\b",
        )
        self.assertNotRegex(
            text,
            r"(?mi)^(?:always\s+)?(?:forward|include|pass)\s+(?:the\s+)?(?:complete|full)\s+transcripts\b",
        )

    def test_context_policy_defines_observable_relevance_filter_and_drift_checkpoint(self):
        self.assert_context_policy_contract(self.read(REFERENCES / "context-management.md"))

    def test_context_policy_contract_rejects_checkpoint_and_transcript_bypasses(self):
        policy = self.read(REFERENCES / "context-management.md")
        contradictions = (
            "\nSkip the goal-drift checkpoint before costly research.\n",
            "\nForward full transcripts to every specialist for completeness.\n",
        )
        for contradiction in contradictions:
            with self.subTest(contradiction=contradiction.strip()):
                with self.assertRaises(AssertionError):
                    self.assert_context_policy_contract(policy + contradiction)

    def assert_handoff_policy_contract(self, text: str) -> None:
        text = text.lower()
        for required in (
            "root goal",
            "explicit user decision",
            "cannot redefine",
            "goal-relevant delta",
        ):
            self.assertIn(required, text)
        self.assertNotRegex(
            text,
            r"(?mi)^(?:a\s+)?(?:reviewer|worker|teammate|phase|assignment)\s+may\s+(?:overwrite|replace|redefine)\s+(?:the\s+)?root goal\b",
        )
        self.assertNotRegex(
            text,
            r"(?mi)^(?:always\s+)?(?:forward|include|pass|return)\s+(?:the\s+)?(?:complete|full)\s+transcripts\b",
        )

    def test_handoff_policy_preserves_root_goal_and_returns_only_relevant_delta(self):
        for text in (
            self.read(REFERENCES / "continuity-collaboration.md"),
            self.read(REFERENCES / "team-continuity.md"),
        ):
            self.assert_handoff_policy_contract(text)

    def test_handoff_contract_rejects_goal_overwrite_and_full_transcript_forwarding(self):
        policy = self.read(REFERENCES / "team-continuity.md")
        contradictions = (
            "\nA reviewer may overwrite the root goal when its local analysis is persuasive.\n",
            "\nReturn complete transcripts to the next worker.\n",
        )
        for contradiction in contradictions:
            with self.subTest(contradiction=contradiction.strip()):
                with self.assertRaises(AssertionError):
                    self.assert_handoff_policy_contract(policy + contradiction)

    def assert_router_goal_gate_contract(self, router: str) -> None:
        router = router.lower()
        direct = router.index("stable, single-step, and low-risk")
        checkpoint = router.index("before costly research, delegation, replanning, or review")
        research = router.index("for production with material scale")
        self.assertLess(direct, checkpoint)
        self.assertLess(checkpoint, research)
        self.assertIn("load [context management](references/context-management.md)", router)
        self.assertIn("run its goal-drift checkpoint", router)
        self.assertIn("cheap, reversible direct work", router)
        self.assertNotRegex(
            router,
            r"(?mi)^(?:always\s+)?(?:skip|bypass|omit)\s+(?:the\s+)?goal-drift checkpoint\b",
        )

    def test_router_mandates_goal_drift_checkpoint_only_after_direct_fast_path(self):
        self.assert_router_goal_gate_contract(self.read(SKILL / "SKILL.md"))

    def test_router_contract_rejects_mandatory_gate_without_direct_exemption(self):
        router = self.read(SKILL / "SKILL.md")
        mutations = (
            lambda text: text.replace(
                "Before costly research, delegation, replanning, or review",
                "Before expensive work",
            ),
            lambda text: text.replace("cheap, reversible direct work", "every request"),
            lambda text: text + "\nSkip the goal-drift checkpoint when deadlines are tight.\n",
        )
        for mutate in mutations:
            mutated = mutate(router)
            self.assertNotEqual(mutated, router)
            with self.assertRaises((AssertionError, ValueError)):
                self.assert_router_goal_gate_contract(mutated)

    def assert_project_state_truth_contract(self, text: str) -> None:
        text = text.lower()
        for required in (
            "accepted, high-quality result",
            "tokens",
            "smallest adequate workflow",
            "no mcp",
            "no security",
            "no universal workflow ceremony",
            "context pruning",
            "fresh-host behavioral acceptance",
            "unverified",
        ):
            self.assertIn(required, text)
        self.assertNotRegex(
            text,
            r"fresh-host behavioral acceptance\s+(?:is|:)?\s*(?:`)?verified(?:`)?",
        )

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
        self.assert_project_state_truth_contract(self.read(ROOT / "docs" / "PROJECT-STATE.md"))

    def test_project_state_truth_contract_rejects_false_fresh_host_verification(self):
        state = self.read(ROOT / "docs" / "PROJECT-STATE.md")
        contradiction = "\nFresh-host behavioral acceptance is VERIFIED.\n"
        with self.assertRaises(AssertionError):
            self.assert_project_state_truth_contract(state + contradiction)

    def test_scenario_matrix_covers_drift_pruning_without_burdening_direct_work(self):
        scenarios = {
            item["id"]: item
            for item in json.loads(self.read(ROOT / "tests" / "scenarios.json"))
        }
        expected = {
            "context-noisy-reviewer-01": (
                "prune-mcp-security-tangent-and-return-to-root-goal",
                {"context-management", "continuity-collaboration"},
                {"reviewer", "mcp", "root goal", "does not advance", "success criterion"},
            ),
            "context-minimal-capsule-01": (
                "send-minimal-goal-anchored-fresh-specialist-capsule",
                {"context-management", "team-continuity"},
                {"fresh specialist", "only the context needed", "bounded workstream", "root goal"},
            ),
            "context-phase-change-01": (
                "refresh-working-set-for-phase-without-changing-root-goal",
                {"context-management", "continuity-collaboration"},
                {"research", "implementation", "working set", "root goal", "transcript"},
            ),
            "direct-goal-lightweight-01": (
                "direct-without-goal-management-ceremony",
                set(),
                {"one typo", "disposable", "do not add", "ceremony"},
            ),
        }
        for scenario_id, (outcome, modules, prompt_tokens) in expected.items():
            self.assertIn(scenario_id, scenarios)
            self.assertEqual(scenarios[scenario_id]["expect"], outcome)
            self.assertEqual(set(scenarios[scenario_id]["modules"]), modules)
            prompt = scenarios[scenario_id]["prompt"].lower()
            self.assertTrue(all(token in prompt for token in prompt_tokens), scenario_id)


if __name__ == "__main__":
    unittest.main()
