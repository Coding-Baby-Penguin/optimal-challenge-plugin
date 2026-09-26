from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
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
    if not isinstance(surface, str) or not surface.strip():
        errors.append("surface must be a non-empty string")
    if policy.get("surface_id") != surface:
        errors.append("policy surface_id must match the active surface")
    if capability not in CAPABILITY_FALLBACKS:
        errors.append("policy capability is unsupported")
    for field in ("detector", "evidence_ref", "verified_version"):
        if not isinstance(policy.get(field), str) or not policy[field].strip():
            errors.append(f"policy {field} must be a non-empty string")
    if policy.get("support_level") not in POLICY_SUPPORT_LEVELS:
        errors.append("policy support_level must be policy-only or unsupported")
    if policy.get("provenance") != "policy_declaration":
        errors.append("policy provenance must be policy_declaration")
    if capability in CAPABILITY_FALLBACKS:
        if policy.get("required_fallback") != CAPABILITY_FALLBACKS[capability]:
            errors.append("policy required_fallback does not match the capability contract")
    needs_measurement = capability in {
        "usage_measurement",
        "local_enforcement",
        "provider_enforcement",
    }
    measurement_surface = policy.get("measurement_surface")
    if needs_measurement and (not isinstance(measurement_surface, str) or not measurement_surface.strip()):
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
        if not _non_user_reference(proof.stop_primitive):
            return "pause/cancel requires an adapter stop primitive"
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
        if proof.primitive_scope != required_scope or not _non_user_reference(proof.stop_primitive):
            return "enforcement proof lacks the matching local/provider stop primitive"
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
                "API/SDK support requires trusted executable live adapter evidence",
            )
        live_error = _evidence_error(live, surface, policy, "live_detection", checked_at)
        if live_error:
            return _unknown(surface, policy, "live_detection", live_error)
        if not isinstance(acceptance, TrustedCapabilityEvidence):
            return _unknown(
                surface,
                policy,
                "acceptance_run",
                "API/SDK support requires a current matching acceptance run",
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
                "live claim is not closed trusted adapter evidence",
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
                "acceptance claim is not closed trusted adapter evidence",
            )
        error = _evidence_error(acceptance, surface, policy, "acceptance_run", checked_at)
        if error:
            return _unknown(surface, policy, "acceptance_run", error)
        return _resolved(surface, acceptance, policy, "acceptance_run")

    return _policy_result(surface, policy, checked_at)
