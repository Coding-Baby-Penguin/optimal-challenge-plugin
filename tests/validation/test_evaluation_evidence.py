"""Host evidence must be independent of internally consistent scored JSON."""
from __future__ import annotations

import unittest
import hashlib
import json
import tempfile
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from scripts.evaluate_behavior import compare_arms
from scripts.evaluation_evidence import (
    _issue, combine_verified_contexts, register_recorder_review, verify_run_evidence,
)
from scripts.record_acceptance import build_receipt
from scripts.review_acceptance import _approval_digest, run_reviewed_comparison
from tests.validation.test_behavioral_evaluation import bundle, manifest, manifest_digest, mutate_runs, set_run_quality


class EvidenceBoundaryTests(unittest.TestCase):
    def verified_bundle(self, pinned, arm_id):
        result = bundle(arm_id)
        result["manifest_sha256"] = manifest_digest(pinned)
        result["subject"]["identity_status"] = "verified"
        result["identity_verification"].update(artifact="verified", installed_read_back="verified")
        return result

    def write_artifacts(self, root: Path, scored, pinned):
        (root / "raw").mkdir(exist_ok=True)
        (root / "grade").mkdir(exist_ok=True)
        (root / "native").mkdir(exist_ok=True)
        observations = []
        native_audit = {}
        for index, record in enumerate(scored["runs"]):
            run_id = record["run_id"]
            task_id = f"disposable-{scored['arm_id']}-{index}"
            raw = {
                "run_id": run_id, "arm_id": scored["arm_id"],
                "scenario_id": record["scenario_id"], "replicate_id": record["replicate_id"],
                "task_id": task_id, "session_id": f"host-session-{scored['arm_id']}-{index}",
                "host": pinned["host"], "host_version": "0.158.0-test", "host_source": "desktop-ui",
                "surface": pinned["surface"],
                "model": pinned["model"], "reasoning": pinned["reasoning"],
                "archive_sha256": scored["subject"]["archive_sha256"],
                "installed_read_back": scored["subject"]["installed_plugin_read_back"],
                "terminal_status": "completed", "usage": {"complete": True, "whole_job_tokens": 10, "model_calls": record["proxies"]["model_calls"]},
                "wall_seconds": 10,
                "critical_path_seconds": record["critical_path"]["value"],
                "tool_events_complete": True,
                "tool_events": (
                    [{"type": "spawn_agent"} for _ in range(record["proxies"]["spawn_count"])]
                    + [{"type": "tool_call"} for _ in range(record["proxies"]["tool_calls"])]
                    + [{"type": "user_question"} for _ in range(record["proxies"]["question_count"])]
                ),
                "output": record["output"],
            }
            raw_path = root / "raw" / f"{scored['arm_id']}-{index}.json"
            raw_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
            native_path = root / "native" / f"{scored['arm_id']}-{index}.jsonl"
            native_path.write_text(json.dumps({"fixture_only": True, "run_id": run_id}) + "\n", encoding="utf-8")
            native_audit[run_id] = {
                "native_sha256": hashlib.sha256(native_path.read_bytes()).hexdigest(),
                "native_source": "codex-desktop-event-v1",
                **{field: deepcopy(raw[field]) for field in (
                    "task_id", "session_id", "host", "host_version", "host_source", "surface",
                    "model", "reasoning", "archive_sha256", "terminal_status", "usage",
                    "wall_seconds", "critical_path_seconds", "tool_events", "tool_events_complete",
                )},
                "output_sha256": hashlib.sha256(raw["output"].encode("utf-8")).hexdigest(),
                "semantic_trace_sha256": None,
            }
            grade = {
                "run_id": run_id, "arm_id": scored["arm_id"],
                "raw_identity_id": record["raw_evidence_refs"][0]["identity_id"],
                "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                "grader_identity_id": record["grader_evidence_refs"][0]["identity_id"],
                "grader_id": "grader-independent", "independent": True,
                "scored": {field: deepcopy(record[field]) for field in (
                    "output", "recommendation", "observed_behaviors", "quality", "passed", "safety_authority_pass", "budget_truthfulness_pass",
                    "failure_visibility_pass", "unsafe_failures", "observed_route", "question_result",
                    "rubric_outcome", "proxies", "cost", "latency", "critical_path",
                )},
            }
            grade_path = root / "grade" / f"{scored['arm_id']}-{index}.json"
            grade_path.write_text(json.dumps(grade, sort_keys=True), encoding="utf-8")
            observations.append({"run_id": run_id, "task_id": task_id,
                                 "raw_path": raw_path.relative_to(root).as_posix(),
                                 "grade_path": grade_path.relative_to(root).as_posix(),
                                 "native_path": native_path.relative_to(root).as_posix()})
        return build_receipt(scored, pinned, root, observations, recorder_id=f"recorder-{root.name}"), native_audit

    def test_synthetic_verified_statuses_cannot_award_comparison(self):
        pinned = manifest()
        for arm in pinned["arms"]:
            arm["identity_status"] = "verified"
        baseline = bundle("A")
        candidate = mutate_runs(
            bundle("D"),
            lambda item: "high-value-delegation" in item["evaluation_groups"],
            lambda item: (set_run_quality(item, 3.2), item["critical_path"].__setitem__("value", 9.0)),
        )
        for run_bundle in (baseline, candidate):
            run_bundle["manifest_sha256"] = manifest_digest(pinned)
            run_bundle["subject"]["identity_status"] = "verified"
            run_bundle["identity_verification"].update(artifact="verified", installed_read_back="verified")
        result = compare_arms(baseline, candidate, pinned)
        self.assertEqual(result["status"], "unverified", result)
        self.assertGreater(result["quality_difference"], 0)
        self.assertEqual(result["quality_noninferiority"]["claim"], "unverified")
        self.assertFalse(result["simple_tasks"]["cost"]["claim_allowed"])
        self.assertFalse(result["high_value_delegation"]["claim_allowed"])
        self.assertEqual(result["semantic_diagnostics"]["status"], "unverified")

    def test_malformed_nested_identity_returns_errors_not_exception(self):
        pinned = manifest()
        scored = bundle("D")
        scored["runs"][0]["raw_evidence_refs"][0]["identity_id"] = ["unhashable"]
        with tempfile.TemporaryDirectory() as directory:
            context, errors = verify_run_evidence(scored, pinned, Path(directory), {})
        self.assertIsNone(context)
        self.assertTrue(errors)

    def test_reviewed_receipt_binds_every_run_and_detects_tampering(self):
        pinned = manifest()
        for arm in pinned["arms"]:
            arm["identity_status"] = "verified"
        scored = self.verified_bundle(pinned, "D")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            receipt, audit = self.write_artifacts(root, scored, pinned)
            context, errors = verify_run_evidence(scored, pinned, root, receipt)
            self.assertIsNone(context)
            self.assertIn("independently reviewed", " ".join(errors))
            register_recorder_review(receipt, reviewer_id="reviewer-external", independent_graders=["grader-independent"], native_audit=audit)
            context, errors = verify_run_evidence(scored, pinned, root, receipt)
            self.assertEqual(errors, [])
            self.assertEqual(len(context.raw_grader_identities), len(scored["runs"]))
            raw_path = root / receipt["runs"][0]["raw"]["path"]
            raw_path.write_bytes(raw_path.read_bytes() + b" ")
            context, errors = verify_run_evidence(scored, pinned, root, receipt)
            self.assertIsNone(context)
            self.assertIn("altered", " ".join(errors))

    def test_reviewed_receipt_rejects_unsafe_and_reused_paths(self):
        pinned = manifest()
        for arm in pinned["arms"]:
            arm["identity_status"] = "verified"
        scored = self.verified_bundle(pinned, "D")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            receipt, audit = self.write_artifacts(root, scored, pinned)
            outside = deepcopy(receipt)
            outside["runs"][0]["raw"]["path"] = "../outside.json"
            register_recorder_review(outside, reviewer_id="reviewer-external", independent_graders=["grader-independent"], native_audit=audit)
            context, errors = verify_run_evidence(scored, pinned, root, outside)
            self.assertIsNone(context)
            self.assertIn("unsafe", " ".join(errors))
            reused = deepcopy(receipt)
            reused["runs"][1]["raw"] = deepcopy(reused["runs"][0]["raw"])
            register_recorder_review(reused, reviewer_id="reviewer-external", independent_graders=["grader-independent"], native_audit=audit)
            context, errors = verify_run_evidence(scored, pinned, root, reused)
            self.assertIsNone(context)
            self.assertIn("duplicated", " ".join(errors))

    def test_self_declared_completion_without_native_events_cannot_unlock(self):
        pinned = manifest()
        for arm in pinned["arms"]:
            arm["identity_status"] = "verified"
        scored = self.verified_bundle(pinned, "D")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            receipt, audit = self.write_artifacts(root, scored, pinned)
            self.assertTrue(json.loads((root / receipt["runs"][0]["raw"]["path"]).read_text())["usage"]["complete"])
            missing = deepcopy(receipt)
            missing["runs"][0].pop("native")
            with self.assertRaisesRegex(ValueError, "native review"):
                register_recorder_review(missing, reviewer_id="reviewer-external", independent_graders=["grader-independent"], native_audit=audit)
            context, errors = verify_run_evidence(scored, pinned, root, missing)
            self.assertIsNone(context)
            self.assertIn("reviewed native", " ".join(errors))

    def test_synthetic_native_source_cannot_be_approved_for_host_acceptance(self):
        pinned = manifest()
        for arm in pinned["arms"]:
            arm["identity_status"] = "verified"
        scored = self.verified_bundle(pinned, "D")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            receipt, audit = self.write_artifacts(root, scored, pinned)
            audit[receipt["runs"][0]["run_id"]]["native_source"] = "synthetic-test-fixture"
            with self.assertRaisesRegex(ValueError, "native review"):
                register_recorder_review(receipt, reviewer_id="reviewer-external", independent_graders=["grader-independent"], native_audit=audit)
            context, errors = verify_run_evidence(scored, pinned, root, receipt)
            self.assertIsNone(context)
            self.assertIn("independently reviewed", " ".join(errors))

    def test_rehashed_raw_output_cannot_score_an_answer_the_host_did_not_return(self):
        pinned = manifest()
        for arm in pinned["arms"]:
            arm["identity_status"] = "verified"
        scored = self.verified_bundle(pinned, "D")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            receipt, audit = self.write_artifacts(root, scored, pinned)
            first = receipt["runs"][0]
            raw_path = root / first["raw"]["path"]
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["output"] = "A different host answer"
            raw_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
            first["raw"]["sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            grade_path = root / first["grade"]["path"]
            grade = json.loads(grade_path.read_text(encoding="utf-8"))
            grade["raw_sha256"] = first["raw"]["sha256"]
            grade_path.write_text(json.dumps(grade, sort_keys=True), encoding="utf-8")
            first["grade"]["sha256"] = hashlib.sha256(grade_path.read_bytes()).hexdigest()
            register_recorder_review(receipt, reviewer_id="reviewer-external", independent_graders=["grader-independent"], native_audit=audit)
            context, errors = verify_run_evidence(scored, pinned, root, receipt)
            self.assertIsNone(context)
            self.assertIn("scored output differs", " ".join(errors))

    def test_reviewed_context_can_be_combined_only_for_two_distinct_arms(self):
        pinned = manifest()
        for arm in pinned["arms"]:
            arm["identity_status"] = "verified"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            contexts = []
            for arm_id in ("A", "D"):
                scored = self.verified_bundle(pinned, arm_id)
                receipt, audit = self.write_artifacts(root, scored, pinned)
                register_recorder_review(receipt, reviewer_id="reviewer-external", independent_graders=["grader-independent"], native_audit=audit)
                context, errors = verify_run_evidence(scored, pinned, root, receipt)
                self.assertEqual(errors, [])
                contexts.append(context)
            combined = combine_verified_contexts(*contexts)
            self.assertEqual(len(combined.raw_grader_identities), 280)
            with self.assertRaisesRegex(ValueError, "distinct"):
                combine_verified_contexts(contexts[0], contexts[0])
            reused_raw = list(contexts[1].raw_grader_identities)
            item = list(reused_raw[0]); item[2] = contexts[0].raw_grader_identities[0][2]
            reused_raw[0] = tuple(item)
            with self.assertRaisesRegex(ValueError, "raw or grader"):
                combine_verified_contexts(contexts[0], _issue(replace(contexts[1], raw_grader_identities=tuple(reused_raw))))
            reused_session = list(contexts[1].host_task_sessions)
            reused_session[0] = (reused_session[0][0], contexts[0].host_task_sessions[0][1],
                                 contexts[0].host_task_sessions[0][2])
            with self.assertRaisesRegex(ValueError, "task or native session"):
                combine_verified_contexts(contexts[0], _issue(replace(contexts[1], host_task_sessions=tuple(reused_session))))

    def test_one_process_reviewed_command_consumes_context_without_auto_approval(self):
        pinned = manifest()
        for arm in pinned["arms"]:
            arm["identity_status"] = "verified"
        baseline = self.verified_bundle(pinned, "A")
        candidate = mutate_runs(
            self.verified_bundle(pinned, "D"),
            lambda item: "high-value-delegation" in item["evaluation_groups"],
            lambda item: (set_run_quality(item, 3.2), item["critical_path"].__setitem__("value", 9.0)),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            receipts = {}
            audits = {}
            for scored in (baseline, candidate):
                arm_id = scored["arm_id"]
                receipt, native = self.write_artifacts(root, scored, pinned)
                receipts[arm_id] = receipt
                audits[arm_id] = {"independent_graders": ["grader-independent"], "native_audit": native}
            denied = run_reviewed_comparison(pinned, baseline, candidate, receipts, audits, root,
                                             reviewer_id="reviewer-external", approval_digest="unreviewed")
            self.assertEqual(denied["status"], "blocked")
            approved = run_reviewed_comparison(pinned, baseline, candidate, receipts, audits, root,
                                               reviewer_id="reviewer-external",
                                               approval_digest=_approval_digest(pinned, baseline, candidate, receipts, audits))
            self.assertEqual(approved["status"], "pass", approved)
            self.assertEqual(approved["semantic_diagnostics"]["status"], "unverified")
            self.assertEqual(approved["semantic_diagnostics"]["observed_runs"], 0)

    def test_verified_comparison_with_no_required_semantic_cases_is_not_applicable(self):
        pinned = manifest()
        for arm in pinned["arms"]:
            arm["identity_status"] = "verified"
        baseline = self.verified_bundle(pinned, "A")
        candidate = self.verified_bundle(pinned, "B")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            contexts = []
            for scored in (baseline, candidate):
                receipt, audit = self.write_artifacts(root, scored, pinned)
                register_recorder_review(receipt, reviewer_id="reviewer-external",
                                         independent_graders=["grader-independent"], native_audit=audit)
                context, errors = verify_run_evidence(scored, pinned, root, receipt)
                self.assertEqual(errors, [])
                contexts.append(context)
            result = compare_arms(baseline, candidate, pinned,
                                  evidence_context=combine_verified_contexts(*contexts))
            self.assertEqual(result["semantic_diagnostics"]["status"], "not_applicable")
            self.assertEqual(result["semantic_diagnostics"]["required_runs"], 0)
