from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
import zlib
from pathlib import Path

from scripts.package_release import build_archive, compare_archive, iter_package_files


ROOT = Path(__file__).resolve().parents[2]


def canonical_zip_bytes(root: Path, files: list[Path]) -> bytes:
    """Build the expected ZIP bytes without using the production writer."""

    local_parts: list[bytes] = []
    central_parts: list[bytes] = []
    offset = 0
    made_by = (3 << 8) | 20
    version_needed = 20
    dos_time = 0
    dos_date = 33
    external_attr = (stat.S_IFREG | 0o644) << 16
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        name = path.relative_to(root).as_posix().encode("ascii")
        data = path.read_bytes()
        crc = zlib.crc32(data) & 0xFFFFFFFF
        local = struct.pack(
            "<IHHHHHIIIHH",
            0x04034B50,
            version_needed,
            0,
            zipfile.ZIP_STORED,
            dos_time,
            dos_date,
            crc,
            len(data),
            len(data),
            len(name),
            0,
        ) + name + data
        central = struct.pack(
            "<IHHHHHHIIIHHHHHII",
            0x02014B50,
            made_by,
            version_needed,
            0,
            zipfile.ZIP_STORED,
            dos_time,
            dos_date,
            crc,
            len(data),
            len(data),
            len(name),
            0,
            0,
            0,
            0,
            external_attr,
            offset,
        ) + name
        local_parts.append(local)
        central_parts.append(central)
        offset += len(local)
    central = b"".join(central_parts)
    end = struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,
        0,
        len(files),
        len(files),
        len(central),
        offset,
        0,
    )
    return b"".join(local_parts) + central + end


class ReleasePackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        # Windows CI may supply a short TEMP path while Path.resolve() returns
        # its long-name alias. Match the package selector's canonical root.
        self.root = Path(self.tempdir.name).resolve()
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
        self._git("init", "-q")
        self._git("add", "-f", ".codex-plugin/plugin.json", "a.txt", "nested/z.txt")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_fixture_and_selected_paths_share_the_canonical_root(self):
        files = iter_package_files(self.root, ["dist/**", "**/__pycache__/**"])
        self.assertEqual(self.root, Path(self.tempdir.name).resolve())
        self.assertEqual(
            [path.relative_to(self.root).as_posix() for path in files],
            [".codex-plugin/plugin.json", "a.txt", "nested/z.txt"],
        )

    def test_raw_results_are_ignored_locally_and_excluded_even_if_force_tracked(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/tests/results/", ignore)
        check = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "--no-index", "--quiet",
                                "tests/results/probe/raw.json"], capture_output=True)
        self.assertEqual(check.returncode, 0, check.stderr.decode("utf-8", errors="replace"))
        self.assertIn("tests/results/**", json.loads((ROOT / "config/project.json").read_text(encoding="utf-8"))["packaging"]["excludes"])
        (self.root / "tests" / "results" / "probe").mkdir(parents=True)
        raw = self.root / "tests" / "results" / "probe" / "raw.json"
        raw.write_text('{"private":"fixture"}', encoding="utf-8")
        self._git("add", "-f", "tests/results/probe/raw.json")
        selected = iter_package_files(self.root, ["tests/results/**"])
        self.assertNotIn(raw, selected)

    def _git(self, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_iter_package_files_is_sorted_posix_includes_hidden_manifest_and_excludes_configured_paths(self):
        (self.root / "untracked.txt").write_text("must not ship", encoding="utf-8")
        (self.root / ".env").write_text("SECRET=not-real", encoding="utf-8")
        (self.root / "credentials.live.json").write_text("{}", encoding="utf-8")
        (self.root / "private.pem").write_text("not-a-key", encoding="utf-8")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "dep.js").write_text("dependency", encoding="utf-8")
        files = iter_package_files(
            self.root,
            ["dist/**", "**/__pycache__/**", "**/*.py[cod]"],
        )

        self.assertEqual(
            [path.relative_to(self.root).as_posix() for path in files],
            [".codex-plugin/plugin.json", "a.txt", "nested/z.txt"],
        )

    def test_tracked_sensitive_path_fails_closed_but_narrow_safe_examples_are_allowed(self):
        (self.root / ".env").write_text("SECRET=not-real", encoding="utf-8")
        self._git("add", "-f", ".env")
        with self.assertRaisesRegex(ValueError, "sensitive tracked path"):
            iter_package_files(self.root, [".env", ".env.*"])

        self._git("rm", "--cached", "-q", ".env")
        (self.root / ".env.example").write_text("TOKEN=<set-locally>", encoding="utf-8")
        (self.root / "credentials.example.json").write_text("{}", encoding="utf-8")
        (self.root / "docs" / "superpowers").mkdir(parents=True)
        (self.root / "docs" / "superpowers" / ".env.example").write_text(
            "TOKEN=<not-distributable>", encoding="utf-8"
        )
        self._git(
            "add",
            "-f",
            ".env.example",
            "credentials.example.json",
            "docs/superpowers/.env.example",
        )
        files = iter_package_files(
            self.root,
            [".env", ".env.*", "credentials.*", "docs/superpowers/**"],
        )
        selected = {path.relative_to(self.root).as_posix() for path in files}
        self.assertIn(".env.example", selected)
        self.assertIn("credentials.example.json", selected)
        self.assertNotIn("docs/superpowers/.env.example", selected)

        (self.root / "credentials.example.pem").write_text("not-a-key", encoding="utf-8")
        self._git("add", "-f", "credentials.example.pem")
        with self.assertRaisesRegex(ValueError, "sensitive tracked path"):
            iter_package_files(self.root, [".env", ".env.*", "credentials.*"])

    def test_runtime_allowlist_cannot_hide_tracked_sensitive_paths_or_missing_members(self):
        (self.root / "credentials.live.json").write_text("{}", encoding="utf-8")
        self._git("add", "-f", "credentials.live.json")
        with self.assertRaisesRegex(ValueError, "sensitive tracked path"):
            iter_package_files(self.root, ["credentials.*"], ["a.txt"])
        self._git("rm", "--cached", "-q", "credentials.live.json")
        with self.assertRaisesRegex(ValueError, "unmatched runtime include"):
            iter_package_files(self.root, [], ["a.txt", "scripts/missing.py"])

    def test_iter_package_files_rejects_included_symlink(self):
        link = self.root / "linked.txt"
        try:
            os.symlink(self.root / "a.txt", link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        self._git("add", "linked.txt")

        with self.assertRaisesRegex(ValueError, "symlink"):
            iter_package_files(self.root, ["dist/**", "**/__pycache__/**"])

    def test_build_archive_is_deterministic_and_uses_fixed_metadata(self):
        files = iter_package_files(self.root, ["dist/**", "**/__pycache__/**"])
        first = self.root / "dist" / "first.zip"
        second = self.root / "dist" / "second.zip"

        first_sha = build_archive(self.root, first, files)
        second_sha = build_archive(self.root, second, files)

        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first.read_bytes(), canonical_zip_bytes(self.root, files))
        self.assertEqual(first_sha, hashlib.sha256(first.read_bytes()).hexdigest())
        self.assertEqual(second_sha, first_sha)
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(archive.namelist(), sorted(archive.namelist()))
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(stat.S_IMODE(info.external_attr >> 16), 0o644)
                self.assertTrue(stat.S_ISREG(info.external_attr >> 16))
                self.assertFalse(stat.S_ISLNK(info.external_attr >> 16))
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(info.flag_bits, 0)

    def test_canonical_archive_matches_available_python_312_and_314(self):
        alternate = shutil.which("python")
        if not alternate or Path(alternate).resolve() == Path(sys.executable).resolve():
            self.skipTest("no alternate Python runtime is available")
        files = iter_package_files(self.root, ["dist/**", "**/__pycache__/**"])
        expected = self.root / "dist" / "current.zip"
        build_archive(self.root, expected, files)
        alternate_output = self.root / "dist" / "alternate.zip"
        code = (
            "import sys; from pathlib import Path; "
            f"sys.path.insert(0, {str(ROOT)!r}); "
            "from scripts.package_release import iter_package_files, build_archive; "
            f"root=Path({str(self.root)!r}); output=Path({str(alternate_output)!r}); "
            "files=iter_package_files(root, ['dist/**', '**/__pycache__/**']); "
            "print(build_archive(root, output, files))"
        )
        completed = subprocess.run(
            [alternate, "-c", code],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.stdout.strip(), hashlib.sha256(expected.read_bytes()).hexdigest())
        self.assertEqual(alternate_output.read_bytes(), expected.read_bytes())

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

    def test_compare_archive_rejects_noncanonical_order_and_metadata(self):
        files = iter_package_files(self.root, ["dist/**", "**/__pycache__/**"])
        archive_path = self.root / "dist" / "corrupt.zip"

        corruptions = {
            "order": {"reverse": True},
            "timestamp": {"timestamp": (2026, 1, 1, 0, 0, 0)},
            "mode": {"mode": stat.S_IFREG | 0o777},
            "compression": {"compression": zipfile.ZIP_DEFLATED},
        }
        for label, options in corruptions.items():
            with self.subTest(label=label):
                ordered = sorted(files, key=lambda item: item.relative_to(self.root).as_posix())
                if options.get("reverse"):
                    ordered.reverse()
                with zipfile.ZipFile(archive_path, "w") as archive:
                    for path in ordered:
                        name = path.relative_to(self.root).as_posix()
                        info = zipfile.ZipInfo(name, options.get("timestamp", (1980, 1, 1, 0, 0, 0)))
                        info.create_system = 3
                        info.compress_type = options.get("compression", zipfile.ZIP_STORED)
                        info.external_attr = options.get("mode", stat.S_IFREG | 0o644) << 16
                        archive.writestr(info, path.read_bytes(), compress_type=info.compress_type)
                errors = compare_archive(self.root, archive_path, files)
                self.assertTrue(any(label in error.lower() for error in errors), errors)

        build_archive(self.root, archive_path, files)
        raw = bytearray(archive_path.read_bytes())
        local = raw.find(b"PK\x03\x04")
        central = raw.find(b"PK\x01\x02")
        struct.pack_into("<H", raw, local + 6, 0x0800)
        struct.pack_into("<H", raw, central + 8, 0x0800)
        archive_path.write_bytes(raw)
        self.assertTrue(
            any("flag" in error.lower() for error in compare_archive(self.root, archive_path, files))
        )

    def test_compare_archive_rejects_duplicate_members(self):
        files = iter_package_files(self.root, ["dist/**", "**/__pycache__/**"])
        archive_path = self.root / "dist" / "duplicate.zip"
        source = self.root / "a.txt"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
                for _ in range(2):
                    info = zipfile.ZipInfo("a.txt", (1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.create_version = 20
                    info.extract_version = 20
                    info.external_attr = (stat.S_IFREG | 0o644) << 16
                    archive.writestr(info, source.read_bytes())
        self.assertTrue(
            any("duplicate" in error.lower() for error in compare_archive(self.root, archive_path, files))
        )

    def test_compare_archive_rejects_internal_attributes_and_noncanonical_framing(self):
        files = iter_package_files(self.root, ["dist/**", "**/__pycache__/**"])
        archive_path = self.root / "dist" / "framing.zip"
        ordered = sorted(files, key=lambda item: item.relative_to(self.root).as_posix())

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
            for path in ordered:
                info = zipfile.ZipInfo(
                    path.relative_to(self.root).as_posix(),
                    (1980, 1, 1, 0, 0, 0),
                )
                info.create_system = 3
                info.create_version = 20
                info.extract_version = 20
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.internal_attr = 1
                archive.writestr(info, path.read_bytes())
        self.assertTrue(
            any("internal" in error.lower() for error in compare_archive(self.root, archive_path, files))
        )

        build_archive(self.root, archive_path, files)
        canonical = archive_path.read_bytes()
        archive_path.write_bytes(canonical + b"junk")
        self.assertTrue(
            any("framing" in error.lower() or "bytes" in error.lower() for error in compare_archive(self.root, archive_path, files))
        )

        archive_path.write_bytes(b"junk" + canonical)
        self.assertTrue(
            any("framing" in error.lower() or "bytes" in error.lower() for error in compare_archive(self.root, archive_path, files))
        )

    def test_project_configuration_declares_release_command_and_required_exclusions(self):
        project = json.loads((ROOT / "config/project.json").read_text(encoding="utf-8"))
        self.assertEqual(project["commands"]["package"], "python scripts/package_release.py")
        exclusions = set(project["packaging"]["excludes"])
        for pattern in {
            ".git/**",
            ".env",
            ".env.*",
            "credentials.*",
            "*.pem",
            "*.key",
            "*.p12",
            "*.pfx",
            "node_modules/**",
            ".venv/**",
            "venv/**",
            "dist/**",
            ".optimal-challenge/**",
            "docs/superpowers/**",
            "**/__pycache__/**",
            "tests/raw/**",
            "tests/results/**",
            "tests/subjects/**",
        }:
            self.assertIn(pattern, exclusions)

    def test_repository_release_archive_matches_selected_source_exactly(self):
        project = json.loads((ROOT / "config/project.json").read_text(encoding="utf-8"))
        files = iter_package_files(ROOT, project["packaging"]["excludes"], project["packaging"]["runtime_includes"])
        archive = ROOT / project["paths"]["package"]
        sha256 = build_archive(ROOT, archive, files)

        self.assertRegex(sha256, r"^[0-9a-f]{64}$")
        self.assertEqual(compare_archive(ROOT, archive, files), [])

    def test_runtime_package_closes_skill_references_without_shipping_mutable_evidence(self):
        project = json.loads((ROOT / "config/project.json").read_text(encoding="utf-8"))
        files = iter_package_files(ROOT, project["packaging"]["excludes"], project["packaging"]["runtime_includes"])
        selected = {path.relative_to(ROOT).as_posix() for path in files}
        for required in (
            ".codex-plugin/plugin.json", ".claude-plugin/plugin.json", "plugin.json",
            "skills/optimal-challenge/SKILL.md", "scripts/evaluate_routing.py",
            "scripts/capability_matrix.py", "scripts/orchestration_config.py",
            "scripts/validate_orchestration.py", "scripts/optimal_challenge/recovery.py",
            "config/orchestration.json", "config/team-registry.schema.json",
            "config/allocation-ledger.schema.json",
        ):
            self.assertIn(required, selected)
        self.assertFalse(any(name.startswith(("tests/", "docs/", "submission/", ".github/")) for name in selected))
        self.assertFalse(any(name in selected for name in (
            "scripts/evaluation_evidence.py", "scripts/record_acceptance.py",
            "scripts/review_acceptance.py", "scripts/verify_subject.py",
            "scripts/check_quality.py", "requirements-dev.lock", "config/project.json",
        )))
        links = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
        for name in selected:
            if not name.startswith("skills/") or not name.endswith(".md"):
                continue
            for match in links.finditer((ROOT / name).read_text(encoding="utf-8")):
                target = match.group(1).split("#", 1)[0]
                if not target or ":" in target or target.startswith("/"):
                    continue
                resolved = ((ROOT / name).parent / target).resolve()
                self.assertIn(resolved.relative_to(ROOT).as_posix(), selected, f"missing packaged skill link {name} -> {target}")

    def test_packaged_orchestration_validator_runs_without_site_packages_from_task_directory(self):
        project = json.loads((ROOT / "config/project.json").read_text(encoding="utf-8"))
        files = iter_package_files(ROOT, project["packaging"]["excludes"], project["packaging"]["runtime_includes"])
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            archive = scratch / "runtime.zip"
            build_archive(ROOT, archive, files)
            plugin = scratch / "plugin"
            plugin.mkdir()
            with zipfile.ZipFile(archive) as package:
                package.extractall(plugin)
            task = scratch / "task"
            task.mkdir()
            fixtures = ROOT / "tests/fixtures/orchestration"
            for name in ("valid-registry.json", "valid-ledger.json"):
                shutil.copyfile(fixtures / name, task / name)
            command = [
                sys.executable, "-I", "-S", str(plugin / "scripts/validate_orchestration.py"),
                "--registry", str(task / "valid-registry.json"),
                "--ledger", str(task / "valid-ledger.json"),
            ]
            valid = subprocess.run(command, cwd=task, capture_output=True, text=True, check=False)
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            self.assertIn("ORCHESTRATION STATE VALIDATION PASSED", valid.stdout)
            invalid_registry = json.loads((task / "valid-registry.json").read_text(encoding="utf-8"))
            invalid_registry["unexpected"] = True
            (task / "valid-registry.json").write_text(json.dumps(invalid_registry), encoding="utf-8")
            invalid = subprocess.run(command, cwd=task, capture_output=True, text=True, check=False)
            self.assertEqual(invalid.returncode, 1, invalid.stdout + invalid.stderr)
            self.assertIn("$.registry.unexpected", invalid.stdout)
            self.assertNotIn("Traceback", invalid.stderr)

    def test_release_hash_is_external_and_candidate_identity_remains_unverified(self):
        documentation = (ROOT / "config/README.md").read_text(encoding="utf-8").lower()
        self.assertIn("evaluation manifest is external to the runtime archive", documentation)
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
