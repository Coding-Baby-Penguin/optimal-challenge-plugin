#!/usr/bin/env python3
"""Build and verify a deterministic Optimal Challenge release archive."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
PROJECT_CONFIG = ROOT / "config" / "project.json"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
FIXED_FILE_MODE = stat.S_IFREG | 0o644


def _relative_posix(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"package file is outside root: {path}") from exc
    if not relative.parts or ".." in relative.parts:
        raise ValueError(f"unsafe package path: {path}")
    return relative.as_posix()


def _matches_exclude(relative: str, excludes: Sequence[str]) -> bool:
    path = PurePosixPath(relative)
    for pattern in excludes:
        normalized = pattern.replace("\\", "/").strip("/")
        if not normalized:
            continue
        if path.match(normalized):
            return True
        prefix = normalized.removesuffix("/**")
        if normalized.endswith("/**") and (relative == prefix or relative.startswith(prefix + "/")):
            return True
    return False


def iter_package_files(root: Path, excludes: Sequence[str]) -> list[Path]:
    """Return the selected regular files in stable POSIX-path order."""

    root = root.resolve()
    selected: list[Path] = []
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for dirname in dirnames:
            candidate = current_path / dirname
            relative = _relative_posix(root, candidate)
            if _matches_exclude(relative, excludes):
                continue
            if candidate.is_symlink():
                raise ValueError(f"symlink is not allowed in release package: {relative}")
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in filenames:
            candidate = current_path / filename
            relative = _relative_posix(root, candidate)
            if _matches_exclude(relative, excludes):
                continue
            if candidate.is_symlink():
                raise ValueError(f"symlink is not allowed in release package: {relative}")
            if not candidate.is_file():
                raise ValueError(f"non-regular file is not allowed in release package: {relative}")
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
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            strict_timestamps=True,
        ) as archive:
            for relative, path in ordered:
                info = zipfile.ZipInfo(relative, date_time=FIXED_ZIP_TIME)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = FIXED_FILE_MODE << 16
                info.flag_bits |= 0x800
                archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()

    return hashlib.sha256(output.read_bytes()).hexdigest()


def compare_archive(root: Path, archive: Path, files: Sequence[Path]) -> list[str]:
    """Compare archive members and bytes with the selected source files."""

    root = root.resolve()
    expected = {_relative_posix(root, Path(path)): Path(path) for path in files}
    errors: list[str] = []
    try:
        with zipfile.ZipFile(archive) as package:
            infos = package.infolist()
            names = [info.filename for info in infos]
            duplicates = sorted({name for name in names if names.count(name) > 1})
            if duplicates:
                errors.append(f"duplicate archive members: {duplicates}")

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
                if pure.is_absolute() or ".." in pure.parts or name.endswith("/"):
                    errors.append(f"unsafe archive member: {name}")
                    continue
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    errors.append(f"symlink archive member: {name}")
                    continue
                if name in expected and package.read(info) != expected[name].read_bytes():
                    errors.append(f"changed archive member: {name}")
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
