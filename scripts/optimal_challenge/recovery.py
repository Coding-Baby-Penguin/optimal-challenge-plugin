"""Recover validated state and reserve mandatory obligations before dispatch."""
from __future__ import annotations
from copy import deepcopy
from typing import Any, Mapping, Sequence
from .ledger import apply_ledger_event, _canonical_hash, _is_non_negative, _number, _required_text, _validate_event
from .state_validation import validate_orchestration_state

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


def _safe_refs(value: Any, evidence: Mapping[str, Any]) -> list[str]:
    return [ref for ref in value if isinstance(ref,str) and ref in evidence] if isinstance(value,list) else []


def _unknown_recovery(registry: Mapping[str, Any], ledger: Mapping[str, Any], reasons: list[str]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Return a closed-schema, cross-record-valid blocked state with safe entries retained."""
    reason = "; ".join(str(item) for item in reasons if str(item).strip()) or "orchestration state could not be verified"
    raw_evidence = registry.get("evidence", {}) if isinstance(registry.get("evidence"), Mapping) else {}
    recovered_evidence: dict[str, Any] = {}
    for key, item in raw_evidence.items():
        if isinstance(key, str) and key.strip() and isinstance(item, Mapping) and item.get("evidence_id") == key:
            allowed = {name: deepcopy(item[name]) for name in ("evidence_id", "kind", "outcome", "sha256", "version") if name in item}
            if isinstance(allowed.get("kind"),str) and isinstance(allowed.get("outcome"),str) and allowed.get("kind") in {"review", "source", "test", "task", "return", "reservation", "terminal", "decision"} and allowed.get("outcome") in {"accepted", "rejected", "verified", "failed", "unknown"}:
                recovered_evidence[key] = allowed

    raw_teammates = registry.get("teammates", {}) if isinstance(registry.get("teammates"), Mapping) else {}
    recovered_teammates: dict[str, Any] = {}
    for key, item in raw_teammates.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(item, Mapping) or item.get("logical_teammate_id") != key:
            continue
        trust = item.get("trust", {}) if isinstance(item.get("trust"), Mapping) else {}
        trust_refs = [ref for ref in _safe_refs(trust.get("evidence_refs"), recovered_evidence) if recovered_evidence[ref].get("kind") == "review"]
        successful = sum(recovered_evidence[ref].get("outcome") == "accepted" for ref in trust_refs)
        failed = sum(recovered_evidence[ref].get("outcome") in {"rejected", "failed"} for ref in trust_refs)
        capability = item.get("capability_class") if isinstance(item.get("capability_class"),str) and item.get("capability_class") in {"economy", "standard", "reasoning", "frontier"} else "standard"
        continuity = item.get("continuity_mode") if isinstance(item.get("continuity_mode"),str) and item.get("continuity_mode") in {"resume", "rehydrate", "fresh"} else "rehydrate"
        recovered_teammates[key] = {
            "logical_teammate_id": key,
            "role": item.get("role") if isinstance(item.get("role"), str) and item.get("role").strip() else "recovered",
            "capability_class": capability,
            "continuity_mode": continuity,
            "native_handle": None,
            "working_set_evidence_refs": _safe_refs(item.get("working_set_evidence_refs"), recovered_evidence),
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
        reservation = raw_reservations.get(reservation_id) if isinstance(reservation_id,str) else None
        if not isinstance(teammate_id,str) or teammate_id not in recovered_teammates or not isinstance(reservation_id, str) or not reservation_id.strip() or not isinstance(reservation, Mapping):
            continue
        if reservation.get("reservation_id") != reservation_id or reservation.get("assignment_id") != assignment_id or reservation.get("logical_teammate_id") != teammate_id:
            continue
        cleaned = {name: deepcopy(reservation.get(name)) for name in reservation_fields}
        cleaned["state"] = "unknown"
        cleaned["terminal_evidence"] = None
        cleaned["evidence_refs"] = _safe_refs(reservation.get("evidence_refs"), recovered_evidence)
        if any(not _is_non_negative(cleaned.get(name)) for name in ("initial_reserved", "active_reserved", "funded_consumed", "funded_reservation_overrun", "unfunded_consumed", "released_unused")):
            continue
        recovered_reservations[reservation_id] = cleaned
        recovered_assignments[assignment_id] = {
            "assignment_id": assignment_id,
            "logical_teammate_id": teammate_id,
            "reservation_id": reservation_id,
            "capability_class": recovered_teammates[teammate_id]["capability_class"],
            "state": "unknown",
            "evidence_refs": _safe_refs(assignment.get("evidence_refs"), recovered_evidence),
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
    unit = ledger.get("unit") if isinstance(ledger.get("unit"),str) and ledger.get("unit") in {"credits", "tokens", "seconds", "currency", "tool_calls", "model_calls"} else "model_calls"
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
    input_errors = []
    if not isinstance(registry,Mapping): input_errors.append("$.registry: expected an object")
    if not isinstance(ledger,Mapping): input_errors.append("$.ledger: expected an object")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        input_errors.append("$.evidence: must be a sequence of mappings")
    if input_errors:
        return _unknown_recovery(registry if isinstance(registry,Mapping) else {},ledger if isinstance(ledger,Mapping) else {},input_errors)
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
            if not isinstance(event_type,str):
                raise ValueError("$.evidence.type: must be a string")
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


def prepare_dispatch(registry: Mapping[str, Any], ledger: Mapping[str, Any], worker_event: Mapping[str, Any]) -> tuple[dict, dict]:
    """Protect planning obligations with real holds before atomic worker dispatch.

    This is the supported coordinator-owned path; raw ledger calls do not protect
    reserves. Existing funded holds or consumed obligation capacity count once.
    """
    errors = validate_orchestration_state(registry,ledger)
    if errors:
        raise ValueError("invalid dispatch state: " + "; ".join(errors))
    if not ledger.get("balances_known") or ledger.get("status") == "blocked":
        raise ValueError("dispatch blocked: balances are unknown or state is blocked")
    if not isinstance(worker_event,Mapping):
        raise ValueError("worker event must be an object")
    _validate_event(worker_event)
    if worker_event.get("type") not in {"start","retry_start"} or worker_event.get("kind","worker") != "worker":
        raise ValueError("dispatch requires a worker start or retry_start event")
    r,l=deepcopy(dict(registry)),deepcopy(dict(ledger))
    owner="obligation:" + _required_text(registry.get("coordinator_id"),"$.registry.coordinator_id")
    if owner in r["teammates"] and r["teammates"][owner].get("role") != "protected-obligations":
        raise ValueError("protected obligation owner conflicts with existing teammate")
    missing=[]
    for requirement,kind in (("coordinator","coordinator"),("integration","integration"),("mandatory_review","review")):
        required=_number(l.get("reserves",{}).get(requirement),"$.ledger.reserves."+requirement)
        funded=sum(item["active_reserved"]+item["funded_consumed"] for item in l["reservations"].values() if item.get("logical_teammate_id")==owner and item.get("kind")==kind)
        if required > funded: missing.append((kind,required-funded))
    amount=_number(worker_event.get("amount"),"$.worker_event.amount")
    if amount + sum(amount for _,amount in missing) > l["available"]:
        raise ValueError("insufficient capacity after protected coordinator/integration/review obligations")
    if missing:
        r["teammates"].setdefault(owner,{"logical_teammate_id":owner,"role":"protected-obligations","capability_class":"standard","continuity_mode":"fresh","native_handle":None,"working_set_evidence_refs":[],"trust":{"successful_reviews":0,"failed_reviews":0,"evidence_refs":[]},"active_assignment_ids":[]})
    events=[]
    for kind,amount in missing:
        identity=worker_event["event_id"]+":protected:"+kind
        events.append({"event_id":identity,"transaction_id":identity,"type":"start","reservation_id":identity,"assignment_id":identity,"logical_teammate_id":owner,"kind":kind,"amount":amount,"attempt":1,"evidence_refs":[]})
    events.append(dict(worker_event))
    recovered_r,recovered_l,notices=recover_state(r,l,events)
    if notices or recovered_l.get("status")=="blocked":
        raise ValueError("dispatch failed before mutation: " + "; ".join(notices))
    errors=validate_orchestration_state(recovered_r,recovered_l)
    if errors: raise ValueError("dispatch produced invalid state: "+"; ".join(errors))
    return recovered_r,recovered_l
