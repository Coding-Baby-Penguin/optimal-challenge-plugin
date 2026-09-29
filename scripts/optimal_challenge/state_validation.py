"""Guard JSON shapes and cross-record invariants before any dispatch."""
from __future__ import annotations
import json
import math
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping
from .ledger import ACTIVE_STATES, BALANCE_FIELDS, TERMINAL_STATES, _canonical_hash, _finite_number, _is_non_negative

@lru_cache(maxsize=2)
def _state_schema(name: str) -> dict[str, Any]:
    return json.loads((Path(__file__).resolve().parents[2] / "config" / name).read_text(encoding="utf-8"))


def _shape_errors(value: Any, schema: Mapping[str, Any], root: Mapping[str, Any], path: str) -> list[str]:
    """Check JSON-derived shapes before semantic code hashes or dereferences them."""
    if "$ref" in schema:
        target = root
        for key in schema["$ref"].split("/")[1:]:
            target = target[key]
        return _shape_errors(value,target,root,path)
    if "oneOf" in schema:
        matches = sum(not _shape_errors(value,branch,root,path) for branch in schema["oneOf"])
        if matches != 1: return [f"{path}: must match exactly one allowed shape"]
    types = schema.get("type", [])
    types = [types] if isinstance(types,str) else types
    matches = {
        "object": isinstance(value,Mapping), "array": isinstance(value,list),
        "string": isinstance(value,str), "integer": isinstance(value,int) and not isinstance(value,bool),
        "number": _finite_number(value),
        "boolean": isinstance(value,bool), "null": value is None,
    }
    if types and not any(matches.get(kind,False) for kind in types):
        return [f"{path}: expected {' or '.join(types)}"]
    if "const" in schema and (value != schema["const"] or isinstance(value,bool) != isinstance(schema["const"],bool)):
        return [f"{path}: violates constant contract"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: invalid enum value"]
    errors = []
    if isinstance(value,str):
        if len(value)<schema.get("minLength",0) or ("pattern" in schema and re.search(schema["pattern"],value) is None): errors.append(f"{path}: string violates identifier or length contract")
    if _finite_number(value):
        if ("minimum" in schema and value<schema["minimum"]) or ("maximum" in schema and value>schema["maximum"]): errors.append(f"{path}: number violates bounds")
    if isinstance(value,Mapping):
        for key in schema.get("required",[]):
            if key not in value: errors.append(f"{path}.{key}: required key is missing")
        properties=schema.get("properties",{})
        additional=schema.get("additionalProperties",{})
        for key,item in value.items():
            if "propertyNames" in schema:
                errors.extend(_shape_errors(key,schema["propertyNames"],root,path+".<key>"))
            if not isinstance(key,str):
                errors.append(f"{path}: object keys must be strings")
                continue
            child=properties.get(key,additional)
            if child is False and key != "last_known_good": errors.append(f"{path}.{key}: unexpected key")
            if isinstance(child,Mapping): errors.extend(_shape_errors(item,child,root,f"{path}.{key}"))
    elif isinstance(value,list) and isinstance(schema.get("items"),Mapping):
        if schema.get("uniqueItems") and any(value[index] in value[:index] for index in range(len(value))): errors.append(f"{path}: array entries must be unique")
        for index,item in enumerate(value): errors.extend(_shape_errors(item,schema["items"],root,f"{path}[{index}]"))
    return errors


def validate_orchestration_state(registry: Mapping[str, Any], ledger: Mapping[str, Any]) -> list[str]:
    """Return path-qualified structural and cross-record invariant violations."""
    errors: list[str] = []
    if not isinstance(registry, Mapping):
        return ["$.registry: expected an object"]
    if not isinstance(ledger, Mapping):
        return ["$.ledger: expected an object"]
    for value, name, path in ((registry,"team-registry.schema.json","$.registry"),(ledger,"allocation-ledger.schema.json","$.ledger")):
        schema = _state_schema(name)
        errors.extend(_shape_errors(value,schema,schema,path))
    if any("required key is missing" not in item for item in errors):
        return errors
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
        sorted_versions = sorted(transaction_versions, key=lambda value: (-1 if not isinstance(value, int) or isinstance(value, bool) else value))
        if path == "history":
            if transaction_versions != sorted_versions or len(transaction_versions) != len(set(transaction_versions)):
                errors.append("$.ledger.history: transaction versions must be strictly increasing")
        elif transaction_versions != sorted_versions:
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
        if len(reconciliation_versions) != current_reconciliation or any(version != index for index,version in enumerate(sorted(reconciliation_versions),1)):
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
