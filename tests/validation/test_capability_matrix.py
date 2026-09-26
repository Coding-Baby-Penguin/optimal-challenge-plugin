from __future__ import annotations

import re
import unittest
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.capability_matrix import (
    EnforcementProof,
    NativeResumeProof,
    ParallelExecutionProof,
    PauseCancelProof,
    PersistencePrivacyProof,
    TracingProof,
    TrustedCapabilityEvidence,
    UsageCounterProof,
    issue_adapter_evidence,
    resolve_capability,
)


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
CAPABILITIES = {
    "native_resume": "rehydrate",
    "pause_cancel": "blocked",
    "usage_measurement": "advisory",
    "local_enforcement": "advisory",
    "provider_enforcement": "advisory",
    "persistence_privacy": "blocked",
    "parallel_execution": "inline",
    "tracing": "advisory",
}
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
API_SURFACES = ("openai-api-agents", "anthropic-api-agent-sdk")
ADAPTER_IDS = {
    "codex-local": "codex-host",
    "openai-api-agents": "openai-agents-adapter",
    "claude-code-local": "claude-code-host",
    "anthropic-api-agent-sdk": "anthropic-agent-adapter",
}
PAUSE_PRIMITIVES = {
    "codex-local": "interrupt_task",
    "openai-api-agents": "cancel_response",
    "claude-code-local": "stop_task",
    "anthropic-api-agent-sdk": "cancel_request",
}
ENFORCEMENT_PRIMITIVES = {
    ("codex-local", "local"): "codex_local_budget_gate",
    ("codex-local", "provider"): "codex_provider_stop",
    ("openai-api-agents", "local"): "openai_local_budget_gate",
    ("openai-api-agents", "provider"): "openai_provider_limit",
    ("claude-code-local", "local"): "claude_local_budget_gate",
    ("claude-code-local", "provider"): "claude_provider_stop",
    ("anthropic-api-agent-sdk", "local"): "anthropic_local_budget_gate",
    ("anthropic-api-agent-sdk", "provider"): "anthropic_provider_limit",
}


def policy(
    *,
    surface: str = "codex-local",
    version: str = "codex-host/1.2.3",
    capability: str = "native_resume",
    **overrides,
):
    record = {
        "surface_id": surface,
        "capability": capability,
        "support_level": "policy-only",
        "detector": "policy:host-capability-probe",
        "evidence_ref": f"policy:{surface}/{capability}",
        "verified_version": version,
        "verified_at": "2026-09-01T00:00:00Z",
        "expires_at": "2026-12-01T00:00:00Z",
        "provenance": "policy_declaration",
        "required_fallback": CAPABILITIES.get(capability, "rehydrate"),
        "measurement_surface": (
            "codex-product-usage"
            if capability in {"usage_measurement", "local_enforcement", "provider_enforcement"}
            else None
        ),
    }
    record.update(overrides)
    return record


def usage_counter(surface: str, version: str, **overrides) -> UsageCounterProof:
    values = {
        "surface_id": surface,
        "verified_version": version,
        "measurement_surface": "codex-product-usage",
        "counter_id": "counter:host-usage-17",
        "observed": True,
    }
    values.update(overrides)
    return UsageCounterProof(**values)


def proof_for(capability: str, surface: str, version: str):
    if capability == "native_resume":
        return NativeResumeProof(surface, version, "handle:task-17", "continuity:checkpoint-17")
    if capability == "pause_cancel":
        return PauseCancelProof(surface, version, PAUSE_PRIMITIVES[surface])
    if capability == "usage_measurement":
        return usage_counter(surface, version)
    if capability in {"local_enforcement", "provider_enforcement"}:
        scope = capability.removesuffix("_enforcement")
        return EnforcementProof(
            surface,
            version,
            usage_counter(surface, version),
            scope,
            ENFORCEMENT_PRIMITIVES[(surface, scope)],
        )
    if capability == "persistence_privacy":
        return PersistencePrivacyProof(surface, version, "workspace", "privacy:policy-17")
    if capability == "parallel_execution":
        return ParallelExecutionProof(surface, version, "slots:probe-17", 4)
    if capability == "tracing":
        return TracingProof(surface, version, "trace:host-17")
    raise AssertionError(capability)


