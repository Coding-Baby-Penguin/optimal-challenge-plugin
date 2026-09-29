#!/usr/bin/env python3
"""Capture exact seeded workspace bytes immediately before a timed CLI launch.

Call this from the controller command after home setup and before Codex exec.
The native controller log must establish that ordering; the snapshot alone does
not prove it was the workspace actually passed to the host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .prepare_cli_pilot import _safe_relative, _sha
else:
    from prepare_cli_pilot import _safe_relative, _sha


def snapshot_input(plan_path: Path, manifest_path: Path) -> dict:
    root = plan_path.parent.resolve(strict=True)
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if (not isinstance(plan, dict) or not isinstance(manifest, dict) or
            plan.get("status") != "prepared-unrun" or
            _sha(manifest_bytes) != plan.get("manifest_sha256")):
        raise ValueError("run plan or frozen pilot manifest changed")
    cases = [case for case in manifest.get("cases", []) if isinstance(case, dict) and case.get("id") == plan.get("case_id")]
    if len(cases) != 1:
        raise ValueError("pilot case is missing or duplicated")
    case = cases[0]
    expected = {} if case.get("workspace") is None else manifest.get("workspace_file_sha256s", {}).get(case["workspace"])
    if not isinstance(expected, dict) or expected != plan.get("workspace_file_sha256s"):
        raise ValueError("run seed inventory differs from frozen pilot manifest")
    workspace = root / "workspace"
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError("disposable workspace is absent or symlinked")
    found = {}
    for path in workspace.rglob("*"):
        if path.is_symlink():
            raise ValueError("workspace has a symlink")
        if path.is_file():
            found[path.relative_to(workspace).as_posix()] = path
    if set(found) != set(expected):
        raise ValueError("prelaunch workspace has missing or unexpected files")
    bytes_by_name = {}
    for name, digest in expected.items():
        _safe_relative(name)
        data = found[name].read_bytes()
        if _sha(data) != digest:
            raise ValueError("prelaunch workspace differs from frozen seed bytes")
        bytes_by_name[name] = data
    snapshot_root = root / "prelaunch-input"
    record_path = root / "prelaunch-snapshot.json"
    if snapshot_root.exists() or record_path.exists():
        raise ValueError("prelaunch snapshot must be captured once in a fresh run")
    snapshot_root.mkdir()
    for name, data in bytes_by_name.items():
        destination = snapshot_root / _safe_relative(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    record = {
        "schema_version": 1, "status": "captured-unreviewed",
        "run_id": plan.get("run_id"), "case_id": plan.get("case_id"), "arm_id": plan.get("arm_id"),
        "run_plan_sha256": _sha(plan_bytes), "pilot_manifest_sha256": _sha(manifest_bytes),
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "source_workspace_relpath": "workspace", "snapshot_relpath": "prelaunch-input",
        "file_sha256s": {name: _sha(data) for name, data in bytes_by_name.items()},
    }
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--pilot-manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        record = snapshot_input(args.plan, args.pilot_manifest)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(1, f"prelaunch snapshot blocked: {type(exc).__name__}: {exc}\n")
    print(json.dumps({key: record[key] for key in ("status", "run_id", "case_id", "arm_id")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
