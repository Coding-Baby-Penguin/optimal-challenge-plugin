from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "evaluate_behavior.py"
SPEC = importlib.util.spec_from_file_location("evaluate_behavior", MODULE_PATH) if MODULE_PATH.exists() else None
EVALUATOR = importlib.util.module_from_spec(SPEC) if SPEC is not None else None
if SPEC is not None and SPEC.loader is not None:
    SPEC.loader.exec_module(EVALUATOR)


def require_evaluator(test: unittest.TestCase):
    test.assertIsNotNone(EVALUATOR, "scripts/evaluate_behavior.py must exist")
    return EVALUATOR


def subject(arm_id: str = "D", *, version: str = "1.2.0") -> dict:
    policy_overrides = {
        "A": {"release": "v1.1", "delegation": "v1.1-routing", "continuity": "v1.1-routing", "premise_gate": "v1.1-routing"},
        "B": {"release": "v1.2-candidate", "delegation": "always-for-decomposable", "continuity": "disabled", "premise_gate": "disabled"},
        "C": {"release": "v1.2-candidate", "delegation": "economic-gate", "continuity": "disabled", "premise_gate": "disabled"},
        "D": {"release": "v1.2-candidate", "delegation": "economic-gate", "continuity": "enabled", "premise_gate": "enabled"},
    }
    return {
        "arm_id": arm_id,
        "policy_overrides": policy_overrides[arm_id],
        "commit": "d" * 40,
        "tag": f"v{version}",
        "archive_sha256": "a" * 64,
        "expected_manifest_version": version,
        "cachebuster": f"acceptance-{arm_id.lower()}-001",
        "install_source": "isolated-local-archive",
        "installed_plugin_read_back": {
            "name": "optimal-challenge",
            "version": version,
            "cachebuster": f"acceptance-{arm_id.lower()}-001",
            "archive_sha256": "a" * 64,
        },
    }


def manifest(*, minimum_runs: int = 5) -> dict:
    return {
        "manifest_version": 1,
        "prompt_hashes": {"system": "1" * 64, "task_template": "2" * 64},
        "fixture_hashes": {
            "behavioral_acceptance": "3" * 64,
            "team_routing": "4" * 64,
        },
        "host": "codex-desktop",
        "surface": "codex-local",
        "model": "host-configured",
        "reasoning": "host-configured",
        "tool_set": ["filesystem", "shell", "collaboration"],
        "profile": "balanced",
        "config_sha256": "5" * 64,
        "evaluator_version": "1.0.0",
        "rubric_version": "1.0.0",
        "randomization": {"method": "seeded-counterbalance", "seed": 12027},
        "minimum_run_count": minimum_runs,
        "aggregation": {
            "quality": "mean",
            "cost": "median-observed-only",
            "latency": "median-observed-only",
            "pass_rate": "raw-proportion",
            "confidence_interval": "paired-bootstrap-95",
        },
        "margins": {
            "quality_noninferiority": 0.10,
            "simple_task_cost_latency": 0.05,
            "high_value_quality_gain": 0.20,
            "high_value_critical_path_reduction": 0.10,
            "unnecessary_spawn_rate_max": 0.10,
        },
        "arms": [
            subject("A", version="1.1.0"),
            subject("B"),
            subject("C"),
            subject("D"),
        ],
    }


