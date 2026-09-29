import importlib
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

class ModuleOwnershipTests(unittest.TestCase):
    def test_state_owners_export_same_public_callables(self):
        facade=importlib.import_module("scripts.orchestration_state")
        for owner,name in (("ledger","apply_ledger_event"),("state_validation","validate_orchestration_state"),("recovery","recover_state"),("recovery","prepare_dispatch")):
            with self.subTest(name=name):
                owned=importlib.import_module("scripts.optimal_challenge."+owner)
                self.assertIs(getattr(facade,name),getattr(owned,name))

    def test_capability_proof_classes_have_one_identity(self):
        facade=importlib.import_module("scripts.capability_matrix")
        owned=importlib.import_module("scripts.optimal_challenge.capability_evidence")
        for name in ("NativeResumeProof","PauseCancelProof","UsageCounterProof","EnforcementProof","PersistencePrivacyProof","ParallelExecutionProof","TracingProof","TrustedCapabilityEvidence"):
            self.assertIs(getattr(facade,name),getattr(owned,name))

    def test_evaluator_owners_keep_public_identity(self):
        facade=importlib.import_module("scripts.evaluate_behavior")
        for owner,name in (("evaluation_contracts","validate_run_bundle"),("evaluation_statistics","summarize_arm"),("evaluation_comparison","compare_arms")):
            owned=importlib.import_module("scripts.optimal_challenge."+owner)
            self.assertIs(getattr(facade,name),getattr(owned,name))
        self.assertTrue(callable(importlib.import_module("scripts.optimal_challenge.evaluation_semantics")._compute_semantic_result))

    def test_facade_cli_keeps_unverified_exit_status(self):
        process=subprocess.run([sys.executable,str(ROOT/"scripts/evaluate_behavior.py"),"--manifest",str(ROOT/"tests/evaluation-manifest.json"),"--baseline",str(ROOT/"tests/baselines/v1.1.json"),"--candidate",str(ROOT/"tests/baselines/v1.1.json")],capture_output=True,text=True,cwd=ROOT)
        self.assertEqual(process.returncode,2,process.stdout+process.stderr)
