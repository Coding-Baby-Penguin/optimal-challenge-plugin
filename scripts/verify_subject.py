#!/usr/bin/env python3
"""Verify one externally pinned source/archive/installed plugin subject.

The subject manifest lives outside its archive. This checks exact bytes and
member identity; a caller separately verifies release provenance and the host
registry's cachebuster/read-back path.
"""
from __future__ import annotations

import hashlib
import json
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


CRITICAL_POLICY_PATHS = frozenset({
    ".codex-plugin/plugin.json",
    "skills/optimal-challenge/SKILL.md",
    "skills/optimal-challenge/references/routing.md",
    "skills/optimal-challenge/references/context-management.md",
    "skills/optimal-challenge/references/team-continuity.md",
    "skills/optimal-challenge/references/team-orchestration.md",
})
MAX_SUBJECT_BYTES = 100_000_000
BASELINE_CRITICAL_PATHS = frozenset({
    ".codex-plugin/plugin.json",
    "skills/optimal-challenge/SKILL.md",
    "skills/optimal-challenge/references/routing.md",
    "skills/optimal-challenge/references/context-management.md",
})


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _safe_name(name: Any) -> bool:
    if (not isinstance(name, str) or not name or not name.isascii()
            or any(ord(char) < 32 or ord(char) == 127 for char in name)
            or "\\" in name or ":" in name):
        return False
    pure = PurePosixPath(name)
    return not pure.is_absolute() and ".." not in pure.parts and pure.as_posix() == name and not name.endswith("/")


def _file_under(root: Path, name: str) -> bytes:
    path = root.joinpath(*PurePosixPath(name).parts)
    current = root
    for part in PurePosixPath(name).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlink component")
    path.resolve(strict=True).relative_to(root)
    if not path.is_file():
        raise ValueError("missing or non-regular file")
    if path.stat().st_size > MAX_SUBJECT_BYTES:
        raise ValueError("file exceeds bounded subject size")
    return path.read_bytes()


def _tree_members(root: Path) -> set[str]:
    members: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("source tree contains a symlink")
        if path.is_file():
            members.add(path.relative_to(root).as_posix())
    return members


