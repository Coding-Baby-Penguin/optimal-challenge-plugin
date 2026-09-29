import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_cli_pilot import prepare_run


class CliPilotPreparationTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.seed = self.root / "seeds"
        (self.seed / "code" / "app").mkdir(parents=True)
        (self.seed / "code" / "app" / "task.py").write_bytes(b"VALUE = 0\n")
        (self.seed / "code" / "ignored.pyc").write_bytes(b"do not copy")
        digest = hashlib.sha256(b"VALUE = 0\n").hexdigest()
        manifest = {
            "pilot_version": 1, "status": "frozen-before-first-run",
            "arms": ["A", "D", "B", "C"], "host": "codex-cli", "surface": "codex-cli-local",
            "task_prompt_prefix": "Invoke the installed plugin.",
            "cases": [{"id": "fix-code", "workspace": "code", "prompt": "Fix app/task.py", "oracle": "Set VALUE to 1"}],
            "workspace_file_sha256s": {"code": {"app/task.py": digest}},
        }
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        self.manifest_sha = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def test_only_pinned_seed_bytes_and_prompt_reach_disposable_run(self):
        output = self.root / "runs" / "run-1"
        plan = prepare_run(self.manifest, self.manifest_sha, self.seed, "fix-code", "B", "run-1", output)
        self.assertEqual((output / "workspace/app/task.py").read_bytes(), b"VALUE = 0\n")
        self.assertFalse((output / "workspace/ignored.pyc").exists())
        self.assertEqual(list((output / "host-home").iterdir()), [])
        self.assertNotIn("oracle", (output / "run-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["status"], "prepared-unrun")
        self.assertIsNone(plan["outer_wall_seconds"])
        with self.assertRaisesRegex(ValueError, "fresh"):
            prepare_run(self.manifest, self.manifest_sha, self.seed, "fix-code", "B", "run-1", output)

    def test_changed_manifest_or_seed_blocks_without_creating_run(self):
        output = self.root / "run"
        (self.seed / "code/app/task.py").write_bytes(b"VALUE = 7\n")
        with self.assertRaisesRegex(ValueError, "seed bytes"):
            prepare_run(self.manifest, self.manifest_sha, self.seed, "fix-code", "A", "run-2", output)
        self.assertFalse(output.exists())
        (self.seed / "code/app/task.py").write_bytes(b"VALUE = 0\n")
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest differs"):
            prepare_run(self.manifest, self.manifest_sha, self.seed, "fix-code", "A", "run-2", output)

    def test_traversal_and_wrong_arm_block(self):
        output = self.root / "run"
        with self.assertRaisesRegex(ValueError, "arm"):
            prepare_run(self.manifest, self.manifest_sha, self.seed, "fix-code", "E", "run-3", output)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            prepare_run(self.manifest, self.manifest_sha, self.seed, "fix-code", "A", "../run-3", output)

    def test_run_scoping_rejects_reused_task7_checkpoint_home(self):
        from scripts.verify_cli_pilot_run import verify_run_scoping
        output = self.root / "run"
        home = output / "host-home"
        installed = home / "plugins/cache/quality-B-local/optimal-challenge/1.2.0"
        registry = output / "registry-readback.json"
        stream = output / "stream.jsonl"
        rollout = home / "sessions/one.jsonl"
        for path in (installed, rollout.parent):
            path.mkdir(parents=True)
        for path in (registry, stream, rollout):
            path.write_bytes(b"{}\n")
        self.assertEqual(verify_run_scoping(output, home, installed, registry, stream, [rollout]), [])
        checkpoint = self.root / "task7-checkpoint/plugins/cache/quality-B-local/optimal-challenge/1.2.0"
        checkpoint.mkdir(parents=True)
        self.assertTrue(any("per-run host home" in error for error in
                            verify_run_scoping(output, home, checkpoint, registry, stream, [rollout])))

    def test_registry_inventory_preserves_remote_plugins_and_rejects_second_local_subject(self):
        from scripts.verify_cli_pilot_run import compare_ambient_plugin_inventories, summarize_registry_inventory
        target = {"pluginId": "optimal-challenge@quality-A-local", "name": "optimal-challenge",
                  "version": "1.1.0", "marketplaceName": "quality-A-local", "installed": True,
                  "enabled": True, "source": {"source": "local", "path": "C:/run/marketplace/optimal-challenge"}}
        remote = {"pluginId": "superpowers@openai-curated-remote", "name": "superpowers",
                  "version": "6.4.2", "marketplaceName": "openai-curated-remote", "installed": True,
                  "enabled": True, "source": {"source": "remote"}}
        inventory, errors = summarize_registry_inventory({"installed": [target, remote]}, target["pluginId"])
        self.assertEqual(errors, [])
        self.assertEqual(inventory["status"], "target_verified_with_shared_remote_plugins")
        self.assertEqual([item["plugin_id"] for item in inventory["other_installed_enabled"]],
                         ["superpowers@openai-curated-remote"])
        another_target = {**target, "pluginId": "optimal-challenge@quality-D-local",
                          "marketplaceName": "quality-D-local"}
        other_inventory, errors = summarize_registry_inventory(
            {"installed": [remote, another_target]}, another_target["pluginId"])
        self.assertEqual(errors, [])
        first_receipt = {"status": "identity_activation_verified", "registry_inventory": inventory}
        second_receipt = {"status": "identity_activation_verified", "registry_inventory": other_inventory}
        self.assertEqual(compare_ambient_plugin_inventories([first_receipt, second_receipt]), [])
        remote["version"] = "changed"
        changed_inventory, errors = summarize_registry_inventory(
            {"installed": [remote, another_target]}, another_target["pluginId"])
        self.assertEqual(errors, [])
        self.assertIn("differs", " ".join(compare_ambient_plugin_inventories(
            [first_receipt, {"status": "identity_activation_verified", "registry_inventory": changed_inventory}])))
        second = {**target, "pluginId": "optimal-challenge@quality-D-local",
                  "marketplaceName": "quality-D-local"}
        _, errors = summarize_registry_inventory({"installed": [target, remote, second]}, target["pluginId"])
        self.assertIn("second local subject", " ".join(errors))

    def test_native_skill_read_requires_exact_installed_bytes_and_session(self):
        from scripts.verify_cli_pilot_run import verify_skill_activation
        skill = self.root / "host-home/plugins/cache/local/plugin/1.2.0/skills/optimal-challenge/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_bytes(b"# Installed\n")
        stream = self.root / "stream.jsonl"
        command = "pwsh -Command Get-Content -LiteralPath '" + str(skill.resolve()).replace("\\", "\\\\") + "'"
        events = [
            {"type": "thread.started", "thread_id": "session-1"},
            {"type": "item.completed", "item": {"id": "read-1", "type": "command_execution", "command": command,
                                             "aggregated_output": "# Installed\r\n", "exit_code": 0, "status": "completed"}},
            {"type": "item.completed", "item": {"id": "answer", "type": "agent_message", "text": "Done"}},
            {"type": "turn.completed", "usage": {}},
        ]
        stream.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")
        audit = {"root_session_id": "session-1", "output_sha256": hashlib.sha256(b"Done").hexdigest()}
        self.assertEqual(verify_skill_activation(stream, skill, audit)["skill_read_event_ids"], ["read-1"])
        events[1]["item"]["aggregated_output"] = "# Different\r\n"
        stream.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "no successful read"):
            verify_skill_activation(stream, skill, audit)

    def test_outer_timer_records_full_wrapped_command_and_failure(self):
        from scripts.time_cli_pilot_job import time_job
        success = time_job([sys.executable, "-c", "print('ready')"], self.root / "success.json", timeout_seconds=10)
        self.assertEqual(success["status"], "completed")
        self.assertGreaterEqual(success["outer_whole_job_wall_seconds"], 0)
        self.assertEqual(success["scope_claim"].split(";", 1)[0], "unreviewed")
        self.assertEqual(json.loads((self.root / "success.argv.json").read_text()), [sys.executable, "-c", "print('ready')"])
        self.assertEqual((self.root / "success.stdout.log").read_text().strip(), "ready")
        failure = time_job([sys.executable, "-c", "raise SystemExit(7)"], self.root / "failure.json", timeout_seconds=10)
        self.assertEqual(failure["status"], "failed")
        self.assertEqual(failure["returncode"], 7)
        with self.assertRaisesRegex(ValueError, "fresh"):
            time_job([sys.executable, "-c", "pass"], self.root / "success.json", timeout_seconds=10)

    def test_native_settings_must_match_frozen_cli_surface(self):
        from scripts.verify_cli_pilot_run import validate_surface_audit
        surface = json.loads((Path(__file__).resolve().parents[2] / "tests/subjects/cli-pilot-surface.json").read_text())
        native = {field: surface[field] for field in ("host", "host_source", "surface", "host_version", "model", "reasoning")}
        native["usage"] = {"model_calls": None}
        self.assertEqual(validate_surface_audit(surface, native), [])
        native["model"] = "another-model"
        self.assertIn("model", " ".join(validate_surface_audit(surface, native)))

    def test_prelaunch_snapshot_preserves_exact_seed_before_code_edits(self):
        from scripts.snapshot_cli_pilot_input import snapshot_input
        from scripts.verify_cli_pilot_run import verify_prelaunch_snapshot
        output = self.root / "run-prelaunch"
        prepare_run(self.manifest, self.manifest_sha, self.seed, "fix-code", "D", "run-prelaunch", output)
        record = snapshot_input(output / "run-plan.json", self.manifest)
        self.assertEqual(record["status"], "captured-unreviewed")
        self.assertEqual(verify_prelaunch_snapshot(output / "run-plan.json", self.manifest)[1], [])
        (output / "workspace/app/task.py").write_bytes(b"VALUE = 1\n")
        self.assertEqual(verify_prelaunch_snapshot(output / "run-plan.json", self.manifest)[1], [])
        (output / "prelaunch-input/app/task.py").write_bytes(b"VALUE = 2\n")
        self.assertTrue(verify_prelaunch_snapshot(output / "run-plan.json", self.manifest)[1])
