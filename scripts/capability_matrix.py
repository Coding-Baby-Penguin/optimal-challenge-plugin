"""Compatibility facade for capability proofs, issuance and resolution."""
from __future__ import annotations
import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.optimal_challenge.capability_evidence import (
    CAPABILITY_FALLBACKS, API_SDK_SURFACES, EVIDENCE_SUPPORT_LEVELS,
    POLICY_SUPPORT_LEVELS, TRUSTED_LIVE_ADAPTERS, TRUSTED_ACCEPTANCE_ADAPTER,
    PAUSE_CANCEL_PRIMITIVES, ENFORCEMENT_STOP_PRIMITIVES,
    NativeResumeProof, PauseCancelProof, UsageCounterProof, EnforcementProof,
    PersistencePrivacyProof, ParallelExecutionProof, TracingProof,
    CapabilityProof, TrustedCapabilityEvidence, DISPLAY_CAPABILITIES,
    CAPABILITY_DOCUMENT_SURFACES, issue_adapter_evidence,
)
from scripts.optimal_challenge.capability_resolution import resolve_capability, validate_capability_contracts
__all__ = [
    "CAPABILITY_FALLBACKS", "API_SDK_SURFACES", "EVIDENCE_SUPPORT_LEVELS",
    "POLICY_SUPPORT_LEVELS", "TRUSTED_LIVE_ADAPTERS", "TRUSTED_ACCEPTANCE_ADAPTER",
    "PAUSE_CANCEL_PRIMITIVES", "ENFORCEMENT_STOP_PRIMITIVES",
    "NativeResumeProof", "PauseCancelProof", "UsageCounterProof", "EnforcementProof",
    "PersistencePrivacyProof", "ParallelExecutionProof", "TracingProof",
    "CapabilityProof", "TrustedCapabilityEvidence", "DISPLAY_CAPABILITIES",
    "CAPABILITY_DOCUMENT_SURFACES", "issue_adapter_evidence", "resolve_capability",
    "validate_capability_contracts",
]
