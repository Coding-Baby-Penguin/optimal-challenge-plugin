from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.orchestration_state import apply_ledger_event, recover_state, validate_orchestration_state


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "orchestration"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def event(event_type: str, number: int, **values: object) -> dict:
    return {"event_id": f"event-{number}", "type": event_type, "transaction_id": f"tx-{number}", **values}


def state_hash(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


class SchemaTests(unittest.TestCase):
    def test_closed_schemas_accept_fixtures_and_reject_unknown_fields(self) -> None:
        for schema_name, fixture_name in [
            ("team-registry.schema.json", "valid-registry.json"),
            ("allocation-ledger.schema.json", "valid-ledger.json"),
        ]:
            schema = json.loads((ROOT / "config" / schema_name).read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema)
            fixture = load_fixture(fixture_name)
            self.assertEqual([], list(validator.iter_errors(fixture)))
            fixture["unexpected"] = True
            self.assertTrue(list(validator.iter_errors(fixture)))

    def test_cross_record_ids_evidence_versions_and_capability_are_checked(self) -> None:
        registry, ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        self.assertEqual([], validate_orchestration_state(registry, ledger))
        registry["teammates"]["worker-1"]["logical_teammate_id"] = "conflict"
        registry["teammates"]["worker-1"]["trust"]["evidence_refs"] = ["missing-review"]
        registry["assignments"]["assignment-1"]["capability_class"] = "frontier"
        ledger["snapshot_version"] = 2
        errors = "\n".join(validate_orchestration_state(registry, ledger))
        self.assertIn("logical_teammate_id", errors)
        self.assertIn("missing-review", errors)
        self.assertIn("capability_class", errors)
        self.assertIn("snapshot_version", errors)

    def test_duplicate_assignment_reservations_and_non_monotonic_history_are_rejected(self) -> None:
        registry, ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        duplicate = copy.deepcopy(ledger["reservations"]["reservation-1"])
        duplicate["reservation_id"] = "reservation-2"
        duplicate["active_reserved"] = 0
        duplicate["initial_reserved"] = 0
        ledger["reservations"]["reservation-2"] = duplicate
        ledger["history"] = [
            {"event_id": "e2", "type": "start", "transaction_id": "t2", "transaction_version": 2, "event_hash": "0" * 64},
            {"event_id": "e1", "type": "start", "transaction_id": "t1", "transaction_version": 1, "event_hash": "1" * 64},
        ]
        errors = "\n".join(validate_orchestration_state(registry, ledger))
        self.assertIn("more than one reservation", errors)
        self.assertIn("strictly increasing", errors)
    def test_bidirectional_registry_ledger_links_states_membership_and_evidence_are_checked(self) -> None:
        registry, ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        registry["evidence"]["wrong-key"] = {"evidence_id": "different-id", "kind": "source", "outcome": "verified"}
        registry["teammates"]["worker-1"]["active_assignment_ids"] = ["assignment-1"]
        registry["assignments"]["assignment-1"]["state"] = "complete"
        ledger["reservations"]["reservation-1"]["logical_teammate_id"] = "other-worker"
        orphan = copy.deepcopy(ledger["reservations"]["reservation-1"])
        orphan.update({"reservation_id": "orphan", "assignment_id": "orphan-assignment", "active_reserved": 0, "initial_reserved": 0, "evidence_refs": ["missing-evidence"]})
        ledger["reservations"]["orphan"] = orphan
        errors = "\n".join(validate_orchestration_state(registry, ledger))
        self.assertIn("evidence_id", errors)
        self.assertIn("active_assignment_ids", errors)
        self.assertIn("state", errors)
        self.assertIn("logical_teammate_id", errors)
        self.assertIn("orphan-assignment", errors)
        self.assertIn("missing-evidence", errors)

    def test_retry_lineage_is_enforced_by_schema_and_validator(self) -> None:
        registry, ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        reservation = ledger["reservations"]["reservation-1"]
        reservation.update({"kind": "retry", "attempt": 2, "retry_of_reservation_id": None})
        schema = json.loads((ROOT / "config" / "allocation-ledger.schema.json").read_text(encoding="utf-8"))
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(ledger)))
        self.assertIn("retry_of_reservation_id", "\n".join(validate_orchestration_state(registry, ledger)))
    def test_active_assignment_owner_and_terminal_evidence_are_bidirectional(self) -> None:
        registry, ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        second = copy.deepcopy(registry["teammates"]["worker-1"])
        second["logical_teammate_id"] = "worker-2"
        second["active_assignment_ids"] = ["assignment-1"]
        registry["teammates"]["worker-2"] = second
        registry["teammates"]["worker-1"]["active_assignment_ids"] = []
        errors = "\n".join(validate_orchestration_state(registry, ledger))
        self.assertIn("assigned teammate", errors)

        registry, ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        registry["teammates"]["worker-1"]["active_assignment_ids"] = []
        registry["assignments"]["assignment-1"]["state"] = "complete"
        reservation = ledger["reservations"]["reservation-1"]
        reservation.update({"state": "complete", "active_reserved": 0, "funded_consumed": 40, "terminal_evidence": "missing-terminal"})
        ledger.update({"reserved": 0, "funded_consumed": 40, "total_consumed": 40})
        self.assertIn("missing-terminal", "\n".join(validate_orchestration_state(registry, ledger)))
    def test_reconciliation_and_reset_histories_must_match_version_and_order(self) -> None:
        registry, ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        ledger["reconciliation_version"] = 2
        ledger["reconciliation_history"] = [
            {"event_id": "r2", "type": "late_report", "transaction_id": "t2", "transaction_version": 3, "reconciliation_version": 2, "event_hash": "0" * 64},
            {"event_id": "r1", "type": "late_report", "transaction_id": "t1", "transaction_version": 2, "reconciliation_version": 1, "event_hash": "1" * 64},
        ]
        errors = "\n".join(validate_orchestration_state(registry, ledger))
        self.assertIn("reconciliation versions must be nondecreasing", errors)
        ledger["reconciliation_history"] = []
        self.assertIn("history count", "\n".join(validate_orchestration_state(registry, ledger)))
        ledger["reset_history"] = [{"reconciliation_version": 2}, {"reconciliation_version": 1}]
        self.assertIn("reset_history: reconciliation versions must be nondecreasing", "\n".join(validate_orchestration_state(registry, ledger)))

    def test_schemas_reject_whitespace_only_ids_and_property_names(self) -> None:
        registry_schema = json.loads((ROOT / "config" / "team-registry.schema.json").read_text(encoding="utf-8"))
        ledger_schema = json.loads((ROOT / "config" / "allocation-ledger.schema.json").read_text(encoding="utf-8"))
        registry = load_fixture("valid-registry.json")
        registry["transaction_id"] = "   "
        registry["evidence"]["   "] = {"evidence_id": "   ", "kind": "source", "outcome": "verified"}
        ledger = load_fixture("valid-ledger.json")
        ledger["reservations"]["reservation-1"]["assignment_id"] = "   "
        ledger["reservations"]["   "] = ledger["reservations"].pop("reservation-1")
        self.assertTrue(list(Draft202012Validator(registry_schema).iter_errors(registry)))
        self.assertTrue(list(Draft202012Validator(ledger_schema).iter_errors(ledger)))
    def test_normal_transaction_history_versions_must_be_strictly_increasing(self) -> None:
        registry, ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        ledger["history"] = [
            {"event_id": "one", "type": "start", "transaction_id": "tx-a", "transaction_version": 1, "event_hash": "1" * 64},
            {"event_id": "two", "type": "complete", "transaction_id": "tx-b", "transaction_version": 1, "event_hash": "2" * 64},
        ]
        ledger["applied_event_ids"] = ["one", "two"]
        self.assertIn("history: transaction versions must be strictly increasing", "\n".join(validate_orchestration_state(registry, ledger)))
    def test_balance_and_registry_reservation_invariants_are_checked(self) -> None:
        registry, ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        ledger["available"] = 61
        ledger["reservations"]["reservation-1"]["assignment_id"] = "wrong"
        errors = "\n".join(validate_orchestration_state(registry, ledger))
        self.assertIn("whole-ledger conservation", errors)
        self.assertIn("assignment-1", errors)