def manifest_digest(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run(
    index: int,
    *,
    scenario_id: str = "direct-fast-path",
    category: str = "direct",
    quality: float = 3.0,
    passed: bool = True,
    cost: float | None = 10.0,
    latency: float | None = 10.0,
    critical_path: float | None = 10.0,
    provenance: str = "observed",
    spawn_count: int = 0,
    question_count: int = 0,
    unnecessary_spawn: bool = False,
    premise_reset: bool = False,
    repeated_settled_question: bool = False,
    unsafe_failures: list[str] | None = None,
) -> dict:
    return {
        "run_id": f"run-{index}",
        "replicate_id": index,
        "scenario_id": scenario_id,
        "category": category,
        "run_kind": "stochastic",
        "quality": quality,
        "passed": passed,
        "safety_authority_pass": not unsafe_failures,
        "budget_truthfulness_pass": True,
        "failure_visibility_pass": True,
        "cost": {"value": cost, "provenance": provenance},
        "latency": {"value": latency, "provenance": provenance},
        "critical_path": {"value": critical_path, "provenance": provenance},
        "proxies": {
            "model_calls": 1 + spawn_count,
            "spawn_count": spawn_count,
            "tool_calls": 1,
            "question_count": question_count,
        },
        "unnecessary_spawn": unnecessary_spawn,
        "premise_reset": premise_reset,
        "repeated_settled_question": repeated_settled_question,
        "unsafe_failures": unsafe_failures or [],
        "capability_result": "not-applicable",
        "expected_route": "direct",
        "observed_route": "direct",
        "expected_question_count": question_count,
        "expected_spawn_count": spawn_count,
        "prohibited_behaviors": [],
        "observed_behaviors": [],
        "evidence_refs": ["result:fixture"],
    }


def bundle(arm_id: str = "D", *, runs: list[dict] | None = None, version: str = "1.2.0") -> dict:
    m = manifest()
    selected_runs = deepcopy(runs if runs is not None else [run(i) for i in range(5)])
    for record in selected_runs:
        record["run_id"] = f"{arm_id}:{record['run_id']}"
    return {
        "bundle_version": 1,
        "arm_id": arm_id,
        "manifest_sha256": manifest_digest(m),
        "prompt_hashes": deepcopy(m["prompt_hashes"]),
        "fixture_hashes": deepcopy(m["fixture_hashes"]),
        "host": m["host"],
        "surface": m["surface"],
        "model": m["model"],
        "reasoning": m["reasoning"],
        "tool_set": deepcopy(m["tool_set"]),
        "profile": m["profile"],
        "config_sha256": m["config_sha256"],
        "evaluator_version": m["evaluator_version"],
        "rubric_version": m["rubric_version"],
        "randomization": deepcopy(m["randomization"]),
        "aggregation": deepcopy(m["aggregation"]),
        "margins": deepcopy(m["margins"]),
        "subject": subject(arm_id, version=version),
        "arm_policy": deepcopy(subject(arm_id, version=version)["policy_overrides"]),
        "isolation": {
            "fresh_task": True,
            "cache_cleared": True,
            "fresh_registry": True,
            "fresh_ledger": True,
            "registry_fingerprint": f"registry-{arm_id}",
            "ledger_fingerprint": f"ledger-{arm_id}",
            "config_fingerprint": m["config_sha256"],
            "prior_arm_state_detected": False,
        },
        "execution_order": list(range(1, len(selected_runs) + 1)),
        "run_count": len(selected_runs),
        "runs": selected_runs,
    }


class EvaluationArtifactTests(unittest.TestCase):
    def test_task_seven_artifacts_exist_and_parse(self):
        for relative in (
            "tests/behavioral-acceptance.json",
            "tests/evaluation-manifest.json",
            "tests/baselines/v1.1.json",
            "scripts/evaluate_behavior.py",
        ):
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file())
        for relative in (
            "tests/behavioral-acceptance.json",
            "tests/evaluation-manifest.json",
            "tests/baselines/v1.1.json",
        ):
            with self.subTest(json=relative):
                json.loads((ROOT / relative).read_text(encoding="utf-8"))

    def test_acceptance_matrix_covers_routes_ux_and_failure_boundaries(self):
        matrix = json.loads((ROOT / "tests/behavioral-acceptance.json").read_text(encoding="utf-8"))
        cases = matrix["cases"]
        categories = {case["category"] for case in cases}
        self.assertTrue({"direct", "premise", "invocation", "profile", "continuity", "budget", "review", "capability-fallback", "failure"} <= categories)
        required_routes = {
            "direct", "investigate", "default", "ask", "inline", "auto", "team-requested",
            "exact-specialists", "resolution-question", "resume", "rehydrate", "fresh", "blocked", "degraded",
        }
        self.assertTrue(required_routes <= {case["expected_route"] for case in cases})
        profiles = {case["config"].get("profile") for case in cases}
        self.assertTrue({"economy", "balanced", "quality", "custom"} <= profiles)
        for case in cases:
            self.assertIn(case["surface"], {"codex-local", "openai-api-agents", "claude-code-local", "anthropic-api-agent-sdk"})
            self.assertIsInstance(case["prohibited_behaviors"], list)
            self.assertIsInstance(case["expected_question_count"], int)
            self.assertIsInstance(case["expected_spawn_count"], int)
            self.assertIsInstance(case["evidence_requirement"], list)
            self.assertEqual(set(case["rubric"]), {"quality", "safety_authority", "budget_truthfulness", "failure_visibility"})
            if case["expected_question_count"]:
                self.assertEqual(
                    set(case["question_contract"]),
                    {"decision_id", "bundle", "recommendation", "impact", "next_step"},
                )
            else:
                self.assertIsNone(case["question_contract"])

    def test_manifest_pins_four_arms_identity_and_exact_research_margins(self):
        stored = json.loads((ROOT / "tests/evaluation-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual({arm["arm_id"] for arm in stored["arms"]}, {"A", "B", "C", "D"})
        self.assertEqual(stored["minimum_run_count"], 5)
        self.assertEqual(stored["margins"], manifest()["margins"])
        self.assertEqual(stored["arms"][0]["commit"], "c3c379ab5429d1bfef3c145260247bc72f8844f9")
        for arm in stored["arms"]:
            for field in ("commit", "tag", "archive_sha256", "expected_manifest_version", "cachebuster", "install_source", "installed_plugin_read_back"):
                self.assertIn(field, arm)
            self.assertRegex(arm["archive_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(set(arm["policy_overrides"]), {"release", "delegation", "continuity", "premise_gate"})
        self.assertTrue(stored["arms"][1]["evaluation_only"])

    def test_v11_baseline_is_truthfully_unverified(self):
        baseline = json.loads((ROOT / "tests/baselines/v1.1.json").read_text(encoding="utf-8"))
        self.assertEqual(baseline["subject_commit"], "c3c379ab5429d1bfef3c145260247bc72f8844f9")
        self.assertEqual(baseline["status"], "unverified")
        self.assertEqual(baseline["raw_result_ids"], [])
        self.assertIsNone(baseline["manifest_sha256"])
        self.assertIsNone(baseline["installed_plugin_read_back"])
        self.assertFalse(baseline["comparative_claims_allowed"])
        self.assertIn("fresh", baseline["next_action"].lower())


class BundleValidationTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = require_evaluator(self)
        self.manifest = manifest()

    def test_valid_bundle_has_no_errors(self):
        self.assertEqual(self.evaluator.validate_run_bundle(bundle(), self.manifest), [])

    def test_rejects_changed_prompt_fixture_evaluator_and_wrong_plugin_identity(self):
        mutations = {
            "prompt hash": lambda b: b["prompt_hashes"].__setitem__("system", "f" * 64),
            "fixture hash": lambda b: b["fixture_hashes"].__setitem__("team_routing", "f" * 64),
            "evaluator": lambda b: b.__setitem__("evaluator_version", "9.9.9"),
            "plugin version": lambda b: b["subject"]["installed_plugin_read_back"].__setitem__("version", "1.1.0"),
            "cachebuster": lambda b: b["subject"]["installed_plugin_read_back"].__setitem__("cachebuster", "stale-cache"),
            "archive": lambda b: b["subject"]["installed_plugin_read_back"].__setitem__("archive_sha256", "f" * 64),
            "arm policy": lambda b: b["arm_policy"].__setitem__("continuity", "wrong"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = bundle()
                mutate(candidate)
                errors = self.evaluator.validate_run_bundle(candidate, self.manifest)
                self.assertTrue(errors)
                self.assertIn(label.split()[0], " ".join(errors).lower())

        wrong_manifest = bundle()
        wrong_manifest["manifest_sha256"] = "f" * 64
        self.assertIn("manifest", " ".join(self.evaluator.validate_run_bundle(wrong_manifest, self.manifest)).lower())

    def test_rejects_cache_config_registry_or_ledger_leakage(self):
        mutations = {
            "cache": lambda b: b["isolation"].__setitem__("cache_cleared", False),
            "config": lambda b: b["isolation"].__setitem__("config_fingerprint", "wrong"),
            "registry": lambda b: b["isolation"].__setitem__("fresh_registry", False),
            "ledger": lambda b: b["isolation"].__setitem__("prior_arm_state_detected", True),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = bundle()
                mutate(candidate)
                self.assertIn(label, " ".join(self.evaluator.validate_run_bundle(candidate, self.manifest)).lower())

    def test_rejects_insufficient_runs_duplicate_ids_and_invalid_execution_order(self):
        too_few = bundle(runs=[run(i) for i in range(4)])
        duplicate = bundle(runs=[run(1) for _ in range(5)])
        wrong_order = bundle()
        wrong_order["execution_order"] = [1, 2, 3]
        self.assertIn("minimum", " ".join(self.evaluator.validate_run_bundle(too_few, self.manifest)).lower())
        self.assertIn("duplicate", " ".join(self.evaluator.validate_run_bundle(duplicate, self.manifest)).lower())
        self.assertIn("execution_order", " ".join(self.evaluator.validate_run_bundle(wrong_order, self.manifest)))

    def test_rejects_five_total_runs_when_each_stochastic_scenario_lacks_five(self):
        mixed = [run(i, scenario_id="one") for i in range(3)] + [run(i + 3, scenario_id="two") for i in range(2)]
        errors = self.evaluator.validate_run_bundle(bundle(runs=mixed), self.manifest)
        self.assertIn("per stochastic scenario", " ".join(errors).lower())

    def test_rejects_unsafe_failures_invalid_quality_and_false_measurement_precision(self):
        unsafe = bundle(runs=[run(i, unsafe_failures=["authority override"]) for i in range(5)])
        quality = bundle()
        quality["runs"][0]["quality"] = 4.1
        unavailable = bundle()
        unavailable["runs"][0]["cost"] = {"value": 1.0, "provenance": "unavailable"}
        self.assertIn("unsafe", " ".join(self.evaluator.validate_run_bundle(unsafe, self.manifest)).lower())
        self.assertIn("quality", " ".join(self.evaluator.validate_run_bundle(quality, self.manifest)).lower())
        self.assertIn("unavailable", " ".join(self.evaluator.validate_run_bundle(unavailable, self.manifest)).lower())

    def test_malformed_identifiers_and_behavior_lists_return_errors_not_exceptions(self):
        malformed = bundle()
        malformed["runs"][0]["run_id"] = {}
        malformed["runs"][0]["prohibited_behaviors"] = [{}]
        errors = self.evaluator.validate_run_bundle(malformed, self.manifest)
        self.assertTrue(errors)
        bad_manifest = manifest()
        bad_manifest["arms"][0]["arm_id"] = {}
        errors = self.evaluator.validate_run_bundle(bundle(), bad_manifest)
        self.assertTrue(errors)

    def test_rejects_route_spawn_question_prohibition_and_evidence_mismatches(self):
        mutations = {
            "route": lambda r: r.__setitem__("observed_route", "delegate"),
            "spawn": lambda r: r["proxies"].__setitem__("spawn_count", 1),
            "question": lambda r: r["proxies"].__setitem__("question_count", 1),
            "prohibited": lambda r: (r["prohibited_behaviors"].append("profile-chatter"), r["observed_behaviors"].append("profile-chatter")),
            "evidence": lambda r: r.__setitem__("evidence_refs", []),
            "budget": lambda r: r.__setitem__("budget_truthfulness_pass", False),
            "failure": lambda r: r.__setitem__("failure_visibility_pass", False),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = bundle()
                mutate(candidate["runs"][0])
                self.assertIn(label, " ".join(self.evaluator.validate_run_bundle(candidate, self.manifest)).lower())

    def test_records_non_safety_behavior_failure_when_truthfully_marked_failed(self):
        candidate = bundle()
        candidate["runs"][0]["observed_route"] = "delegate"
        candidate["runs"][0]["passed"] = False
        self.assertEqual(self.evaluator.validate_run_bundle(candidate, self.manifest), [])


class StatisticsAndComparisonTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = require_evaluator(self)
        self.manifest = manifest()

    def test_summary_reports_required_statistics_and_labels_proxy_only(self):
        observed = self.evaluator.summarize_arm([run(i, quality=3 + (i % 2), cost=10 + i, latency=20 + i) for i in range(5)])
        self.assertEqual(observed["run_count"], 5)
        self.assertEqual(observed["mean_quality"], 3.4)
        self.assertEqual(observed["median_cost"], 12.0)
        self.assertEqual(observed["median_latency"], 22.0)
        self.assertEqual(observed["pass_rate"], 1.0)
        self.assertFalse(observed["proxy_only"])

        proxy = self.evaluator.summarize_arm([run(i, cost=None, latency=None, critical_path=None, provenance="unavailable") for i in range(5)])
        self.assertIsNone(proxy["median_cost"])
        self.assertIsNone(proxy["median_latency"])
        self.assertTrue(proxy["proxy_only"])
        self.assertEqual(proxy["cost_claim"], "unavailable")

    def test_clear_noninferiority_with_no_regressions_passes_deterministically(self):
        base_runs = [
            run(i, scenario_id="direct" if i % 2 == 0 else "valuable", category="direct" if i % 2 == 0 else "high-value-delegation", quality=3.0, cost=10, latency=10, critical_path=10)
            for i in range(10)
        ]
        candidate_runs = [
            run(i, scenario_id="direct" if i % 2 == 0 else "valuable", category="direct" if i % 2 == 0 else "high-value-delegation", quality=3.0 if i % 2 == 0 else 3.3, cost=10, latency=10, critical_path=10 if i % 2 == 0 else 9)
            for i in range(10)
        ]
        result = self.evaluator.compare_arms(bundle("A", runs=base_runs, version="1.1.0"), bundle("D", runs=candidate_runs), self.manifest)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["quality_difference"], 0.15)
        self.assertEqual(result["confidence_interval"]["level"], 0.95)
        self.assertEqual(result["high_value_delegation"]["status"], "pass")

    def test_quality_regression_beyond_point_ten_fails(self):
        baseline = bundle("A", runs=[run(i, quality=3.0) for i in range(5)], version="1.1.0")
        candidate = bundle("D", runs=[run(i, quality=2.89) for i in range(5)])
        result = self.evaluator.compare_arms(baseline, candidate, self.manifest)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["quality_noninferiority"]["status"], "fail")

    def test_simple_task_cost_or_latency_increase_above_five_percent_fails(self):
        base = [run(i, scenario_id="simple", category="direct", cost=100, latency=100) for i in range(5)]
        for metric in ("cost", "latency"):
            with self.subTest(metric=metric):
                candidate = deepcopy(base)
                for item in candidate:
                    item[metric]["value"] = 105.1
                result = self.evaluator.compare_arms(bundle("A", runs=base, version="1.1.0"), bundle("D", runs=candidate), self.manifest)
                self.assertEqual(result["status"], "fail")
                self.assertEqual(result["simple_tasks"][metric]["status"], "fail")

    def test_high_value_gain_requires_point_two_quality_or_ten_percent_critical_path(self):
        base = [run(i, category="high-value-delegation", quality=3.0, critical_path=100) for i in range(5)]
        weak = [run(i, category="high-value-delegation", quality=3.19, critical_path=90.1) for i in range(5)]
        strong_quality = [run(i, category="high-value-delegation", quality=3.2, critical_path=100) for i in range(5)]
        strong_time = [run(i, category="high-value-delegation", quality=3.0, critical_path=90) for i in range(5)]
        weak_result = self.evaluator.compare_arms(bundle("A", runs=base, version="1.1.0"), bundle("D", runs=weak), self.manifest)
        self.assertEqual(weak_result["high_value_delegation"]["status"], "fail")
        self.assertEqual(self.evaluator.compare_arms(bundle("A", runs=base, version="1.1.0"), bundle("D", runs=strong_quality), self.manifest)["status"], "pass")
        self.assertEqual(self.evaluator.compare_arms(bundle("A", runs=base, version="1.1.0"), bundle("D", runs=strong_time), self.manifest)["status"], "pass")

    def test_unsafe_failure_and_spawn_or_question_regression_fail_closed(self):
        base = [run(i) for i in range(10)]
        cases = {
            "unsafe": [run(i, unsafe_failures=["budget lie"]) for i in range(10)],
            "spawn": [run(i, unnecessary_spawn=i < 2) for i in range(10)],
            "premise": [run(i, premise_reset=i == 0) for i in range(10)],
            "question": [run(i, repeated_settled_question=i == 0) for i in range(10)],
        }
        for label, candidate in cases.items():
            with self.subTest(label=label):
                result = self.evaluator.compare_arms(bundle("A", runs=base, version="1.1.0"), bundle("D", runs=candidate), self.manifest)
                self.assertEqual(result["status"], "fail")

    def test_comparison_rejects_changed_case_contract_or_reused_raw_result_id(self):
        base = bundle("A", version="1.1.0")
        changed = bundle("D")
        changed["runs"][0]["category"] = "high-value-delegation"
        result = self.evaluator.compare_arms(base, changed, self.manifest)
        self.assertEqual(result["status"], "fail")
        self.assertIn("case contract", " ".join(result["errors"]).lower())

        reused = bundle("D")
        reused["runs"][0]["run_id"] = base["runs"][0]["run_id"]
        result = self.evaluator.compare_arms(base, reused, self.manifest)
        self.assertEqual(result["status"], "fail")
        self.assertIn("raw result", " ".join(result["errors"]).lower())

    def test_uncertain_interval_is_inconclusive_not_improvement(self):
        base = [run(i, quality=value) for i, value in enumerate([1, 4, 1, 4, 2])]
        candidate = [run(i, quality=value) for i, value in enumerate([4, 1, 4, 1, 3])]
        result = self.evaluator.compare_arms(bundle("A", runs=base, version="1.1.0"), bundle("D", runs=candidate), self.manifest)
        self.assertEqual(result["status"], "inconclusive")
        self.assertNotEqual(result["quality_noninferiority"]["status"], "improvement")

    def test_unavailable_cost_uses_labelled_nonincreasing_proxies_without_cost_claim(self):
        base = [run(i, cost=None, latency=None, critical_path=None, provenance="unavailable", spawn_count=1) for i in range(5)]
        candidate = [run(i, cost=None, latency=None, critical_path=None, provenance="unavailable", spawn_count=1) for i in range(5)]
        result = self.evaluator.compare_arms(bundle("A", runs=base, version="1.1.0"), bundle("D", runs=candidate), self.manifest)
        self.assertEqual(result["simple_tasks"]["cost"]["status"], "proxy-only")
        self.assertFalse(result["simple_tasks"]["cost"]["claim_allowed"])
        self.assertEqual(result["status"], "pass")


class CliTests(unittest.TestCase):
    def test_cli_reports_unverified_inputs_without_comparative_claim(self):
        require_evaluator(self)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            manifest_path = temp / "manifest.json"
            baseline_path = temp / "baseline.json"
            candidate_path = temp / "candidate.json"
            manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")
            baseline_path.write_text(json.dumps({"status": "unverified"}), encoding="utf-8")
            candidate_path.write_text(json.dumps({"status": "unverified"}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--manifest", str(manifest_path), "--baseline", str(baseline_path), "--candidate", str(candidate_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("UNVERIFIED", result.stdout)
        self.assertNotIn("IMPROVED", result.stdout)


if __name__ == "__main__":
    unittest.main()
