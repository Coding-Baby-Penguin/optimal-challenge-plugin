from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.capability_matrix import resolve_capability


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


def policy(**overrides):
    record = {
        "surface_id": "codex-local",
        "capability": "native_resume",
        "support_level": "policy-only",
        "detector": "host capability probe",
        "evidence_ref": "policy:platform-codex#codex-local",
        "verified_version": "1.2.3",
        "verified_at": "2026-09-01T00:00:00Z",
        "expires_at": "2026-12-01T00:00:00Z",
        "provenance": "policy_declaration",
        "required_fallback": "rehydrate",
    }
    record.update(overrides)
    return record


def live(**overrides):
    record = {
        "surface_id": "codex-local",
        "capability": "native_resume",
        "support_level": "observed",
        "detector": "codex capability probe",
        "detector_status": "success",
        "evidence_ref": "live:run-17",
        "verified_version": "1.2.3",
        "verified_at": "2026-09-27T11:30:00Z",
        "expires_at": "2026-09-27T13:00:00Z",
        "provenance": "live_detection",
        "required_fallback": "rehydrate",
        "conflicting": False,
    }
    record.update(overrides)
    return record


def acceptance(**overrides):
    record = live(
        detector="acceptance harness",
        detector_status="success",
        evidence_ref="acceptance:run-11",
        verified_at="2026-09-26T12:00:00Z",
        expires_at="2026-10-04T12:00:00Z",
        provenance="acceptance_run",
    )
    record.update(overrides)
    return record


class CapabilityPrecedenceTests(unittest.TestCase):
    def test_matching_live_evidence_outranks_acceptance_and_policy(self):
        result = resolve_capability("codex-local", live(), acceptance(), policy(), NOW)

        self.assertEqual(result["support_level"], "observed")
        self.assertEqual(result["evidence_source"], "live_detection")
        self.assertEqual(result["evidence_ref"], "live:run-17")
        self.assertEqual(result["expires_at"], "2026-09-27T13:00:00Z")
        self.assertEqual(result["required_fallback"], "rehydrate")

    def test_unexpired_acceptance_evidence_outranks_policy_without_live_data(self):
        result = resolve_capability("codex-local", None, acceptance(), policy(), NOW)

        self.assertEqual(result["support_level"], "observed")
        self.assertEqual(result["evidence_source"], "acceptance_run")
        self.assertEqual(result["evidence_ref"], "acceptance:run-11")

    def test_policy_is_used_only_when_higher_priority_evidence_is_absent(self):
        result = resolve_capability("codex-local", None, None, policy(), NOW)

        self.assertEqual(result["support_level"], "policy-only")
        self.assertEqual(result["evidence_source"], "policy_declaration")
        self.assertEqual(result["required_fallback"], "rehydrate")

    def test_explicit_unsupported_evidence_is_preserved(self):
        result = resolve_capability(
            "codex-local",
            live(support_level="unsupported", required_fallback="blocked"),
            acceptance(),
            policy(required_fallback="blocked"),
            NOW,
        )

        self.assertEqual(result["support_level"], "unsupported")
        self.assertEqual(result["evidence_source"], "live_detection")
        self.assertEqual(result["required_fallback"], "blocked")

    def test_evidence_cannot_substitute_a_different_fallback(self):
        result = resolve_capability(
            "codex-local", live(required_fallback="inline"), None, policy(), NOW
        )

        self.assertEqual(result["support_level"], "unknown")
        self.assertEqual(result["required_fallback"], "rehydrate")
        self.assertIn("fallback", result["reason"])

    def test_wrong_surface_fails_closed_instead_of_using_lower_evidence(self):
        result = resolve_capability(
            "codex-local", live(surface_id="claude-local"), acceptance(), policy(), NOW
        )

        self.assertEqual(result["support_level"], "unknown")
        self.assertEqual(result["required_fallback"], "rehydrate")
        self.assertIn("surface", result["reason"])

    def test_wrong_version_fails_closed(self):
        result = resolve_capability(
            "codex-local", live(verified_version="1.2.2"), acceptance(), policy(), NOW
        )

        self.assertEqual(result["support_level"], "unknown")
        self.assertIn("version", result["reason"])

    def test_expired_evidence_fails_closed_at_the_boundary(self):
        result = resolve_capability(
            "codex-local",
            live(expires_at=NOW.isoformat()),
            acceptance(),
            policy(),
            NOW,
        )

        self.assertEqual(result["support_level"], "unknown")
        self.assertIn("expired", result["reason"])

    def test_missing_or_untrusted_provenance_fails_closed(self):
        for bad_provenance in (None, "", "policy_declaration", "user_claim"):
            with self.subTest(provenance=bad_provenance):
                candidate = live()
                if bad_provenance is None:
                    candidate.pop("provenance")
                else:
                    candidate["provenance"] = bad_provenance

                result = resolve_capability("codex-local", candidate, acceptance(), policy(), NOW)

                self.assertEqual(result["support_level"], "unknown")
                self.assertIn("provenance", result["reason"])

    def test_conflicting_observations_fail_closed(self):
        result = resolve_capability(
            "codex-local", live(conflicting=True), acceptance(), policy(), NOW
        )

        self.assertEqual(result["support_level"], "unknown")
        self.assertIn("conflict", result["reason"])

    def test_detector_failure_fails_closed(self):
        result = resolve_capability(
            "codex-local", live(detector_status="failed"), acceptance(), policy(), NOW
        )

        self.assertEqual(result["support_level"], "unknown")
        self.assertIn("detector", result["reason"])

    def test_malformed_evidence_fields_fail_closed_without_throwing(self):
        malformed = [
            ({"evidence_ref": ""}, "evidence_ref"),
            ({"verified_at": "not-a-date"}, "timestamp"),
            ({"verified_at": (NOW + timedelta(seconds=1)).isoformat()}, "future"),
            ({"expires_at": "not-a-date"}, "expired"),
            ({"support_level": "supported"}, "support level"),
            ({"conflicting": "false"}, "conflict"),
            ({"capability": "pause_cancel"}, "capability"),
        ]
        for override, reason in malformed:
            with self.subTest(override=override):
                result = resolve_capability("codex-local", live(**override), None, policy(), NOW)
                self.assertEqual(result["support_level"], "unknown")
                self.assertIn(reason, result["reason"])

    def test_acceptance_record_requires_acceptance_provenance(self):
        result = resolve_capability(
            "codex-local", None, acceptance(provenance="live_detection"), policy(), NOW
        )

        self.assertEqual(result["support_level"], "unknown")
        self.assertEqual(result["evidence_source"], "acceptance_run")
        self.assertIn("provenance", result["reason"])

    def test_expired_policy_fails_closed_when_no_observed_evidence_exists(self):
        result = resolve_capability(
            "codex-local",
            None,
            None,
            policy(expires_at=NOW.isoformat()),
            NOW,
        )

        self.assertEqual(result["support_level"], "unknown")
        self.assertEqual(result["required_fallback"], "rehydrate")
        self.assertIn("expired", result["reason"])

    def test_unknown_uses_the_same_policy_fallback_as_unsupported(self):
        unsupported = resolve_capability(
            "codex-local", live(support_level="unsupported"), None, policy(), NOW
        )
        unknown = resolve_capability(
            "codex-local", live(conflicting=True, required_fallback="inline"), None, policy(), NOW
        )

        self.assertEqual(unsupported["required_fallback"], policy()["required_fallback"])
        self.assertEqual(unknown["required_fallback"], policy()["required_fallback"])

    def test_invalid_policy_or_naive_now_is_rejected_not_guessed(self):
        invalid_records = [
            policy(surface_id="claude-local"),
            policy(required_fallback="continue"),
            policy(support_level="observed"),
        ]
        for record in invalid_records:
            with self.subTest(record=record):
                with self.assertRaises(ValueError):
                    resolve_capability("codex-local", None, None, record, NOW)

        with self.assertRaises(ValueError):
            resolve_capability("codex-local", None, None, policy(), NOW.replace(tzinfo=None))

    def test_inputs_are_not_mutated(self):
        live_record = live()
        acceptance_record = acceptance()
        policy_record = policy()
        originals = deepcopy((live_record, acceptance_record, policy_record))

        resolve_capability("codex-local", live_record, acceptance_record, policy_record, NOW)

        self.assertEqual((live_record, acceptance_record, policy_record), originals)


