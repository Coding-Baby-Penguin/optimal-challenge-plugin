"""Dependency-free mutation, validation, and recovery for disposable team state."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


TERMINAL_STATES = {"complete", "failed", "cancelled"}
BALANCE_FIELDS = (
    "available", "reserved", "funded_consumed", "funded_reservation_overrun",
    "unfunded_consumed", "total_consumed", "released",
)
EVENT_TYPES = {"start", "retry_start", "complete", "retry_complete", "cancel", "failed", "fail", "timeout", "late_report", "reconcile", "reconciliation_failure", "reset"}
RESERVATION_KINDS = {"coordinator", "worker", "tool", "review", "integration"}
MEASUREMENTS = {"observed", "estimated", "unavailable"}
ACTIVE_STATES = {"reserved", "running", "unknown"}
MAX_ATTEMPT = 13
EVENT_FIELDS = {
    "start": {"event_id", "type", "transaction_id", "reservation_id", "assignment_id", "logical_teammate_id", "kind", "amount", "attempt", "evidence_refs", "measurement"},
    "retry_start": {"event_id", "type", "transaction_id", "reservation_id", "assignment_id", "logical_teammate_id", "retry_of_reservation_id", "amount", "attempt", "evidence_refs", "measurement"},
    "complete": {"event_id", "type", "transaction_id", "reservation_id", "amount", "measurement", "terminal_evidence"},
    "retry_complete": {"event_id", "type", "transaction_id", "reservation_id", "amount", "measurement", "terminal_evidence"},
    "cancel": {"event_id", "type", "transaction_id", "reservation_id", "amount", "measurement", "terminal_evidence", "confirmed_remainder"},
    "failed": {"event_id", "type", "transaction_id", "reservation_id", "amount", "measurement", "terminal_evidence", "confirmed_remainder", "confirms_no_further_use"},
    "fail": {"event_id", "type", "transaction_id", "reservation_id", "amount", "measurement", "terminal_evidence", "confirmed_remainder", "confirms_no_further_use"},
    "timeout": {"event_id", "type", "transaction_id", "reservation_id", "amount", "measurement", "terminal_evidence", "confirmed_remainder"},
    "late_report": {"event_id", "type", "transaction_id", "reservation_id", "amount", "measurement", "terminal_evidence"},
    "reconcile": {"event_id", "type", "transaction_id", "reservation_id", "amount", "measurement", "terminal_evidence"},
    "reconciliation_failure": {"event_id", "type", "transaction_id", "reason"},
    "reset": {"event_id", "type", "transaction_id", "reservation_id", "reason", "authority", "evidence_ref"},
}


def _number(value: Any, path: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{path}: must be a finite non-negative number")
    return value


def _required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: must be a non-empty string")
    return value


def _validate_identifier_list(value: Any, path: str) -> None:
    if not isinstance(value, list):
        raise TypeError(f"{path}: must be an array")
    checked = [_required_text(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if len(checked) != len(set(checked)):
        raise ValueError(f"{path}: identifiers must be unique")


def _validate_attempt(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_ATTEMPT:
        raise ValueError(f"{path}: must be an integer from 1 through {MAX_ATTEMPT}")
    return value


def _validate_event(event: Mapping[str, Any]) -> None:
    event_type = _required_text(event.get("type"), "$.event.type")
    if event_type not in EVENT_TYPES:
        raise ValueError(f"$.event.type: unsupported ledger event {event_type!r}")
    unknown = set(event) - EVENT_FIELDS[event_type]
    if unknown:
        raise ValueError(f"$.event: unknown fields {sorted(unknown)!r}")
    _required_text(event.get("event_id"), "$.event.event_id")
    _required_text(event.get("transaction_id"), "$.event.transaction_id")
    if event_type in {"start", "retry_start", "complete", "retry_complete", "cancel", "failed", "fail", "timeout", "late_report", "reconcile", "reset"}:
        _required_text(event.get("reservation_id"), "$.event.reservation_id")
    if event_type in {"start", "retry_start"}:
        _required_text(event.get("assignment_id"), "$.event.assignment_id")
        _number(event.get("amount"), "$.event.amount")
        _validate_attempt(event.get("attempt", 1), "$.event.attempt")
        if event.get("logical_teammate_id") is not None:
            _required_text(event["logical_teammate_id"], "$.event.logical_teammate_id")
        if event_type == "start" and event.get("kind", "worker") not in RESERVATION_KINDS:
            raise ValueError("$.event.kind: invalid reservation kind")
        if event_type == "retry_start":
            _required_text(event.get("retry_of_reservation_id"), "$.event.retry_of_reservation_id")
        _validate_identifier_list(event.get("evidence_refs", []), "$.event.evidence_refs")
    for field in ("terminal_evidence", "reason", "evidence_ref"):
        if field in event:
            _required_text(event[field], f"$.event.{field}")
    if "measurement" in event and event["measurement"] not in MEASUREMENTS:
        raise ValueError("$.event.measurement: invalid measurement")
    for field in ("amount", "confirmed_remainder"):
        if field in event:
            _number(event[field], f"$.event.{field}")
    if "confirms_no_further_use" in event and not isinstance(event["confirms_no_further_use"], bool):
        raise TypeError("$.event.confirms_no_further_use: must be a boolean")
    if event_type == "reset" and event.get("authority") not in {"user", "coordinator"}:
        raise ValueError("$.event.authority: must be user or coordinator")


def _canonical_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _history_record(event: Mapping[str, Any], version: int) -> dict[str, Any]:
    record = {
        "event_id": event["event_id"], "type": event["type"],
        "transaction_id": event["transaction_id"], "transaction_version": version,
        "event_hash": _canonical_hash(event),
    }
    for key in ("reservation_id", "reason"):
        if isinstance(event.get(key), str) and event[key]:
            record[key] = event[key]
    return record


def _recompute(ledger: dict[str, Any]) -> None:
    reservations = ledger.get("reservations", {})
    ledger["reserved"] = sum(item["active_reserved"] for item in reservations.values())
    ledger["funded_consumed"] = sum(item["funded_consumed"] for item in reservations.values())
    ledger["funded_reservation_overrun"] = sum(item["funded_reservation_overrun"] for item in reservations.values())
    ledger["unfunded_consumed"] = sum(item["unfunded_consumed"] for item in reservations.values())
    ledger["total_consumed"] = ledger["funded_consumed"] + ledger["unfunded_consumed"]
    ledger["released"] = sum(item["released_unused"] for item in reservations.values())
    ledger["available"] = ledger["ceiling"] - ledger["reserved"] - ledger["funded_consumed"]
    if ledger["available"] < 0 and abs(ledger["available"]) < 1e-9:
        ledger["available"] = 0
    if ledger["unfunded_consumed"] > 0:
        ledger["status"] = "degraded" if ledger.get("status") != "blocked" else "blocked"


def _advance(ledger: dict[str, Any], event: Mapping[str, Any], *, reconciliation: bool = False, record_history: bool = True) -> None:
    ledger["transaction_version"] += 1
    ledger["snapshot_version"] += 1
    if reconciliation:
        ledger["reconciliation_version"] += 1
    ledger["transaction_id"] = event["transaction_id"]
    if record_history:
        ledger.setdefault("history", []).append(_history_record(event, ledger["transaction_version"]))
    ledger.setdefault("applied_event_ids", []).append(event["event_id"])


def _settle(reservation: dict[str, Any], usage: float | int, state: str, measurement: str, terminal: str, funded_capacity: float | int) -> None:
    initial = reservation["initial_reserved"]
    funded = min(usage, max(0, funded_capacity))
    overrun = max(0, funded - initial)
    reservation.update({
        "active_reserved": 0,
        "funded_consumed": funded,
        "funded_reservation_overrun": overrun,
        "unfunded_consumed": max(0, usage - funded),
        "released_unused": max(0, initial + overrun - funded),
        "state": state,
        "measurement": measurement,
        "terminal_evidence": terminal,
    })


def _validated_result(ledger: dict[str, Any]) -> dict[str, Any]:
    """Fail closed when a mutation would return a structurally inconsistent ledger."""
    reservations = ledger.get("reservations")
    if not isinstance(reservations, Mapping):
        raise ValueError("$.ledger.reservations: must be an object")
    transaction_version = ledger.get("transaction_version")
    reconciliation_version = ledger.get("reconciliation_version")
    if isinstance(transaction_version, bool) or not isinstance(transaction_version, int) or transaction_version < 0:
        raise ValueError("$.ledger.transaction_version: must be a non-negative integer")
    if isinstance(reconciliation_version, bool) or not isinstance(reconciliation_version, int) or reconciliation_version < 0:
        raise ValueError("$.ledger.reconciliation_version: must be a non-negative integer")
    seen_events: dict[str, Any] = {}
    reconciliation_versions: list[int] = []
    for name in ("history", "failure_history", "reconciliation_history", "reset_history"):
        records = ledger.get(name)
        if not isinstance(records, list):
            raise ValueError(f"$.ledger.{name}: must be an array")
        prior_transaction = -1
        prior_reconciliation = -1
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                raise ValueError(f"$.ledger.{name}[{index}]: must be an object")
            version = record.get("transaction_version")
            if isinstance(version, bool) or not isinstance(version, int) or not prior_transaction <= version <= transaction_version:
                raise ValueError(f"$.ledger.{name}: transaction versions must be nondecreasing and must not exceed current")
            prior_transaction = version
            if name != "history" or "reconciliation_version" in record:
                recon = record.get("reconciliation_version")
                if isinstance(recon, bool) or not isinstance(recon, int) or not prior_reconciliation <= recon <= reconciliation_version:
                    raise ValueError(f"$.ledger.{name}: reconciliation versions must be nondecreasing and must not exceed current")
                prior_reconciliation = recon
                if name in {"reconciliation_history", "reset_history"}:
                    reconciliation_versions.append(recon)
            event_id = _required_text(record.get("event_id"), f"$.ledger.{name}[{index}].event_id")
            event_hash = record.get("event_hash")
            if not isinstance(event_hash, str) or len(event_hash) != 64:
                raise ValueError(f"$.ledger.{name}[{index}].event_hash: invalid canonical hash")
            if event_id in seen_events:
                detail = "conflicting event hash" if seen_events[event_id] != event_hash else "duplicate event ID"
                raise ValueError(f"$.ledger.{name}[{index}].event_id: {detail}")
            seen_events[event_id] = event_hash
    if sorted(reconciliation_versions) != list(range(1, reconciliation_version + 1)):
        raise ValueError("$.ledger.reconciliation_version: specialized histories must exactly cover reconciliation versions")
    applied = ledger.get("applied_event_ids")
    if not isinstance(applied, list) or len(applied) != len(set(applied)) or set(applied) != set(seen_events):
        raise ValueError("$.ledger.applied_event_ids: must uniquely match all history event IDs")
    successors: set[tuple[str, int]] = set()
    roots: dict[str, str] = {}
    for key, reservation in reservations.items():
        if not isinstance(reservation, Mapping):
            raise ValueError(f"$.ledger.reservations.{key}: must be an object")
        attempt = _validate_attempt(reservation.get("attempt"), f"$.ledger.reservations.{key}.attempt")
        parent = reservation.get("retry_of_reservation_id")
        if reservation.get("kind") == "retry":
            successor = (_required_text(parent, f"$.ledger.reservations.{key}.retry_of_reservation_id"), attempt)
            if successor in successors:
                raise ValueError(f"$.ledger.reservations.{key}: retry predecessor/attempt already has a successor")
            successors.add(successor)
    for key in reservations:
        current, seen = key, set()
        while current in reservations and current not in seen:
            seen.add(current)
            parent = reservations[current].get("retry_of_reservation_id")
            if not isinstance(parent, str):
                break
            current = parent
        roots[key] = current
    active: dict[str, int] = {}
    for key, reservation in reservations.items():
        if reservation.get("state") in ACTIVE_STATES:
            root = roots[key]
            active[root] = active.get(root, 0) + 1
    if any(count > 1 for count in active.values()):
        raise ValueError("$.ledger.reservations: at most one active reservation is allowed per retry lineage")
    if ledger.get("balances_known"):
        expected_reserved = sum(item.get("active_reserved", 0) for item in reservations.values())
        if not _is_non_negative(ledger.get("reserved")) or not math.isclose(ledger["reserved"], expected_reserved, abs_tol=1e-9):
            raise ValueError("$.ledger.reserved: does not match active reservations")
        if not all(_is_non_negative(ledger.get(field)) for field in ("available", "reserved", "funded_consumed", "ceiling")) or not math.isclose(ledger["available"] + ledger["reserved"] + ledger["funded_consumed"], ledger["ceiling"], abs_tol=1e-9):
            raise ValueError("$.ledger: whole-ledger conservation failed")
    return ledger

def apply_ledger_event(ledger: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    """Apply one idempotent event to a copy of a ledger; never mutate its input."""
    if not isinstance(ledger, Mapping) or not isinstance(event, Mapping):
        raise TypeError("ledger and event must be mappings")
    _validate_event(event)
    result = deepcopy(dict(ledger))
    event_id = _required_text(event.get("event_id"), "$.event.event_id")
    kind = _required_text(event.get("type"), "$.event.type")
    _required_text(event.get("transaction_id"), "$.event.transaction_id")
    if event_id in result.get("applied_event_ids", []):
        matching = [item for collection in (result.get("history", []), result.get("failure_history", []), result.get("reconciliation_history", []), result.get("reset_history", [])) for item in collection if item.get("event_id") == event_id]
        if len(matching) != 1 or matching[0].get("event_hash") != _canonical_hash(event):
            raise ValueError(f"$.event.event_id: conflicting replay for {event_id!r}")
        return _validated_result(result)

    if kind == "reconciliation_failure":
        reason = _required_text(event.get("reason"), "$.event.reason")
        result["status"] = "degraded"
        result["recovery_required"] = True
        result["recovery_error"] = reason
        result.setdefault("failure_history", []).append({
            "event_id": event_id,
            "type": kind,
            "transaction_id": event["transaction_id"],
            "transaction_version": result["transaction_version"],
            "reconciliation_version": result["reconciliation_version"],
            "event_hash": _canonical_hash(event),
            "reason": reason,
        })
        result.setdefault("applied_event_ids", []).append(event_id)
        return _validated_result(result)

    reservations = result.setdefault("reservations", {})
    if kind in {"start", "retry_start"}:
        if not result.get("balances_known"):
            raise ValueError("$.ledger.available: balances are unknown; new reservations are blocked")
        reservation_id = _required_text(event.get("reservation_id"), "$.event.reservation_id")
        assignment_id = _required_text(event.get("assignment_id"), "$.event.assignment_id")
        amount = _number(event.get("amount"), "$.event.amount")
        if reservation_id in reservations:
            raise ValueError(f"$.event.reservation_id: {reservation_id!r} already exists")
        if amount > result.get("available", -1):
            raise ValueError("$.event.amount: reservation exceeds available funded capacity")
        if any(item.get("assignment_id") == assignment_id for item in reservations.values()):
            message = "retry attempts require a unique attempt assignment ID" if kind == "retry_start" else f"{assignment_id!r} already has a reservation"
            raise ValueError(f"$.event.assignment_id: {message}")
        retry_of = event.get("retry_of_reservation_id")
        attempt = event.get("attempt", 1)
        if kind == "retry_start":
            retry_of = _required_text(retry_of, "$.event.retry_of_reservation_id")
            prior = reservations.get(retry_of)
            if not isinstance(prior, Mapping):
                raise ValueError("$.event.retry_of_reservation_id: must identify an earlier reservation")
            if prior.get("state") not in TERMINAL_STATES:
                raise ValueError("$.event.retry_of_reservation_id: prior attempt must be terminal before retry")
            if attempt != prior.get("attempt", 0) + 1:
                raise ValueError("$.event.attempt: retry attempt must increment the prior attempt")
            if any(item.get("retry_of_reservation_id") == retry_of and item.get("attempt") == attempt for item in reservations.values()):
                raise ValueError("$.event.retry_of_reservation_id: predecessor already has a successor for this attempt")
            lineage = {retry_of}
            changed = True
            while changed:
                changed = False
                for key, item in reservations.items():
                    if key in lineage or item.get("retry_of_reservation_id") in lineage:
                        before = len(lineage)
                        lineage.add(key)
                        parent = item.get("retry_of_reservation_id")
                        if isinstance(parent, str):
                            lineage.add(parent)
                        changed = changed or len(lineage) != before
            if any(reservations[key].get("state") in ACTIVE_STATES for key in lineage if key in reservations):
                raise ValueError("$.event.retry_of_reservation_id: retry lineage already has an active reservation")
        elif retry_of is not None or attempt != 1:
            raise ValueError("$.event: initial reservations require attempt 1 and no retry lineage")
        measurement = event.get("measurement", result.get("measurement"))
        if measurement not in {"observed", "estimated", "unavailable"}:
            raise ValueError("$.event.measurement: invalid measurement")
        reservations[reservation_id] = {
            "reservation_id": reservation_id,
            "assignment_id": assignment_id,
            "logical_teammate_id": event.get("logical_teammate_id"),
            "retry_of_reservation_id": retry_of,
            "kind": "retry" if kind == "retry_start" else event.get("kind", "worker"),
            "attempt": attempt,
            "initial_reserved": amount, "active_reserved": amount,
            "funded_consumed": 0, "funded_reservation_overrun": 0,
            "unfunded_consumed": 0, "released_unused": 0,
            "state": "running", "measurement": measurement,
            "reservation_transaction_id": event["transaction_id"],
            "evidence_refs": list(event.get("evidence_refs", [])), "terminal_evidence": None,
        }
        _advance(result, event)
        _recompute(result)
        return _validated_result(result)

    reservation_id = event.get("reservation_id")
    if kind == "reset":
        if result.get("enforcement") != "advisory":
            raise ValueError("$.event.type: reset is permitted only for an advisory ledger")
        reservation_id = _required_text(reservation_id, "$.event.reservation_id")
        reservation = reservations.get(reservation_id)
        if not isinstance(reservation, dict):
            raise ValueError(f"$.event.reservation_id: unknown reservation {reservation_id!r}")
        reason = _required_text(event.get("reason"), "$.event.reason")
        authority = event.get("authority")
        if authority not in {"user", "coordinator"}:
            raise ValueError("$.event.authority: must be user or coordinator")
        evidence_ref = _required_text(event.get("evidence_ref"), "$.event.evidence_ref")
        prior = deepcopy(reservation)
        reservation["released_unused"] += reservation["active_reserved"]
        reservation["active_reserved"] = 0
        reservation["state"] = "cancelled"
        result["status"] = "degraded"
        result["accuracy_marker"] = "advisory_reset"
        _advance(result, event, reconciliation=True, record_history=False)
        result.setdefault("reset_history", []).append({"event_id": event_id, "transaction_id": event["transaction_id"], "transaction_version": result["transaction_version"], "reconciliation_version": result["reconciliation_version"], "event_hash": _canonical_hash(event), "reason": reason, "authority": authority, "evidence_ref": evidence_ref, "prior": prior})
        _recompute(result)
        return _validated_result(result)

    reservation_id = _required_text(reservation_id, "$.event.reservation_id")
    reservation = reservations.get(reservation_id)
    if not isinstance(reservation, dict):
        raise ValueError(f"$.event.reservation_id: unknown reservation {reservation_id!r}")

    if kind in {"late_report", "reconcile"}:
        usage = _number(event.get("amount"), "$.event.amount")
        terminal = _required_text(event.get("terminal_evidence"), "$.event.terminal_evidence")
        measurement = event.get("measurement", "observed")
        if measurement not in {"observed", "estimated"}:
            raise ValueError("$.event.measurement: reconciliation must be observed or estimated")
        other_committed = sum(item["funded_consumed"] + item["active_reserved"] for key, item in reservations.items() if key != reservation_id)
        _settle(reservation, usage, reservation.get("state", "complete") if reservation.get("state") in TERMINAL_STATES else "complete", measurement, terminal, result["ceiling"] - other_committed)
        _advance(result, event, reconciliation=True, record_history=False)
        reconciliation_record = _history_record(event, result["transaction_version"])
        reconciliation_record["reconciliation_version"] = result["reconciliation_version"]
        result.setdefault("reconciliation_history", []).append(reconciliation_record)
        _recompute(result)
        return _validated_result(result)

    aliases = {"fail": "failed", "retry_complete": "complete"}
    target = aliases.get(kind, kind)
    if target not in {"complete", "cancel", "failed", "timeout"}:
        raise ValueError(f"$.event.type: unsupported ledger event {kind!r}")
    if reservation.get("state") in TERMINAL_STATES:
        raise ValueError(f"$.reservation.state: terminal reservation cannot transition via {kind}")
    measurement = event.get("measurement", reservation.get("measurement", result.get("measurement")))
    terminal = event.get("terminal_evidence")

    if measurement == "unavailable" and target in {"cancel", "timeout"}:
        reservation["state"] = "unknown"
        _advance(result, event)
        _recompute(result)
        return _validated_result(result)
    if target == "timeout" and not terminal:
        reservation["state"] = "unknown"
        _advance(result, event)
        _recompute(result)
        return _validated_result(result)
    if target == "failed" and measurement == "unavailable" and not event.get("confirms_no_further_use"):
        reservation["state"] = "unknown"
        _advance(result, event)
        _recompute(result)
        return _validated_result(result)
    terminal = _required_text(terminal, "$.event.terminal_evidence")
    if measurement == "unavailable" and target == "complete":
        usage = reservation["active_reserved"]
    else:
        usage = _number(event.get("amount"), "$.event.amount")
    confirmed_remainder = event.get("confirmed_remainder")
    if target in {"cancel", "failed", "timeout"}:
        if confirmed_remainder is None:
            reservation["state"] = "unknown"
            _advance(result, event)
            _recompute(result)
            return _validated_result(result)
        remainder = _number(confirmed_remainder, "$.event.confirmed_remainder")
        expected_remainder = max(reservation["active_reserved"] - usage, 0)
        if not math.isclose(remainder, expected_remainder, abs_tol=1e-9):
            raise ValueError("$.event.confirmed_remainder: must exactly equal the unused active reservation after evidenced usage")
    state = "cancelled" if target == "cancel" else "failed" if target == "timeout" else target
    other_committed = sum(item["funded_consumed"] + item["active_reserved"] for key, item in reservations.items() if key != reservation_id)
    _settle(reservation, usage, state, measurement, terminal, result["ceiling"] - other_committed)
    _advance(result, event)
    _recompute(result)
    return _validated_result(result)


def _is_non_negative(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def validate_orchestration_state(registry: Mapping[str, Any], ledger: Mapping[str, Any]) -> list[str]:
    """Return path-qualified structural and cross-record invariant violations."""
    errors: list[str] = []
    if not isinstance(registry, Mapping):
        return ["$.registry: expected an object"]
    if not isinstance(ledger, Mapping):
        return ["$.ledger: expected an object"]
    registry_required = {
        "schema_version", "snapshot_version", "transaction_version", "transaction_id",
        "run_id", "coordinator_id", "status", "evidence", "teammates",
        "assignments", "quarantine",
    }
    ledger_required = {
        "schema_version", "snapshot_version", "transaction_version", "reconciliation_version",
        "transaction_id", "status", "balances_known", "unit", "ceiling", "measurement",
        "enforcement", "measurement_source", "reserves", *BALANCE_FIELDS, "reservations",
        "history", "reconciliation_history", "reset_history", "failure_history", "applied_event_ids",
    }
    for key in sorted(registry_required - set(registry)):
        errors.append(f"$.registry.{key}: required key is missing")
    for key in sorted(ledger_required - set(ledger)):
        errors.append(f"$.ledger.{key}: required key is missing")
    for key in ("snapshot_version", "transaction_version"):
        if registry.get(key) != ledger.get(key):
            errors.append(f"$.{key}: registry {registry.get(key)!r} does not match ledger {ledger.get(key)!r}")
    if registry.get("transaction_id") != ledger.get("transaction_id"):
        errors.append("$.transaction_id: registry and ledger transaction IDs do not match")

    evidence = registry.get("evidence", {})
    teammates = registry.get("teammates", {})
    assignments = registry.get("assignments", {})
    reservations = ledger.get("reservations", {})
    if not all(isinstance(value, Mapping) for value in (evidence, teammates, assignments, reservations)):
        errors.append("$: evidence, teammates, assignments, and reservations must be objects")
        return errors
    for key, item in evidence.items():
        if not isinstance(item, Mapping) or item.get("evidence_id") != key:
            errors.append(f"$.registry.evidence.{key}.evidence_id: must equal its key")
    logical_ids: set[str] = set()
    active_owners: dict[str, str] = {}
    for key, teammate in teammates.items():
        if not isinstance(teammate, Mapping):
            errors.append(f"$.registry.teammates.{key}: expected an object")
            continue
        logical = teammate.get("logical_teammate_id")
        if logical != key:
            errors.append(f"$.registry.teammates.{key}.logical_teammate_id: must equal its key")
        if logical in logical_ids:
            errors.append(f"$.registry.teammates.{key}.logical_teammate_id: conflicting logical ID")
        logical_ids.add(logical)
        trust = teammate.get("trust", {})
        refs = trust.get("evidence_refs", []) if isinstance(trust, Mapping) else []
        accepted = failed = 0
        for ref in refs:
            item = evidence.get(ref)
            if not isinstance(item, Mapping) or item.get("kind") != "review":
                errors.append(f"$.registry.teammates.{key}.trust.evidence_refs: {ref!r} is not review evidence")
            elif item.get("outcome") == "accepted":
                accepted += 1
            elif item.get("outcome") in {"rejected", "failed"}:
                failed += 1
        if trust.get("successful_reviews") != accepted or trust.get("failed_reviews") != failed:
            errors.append(f"$.registry.teammates.{key}.trust: counters are not backed by cited review evidence")
        for ref in teammate.get("working_set_evidence_refs", []):
            if ref not in evidence:
                errors.append(f"$.registry.teammates.{key}.working_set_evidence_refs: missing evidence {ref!r}")
        native_handle = teammate.get("native_handle")
        if isinstance(native_handle, Mapping):
            native_ref = native_handle.get("evidence_ref")
            if native_ref not in evidence:
                errors.append(f"$.registry.teammates.{key}.native_handle.evidence_ref: missing evidence {native_ref!r}")
            try:
                expires_at = datetime.fromisoformat(str(native_handle.get("expires_at", "")).replace("Z", "+00:00"))
                if expires_at.tzinfo is None or expires_at.utcoffset() is None:
                    raise ValueError("timezone missing")
                if expires_at <= datetime.now(timezone.utc):
                    errors.append(f"$.registry.teammates.{key}.native_handle.expires_at: native handle is expired")
            except ValueError:
                errors.append(f"$.registry.teammates.{key}.native_handle.expires_at: must be a timezone-aware date-time")
        for assignment_id in teammate.get("active_assignment_ids", []):
            if assignment_id in active_owners:
                errors.append(f"$.registry.assignments.{assignment_id}: active assignment is not unique")
            else:
                active_owners[assignment_id] = key
            if assignment_id not in assignments:
                errors.append(f"$.registry.teammates.{key}.active_assignment_ids: missing assignment {assignment_id!r}")

    for key, assignment in assignments.items():
        if not isinstance(assignment, Mapping):
            errors.append(f"$.registry.assignments.{key}: expected an object")
            continue
        if assignment.get("assignment_id") != key:
            errors.append(f"$.registry.assignments.{key}.assignment_id: must equal its key")
        teammate = teammates.get(assignment.get("logical_teammate_id"))
        if not isinstance(teammate, Mapping):
            errors.append(f"$.registry.assignments.{key}.logical_teammate_id: unknown teammate")
        elif assignment.get("capability_class") != teammate.get("capability_class"):
            errors.append(f"$.registry.assignments.{key}.capability_class: does not match teammate capability_class")
        reservation_id = assignment.get("reservation_id")
        reservation = reservations.get(reservation_id)
        if not isinstance(reservation, Mapping) or reservation.get("assignment_id") != key:
            errors.append(f"$.registry.assignments.{key}.reservation_id: does not resolve to assignment {key!r}")
        else:
            if reservation.get("logical_teammate_id") != assignment.get("logical_teammate_id"):
                errors.append(f"$.registry.assignments.{key}.logical_teammate_id: does not match reservation logical_teammate_id")
            if reservation.get("state") != assignment.get("state"):
                errors.append(f"$.registry.assignments.{key}.state: does not match reservation state")
        is_active = assignment.get("state") in {"reserved", "running", "unknown"}
        active_owner = active_owners.get(key)
        listed_with_owner = active_owner == assignment.get("logical_teammate_id")
        if is_active != listed_with_owner:
            errors.append(f"$.registry.assignments.{key}.state: active_assignment_ids membership under the assigned teammate does not match state")
        if active_owner is not None and active_owner != assignment.get("logical_teammate_id"):
            errors.append(f"$.registry.assignments.{key}: active assignment is listed under a teammate other than its assigned teammate")
        for ref in assignment.get("evidence_refs", []):
            if ref not in evidence:
                errors.append(f"$.registry.assignments.{key}.evidence_refs: missing evidence {ref!r}")

    assignment_reservations: dict[str, str] = {}
    for reservation_key, reservation in reservations.items():
        if isinstance(reservation, Mapping):
            assignment_id = reservation.get("assignment_id")
            if isinstance(assignment_id, str) and assignment_id in assignment_reservations:
                errors.append(f"$.ledger.reservations.{reservation_key}.assignment_id: assignment {assignment_id!r} has more than one reservation")
            elif isinstance(assignment_id, str):
                assignment_reservations[assignment_id] = reservation_key
            assignment = assignments.get(assignment_id)
            if not isinstance(assignment, Mapping):
                errors.append(f"$.ledger.reservations.{reservation_key}.assignment_id: orphan reservation references unknown assignment {assignment_id!r}")
            else:
                if assignment.get("reservation_id") != reservation_key:
                    errors.append(f"$.ledger.reservations.{reservation_key}.assignment_id: assignment does not point back to reservation")
                if assignment.get("logical_teammate_id") != reservation.get("logical_teammate_id"):
                    errors.append(f"$.ledger.reservations.{reservation_key}.logical_teammate_id: does not match assignment")
                if assignment.get("state") != reservation.get("state"):
                    errors.append(f"$.ledger.reservations.{reservation_key}.state: does not match assignment state")
            for ref in reservation.get("evidence_refs", []):
                if ref not in evidence:
                    errors.append(f"$.ledger.reservations.{reservation_key}.evidence_refs: missing evidence {ref!r}")
    history = ledger.get("history", [])
    reconciliation_history = ledger.get("reconciliation_history", [])
    reset_history = ledger.get("reset_history", [])
    failure_history = ledger.get("failure_history", [])
    collections = (
        ("history", history), ("failure_history", failure_history),
        ("reconciliation_history", reconciliation_history), ("reset_history", reset_history),
    )
    current_transaction = ledger.get("transaction_version", -1)
    current_reconciliation = ledger.get("reconciliation_version", -1)
    all_records: list[tuple[str, Mapping[str, Any]]] = []
    reconciliation_versions: list[int] = []
    for path, records in collections:
        if not isinstance(records, list):
            errors.append(f"$.ledger.{path}: must be an array")
            continue
        mapped = [item for item in records if isinstance(item, Mapping)]
        transaction_versions = [item.get("transaction_version") for item in mapped]
        if transaction_versions != sorted(transaction_versions, key=lambda value: (-1 if not isinstance(value, int) or isinstance(value, bool) else value)):
            errors.append(f"$.ledger.{path}: transaction versions must be nondecreasing")
        if any(not isinstance(version, int) or isinstance(version, bool) or version < 0 or version > current_transaction for version in transaction_versions):
            errors.append(f"$.ledger.{path}: transaction versions must be non-negative and must not exceed the current transaction version")
        versioned = mapped if path != "history" else [item for item in mapped if "reconciliation_version" in item]
        if versioned:
            versions = [item.get("reconciliation_version") for item in versioned]
            if versions != sorted(versions, key=lambda value: (-1 if not isinstance(value, int) or isinstance(value, bool) else value)):
                errors.append(f"$.ledger.{path}: reconciliation versions must be nondecreasing")
            if any(not isinstance(version, int) or isinstance(version, bool) or version < 0 or version > current_reconciliation for version in versions):
                errors.append(f"$.ledger.{path}: reconciliation versions must be non-negative and must not exceed the current reconciliation version")
            if path in {"reconciliation_history", "reset_history"}:
                reconciliation_versions.extend(version for version in versions if isinstance(version, int) and not isinstance(version, bool))
        all_records.extend((path, item) for item in mapped)
    if isinstance(current_reconciliation, int) and not isinstance(current_reconciliation, bool):
        if sorted(reconciliation_versions) != list(range(1, current_reconciliation + 1)):
            errors.append("$.ledger.reconciliation_version: history count and versions must exactly match reconciliation_version")
    event_records: dict[str, tuple[str, Any]] = {}
    for path, record in all_records:
        event_id = record.get("event_id")
        if not isinstance(event_id, str):
            continue
        event_hash = record.get("event_hash")
        if event_id in event_records:
            previous_path, previous_hash = event_records[event_id]
            if previous_hash != event_hash:
                errors.append(f"$.ledger.{path}: event ID {event_id!r} has a conflicting event hash with {previous_path}")
            else:
                errors.append(f"$.ledger.{path}: event ID {event_id!r} is duplicated across histories")
        else:
            event_records[event_id] = (path, event_hash)
    applied_ids = ledger.get("applied_event_ids", [])
    recorded_ids = list(event_records)
    if isinstance(applied_ids, list) and (len(applied_ids) != len(set(applied_ids)) or set(applied_ids) != set(recorded_ids)):
        errors.append("$.ledger.applied_event_ids: must uniquely match all history event IDs")
    measurement, enforcement = ledger.get("measurement"), ledger.get("enforcement")
    if enforcement in {"local_enforced", "provider_enforced"} and (measurement != "observed" or not ledger.get("measurement_source")):
        errors.append("$.ledger.enforcement: enforced ledgers require observed measurement and a source")
    balances_known = ledger.get("balances_known")
    if balances_known:
        for field in BALANCE_FIELDS:
            if not _is_non_negative(ledger.get(field)):
                errors.append(f"$.ledger.{field}: must be a non-negative finite number when balances are known")
        if all(_is_non_negative(ledger.get(field)) for field in ("available", "reserved", "funded_consumed", "ceiling")):
            if not math.isclose(ledger["available"] + ledger["reserved"] + ledger["funded_consumed"], ledger["ceiling"], abs_tol=1e-9):
                errors.append("$.ledger: whole-ledger conservation failed: available + reserved + funded_consumed must equal ceiling")
        if all(_is_non_negative(ledger.get(field)) for field in ("total_consumed", "funded_consumed", "unfunded_consumed")) and not math.isclose(ledger["total_consumed"], ledger["funded_consumed"] + ledger["unfunded_consumed"], abs_tol=1e-9):
            errors.append("$.ledger.total_consumed: must equal funded_consumed + unfunded_consumed")
    elif any(ledger.get(field) is not None for field in BALANCE_FIELDS):
        errors.append("$.ledger: unknown balances must be represented as null")
    for key, reservation in reservations.items():
        if not isinstance(reservation, Mapping):
            errors.append(f"$.ledger.reservations.{key}: expected an object")
            continue
        if reservation.get("reservation_id") != key:
            errors.append(f"$.ledger.reservations.{key}.reservation_id: must equal its key")
        fields = ("initial_reserved", "active_reserved", "funded_consumed", "funded_reservation_overrun", "unfunded_consumed", "released_unused")
        if not all(_is_non_negative(reservation.get(field)) for field in fields):
            errors.append(f"$.ledger.reservations.{key}: all amounts must be non-negative finite numbers")
        elif not math.isclose(reservation["initial_reserved"] + reservation["funded_reservation_overrun"], reservation["active_reserved"] + reservation["funded_consumed"] + reservation["released_unused"], abs_tol=1e-9):
            errors.append(f"$.ledger.reservations.{key}: per-reservation conservation failed")
        retry_of = reservation.get("retry_of_reservation_id")
        attempt = reservation.get("attempt")
        if reservation.get("kind") == "retry":
            prior = reservations.get(retry_of)
            if not isinstance(prior, Mapping):
                errors.append(f"$.ledger.reservations.{key}.retry_of_reservation_id: retry must identify an earlier reservation")
            else:
                if prior.get("state") not in TERMINAL_STATES:
                    errors.append(f"$.ledger.reservations.{key}.retry_of_reservation_id: prior attempt must be terminal")
                if attempt != prior.get("attempt", 0) + 1:
                    errors.append(f"$.ledger.reservations.{key}.attempt: must increment the prior attempt")
        elif retry_of is not None or attempt != 1:
            errors.append(f"$.ledger.reservations.{key}.retry_of_reservation_id: non-retry reservations require null lineage and attempt 1")
        terminal_evidence = reservation.get("terminal_evidence")
        if reservation.get("state") in TERMINAL_STATES and not terminal_evidence:
            errors.append(f"$.ledger.reservations.{key}.terminal_evidence: terminal state requires evidence")
        elif terminal_evidence and terminal_evidence not in evidence:
            errors.append(f"$.ledger.reservations.{key}.terminal_evidence: missing registry evidence {terminal_evidence!r}")
    successors: dict[tuple[str, Any], str] = {}
    for key, reservation in reservations.items():
        if not isinstance(reservation, Mapping) or reservation.get("kind") != "retry":
            continue
        successor_key = (reservation.get("retry_of_reservation_id"), reservation.get("attempt"))
        if successor_key in successors:
            errors.append(f"$.ledger.reservations.{key}: retry predecessor/attempt already has successor {successors[successor_key]!r}")
        else:
            successors[successor_key] = key
    roots: dict[str, str] = {}
    for key in reservations:
        current = key
        seen: set[str] = set()
        while current in reservations and current not in seen:
            seen.add(current)
            parent = reservations[current].get("retry_of_reservation_id") if isinstance(reservations[current], Mapping) else None
            if not isinstance(parent, str):
                break
            current = parent
        roots[key] = current
    active_by_root: dict[str, list[str]] = {}
    for key, reservation in reservations.items():
        if isinstance(reservation, Mapping) and reservation.get("state") in ACTIVE_STATES:
            active_by_root.setdefault(roots.get(key, key), []).append(key)
    for root, active in active_by_root.items():
        if len(active) > 1:
            errors.append(f"$.ledger.reservations: retry lineage {root!r} has more than one active reservation: {active!r}")
    if _is_non_negative(ledger.get("unfunded_consumed")) and ledger.get("unfunded_consumed", 0) > 0 and ledger.get("status") not in {"degraded", "blocked"}:
        errors.append("$.ledger.status: unfunded consumption requires degraded or blocked status")
    return errors


def _verified_snapshot(container: Mapping[str, Any]) -> dict[str, Any] | None:
    candidate = container.get("last_known_good")
    if not isinstance(candidate, Mapping) or not isinstance(candidate.get("state"), Mapping):
        return None
    state = deepcopy(dict(candidate["state"]))
    if candidate.get("sha256") != _canonical_hash(state):
        return None
    if candidate.get("snapshot_version") != state.get("snapshot_version") or candidate.get("transaction_id") != state.get("transaction_id"):
        return None
    return state


def _unknown_recovery(registry: Mapping[str, Any], ledger: Mapping[str, Any], reasons: list[str]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Return a closed-schema, cross-record-valid blocked state with safe entries retained."""
    reason = "; ".join(str(item) for item in reasons if str(item).strip()) or "orchestration state could not be verified"
    raw_evidence = registry.get("evidence", {}) if isinstance(registry.get("evidence"), Mapping) else {}
    recovered_evidence: dict[str, Any] = {}
    for key, item in raw_evidence.items():
        if isinstance(key, str) and key.strip() and isinstance(item, Mapping) and item.get("evidence_id") == key:
            allowed = {name: deepcopy(item[name]) for name in ("evidence_id", "kind", "outcome", "sha256", "version") if name in item}
            if allowed.get("kind") in {"review", "source", "test", "task", "return", "reservation", "terminal", "decision"} and allowed.get("outcome") in {"accepted", "rejected", "verified", "failed", "unknown"}:
                recovered_evidence[key] = allowed

    raw_teammates = registry.get("teammates", {}) if isinstance(registry.get("teammates"), Mapping) else {}
    recovered_teammates: dict[str, Any] = {}
    for key, item in raw_teammates.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(item, Mapping) or item.get("logical_teammate_id") != key:
            continue
        trust = item.get("trust", {}) if isinstance(item.get("trust"), Mapping) else {}
        trust_refs = [ref for ref in trust.get("evidence_refs", []) if ref in recovered_evidence and recovered_evidence[ref].get("kind") == "review"]
        successful = sum(recovered_evidence[ref].get("outcome") == "accepted" for ref in trust_refs)
        failed = sum(recovered_evidence[ref].get("outcome") in {"rejected", "failed"} for ref in trust_refs)
        capability = item.get("capability_class") if item.get("capability_class") in {"economy", "standard", "reasoning", "frontier"} else "standard"
        continuity = item.get("continuity_mode") if item.get("continuity_mode") in {"resume", "rehydrate", "fresh"} else "rehydrate"
        recovered_teammates[key] = {
            "logical_teammate_id": key,
            "role": item.get("role") if isinstance(item.get("role"), str) and item.get("role").strip() else "recovered",
            "capability_class": capability,
            "continuity_mode": continuity,
            "native_handle": None,
            "working_set_evidence_refs": [ref for ref in item.get("working_set_evidence_refs", []) if ref in recovered_evidence],
            "trust": {"successful_reviews": successful, "failed_reviews": failed, "evidence_refs": trust_refs},
            "active_assignment_ids": [],
        }

    raw_assignments = registry.get("assignments", {}) if isinstance(registry.get("assignments"), Mapping) else {}
    raw_reservations = ledger.get("reservations", {}) if isinstance(ledger.get("reservations"), Mapping) else {}
    recovered_assignments: dict[str, Any] = {}
    recovered_reservations: dict[str, Any] = {}
    reservation_fields = {
        "reservation_id", "assignment_id", "retry_of_reservation_id", "logical_teammate_id", "kind", "attempt",
        "initial_reserved", "active_reserved", "funded_consumed", "funded_reservation_overrun",
        "unfunded_consumed", "released_unused", "state", "measurement", "reservation_transaction_id",
        "evidence_refs", "terminal_evidence",
    }
    for assignment_id, assignment in raw_assignments.items():
        if not isinstance(assignment_id, str) or not assignment_id.strip() or not isinstance(assignment, Mapping):
            continue
        teammate_id = assignment.get("logical_teammate_id")
        reservation_id = assignment.get("reservation_id")
        reservation = raw_reservations.get(reservation_id)
        if teammate_id not in recovered_teammates or not isinstance(reservation_id, str) or not reservation_id.strip() or not isinstance(reservation, Mapping):
            continue
        if reservation.get("reservation_id") != reservation_id or reservation.get("assignment_id") != assignment_id or reservation.get("logical_teammate_id") != teammate_id:
            continue
        cleaned = {name: deepcopy(reservation.get(name)) for name in reservation_fields}
        cleaned["state"] = "unknown"
        cleaned["terminal_evidence"] = None
        cleaned["evidence_refs"] = [ref for ref in reservation.get("evidence_refs", []) if ref in recovered_evidence]
        if any(not _is_non_negative(cleaned.get(name)) for name in ("initial_reserved", "active_reserved", "funded_consumed", "funded_reservation_overrun", "unfunded_consumed", "released_unused")):
            continue
        recovered_reservations[reservation_id] = cleaned
        recovered_assignments[assignment_id] = {
            "assignment_id": assignment_id,
            "logical_teammate_id": teammate_id,
            "reservation_id": reservation_id,
            "capability_class": recovered_teammates[teammate_id]["capability_class"],
            "state": "unknown",
            "evidence_refs": [ref for ref in assignment.get("evidence_refs", []) if ref in recovered_evidence],
        }
        recovered_teammates[teammate_id]["active_assignment_ids"].append(assignment_id)

    snapshot_version = ledger.get("snapshot_version") if isinstance(ledger.get("snapshot_version"), int) and not isinstance(ledger.get("snapshot_version"), bool) and ledger.get("snapshot_version") >= 0 else 0
    transaction_version = ledger.get("transaction_version") if isinstance(ledger.get("transaction_version"), int) and not isinstance(ledger.get("transaction_version"), bool) and ledger.get("transaction_version") >= 0 else 0
    transaction_id = ledger.get("transaction_id") if isinstance(ledger.get("transaction_id"), str) and ledger.get("transaction_id").strip() else "recovery-quarantine"
    quarantine_entries = [{"reason": reason, "source": "cross-record", "snapshot_version": snapshot_version}]
    for teammate_id, teammate in raw_teammates.items():
        if isinstance(teammate, Mapping) and isinstance(teammate.get("native_handle"), Mapping):
            quarantine_entries.append({"reason": f"removed unverified or expired native handle for {teammate_id}", "source": "native-handle", "snapshot_version": snapshot_version})
    recovered_registry = {
        "schema_version": 1,
        "snapshot_version": snapshot_version,
        "transaction_version": transaction_version,
        "transaction_id": transaction_id,
        "run_id": registry.get("run_id") if isinstance(registry.get("run_id"), str) and registry.get("run_id").strip() else "recovered-run",
        "coordinator_id": registry.get("coordinator_id") if isinstance(registry.get("coordinator_id"), str) and registry.get("coordinator_id").strip() else "recovered-coordinator",
        "status": "degraded",
        "evidence": recovered_evidence,
        "teammates": recovered_teammates,
        "assignments": recovered_assignments,
        "quarantine": quarantine_entries,
    }
    unit = ledger.get("unit") if ledger.get("unit") in {"credits", "tokens", "seconds", "currency", "tool_calls", "model_calls"} else "model_calls"
    ceiling = ledger.get("ceiling") if _is_non_negative(ledger.get("ceiling")) else 0
    reserves = ledger.get("reserves") if isinstance(ledger.get("reserves"), Mapping) else {}
    recovered_ledger = {
        "schema_version": 1,
        "snapshot_version": snapshot_version,
        "transaction_version": transaction_version,
        "reconciliation_version": 0,
        "transaction_id": transaction_id,
        "status": "blocked",
        "balances_known": False,
        "unit": unit,
        "ceiling": ceiling,
        "measurement": "unavailable",
        "enforcement": "advisory",
        "measurement_source": None,
        "reserves": {name: reserves.get(name) if _is_non_negative(reserves.get(name)) else 0 for name in ("coordinator", "integration", "mandatory_review")},
        "available": None,
        "reserved": None,
        "funded_consumed": None,
        "funded_reservation_overrun": None,
        "unfunded_consumed": None,
        "total_consumed": None,
        "released": None,
        "reservations": recovered_reservations,
        "history": [],
        "reconciliation_history": [],
        "reset_history": [],
        "failure_history": [],
        "applied_event_ids": [],
        "recovery_required": True,
        "recovery_error": reason,
        "accuracy_marker": "unknown_recovery",
        "quarantine": [{"reason": reason, "source": "cross-record"}],
    }
    recovery_errors = validate_orchestration_state(recovered_registry, recovered_ledger)
    if recovery_errors:
        recovered_registry["evidence"] = {}
        recovered_registry["teammates"] = {}
        recovered_registry["assignments"] = {}
        recovered_ledger["reservations"] = {}
        recovery_errors = validate_orchestration_state(recovered_registry, recovered_ledger)
        if recovery_errors:
            reasons = reasons + [f"degraded recovery validation failed: {item}" for item in recovery_errors]
    return recovered_registry, recovered_ledger, reasons


