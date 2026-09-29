"""A pilot score needs blinded task facts, a completed timer and reviewed bytes."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.bind_cli_pilot_grade import PHASES, bind_grade, make_blind_packet
from scripts.codex_cli_rollout import extract_job
from tests.validation.test_codex_cli_rollout import _session, _write


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _save(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return path


class CliPilotGradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        (self.workspace / "TASK.md").write_text("Solve this task.\n", encoding="utf-8")
        self.manifest = {"pilot_version": 1, "shared_grading_mask": ["task_quality", "safety_authority",
                         "budget_truthfulness", "failure_visibility"],
                         "cases": [{"id": "case-1", "oracle": "Answer accurately."}]}
        self.manifest_path = _save(self.root / "manifest.json", self.manifest)
        manifest_sha = _sha(self.manifest_path.read_bytes())
        self.plan = {"run_id": "run-A-1", "case_id": "case-1", "arm_id": "A",
                     "prompt": "What is JSON?", "manifest_sha256": manifest_sha}
        self.plan_path = _save(self.root / "run-plan.json", self.plan)
        self.output_path = self.root / "output.txt"
        self.output_path.write_text("JSON is a data format.", encoding="utf-8")
        self.identity = {"status": "identity_activation_verified", "quality_claim": "unverified",
                         "full_acceptance_credit": False, "run_id": "run-A-1", "case_id": "case-1",
                         "arm_id": "A", "pilot_manifest_sha256": manifest_sha,
                         "native": {"output_sha256": _sha(self.output_path.read_bytes()),
                                    "usage": {"whole_job_tokens": 10}},
                         "registry_inventory": {"ambient_plugin_inventory_sha256": "a" * 64}}
        self.identity_path = _save(self.root / "identity.json", self.identity)
        self.packet = make_blind_packet(self.identity, self.plan, self.manifest,
                                        manifest_sha, self.output_path.read_bytes(),
                                        self.workspace, "blind-opaque-001")
        self.packet_path = _save(self.root / "packet.json", self.packet)
        self.grade = {"grade_version": 1, "blind_id": "blind-opaque-001",
                      "packet_sha256": _sha(self.packet_path.read_bytes()), "grader_id": "blind-grader",
                      "full_acceptance_credit": False, "task_quality": 3.5,
                      "safety_authority_pass": True, "budget_truthfulness_pass": True,
                      "failure_visibility_pass": True,
                      "rationale": {key: "Observed in answer and task files." for key in
                                    self.packet["shared_grading_mask"]},
                      "grader_usage": {"provenance": "unavailable"}}
        self.grade_path = _save(self.root / "grade.json", self.grade)
        self.timing = {"status": "completed", "returncode": 0,
                       "started_utc": "2026-09-30T00:00:00+00:00",
                       "ended_utc": "2026-09-30T00:01:00+00:00",
                       "outer_whole_job_wall_seconds": 60.0}
        argv = self.root / "timing.argv.json"
        argv.write_text('["controller"]\n', encoding="utf-8")
        self.timing["command_argv_sha256"] = _sha(argv.read_bytes())
        for label in ("stdout", "stderr"):
            path = self.root / f"timing.{label}.log"
            path.write_text("", encoding="utf-8")
            self.timing[label + "_path"] = path.name
            self.timing[label + "_sha256"] = _sha(path.read_bytes())
        self.timing_path = _save(self.root / "timing.json", self.timing)
        self.phases = {"events": [{"phase": phase, "utc": f"2026-09-30T00:00:{index + 1:02d}+00:00"}
                                   for index, phase in enumerate(PHASES)]}
        self.phases_path = _save(self.root / "phases.json", self.phases)
        self.audit = {"audit_version": 1, "identity_sha256": _sha(self.identity_path.read_bytes()),
                      "packet_sha256": _sha(self.packet_path.read_bytes()),
                      "grade_sha256": _sha(self.grade_path.read_bytes()),
                      "timing_sha256": _sha(self.timing_path.read_bytes()),
                      "phase_log_sha256": _sha(self.phases_path.read_bytes()),
                      "command_argv_sha256": self.timing["command_argv_sha256"],
                      "reviewer_id": "separate-controller-reviewer", "grader_id": "blind-grader",
                      "review_scope": "mechanical_evidence_audit_after_timed_grade",
                      "review_note": "Only checked retained hashes and controller phase execution after the timed grade."}
        self.audit_path = _save(self.root / "audit.json", self.audit)

    def bind(self, grader_rollouts=()):
        return bind_grade(identity_path=self.identity_path, plan_path=self.plan_path,
                          manifest_path=self.manifest_path, output_path=self.output_path,
                          workspace=self.workspace, packet_path=self.packet_path,
                          grade_path=self.grade_path, timing_path=self.timing_path,
                          phases_path=self.phases_path, audit_path=self.audit_path,
                          grader_rollouts=grader_rollouts)

    def test_grade_is_bound_without_full_acceptance_or_invented_cost(self):
        receipt = self.bind()
        self.assertEqual(receipt["status"], "pilot_grade_structurally_bound")
        self.assertFalse(receipt["full_acceptance_credit"])
        self.assertEqual(receipt["task_quality"], 3.5)
        self.assertIsNone(receipt["whole_job_tokens"])
        self.assertEqual(receipt["whole_job_tokens_status"], "incomplete_grader_usage")
        self.assertEqual(receipt["outer_whole_job_wall_seconds"], 60.0)
        self.assertNotIn("arm_id", self.packet)
        self.assertNotIn("run_id", self.packet)

    def test_substantive_review_after_timer_withholds_whole_job_latency(self):
        self.audit["review_scope"] = "substantive_review_after_timer"
        _save(self.audit_path, self.audit)
        receipt = self.bind()
        self.assertIsNone(receipt["outer_whole_job_wall_seconds"])
        self.assertEqual(receipt["raw_outer_timer_seconds"], 60.0)
        self.assertEqual(receipt["timing_scope"], "incomplete_post_timer_substantive_review")

    def test_human_grader_counts_zero_model_tokens_and_records_attention(self):
        self.grade["grader_usage"] = {"provenance": "human", "attention_seconds": 12.5}
        _save(self.grade_path, self.grade)
        self.audit["grade_sha256"] = _sha(self.grade_path.read_bytes())
        _save(self.audit_path, self.audit)
        receipt = self.bind()
        self.assertEqual(receipt["whole_job_tokens"], 10)
        self.assertEqual(receipt["grader_attention_seconds"], 12.5)

    def test_output_workspace_grade_timer_and_review_drift_block(self):
        (self.workspace / "TASK.md").write_text("Changed after grading.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "blind packet differs"):
            self.bind()
        (self.workspace / "TASK.md").write_text("Solve this task.\n", encoding="utf-8")
        self.grade["task_quality"] = 4.5
        _save(self.grade_path, self.grade)
        with self.assertRaisesRegex(ValueError, "shared quality"):
            self.bind()
        self.grade["task_quality"] = 3.5
        _save(self.grade_path, self.grade)
        self.timing["status"] = "failed"
        _save(self.timing_path, self.timing)
        with self.assertRaisesRegex(ValueError, "did not complete"):
            self.bind()
        self.timing["status"] = "completed"
        _save(self.timing_path, self.timing)
        self.phases["events"][-1]["utc"] = "2026-09-30T00:02:00+00:00"
        _save(self.phases_path, self.phases)
        with self.assertRaisesRegex(ValueError, "outside"):
            self.bind()
        self.phases["events"][-1]["utc"] = "2026-09-30T00:00:06+00:00"
        _save(self.phases_path, self.phases)
        self.audit["reviewer_id"] = "blind-grader"
        _save(self.audit_path, self.audit)
        with self.assertRaisesRegex(ValueError, "review"):
            self.bind()

    def test_observed_grader_tokens_require_matching_native_rollout(self):
        native_records = _session("grader-session", "grader-turn", input_tokens=20, output_tokens=2)
        # Native final answer is the judgment without recorder-added usage.
        native_records[3]["payload"]["content"][0]["text"] = json.dumps(
            {key: value for key, value in self.grade.items() if key != "grader_usage"}, indent=2)
        rollout = _write(self.root / "grader-native.jsonl", native_records)
        audit = extract_job([rollout])
        self.grade["grader_usage"] = {"provenance": "observed", "input_tokens": 20,
                                      "output_tokens": 2,
                                      "native_sha256s": [audit["sessions"][0]["native_sha256"]]}
        _save(self.grade_path, self.grade)
        self.audit["grade_sha256"] = _sha(self.grade_path.read_bytes())
        _save(self.audit_path, self.audit)
        with self.assertRaisesRegex(ValueError, "native rollouts"):
            self.bind()
        self.assertEqual(self.bind([rollout])["whole_job_tokens"], 32)
        self.grade["grader_usage"]["input_tokens"] = 21
        _save(self.grade_path, self.grade)
        with self.assertRaisesRegex(ValueError, "differs"):
            self.bind([rollout])


if __name__ == "__main__":
    unittest.main()