class LedgerMutationTests(unittest.TestCase):
    def empty_ledger(self, *, measurement: str = "observed", enforcement: str = "advisory") -> dict:
        ledger = load_fixture("valid-ledger.json")
        ledger.update({"available": 100, "reserved": 0, "measurement": measurement, "enforcement": enforcement})
        ledger["reservations"] = {}
        return ledger

    def test_start_is_immutable_atomic_and_idempotent(self) -> None:
        before = self.empty_ledger()
        started = apply_ledger_event(before, event("start", 2, reservation_id="r2", assignment_id="a2", logical_teammate_id="w2", kind="worker", amount=30, evidence_refs=["launch-2"]))
        self.assertEqual(100, before["available"])
        self.assertEqual((70, 30, 2), (started["available"], started["reserved"], started["transaction_version"]))
        self.assertEqual(started, apply_ledger_event(started, event("start", 2, reservation_id="r2", assignment_id="a2", logical_teammate_id="w2", kind="worker", amount=30, evidence_refs=["launch-2"])))
        with self.assertRaisesRegex(ValueError, "available"):
            apply_ledger_event(started, event("start", 3, reservation_id="r3", assignment_id="a3", amount=80))

    def test_conflicting_reuse_of_event_id_is_rejected(self) -> None:
        ledger = apply_ledger_event(self.empty_ledger(), event("start", 2, reservation_id="r2", assignment_id="a2", amount=30))
        with self.assertRaisesRegex(ValueError, "event_id"):
            apply_ledger_event(ledger, event("start", 2, reservation_id="different", assignment_id="different", amount=10))
    def test_observed_complete_release_and_funded_overrun(self) -> None:
        ledger = apply_ledger_event(self.empty_ledger(), event("start", 2, reservation_id="r2", assignment_id="a2", amount=30))
        complete = apply_ledger_event(ledger, event("complete", 3, reservation_id="r2", amount=40, measurement="observed", terminal_evidence="return-2"))
        self.assertEqual((60, 0, 40, 10, 0), (complete["available"], complete["reserved"], complete["funded_consumed"], complete["funded_reservation_overrun"], complete["unfunded_consumed"]))
        self.assertEqual("complete", complete["reservations"]["r2"]["state"])

    def test_whole_job_overrun_is_only_unfunded_and_degraded(self) -> None:
        ledger = apply_ledger_event(self.empty_ledger(), event("start", 2, reservation_id="r2", assignment_id="a2", amount=90))
        complete = apply_ledger_event(ledger, event("complete", 3, reservation_id="r2", amount=120, measurement="observed", terminal_evidence="return-2"))
        self.assertEqual((100, 10, 20, 120), (complete["funded_consumed"], complete["funded_reservation_overrun"], complete["unfunded_consumed"], complete["total_consumed"]))
        self.assertEqual("degraded", complete["status"])

    def test_concurrent_reservations_cannot_spend_each_others_funded_capacity(self) -> None:
        ledger = apply_ledger_event(self.empty_ledger(), event("start", 2, reservation_id="r1", assignment_id="a1", amount=60))
        ledger = apply_ledger_event(ledger, event("start", 3, reservation_id="r2", assignment_id="a2", amount=40))
        ledger = apply_ledger_event(ledger, event("complete", 4, reservation_id="r1", amount=80, terminal_evidence="return-1"))
        self.assertEqual((0, 40, 60, 20), (ledger["available"], ledger["reserved"], ledger["funded_consumed"], ledger["unfunded_consumed"]))
        self.assertEqual("running", ledger["reservations"]["r2"]["state"])
    def test_cancel_fail_timeout_and_immutable_terminal_transitions(self) -> None:
        cancel = apply_ledger_event(apply_ledger_event(self.empty_ledger(), event("start", 2, reservation_id="r2", assignment_id="a2", amount=20)), event("cancel", 3, reservation_id="r2", amount=5, confirmed_remainder=15, terminal_evidence="cancel-2"))
        self.assertEqual(("cancelled", 5, 15), (cancel["reservations"]["r2"]["state"], cancel["funded_consumed"], cancel["released"]))
        failed = apply_ledger_event(apply_ledger_event(self.empty_ledger(measurement="estimated"), event("start", 4, reservation_id="r4", assignment_id="a4", amount=20)), event("failed", 5, reservation_id="r4", amount=7, confirmed_remainder=13, terminal_evidence="failure-4"))
        self.assertEqual("failed", failed["reservations"]["r4"]["state"])
        timed = apply_ledger_event(apply_ledger_event(self.empty_ledger(measurement="unavailable"), event("start", 6, reservation_id="r6", assignment_id="a6", amount=20)), event("timeout", 7, reservation_id="r6"))
        self.assertEqual(("unknown", 20), (timed["reservations"]["r6"]["state"], timed["reserved"]))
        with self.assertRaisesRegex(ValueError, "terminal"):
            apply_ledger_event(cancel, event("complete", 8, reservation_id="r2", amount=5, terminal_evidence="late-wrong-event"))

    def test_retry_uses_new_reservation_and_unavailable_complete_is_conservative(self) -> None:
        ledger = apply_ledger_event(self.empty_ledger(measurement="unavailable"), event("start", 2, reservation_id="first", assignment_id="a", amount=20))
        ledger = apply_ledger_event(ledger, event("failed", 3, reservation_id="first", confirms_no_further_use=True, amount=0, confirmed_remainder=20, terminal_evidence="failed"))
        ledger = apply_ledger_event(ledger, event("retry_start", 4, reservation_id="retry", assignment_id="a-retry-2", retry_of_reservation_id="first", amount=10, attempt=2))
        ledger = apply_ledger_event(ledger, event("retry_complete", 5, reservation_id="retry", terminal_evidence="retry-return"))
        self.assertEqual(("failed", "complete", 10), (ledger["reservations"]["first"]["state"], ledger["reservations"]["retry"]["state"], ledger["funded_consumed"]))

    def test_retry_requires_unique_attempt_assignment_and_lineage(self) -> None:
        ledger = apply_ledger_event(self.empty_ledger(), event("start", 2, reservation_id="first", assignment_id="a", amount=20))
        ledger = apply_ledger_event(ledger, event("failed", 3, reservation_id="first", amount=0, confirmed_remainder=20, terminal_evidence="failed"))
        with self.assertRaisesRegex(ValueError, "unique attempt assignment"):
            apply_ledger_event(ledger, event("retry_start", 4, reservation_id="retry", assignment_id="a", retry_of_reservation_id="first", amount=10, attempt=2))
        with self.assertRaisesRegex(ValueError, "retry_of_reservation_id"):
            apply_ledger_event(ledger, event("retry_start", 5, reservation_id="retry", assignment_id="a-retry-2", amount=10, attempt=2))

    def test_unavailable_cancel_and_timeout_retain_unknown_reservation(self) -> None:
        for event_type in ("cancel", "timeout"):
            with self.subTest(event_type=event_type):
                ledger = apply_ledger_event(self.empty_ledger(measurement="unavailable"), event("start", 2, reservation_id="r", assignment_id="a", amount=20))
                result = apply_ledger_event(ledger, event(event_type, 3, reservation_id="r", amount=0, confirmed_remainder=20, terminal_evidence="host-signal"))
                self.assertEqual(("unknown", 20, 0), (result["reservations"]["r"]["state"], result["reserved"], result["released"]))
    def test_late_observed_report_replaces_estimate_and_reconciles(self) -> None:
        ledger = apply_ledger_event(self.empty_ledger(measurement="estimated"), event("start", 2, reservation_id="r2", assignment_id="a2", amount=30))
        ledger = apply_ledger_event(ledger, event("complete", 3, reservation_id="r2", amount=20, measurement="estimated", terminal_evidence="estimate"))
        reconciled = apply_ledger_event(ledger, event("late_report", 4, reservation_id="r2", amount=35, measurement="observed", terminal_evidence="counter"))
        self.assertEqual((65, 35, 5, 1), (reconciled["available"], reconciled["funded_consumed"], reconciled["funded_reservation_overrun"], reconciled["reconciliation_version"]))
        self.assertEqual("observed", reconciled["reservations"]["r2"]["measurement"])

    def test_reconciliation_failure_preserves_balances_and_versions(self) -> None:
        ledger = self.empty_ledger()
        failed = apply_ledger_event(ledger, event("reconciliation_failure", 2, reason="counter unavailable"))
        for key in ("available", "reserved", "funded_consumed", "unfunded_consumed", "transaction_version", "reconciliation_version"):
            self.assertEqual(ledger[key], failed[key])
        self.assertTrue(failed["recovery_required"])
        self.assertEqual("degraded", failed["status"])
        self.assertEqual(["event-2"], failed["applied_event_ids"])
        self.assertEqual(failed, apply_ledger_event(failed, event("reconciliation_failure", 2, reason="counter unavailable")))
        with self.assertRaisesRegex(ValueError, "conflicting replay"):
            apply_ledger_event(failed, event("reconciliation_failure", 2, reason="different failure"))

    def test_advisory_reset_preserves_prior_values_and_marks_accuracy_degraded(self) -> None:
        ledger = apply_ledger_event(self.empty_ledger(measurement="estimated"), event("start", 2, reservation_id="r2", assignment_id="a2", amount=20))
        reset = apply_ledger_event(ledger, event("reset", 3, reservation_id="r2", reason="user accepted stale reservation release", authority="user", evidence_ref="decision-1"))
        self.assertEqual((100, 0, "degraded", 1), (reset["available"], reset["reserved"], reset["status"], reset["reconciliation_version"]))
        self.assertEqual(20, reset["reset_history"][0]["prior"]["active_reserved"])
        self.assertEqual("advisory_reset", reset["accuracy_marker"])

    def test_unknown_balances_block_new_reservations(self) -> None:
        ledger = self.empty_ledger(measurement="unavailable")
        ledger.update({"balances_known": False, "available": None, "reserved": None, "funded_consumed": None, "funded_reservation_overrun": None, "unfunded_consumed": None, "total_consumed": None, "released": None, "status": "blocked"})
        with self.assertRaisesRegex(ValueError, "unknown"):
            apply_ledger_event(ledger, event("start", 2, reservation_id="r2", assignment_id="a2", amount=10))


    def test_retry_rejects_branching_and_multiple_active_lineage_members(self) -> None:
        ledger = apply_ledger_event(self.empty_ledger(), event("start", 20, reservation_id="first", assignment_id="a1", amount=20))
        ledger = apply_ledger_event(ledger, event("failed", 21, reservation_id="first", amount=0, confirmed_remainder=20, terminal_evidence="failed"))
        ledger = apply_ledger_event(ledger, event("retry_start", 22, reservation_id="second", assignment_id="a2", retry_of_reservation_id="first", amount=10, attempt=2))
        before = copy.deepcopy(ledger)
        with self.assertRaisesRegex(ValueError, "successor"):
            apply_ledger_event(ledger, event("retry_start", 23, reservation_id="branch", assignment_id="a3", retry_of_reservation_id="first", amount=5, attempt=2))
        self.assertEqual(before, ledger)
        registry = load_fixture("valid-registry.json")
        registry["assignments"] = {}
        registry["teammates"]["worker-1"]["active_assignment_ids"] = []
        corrupted = copy.deepcopy(ledger)
        corrupted["reservations"]["first"]["state"] = "unknown"
        self.assertIn("retry lineage", "\n".join(validate_orchestration_state(registry, corrupted)))

    def test_event_validation_is_strict_and_failures_do_not_mutate(self) -> None:
        invalid_events = [
            event("bogus", 30),
            event("start", 31, reservation_id="r", assignment_id="a", amount=1, attempt=True),
            event("start", 32, reservation_id="r", assignment_id="a", amount=1, attempt=0),
            event("start", 33, reservation_id="   ", assignment_id="a", amount=1),
            event("start", 34, reservation_id="r", assignment_id="a", amount=1, kind="bogus"),
            event("start", 35, reservation_id="r", assignment_id="a", amount=1, evidence_refs="not-a-list"),
            event("start", 36, reservation_id="r", assignment_id="a", amount=1, evidence_refs=["ok", " "]),
            {**event("start", 37, reservation_id="r", assignment_id="a", amount=1), "unexpected": True},
        ]
        for invalid in invalid_events:
            with self.subTest(invalid=invalid):
                ledger = self.empty_ledger()
                before = copy.deepcopy(ledger)
                with self.assertRaises((TypeError, ValueError)):
                    apply_ledger_event(ledger, invalid)
                self.assertEqual(before, ledger)

    def test_confirmed_remainder_must_exactly_match_unused_reservation(self) -> None:
        ledger = apply_ledger_event(self.empty_ledger(), event("start", 40, reservation_id="r", assignment_id="a", amount=20))
        for usage, remainder in ((5, 14), (5, 16), (25, 1)):
            with self.subTest(usage=usage, remainder=remainder):
                with self.assertRaisesRegex(ValueError, "confirmed_remainder"):
                    apply_ledger_event(ledger, event("failed", 41, reservation_id="r", amount=usage, confirmed_remainder=remainder, terminal_evidence="failed"))
        settled = apply_ledger_event(ledger, event("failed", 42, reservation_id="r", amount=5, confirmed_remainder=15, terminal_evidence="failed"))
        self.assertEqual(15, settled["released"])
        large = self.empty_ledger()
        large.update({"ceiling": 1_000_000_000_000, "available": 1_000_000_000_000})
        large = apply_ledger_event(large, event("start", 43, reservation_id="large", assignment_id="large-a", amount=1_000_000_000_000))
        with self.assertRaisesRegex(ValueError, "confirmed_remainder"):
            apply_ledger_event(large, event("failed", 44, reservation_id="large", amount=1, confirmed_remainder=1_000_000_000_000, terminal_evidence="failed"))

    def test_every_history_version_and_global_event_identity_are_validated(self) -> None:
        registry, ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        ledger["transaction_version"] = registry["transaction_version"] = 3
        ledger["snapshot_version"] = registry["snapshot_version"] = 3
        ledger["transaction_id"] = registry["transaction_id"] = "tx-3"
        ledger["failure_history"] = [
            {"event_id": "f2", "type": "reconciliation_failure", "transaction_id": "tx-3", "transaction_version": 4, "reconciliation_version": 0, "event_hash": "2" * 64, "reason": "x"},
            {"event_id": "f1", "type": "reconciliation_failure", "transaction_id": "tx-2", "transaction_version": 2, "reconciliation_version": 0, "event_hash": "1" * 64, "reason": "y"},
        ]
        ledger["history"] = [{"event_id": "duplicate", "type": "start", "transaction_id": "tx-1", "transaction_version": 1, "event_hash": "0" * 64}]
        ledger["failure_history"][0]["event_id"] = "duplicate"
        ledger["applied_event_ids"] = ["duplicate", "f1"]
        errors = "\n".join(validate_orchestration_state(registry, ledger))
        self.assertIn("failure_history: transaction versions must be nondecreasing", errors)
        self.assertIn("must not exceed", errors)
        self.assertIn("conflicting event hash", errors)
        ledger["history"][0]["reconciliation_version"] = 1
        self.assertIn("history: reconciliation versions must be non-negative", "\n".join(validate_orchestration_state(registry, ledger)))
