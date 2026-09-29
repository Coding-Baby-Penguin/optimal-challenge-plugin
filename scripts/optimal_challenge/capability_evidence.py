"""Typed capability evidence issuance and process-local attestation."""
from __future__ import annotations

import hashlib
import json
import weakref
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, TypeAlias


CAPABILITY_FALLBACKS = {
    "native_resume": "rehydrate",
    "pause_cancel": "blocked",
    "usage_measurement": "advisory",
    "local_enforcement": "advisory",
    "provider_enforcement": "advisory",
    "persistence_privacy": "blocked",
    "parallel_execution": "inline",
    "tracing": "advisory",
}
API_SDK_SURFACES = frozenset({"openai-api-agents", "anthropic-api-agent-sdk"})
EVIDENCE_SUPPORT_LEVELS = frozenset({"observed", "unsupported"})
POLICY_SUPPORT_LEVELS = frozenset({"policy-only", "unsupported"})
TRUSTED_LIVE_ADAPTERS = {
    "codex-local": "codex-host",
    "openai-api-agents": "openai-agents-adapter",
    "claude-code-local": "claude-code-host",
    "anthropic-api-agent-sdk": "anthropic-agent-adapter",
}
TRUSTED_ACCEPTANCE_ADAPTER = "capability-acceptance-harness"
PAUSE_CANCEL_PRIMITIVES = {
    "codex-local": frozenset({"interrupt_task"}),
    "openai-api-agents": frozenset({"cancel_response"}),
    "claude-code-local": frozenset({"stop_task"}),
    "anthropic-api-agent-sdk": frozenset({"cancel_request"}),
}
ENFORCEMENT_STOP_PRIMITIVES = {
    ("codex-local", "local"): frozenset({"codex_local_budget_gate"}),
    ("codex-local", "provider"): frozenset({"codex_provider_stop"}),
    ("openai-api-agents", "local"): frozenset({"openai_local_budget_gate"}),
    ("openai-api-agents", "provider"): frozenset({"openai_provider_limit"}),
    ("claude-code-local", "local"): frozenset({"claude_local_budget_gate"}),
    ("claude-code-local", "provider"): frozenset({"claude_provider_stop"}),
    ("anthropic-api-agent-sdk", "local"): frozenset({"anthropic_local_budget_gate"}),
    ("anthropic-api-agent-sdk", "provider"): frozenset({"anthropic_provider_limit"}),
}
_PROCESS_ADAPTER_ATTESTATION = object()


@dataclass(frozen=True, slots=True)
class NativeResumeProof:
    surface_id: str
    verified_version: str
    native_handle_ref: str
    continuity_evidence_ref: str


@dataclass(frozen=True, slots=True)
class PauseCancelProof:
    surface_id: str
    verified_version: str
    stop_primitive: str


@dataclass(frozen=True, slots=True)
class UsageCounterProof:
    surface_id: str
    verified_version: str
    measurement_surface: str
    counter_id: str
    observed: bool


@dataclass(frozen=True, slots=True)
class EnforcementProof:
    surface_id: str
    verified_version: str
    usage_counter: UsageCounterProof
    primitive_scope: str
    stop_primitive: str


@dataclass(frozen=True, slots=True)
class PersistencePrivacyProof:
    surface_id: str
    verified_version: str
    storage_boundary: str
    privacy_control_ref: str


@dataclass(frozen=True, slots=True)
class ParallelExecutionProof:
    surface_id: str
    verified_version: str
    slot_detector_ref: str
    detected_max: int


@dataclass(frozen=True, slots=True)
class TracingProof:
    surface_id: str
    verified_version: str
    trace_source: str


CapabilityProof: TypeAlias = (
    NativeResumeProof
    | PauseCancelProof
    | UsageCounterProof
    | EnforcementProof
    | PersistencePrivacyProof
    | ParallelExecutionProof
    | TracingProof
)


