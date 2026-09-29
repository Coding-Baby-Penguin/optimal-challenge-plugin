#!/usr/bin/env python3
"""Build exact B/C/D evaluation archives from one committed candidate tree.

Outputs are local staging artifacts. Installation and host behavior remain
unverified until a separate read-back verifies each isolated host cache.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from package_release import (
    SAFE_EXAMPLE_EXCLUDE_PATTERNS, _has_sensitive_suffix, _is_safe_example, _is_sensitive_path,
    _matches_exclude, _matches_runtime_include, _validate_tracked_name,
    build_archive, compare_archive,
)
from verify_subject import CRITICAL_POLICY_PATHS


ROOT = Path(__file__).resolve().parents[1]
OVERLAY_PREFIX = "tests/subjects/overrides"
COMMON_OVERLAYS = (
    "README.md",
    "config/orchestration.json",
    "skills/optimal-challenge/references/team-orchestration.md",
    "skills/optimal-challenge/references/context-management.md",
    "skills/optimal-challenge/references/cost-quality-routing.md",
    "skills/optimal-challenge/references/premise-validation.md",
    "skills/optimal-challenge/references/high-cost-research.md",
    "skills/optimal-challenge/references/team-continuity.md",
)
OVERLAYS = {
    "B": ("skills/optimal-challenge/SKILL.md", *COMMON_OVERLAYS,
          "skills/optimal-challenge/references/delegation-budget.md"),
    "C": ("skills/optimal-challenge/SKILL.md", *COMMON_OVERLAYS),
    "D": (),
}


def _git(*arguments: str) -> bytes:
    completed = subprocess.run(["git", "-C", str(ROOT), *arguments],
                               capture_output=True, check=False)
    if completed.returncode:
        raise ValueError("Git subject source cannot be read: " +
                         completed.stderr.decode("utf-8", errors="replace").strip())
    return completed.stdout


def _tree(commit: str) -> dict[str, tuple[str, str]]:
    entries: dict[str, tuple[str, str]] = {}
    for item in _git("ls-tree", "-r", "-z", commit).split(b"\0"):
        if not item:
            continue
        header, name = item.split(b"\t", 1)
        mode, kind, blob = header.decode("ascii").split(" ")
        path = name.decode("utf-8")
        _validate_tracked_name(path)
        if kind != "blob" or path in entries:
            raise ValueError("unsupported or duplicate committed subject path: " + path)
        entries[path] = (mode, blob)
    return entries


def _selected(tree: dict[str, tuple[str, str]], project: dict) -> list[str]:
    packaging = project["packaging"]
    includes = packaging["runtime_includes"]
    excludes = packaging["excludes"]
    selected = []
    for path, (mode, _) in tree.items():
        safe_example = _is_safe_example(path)
        if _is_sensitive_path(path) and (not safe_example or _has_sensitive_suffix(path)):
            raise ValueError("sensitive committed path is forbidden: " + path)
        ignored = SAFE_EXAMPLE_EXCLUDE_PATTERNS if safe_example else frozenset()
        if not _matches_runtime_include(path, includes) or _matches_exclude(path, excludes, ignored):
            continue
        if mode != "100644" and mode != "100755":
            raise ValueError("non-regular committed runtime member: " + path)
        selected.append(path)
    for pattern in includes:
        if not any(_matches_runtime_include(path, [pattern]) for path in selected):
            raise ValueError("unmatched runtime include: " + pattern)
    return sorted(selected)


def _overlay_source(arm: str, path: str) -> str:
    if path == "skills/optimal-challenge/SKILL.md":
        return f"{OVERLAY_PREFIX}/{arm}-SKILL.md"
    return f"{OVERLAY_PREFIX}/{arm}/{path}"


def build_subjects(commit: str, output_root: Path) -> dict[str, dict]:
    """Stage source, archive and external identity manifests without installing."""
    resolved = _git("rev-parse", "--verify", commit + "^{commit}").decode("ascii").strip()
    if len(resolved) != 40 or any(character not in "0123456789abcdef" for character in resolved):
        raise ValueError("candidate commit must resolve to one full SHA-1")
    tree = _tree(resolved)
    project_path = tree.get("config/project.json")
    if project_path is None:
        raise ValueError("committed project packaging contract is absent")
    project = json.loads(_git("cat-file", "blob", project_path[1]))
    selected = _selected(tree, project)
    if not set(CRITICAL_POLICY_PATHS).issubset(selected):
        raise ValueError("candidate runtime selection lacks critical policy members")
    output_root = Path(output_root).resolve()
    try:
        output_root.relative_to((ROOT / "tmp/quality").resolve())
    except ValueError as exc:
        raise ValueError("subject output must stay inside ignored tmp/quality") from exc
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("subject output directory must be empty")
    output_root.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    for arm, destinations in OVERLAYS.items():
        stage = output_root / arm
        source_root = stage / "source"
        source_root.mkdir(parents=True)
        overlay_hashes = {}
        for path in selected:
            blob = tree[path][1]
            data = _git("cat-file", "blob", blob)
            if path in destinations:
                source_name = _overlay_source(arm, path)
                if source_name not in tree or tree[source_name][0] not in {"100644", "100755"}:
                    raise ValueError("reviewed overlay is absent from candidate commit: " + source_name)
                data = _git("cat-file", "blob", tree[source_name][1])
                overlay_hashes[path] = hashlib.sha256(data).hexdigest()
            target = source_root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        if set(destinations) != set(overlay_hashes):
            raise ValueError("candidate overlay is outside runtime selection")
        archive = stage / f"optimal-challenge-{arm}-{resolved[:12]}.zip"
        files = [source_root / path for path in selected]
        archive_sha = build_archive(source_root, archive, files)
        if compare_archive(source_root, archive, files):
            raise ValueError("candidate archive differs from staged source")
        plugin = json.loads((source_root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        manifest = {
            "subject_version": 1,
            "arm_id": arm,
            "source_kind": "reviewed-candidate-tree",
            "source_identity": (
                {"commit": resolved} if arm == "D" else
                {"base_commit": resolved, "overlay_sha256s": overlay_hashes}
            ),
            "archive_sha256": archive_sha,
            "member_sha256s": {path: hashlib.sha256((source_root / path).read_bytes()).hexdigest()
                               for path in selected},
            "critical_paths": sorted(CRITICAL_POLICY_PATHS),
            "plugin_name": plugin["name"],
            "plugin_version": plugin["version"],
            "marketplace_name": f"quality-{arm}-local",
            "cachebuster": f"candidate-{resolved[:12]}-arm-{arm.lower()}",
            "install_source": "isolated-clean-archive",
            "policy_config_sha256": hashlib.sha256(
                (source_root / "config/orchestration.json").read_bytes()).hexdigest(),
            "evaluation_only": arm != "D",
        }
        (stage / "subject.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
        results[arm] = {"archive": str(archive), "archive_sha256": archive_sha,
                        "manifest": str(stage / "subject.json"),
                        "member_count": len(selected), "source_root": str(source_root)}
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        result = build_subjects(arguments.commit, arguments.output_root)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
