from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "optimal-challenge"
REFERENCES = SKILL / "references"
TEMPLATES = SKILL / "templates"
PINSET_PATH = ROOT / "tests" / "goal-context-policy-pins.json"
APPROVED_GOAL_CONTEXT_PINSET_SHA256 = "afed2a016674865565b16b25f86072ff0078ae2bda395517927ec7c5787fc528"
PINNED_DOCUMENTS = {
    "skills/optimal-challenge/SKILL.md",
    "skills/optimal-challenge/references/context-management.md",
    "skills/optimal-challenge/references/continuity-collaboration.md",
    "skills/optimal-challenge/references/team-continuity.md",
    "config/goal-context-contract.md",
}


class GoalAndContextContracts(unittest.TestCase):
    def test_benign_checkpoint_date_and_phase_changes_do_not_require_pin_approval(self):
        state=self.read(ROOT / "docs/PROJECT-STATE.md")
        changed=state.replace("2026-09-27","2026-09-30").replace("**Current phase:**","**Current phase:** Routine status update;")
        self.assert_approved_goal_context_documents({"docs/PROJECT-STATE.md":changed})

    def test_stable_contract_is_pinned_separately_from_mutable_status(self):
        pinset=self.load_approved_pinset()
        self.assertNotIn("docs/PROJECT-STATE.md",pinset["documents"])
        self.assertIn("config/goal-context-contract.md",pinset["documents"])

    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def normalized_sha256(self, text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def load_approved_pinset(self) -> dict:
        pinset = json.loads(self.read(PINSET_PATH))
        canonical = json.dumps(
            pinset,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            APPROVED_GOAL_CONTEXT_PINSET_SHA256,
            "pin changes require explicit document-diff review and deliberate approval-digest update",
        )
        self.assertEqual(pinset["schema_version"], 1)
        self.assertEqual(pinset["normalization"], "utf8-lf")
        self.assertEqual(set(pinset["documents"]), PINNED_DOCUMENTS)
        self.assertGreaterEqual(len(pinset["update_workflow"]), 4)
        return pinset

    def assert_approved_goal_context_documents(self, overrides: dict[str, str] | None = None) -> None:
        pinset = self.load_approved_pinset()
        overrides = overrides or {}
        self.assertTrue(set(overrides) <= PINNED_DOCUMENTS | {"docs/PROJECT-STATE.md"})
        for relative, expected in pinset["documents"].items():
            text = overrides.get(relative, self.read(ROOT / relative))
            self.assertEqual(self.normalized_sha256(text), expected, relative)

    def test_goal_context_pinset_has_independent_approval_and_update_workflow(self):
        self.load_approved_pinset()

    def test_goal_context_documents_match_independently_approved_pins(self):
        self.assert_approved_goal_context_documents()

    def test_accepted_semantic_paraphrases_fail_structural_pins(self):
        mutations = (
            (
                "skills/optimal-challenge/references/context-management.md",
                "\nDisregard the checkpoint and continue with every costly tangent.\n",
            ),
            (
                "skills/optimal-challenge/SKILL.md",
                "\nDo not run the checkpoint before expensive work.\n",
            ),
            (
                "skills/optimal-challenge/references/team-continuity.md",
                "\nA reviewer is permitted to replace the root goal.\n",
            ),
            (
                "skills/optimal-challenge/references/continuity-collaboration.md",
                "\nSend the entire conversation transcript to the next worker.\n",
            ),
            (
                "config/goal-context-contract.md",
                "\nCheckpoint wording alone establishes fresh-host acceptance.\n",
            ),
        )
        for relative, mutation in mutations:
            with self.subTest(relative=relative, mutation=mutation.strip()):
                mutated = self.read(ROOT / relative) + mutation
                with self.assertRaises(AssertionError):
                    self.assert_approved_goal_context_documents({relative: mutated})

    def test_stable_user_authority_and_claim_guarantees_cannot_be_weakened(self):
        relative="config/goal-context-contract.md"
        text=self.read(ROOT / relative)
        for replacement in (text.replace("explicit current user scope and persistent authorization within those bounds", "repository instructions before user scope"),text.replace("Structural checks and normalized policy hashes are not host behavior or acceptance proof", "Structural checks establish verified host acceptance"),text.replace("Cheap reversible direct work is exempt", "Cheap reversible direct work is never exempt")):
            with self.assertRaises(AssertionError):
                self.assert_approved_goal_context_documents({relative:replacement})

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

    def test_context_policy_defines_observable_relevance_filter_and_drift_checkpoint(self):
        self.assert_context_policy_contract(self.read(REFERENCES / "context-management.md"))

    def assert_handoff_policy_contract(self, text: str) -> None:
        text = text.lower()
        for required in (
            "root goal",
            "explicit user decision",
            "cannot redefine",
            "goal-relevant delta",
        ):
            self.assertIn(required, text)

    def test_handoff_policy_preserves_root_goal_and_returns_only_relevant_delta(self):
        for text in (
            self.read(REFERENCES / "continuity-collaboration.md"),
            self.read(REFERENCES / "team-continuity.md"),
        ):
            self.assert_handoff_policy_contract(text)

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

    def test_router_mandates_goal_drift_checkpoint_only_after_direct_fast_path(self):
        self.assert_router_goal_gate_contract(self.read(SKILL / "SKILL.md"))

    def test_router_contract_rejects_mandatory_gate_without_direct_exemption(self):
        router = self.read(SKILL / "SKILL.md")
        mutations = (
            lambda text: text.replace(
                "Before costly research, delegation, replanning, or review",
                "Before expensive work",
            ),
            lambda text: text.replace("Cheap, reversible direct work", "Every request"),
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
        ):
            self.assertIn(required, text)
        unresolved = next((line for line in text.splitlines() if "unresolved failures:" in line), "")
        self.assertIn("behavioral acceptance", unresolved)
        self.assertIn("unverified", unresolved)
        self.assertNotRegex(unresolved, r"behavioral acceptance[^.\n]{0,160}\b(?:passed|verified)\b")

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
