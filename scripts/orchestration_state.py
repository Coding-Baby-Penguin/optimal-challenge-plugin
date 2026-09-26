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


def _number(value: Any, path: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{path}: must be a finite non-negative number")
    return value


def _required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: must be a non-empty string")
    return value


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


def _advance(ledger: dict[str, Any], event: Mapping[str, Any], *, reconciliation: bool = False) -> None:
    ledger["transaction_version"] += 1
    ledger["snapshot_version"] += 1
    if reconciliation:
        ledger["reconciliation_version"] += 1
    ledger["transaction_id"] = event["transaction_id"]
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


def apply_ledger_event(ledger: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    """Apply one idempotent event to a copy of a ledger; never mutate its input."""
    if not isinstance(ledger, Mapping) or not isinstance(event, Mapping):
        raise TypeError("ledger and event must be mappings")
    result = deepcopy(dict(ledger))
    event_id = _required_text(event.get("event_id"), "$.event.event_id")
    kind = _required_text(event.get("type"), "$.event.type")
    _required_text(event.get("transaction_id"), "$.event.transaction_id")
    if event_id in result.get("applied_event_ids", []):
        matching = [item for item in result.get("history", []) if item.get("event_id") == event_id]
        if len(matching) != 1 or matching[0].get("event_hash") != _canonical_hash(event):
            raise ValueError(f"$.event.event_id: conflicting replay for {event_id!r}")
        return result

    if kind == "reconciliation_failure":
        result["status"] = "degraded"
        result["recovery_required"] = True
        result["recovery_error"] = _required_text(event.get("reason"), "$.event.reason")
        return result

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
        if any(item.get("assignment_id") == assignment_id and item.get("state") in {"reserved", "running", "unknown"} for item in reservations.values()):
            raise ValueError(f"$.event.assignment_id: {assignment_id!r} already has an active reservation")
        measurement = event.get("measurement", result.get("measurement"))
        if measurement not in {"observed", "estimated", "unavailable"}:
            raise ValueError("$.event.measurement: invalid measurement")
        reservations[reservation_id] = {
            "reservation_id": reservation_id,
            "assignment_id": assignment_id,
            "logical_teammate_id": event.get("logical_teammate_id"),
            "kind": "retry" if kind == "retry_start" else event.get("kind", "worker"),
            "attempt": event.get("attempt", 1),
            "initial_reserved": amount, "active_reserved": amount,
            "funded_consumed": 0, "funded_reservation_overrun": 0,
            "unfunded_consumed": 0, "released_unused": 0,
            "state": "running", "measurement": measurement,
            "reservation_transaction_id": event["transaction_id"],
            "evidence_refs": list(event.get("evidence_refs", [])), "terminal_evidence": None,
        }
        _advance(result, event)
        _recompute(result)
        return result

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
        result.setdefault("reset_history", []).append({"event_id": event_id, "transaction_id": event["transaction_id"], "reason": reason, "authority": authority, "evidence_ref": evidence_ref, "prior": prior})
        result["status"] = "degraded"
        result["accuracy_marker"] = "advisory_reset"
        _advance(result, event, reconciliation=True)
        _recompute(result)
        return result

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
        _advance(result, event, reconciliation=True)
        result.setdefault("reconciliation_history", []).append(_history_record(event, result["transaction_version"]))
        _recompute(result)
        return result

    aliases = {"fail": "failed", "retry_complete": "complete"}
    target = aliases.get(kind, kind)
    if target not in {"complete", "cancel", "failed", "timeout"}:
        raise ValueError(f"$.event.type: unsupported ledger event {kind!r}")
    if reservation.get("state") in TERMINAL_STATES:
        raise ValueError(f"$.reservation.state: terminal reservation cannot transition via {kind}")
    measurement = event.get("measurement", reservation.get("measurement", result.get("measurement")))
    terminal = event.get("terminal_evidence")

    if target == "timeout" and not terminal:
        reservation["state"] = "unknown"
        _advance(result, event)
        _recompute(result)
        return result
    if target == "failed" and measurement == "unavailable" and not event.get("confirms_no_further_use"):
        reservation["state"] = "unknown"
        _advance(result, event)
        _recompute(result)
        return result
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
            return result
        remainder = _number(confirmed_remainder, "$.event.confirmed_remainder")
        if usage + remainder < reservation["active_reserved"]:
            reservation["state"] = "unknown"
            _advance(result, event)
            _recompute(result)
            return result
    state = "cancelled" if target == "cancel" else target
    other_committed = sum(item["funded_consumed"] + item["active_reserved"] for key, item in reservations.items() if key != reservation_id)
    _settle(reservation, usage, state, measurement, terminal, result["ceiling"] - other_committed)
    _advance(result, event)
    _recompute(result)
    return result


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
        "history", "reconciliation_history", "reset_history", "applied_event_ids",
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
    logical_ids: set[str] = set()
    active_ids: set[str] = set()
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
            if assignment_id in active_ids:
                errors.append(f"$.registry.assignments.{assignment_id}: active assignment is not unique")
            active_ids.add(assignment_id)
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
    history = ledger.get("history", [])
    if isinstance(history, list):
        versions = [item.get("transaction_version") for item in history if isinstance(item, Mapping)]
        if versions != sorted(versions) or len(versions) != len(set(versions)):
            errors.append("$.ledger.history: transaction versions must be strictly increasing")
        if any(not isinstance(version, int) or isinstance(version, bool) or version < 0 or version > ledger.get("transaction_version", -1) for version in versions):
            errors.append("$.ledger.history: transaction versions must be non-negative and not exceed the ledger version")
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
        if reservation.get("state") in TERMINAL_STATES and not reservation.get("terminal_evidence"):
            errors.append(f"$.ledger.reservations.{key}.terminal_evidence: terminal state requires evidence")
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
    recovered_registry = deepcopy(dict(registry))
    recovered_registry.pop("last_known_good", None)
    recovered_registry.setdefault("assignments", {})
    for assignment in recovered_registry["assignments"].values():
        if isinstance(assignment, dict) and assignment.get("state") not in TERMINAL_STATES:
            assignment["state"] = "unknown"
    recovered_registry["status"] = "degraded"
    recovered_registry.setdefault("quarantine", []).append({"reason": "; ".join(reasons), "source": "cross-record", "snapshot_version": recovered_registry.get("snapshot_version") if isinstance(recovered_registry.get("snapshot_version"), int) else None})
    recovered_ledger = deepcopy(dict(ledger))
    recovered_ledger.pop("last_known_good", None)
    recovered_ledger["status"] = "blocked"
    recovered_ledger["balances_known"] = False
    for field in BALANCE_FIELDS:
        recovered_ledger[field] = None
    recovered_ledger["recovery_required"] = True
    recovered_ledger["recovery_error"] = "; ".join(reasons)
    recovered_ledger["accuracy_marker"] = "unknown_recovery"
    recovered_ledger.setdefault("quarantine", []).append({"reason": "; ".join(reasons), "source": "cross-record"})
    return recovered_registry, recovered_ledger, reasons


def recover_state(registry: Mapping[str, Any], ledger: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Recover from valid current state or verified snapshots, then replay evidence once."""
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
            if item.get("type") in {"start", "retry_start", "complete", "retry_complete", "cancel", "failed", "fail", "timeout", "late_report", "reconcile", "reconciliation_failure", "reset"}:
                recovered_ledger = apply_ledger_event(recovered_ledger, item)
    except (TypeError, ValueError, KeyError) as exc:
        return _unknown_recovery(recovered_registry, recovered_ledger, notices + [f"evidence replay failed: {exc}"])

    recovered_registry["snapshot_version"] = recovered_ledger.get("snapshot_version")
    recovered_registry["transaction_version"] = recovered_ledger.get("transaction_version")
    recovered_registry["transaction_id"] = recovered_ledger.get("transaction_id")
    state_map = {"reserved": "reserved", "running": "running", "complete": "complete", "failed": "failed", "cancelled": "cancelled", "unknown": "unknown"}
    for assignment_id, assignment in recovered_registry.get("assignments", {}).items():
        if isinstance(assignment, dict):
            reservation = recovered_ledger.get("reservations", {}).get(assignment.get("reservation_id"))
            if isinstance(reservation, Mapping):
                assignment["state"] = state_map.get(reservation.get("state"), "unknown")
    final_errors = validate_orchestration_state(recovered_registry, recovered_ledger)
    if final_errors:
        return _unknown_recovery(recovered_registry, recovered_ledger, notices + final_errors)
    return recovered_registry, recovered_ledger, notices