@dataclass(frozen=True, slots=True, weakref_slot=True)
class TrustedCapabilityEvidence:
    """Closed adapter output; configuration mappings never satisfy this contract."""

    surface_id: str
    capability: str
    support_level: str
    detector_id: str
    evidence_ref: str
    verified_version: str
    verified_at: datetime
    expires_at: datetime
    provenance: str
    detector_status: str
    conflicting: bool
    executable_adapter: bool
    required_fallback: str
    proof: CapabilityProof
    _attestation: object | None = field(default=None, repr=False, compare=False)


_PROOF_TYPES = (
    NativeResumeProof,
    PauseCancelProof,
    UsageCounterProof,
    EnforcementProof,
    PersistencePrivacyProof,
    ParallelExecutionProof,
    TracingProof,
)
_ISSUED_EVIDENCE: dict[
    int,
    tuple[weakref.ReferenceType[TrustedCapabilityEvidence], str],
] = {}

DISPLAY_CAPABILITIES = {
    "native resume": "native_resume",
    "pause/cancel": "pause_cancel",
    "usage measurement": "usage_measurement",
    "local enforcement": "local_enforcement",
    "provider enforcement": "provider_enforcement",
    "persistence/privacy": "persistence_privacy",
    "parallel execution": "parallel_execution",
    "tracing": "tracing",
}
CAPABILITY_DOCUMENT_SURFACES = {
    "platform-codex.md": frozenset({"codex-local", "openai-api-agents"}),
    "platform-claude.md": frozenset({"claude-code-local", "anthropic-api-agent-sdk"}),
}


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _iso_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _proof_shape_error(proof: Any) -> str | None:
    if not isinstance(proof, _PROOF_TYPES):
        return "malformed proof: unrecognized proof type"
    for field_name in ("surface_id", "verified_version"):
        if not _is_text(getattr(proof, field_name)):
            return f"malformed proof: {field_name} must be a non-empty string"
    if isinstance(proof, NativeResumeProof):
        fields = ("native_handle_ref", "continuity_evidence_ref")
    elif isinstance(proof, PauseCancelProof):
        fields = ("stop_primitive",)
    elif isinstance(proof, UsageCounterProof):
        fields = ("measurement_surface", "counter_id")
        if type(proof.observed) is not bool:
            return "malformed proof: observed must be a boolean"
    elif isinstance(proof, EnforcementProof):
        fields = ("primitive_scope", "stop_primitive")
        if not isinstance(proof.usage_counter, UsageCounterProof):
            return "malformed proof: usage_counter must be UsageCounterProof"
        nested_error = _proof_shape_error(proof.usage_counter)
        if nested_error:
            return nested_error
    elif isinstance(proof, PersistencePrivacyProof):
        fields = ("storage_boundary", "privacy_control_ref")
    elif isinstance(proof, ParallelExecutionProof):
        fields = ("slot_detector_ref",)
        if (
            not isinstance(proof.detected_max, int)
            or isinstance(proof.detected_max, bool)
        ):
            return "malformed proof: detected_max must be an integer"
    else:
        fields = ("trace_source",)
    for field_name in fields:
        if not _is_text(getattr(proof, field_name)):
            return f"malformed proof: {field_name} must be a non-empty string"
    return None


def _evidence_shape_error(evidence: TrustedCapabilityEvidence) -> str | None:
    for field_name in (
        "surface_id",
        "capability",
        "support_level",
        "detector_id",
        "evidence_ref",
        "verified_version",
        "provenance",
        "detector_status",
        "required_fallback",
    ):
        if not _is_text(getattr(evidence, field_name)):
            return f"malformed evidence: {field_name} must be a non-empty string"
    for field_name in ("verified_at", "expires_at"):
        value = getattr(evidence, field_name)
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            return f"malformed evidence: {field_name} must be a timezone-aware datetime"
    if type(evidence.conflicting) is not bool:
        return "malformed evidence: conflicting must be a boolean"
    if type(evidence.executable_adapter) is not bool:
        return "malformed evidence: executable_adapter must be a boolean"
    return _proof_shape_error(evidence.proof)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso_timestamp(value)
    if is_dataclass(value):
        return {
            "type": type(value).__name__,
            "fields": {
                item.name: _canonical_value(getattr(value, item.name))
                for item in fields(value)
                if item.name != "_attestation"
            },
        }
    return value


