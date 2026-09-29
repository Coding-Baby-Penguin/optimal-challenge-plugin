import json
import tempfile
import unittest
from pathlib import Path
import yaml

class QualityRunnerTests(unittest.TestCase):
    def test_hosted_workflow_parses_and_runs_structural_gate_on_both_platforms(self):
        workflow = yaml.safe_load((Path(__file__).resolve().parents[2] / ".github/workflows/quality.yml").read_text(encoding="utf-8"))
        job = workflow["jobs"]["structural"]
        self.assertEqual(set(job["strategy"]["matrix"]["os"]), {"ubuntu-24.04", "windows-2025"})
        commands = [step["run"] for step in job["steps"] if "run" in step]
        self.assertTrue(all(isinstance(command, str) for command in commands))
        self.assertTrue(any("scripts/check_quality.py --mode structural" in command for command in commands))

    def test_missing_or_unpinned_prerequisites_block_with_actionable_reason(self):
        from scripts.check_quality import validate_environment
        self.assertEqual(validate_environment((3,12),{"jsonschema":"4.25.1","PyYAML":"6.0.2"}),[])
        self.assertTrue(validate_environment((3,11),{}))
        errors=validate_environment((3,12),{"jsonschema":"4.25.0","PyYAML":"6.0.2"})
        self.assertIn("requirements-dev.lock"," ".join(errors))

    def test_structural_status_never_establishes_host_release_acceptance(self):
        from scripts.check_quality import release_gate
        self.assertEqual(release_gate(None)["status"],"blocked")
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root / "summary.json").write_text(json.dumps({"structural":"pass","host":"verified","score":100}))
            result=release_gate(root)
            self.assertEqual(result["status"],"blocked")
            self.assertTrue(result["reasons"])

    def test_zero_test_discovery_cannot_pass(self):
        import sys
        from scripts.check_quality import execute_check
        result=execute_check("unit",[sys.executable,"-c","print('Ran 0 tests')"],Path.cwd())
        self.assertEqual(result["status"],"failed")
        self.assertIn("zero",result["output"].lower())

    def test_timeout_retains_partial_diagnostics(self):
        import sys
        from scripts.check_quality import execute_check
        result=execute_check("timeout",[sys.executable,"-c","import time; print('BEFORE_TIMEOUT',flush=True); time.sleep(4)"],Path.cwd(),timeout_seconds=1.5)
        self.assertEqual(result["status"],"blocked")
        self.assertIn("BEFORE_TIMEOUT",result["output"])
        self.assertIn("timeout",result["output"].lower())

    def test_bad_policy_and_failed_subprocess_remain_failed(self):
        import sys
        from scripts.check_quality import execute_check
        result=execute_check("failure",[sys.executable,"-c","raise SystemExit(7)"],Path.cwd())
        self.assertEqual(result["status"],"failed")
        self.assertEqual(result["returncode"],7)

    def test_checkpoint_claim_paraphrases_cannot_unlock_release(self):
        from scripts.check_quality import release_gate
        for claim in ("We have verified fresh-host acceptance.","All host gates are green.","Independent approval: 100/100."):
            with self.subTest(claim=claim), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                (root / "PROJECT-STATE.md").write_text(claim)
                (root / "summary.json").write_text(json.dumps({"host":"verified","claim":claim,"structural":"pass"}))
                self.assertEqual(release_gate(root)["status"],"blocked")
