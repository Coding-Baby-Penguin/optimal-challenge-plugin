from __future__ import annotations

import hashlib
import json
import weakref
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
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


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


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


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _iso_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _non_user_reference(value: Any, prefix: str | None = None) -> bool:
    if not isinstance(value, str) or not value.strip() or value.startswith("user:"):
        return False
    return prefix is None or value.startswith(prefix)


def _policy_errors(surface: str, policy: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    capability = policy.get("capability")
    if not _is_text(surface):
        errors.append("surface must be a non-empty string")
    policy_surface = policy.get("surface_id")
    if not _is_text(policy_surface):
        errors.append("policy surface_id must be a non-empty string")
    elif policy_surface != surface:
        errors.append("policy surface_id must match the active surface")
    if not _is_text(capability):
        errors.append("policy capability must be a non-empty string")
    elif capability not in CAPABILITY_FALLBACKS:
        errors.append("policy capability is unsupported")
    for field in ("detector", "evidence_ref", "verified_version"):
        if not _is_text(policy.get(field)):
            errors.append(f"policy {field} must be a non-empty string")
    support_level = policy.get("support_level")
    if not _is_text(support_level) or support_level not in POLICY_SUPPORT_LEVELS:
        errors.append("policy support_level must be policy-only or unsupported")
    provenance = policy.get("provenance")
    if not _is_text(provenance) or provenance != "policy_declaration":
        errors.append("policy provenance must be policy_declaration")
    if _is_text(capability) and capability in CAPABILITY_FALLBACKS:
        fallback = policy.get("required_fallback")
        if not _is_text(fallback) or fallback != CAPABILITY_FALLBACKS[capability]:
            errors.append("policy required_fallback does not match the capability contract")
    needs_measurement = _is_text(capability) and capability in {
        "usage_measurement",
        "local_enforcement",
        "provider_enforcement",
    }
    measurement_surface = policy.get("measurement_surface")
    if needs_measurement and not _is_text(measurement_surface):
        errors.append("policy measurement_surface is required for measured capabilities")
    if not needs_measurement and measurement_surface is not None:
        errors.append("policy measurement_surface must be null for unmeasured capabilities")
    verified_at = _timestamp(policy.get("verified_at"))
    expires_at = _timestamp(policy.get("expires_at"))
    if verified_at is None:
        errors.append("policy verified_at must be an aware ISO-8601 timestamp")
    if expires_at is None:
        errors.append("policy expires_at must be an aware ISO-8601 timestamp")
    if verified_at is not None and expires_at is not None and expires_at <= verified_at:
        errors.append("policy expires_at must be later than verified_at")
    return errors


def _unknown(
    surface: str,
    policy: Mapping[str, Any],
    source: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "surface": surface,
        "capability": policy["capability"],
        "support_level": "unknown",
        "evidence_source": source,
        "evidence_ref": None,
        "verified_version": policy["verified_version"],
        "expires_at": policy["expires_at"],
        "required_fallback": policy["required_fallback"],
        "reason": reason,
    }


def _base_proof_error(
    proof: CapabilityProof,
    surface: str,
    version: str,
    label: str,
) -> str | None:
    if proof.surface_id != surface or proof.verified_version != version:
        return f"{label} proof does not match the exact surface/version"
    return None


def _usage_error(
    proof: UsageCounterProof,
    surface: str,
    version: str,
    measurement_surface: str,
) -> str | None:
    mismatch = _base_proof_error(proof, surface, version, "usage")
    if mismatch:
        return mismatch
    if proof.observed is not True:
        return "usage proof requires an observed counter"
    if proof.measurement_surface != measurement_surface:
        return "usage proof has the wrong measurement surface"
    if not _non_user_reference(proof.counter_id, "counter:"):
        return "usage proof requires an adapter counter reference"
    return None


def _proof_error(evidence: TrustedCapabilityEvidence, policy: Mapping[str, Any]) -> str | None:
    capability = evidence.capability
    proof = evidence.proof
    surface = evidence.surface_id
    version = evidence.verified_version

    if capability == "native_resume":
        if not isinstance(proof, NativeResumeProof):
            return "native resume requires NativeResumeProof"
        mismatch = _base_proof_error(proof, surface, version, "native resume")
        if mismatch:
            return mismatch
        if not _non_user_reference(proof.native_handle_ref, "handle:") or not _non_user_reference(
            proof.continuity_evidence_ref, "continuity:"
        ):
            return "native resume requires a native handle and continuity proof"
        return None

    if capability == "pause_cancel":
        if not isinstance(proof, PauseCancelProof):
            return "pause/cancel requires PauseCancelProof"
        mismatch = _base_proof_error(proof, surface, version, "pause/cancel")
        if mismatch:
            return mismatch
        allowed = PAUSE_CANCEL_PRIMITIVES.get(surface, frozenset())
        if proof.stop_primitive not in allowed:
            return "pause/cancel stop primitive is not allowlisted for this surface"
        return None

    if capability == "usage_measurement":
        if not isinstance(proof, UsageCounterProof):
            return "usage measurement requires UsageCounterProof"
        return _usage_error(proof, surface, version, policy["measurement_surface"])

    if capability in {"local_enforcement", "provider_enforcement"}:
        if not isinstance(proof, EnforcementProof):
            return "enforcement requires EnforcementProof"
        mismatch = _base_proof_error(proof, surface, version, "enforcement")
        if mismatch:
            return mismatch
        required_scope = capability.removesuffix("_enforcement")
        allowed = ENFORCEMENT_STOP_PRIMITIVES.get((surface, required_scope), frozenset())
        if proof.primitive_scope != required_scope or proof.stop_primitive not in allowed:
            return "enforcement stop primitive is not allowlisted for this surface and scope"
        usage_error = _usage_error(
            proof.usage_counter,
            surface,
            version,
            policy["measurement_surface"],
        )
        if usage_error:
            return f"enforcement {usage_error}"
        return None

    if capability == "persistence_privacy":
        if not isinstance(proof, PersistencePrivacyProof):
            return "persistence/privacy requires PersistencePrivacyProof"
        mismatch = _base_proof_error(proof, surface, version, "persistence/privacy")
        if mismatch:
            return mismatch
        if not _non_user_reference(proof.storage_boundary) or not _non_user_reference(
            proof.privacy_control_ref, "privacy:"
        ):
            return "persistence/privacy proof is incomplete"
        return None

    if capability == "parallel_execution":
        if not isinstance(proof, ParallelExecutionProof):
            return "parallel execution requires ParallelExecutionProof"
        mismatch = _base_proof_error(proof, surface, version, "parallel execution")
        if mismatch:
            return mismatch
        if (
            not _non_user_reference(proof.slot_detector_ref, "slots:")
            or not isinstance(proof.detected_max, int)
            or isinstance(proof.detected_max, bool)
            or proof.detected_max < 0
        ):
            return "parallel execution proof is incomplete"
        return None

    if capability == "tracing":
        if not isinstance(proof, TracingProof):
            return "tracing requires TracingProof"
        mismatch = _base_proof_error(proof, surface, version, "tracing")
        if mismatch:
            return mismatch
        if not _non_user_reference(proof.trace_source, "trace:"):
            return "tracing proof is incomplete"
        return None

    return "capability has no closed proof contract"


def _evidence_error(
    evidence: TrustedCapabilityEvidence,
    surface: str,
    policy: Mapping[str, Any],
    expected_provenance: str,
    now: datetime,
) -> str | None:
    if evidence._attestation is not _PROCESS_ADAPTER_ATTESTATION:
        return "adapter attestation is absent or forged"
    shape_error = _evidence_shape_error(evidence)
    if shape_error:
        return shape_error
    issuance_error = _issuance_error(evidence)
    if issuance_error:
        return issuance_error
    if evidence.surface_id != surface:
        return "wrong surface in capability evidence"
    if policy["verified_version"] == "unavailable":
        return "policy verified version is unavailable and cannot match runtime evidence"
    if evidence.verified_version != policy["verified_version"]:
        return "wrong version in capability evidence"
    if evidence.capability != policy["capability"]:
        return "wrong capability in evidence"
    if evidence.provenance != expected_provenance:
        return "missing provenance or untrusted provenance"
    detector_prefix = "adapter:" if expected_provenance == "live_detection" else "acceptance:"
    evidence_prefix = "live:" if expected_provenance == "live_detection" else "acceptance:"
    if not _non_user_reference(evidence.detector_id, detector_prefix):
        return "detector_id is not from the required trusted namespace"
    if not _non_user_reference(evidence.evidence_ref, evidence_prefix):
        return "evidence_ref is not from the required trusted namespace"
    if evidence.detector_status != "success":
        return "detector failure or missing detector status"
    if evidence.conflicting is not False:
        return "conflicting or unclassified observations"
    if evidence.executable_adapter is not True:
        return "executable adapter evidence is required"
    if evidence.support_level not in EVIDENCE_SUPPORT_LEVELS:
        return "invalid support level"
    if evidence.required_fallback != policy["required_fallback"]:
        return "fallback conflicts with policy"
    if (
        not isinstance(evidence.verified_at, datetime)
        or evidence.verified_at.tzinfo is None
        or evidence.verified_at.utcoffset() is None
        or evidence.verified_at.astimezone(timezone.utc) > now
    ):
        return "invalid or future verification timestamp"
    if (
        not isinstance(evidence.expires_at, datetime)
        or evidence.expires_at.tzinfo is None
        or evidence.expires_at.utcoffset() is None
        or evidence.expires_at.astimezone(timezone.utc) <= now
    ):
        return "capability evidence is expired"
    if evidence.expires_at <= evidence.verified_at:
        return "expiry does not follow verification"
    return _proof_error(evidence, policy)


def _resolved(
    surface: str,
    evidence: TrustedCapabilityEvidence,
    policy: Mapping[str, Any],
    source: str,
) -> dict[str, Any]:
    return {
        "surface": surface,
        "capability": policy["capability"],
        "support_level": evidence.support_level,
        "evidence_source": source,
        "evidence_ref": evidence.evidence_ref,
        "verified_version": evidence.verified_version,
        "expires_at": _iso_timestamp(evidence.expires_at),
        "required_fallback": policy["required_fallback"],
        "reason": "matching, current adapter evidence",
    }


def _policy_result(
    surface: str,
    policy: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    verified_at = _timestamp(policy["verified_at"])
    expires_at = _timestamp(policy["expires_at"])
    if verified_at is None or verified_at > now:
        return _unknown(surface, policy, "policy_declaration", "invalid or future policy timestamp")
    if expires_at is None or expires_at <= now:
        return _unknown(surface, policy, "policy_declaration", "policy declaration is expired")
    return {
        "surface": surface,
        "capability": policy["capability"],
        "support_level": policy["support_level"],
        "evidence_source": "policy_declaration",
        "evidence_ref": policy["evidence_ref"],
        "verified_version": policy["verified_version"],
        "expires_at": policy["expires_at"],
        "required_fallback": policy["required_fallback"],
        "reason": "no runtime capability claim was made",
    }


def resolve_capability(
    surface: str,
    live: TrustedCapabilityEvidence | Mapping[str, Any] | None,
    acceptance: TrustedCapabilityEvidence | Mapping[str, Any] | None,
    policy: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Resolve one capability from closed, adapter-produced evidence."""

    if not isinstance(policy, Mapping):
        raise ValueError("policy must be a mapping")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    checked_at = now.astimezone(timezone.utc)
    errors = _policy_errors(surface, policy)
    if errors:
        raise ValueError("Invalid capability policy: " + "; ".join(errors))

    if surface in API_SDK_SURFACES:
        if live is None and acceptance is None:
            return _policy_result(surface, policy, checked_at)
        if not isinstance(live, TrustedCapabilityEvidence):
            return _unknown(
                surface,
                policy,
                "live_detection",
                "API/SDK support requires trusted executable live adapter evidence; adapter attestation unavailable",
            )
        live_error = _evidence_error(live, surface, policy, "live_detection", checked_at)
        if live_error:
            return _unknown(surface, policy, "live_detection", live_error)
        if not isinstance(acceptance, TrustedCapabilityEvidence):
            return _unknown(
                surface,
                policy,
                "acceptance_run",
                "API/SDK support requires a current matching acceptance run; adapter attestation unavailable",
            )
        acceptance_error = _evidence_error(
            acceptance,
            surface,
            policy,
            "acceptance_run",
            checked_at,
        )
        if acceptance_error:
            return _unknown(
                surface,
                policy,
                "acceptance_run",
                f"acceptance evidence invalid: {acceptance_error}",
            )
        if live.support_level != acceptance.support_level or live.proof != acceptance.proof:
            return _unknown(
                surface,
                policy,
                "live_detection+acceptance_run",
                "acceptance evidence does not match live adapter evidence",
            )
        result = _resolved(surface, live, policy, "live_detection+acceptance_run")
        result["acceptance_evidence_ref"] = acceptance.evidence_ref
        result["reason"] = "matching executable live evidence and current acceptance run"
        return result

    if live is not None:
        if not isinstance(live, TrustedCapabilityEvidence):
            return _unknown(
                surface,
                policy,
                "live_detection",
                "live claim is not closed trusted adapter evidence; adapter attestation unavailable",
            )
        error = _evidence_error(live, surface, policy, "live_detection", checked_at)
        if error:
            return _unknown(surface, policy, "live_detection", error)
        return _resolved(surface, live, policy, "live_detection")

    if acceptance is not None:
        if not isinstance(acceptance, TrustedCapabilityEvidence):
            return _unknown(
                surface,
                policy,
                "acceptance_run",
                "acceptance claim is not closed trusted adapter evidence; adapter attestation unavailable",
            )
        error = _evidence_error(acceptance, surface, policy, "acceptance_run", checked_at)
        if error:
            return _unknown(surface, policy, "acceptance_run", error)
        return _resolved(surface, acceptance, policy, "acceptance_run")

    return _policy_result(surface, policy, checked_at)