def evidence(
    *,
    surface: str = "codex-local",
    version: str = "codex-host/1.2.3",
    capability: str = "native_resume",
    provenance: str = "live_detection",
    **overrides,
) -> TrustedCapabilityEvidence:
    issued = issue_adapter_evidence(
        surface_id=surface,
        capability=capability,
        support_level="observed",
        adapter_id=(
            ADAPTER_IDS[surface] if provenance == "live_detection" else "capability-acceptance-harness"
        ),
        evidence_id="run-17" if provenance == "live_detection" else "run-11",
        verified_version=version,
        verified_at=NOW - timedelta(minutes=30),
        expires_at=NOW + timedelta(hours=1),
        provenance=provenance,
        required_fallback=CAPABILITIES[capability],
        proof=proof_for(capability, surface, version),
    )
    return replace(issued, **overrides)


class CapabilityTrustBoundaryTests(unittest.TestCase):
    def test_matching_typed_live_evidence_outranks_acceptance_and_policy(self):
        result = resolve_capability(
            "codex-local",
            evidence(),
            evidence(provenance="acceptance_run"),
            policy(),
            NOW,
        )

        self.assertEqual(result["support_level"], "observed")
        self.assertEqual(result["evidence_source"], "live_detection")
        self.assertEqual(result["evidence_ref"], "live:run-17")
        self.assertEqual(result["required_fallback"], "rehydrate")

    def test_generic_or_user_authored_mappings_are_never_trusted(self):
        claim = {
            "surface_id": "codex-local",
            "capability": "native_resume",
            "support_level": "observed",
            "detector_id": "user:claim",
            "evidence_ref": "user:claim",
            "verified_version": "codex-host/1.2.3",
            "verified_at": (NOW - timedelta(minutes=1)).isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
            "provenance": "live_detection",
            "detector_status": "success",
            "conflicting": False,
            "executable_adapter": True,
        }

        result = resolve_capability("codex-local", claim, None, policy(), NOW)

        self.assertEqual(result["support_level"], "unknown")
        self.assertIn("trusted adapter evidence", result["reason"])

    def test_ordinary_construction_forged_attestation_and_serialization_cannot_recreate_trust(self):
        issued = evidence()
        fields = {
            "surface_id": issued.surface_id,
            "capability": issued.capability,
            "support_level": issued.support_level,
            "detector_id": issued.detector_id,
            "evidence_ref": issued.evidence_ref,
            "verified_version": issued.verified_version,
            "verified_at": issued.verified_at,
            "expires_at": issued.expires_at,
            "provenance": issued.provenance,
            "detector_status": issued.detector_status,
            "conflicting": issued.conflicting,
            "executable_adapter": issued.executable_adapter,
            "required_fallback": issued.required_fallback,
            "proof": issued.proof,
        }
        ordinary = TrustedCapabilityEvidence(**fields)
        forged = replace(issued, _attestation=object())
        serialized = asdict(issued)

        for claim in [ordinary, forged, serialized]:
            with self.subTest(claim=type(claim).__name__):
                result = resolve_capability("codex-local", claim, None, policy(), NOW)
                self.assertEqual(result["support_level"], "unknown")
                self.assertIn("attestation", result["reason"])

        legitimate = resolve_capability("codex-local", issued, None, policy(), NOW)
        self.assertEqual(legitimate["support_level"], "observed")

    def test_malformed_evidence_fields_resolve_unknown_without_exceptions(self):
        malformed = {
            "surface_id": [],
            "capability": {},
            "support_level": [],
            "detector_id": True,
            "evidence_ref": [],
            "verified_version": {},
            "verified_at": "2026-09-27T11:30:00Z",
            "expires_at": [],
            "provenance": {},
            "detector_status": [],
            "conflicting": "false",
            "executable_adapter": 1,
            "required_fallback": [],
            "proof": {},
        }
        for field, value in malformed.items():
            with self.subTest(field=field):
                result = resolve_capability(
                    "codex-local", replace(evidence(), **{field: value}), None, policy(), NOW
                )
                self.assertEqual(result["support_level"], "unknown")
                self.assertIn("malformed", result["reason"])

    def test_malformed_policy_fields_raise_controlled_value_error(self):
        malformed = {
            "surface_id": [],
            "capability": [],
            "support_level": {},
            "detector": True,
            "evidence_ref": [],
            "verified_version": {},
            "verified_at": [],
            "expires_at": True,
            "provenance": {},
            "required_fallback": [],
            "measurement_surface": [],
        }
        for field, value in malformed.items():
            with self.subTest(field=field):
                record = policy()
                record[field] = value
                with self.assertRaisesRegex(ValueError, "Invalid capability policy"):
                    resolve_capability("codex-local", None, None, record, NOW)

    def test_user_namespaces_are_rejected_even_on_typed_evidence(self):
        for field, value in [("detector_id", "user:claim"), ("evidence_ref", "user:claim")]:
            with self.subTest(field=field):
                result = resolve_capability(
                    "codex-local", replace(evidence(), **{field: value}), None, policy(), NOW
                )
                self.assertEqual(result["support_level"], "unknown")
                self.assertIn(field, result["reason"])

    def test_all_capabilities_require_their_exact_closed_proof_type(self):
        wrong_proof = NativeResumeProof(
            "codex-local", "codex-host/1.2.3", "handle:task-17", "continuity:checkpoint-17"
        )
        for capability in CAPABILITIES:
            if capability == "native_resume":
                continue
            with self.subTest(capability=capability):
                record = evidence(capability=capability, proof=wrong_proof)
                result = resolve_capability(
                    "codex-local", record, None, policy(capability=capability), NOW
                )
                self.assertEqual(result["support_level"], "unknown")
                self.assertIn("proof", result["reason"].lower())

    def test_each_capability_accepts_its_matching_proof(self):
        for capability in CAPABILITIES:
            with self.subTest(capability=capability):
                result = resolve_capability(
                    "codex-local",
                    evidence(capability=capability),
                    None,
                    policy(capability=capability),
                    NOW,
                )
                self.assertEqual(result["support_level"], "observed", result)

    def test_usage_measurement_requires_linked_observed_counter_proof(self):
        cases = [
            usage_counter("codex-local", "codex-host/1.2.3", observed=False),
            usage_counter("other", "codex-host/1.2.3"),
            usage_counter("codex-local", "codex-host/1.2.2"),
            usage_counter("codex-local", "codex-host/1.2.3", counter_id="user:claim"),
            usage_counter("codex-local", "codex-host/1.2.3", measurement_surface="api-billing"),
        ]
        for proof in cases:
            with self.subTest(proof=proof):
                result = resolve_capability(
                    "codex-local",
                    evidence(capability="usage_measurement", proof=proof),
                    None,
                    policy(capability="usage_measurement"),
                    NOW,
                )
                self.assertEqual(result["support_level"], "unknown")
                self.assertIn("usage", result["reason"])

    def test_enforcement_requires_linked_counter_and_matching_stop_primitive(self):
        for capability, required_scope in [
            ("local_enforcement", "local"),
            ("provider_enforcement", "provider"),
        ]:
            base = proof_for(capability, "codex-local", "codex-host/1.2.3")
            invalid = [
                replace(base, primitive_scope="provider" if required_scope == "local" else "local"),
                replace(base, stop_primitive="user:claim"),
                replace(base, usage_counter=replace(base.usage_counter, observed=False)),
                replace(base, usage_counter=replace(base.usage_counter, surface_id="other")),
                replace(base, usage_counter=replace(base.usage_counter, verified_version="old")),
            ]
            for proof in invalid:
                with self.subTest(capability=capability, proof=proof):
                    result = resolve_capability(
                        "codex-local",
                        evidence(capability=capability, proof=proof),
                        None,
                        policy(capability=capability),
                        NOW,
                    )
                    self.assertEqual(result["support_level"], "unknown")
                    self.assertIn("enforcement", result["reason"])

    def test_stop_primitives_are_allowlisted_by_surface_capability_and_scope(self):
        surfaces = (
            "codex-local",
            "openai-api-agents",
            "claude-code-local",
            "anthropic-api-agent-sdk",
        )
        for surface in surfaces:
            version = "host/1.2.3"
            for capability in ("pause_cancel", "local_enforcement", "provider_enforcement"):
                selected_policy = policy(surface=surface, version=version, capability=capability)
                live_record = evidence(surface=surface, version=version, capability=capability)
                bad_proof = replace(live_record.proof, stop_primitive="arbitrary_stop")
                bad_live = replace(live_record, proof=bad_proof)
                acceptance_record = (
                    evidence(
                        surface=surface,
                        version=version,
                        capability=capability,
                        provenance="acceptance_run",
                    )
                    if surface in API_SURFACES
                    else None
                )
                with self.subTest(surface=surface, capability=capability):
                    result = resolve_capability(
                        surface, bad_live, acceptance_record, selected_policy, NOW
                    )
                    self.assertEqual(result["support_level"], "unknown")
                    self.assertIn("allowlisted", result["reason"])

    def test_every_proof_dataclass_rejects_wrong_runtime_field_types(self):
        cases = [
            ("native_resume", "surface_id", []),
            ("native_resume", "verified_version", {}),
            ("native_resume", "native_handle_ref", True),
            ("native_resume", "continuity_evidence_ref", []),
            ("pause_cancel", "surface_id", {}),
            ("pause_cancel", "verified_version", []),
            ("pause_cancel", "stop_primitive", True),
            ("usage_measurement", "surface_id", []),
            ("usage_measurement", "verified_version", {}),
            ("usage_measurement", "measurement_surface", True),
            ("usage_measurement", "counter_id", []),
            ("usage_measurement", "observed", "true"),
            ("local_enforcement", "surface_id", []),
            ("local_enforcement", "verified_version", {}),
            ("local_enforcement", "usage_counter", []),
            ("local_enforcement", "primitive_scope", True),
            ("local_enforcement", "stop_primitive", []),
            ("persistence_privacy", "surface_id", []),
            ("persistence_privacy", "verified_version", {}),
            ("persistence_privacy", "storage_boundary", True),
            ("persistence_privacy", "privacy_control_ref", []),
            ("parallel_execution", "surface_id", []),
            ("parallel_execution", "verified_version", {}),
            ("parallel_execution", "slot_detector_ref", True),
            ("parallel_execution", "detected_max", []),
            ("parallel_execution", "detected_max", True),
            ("tracing", "surface_id", []),
            ("tracing", "verified_version", {}),
            ("tracing", "trace_source", True),
        ]
        for capability, field, value in cases:
            with self.subTest(capability=capability, field=field):
                valid = evidence(capability=capability)
                bad_proof = replace(valid.proof, **{field: value})
                result = resolve_capability(
                    "codex-local",
                    replace(valid, proof=bad_proof),
                    None,
                    policy(capability=capability),
                    NOW,
                )
                self.assertEqual(result["support_level"], "unknown")
                self.assertIn("malformed", result["reason"])

    def test_native_resume_requires_native_handle_and_continuity_proof(self):
        base = proof_for("native_resume", "codex-local", "codex-host/1.2.3")
        for proof in [
            replace(base, native_handle_ref=""),
            replace(base, native_handle_ref="user:claim"),
            replace(base, continuity_evidence_ref=""),
            replace(base, continuity_evidence_ref="user:claim"),
            replace(base, surface_id="other"),
        ]:
            with self.subTest(proof=proof):
                result = resolve_capability(
                    "codex-local", evidence(proof=proof), None, policy(), NOW
                )
                self.assertEqual(result["support_level"], "unknown")
                self.assertTrue(
                    "resume" in result["reason"] or "malformed proof" in result["reason"],
                    result,
                )


