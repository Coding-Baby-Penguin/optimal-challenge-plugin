"""Archive, source and installed identity must converge on exact bytes."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.verify_subject import CRITICAL_POLICY_PATHS, BASELINE_CRITICAL_PATHS, MAX_SUBJECT_BYTES, _safe_name, verify_subject, verify_codex_registry_read_back

ROOT = Path(__file__).resolve().parents[2]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SubjectIdentityTests(unittest.TestCase):
    def test_codex_registry_requires_exact_plugin_version_enabled_state_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "marketplace/optimal-challenge"
            source.mkdir(parents=True)
            raw = {"installed": [{"pluginId": "optimal-challenge@quality-A-local",
                                  "name": "optimal-challenge", "version": "1.1.0",
                                  "marketplaceName": "quality-A-local", "installed": True,
                                  "enabled": True, "source": {"source": "local", "path": str(source)}}]}
            arguments = {"name": "optimal-challenge", "version": "1.1.0",
                         "marketplace_name": "quality-A-local", "expected_source": source}
            result, errors = verify_codex_registry_read_back(raw, **arguments)
            self.assertEqual(errors, [])
            self.assertEqual(result["plugin_id"], "optimal-challenge@quality-A-local")
            for changed in ({"enabled": False}, {"version": "1.0.0"},
                            {"source": {"source": "local", "path": str(source.parent)}}):
                bad = json.loads(json.dumps(raw))
                bad["installed"][0].update(changed)
                result, errors = verify_codex_registry_read_back(bad, **arguments)
                self.assertIsNone(result)
                self.assertTrue(errors)

    def test_published_asset_manifest_keeps_tag_mismatch_explicit(self):
        pinned = json.loads((ROOT / "tests/subjects/A-published-v1.1.json").read_text(encoding="utf-8"))
        self.assertEqual(pinned["source_kind"], "published-release-asset")
        self.assertEqual(pinned["archive_sha256"], "f810f6bdb1e38eb722a7a1a89e01c1f4f5617fea1b7b396c6b582a83f5daba44")
        self.assertEqual(pinned["source_identity"]["tag_commit"], "b4510c8de09c64bc9ecfff07574c0d350e3b6da4")
        self.assertNotIn("commit", pinned["source_identity"])
        self.assertEqual(set(pinned["source_identity"]["tag_tree_mismatched_members"]),
                         {".codex-plugin/plugin.json", "LICENSE"})
        self.assertEqual(len(pinned["member_sha256s"]), 32)
        self.assertNotIn("config/orchestration.json", pinned["member_sha256s"])

    def test_evaluation_ablations_pin_disabled_policy_and_exact_overlay_members(self):
        for arm in ("B", "C"):
            root = ROOT / "tests" / "subjects" / "overrides" / arm
            self.assertIn("evaluation-only ablation", (root / "README.md").read_text(encoding="utf-8"))
            config = json.loads((root / "config/orchestration.json").read_text(encoding="utf-8"))
            self.assertFalse(config["premise_gate"]["enabled"])
            for name in ("premise-validation.md", "high-cost-research.md", "team-continuity.md"):
                text = (root / "skills/optimal-challenge/references" / name).read_text(encoding="utf-8")
                self.assertIn("disabled in evaluation arm " + arm, text)
            team = (root / "skills/optimal-challenge/references/team-orchestration.md").read_text(encoding="utf-8")
            self.assertIn("evaluation-only " + arm, team)
            self.assertIn("permission", team)
        b = ROOT / "tests/subjects/overrides/B/skills/optimal-challenge/references/cost-quality-routing.md"
        self.assertIn("economic delegation gate", b.read_text(encoding="utf-8"))

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name).resolve()
        self.source = self.root / "source"
        self.installed = self.root / "installed"
        self.source.mkdir(); self.installed.mkdir()
        self.archive = self.root / "subject.zip"
        self.members = {}
        for name in CRITICAL_POLICY_PATHS:
            data = (json.dumps({"name": "optimal-challenge", "version": "1.2.0"}) if
                    name == ".codex-plugin/plugin.json" else "policy:" + name).encode()
            self.members[name] = data
            for root in (self.source, self.installed):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        self._archive(self.members)
        self.manifest = self._manifest()

    def _archive(self, members):
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_STORED) as zipped:
            for name, data in sorted(members.items()):
                zipped.writestr(name, data)

    def _manifest(self):
        return {
            "subject_version": 1, "arm_id": "D", "source_kind": "reviewed-candidate-tree",
            "source_identity": {"commit": "a" * 40},
            "archive_sha256": sha(self.archive.read_bytes()),
            "member_sha256s": {name: sha(data) for name, data in self.members.items()},
            "critical_paths": sorted(CRITICAL_POLICY_PATHS),
            "plugin_name": "optimal-challenge", "plugin_version": "1.2.0",
            "marketplace_name": "quality-D-local",
            "cachebuster": "candidate-d-exact", "install_source": "isolated-clean-archive",
        }

    def verify(self, manifest=None):
        return verify_subject(manifest or self.manifest, self.source, self.archive, self.installed)

    def test_matching_source_archive_and_installed_tree_verifies_external_identity(self):
        result, errors = self.verify()
        self.assertEqual(errors, [])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["member_count"], len(self.members))
        self.assertEqual(result["cachebuster_registry_status"], "label_only_not_host_readback")

    def test_wrong_archive_source_drift_stale_cache_and_partial_install_fail(self):
        extra = self.installed / "skills/optimal-challenge/references/obsolete-policy.md"
        extra.write_text("stale policy")
        result, errors = self.verify()
        self.assertIsNone(result)
        self.assertIn("unexpected package members", " ".join(errors))
        extra.unlink()
        (self.installed / "skills/optimal-challenge/references/routing.md").write_text("old cache")
        result, errors = self.verify()
        self.assertIsNone(result)
        self.assertIn("installed bytes differ", " ".join(errors))
        (self.installed / "skills/optimal-challenge/references/routing.md").write_bytes(
            self.members["skills/optimal-challenge/references/routing.md"])
        (self.installed / "skills/optimal-challenge/references/context-management.md").unlink()
        result, errors = self.verify()
        self.assertIsNone(result)
        self.assertIn("installed file is missing", " ".join(errors))
        (self.installed / "skills/optimal-challenge/references/context-management.md").write_bytes(
            self.members["skills/optimal-challenge/references/context-management.md"])
        (self.source / "skills/optimal-challenge/SKILL.md").write_text("drift")
        result, errors = self.verify()
        self.assertIsNone(result)
        self.assertIn("source bytes differ", " ".join(errors))
        (self.source / "skills/optimal-challenge/SKILL.md").write_bytes(self.members["skills/optimal-challenge/SKILL.md"])
        self.archive.write_bytes(self.archive.read_bytes() + b"unexpected")
        result, errors = self.verify()
        self.assertIsNone(result)
        self.assertIn("archive SHA-256 differs", " ".join(errors))

    def test_duplicate_unsafe_members_and_symlink_escape_fail(self):
        self.assertFalse(_safe_name("skills/bad\nname.md"))
        self.assertFalse(_safe_name("skills/bad\tname.md"))
        self.assertFalse(_safe_name("skills/bad\x00name.md"))
        with zipfile.ZipFile(self.archive, "a") as zipped:
            zipped.writestr("../outside", b"unsafe")
        self.manifest["archive_sha256"] = sha(self.archive.read_bytes())
        result, errors = self.verify()
        self.assertIsNone(result)
        self.assertIn("archive members", " ".join(errors))
        self._archive(self.members)
        self.manifest["archive_sha256"] = sha(self.archive.read_bytes())
        link = self.installed / "skills/optimal-challenge/references/routing.md"
        link.unlink()
        try:
            link.symlink_to(self.root / "outside")
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        result, errors = self.verify()
        self.assertIsNone(result)
        self.assertIn("installed tree is unsafe", " ".join(errors))

    def test_oversized_archive_is_rejected_before_reading_it(self):
        with self.archive.open("ab") as stream:
            stream.truncate(MAX_SUBJECT_BYTES + 1)
        result, errors = self.verify()
        self.assertIsNone(result)
        self.assertIn("archive exceeds bounded", " ".join(errors))

    def test_published_baseline_can_have_older_four_file_policy_set(self):
        for name in CRITICAL_POLICY_PATHS - BASELINE_CRITICAL_PATHS:
            self.members.pop(name)
            (self.source / name).unlink()
            (self.installed / name).unlink()
        self._archive(self.members)
        self.manifest = self._manifest()
        self.manifest.update(arm_id="A", source_kind="published-release-asset",
                             critical_paths=sorted(BASELINE_CRITICAL_PATHS))
        self.manifest["source_identity"]["tag_commit"] = self.manifest["source_identity"].pop("commit")
        self.manifest["source_identity"]["release_asset_sha256"] = self.manifest["archive_sha256"]
        result, errors = self.verify()
        self.assertEqual(errors, [])
        self.assertEqual(result["source_kind"], "published-release-asset")
        self.assertIsNone(result["source_commit"])
        self.assertEqual(result["release_tag_commit"], "a" * 40)

    def test_derived_ablation_identifies_base_commit_and_overlay_bytes(self):
        overlay = "skills/optimal-challenge/SKILL.md"
        self.manifest["arm_id"] = "B"
        self.manifest["source_identity"] = {
            "base_commit": "a" * 40,
            "overlay_sha256s": {overlay: self.manifest["member_sha256s"][overlay]},
        }
        result, errors = self.verify()
        self.assertEqual(errors, [])
        self.assertIsNone(result["source_commit"])
        self.assertEqual(result["base_commit"], "a" * 40)
        self.manifest["source_identity"]["overlay_sha256s"][overlay] = "f" * 64
        result, errors = self.verify()
        self.assertIsNone(result)
        self.assertIn("overlay identity", " ".join(errors))


if __name__ == "__main__":
    unittest.main()
