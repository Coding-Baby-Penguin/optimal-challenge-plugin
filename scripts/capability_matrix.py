from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


SUPPORT_LEVELS = frozenset({"observed", "unsupported"})
POLICY_SUPPORT_LEVELS = frozenset({"policy-only", "unsupported"})
FALLBACKS = frozenset({"inline", "rehydrate", "advisory", "blocked"})


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


def _policy_errors(surface: str, policy: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(surface, str) or not surface.strip():
        errors.append("surface must be a non-empty string")
    if policy.get("surface_id") != surface:
        errors.append("policy surface_id must match the active surface")
    for field in ("capability", "detector", "evidence_ref", "verified_version"):
        if not isinstance(policy.get(field), str) or not policy[field].strip():
            errors.append(f"policy {field} must be a non-empty string")
    if policy.get("support_level") not in POLICY_SUPPORT_LEVELS:
        errors.append("policy support_level must be policy-only or unsupported")
    if policy.get("provenance") != "policy_declaration":
        errors.append("policy provenance must be policy_declaration")
    if policy.get("required_fallback") not in FALLBACKS:
        errors.append("policy required_fallback is invalid")
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
    expiry: Any = None,
) -> dict[str, Any]:
    return {
        "surface": surface,
        "capability": policy["capability"],
        "support_level": "unknown",
        "evidence_source": source,
        "evidence_ref": None,
        "verified_version": policy["verified_version"],
        "expires_at": expiry if isinstance(expiry, str) else policy["expires_at"],
        "required_fallback": policy["required_fallback"],
        "reason": reason,
    }


def _resolve_evidence(
    surface: str,
    record: Mapping[str, Any],
    policy: Mapping[str, Any],
    expected_provenance: str,
    now: datetime,
) -> dict[str, Any]:
    source = expected_provenance
    fallback = policy["required_fallback"]

    if record.get("surface_id") != surface:
        return _unknown(surface, policy, source, "wrong surface in capability evidence", record.get("expires_at"))
    if record.get("verified_version") != policy["verified_version"]:
        return _unknown(surface, policy, source, "wrong version in capability evidence", record.get("expires_at"))
    if record.get("capability") != policy["capability"]:
        return _unknown(surface, policy, source, "wrong capability in evidence", record.get("expires_at"))
    if record.get("provenance") != expected_provenance:
        return _unknown(surface, policy, source, "missing provenance or untrusted provenance", record.get("expires_at"))
    if record.get("detector_status") != "success":
        return _unknown(surface, policy, source, "detector failure or missing detector status", record.get("expires_at"))
    if record.get("conflicting") is not False:
        return _unknown(surface, policy, source, "conflicting or unclassified observations", record.get("expires_at"))

    for field in ("detector", "evidence_ref"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            return _unknown(surface, policy, source, f"missing {field}", record.get("expires_at"))
    if record.get("support_level") not in SUPPORT_LEVELS:
        return _unknown(surface, policy, source, "invalid support level", record.get("expires_at"))
    if record.get("required_fallback") != fallback:
        return _unknown(surface, policy, source, "fallback conflicts with policy", record.get("expires_at"))

    verified_at = _timestamp(record.get("verified_at"))
    expires_at = _timestamp(record.get("expires_at"))
    if verified_at is None or verified_at > now:
        return _unknown(surface, policy, source, "invalid or future verification timestamp", record.get("expires_at"))
    if expires_at is None or expires_at <= now:
        return _unknown(surface, policy, source, "capability evidence is expired", record.get("expires_at"))
    if expires_at <= verified_at:
        return _unknown(surface, policy, source, "expiry does not follow verification", record.get("expires_at"))

    return {
        "surface": surface,
        "capability": policy["capability"],
        "support_level": record["support_level"],
        "evidence_source": source,
        "evidence_ref": record["evidence_ref"],
        "verified_version": record["verified_version"],
        "expires_at": record["expires_at"],
        "required_fallback": fallback,
        "reason": "matching, current evidence",
    }


def resolve_capability(
    surface: str,
    live: Mapping[str, Any] | None,
    acceptance: Mapping[str, Any] | None,
    policy: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Resolve one capability without trusting stale or mismatched evidence.

    A present but invalid higher-priority record fails closed instead of being
    hidden by lower-priority evidence.
    """

    if not isinstance(policy, Mapping):
        raise ValueError("policy must be a mapping")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    checked_at = now.astimezone(timezone.utc)
    errors = _policy_errors(surface, policy)
    if errors:
        raise ValueError("Invalid capability policy: " + "; ".join(errors))

    if live is not None:
        if not isinstance(live, Mapping):
            return _unknown(surface, policy, "live_detection", "live evidence is not a mapping")
        return _resolve_evidence(surface, live, policy, "live_detection", checked_at)

    if acceptance is not None:
        if not isinstance(acceptance, Mapping):
            return _unknown(surface, policy, "acceptance_run", "acceptance evidence is not a mapping")
        return _resolve_evidence(surface, acceptance, policy, "acceptance_run", checked_at)

    verified_at = _timestamp(policy["verified_at"])
    expires_at = _timestamp(policy["expires_at"])
    if verified_at is None or verified_at > checked_at:
        return _unknown(surface, policy, "policy_declaration", "invalid or future policy timestamp")
    if expires_at is None or expires_at <= checked_at:
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
        "reason": "no higher-priority evidence is available",
    }