class PlatformMatrixDocumentationTests(unittest.TestCase):
    def test_each_platform_reference_has_separate_local_and_api_surfaces(self):
        expected = {
            "platform-codex.md": ["codex-local", "openai-api-agents"],
            "platform-claude.md": ["claude-code-local", "anthropic-api-agent-sdk"],
        }
        for filename, surfaces in expected.items():
            text = (ROOT / "skills" / "optimal-challenge" / "references" / filename).read_text(
                encoding="utf-8"
            ).lower()
            with self.subTest(filename=filename):
                for surface in surfaces:
                    self.assertIn(surface, text)
                for capability in [
                    "native resume",
                    "pause/cancel",
                    "usage measurement",
                    "local enforcement",
                    "provider enforcement",
                    "persistence/privacy",
                    "parallel execution",
                    "tracing",
                ]:
                    self.assertIn(capability, text)

    def test_each_platform_reference_documents_evidence_fields_and_fail_closed_rules(self):
        for filename in ["platform-codex.md", "platform-claude.md"]:
            text = (ROOT / "skills" / "optimal-challenge" / "references" / filename).read_text(
                encoding="utf-8"
            ).lower()
            with self.subTest(filename=filename):
                for field in [
                    "surface id",
                    "support level",
                    "detector",
                    "evidence ref",
                    "verified version",
                    "verified at",
                    "expires at",
                    "required fallback",
                ]:
                    self.assertIn(field, text)
                self.assertIn("missing provenance", text)
                self.assertIn("wrong surface", text)
                self.assertIn("wrong version", text)
                self.assertIn("conflicting", text)
                self.assertIn("detector failure", text)
                self.assertIn("unknown", text)
                self.assertIn("product subscription", text)
                self.assertIn("api billing", text)

    def test_api_sdk_rows_do_not_claim_observed_executable_support(self):
        for filename, api_surface in [
            ("platform-codex.md", "openai-api-agents"),
            ("platform-claude.md", "anthropic-api-agent-sdk"),
        ]:
            lines = (ROOT / "skills" / "optimal-challenge" / "references" / filename).read_text(
                encoding="utf-8"
            ).lower().splitlines()
            api_rows = [line for line in lines if line.startswith("|") and api_surface in line]
            self.assertEqual(len(api_rows), 8, (filename, api_rows))
            for row in api_rows:
                self.assertIn("policy-only", row)
                self.assertNotIn("| observed |", row)


if __name__ == "__main__":
    unittest.main()
