from __future__ import annotations

import importlib.util
import hashlib
import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.evaluate_routing import score_delegation
from scripts.orchestration_config import load_effective_config
from scripts.optimal_challenge.evaluation_semantics import _compute_semantic_result


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "evaluate_behavior.py"
SPEC = importlib.util.spec_from_file_location("evaluate_behavior", MODULE_PATH) if MODULE_PATH.exists() else None
EVALUATOR = importlib.util.module_from_spec(SPEC) if SPEC is not None else None
if SPEC is not None and SPEC.loader is not None:
    SPEC.loader.exec_module(EVALUATOR)


def require_evaluator(test: unittest.TestCase):
    test.assertIsNotNone(EVALUATOR, "scripts/evaluate_behavior.py must exist")
    return EVALUATOR


def manifest() -> dict:
    return json.loads((ROOT / "tests/evaluation-manifest.json").read_text(encoding="utf-8"))


def acceptance() -> dict:
    return json.loads((ROOT / "tests/behavioral-acceptance.json").read_text(encoding="utf-8"))


def subject(arm_id: str = "D", **_ignored) -> dict:
    return deepcopy(next(arm for arm in manifest()["arms"] if arm["arm_id"] == arm_id))


def manifest_digest(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run(
    index: int,
    *,
    scenario_id: str = "accept-direct-fast-path",
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


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_run(case: dict, arm_id: str, replicate: int) -> dict:
    expected_questions = case["expected_question_count"]
    expected_spawns = case["expected_spawn_count"]
    question = case["question_contract"]
    calculation_contract = case["calculation_assertions"]
    semantic_contract = calculation_contract["semantic_contract"]
    profile = case["config"].get("profile", "balanced")
    margins = {"economy": 3, "balanced": 1, "quality": 1}
    calculation_inputs = deepcopy(semantic_contract["canonical_inputs"])
    evidence_refs = [f"evidence:{case['id']}:{item}" for item in case["evidence_requirement"]]
    artifact_sha256 = subject(arm_id)["archive_sha256"]
    raw_id = f"raw:{arm_id}:{case['id']}:{replicate}:{artifact_sha256[:12]}"
    grader_id = f"grader:{arm_id}:{case['id']}:{replicate}:{artifact_sha256[:12]}"
    return {
        "run_id": f"{arm_id}:{case['id']}:{replicate}",
        "replicate_id": replicate,
        "scenario_id": case["id"],
        "source_case_id": case["source_case_id"],
        "case_sha256": manifest_digest(case),
        "prompt_sha256": _sha_text(case["prompt"]),
        "category": case["category"],
        "run_kind": acceptance()["execution_policy"]["default_run_kind"],
        "evaluation_groups": deepcopy(case.get("evaluation_groups", [])),
        "quality": 3.0,
        "passed": True,
        "safety_authority_pass": True,
        "budget_truthfulness_pass": True,
        "failure_visibility_pass": True,
        "cost": {"value": 10.0, "provenance": "observed", "evidence_refs": evidence_refs[:1]},
        "latency": {"value": 10.0, "provenance": "observed", "evidence_refs": evidence_refs[:1]},
        "critical_path": {"value": 10.0, "provenance": "observed", "evidence_refs": evidence_refs[:1]},
        "proxies": {"model_calls": 1 + expected_spawns, "spawn_count": expected_spawns, "tool_calls": 1, "question_count": expected_questions},
        "unnecessary_spawn": False,
        "premise_reset": False,
        "repeated_settled_question": False,
        "unsafe_failures": [],
        "capability_result": "not-applicable",
        "expected_route": case["expected_route"],
        "observed_route": case["expected_route"],
        "expected_question_count": expected_questions,
        "expected_spawn_count": expected_spawns,
        "prohibited_behaviors": deepcopy(case["prohibited_behaviors"]),
        "observed_behaviors": [],
        "evidence_requirement": deepcopy(case["evidence_requirement"]),
        "evidence_refs": evidence_refs,
        "question_contract": deepcopy(question),
        "question_result": {
            "asked_count": expected_questions,
            "decision_id": question["decision_id"] if question else None,
            "bundle": question["bundle"] if question else None,
            "recommendation": question["recommendation"] if question else None,
            "impact": question["impact"] if question else None,
            "next_step": question["next_step"] if question else None,
            "actual_question": {
                "evidence_ref": f"question:{arm_id}:{case['id']}:{replicate}",
                "decision_id": question["decision_id"],
                "bundle": question["bundle"],
                "recommendation": question["recommendation"],
                "impact": question["impact"],
                "next_step": question["next_step"],
            } if question else None,
            "suppression": {
                "applied": "suppression" in case["id"],
                "reason": "settled decision retained" if "suppression" in case["id"] else "not applicable",
                "evidence_refs": evidence_refs[:1],
            },
        },
        "recommendation": f"recommended route: {case['expected_route']}",
        "output": f"observed route: {case['expected_route']}",
        "calculation_contract": deepcopy(calculation_contract),
        "calculation": {
            "formula": semantic_contract["formula_id"],
            "formula_version": semantic_contract["version"],
            "inputs": calculation_inputs,
            "results": deepcopy(semantic_contract["expected"]),
            "profile": profile,
            "profile_margin": case["config"].get("delegation_margin", margins.get(profile)),
            "provenance": calculation_contract.get("provenance", "observed"),
            "evidence_refs": evidence_refs,
        },
        "assertions": [{"id": f"assertion:{case['id']}", "provenance": calculation_contract.get("provenance", "observed"), "evidence_refs": evidence_refs}],
        "rubric_contract": deepcopy(case["rubric"]),
        "rubric_outcome": {dimension: {"score": 3.0, "passed": True, "evidence_refs": evidence_refs, "grader_evidence_id": grader_id} for dimension in case["rubric"]},
        "raw_evidence_refs": [{"identity_id": raw_id, "kind": "raw-result", "arm_id": arm_id, "scenario_id": case["id"], "replicate_id": replicate, "artifact_sha256": artifact_sha256}],
        "grader_evidence_refs": [{"identity_id": grader_id, "kind": "grader-result", "arm_id": arm_id, "scenario_id": case["id"], "replicate_id": replicate, "artifact_sha256": artifact_sha256, "raw_identity_id": raw_id, "independent": True}],
    }


def bundle(arm_id: str = "D", *, runs: list[dict] | None = None, **_ignored) -> dict:
    m = manifest()
    matrix = acceptance()
    repetitions = matrix["execution_policy"]["stochastic_repetitions"]
    applicable = [case for case in matrix["cases"] if case["surface"] == m["surface"]]
    selected_runs = deepcopy(runs if runs is not None else [_canonical_run(case, arm_id, repeat) for case in applicable for repeat in range(repetitions)])
    arm_order = m["randomization"]["execution_order"]
    run_order = [record["run_id"] for record in selected_runs]
    identity_status = subject(arm_id)["identity_status"]
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
        "subject": subject(arm_id),
        "arm_policy": deepcopy(subject(arm_id)["policy_overrides"]),
        "identity_verification": {
            "artifact": identity_status,
            "installed_read_back": identity_status,
            "run_identity": "verified",
            "surface": "verified",
        },
        "surface_evidence": {"surface_id": m["surface"], "status": "verified", "evidence_ref": f"evidence:surface:{arm_id}"},
        "isolation": {
            "fresh_task": True,
            "cache_cleared": True,
            "fresh_registry": True,
            "fresh_ledger": True,
            "task_fingerprint": _sha_text(f"task:{arm_id}"),
            "cache_fingerprint": _sha_text(f"cache:{arm_id}"),
            "artifact_fingerprint": subject(arm_id)["archive_sha256"],
            "registry_fingerprint": _sha_text(f"registry:{arm_id}"),
            "ledger_fingerprint": _sha_text(f"ledger:{arm_id}"),
            "config_fingerprint": m["config_sha256"],
            "environment_evidence_id": f"evidence:environment:{arm_id}",
            "prior_arm_state_detected": False,
        },
        "recorded_arm_order": deepcopy(arm_order),
        "arm_position": arm_order.index(arm_id) + 1,
        "randomization_evidence": {"seed": m["randomization"]["seed"], "method": m["randomization"]["method"], "evidence_ref": f"evidence:order:{arm_id}"},
        "execution_order": run_order,
        "execution_order_sha256": manifest_digest(run_order),
        "run_count": len(selected_runs),
        "runs": selected_runs,
    }


def refresh_execution_order(value: dict) -> None:
    value["execution_order"] = [record["run_id"] for record in value["runs"]]
    value["execution_order_sha256"] = manifest_digest(value["execution_order"])


def mutate_runs(value: dict, predicate, mutate) -> dict:
    for record in value["runs"]:
        if predicate(record):
            mutate(record)
    return value


def set_run_quality(record: dict, quality: float) -> None:
    record["quality"] = quality
    for outcome in record["rubric_outcome"].values():
        outcome["score"] = quality


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
        self.assertEqual(len(cases), 31)
        categories = {case["category"] for case in cases}
        self.assertTrue({"direct", "premise", "invocation", "profile", "continuity", "budget", "review", "capability-fallback", "failure"} <= categories)
        required_routes = {
            "direct", "investigate", "default", "ask", "inline", "auto", "delegate",
            "resolution-question", "resume", "rehydrate", "fresh", "blocked", "degraded",
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

    def test_every_case_has_a_typed_versioned_semantic_calculation_contract(self):
        for case in acceptance()["cases"]:
            with self.subTest(case=case["id"]):
                contract = case["calculation_assertions"].get("semantic_contract")
                self.assertIsInstance(contract, dict)
                self.assertRegex(contract["formula_id"], r"^[a-z][a-z0-9.-]+\.v1$")
                self.assertEqual(contract["version"], 1)
                self.assertIsInstance(contract["inputs"], dict)
                self.assertIsInstance(contract["expected"], dict)

    def test_question_bundle_canonical_filename_uses_exact_git_case(self):
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.splitlines()
        exact = "skills/optimal-challenge/templates/QUESTION-BUNDLE.md"
        self.assertIn(exact, tracked)
        self.assertNotIn("skills/optimal-challenge/templates/question-bundle.md", tracked)
        self.assertEqual(EVALUATOR.CANONICAL_FILES[("prompt_hashes", "question_bundle")].relative_to(ROOT).as_posix(), exact)

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

    def test_approved_fixture_identity_is_independent_of_manifest_and_fixture(self):
        self.assertEqual(EVALUATOR.APPROVED_BEHAVIORAL_FIXTURE_VERSION, 2)
        self.assertRegex(EVALUATOR.APPROVED_BEHAVIORAL_FIXTURE_SHA256, r"^[0-9a-f]{64}$")
        self.assertEqual(
            EVALUATOR.APPROVED_BEHAVIORAL_FIXTURE_SHA256,
            "a4dea28161fc5a593fda9ee9af5686750c337fae849daaf4262fd15ff5fb290e",
        )

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
        candidate["runs"][0]["passed"] = False
        candidate["runs"][0]["rubric_outcome"]["quality"]["passed"] = False
        candidate["runs"][0]["recommendation"] = "direct route selected, but the response quality failed"
        candidate["runs"][0]["output"] = "failed quality rubric with canonical routing evidence preserved"
        self.assertEqual(self.evaluator.validate_run_bundle(candidate, self.manifest), [])


class ReviewerRegressionTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = require_evaluator(self)
        self.manifest = manifest()

    def test_invented_only_suite_cannot_replace_canonical_matrix(self):
        invented = bundle(runs=[run(i, scenario_id="invented-only") for i in range(5)])
        errors = " ".join(self.evaluator.validate_run_bundle(invented, self.manifest)).lower()
        self.assertIn("missing canonical", errors)
        self.assertIn("invented", errors)

    def test_coordinated_bundle_and_manifest_hash_mutation_cannot_hide_fixture_drift(self):
        altered_manifest = manifest()
        altered_manifest["fixture_hashes"]["behavioral_acceptance"] = "f" * 64
        candidate = bundle()
        candidate["fixture_hashes"] = deepcopy(altered_manifest["fixture_hashes"])
        candidate["manifest_sha256"] = manifest_digest(altered_manifest)
        errors = " ".join(self.evaluator.validate_run_bundle(candidate, altered_manifest)).lower()
        self.assertIn("canonical", errors)
        self.assertIn("behavioral_acceptance", errors)
        altered_manifest = manifest()
        altered_manifest["prompt_hashes"]["invented"] = "f" * 64
        candidate = bundle()
        candidate["prompt_hashes"] = deepcopy(altered_manifest["prompt_hashes"])
        candidate["manifest_sha256"] = manifest_digest(altered_manifest)
        self.assertIn("exactly", " ".join(self.evaluator.validate_run_bundle(candidate, altered_manifest)).lower())

    def test_coordinated_on_disk_fixture_manifest_and_bundle_mutation_fails_approval_pin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            modified = acceptance()
            modified["cases"][0]["rubric"]["quality"] = "tampered quality anchor"
            fixture_path = Path(temp_dir) / "behavioral-acceptance.json"
            fixture_path.write_text(json.dumps(modified), encoding="utf-8")
            changed_hash = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
            altered_manifest = manifest()
            altered_manifest["fixture_hashes"]["behavioral_acceptance"] = changed_hash
            candidate = bundle()
            candidate["fixture_hashes"]["behavioral_acceptance"] = changed_hash
            candidate["manifest_sha256"] = manifest_digest(altered_manifest)
            for record in candidate["runs"]:
                if record["scenario_id"] == modified["cases"][0]["id"]:
                    record["case_contract"] = deepcopy(modified["cases"][0])
                    record["case_sha256"] = manifest_digest(modified["cases"][0])
                    record["rubric_contract"]["quality"] = "tampered quality anchor"
            key = ("fixture_hashes", "behavioral_acceptance")
            original_path = self.evaluator.CANONICAL_FILES[key]
            self.evaluator.CANONICAL_FILES[key] = fixture_path
            try:
                errors = " ".join(self.evaluator.validate_run_bundle(candidate, altered_manifest)).lower()
            finally:
                self.evaluator.CANONICAL_FILES[key] = original_path
        self.assertIn("approved behavioral fixture", errors)

    def test_named_profile_delegation_cases_match_task_two_routes_and_counts(self):
        cases = {case["id"]: case for case in acceptance()["cases"]}
        expected = {
            "accept-profile-economy": (1, 3, "inline", 0),
            "accept-profile-balanced": (1, 1, "delegate", 1),
            "accept-profile-quality": (1, 1, "delegate", 1),
        }
        for case_id, (value, margin, route, count) in expected.items():
            with self.subTest(case=case_id):
                case = cases[case_id]
                semantic = case["calculation_assertions"]["semantic_contract"]
                inputs = semantic["canonical_inputs"]
                benefits = sum(inputs[f"benefit_{name}"] for name in ("parallel", "independence", "context", "quality"))
                costs = sum(inputs[f"cost_{name}"] for name in ("setup", "transfer", "merge", "review_rework"))
                self.assertEqual(benefits - costs, value)
                self.assertEqual(inputs["margin"], margin)
                self.assertEqual(case["expected_route"], route)
                self.assertEqual(case["expected_spawn_count"], count)
                self.assertEqual(semantic["expected"]["route"], route)
                self.assertEqual(semantic["expected"]["specialist_count"], count)

    def test_team_sizing_exact_counts_match_task_two_routing(self):
        base_inputs = {
            "exact_specialists": None,
            "independent_workstreams": 0,
            "max_active_specialists": 3,
            "detected_host_max": 8,
            "available_slots": 8,
            "budget_capacity": 8,
            "authority_allows": True,
            "platform_available": True,
            "fits_job_envelope": True,
            "observable_done_condition": True,
            "benefit_parallel": 0,
            "benefit_independence": 0,
            "benefit_context": 0,
            "benefit_quality": 0,
            "cost_setup": 3,
            "cost_transfer": 3,
            "cost_merge": 3,
            "cost_review_rework": 3,
            "delegation_margin": 1,
        }
        cases = (
            (0, 8, 8, 8, "inline", 0),
            (1, 8, 8, 8, "delegate", 1),
            (5, 4, 4, 8, "resolution-question", 0),
            (5, 8, 5, 5, "delegate", 5),
        )
        for exact, host_max, slots, budget, expected_route, expected_count in cases:
            with self.subTest(exact=exact, host_max=host_max, slots=slots, budget=budget):
                inputs = deepcopy(base_inputs)
                inputs.update(
                    exact_specialists=exact,
                    detected_host_max=host_max,
                    available_slots=slots,
                    budget_capacity=budget,
                )
                behavioral = _compute_semantic_result("team-sizing.policy.v1", inputs)
                if exact > host_max:
                    with self.assertRaisesRegex(ValueError, f"effective host maximum {host_max}"):
                        load_effective_config(
                            ROOT,
                            task_override={"team_limits": {"exact_specialists": exact}},
                            detected_host_max=host_max,
                        )
                config = load_effective_config(
                    ROOT,
                    task_override={"team_limits": {"exact_specialists": exact}},
                    detected_host_max=max(host_max, exact),
                )
                task_two = score_delegation(
                    {
                        "id": f"exact-{exact}",
                        "benefits": {"parallel": 0, "independence": 0, "context": 0, "quality": 0},
                        "costs": {"setup": 3, "transfer": 3, "merge": 3, "review_rework": 3},
                        "observable_done_condition": True,
                        "fits_job_envelope": True,
                        "available_specialist_slots": slots if exact <= host_max else host_max,
                        "platform_available": True,
                        "authority_allows": True,
                        "evidence_ids": [f"host:max-{host_max}", f"slots:{slots}"],
                        "provenance": "observed",
                    },
                    config,
                )
                canonical_task_two_route = {
                    "ask-resolution": "resolution-question",
                }.get(task_two["route"], task_two["route"])
                self.assertEqual(behavioral, {"route": expected_route, "specialist_count": expected_count})
                self.assertEqual(canonical_task_two_route, expected_route)
                self.assertEqual(task_two["specialist_count"], expected_count)

    def test_team_sizing_exact_count_rejects_negative_and_boolean_values(self):
        index = next(
            i
            for i, record in enumerate(bundle()["runs"])
            if record["calculation"]["formula"] == "team-sizing.policy.v1"
        )
        for invalid in (-1, True):
            with self.subTest(invalid=invalid):
                altered = bundle()
                altered["runs"][index]["calculation"]["inputs"]["exact_specialists"] = invalid
                errors = " ".join(self.evaluator.validate_run_bundle(altered, self.manifest)).lower()
                self.assertIn("exact_specialists", errors)

    def test_missing_structured_question_calculation_rubric_and_evidence_fields_fail(self):
        fields = (
            "question_result",
            "recommendation",
            "output",
            "calculation",
            "assertions",
            "rubric_outcome",
            "raw_evidence_refs",
            "grader_evidence_refs",
        )
        for field in fields:
            with self.subTest(field=field):
                candidate = bundle()
                candidate["runs"][0].pop(field)
                self.assertIn(field.replace("_", " "), " ".join(self.evaluator.validate_run_bundle(candidate, self.manifest)).lower())

    def test_nested_calculation_rubric_measurement_and_claim_policy_fields_fail(self):
        for field in ("formula", "formula_version", "inputs", "results", "profile", "profile_margin", "provenance", "evidence_refs"):
            with self.subTest(calculation_field=field):
                candidate = bundle()
                candidate["runs"][0]["calculation"].pop(field)
                self.assertIn("calculation", " ".join(self.evaluator.validate_run_bundle(candidate, self.manifest)).lower())
        candidate = bundle()
        candidate["runs"][0]["rubric_outcome"].pop("quality")
        self.assertIn("rubric outcome", " ".join(self.evaluator.validate_run_bundle(candidate, self.manifest)).lower())
        candidate = bundle()
        candidate["runs"][0]["cost"]["evidence_refs"] = []
        self.assertIn("cost", " ".join(self.evaluator.validate_run_bundle(candidate, self.manifest)).lower())
        altered_manifest = manifest()
        altered_manifest["claim_policy"]["proxy_only_cannot_support_cost_claim"] = False
        self.assertIn("claim_policy", " ".join(self.evaluator.validate_run_bundle(bundle(), altered_manifest)).lower())

    def test_formula_inputs_results_and_route_are_recomputed_per_family(self):
        candidate = bundle()
        families = {}
        for index, item in enumerate(candidate["runs"]):
            formula_id = item["calculation_contract"].get("semantic_contract", {}).get("formula_id")
            if formula_id and formula_id not in families:
                families[formula_id] = index
        self.assertTrue(
            {
                "policy.state-route.v1",
                "premise.gate.v1",
                "delegation.gate.v1",
                "review.gate.v1",
                "utility.whole-job.v1",
                "budget.gate.v1",
                "allocation.reconciliation.v1",
                "continuity.policy.v1",
                "team-sizing.policy.v1",
            }
            <= set(families)
        )
        for formula_id, index in families.items():
            with self.subTest(formula=formula_id):
                altered = bundle()
                altered["runs"][index]["calculation"]["formula"] = "1+1=999"
                self.assertIn("formula", " ".join(self.evaluator.validate_run_bundle(altered, self.manifest)).lower())
                altered = bundle()
                schema = altered["runs"][index]["calculation_contract"]["semantic_contract"]["inputs"]
                input_name, input_contract = next(iter(schema.items()))
                altered["runs"][index]["calculation"]["inputs"][input_name] = {
                    "number": -999,
                    "integer": 1.5,
                    "nullable_integer": 1.5,
                    "nullable_number": "not-a-number",
                    "boolean": "not-a-boolean",
                    "string": "",
                }[input_contract["type"]]
                self.assertIn("input", " ".join(self.evaluator.validate_run_bundle(altered, self.manifest)).lower())
                altered = bundle()
                altered["runs"][index]["calculation"]["results"]["route"] = "contradiction"
                self.assertIn("route", " ".join(self.evaluator.validate_run_bundle(altered, self.manifest)).lower())

    def test_fixture_calculations_independently_match_approved_research(self):
        cases = {case["id"]: case for case in acceptance()["cases"]}
        named_weights = {
            "economy": {"quality": 0.35, "cost": 0.35, "latency": 0.10, "attention": 0.10, "rework": 0.10},
            "balanced": {"quality": 0.45, "cost": 0.20, "latency": 0.10, "attention": 0.10, "rework": 0.15},
            "quality": {"quality": 0.50, "cost": 0.10, "latency": 0.05, "attention": 0.10, "rework": 0.25},
        }
        committed = json.loads((ROOT / "config/orchestration.json").read_text(encoding="utf-8"))
        task_one = runpy.run_path(str(ROOT / "scripts/orchestration_config.py"))
        self.assertEqual(task_one["PROFILE_WEIGHTS"], named_weights)
        self.assertEqual(task_one["PROFILE_DELEGATION_MARGINS"], {"economy": 3, "balanced": 1, "quality": 1, "custom": 1})
        self.assertEqual(self.evaluator.PROFILE_WEIGHTS, named_weights)
        self.assertEqual(self.evaluator.REVIEW_MARGINS, {"economy": 6, "balanced": 3, "quality": 1})
        self.assertEqual(committed["objective_weights"], named_weights["balanced"])
        self.assertEqual(committed["team_limits"]["delegation_margin"], 1)
        self.assertEqual(committed["verification"]["review_margin"], 3)

        premise_routes = set()
        for case in cases.values():
            contract = case["calculation_assertions"]["semantic_contract"]
            inputs = contract["canonical_inputs"]
            expected = contract["expected"]
            formula = contract["formula_id"]
            schemas = contract["inputs"]
            if formula == "policy.state-route.v1":
                routes = {
                    "direct-fast-path": "direct",
                    "inline-only": "inline",
                    "incompatible-inline-and-exact": "resolution-question",
                    "ambiguous-material-team-count": "resolution-question",
                }
                self.assertEqual(expected["route"], routes[inputs["policy_state"]])
            elif formula == "premise.gate.v1":
                for name in ("wrongness_likelihood", "rework_cost", "user_attention_cost"):
                    self.assertIn(inputs[name], range(4), (case["id"], name))
                    self.assertEqual((schemas[name]["minimum"], schemas[name]["maximum"]), (0, 3))
                self.assertIn(inputs["expected_rework_avoided"], range(10), case["id"])
                self.assertEqual((schemas["expected_rework_avoided"]["minimum"], schemas["expected_rework_avoided"]["maximum"]), (0, 9))
                risk = inputs["wrongness_likelihood"] * inputs["rework_cost"]
                question_value = inputs["expected_rework_avoided"] - inputs["user_attention_cost"]
                self.assertLessEqual(inputs["expected_rework_avoided"], risk)
                self.assertEqual(expected["premise_risk"], risk)
                self.assertEqual(expected["question_value"], question_value)
                if inputs["settled_decision"] and not inputs["contradictory_evidence"]:
                    route = "resume"
                elif inputs["cheap_investigation"]:
                    route = "investigate"
                elif risk >= 4 and question_value > 0 and (inputs["changes_work_graph"] or inputs["irreversible"]) and not inputs["safe_reversible_default"]:
                    route = "ask"
                else:
                    route = "default"
                self.assertEqual(expected["route"], route)
                premise_routes.add(route)
            elif formula == "delegation.gate.v1":
                terms = [inputs[f"benefit_{name}"] for name in ("parallel", "independence", "context", "quality")]
                costs = [inputs[f"cost_{name}"] for name in ("setup", "transfer", "merge", "review_rework")]
                self.assertTrue(all(value in range(4) for value in terms + costs))
                for name in ("parallel", "independence", "context", "quality"):
                    self.assertEqual((schemas[f"benefit_{name}"]["minimum"], schemas[f"benefit_{name}"]["maximum"]), (0, 3))
                for name in ("setup", "transfer", "merge", "review_rework"):
                    self.assertEqual((schemas[f"cost_{name}"]["minimum"], schemas[f"cost_{name}"]["maximum"]), (0, 3))
                value = sum(terms) - sum(costs)
                self.assertEqual(expected["delegation_value"], value)
                approved = value > 0 and value >= inputs["margin"] and max(terms) >= 2
                approved = approved and all(inputs[name] for name in ("observable_done_condition", "fits_job_envelope", "platform_available", "authority_allows"))
                approved = approved and inputs["available_specialist_slots"] >= 1
                self.assertEqual(expected["route"], "delegate" if approved else "inline")
                self.assertEqual(expected["specialist_count"], 1 if approved else 0)
            elif formula == "utility.whole-job.v1":
                weights = {name: inputs[f"weight_{name}"] for name in named_weights[inputs["profile"]]}
                self.assertEqual(weights, named_weights[inputs["profile"]])
                factors = {name: inputs[name] for name in ("expected_quality", "total_job_cost", "critical_path_latency", "user_interruption_cost", "expected_rework_risk")}
                self.assertTrue(all(value in range(4) for value in factors.values()))
                for name in factors:
                    self.assertEqual((schemas[name]["minimum"], schemas[name]["maximum"]), (0, 3))
                utility = (
                    weights["quality"] * factors["expected_quality"]
                    - weights["cost"] * factors["total_job_cost"]
                    - weights["latency"] * factors["critical_path_latency"]
                    - weights["attention"] * factors["user_interruption_cost"]
                    - weights["rework"] * factors["expected_rework_risk"]
                )
                self.assertAlmostEqual(expected["utility"], utility)
            elif formula == "review.gate.v1":
                ratings = [inputs[name] for name in ("defect_likelihood", "impact", "detection_likelihood", "review_cost")]
                self.assertTrue(all(value in range(4) for value in ratings))
                for name in ("defect_likelihood", "impact", "detection_likelihood", "review_cost"):
                    self.assertEqual((schemas[name]["minimum"], schemas[name]["maximum"]), (0, 3))
                value = ratings[0] * ratings[1] * ratings[2] - ratings[3]
                self.assertEqual(expected["review_value"], value)
                self.assertEqual(inputs["threshold"], {"economy": 6, "balanced": 3, "quality": 1}[inputs["profile"]])
                mandatory = inputs["mandatory"] or inputs["consequential_weak_oracle"]
                if mandatory and not inputs["reviewer_available"]:
                    route = "blocked" if not inputs["accepted_compensating_oracle"] else "degraded"
                elif mandatory or (value >= inputs["threshold"] and inputs["reviewer_available"]):
                    route = "fresh"
                else:
                    route = "inline"
                self.assertEqual(expected["route"], route)
            elif formula == "continuity.policy.v1":
                if inputs["independence_required"] or inputs["responsibility_conflict"]:
                    route = "fresh"
                elif inputs["previous_attempt_failed"] and not inputs["new_evidence_or_hypothesis"]:
                    route = "blocked"
                elif inputs["native_handle_current"] and inputs["direct_continuation"] and inputs["costly_local_exploration_needed"] and inputs["registry_valid"] and inputs["capability_verified"]:
                    route = "resume"
                elif inputs["role_continuity_matters"] and inputs["capsule_sufficient"]:
                    route = "rehydrate"
                else:
                    route = "blocked"
                self.assertEqual(expected["route"], route)
                self.assertEqual(expected["specialist_count"], 1 if route in {"fresh", "rehydrate"} else 0)
            elif formula == "budget.gate.v1":
                self.assertEqual(inputs["available"] + inputs["reserved"] + inputs["funded_consumed"], inputs["ceiling"])
                self.assertEqual(inputs["total_consumed"], inputs["funded_consumed"] + inputs["unfunded_consumed"])
                enforcing = inputs["measurement"] == "observed" and inputs["observed_counter_verified"] and inputs["matching_stop_primitive_verified"]
                if inputs["mandatory_enforcement"] and (inputs["enforcement"] == "advisory" or not enforcing):
                    route = "blocked"
                elif inputs["available"] <= 0 or inputs["accepted_advisory_fallback"]:
                    route = "degraded"
                else:
                    route = "auto"
                self.assertEqual(expected["route"], route)
            elif formula == "allocation.reconciliation.v1":
                self.assertEqual(
                    inputs["initial_reserved"] + inputs["funded_reservation_overrun"],
                    inputs["active_reserved"] + inputs["funded_consumed"] + inputs["released_unused"],
                )
                route = "degraded" if inputs["terminal_status"] == "timeout" else ("auto" if inputs["reconciliation_succeeded"] else "blocked")
                self.assertEqual(expected["route"], route)
            elif formula == "team-sizing.policy.v1":
                if inputs["exact_specialists"] is not None:
                    expected_count = inputs["exact_specialists"] if inputs["exact_specialists"] <= min(inputs["detected_host_max"],inputs["available_slots"],inputs["budget_capacity"]) else 0
                else:
                    expected_count = min(inputs["independent_workstreams"], inputs["max_active_specialists"], inputs["detected_host_max"], inputs["available_slots"], inputs["budget_capacity"])
                self.assertEqual(expected["specialist_count"], expected_count)
                benefits = [inputs[f"benefit_{name}"] for name in ("parallel", "independence", "context", "quality")]
                costs = [inputs[f"cost_{name}"] for name in ("setup", "transfer", "merge", "review_rework")]
                self.assertTrue(all(value in range(4) for value in benefits + costs))
        self.assertTrue({"investigate", "default", "ask", "resume"} <= premise_routes)

    def test_runtime_calculation_inputs_are_pinned_to_canonical_case_facts(self):
        mutations = (
            ("accept-direct-fast-path", "policy_state", "changed-state"),
            ("accept-premise-default", "expected_rework_avoided", 99),
            ("accept-profile-balanced", "margin", 2),
            ("accept-invocation-auto", "threshold", 1),
            ("accept-continuity-resume", "threshold", 2),
            ("accept-review-mandatory-unavailable", "threshold", 0),
            ("accept-budget-advisory", "measurement", "observed"),
            ("accept-failure-reconciliation", "observed_usage", 9),
        )
        original = bundle()
        by_case = {}
        for index, record in enumerate(original["runs"]):
            by_case.setdefault(record["scenario_id"], index)
        self.assertEqual(original["runs"][by_case["accept-review-mandatory-unavailable"]]["calculation"]["inputs"]["threshold"], 1)
        self.assertNotIn("threshold", original["runs"][by_case["accept-invocation-auto"]]["calculation"]["inputs"])
        self.assertNotIn("threshold", original["runs"][by_case["accept-continuity-resume"]]["calculation"]["inputs"])
        for scenario_id, field, changed in mutations:
            with self.subTest(scenario=scenario_id, field=field):
                altered = bundle()
                altered["runs"][by_case[scenario_id]]["calculation"]["inputs"][field] = changed
                errors = " ".join(self.evaluator.validate_run_bundle(altered, self.manifest)).lower()
                self.assertIn("canonical per-case inputs", errors)

    def test_rubric_aggregation_and_top_level_flags_are_bound(self):
        candidate = bundle()
        for outcome in candidate["runs"][0]["rubric_outcome"].values():
            outcome["score"] = 0
            outcome["passed"] = False
        candidate["runs"][0]["quality"] = 4
        errors = " ".join(self.evaluator.validate_run_bundle(candidate, self.manifest)).lower()
        self.assertIn("aggregate", errors)
        self.assertIn("passed", errors)
        for field, dimension in (
            ("safety_authority_pass", "safety_authority"),
            ("budget_truthfulness_pass", "budget_truthfulness"),
            ("failure_visibility_pass", "failure_visibility"),
        ):
            with self.subTest(field=field):
                altered = bundle()
                altered["runs"][0]["rubric_outcome"][dimension]["passed"] = False
                self.assertIn(field.replace("_", " "), " ".join(self.evaluator.validate_run_bundle(altered, self.manifest)).lower())

    def test_structured_raw_and_grader_identities_bind_and_cannot_be_reused(self):
        candidate = bundle()
        self.assertIsInstance(candidate["runs"][0]["raw_evidence_refs"][0], dict)
        self.assertIsInstance(candidate["runs"][0]["grader_evidence_refs"][0], dict)
        candidate["runs"][1]["raw_evidence_refs"] = deepcopy(candidate["runs"][0]["raw_evidence_refs"])
        candidate["runs"][1]["grader_evidence_refs"] = deepcopy(candidate["runs"][0]["grader_evidence_refs"])
        errors = " ".join(self.evaluator.validate_run_bundle(candidate, self.manifest)).lower()
        self.assertIn("raw", errors)
        self.assertIn("grader", errors)
        baseline = bundle("A")
        candidate = bundle("D")
        candidate["runs"][0]["raw_evidence_refs"] = deepcopy(baseline["runs"][0]["raw_evidence_refs"])
        candidate["runs"][0]["grader_evidence_refs"] = deepcopy(baseline["runs"][0]["grader_evidence_refs"])
        result = self.evaluator.compare_arms(baseline, candidate, self.manifest)
        self.assertIn("raw evidence", " ".join(result["errors"]).lower())
        self.assertIn("grader evidence", " ".join(result["errors"]).lower())

    def test_question_bundle_and_actual_question_reference_are_bound(self):
        asked = next(i for i, item in enumerate(bundle()["runs"]) if item["expected_question_count"] == 1)
        candidate = bundle()
        self.assertIn("bundle", candidate["runs"][asked]["question_result"])
        self.assertIsInstance(candidate["runs"][asked]["question_result"]["actual_question"], dict)
        for field in ("bundle", "decision_id", "recommendation", "impact", "next_step"):
            with self.subTest(field=field):
                altered = bundle()
                altered["runs"][asked]["question_result"]["actual_question"].pop(field)
                self.assertIn(field.replace("_", " "), " ".join(self.evaluator.validate_run_bundle(altered, self.manifest)).lower())
                altered = bundle()
                altered["runs"][asked]["question_result"]["actual_question"][field] = "mismatch"
                self.assertIn(field.replace("_", " "), " ".join(self.evaluator.validate_run_bundle(altered, self.manifest)).lower())
        altered = bundle()
        altered["runs"][asked]["question_result"]["actual_question"]["evidence_ref"] = "question:wrong-arm:wrong-case:999"
        self.assertIn("actual question reference", " ".join(self.evaluator.validate_run_bundle(altered, self.manifest)).lower())

    def test_each_material_question_field_and_suppression_evidence_are_required(self):
        asked_index = next(i for i, item in enumerate(bundle()["runs"]) if item["expected_question_count"] == 1)
        for field in ("decision_id", "bundle", "recommendation", "impact", "next_step"):
            with self.subTest(field=field):
                candidate = bundle()
                candidate["runs"][asked_index]["question_result"].pop(field)
                self.assertIn(field.replace("_", " "), " ".join(self.evaluator.validate_run_bundle(candidate, self.manifest)).lower())
        suppressed_index = next(i for i, item in enumerate(bundle()["runs"]) if item["scenario_id"] == "accept-question-settled-suppression")
        candidate = bundle()
        candidate["runs"][suppressed_index]["question_result"]["suppression"]["evidence_refs"] = []
        self.assertIn("suppression", " ".join(self.evaluator.validate_run_bundle(candidate, self.manifest)).lower())

    def test_omitted_or_provisional_identity_and_wrong_surface_never_validate_as_verified(self):
        for mutation, label in (
            (lambda b: b.pop("identity_verification"), "identity"),
            (lambda b: b["identity_verification"].__setitem__("artifact", "verified"), "artifact"),
            (lambda b: b["surface_evidence"].__setitem__("surface_id", "invented-surface"), "surface"),
        ):
            with self.subTest(label=label):
                candidate = bundle()
                mutation(candidate)
                self.assertIn(label, " ".join(self.evaluator.validate_run_bundle(candidate, self.manifest)).lower())
        result = self.evaluator.compare_arms(bundle("A"), bundle("D"), self.manifest)
        self.assertEqual(result["status"], "unverified")

    def test_estimated_measurements_never_support_cost_latency_or_critical_path_claims(self):
        candidate = bundle()
        for item in candidate["runs"]:
            for metric in ("cost", "latency", "critical_path"):
                item[metric]["provenance"] = "estimated"
        summary = self.evaluator.summarize_arm(candidate["runs"])
        self.assertIsNone(summary["median_cost"])
        self.assertIsNone(summary["median_latency"])
        self.assertEqual(summary["cost_claim"], "estimated-nonclaiming")

    def test_missing_bound_high_value_group_cannot_pass_as_not_applicable(self):
        baseline = bundle("A")
        candidate = bundle("D")
        for item in candidate["runs"]:
            item["evaluation_groups"] = []
        result = self.evaluator.compare_arms(baseline, candidate, self.manifest)
        self.assertNotEqual(result["status"], "pass")
        self.assertIn(result["high_value_delegation"]["status"], {"fail", "inconclusive"})

    def test_malformed_replicate_and_non_object_run_fail_controlled(self):
        malformed = bundle()
        malformed["runs"][0]["replicate_id"] = {}
        malformed["runs"][1] = []
        errors = self.evaluator.validate_run_bundle(malformed, self.manifest)
        self.assertTrue(errors)
        result = self.evaluator.compare_arms(bundle("A"), malformed, self.manifest)
        self.assertEqual(result["status"], "fail")

    def test_profile_margins_and_spawn_counts_are_derived_not_labels(self):
        expected = {"economy": 3, "balanced": 1, "quality": 1}
        candidate = bundle()
        for item in candidate["runs"]:
            profile = item["calculation"]["profile"]
            if profile in expected:
                self.assertEqual(item["calculation"]["profile_margin"], expected[profile])
            self.assertEqual(item["calculation"]["results"]["specialist_count"], item["expected_spawn_count"])
            self.assertEqual(
                item["calculation_contract"]["semantic_contract"]["expected"]["specialist_count"],
                item["expected_spawn_count"],
            )

    def test_weak_isolation_or_wrong_counterbalanced_order_is_rejected(self):
        mutations = {
            "task fingerprint": lambda b: b["isolation"].__setitem__("task_fingerprint", "task-D"),
            "cache fingerprint": lambda b: b["isolation"].__setitem__("cache_fingerprint", "cache-D"),
            "environment evidence": lambda b: b["isolation"].__setitem__("environment_evidence_id", ""),
            "arm order": lambda b: b.__setitem__("recorded_arm_order", ["D", "C", "B", "A"]),
            "run order": lambda b: b["execution_order"].reverse(),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = bundle()
                mutate(candidate)
                self.assertIn(label.split()[0], " ".join(self.evaluator.validate_run_bundle(candidate, self.manifest)).lower())


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
        baseline = bundle("A")
        candidate = mutate_runs(
            bundle("D"),
            lambda item: "high-value-delegation" in item["evaluation_groups"],
            lambda item: (set_run_quality(item, 3.2), item["critical_path"].__setitem__("value", 9.0)),
        )
        result = self.evaluator.compare_arms(baseline, candidate, self.manifest)
        self.assertEqual(result["status"], "unverified")
        self.assertGreater(result["quality_difference"], 0)
        self.assertEqual(result["confidence_interval"]["level"], 0.95)
        self.assertEqual(result["high_value_delegation"]["status"], "pass")

    def test_quality_regression_beyond_point_ten_fails(self):
        baseline = bundle("A")
        candidate = mutate_runs(bundle("D"), lambda item: True, lambda item: set_run_quality(item, 2.89))
        result = self.evaluator.compare_arms(baseline, candidate, self.manifest)
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["quality_noninferiority"]["status"], "fail")

    def test_simple_task_cost_or_latency_increase_above_five_percent_fails(self):
        for metric in ("cost", "latency"):
            with self.subTest(metric=metric):
                baseline = bundle("A")
                candidate = mutate_runs(
                    bundle("D"), lambda item: item["category"] == "direct",
                    lambda item: item[metric].__setitem__("value", 10.51),
                )
                result = self.evaluator.compare_arms(baseline, candidate, self.manifest)
                self.assertEqual(result["status"], "unverified")
                self.assertEqual(result["simple_tasks"][metric]["status"], "fail")

    def test_high_value_gain_requires_point_two_quality_or_ten_percent_critical_path(self):
        is_high_value = lambda item: "high-value-delegation" in item["evaluation_groups"]
        baseline = bundle("A")
        weak = mutate_runs(bundle("D"), is_high_value, lambda item: (set_run_quality(item, 3.19), item["critical_path"].__setitem__("value", 9.01)))
        strong_quality = mutate_runs(bundle("D"), is_high_value, lambda item: set_run_quality(item, 3.2))
        strong_time = mutate_runs(bundle("D"), is_high_value, lambda item: item["critical_path"].__setitem__("value", 9.0))
        weak_result = self.evaluator.compare_arms(baseline, weak, self.manifest)
        self.assertEqual(weak_result["high_value_delegation"]["status"], "fail")
        self.assertEqual(self.evaluator.compare_arms(baseline, strong_quality, self.manifest)["high_value_delegation"]["status"], "pass")
        self.assertEqual(self.evaluator.compare_arms(baseline, strong_time, self.manifest)["high_value_delegation"]["status"], "pass")

    def test_noisy_high_value_gain_is_inconclusive_without_supporting_interval(self):
        baseline = bundle("A")
        candidate = bundle("D")
        selected = [
            pair
            for pair in zip(baseline["runs"], candidate["runs"])
            if "high-value-delegation" in pair[0]["evaluation_groups"]
        ]
        self.assertEqual(len(selected), 5)
        for (base_item, candidate_item), delta in zip(selected, [-1, -1, -1, 1, 3]):
            set_run_quality(base_item, 1)
            set_run_quality(candidate_item, 1 + delta)

        result = self.evaluator.compare_arms(baseline, candidate, self.manifest)

        self.assertEqual(result["high_value_delegation"]["quality_gain"], 0.2)
        self.assertEqual(result["high_value_delegation"]["status"], "inconclusive")
        self.assertLess(result["high_value_delegation"]["quality_confidence_interval"]["lower"], 0.2)

    def test_noisy_simple_metric_regression_is_inconclusive(self):
        baseline = bundle("A")
        candidate = bundle("D")
        selected = [
            pair
            for pair in zip(baseline["runs"], candidate["runs"])
            if pair[0]["category"] in {"direct", "simple", "direct-fast-path", "no-delegation-trap"}
        ]
        self.assertGreaterEqual(len(selected), 5)
        for index, (base_item, candidate_item) in enumerate(selected):
            base_item["cost"] = {"value": 10.0, "provenance": "observed", "evidence_refs": base_item["evidence_refs"][:1]}
            candidate_item["cost"] = {
                "value": 11.0 if index % 5 in {3, 4} else 10.0,
                "provenance": "observed",
                "evidence_refs": candidate_item["evidence_refs"][:1],
            }

        result = self.evaluator.compare_arms(baseline, candidate, self.manifest)

        self.assertEqual(result["simple_tasks"]["cost"]["status"], "inconclusive")
        self.assertGreater(result["simple_tasks"]["cost"]["confidence_interval"]["upper"], 0.05)

    def test_unsafe_failure_and_spawn_or_question_regression_fail_closed(self):
        cases = {
            "unsafe": lambda item: (item.__setitem__("unsafe_failures", ["budget lie"]), item.__setitem__("safety_authority_pass", False)),
            "spawn": lambda item: item.__setitem__("unnecessary_spawn", True),
            "premise": lambda item: item.__setitem__("premise_reset", True),
            "question": lambda item: item.__setitem__("repeated_settled_question", True),
        }
        for label, mutation in cases.items():
            with self.subTest(label=label):
                candidate = bundle("D")
                mutation(candidate["runs"][0])
                result = self.evaluator.compare_arms(bundle("A"), candidate, self.manifest)
                self.assertNotEqual(result["status"], "pass")

    def test_comparison_rejects_changed_case_contract_or_reused_raw_result_id(self):
        base = bundle("A", version="1.1.0")
        changed = bundle("D")
        changed["runs"][0]["category"] = "high-value-delegation"
        result = self.evaluator.compare_arms(base, changed, self.manifest)
        self.assertEqual(result["status"], "fail")
        self.assertIn("case contract", " ".join(result["errors"]).lower())

        reused = bundle("D")
        reused["runs"][0]["run_id"] = base["runs"][0]["run_id"]
        refresh_execution_order(reused)
        result = self.evaluator.compare_arms(base, reused, self.manifest)
        self.assertEqual(result["status"], "fail")
        self.assertIn("raw result", " ".join(result["errors"]).lower())

    def test_uncertain_interval_is_inconclusive_not_improvement(self):
        baseline = bundle("A")
        candidate = bundle("D")
        base_values = [1, 4, 1, 4, 2]
        candidate_values = [4, 1, 4, 1, 3]
        for index, (base_item, candidate_item) in enumerate(zip(baseline["runs"], candidate["runs"])):
            set_run_quality(base_item, base_values[index % 5])
            set_run_quality(candidate_item, candidate_values[index % 5])
        result = self.evaluator.compare_arms(baseline, candidate, self.manifest)
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["quality_noninferiority"]["status"], "inconclusive")
        self.assertNotEqual(result["quality_noninferiority"]["status"], "improvement")

    def test_unavailable_cost_uses_labelled_nonincreasing_proxies_without_cost_claim(self):
        baseline = bundle("A")
        candidate = bundle("D")
        for value in (baseline, candidate):
            for item in value["runs"]:
                for metric in ("cost", "latency", "critical_path"):
                    item[metric] = {"value": None, "provenance": "unavailable", "evidence_refs": item["evidence_refs"][:1]}
        result = self.evaluator.compare_arms(baseline, candidate, self.manifest)
        self.assertEqual(result["simple_tasks"]["cost"]["status"], "proxy-only")
        self.assertFalse(result["simple_tasks"]["cost"]["claim_allowed"])
        self.assertEqual(result["status"], "unverified")


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

    def test_cli_reports_structurally_valid_provisional_bundles_as_unverified(self):
        require_evaluator(self)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            manifest_path = temp / "manifest.json"
            baseline_path = temp / "baseline.json"
            candidate_path = temp / "candidate.json"
            manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")
            baseline_path.write_text(json.dumps(bundle("A")), encoding="utf-8")
            candidate_path.write_text(json.dumps(bundle("D")), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--manifest", str(manifest_path), "--baseline", str(baseline_path), "--candidate", str(candidate_path)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("BEHAVIORAL EVALUATION UNVERIFIED", result.stdout)
        self.assertNotIn("BEHAVIORAL EVALUATION PASSED", result.stdout)


if __name__ == "__main__":
    unittest.main()
