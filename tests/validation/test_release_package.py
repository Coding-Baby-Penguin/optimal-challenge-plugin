from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.package_release import build_archive, compare_archive, iter_package_files


ROOT = Path(__file__).resolve().parents[2]


class ReleasePackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / ".codex-plugin").mkdir()
        (self.root / ".codex-plugin" / "plugin.json").write_text(
            '{"name":"fixture"}\n', encoding="utf-8"
        )
        (self.root / "nested").mkdir()
        (self.root / "nested" / "z.txt").write_bytes(b"z\n")
        (self.root / "a.txt").write_bytes(b"a\n")
        (self.root / "dist").mkdir()
        (self.root / "dist" / "old.zip").write_bytes(b"old")
        (self.root / "nested" / "__pycache__").mkdir()
        (self.root / "nested" / "__pycache__" / "cached.pyc").write_bytes(b"cache")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_iter_package_files_is_sorted_posix_includes_hidden_manifest_and_excludes_configured_paths(self):
        files = iter_package_files(
            self.root,
            ["dist/**", "**/__pycache__/**", "**/*.py[cod]"],
        )

        self.assertEqual(
            [path.relative_to(self.root).as_posix() for path in files],
            [".codex-plugin/plugin.json", "a.txt", "nested/z.txt"],
        )

    def test_iter_package_files_rejects_included_symlink(self):
        link = self.root / "linked.txt"
        try:
            os.symlink(self.root / "a.txt", link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

        with self.assertRaisesRegex(ValueError, "symlink"):
            iter_package_files(self.root, ["dist/**", "**/__pycache__/**"])

    def test_build_archive_is_deterministic_and_uses_fixed_metadata(self):
        files = iter_package_files(self.root, ["dist/**", "**/__pycache__/**"])
        first = self.root / "dist" / "first.zip"
        second = self.root / "dist" / "second.zip"

        first_sha = build_archive(self.root, first, files)
        second_sha = build_archive(self.root, second, files)

        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first_sha, hashlib.sha256(first.read_bytes()).hexdigest())
        self.assertEqual(second_sha, first_sha)
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(archive.namelist(), sorted(archive.namelist()))
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(stat.S_IMODE(info.external_attr >> 16), 0o644)
                self.assertFalse(stat.S_ISLNK(info.external_attr >> 16))

    def test_compare_archive_detects_missing_unexpected_and_changed_members(self):
        files = iter_package_files(self.root, ["dist/**", "**/__pycache__/**"])
        archive_path = self.root / "dist" / "fixture.zip"
        build_archive(self.root, archive_path, files)
        self.assertEqual(compare_archive(self.root, archive_path, files), [])

        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("a.txt", b"changed")
            archive.writestr("unexpected.txt", b"unexpected")

        errors = compare_archive(self.root, archive_path, files)
        self.assertTrue(any("missing" in error.lower() for error in errors), errors)
        self.assertTrue(any("unexpected" in error.lower() for error in errors), errors)
        self.assertTrue(any("changed" in error.lower() for error in errors), errors)

    def test_project_configuration_declares_release_command_and_required_exclusions(self):
        project = json.loads((ROOT / "config/project.json").read_text(encoding="utf-8"))
        self.assertEqual(project["commands"]["package"], "python scripts/package_release.py")
        exclusions = set(project["packaging"]["excludes"])
        for pattern in {
            ".git/**",
            "dist/**",
            ".optimal-challenge/**",
            "docs/superpowers/**",
            "**/__pycache__/**",
            "tests/raw/**",
            "tests/results/**",
        }:
            self.assertIn(pattern, exclusions)

    def test_repository_release_archive_matches_selected_source_exactly(self):
        project = json.loads((ROOT / "config/project.json").read_text(encoding="utf-8"))
        files = iter_package_files(ROOT, project["packaging"]["excludes"])
        archive = ROOT / project["paths"]["package"]
        sha256 = build_archive(ROOT, archive, files)

        self.assertRegex(sha256, r"^[0-9a-f]{64}$")
        self.assertEqual(compare_archive(ROOT, archive, files), [])

    def test_release_hash_is_external_and_candidate_identity_remains_unverified(self):
        documentation = (ROOT / "config/README.md").read_text(encoding="utf-8").lower()
        self.assertIn("cannot embed its own sha-256", documentation)
        self.assertIn("task 10", documentation)

        manifest = json.loads((ROOT / "tests/evaluation-manifest.json").read_text(encoding="utf-8"))
        candidate_arms = [arm for arm in manifest["arms"] if arm["arm_id"] in {"B", "C", "D"}]
        self.assertEqual(len(candidate_arms), 3)
        for arm in candidate_arms:
            self.assertEqual(
                arm["identity_status"],
                "unverified-provisional-refresh-after-task-9",
            )
        self.assertTrue(manifest["claim_policy"]["refresh_candidate_identity_after_release_build"])


if __name__ == "__main__":
    unittest.main()
