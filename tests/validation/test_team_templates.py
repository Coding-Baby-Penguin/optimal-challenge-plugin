from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "skills" / "optimal-challenge" / "templates"
TASK_FILES = {
    "TEAM-CHARTER.md",
    "TEAMMATE-CAPSULE.yaml",
    "RETURN-CAPSULE.yaml",
    "task-capsule.yaml",
    "QUESTION-BUNDLE.md",
    "PROJECT-STATE.md",
}
STATUS_VALUES = {
    "NEEDS_CAPABILITY",
    "NEEDS_DECISION",
    "complete",
    "partial",
    "blocked",
    "degraded",
    "failed",
}
MEASUREMENT_VALUES = {"unavailable", "estimated", "observed"}
ENFORCEMENT_VALUES = {"advisory", "local_enforced", "provider_enforced"}
BUDGET_UNITS = {None, "credits", "tokens", "seconds", "currency", "tool_calls", "model_calls"}
BENEFIT_KEYS = {"parallel", "independence", "context", "quality"}
COST_KEYS = {"setup", "transfer", "merge", "review_rework"}
FACTOR_PROVENANCE_KEYS = {
    *(f"benefits.{key}" for key in BENEFIT_KEYS),
    *(f"costs.{key}" for key in COST_KEYS),
}