class RecoveryAndCliTests(unittest.TestCase):
    def test_recovery_uses_verified_last_known_good_and_idempotent_replay(self) -> None:
        good_registry, good_ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        good_registry["assignments"] = {}
        good_registry["teammates"]["worker-1"]["active_assignment_ids"] = []
        empty = copy.deepcopy(good_ledger)
        empty.update({"available": 100, "reserved": 0})
        empty["reservations"] = {}
        corrupt_registry = {"broken": True, "last_known_good": {"state": good_registry, "sha256": state_hash(good_registry), "snapshot_version": 1, "transaction_id": "tx-1"}}
        corrupt_ledger = {"broken": True, "last_known_good": {"state": empty, "sha256": state_hash(empty), "snapshot_version": 1, "transaction_id": "tx-1"}}
        launch = event("start", 2, reservation_id="reservation-1", assignment_id="assignment-1", logical_teammate_id="worker-1", amount=40)
        registry, ledger, errors = recover_state(corrupt_registry, corrupt_ledger, [launch, launch])
        self.assertEqual([], validate_orchestration_state(registry, ledger))
        self.assertEqual((60, 40, ["event-2"]), (ledger["available"], ledger["reserved"], ledger["applied_event_ids"]))
        self.assertTrue(any("last-known-good" in item for item in errors))

    def test_bad_snapshot_or_incomplete_evidence_blocks_and_quarantines(self) -> None:
        registry, ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        registry["snapshot_version"] = 9
        recovered_registry, recovered_ledger, errors = recover_state(registry, ledger, [])
        self.assertEqual("degraded", recovered_registry["status"])
        self.assertIn(recovered_registry.get("assignments", {}).get("assignment-1", {}).get("state"), {None, "unknown"})
        self.assertEqual((False, "blocked", None), (recovered_ledger["balances_known"], recovered_ledger["status"], recovered_ledger["available"]))
        self.assertTrue(recovered_registry["quarantine"])
        self.assertTrue(errors)
        for schema_name, recovered in [("team-registry.schema.json", recovered_registry), ("allocation-ledger.schema.json", recovered_ledger)]:
            schema = json.loads((ROOT / "config" / schema_name).read_text(encoding="utf-8"))
            self.assertEqual([], list(Draft202012Validator(schema).iter_errors(recovered)))
        self.assertEqual([], validate_orchestration_state(recovered_registry, recovered_ledger))

    def test_stale_native_handle_is_quarantined_and_assignment_becomes_unknown(self) -> None:
        registry, ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        registry["teammates"]["worker-1"]["native_handle"] = {
            "provider": "fixture-host",
            "handle": "expired-handle",
            "expires_at": "2000-01-01T00:00:00+00:00",
            "evidence_ref": "work-1",
        }
        recovered_registry, recovered_ledger, errors = recover_state(registry, ledger, [])
        self.assertIn(recovered_registry.get("assignments", {}).get("assignment-1", {}).get("state"), {None, "unknown"})
        self.assertIsNone(recovered_registry["teammates"]["worker-1"]["native_handle"])
        self.assertTrue(any(item["source"] == "native-handle" for item in recovered_registry["quarantine"]))
        self.assertFalse(recovered_ledger["balances_known"])
        self.assertTrue(any("expired" in error for error in errors))
        for schema_name, recovered in [("team-registry.schema.json", recovered_registry), ("allocation-ledger.schema.json", recovered_ledger)]:
            schema = json.loads((ROOT / "config" / schema_name).read_text(encoding="utf-8"))
            self.assertEqual([], list(Draft202012Validator(schema).iter_errors(recovered)))
        self.assertEqual([], validate_orchestration_state(recovered_registry, recovered_ledger))
    def test_replay_reconstructs_registry_assignment_or_blocks_incomplete_evidence(self) -> None:
        registry, ledger = load_fixture("valid-registry.json"), load_fixture("valid-ledger.json")
        registry["assignments"] = {}
        registry["teammates"]["worker-1"]["active_assignment_ids"] = []
        ledger["reservations"] = {}
        ledger.update({"available": 100, "reserved": 0})
        registry, ledger, errors = recover_state(registry, ledger, [event("start", 2, reservation_id="r2", assignment_id="a2", logical_teammate_id="worker-1", amount=10, evidence_refs=["work-1"])])
        self.assertEqual([], errors)
        self.assertEqual("a2", registry["assignments"]["a2"]["assignment_id"])
        self.assertEqual("r2", registry["assignments"]["a2"]["reservation_id"])
        self.assertEqual([], validate_orchestration_state(registry, ledger))
        _, broken_ledger, broken_errors = recover_state(registry, ledger, [event("start", 3, reservation_id="r3", assignment_id="a3", amount=10)])
        self.assertEqual("blocked", broken_ledger["status"])
        self.assertTrue(any("logical_teammate_id" in error for error in broken_errors))
    def test_cli_reports_success_and_failure_without_tracebacks(self) -> None:
        command = [sys.executable, str(ROOT / "scripts" / "validate_orchestration.py"), "--registry", str(FIXTURES / "valid-registry.json"), "--ledger", str(FIXTURES / "valid-ledger.json")]
        valid = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(0, valid.returncode, valid.stdout + valid.stderr)
        self.assertIn("ORCHESTRATION STATE VALIDATION PASSED", valid.stdout)
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.json"
            bad.write_text("{}", encoding="utf-8")
            invalid = subprocess.run(command[:-1] + [str(bad)], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertNotEqual(0, invalid.returncode)
        self.assertIn("ORCHESTRATION STATE VALIDATION FAILED", invalid.stdout)
        self.assertNotIn("Traceback", invalid.stderr)

    def test_cli_schema_validates_before_cross_record_checks_with_paths(self) -> None:
        registry = load_fixture("valid-registry.json")
        registry["unexpected"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_orchestration.py"), "--registry", str(path), "--ledger", str(FIXTURES / "valid-ledger.json")], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("$.registry", result.stdout)
        self.assertIn("unexpected", result.stdout)
        self.assertNotIn("snapshot_version", result.stdout)
        ledger = load_fixture("valid-ledger.json")
        ledger["unexpected"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            path.write_text(json.dumps(ledger), encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_orchestration.py"), "--registry", str(FIXTURES / "valid-registry.json"), "--ledger", str(path)], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("$.ledger", result.stdout)
        self.assertIn("unexpected", result.stdout)

if __name__ == "__main__":
    unittest.main()