class CapabilityPrecedenceTests(unittest.TestCase):
    def test_acceptance_outranks_policy_for_non_api_surface_without_live_data(self):
        result = resolve_capability(
            "codex-local", None, evidence(provenance="acceptance_run"), policy(), NOW
        )
        self.assertEqual(result["support_level"], "observed")
        self.assertEqual(result["evidence_source"], "acceptance_run")

    def test_policy_is_used_only_when_higher_priority_evidence_is_absent(self):
        result = resolve_capability("codex-local", None, None, policy(), NOW)
        self.assertEqual(result["support_level"], "policy-only")
        self.assertEqual(result["evidence_source"], "policy_declaration")

    def test_invalid_high_priority_evidence_does_not_fall_through(self):
        invalid = [
            replace(evidence(), surface_id="claude-code-local"),
            replace(evidence(), verified_version="old"),
            replace(evidence(), expires_at=NOW),
            replace(evidence(), provenance="acceptance_run"),
            replace(evidence(), conflicting=True),
            replace(evidence(), detector_status="failed"),
            replace(evidence(), executable_adapter=False),
            replace(evidence(), required_fallback="inline"),
        ]
        valid_acceptance = evidence(provenance="acceptance_run")
        for record in invalid:
            with self.subTest(record=record):
                result = resolve_capability(
                    "codex-local", record, valid_acceptance, policy(), NOW
                )
                self.assertEqual(result["support_level"], "unknown")

    def test_explicit_unsupported_evidence_is_preserved(self):
        result = resolve_capability(
            "codex-local",
            replace(evidence(), support_level="unsupported"),
            None,
            policy(),
            NOW,
        )
        self.assertEqual(result["support_level"], "unsupported")
        self.assertEqual(result["required_fallback"], "rehydrate")

    def test_expired_or_unavailable_policy_fails_closed_without_false_match(self):
        expired = resolve_capability(
            "codex-local", None, None, policy(expires_at=NOW.isoformat()), NOW
        )
        unavailable = resolve_capability(
            "codex-local",
            evidence(),
            None,
            policy(version="unavailable"),
            NOW,
        )
        self.assertEqual(expired["support_level"], "unknown")
        self.assertEqual(unavailable["support_level"], "unknown")

    def test_invalid_policy_and_naive_now_are_rejected(self):
        for record in [
            policy(surface_id="claude-code-local"),
            policy(required_fallback="continue"),
            policy(support_level="observed"),
            policy(capability="unknown"),
        ]:
            with self.subTest(record=record):
                with self.assertRaises(ValueError):
                    resolve_capability("codex-local", None, None, record, NOW)
        with self.assertRaises(ValueError):
            resolve_capability("codex-local", None, None, policy(), NOW.replace(tzinfo=None))

    def test_inputs_are_not_mutated(self):
        live_record = evidence()
        acceptance_record = evidence(provenance="acceptance_run")
        policy_record = policy()
        originals = deepcopy((live_record, acceptance_record, policy_record))
        resolve_capability("codex-local", live_record, acceptance_record, policy_record, NOW)
        self.assertEqual((live_record, acceptance_record, policy_record), originals)


