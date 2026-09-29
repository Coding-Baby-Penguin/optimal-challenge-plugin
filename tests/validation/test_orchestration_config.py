from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from scripts.orchestration_config import VerifiedCapabilityContext, issue_config_capability_context, load_effective_config, validate_config
from scripts.capability_matrix import EnforcementProof, UsageCounterProof, issue_adapter_evidence


ROOT = Path(__file__).resolve().parents[2]


class OrchestrationConfigTests(unittest.TestCase):
    def test_rejects_nonfinite_budget_values(self):
        for field in ("limit", "soft_threshold"):
            for value in (float("nan"),float("inf"),float("-inf"),json.loads("1e309"),True,"bad",[]):
                with self.subTest(field=field,value=value):
                    config=load_effective_config(ROOT)
                    config["budget"].update(unit="tokens",limit=100,soft_threshold=50)
                    config["budget"][field]=value
                    self.assertTrue(validate_config(config),f"accepted {field}={value!r}")

    def test_rejects_nonfinite_values_in_each_precedence_layer(self):
        for layer in ("committed","local","task"):
            for field in ("limit","soft_threshold"):
                for value in (float("nan"),float("inf"),float("-inf"),json.loads("1e309")):
                    with self.subTest(layer=layer,field=field,value=value), tempfile.TemporaryDirectory() as directory:
                        root=Path(directory)
                        budget={"unit":"tokens","limit":100,"soft_threshold":50}
                        budget[field]=value
                        override={"budget":budget}
                        if layer!="task":
                            path=root / ("config/orchestration.json" if layer=="committed" else ".optimal-challenge/orchestration.local.json")
                            path.parent.mkdir(parents=True)
                            path.write_text(json.dumps(override),encoding="utf-8")
                        with self.assertRaises(ValueError):
                            load_effective_config(root, task_override=override if layer=="task" else None)

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

    def test_enforced_budget_requires_trusted_matching_capability_context(self):
        config = load_effective_config(ROOT)
        config["budget"].update(
            {
                "unit": "tokens",
                "limit": 1000,
                "measurement": "observed",
                "enforcement": "provider_enforced",
                "measurement_source": "provider usage counter",
            }
        )
        now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
        invented = VerifiedCapabilityContext(
            surface="codex-local",
            version="1.2.3",
            provenance="live_detection",
            evidence_ref="acceptance:capability-17",
            verified_at=now - timedelta(minutes=5),
            expires_at=now + timedelta(minutes=55),
            observed_usage=True,
            local_stop_primitive=False,
            provider_stop_primitive=True,
        )

        def policy(capability):
            return {
                "surface_id": "codex-local", "capability": capability,
                "support_level": "policy-only", "detector": "policy:fixture",
                "evidence_ref": "policy:fixture", "verified_version": "1.2.3",
                "verified_at": "2026-09-01T00:00:00Z", "expires_at": "2026-12-01T00:00:00Z",
                "provenance": "policy_declaration", "required_fallback": "advisory",
                "measurement_surface": "codex-product-usage",
            }

        counter = UsageCounterProof("codex-local", "1.2.3", "codex-product-usage", "counter:fixture", True)
        def evidence(capability, proof):
            return issue_adapter_evidence(
                surface_id="codex-local", capability=capability, support_level="observed",
                adapter_id="codex-host", evidence_id=f"fixture-{capability}",
                verified_version="1.2.3", verified_at=now - timedelta(minutes=5),
                expires_at=now + timedelta(minutes=55), provenance="live_detection",
                required_fallback="advisory", proof=proof,
            )
        # These proofs are synthetically issued by a unit fixture. The current
        # CLI has no audited executable budget-stop adapter, so they must not
        # unlock provider enforcement in the released loader.
        with self.assertRaisesRegex(ValueError, "no observed executable stop adapter"):
            issue_config_capability_context(
                surface="codex-local", version="1.2.3",
                usage_evidence=evidence("usage_measurement", counter),
                enforcement_evidence=evidence(
                    "provider_enforcement",
                    EnforcementProof("codex-local", "1.2.3", counter, "provider", "codex_provider_stop"),
                ),
                usage_policy=policy("usage_measurement"),
                enforcement_policy=policy("provider_enforcement"), now=now,
            )

        missing_context_errors = validate_config(config)
        self.assertTrue(
            any("$context.capabilities" in error for error in missing_context_errors),
            missing_context_errors,
        )
        self.assertTrue(any("trusted adapter" in error for error in validate_config(
            config, capability_context=invented, expected_surface="codex-local",
            expected_version="1.2.3", now=now)), "caller-created context must be rejected")
        with self.assertRaisesRegex(ValueError, "trusted adapter capability context"):
            load_effective_config(
                ROOT,
                task_override={"budget": {"unit": "tokens", "limit": 1000,
                                          "measurement": "observed", "enforcement": "provider_enforced",
                                          "measurement_source": "provider usage counter"}},
                expected_surface="codex-local", expected_version="1.2.3", now=now,
            )
        config["budget"]["enforcement"] = "advisory"
        self.assertEqual(validate_config(config, expected_surface="codex-local",
                                         expected_version="1.2.3", now=now), [])

    def test_user_configuration_cannot_supply_capability_evidence(self):
        untrusted = {
            "budget": {
                "adapter_capabilities": {
                    "observed_measurement": {"verified": True, "evidence_id": "self-asserted"},
                    "provider_stop": {"verified": True, "evidence_id": "self-asserted"},
                }
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / ".optimal-challenge").mkdir()
            committed = root / "config" / "orchestration.json"
            local = root / ".optimal-challenge" / "orchestration.local.json"

            committed.write_text(json.dumps(untrusted), encoding="utf-8")
            with self.assertRaises(ValueError) as committed_error:
                load_effective_config(root)
            self.assertIn("$.budget.adapter_capabilities", str(committed_error.exception))

            committed.write_text("{}", encoding="utf-8")
            local.write_text(json.dumps(untrusted), encoding="utf-8")
            with self.assertRaises(ValueError) as local_error:
                load_effective_config(root)
            self.assertIn("$.budget.adapter_capabilities", str(local_error.exception))

            local.unlink()
            with self.assertRaises(ValueError) as task_error:
                load_effective_config(root, task_override=untrusted)
            self.assertIn("$.budget.adapter_capabilities", str(task_error.exception))
            self.assertIn("unknown configuration key", str(task_error.exception))

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

    def test_profile_layers_apply_atomic_weights_and_delegation_margins(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / ".optimal-challenge").mkdir()
            committed = root / "config" / "orchestration.json"
            local = root / ".optimal-challenge" / "orchestration.local.json"
            committed.write_text(json.dumps({"profile": "economy"}), encoding="utf-8")

            economy = load_effective_config(root)
            self.assertEqual(economy["objective_weights"]["cost"], 0.35)
            self.assertEqual(economy["team_limits"]["delegation_margin"], 3)

            local.write_text(json.dumps({"profile": "balanced"}), encoding="utf-8")
            balanced = load_effective_config(root)
            self.assertEqual(balanced["objective_weights"]["quality"], 0.45)
            self.assertEqual(balanced["team_limits"]["delegation_margin"], 1)

            quality = load_effective_config(root, task_override={"profile": "quality"})
            self.assertEqual(quality["objective_weights"]["rework"], 0.25)
            self.assertEqual(quality["team_limits"]["delegation_margin"], 1)

            local.unlink()
            custom_default = load_effective_config(root, task_override={"profile": "custom"})
            self.assertEqual(custom_default["team_limits"]["delegation_margin"], 1)
            custom_seven = load_effective_config(
                root,
                task_override={"profile": "custom", "team_limits": {"delegation_margin": 7}},
            )
            self.assertEqual(custom_seven["team_limits"]["delegation_margin"], 7)
            custom_partial_weights = load_effective_config(
                root,
                task_override={
                    "profile": "custom",
                    "objective_weights": {"quality": 0.50, "cost": 0.15},
                },
            )
            self.assertEqual(
                custom_partial_weights["objective_weights"],
                {
                    "quality": 0.50,
                    "cost": 0.15,
                    "latency": 0.10,
                    "attention": 0.10,
                    "rework": 0.15,
                },
            )

    def test_malformed_enum_values_are_path_qualified_in_each_override_layer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / ".optimal-challenge").mkdir()
            (root / "config" / "orchestration.json").write_text("{}", encoding="utf-8")
            local = root / ".optimal-challenge" / "orchestration.local.json"
            local.write_text(json.dumps({"mode": []}), encoding="utf-8")

            with self.assertRaises(ValueError) as local_error:
                load_effective_config(root)
            self.assertIn(".optimal-challenge/orchestration.local.json", str(local_error.exception))
            self.assertIn("$.mode", str(local_error.exception))

            local.unlink()
            with self.assertRaises(ValueError) as task_error:
                load_effective_config(root, task_override={"profile": {}})
            self.assertIn("task_override", str(task_error.exception))
            self.assertIn("$.profile", str(task_error.exception))

    def test_invalid_lower_layer_cannot_be_hidden_by_higher_layer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / ".optimal-challenge").mkdir()
            (root / "config" / "orchestration.json").write_text(
                json.dumps({"profile": "economy", "team_limits": {"delegation_margin": 2}}),
                encoding="utf-8",
            )
            (root / ".optimal-challenge" / "orchestration.local.json").write_text(
                json.dumps({"profile": "quality"}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as committed_error:
                load_effective_config(root)
            self.assertIn("config/orchestration.json", str(committed_error.exception))
            self.assertIn("$.team_limits.delegation_margin", str(committed_error.exception))

    def test_draft_2020_12_schema_enforces_named_profile_weights(self):
        schema = json.loads((ROOT / "config" / "orchestration.schema.json").read_text(encoding="utf-8"))
        committed = json.loads((ROOT / "config" / "orchestration.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(committed)

        named_profiles = {
            "economy": (
                {"quality": 0.35, "cost": 0.35, "latency": 0.10, "attention": 0.10, "rework": 0.10},
                3,
            ),
            "balanced": (
                {"quality": 0.45, "cost": 0.20, "latency": 0.10, "attention": 0.10, "rework": 0.15},
                1,
            ),
            "quality": (
                {"quality": 0.50, "cost": 0.10, "latency": 0.05, "attention": 0.10, "rework": 0.25},
                1,
            ),
        }
        for profile, (weights, margin) in named_profiles.items():
            with self.subTest(profile=profile):
                valid = deepcopy(committed)
                valid["profile"] = profile
                valid["objective_weights"] = weights
                valid["team_limits"]["delegation_margin"] = margin
                validator.validate(valid)

                adversarial = deepcopy(valid)
                adversarial["objective_weights"]["quality"] -= 0.05
                adversarial["objective_weights"]["cost"] += 0.05
                with self.assertRaises(ValidationError):
                    validator.validate(adversarial)

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
