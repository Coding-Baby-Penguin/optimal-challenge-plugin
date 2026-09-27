#!/usr/bin/env python3
"""Build and verify a deterministic Optimal Challenge release archive."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
PROJECT_CONFIG = ROOT / "config" / "project.json"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
FIXED_FILE_MODE = stat.S_IFREG | 0o644
CANONICAL_CREATE_SYSTEM = 3
CANONICAL_ZIP_VERSION = 20
CANONICAL_FLAG_BITS = 0
SENSITIVE_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx"})
SAFE_EXAMPLE_EXCLUDE_PATTERNS = frozenset({".env.*", "credentials.*"})


def _relative_posix(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"package file is outside root: {path}") from exc
    if not relative.parts or ".." in relative.parts:
        raise ValueError(f"unsafe package path: {path}")
    return relative.as_posix()


def _matches_exclude(
    relative: str,
    excludes: Sequence[str],
    ignored_patterns: frozenset[str] = frozenset(),
) -> bool:
    path = PurePosixPath(relative)
    for pattern in excludes:
        normalized = pattern.replace("\\", "/").strip("/")
        if not normalized:
            continue
        if normalized in ignored_patterns:
            continue
        if path.match(normalized):
            return True
        prefix = normalized.removesuffix("/**")
        if normalized.endswith("/**") and (relative == prefix or relative.startswith(prefix + "/")):
            return True
    return False


def _is_safe_example(relative: str) -> bool:
    name = PurePosixPath(relative).name.lower()
    return name == ".env.example" or name.startswith("credentials.example.")


def _is_sensitive_path(relative: str) -> bool:
    name = PurePosixPath(relative).name.lower()
    return (
        name == ".env"
        or name.startswith(".env.")
        or name.startswith("credentials.")
        or PurePosixPath(name).suffix in SENSITIVE_SUFFIXES
    )


def _has_sensitive_suffix(relative: str) -> bool:
    return PurePosixPath(relative).suffix.lower() in SENSITIVE_SUFFIXES


def _validate_tracked_name(relative: str) -> PurePosixPath:
    pure = PurePosixPath(relative)
    if (
        not relative
        or not relative.isascii()
        or any(ord(character) < 32 or ord(character) == 127 for character in relative)
        or "\\" in relative
        or pure.is_absolute()
        or ".." in pure.parts
        or pure.as_posix() != relative
    ):
        raise ValueError(f"unsafe or non-canonical tracked path: {relative!r}")
    return pure


def iter_package_files(root: Path, excludes: Sequence[str]) -> list[Path]:
    """Return selected Git-tracked files in stable POSIX-path order."""

    root = root.resolve()
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"cannot enumerate Git-tracked package files: {detail or 'git ls-files failed'}")
    try:
        names = completed.stdout.decode("utf-8").split("\0")
    except UnicodeDecodeError as exc:
        raise ValueError("Git-tracked package paths must be UTF-8 ASCII-compatible") from exc

    selected: list[Path] = []
    for relative in names:
        if not relative:
            continue
        pure = _validate_tracked_name(relative)
        safe_example = _is_safe_example(relative)
        if _is_sensitive_path(relative) and (not safe_example or _has_sensitive_suffix(relative)):
            raise ValueError(f"sensitive tracked path is forbidden in release package: {relative}")
        ignored_patterns = SAFE_EXAMPLE_EXCLUDE_PATTERNS if safe_example else frozenset()
        if _matches_exclude(relative, excludes, ignored_patterns):
            continue
        candidate = root.joinpath(*pure.parts)
        if candidate.is_symlink():
            raise ValueError(f"symlink is not allowed in release package: {relative}")
        if not candidate.is_file():
            raise ValueError(f"tracked package member is missing or non-regular: {relative}")
        selected.append(candidate)

    return sorted(selected, key=lambda path: _relative_posix(root, path))


def build_archive(root: Path, output: Path, files: Sequence[Path]) -> str:
    """Write a deterministic ZIP archive and return its SHA-256 digest."""

    root = root.resolve()
    ordered: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for original in files:
        path = Path(original)
        relative = _relative_posix(root, path)
        if relative in seen:
            raise ValueError(f"duplicate package path: {relative}")
        if path.is_symlink():
            raise ValueError(f"symlink is not allowed in release package: {relative}")
        if not path.is_file():
            raise ValueError(f"package member is not a regular file: {relative}")
        seen.add(relative)
        ordered.append((relative, path))
    ordered.sort(key=lambda item: item[0])

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_STORED,
            allowZip64=False,
            strict_timestamps=True,
        ) as archive:
            for relative, path in ordered:
                info = zipfile.ZipInfo(relative, date_time=FIXED_ZIP_TIME)
                info.create_system = CANONICAL_CREATE_SYSTEM
                info.create_version = CANONICAL_ZIP_VERSION
                info.extract_version = CANONICAL_ZIP_VERSION
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = FIXED_FILE_MODE << 16
                info.internal_attr = 0
                info.flag_bits = CANONICAL_FLAG_BITS
                info.extra = b""
                info.comment = b""
                archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_STORED)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()

    return hashlib.sha256(output.read_bytes()).hexdigest()


def compare_archive(root: Path, archive: Path, files: Sequence[Path]) -> list[str]:
    """Compare archive members and bytes with the selected source files."""

    root = root.resolve()
    expected = {_relative_posix(root, Path(path)): Path(path) for path in files}
    expected_names = sorted(expected)
    errors: list[str] = []
    try:
        with zipfile.ZipFile(archive) as package:
            infos = package.infolist()
            names = [info.filename for info in infos]
            duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
            if duplicates:
                errors.append(f"duplicate archive members: {duplicates}")

            if names != expected_names:
                errors.append(f"archive member order is not canonical: expected {expected_names}, found {names}")

            actual = set(names)
            missing = sorted(set(expected) - actual)
            unexpected = sorted(actual - set(expected))
            if missing:
                errors.append(f"missing archive members: {missing}")
            if unexpected:
                errors.append(f"unexpected archive members: {unexpected}")

            for info in infos:
                name = info.filename
                pure = PurePosixPath(name)
                if (
                    not name.isascii()
                    or "\\" in name
                    or pure.is_absolute()
                    or ".." in pure.parts
                    or name.endswith("/")
                    or pure.as_posix() != name
                ):
                    errors.append(f"unsafe archive member: {name}")
                    continue
                mode = info.external_attr >> 16
                if info.date_time != FIXED_ZIP_TIME:
                    errors.append(f"archive timestamp is not canonical for {name}: {info.date_time}")
                if mode != FIXED_FILE_MODE:
                    errors.append(f"archive mode/type is not canonical for {name}: {oct(mode)}")
                if info.compress_type != zipfile.ZIP_STORED:
                    errors.append(f"archive compression is not canonical for {name}: {info.compress_type}")
                if info.flag_bits != CANONICAL_FLAG_BITS:
                    errors.append(f"archive name flag bits are not canonical for {name}: {info.flag_bits}")
                if info.create_system != CANONICAL_CREATE_SYSTEM:
                    errors.append(f"archive creator system is not canonical for {name}: {info.create_system}")
                if info.create_version != CANONICAL_ZIP_VERSION or info.extract_version != CANONICAL_ZIP_VERSION:
                    errors.append(f"archive ZIP version is not canonical for {name}")
                if info.extra or info.comment:
                    errors.append(f"archive extra/comment metadata is not canonical for {name}")
                if name in expected and package.read(info) != expected[name].read_bytes():
                    errors.append(f"changed archive member: {name}")
            if package.comment:
                errors.append("archive comment is not canonical")
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"cannot read archive: {exc}")
    return errors


def _load_project_config() -> Mapping[str, Any]:
    value = json.loads(PROJECT_CONFIG.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("config/project.json must contain an object")
    return value


def main() -> int:
    try:
        project = _load_project_config()
        packaging = project.get("packaging")
        paths = project.get("paths")
        if not isinstance(packaging, dict) or not isinstance(packaging.get("excludes"), list):
            raise ValueError("config/project.json packaging.excludes must be a list")
        excludes = packaging["excludes"]
        if not all(isinstance(pattern, str) and pattern.strip() for pattern in excludes):
            raise ValueError("config/project.json packaging.excludes entries must be non-empty strings")
        if not isinstance(paths, dict) or not isinstance(paths.get("package"), str):
            raise ValueError("config/project.json paths.package must be a string")

        output = ROOT / paths["package"]
        files = iter_package_files(ROOT, excludes)
        digest = build_archive(ROOT, output, files)
        errors = compare_archive(ROOT, output, files)
        if errors:
            print("PACKAGE COMPARISON FAILED", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        print("PACKAGE COMPARISON PASSED")
        print(f"Files: {len(files)}")
        print(f"SHA-256: {digest}")
        print(f"Archive: {output.relative_to(ROOT).as_posix()}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"PACKAGE FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