class ApiSdkDualEvidenceTests(unittest.TestCase):
    def records(self, surface: str):
        version = "sdk/2.4.1"
        selected_policy = policy(surface=surface, version=version)
        live_record = evidence(surface=surface, version=version)
        acceptance_record = evidence(
            surface=surface,
            version=version,
            provenance="acceptance_run",
            detector_id="acceptance:capability-harness",
        )
        return selected_policy, live_record, acceptance_record

    def test_api_sdk_surface_requires_matching_live_and_acceptance_evidence(self):
        for surface in API_SURFACES:
            selected_policy, live_record, acceptance_record = self.records(surface)
            with self.subTest(surface=surface):
                result = resolve_capability(
                    surface, live_record, acceptance_record, selected_policy, NOW
                )
                self.assertEqual(result["support_level"], "observed", result)
                self.assertEqual(result["evidence_source"], "live_detection+acceptance_run")
                self.assertEqual(result["acceptance_evidence_ref"], "acceptance:run-11")

    def test_api_sdk_missing_invalid_mismatched_or_stale_acceptance_fails_closed(self):
        for surface in API_SURFACES:
            selected_policy, live_record, acceptance_record = self.records(surface)
            invalid = [
                None,
                {"provenance": "acceptance_run", "evidence_ref": "user:claim"},
                replace(acceptance_record, surface_id="other"),
                replace(acceptance_record, verified_version="old"),
                replace(acceptance_record, expires_at=NOW),
                replace(acceptance_record, support_level="unsupported"),
            ]
            for bad_acceptance in invalid:
                with self.subTest(surface=surface, acceptance=bad_acceptance):
                    result = resolve_capability(
                        surface, live_record, bad_acceptance, selected_policy, NOW
                    )
                    self.assertEqual(result["support_level"], "unknown")
                    self.assertIn("acceptance", result["reason"])

    def test_api_sdk_acceptance_without_live_evidence_fails_closed(self):
        for surface in API_SURFACES:
            selected_policy, _, acceptance_record = self.records(surface)
            result = resolve_capability(surface, None, acceptance_record, selected_policy, NOW)
            self.assertEqual(result["support_level"], "unknown")
            self.assertIn("live", result["reason"])

    def test_api_sdk_policy_only_remains_available_when_no_runtime_claim_is_made(self):
        for surface in API_SURFACES:
            selected_policy, _, _ = self.records(surface)
            result = resolve_capability(surface, None, None, selected_policy, NOW)
            self.assertEqual(result["support_level"], "policy-only")


