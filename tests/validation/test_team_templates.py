from __future__ import annotations

import re
import unittest
from pathlib import Path


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


def yaml_paths(text: str) -> set[str]:
    """Return indentation-based mapping paths for the simple capsule YAML."""
    paths: set[str] = set()
    parents: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        match = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_-]*):", raw_line)
        if not match:
            continue
        indent = len(match.group(1))
        key = match.group(2)
        while parents and parents[-1][0] >= indent:
            parents.pop()
        path = ".".join([parent[1] for parent in parents] + [key])
        paths.add(path)
        parents.append((indent, key))
    return paths


class TeamTemplateContracts(unittest.TestCase):
    def read(self, name: str) -> str:
        return (TEMPLATES / name).read_text(encoding="utf-8")

    def assert_yaml_paths(self, name: str, expected: set[str]) -> None:
        actual = yaml_paths(self.read(name))
        self.assertTrue(expected <= actual, f"{name} missing: {sorted(expected - actual)}")

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

    def test_teammate_capsule_covers_identity_continuity_evidence_and_trust(self):
        self.assert_yaml_paths(
            "TEAMMATE-CAPSULE.yaml",
            {
                "logical_teammate_id",
                "role",
                "capability_class",
                "continuity_mode",
                "native_handle.provider",
                "native_handle.handle",
                "native_handle.expires_at",
                "native_handle.evidence_ref",
                "working_set_evidence_refs",
                "trust.successful_reviews",
                "trust.failed_reviews",
                "trust.evidence_refs",
                "active_assignment_ids",
            },
        )

    def test_task_capsule_additively_covers_route_allocation_and_authority(self):
        self.assertIn("return_status: NEEDS_CAPABILITY", self.read("task-capsule.yaml"))
        self.assert_yaml_paths(
            "task-capsule.yaml",
            {
                "goal_id",
                "assignment_id",
                "logical_teammate_id",
                "task.outcome",
                "task.done_when",
                "premise.decision_ids",
                "premise.evidence_refs",
                "premise.settled",
                "profile",
                "capability_class",
                "allocation.unit",
                "allocation.reservation_id",
                "allocation.worker",
                "allocation.tool",
                "allocation.retry",
                "allocation.review",
                "retry_allowance",
                "authority.may_ask_user",
                "authority.may_expand_scope",
                "authority.may_spawn_agents",
                "authority.may_change_profile",
                "authority.may_acquire_permissions",
                "capability_lease.allowed",
                "capability_lease.conditional",
                "capability_lease.forbidden",
                "escalation.status",
                "escalation.reason",
                "escalation.impact",
                "escalation.evidence_refs",
                "escalation.decision_id",
                "return_contract",
            },
        )

    def test_return_capsule_covers_delta_evidence_needs_and_usage(self):
        self.assert_yaml_paths(
            "RETURN-CAPSULE.yaml",
            {
                "assignment_id",
                "logical_teammate_id",
                "status",
                "changed_artifacts",
                "verification",
                "evidence_refs",
                "decisions",
                "assumptions",
                "risks",
                "needs.capabilities",
                "needs.decisions",
                "usage.unit",
                "usage.measurement",
                "usage.amount",
                "usage.source",
            },
        )
        text = self.read("RETURN-CAPSULE.yaml")
        for status in [
            "NEEDS_CAPABILITY",
            "NEEDS_DECISION",
            "complete",
            "partial",
            "blocked",
            "degraded",
            "failed",
        ]:
            self.assertIn(status, text)

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
            for pattern in forbidden:
                self.assertIsNone(re.search(pattern, text), f"{name}: {pattern}")


if __name__ == "__main__":
    unittest.main()