def recover_state(registry: Mapping[str, Any], ledger: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Recover verified state and replay events while rebuilding both sides atomically."""
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        raise TypeError("evidence must be a sequence of mappings")
    current_errors = validate_orchestration_state(registry, ledger)
    recovered_registry, recovered_ledger = deepcopy(dict(registry)), deepcopy(dict(ledger))
    notices: list[str] = []
    if current_errors:
        recovered_registry = _verified_snapshot(registry) or {}
        recovered_ledger = _verified_snapshot(ledger) or {}
        if not recovered_registry or not recovered_ledger:
            return _unknown_recovery(registry, ledger, current_errors + ["no hash/version-verified last-known-good snapshot"])
        snapshot_errors = validate_orchestration_state(recovered_registry, recovered_ledger)
        if snapshot_errors:
            return _unknown_recovery(registry, ledger, current_errors + snapshot_errors + ["last-known-good snapshot pair is inconsistent"])
        notices.append("restored hash/version-verified last-known-good registry and ledger")

    try:
        for item in evidence:
            if not isinstance(item, Mapping):
                raise ValueError("evidence item must be an object")
            event_type = item.get("type")
            if event_type not in {"start", "retry_start", "complete", "retry_complete", "cancel", "failed", "fail", "timeout", "late_report", "reconcile", "reconciliation_failure", "reset"}:
                continue
            already_applied = item.get("event_id") in recovered_ledger.get("applied_event_ids", [])
            recovered_ledger = apply_ledger_event(recovered_ledger, item)
            if already_applied:
                continue
            if event_type in {"start", "retry_start"}:
                assignment_id = _required_text(item.get("assignment_id"), "$.evidence.assignment_id")
                reservation_id = _required_text(item.get("reservation_id"), "$.evidence.reservation_id")
                teammate_id = _required_text(item.get("logical_teammate_id"), "$.evidence.logical_teammate_id")
                teammate = recovered_registry.get("teammates", {}).get(teammate_id)
                if not isinstance(teammate, dict):
                    raise ValueError(f"$.evidence.logical_teammate_id: unknown teammate {teammate_id!r}")
                refs = list(item.get("evidence_refs", []))
                missing = [ref for ref in refs if ref not in recovered_registry.get("evidence", {})]
                if missing:
                    raise ValueError(f"$.evidence.evidence_refs: missing registry evidence {missing!r}")
                if assignment_id in recovered_registry.get("assignments", {}):
                    raise ValueError(f"$.evidence.assignment_id: conflicting assignment {assignment_id!r}")
                recovered_registry.setdefault("assignments", {})[assignment_id] = {
                    "assignment_id": assignment_id,
                    "logical_teammate_id": teammate_id,
                    "reservation_id": reservation_id,
                    "capability_class": teammate["capability_class"],
                    "state": "running",
                    "evidence_refs": refs,
                }
                teammate.setdefault("active_assignment_ids", []).append(assignment_id)
            reservation_id = item.get("reservation_id")
            reservation = recovered_ledger.get("reservations", {}).get(reservation_id)
            if isinstance(reservation, Mapping):
                assignment = recovered_registry.get("assignments", {}).get(reservation.get("assignment_id"))
                if not isinstance(assignment, dict):
                    raise ValueError(f"$.evidence.assignment_id: reservation {reservation_id!r} has no matching registry assignment")
                assignment["state"] = reservation.get("state", "unknown")
                teammate = recovered_registry.get("teammates", {}).get(assignment.get("logical_teammate_id"))
                if not isinstance(teammate, dict):
                    raise ValueError("$.evidence.logical_teammate_id: assignment teammate is unavailable")
                active_ids = teammate.setdefault("active_assignment_ids", [])
                is_active = assignment["state"] in {"reserved", "running", "unknown"}
                if is_active and assignment["assignment_id"] not in active_ids:
                    active_ids.append(assignment["assignment_id"])
                if not is_active and assignment["assignment_id"] in active_ids:
                    active_ids.remove(assignment["assignment_id"])
    except (TypeError, ValueError, KeyError) as exc:
        return _unknown_recovery(recovered_registry, recovered_ledger, notices + [f"evidence replay failed: {exc}"])

    recovered_registry["snapshot_version"] = recovered_ledger.get("snapshot_version")
    recovered_registry["transaction_version"] = recovered_ledger.get("transaction_version")
    recovered_registry["transaction_id"] = recovered_ledger.get("transaction_id")
    final_errors = validate_orchestration_state(recovered_registry, recovered_ledger)
    if final_errors:
        return _unknown_recovery(recovered_registry, recovered_ledger, notices + final_errors)
    return recovered_registry, recovered_ledger, notices
