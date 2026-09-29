"""Dependency-free mutation, validation, and recovery for disposable team state."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import math
import re
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


def _finite_number(value: Any) -> bool:
    if isinstance(value,bool) or not isinstance(value,(int,float)): return False
    try: return math.isfinite(value)
    except OverflowError: return False


def _number(value: Any, path: str) -> float | int:
    if not _finite_number(value) or value < 0:
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
            valid_order = (version > prior_transaction) if name == "history" and isinstance(version, int) and not isinstance(version, bool) else (prior_transaction <= version) if isinstance(version, int) and not isinstance(version, bool) else False
            if not valid_order or version > transaction_version:
                order = "strictly increasing" if name == "history" else "nondecreasing"
                raise ValueError(f"$.ledger.{name}: transaction versions must be {order} and must not exceed current")
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
    if len(reconciliation_versions) != reconciliation_version or any(version != index for index, version in enumerate(sorted(reconciliation_versions), 1)):
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
        if not math.isclose(remainder, expected_remainder, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("$.event.confirmed_remainder: must exactly equal the unused active reservation after evidenced usage")
    state = "cancelled" if target == "cancel" else "failed" if target == "timeout" else target
    other_committed = sum(item["funded_consumed"] + item["active_reserved"] for key, item in reservations.items() if key != reservation_id)
    _settle(reservation, usage, state, measurement, terminal, result["ceiling"] - other_committed)
    _advance(result, event)
    _recompute(result)
    return _validated_result(result)


def _is_non_negative(value: Any) -> bool:
    return _finite_number(value) and value >= 0