def verify_subject(subject_manifest: Mapping[str, Any], source_root: Path,
                   archive: Path, installed_root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Return byte-bound identity only when every selected and installed file matches."""
    errors: list[str] = []
    if not isinstance(subject_manifest, Mapping) or subject_manifest.get("subject_version") != 1:
        return None, ["subject manifest version or shape is invalid"]
    arm = subject_manifest.get("arm_id")
    source_kind = subject_manifest.get("source_kind")
    archive_sha = subject_manifest.get("archive_sha256")
    source_id = subject_manifest.get("source_identity")
    members = subject_manifest.get("member_sha256s")
    critical = subject_manifest.get("critical_paths")
    if (arm == "A" and source_kind != "published-release-asset") or (arm in {"B", "C", "D"} and source_kind != "reviewed-candidate-tree") or arm not in {"A", "B", "C", "D"}:
        errors.append("subject arm or source kind is unsupported")
    commit_field = "tag_commit" if arm == "A" else "base_commit" if arm in {"B", "C"} else "commit"
    commit_value = source_id.get(commit_field) if isinstance(source_id, Mapping) else None
    if not _is_sha(archive_sha) or not isinstance(commit_value, str) or len(commit_value) != 40 or any(c not in "0123456789abcdef" for c in commit_value):
        errors.append("immutable archive/source identity is missing")
    elif source_kind == "published-release-asset" and source_id.get("release_asset_sha256") != archive_sha:
        errors.append("published release asset identity differs from archive")
    if arm in {"B", "C"}:
        overlays = source_id.get("overlay_sha256s") if isinstance(source_id, Mapping) else None
        if not isinstance(overlays, Mapping) or not overlays or any(
            not _safe_name(name) or not _is_sha(digest) or not isinstance(members, Mapping) or members.get(name) != digest
            for name, digest in overlays.items()
        ):
            errors.append("evaluation overlay identity differs from archive members")
    if not isinstance(members, Mapping) or not members or any(not _safe_name(k) or not _is_sha(v) for k, v in members.items()):
        errors.append("member hash map is malformed")
        members = {}
    expected_critical = BASELINE_CRITICAL_PATHS if source_kind == "published-release-asset" else CRITICAL_POLICY_PATHS
    if not isinstance(critical, list) or set(critical) != expected_critical or len(critical) != len(expected_critical):
        errors.append("critical policy read-back set is incomplete or changed")
    if not expected_critical.issubset(members):
        errors.append("critical policy files are absent from the subject")
    for field in ("plugin_name", "plugin_version", "marketplace_name", "cachebuster", "install_source"):
        if not isinstance(subject_manifest.get(field), str) or not subject_manifest[field].strip():
            errors.append(f"subject {field} is missing")
    if errors:
        return None, errors
    try:
        source_path = Path(source_root)
        install_path = Path(installed_root)
        archive_path = Path(archive)
        if source_path.is_symlink() or install_path.is_symlink() or archive_path.is_symlink():
            return None, ["subject root or archive must not be a symlink"]
        source_path = source_path.resolve(strict=True)
        install_path = install_path.resolve(strict=True)
        if not source_path.is_dir() or not install_path.is_dir() or not archive_path.is_file():
            return None, ["source, archive or installed subject is unavailable"]
        if archive_path.stat().st_size > MAX_SUBJECT_BYTES:
            return None, ["archive exceeds bounded subject size"]
        actual_archive_sha = _sha(archive_path.read_bytes())
        if actual_archive_sha != archive_sha:
            errors.append("archive SHA-256 differs from external subject manifest")
        with zipfile.ZipFile(archive_path) as zipped:
            infos = zipped.infolist()
            names = [info.filename for info in infos]
            if len(infos) > 10000 or sum(info.file_size for info in infos) > MAX_SUBJECT_BYTES:
                errors.append("archive exceeds bounded subject size")
                return None, errors
            if len(names) != len(set(names)) or set(names) != set(members):
                errors.append("archive members are duplicate, missing or unexpected")
            for info in infos:
                name = info.filename
                mode = info.external_attr >> 16
                if not _safe_name(name) or info.is_dir() or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                    errors.append(f"unsafe archive member: {name!r}")
                    continue
                if name in members and _sha(zipped.read(info)) != members[name]:
                    errors.append(f"archive member bytes differ: {name}")
        try:
            if _tree_members(source_path) != set(members):
                errors.append("source tree has missing or unexpected selected members")
        except ValueError as exc:
            errors.append(f"source tree is unsafe: {exc}")
        try:
            if _tree_members(install_path) != set(members):
                errors.append("installed tree has missing or unexpected package members")
        except ValueError as exc:
            errors.append(f"installed tree is unsafe: {exc}")
        for name, expected in members.items():
            try:
                if _sha(_file_under(source_path, name)) != expected:
                    errors.append(f"source bytes differ: {name}")
            except (OSError, RuntimeError, ValueError):
                errors.append(f"source file is missing or unsafe: {name}")
            try:
                if _sha(_file_under(install_path, name)) != expected:
                    errors.append(f"installed bytes differ: {name}")
            except (OSError, RuntimeError, ValueError):
                errors.append(f"installed file is missing or unsafe: {name}")
        try:
            plugin = json.loads(_file_under(install_path, ".codex-plugin/plugin.json"))
            if not isinstance(plugin, Mapping) or plugin.get("name") != subject_manifest["plugin_name"] or plugin.get("version") != subject_manifest["plugin_version"]:
                errors.append("installed plugin name or version differs")
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            errors.append("installed plugin manifest cannot be read")
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        errors.append(f"subject bytes unavailable or malformed: {type(exc).__name__}")
    if errors:
        return None, errors
    return {
        "status": "verified", "arm_id": arm, "source_kind": source_kind,
        "source_commit": commit_value if arm == "D" else None,
        "base_commit": commit_value if arm in {"B", "C"} else None,
        "release_tag_commit": commit_value if source_kind == "published-release-asset" else None,
        "archive_sha256": archive_sha,
        "published_tag_mismatch_members": source_id.get("tag_tree_mismatched_members", []) if source_kind == "published-release-asset" else [],
        "member_count": len(members), "critical_read_back": sorted(expected_critical),
        "plugin_name": subject_manifest["plugin_name"],
        "plugin_version": subject_manifest["plugin_version"],
        "cachebuster": subject_manifest["cachebuster"],
        "cachebuster_registry_status": "label_only_not_host_readback",
    }, []


def verify_codex_registry_read_back(raw: Mapping[str, Any], *, name: str, version: str,
                                    marketplace_name: str, expected_source: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Bind an isolated Codex registry entry without treating labels as host data."""
    entries = raw.get("installed") if isinstance(raw, Mapping) else None
    if not isinstance(entries, list):
        return None, ["Codex registry installed entries are missing"]
    plugin_id = f"{name}@{marketplace_name}"
    matches = [item for item in entries if isinstance(item, Mapping) and item.get("pluginId") == plugin_id]
    if len(matches) != 1:
        return None, ["Codex registry must contain one exact installed plugin identity"]
    item = matches[0]
    source = item.get("source")
    if (item.get("name") != name or item.get("version") != version or
            item.get("marketplaceName") != marketplace_name or
            item.get("installed") is not True or item.get("enabled") is not True or
            not isinstance(source, Mapping) or source.get("source") != "local" or
            not isinstance(source.get("path"), str) or not source["path"]):
        return None, ["Codex registry plugin metadata is stale, disabled or incomplete"]
    if Path(source["path"]).resolve() != Path(expected_source).resolve():
        return None, ["Codex registry source path differs from the isolated subject source"]
    return {"plugin_id": plugin_id, "name": name, "version": version,
            "marketplace_name": marketplace_name, "installed": True, "enabled": True,
            "source_path_sha256": hashlib.sha256(str(Path(expected_source).resolve()).encode("utf-8")).hexdigest()}, []


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("manifest", "source-root", "archive", "installed-root"):
        parser.add_argument("--" + field, type=Path, required=True)
    parser.add_argument("--registry-json", type=Path)
    parser.add_argument("--registry-source-path", type=Path)
    args = parser.parse_args()
    if (args.registry_json is None) != (args.registry_source_path is None):
        parser.error("registry JSON and expected source path must be provided together")
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result, errors = verify_subject(manifest, args.source_root, args.archive, args.installed_root)
        if result is not None and args.registry_json is not None:
            raw_bytes = args.registry_json.read_bytes()
            registry = json.loads(raw_bytes)
            read_back, errors = verify_codex_registry_read_back(
                registry, name=result["plugin_name"], version=result["plugin_version"],
                marketplace_name=manifest["marketplace_name"], expected_source=args.registry_source_path)
            if read_back is not None:
                registry_source = args.registry_source_path.resolve(strict=True)
                members = manifest["member_sha256s"]
                if _tree_members(registry_source) != set(members) or any(
                    _sha(_file_under(registry_source, name)) != digest for name, digest in members.items()
                ):
                    errors.append("Codex registry source tree differs from exact archive members")
                    result = None
                else:
                    result["codex_registry_source_bytes"] = "verified"
            if read_back is not None and result is not None:
                result["codex_registry"] = {**read_back,
                    "registry_evidence_sha256": hashlib.sha256(raw_bytes).hexdigest()}
            else:
                result = None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result, errors = None, [f"subject input is invalid: {type(exc).__name__}"]
    print(json.dumps(result if result is not None else {"status": "blocked", "errors": errors}, indent=2, sort_keys=True))
    return 0 if result is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