def _payload_digest(evidence: TrustedCapabilityEvidence) -> str:
    payload = {
        item.name: _canonical_value(getattr(evidence, item.name))
        for item in fields(evidence)
        if item.name != "_attestation"
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _register_issued_evidence(evidence: TrustedCapabilityEvidence) -> None:
    identity = id(evidence)

    def remove_if_current(reference: weakref.ReferenceType[TrustedCapabilityEvidence]) -> None:
        current = _ISSUED_EVIDENCE.get(identity)
        if current is not None and current[0] is reference:
            _ISSUED_EVIDENCE.pop(identity, None)

    reference = weakref.ref(evidence, remove_if_current)
    _ISSUED_EVIDENCE[identity] = (reference, _payload_digest(evidence))


def _issuance_error(evidence: TrustedCapabilityEvidence) -> str | None:
    issued = _ISSUED_EVIDENCE.get(id(evidence))
    if issued is None or issued[0]() is not evidence:
        return "adapter attestation is not bound to this exact issued object"
    try:
        current_digest = _payload_digest(evidence)
    except (TypeError, ValueError, OverflowError):
        return "adapter attestation payload is malformed"
    if current_digest != issued[1]:
        return "adapter attestation payload digest does not match issuance"
    return None


def issue_adapter_evidence(
    *,
    surface_id: str,
    capability: str,
    support_level: str,
    adapter_id: str,
    evidence_id: str,
    verified_version: str,
    verified_at: datetime,
    expires_at: datetime,
    provenance: str,
    required_fallback: str,
    proof: CapabilityProof,
) -> TrustedCapabilityEvidence:
    """Issue process-local evidence from a registered adapter identity.

    The identity token is intentionally not serializable. This is a process
    boundary, not a cryptographic signature or protection from hostile Python
    code running inside this module's process.
    """

    if not _is_text(surface_id) or surface_id not in TRUSTED_LIVE_ADAPTERS:
        raise ValueError("surface_id is not registered for capability evidence")
    if not _is_text(capability) or capability not in CAPABILITY_FALLBACKS:
        raise ValueError("capability is not registered")
    if not _is_text(provenance) or provenance not in {"live_detection", "acceptance_run"}:
        raise ValueError("provenance must be live_detection or acceptance_run")
    expected_adapter = (
        TRUSTED_LIVE_ADAPTERS[surface_id]
        if provenance == "live_detection"
        else TRUSTED_ACCEPTANCE_ADAPTER
    )
    if not _is_text(adapter_id) or adapter_id != expected_adapter:
        raise ValueError("adapter_id is not registered for this surface and provenance")
    if not _is_text(evidence_id) or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in evidence_id):
        raise ValueError("evidence_id must be a non-empty adapter identifier")
    if not _is_text(support_level) or support_level not in EVIDENCE_SUPPORT_LEVELS:
        raise ValueError("support_level must be observed or unsupported")
    if not _is_text(verified_version) or verified_version == "unavailable":
        raise ValueError("verified_version must be an exact runtime version")
    if required_fallback != CAPABILITY_FALLBACKS[capability]:
        raise ValueError("required_fallback does not match capability")
    shape_error = _proof_shape_error(proof)
    if shape_error:
        raise ValueError(shape_error)
    evidence = TrustedCapabilityEvidence(
        surface_id=surface_id,
        capability=capability,
        support_level=support_level,
        detector_id=(
            f"adapter:{adapter_id}"
            if provenance == "live_detection"
            else f"acceptance:{adapter_id}"
        ),
        evidence_ref=(
            f"live:{evidence_id}"
            if provenance == "live_detection"
            else f"acceptance:{evidence_id}"
        ),
        verified_version=verified_version,
        verified_at=verified_at,
        expires_at=expires_at,
        provenance=provenance,
        detector_status="success",
        conflicting=False,
        executable_adapter=True,
        required_fallback=required_fallback,
        proof=proof,
        _attestation=_PROCESS_ADAPTER_ATTESTATION,
    )
    evidence_error = _evidence_shape_error(evidence)
    if evidence_error:
        raise ValueError(evidence_error)
    _register_issued_evidence(evidence)
    return evidence
