#!/usr/bin/env python3
"""Prepare one disposable CLI pilot task from a frozen, independently authored seed.

This command does not invoke a host, grade an answer, or verify a plugin install.
Its output is only a run input for a separate timed host controller.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ARMS = frozenset({"A", "B", "C", "D"})
SAFE_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relative(name: str) -> Path:
    if not isinstance(name, str) or "\\" in name or not name:
        raise ValueError("seed member has an unsafe path")
    parts = name.split("/")
    if any(part in {".", ".."} or not SAFE_PART.fullmatch(part) for part in parts):
        raise ValueError("seed member has an unsafe path")
    return Path(*parts)


def _read_seed(seed_root: Path, workspace: str, member: str) -> bytes:
    relative = _safe_relative(workspace) / _safe_relative(member)
    source = seed_root / relative
    current = seed_root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError("seed member crosses a symlink")
    if not source.is_file() or source.stat().st_size > 1024 * 1024:
        raise ValueError("seed member is absent or oversized")
    return source.read_bytes()


def prepare_run(manifest_path: Path, expected_manifest_sha256: str, seed_root: Path,
                case_id: str, arm: str, run_id: str, output_root: Path) -> dict:
    """Verify frozen inputs and copy only listed seed members to one new workspace."""
    if not SHA256.fullmatch(expected_manifest_sha256):
        raise ValueError("expected manifest SHA-256 is invalid")
    manifest_bytes = manifest_path.read_bytes()
    if _sha(manifest_bytes) != expected_manifest_sha256:
        raise ValueError("pilot manifest differs from its frozen SHA-256")
    manifest = json.loads(manifest_bytes)
    if manifest.get("pilot_version") != 1 or manifest.get("status") != "frozen-before-first-run":
        raise ValueError("pilot manifest is not the frozen version")
    if arm not in ARMS or arm not in manifest.get("arms", []):
        raise ValueError("pilot arm is not in the frozen manifest")
    if not SAFE_PART.fullmatch(run_id) or not SAFE_PART.fullmatch(case_id):
        raise ValueError("run or case ID is unsafe")
    cases = [item for item in manifest.get("cases", []) if item.get("id") == case_id]
    if len(cases) != 1:
        raise ValueError("pilot case ID is absent or duplicated")
    case = cases[0]
    prompt = case.get("prompt")
    prefix = manifest.get("task_prompt_prefix")
    if not isinstance(prompt, str) or not prompt or not isinstance(prefix, str) or not prefix:
        raise ValueError("pilot task prompt is incomplete")
    workspace = case.get("workspace")
    expected = {} if workspace is None else manifest.get("workspace_file_sha256s", {}).get(workspace)
    if not isinstance(expected, dict) or (workspace is not None and not expected):
        raise ValueError("pilot workspace file inventory is missing")
    verified: dict[str, bytes] = {}
    for member, digest in expected.items():
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ValueError("pilot seed hash is invalid")
        data = _read_seed(seed_root, workspace, member)
        if _sha(data) != digest:
            raise ValueError("pilot seed bytes differ from frozen manifest")
        verified[member] = data
    if output_root.exists():
        raise ValueError("pilot output must be a fresh directory")
    run_workspace = output_root / "workspace"
    run_workspace.mkdir(parents=True)
    (output_root / "host-home").mkdir()
    for member, data in verified.items():
        destination = run_workspace / _safe_relative(member)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    plan = {
        "schema_version": 1, "status": "prepared-unrun", "full_acceptance_credit": False,
        "host": manifest.get("host"), "surface": manifest.get("surface"),
        "case_id": case_id, "arm_id": arm, "run_id": run_id,
        "manifest_sha256": expected_manifest_sha256,
        "host_home_relpath": "host-home",
        "host_home_path_sha256": _sha(str((output_root / "host-home").resolve()).encode("utf-8")),
        "workspace_file_sha256s": {member: _sha(data) for member, data in verified.items()},
        "prompt": prefix + "\n\n" + prompt,
        "outer_wall_seconds": None, "installed_identity": None, "native_audit": None,
        "grade": None,
    }
    (output_root / "run-plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--seed-root", required=True, type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        plan = prepare_run(args.manifest, args.expected_manifest_sha256, args.seed_root,
                           args.case_id, args.arm, args.run_id, args.output_root)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(1, f"pilot preparation blocked: {type(exc).__name__}: {exc}\n")
    print(json.dumps({key: plan[key] for key in ("status", "case_id", "arm_id", "run_id", "manifest_sha256")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