def matrix_rows(filename: str) -> list[dict[str, str]]:
    lines = (ROOT / "skills" / "optimal-challenge" / "references" / filename).read_text(
        encoding="utf-8"
    ).splitlines()
    table = [line for line in lines if line.startswith("|")]
    headers = [cell.strip().lower() for cell in table[0].strip("|").split("|")]
    rows = []
    for line in table[2:]:
        values = [cell.strip().lower() for cell in line.strip("|").split("|")]
        rows.append(dict(zip(headers, values, strict=True)))
    return rows


class PlatformMatrixDocumentationTests(unittest.TestCase):
    def test_every_matrix_row_matches_the_executable_contract(self):
        expected_surfaces = {
            "platform-codex.md": {"codex-local", "openai-api-agents"},
            "platform-claude.md": {"claude-code-local", "anthropic-api-agent-sdk"},
        }
        required_headers = {
            "surface id",
            "capability",
            "support level",
            "detector",
            "evidence ref",
            "verified version",
            "verified at",
            "expires at",
            "measurement surface",
            "fallback",
            "fallback explanation",
        }
        version_pattern = re.compile(r"^[a-z0-9.-]+/\d+\.\d+(?:\.\d+)?$")
        for filename, surfaces in expected_surfaces.items():
            rows = matrix_rows(filename)
            self.assertEqual(len(rows), 16)
            self.assertEqual(set(rows[0]), required_headers)
            self.assertEqual({row["surface id"] for row in rows}, surfaces)
            for row in rows:
                capability = DISPLAY_CAPABILITIES[row["capability"]]
                self.assertIn(row["support level"], {"policy-only", "observed", "unsupported"})
                self.assertEqual(row["fallback"], CAPABILITIES[capability])
                self.assertTrue(row["fallback explanation"])
                self.assertTrue(row["detector"].startswith("policy:"))
                self.assertTrue(row["evidence ref"].startswith("policy:"))
                version = row["verified version"]
                self.assertTrue(version == "unavailable" or version_pattern.fullmatch(version), version)
                verified = datetime.fromisoformat(row["verified at"].replace("z", "+00:00"))
                expiry = datetime.fromisoformat(row["expires at"].replace("z", "+00:00"))
                self.assertIsNotNone(verified.utcoffset())
                self.assertGreater(expiry, verified)
                if capability in {"usage_measurement", "local_enforcement", "provider_enforcement"}:
                    self.assertNotEqual(row["measurement surface"], "n/a")
                else:
                    self.assertEqual(row["measurement surface"], "n/a")

    def test_api_sdk_rows_are_policy_only_and_unavailable_until_dual_evidence(self):
        for filename, api_surface in [
            ("platform-codex.md", "openai-api-agents"),
            ("platform-claude.md", "anthropic-api-agent-sdk"),
        ]:
            api_rows = [row for row in matrix_rows(filename) if row["surface id"] == api_surface]
            self.assertEqual(len(api_rows), 8)
            for row in api_rows:
                self.assertEqual(row["support level"], "policy-only")
                self.assertEqual(row["verified version"], "unavailable")

    def test_docs_state_fail_closed_and_dual_evidence_rules(self):
        for filename in ["platform-codex.md", "platform-claude.md"]:
            text = (ROOT / "skills" / "optimal-challenge" / "references" / filename).read_text(
                encoding="utf-8"
            ).lower()
            for phrase in [
                "missing provenance",
                "wrong surface",
                "wrong version",
                "conflicting",
                "detector failure",
                "unknown",
                "product subscription",
                "api billing",
                "both executable live adapter evidence and a current matching acceptance run",
                "process-local attestation",
                "not a cryptographic signature",
                "serialization cannot recreate",
            ]:
                self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
