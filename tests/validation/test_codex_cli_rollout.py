"""Native CLI extraction must not count inherited child history twice."""
from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.codex_cli_rollout import extract_job, extract_rollout
from scripts.verify_cli_preflight import verify_cli_preflight


def _write(path: Path, records: list[dict]) -> Path:
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return path


def _record(kind: str, **payload):
    return {"type": kind, "payload": payload}


def _session(session: str, turn: str, *, parent: str | None = None, inherited: list[dict] | None = None,
             input_tokens: int = 10, output_tokens: int = 2, spawn: bool = False,
             guardian: bool = False):
    source = "exec" if parent is None else ({"subagent": {"other": "guardian"}} if guardian else
            {"subagent": {"thread_spawn": {"parent_thread_id": parent, "depth": 1,
                                            "agent_path": "/root/child", "agent_nickname": "Child",
                                            "agent_role": None}}})
    records = [_record("session_meta", id=session, cli_version="0.158.0-alpha.2.1",
                       parent_thread_id=parent, source=source)]
    records.extend(inherited or [])
    records += [_record("event_msg", type="task_started", turn_id=turn),
                _record("turn_context", turn_id=turn,
                        model="codex-auto-review" if guardian else "gpt-6-sol",
                        effort="low" if guardian else "medium")]
    if spawn:
        records.append(_record("response_item", type="function_call", name="spawn_agent",
                               namespace="collaboration", call_id="call-1", arguments="opaque"))
        records.append(_record("response_item", type="function_call_output", call_id="call-1", output="opaque"))
    records += [_record("response_item", type="message", role="assistant", phase="final_answer",
                        content=[{"type": "output_text", "text": "done"}]),
                _record("event_msg", type="token_count", info={"total_token_usage": {
                    "input_tokens": input_tokens, "cached_input_tokens": 0, "cache_write_input_tokens": 0,
                    "output_tokens": output_tokens, "reasoning_output_tokens": 0,
                    "total_tokens": input_tokens + output_tokens}}),
                _record("event_msg", type="task_complete", turn_id=turn, duration_ms=1000)]
    return records


