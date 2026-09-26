from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts.orchestration_config import load_effective_config, validate_config


ROOT = Path(__file__).resolve().parents[2]


class OrchestrationConfigTests(unittest.TestCase):
    def test_balanced_auto_defaults_are_quiet(self):
        schema_path = ROOT / "config" / "orchestration.schema.json"
        committed_path = ROOT / "config" / "orchestration.json"
        self.assertTrue(schema_path.is_file())
        self.assertTrue(committed_path.is_file())

        output = io.StringIO()
        with redirect_stdout(output):
            config = load_effective_config(ROOT)

        self.assertEqual(config["mode"], "auto")
        self.assertEqual(config["profile"], "balanced")
        self.assertEqual(
            config["objective_weights"],
            {
                "quality": 0.45,
                "cost": 0.20,
                "latency": 0.10,
                "attention": 0.10,
                "rework": 0.15,
            },
        )
        self.assertFalse(config["premise_gate"]["apply_to_direct_fast_path"])
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(json.loads(committed_path.read_text(encoding="utf-8")), config)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        for key in [
            "objective_weights",
            "team_limits",
            "premise_gate",
            "verification",
            "persistence_privacy",
            "budget",
        ]:
            self.assertFalse(schema["properties"][key]["additionalProperties"], key)
        self.assertEqual(validate_config(config), [])

    def test_task_override_beats_local_and_committed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / ".optimal-challenge").mkdir()
            (root / "config" / "orchestration.json").write_text(
                json.dumps({"profile": "economy", "team_limits": {"retry_limit": 1}}),
                encoding="utf-8",
            )
            (root / ".optimal-challenge" / "orchestration.local.json").write_text(
                json.dumps({"profile": "quality", "team_limits": {"retry_limit": 2}}),
                encoding="utf-8",
            )

            config = load_effective_config(
                root,
                task_override={"profile": "custom", "team_limits": {"retry_limit": 4}},
            )

        self.assertEqual(config["profile"], "custom")
        self.assertEqual(config["team_limits"]["retry_limit"], 4)

    def test_unknown_key_fails(self):
        config = load_effective_config(ROOT)
        config["surprise"] = True

        errors = validate_config(config)

        self.assertTrue(any("$.surprise" in error and "unknown" in error.lower() for error in errors), errors)

    def test_invalid_measurement_enforcement_pair_fails(self):
        config = load_effective_config(ROOT)
        config["budget"]["measurement"] = "estimated"
        config["budget"]["enforcement"] = "provider_enforced"
        config["budget"]["measurement_source"] = "provider counter"

        errors = validate_config(config)

        self.assertTrue(
            any("$.budget.enforcement" in error and "observed" in error.lower() for error in errors),
            errors,
        )

    def test_custom_weights_sum_to_one(self):
        config = load_effective_config(ROOT)
        config["profile"] = "custom"
        config["objective_weights"]["quality"] = 0.40

        errors = validate_config(config)

        self.assertTrue(any("$.objective_weights" in error and "sum to 1" in error for error in errors), errors)

    def test_custom_margin_override_defaults_false(self):
        config = load_effective_config(ROOT, task_override={"profile": "custom"})

        self.assertFalse(config["team_limits"]["allow_mode_margin_override"])
        self.assertEqual(config["team_limits"]["delegation_margin"], 1)

    def test_exact_specialists_uses_minimum_host_limit(self):
        config = load_effective_config(
            ROOT,
            task_override={"team_limits": {"exact_specialists": 4}},
        )

        errors = validate_config(config, detected_host_max=3)

        self.assertTrue(
            any("$.team_limits.exact_specialists" in error and "maximum 3" in error for error in errors),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