class TeamTemplateContracts(unittest.TestCase):
    def read(self, name: str) -> str:
        return (TEMPLATES / name).read_text(encoding="utf-8")

    def load_yaml(self, name: str) -> dict:
        documents = list(yaml.safe_load_all(self.read(name)))
        self.assertEqual(len(documents), 1, name)
        self.assertIsInstance(documents[0], dict, name)
        return documents[0]

    def test_development_dependencies_pin_real_yaml_and_schema_parsers(self):
        requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("jsonschema==4.25.1", requirements)
        self.assertIn("PyYAML==6.0.2", requirements)
        docs = (ROOT / "config" / "README.md").read_text(encoding="utf-8")
        self.assertIn("Python 3.12", docs)
        self.assertIn("PyYAML", docs)
        self.assertNotIn("C:\\Users\\", docs)

    def test_all_team_templates_exist_and_stay_below_ten_kibibytes(self):
        for name in TASK_FILES:
            path = TEMPLATES / name
            self.assertTrue(path.is_file(), name)
            self.assertLess(path.stat().st_size, 10 * 1024, name)

    def test_team_charter_covers_ownership_budget_and_interruptions(self):
        text = self.read("TEAM-CHARTER.md").lower()
        for field in [
            "coordinator id:",
            "user-facing authority:",
            "shared outcome:",
            "done when:",
            "workstream owners:",
            "budget unit:",
            "ceiling:",
            "measurement:",
            "enforcement:",
            "integration reserve:",
            "mandatory-review reserve:",
            "needs_capability",
            "needs_decision",
            "timeout or missing terminal result:",
            "stop condition:",
        ]:
            self.assertIn(field, text)

    def test_unavailable_native_handle_is_null_and_example_is_documented(self):
        teammate = self.load_yaml("TEAMMATE-CAPSULE.yaml")
        self.assertIsNone(teammate["native_handle"])
        text = self.read("TEAMMATE-CAPSULE.yaml")
        self.assertIn("When available, replace null with", text)
        for field in ["provider:", "handle:", "expires_at:", "evidence_ref:"]:
            self.assertIn(field, text)

    def test_minimally_populated_teammate_matches_registry_schema(self):
        teammate = self.load_yaml("TEAMMATE-CAPSULE.yaml")
        teammate["logical_teammate_id"] = "teammate-1"
        teammate["role"] = "implementer"
        registry = {
            "schema_version": 1,
            "snapshot_version": 0,
            "transaction_version": 0,
            "transaction_id": "transaction-0",
            "run_id": "run-1",
            "coordinator_id": "coordinator-1",
            "status": "active",
            "evidence": {},
            "teammates": {"teammate-1": teammate},
            "assignments": {},
            "quarantine": [],
        }
        schema = json.loads((ROOT / "config" / "team-registry.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(registry)

    def test_task_capsule_has_native_typed_route_decision_contract(self):
        task = self.load_yaml("task-capsule.yaml")
        routing = task["routing"]
        self.assertIn(routing["invocation_mode"], {"inline-only", "auto", "team-requested"})
        self.assertIsNone(routing["exact_specialists"])
        self.assertIsInstance(routing["selected_route"], str)

        delegation = routing["delegation"]
        self.assertEqual(set(delegation["benefits"]), BENEFIT_KEYS)
        self.assertEqual(set(delegation["costs"]), COST_KEYS)
        for value in [*delegation["benefits"].values(), *delegation["costs"].values()]:
            self.assertIs(type(value), int)
            self.assertIn(value, range(4))
        self.assertEqual(set(delegation["provenance"]), FACTOR_PROVENANCE_KEYS)
        self.assertTrue(all(value in {"observed", "estimated", "unknown"} for value in delegation["provenance"].values()))
        self.assertIsInstance(delegation["evidence_ids"], list)
        self.assertIs(type(delegation["required_margin"]), int)
        self.assertGreaterEqual(delegation["required_margin"], 1)
        self.assertIsInstance(delegation["decision_reason"], str)

    def test_task_allocation_uses_budget_enums_nulls_and_native_numbers(self):
        allocation = self.load_yaml("task-capsule.yaml")["allocation"]
        self.assertIn(allocation["unit"], BUDGET_UNITS)
        self.assertIn(allocation["measurement"], MEASUREMENT_VALUES)
        self.assertIn(allocation["enforcement"], ENFORCEMENT_VALUES)
        self.assertIn("measurement_source", allocation)
        self.assertIsInstance(allocation["evidence_refs"], list)
        for key in ["worker", "tool", "retry", "review"]:
            self.assertIn(type(allocation[key]), {int, float})
            self.assertGreaterEqual(allocation[key], 0)
        if allocation["measurement"] == "unavailable":
            self.assertIsNone(allocation["measurement_source"])
            self.assertEqual(allocation["enforcement"], "advisory")
        if allocation["enforcement"] != "advisory":
            self.assertEqual(allocation["measurement"], "observed")
            self.assertIsInstance(allocation["measurement_source"], str)
            self.assertTrue(allocation["measurement_source"])

    def test_task_authority_and_escalation_are_native_typed(self):
        task = self.load_yaml("task-capsule.yaml")
        self.assertEqual(task["escalation"]["return_status"], "NEEDS_CAPABILITY")
        for key in [
            "may_ask_user",
            "may_expand_scope",
            "may_spawn_agents",
            "may_change_profile",
            "may_acquire_permissions",
        ]:
            self.assertIs(task["authority"][key], False)
        self.assertIs(task["premise"]["settled"], False)
        self.assertIs(type(task["retry_allowance"]), int)

    def test_task_return_contract_exactly_matches_return_capsule_payload(self):
        task = self.load_yaml("task-capsule.yaml")
        returned = self.load_yaml("RETURN-CAPSULE.yaml")
        payload_keys = set(returned) - {"_template"}
        self.assertEqual(set(task["return_contract"]), payload_keys)
        for identity in ["goal_id", "assignment_id", "logical_teammate_id"]:
            self.assertIn(identity, task)
            self.assertIn(identity, returned)
        for additive_alias in ["decision_delta", "concerns"]:
            self.assertIn(additive_alias, returned)

    def test_return_statuses_are_machine_readable_not_comment_only(self):
        returned = self.load_yaml("RETURN-CAPSULE.yaml")
        self.assertEqual(set(returned["_template"]["allowed_statuses"]), STATUS_VALUES)
        self.assertEqual(returned["status"], "")
        usage = returned["usage"]
        self.assertIsNone(usage["unit"])
        self.assertEqual(usage["measurement"], "unavailable")
        self.assertIsNone(usage["amount"])
        self.assertIsNone(usage["source"])

    def test_question_bundle_tracks_decisions_and_reversible_defaults(self):
        text = self.read("QUESTION-BUNDLE.md").lower()
        for field in [
            "decision id:",
            "decision class:",
            "material premise:",
            "evidence already checked:",
            "reversible default:",
            "recommended default:",
            "budget/profile decisions",
            "safe work that can continue meanwhile:",
        ]:
            self.assertIn(field, text)
        self.assertIn("active ceiling", text)
        self.assertIn("irreversible", text)

    def test_project_state_tracks_team_decisions_without_copying_runtime_state(self):
        text = self.read("PROJECT-STATE.md").lower()
        for field in [
            "durable team decisions:",
            "unresolved assignments:",
            "assignment id:",
            "state:",
            "owner:",
            "evidence:",
            "exact resume action:",
        ]:
            self.assertIn(field, text)
        self.assertIn("do not copy the runtime registry", text)

    def test_capsules_forbid_sensitive_or_unverified_persistence(self):
        for name in [
            "TEAM-CHARTER.md",
            "TEAMMATE-CAPSULE.yaml",
            "task-capsule.yaml",
            "RETURN-CAPSULE.yaml",
        ]:
            text = self.read(name).lower()
            self.assertIn("secrets", text, name)
            self.assertIn("complete transcripts", text, name)
            self.assertIn("unverified", text, name)

    def test_yaml_capsules_ship_with_safe_non_secret_placeholders(self):
        forbidden = [
            r"sk-[a-z0-9_-]{12,}",
            r"gh[opusr]_[a-z0-9_]{12,}",
            r"-----begin [a-z ]*private key-----",
            r"@[a-z0-9.-]+\.[a-z]{2,}",
            r"https?://(?!example\.(?:com|org)(?:/|$))\S+",
        ]
        for name in ["TEAMMATE-CAPSULE.yaml", "task-capsule.yaml", "RETURN-CAPSULE.yaml"]:
            text = self.read(name).lower()
            self.load_yaml(name)
            for pattern in forbidden:
                self.assertIsNone(re.search(pattern, text), f"{name}: {pattern}")


if __name__ == "__main__":
    unittest.main()