class CodexCliRolloutTests(unittest.TestCase):
    def test_native_custom_tool_call_and_output_are_counted_without_inventing_success(self):
        with tempfile.TemporaryDirectory() as directory:
            records = _session("session", "turn")
            records[3:3] = [
                _record("response_item", type="custom_tool_call", id="item-1", status="completed",
                        call_id="call-native", name="exec", input="opaque command arguments"),
                _record("response_item", type="custom_tool_call_output", id="item-2",
                        call_id="call-native", output="opaque tool output"),
            ]
            path = _write(Path(directory) / "custom.jsonl", records)
            report = extract_job([path])
            self.assertEqual(report["tool_events"], [{"type": "tool_call", "namespace": None,
                                                       "name": "exec", "call_id": "call-native",
                                                       "outcome": "unknown", "output_present": True}])
            self.assertTrue(report["tool_events_complete"])
            records.pop(4)
            with self.assertRaisesRegex(ValueError, "missing.*output"):
                extract_job([_write(path, records)])
            records.insert(3, _record("response_item", type="custom_tool_call_output",
                                      call_id="orphan", output="opaque"))
            with self.assertRaisesRegex(ValueError, "orphan"):
                extract_job([_write(path, records)])
            records.pop(3)
            records.insert(4, _record("response_item", type="custom_tool_call_output",
                                      call_id="call-native", output="opaque"))
            records.insert(5, _record("response_item", type="custom_tool_call_output",
                                      call_id="call-native", output="opaque"))
            with self.assertRaisesRegex(ValueError, "duplicate native tool output"):
                extract_job([_write(path, records)])

    def test_child_inherited_parent_records_are_not_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = _session("parent", "parent-turn", input_tokens=100, output_tokens=3, spawn=True)
            child = _session("child", "child-turn", parent="parent", inherited=parent[:4],
                             input_tokens=20, output_tokens=2)
            report = extract_job([_write(root / "parent.jsonl", parent), _write(root / "child.jsonl", child)])
            self.assertEqual(report["usage"]["input_tokens"], 120)
            self.assertEqual(report["usage"]["output_tokens"], 5)
            self.assertEqual(report["usage"]["session_count"], 2)
            self.assertIsNone(report["usage"]["model_calls"])
            self.assertEqual(report["wall_seconds"], 1)
            self.assertEqual(sum(event["type"] == "spawn_agent" for event in report["tool_events"]), 1)
            self.assertEqual(report["host"], "codex-cli")
            self.assertEqual(report["quality_claim"], "unverified")

    def test_native_guardian_review_is_overhead_not_product_delegation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = _session("parent", "parent-turn", input_tokens=100, output_tokens=3)
            guardian = _session("review", "review-turn", parent="parent", inherited=parent[:4],
                                input_tokens=20, output_tokens=2, guardian=True)
            report = extract_job([_write(root / "parent.jsonl", parent),
                                  _write(root / "review.jsonl", guardian)])
            self.assertEqual(report["usage"]["whole_job_tokens"], 125)
            self.assertEqual(report["usage"]["review_tokens"], 22)
            self.assertEqual(report["usage"]["product_tokens"], 103)
            self.assertEqual(report["usage"]["guardian_session_count"], 1)
            self.assertEqual(report["usage"]["product_session_count"], 1)
            self.assertEqual(report["tool_events"], [])
            self.assertEqual(report["sessions"][1]["session_role"], "review-guardian")
            guardian[0]["payload"]["source"] = {"subagent": {"other": "unknown"}}
            with self.assertRaisesRegex(ValueError, "source"):
                extract_job([_write(root / "parent.jsonl", parent),
                             _write(root / "review.jsonl", guardian)])
            guardian[0]["payload"]["source"] = {"subagent": {"other": "guardian"}}
            next(record for record in guardian if record["type"] == "turn_context" and
                 record["payload"]["turn_id"] == "review-turn")["payload"]["model"] = "different-model"
            with self.assertRaisesRegex(ValueError, "guardian.*model"):
                extract_job([_write(root / "parent.jsonl", parent),
                             _write(root / "review.jsonl", guardian)])

    def test_guardian_can_review_a_product_child_but_not_another_guardian(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = _session("parent", "parent-turn", spawn=True)
            child = _session("child", "child-turn", parent="parent")
            guardian = _session("review", "review-turn", parent="child", guardian=True)
            paths = [_write(root / "parent.jsonl", parent), _write(root / "child.jsonl", child),
                     _write(root / "review.jsonl", guardian)]
            report = extract_job(paths)
            self.assertEqual(report["usage"]["product_session_count"], 2)
            self.assertEqual(report["usage"]["guardian_session_count"], 1)
            self.assertEqual(sum(event["type"] == "spawn_agent" for event in report["tool_events"]), 1)
            guardian[0]["payload"]["parent_thread_id"] = "review-2"
            other = _session("review-2", "review-2-turn", parent="child", guardian=True)
            with self.assertRaisesRegex(ValueError, "guardian.*product"):
                extract_job(paths[:2] + [_write(root / "review-2.jsonl", other),
                                         _write(root / "review.jsonl", guardian)])
            guardian[0]["payload"]["parent_thread_id"] = "child"
            product_under_review = _session("nested", "nested-turn", parent="review")
            with self.assertRaisesRegex(ValueError, "ancestry"):
                extract_job(paths[:2] + [_write(root / "review.jsonl", guardian),
                                         _write(root / "nested.jsonl", product_under_review)])

    def test_missing_terminal_counters_and_duplicate_native_json_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = _session("session", "turn")[:-2]
            with self.assertRaisesRegex(ValueError, "complete"):
                extract_rollout(_write(root / "missing.jsonl", missing))
            (root / "duplicate.jsonl").write_text('{"type":"session_meta","payload":{"id":"x","id":"y"}}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                extract_rollout(root / "duplicate.jsonl")

    def test_duplicate_session_and_missing_child_parent_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = _write(root / "parent.jsonl", _session("parent", "p"))
            duplicate = _write(root / "duplicate.jsonl", _session("parent", "p2"))
            with self.assertRaisesRegex(ValueError, "duplicate native session"):
                extract_job([parent, duplicate])
            child = _write(root / "child.jsonl", _session("child", "c", parent="missing"))
            with self.assertRaisesRegex(ValueError, "missing child-parent"):
                extract_job([parent, child])

    def test_non_cli_source_and_inconsistent_counters_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            desktop = _session("session", "turn")
            desktop[0]["payload"]["source"] = "desktop-ui"
            with self.assertRaisesRegex(ValueError, "CLI exec source"):
                extract_rollout(_write(root / "desktop.jsonl", desktop))
            inconsistent = _session("session", "turn")
            inconsistent[-2]["payload"]["info"]["total_token_usage"]["total_tokens"] = 999
            with self.assertRaisesRegex(ValueError, "totals"):
                extract_rollout(_write(root / "inconsistent.jsonl", inconsistent))

    def test_multiple_token_events_in_one_session_do_not_become_multiple_model_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = _session("session", "turn")
            records.insert(-2, records[-2].copy())
            report = extract_job([_write(root / "multi.jsonl", records)])
            self.assertEqual(report["usage"]["session_count"], 1)
            self.assertIsNone(report["usage"]["model_calls"])

    def test_one_run_preflight_binds_exact_native_output_and_bytes_without_quality_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rollout = _write(root / "native.jsonl", _session("session", "turn"))
            audit = extract_job([rollout])
            manifest = {"preflight_version": 1, "task_id": "disposable-1", "host": "codex-cli",
                        "surface": "codex-cli-local", "host_source": "codex-cli",
                        "host_version": audit["host_version"], "model": audit["model"],
                        "reasoning": audit["reasoning"], "subject_archive_sha256": "a" * 64,
                        "installed_read_back": {"router": "b" * 64}}
            raw = {**manifest, "session_id": audit["root_session_id"], "output": "done",
                   "terminal_status": "completed", "usage": audit["usage"],
                   "wall_seconds": audit["wall_seconds"], "tool_events": audit["tool_events"],
                   "tool_events_complete": True, "recorder_id": "recorder"}
            def save(name, value):
                path = root / name
                path.write_text(json.dumps(value), encoding="utf-8")
                return path
            manifest_path = save("manifest.json", manifest)
            raw_path = save("raw.json", raw)
            grade = {"grader_id": "reviewer", "task_id": manifest["task_id"],
                     "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                     "output_sha256": audit["output_sha256"], "quality_claim": "unverified",
                     "observed_result": "done"}
            grade_path = save("grade.json", grade)
            bundle = {"preflight_version": 1, "task_id": manifest["task_id"],
                      "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                      "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                      "grade_sha256": hashlib.sha256(grade_path.read_bytes()).hexdigest(),
                      "native_rollout_sha256s": [audit["sessions"][0]["native_sha256"]],
                      "quality_claim": "unverified"}
            bundle_path = save("bundle.json", bundle)
            result = verify_cli_preflight(manifest_path, raw_path, grade_path, bundle_path, [rollout])
            self.assertEqual(result["status"], "structurally_verified", result)
            self.assertEqual(result["desktop_acceptance"], "unverified")
            raw["output"] = "different"
            save("raw.json", raw)
            result = verify_cli_preflight(manifest_path, raw_path, grade_path, bundle_path, [rollout])
            self.assertEqual(result["status"], "blocked")
            self.assertIn("raw output differs", " ".join(result["errors"]))


if __name__ == "__main__":
    unittest.main()
