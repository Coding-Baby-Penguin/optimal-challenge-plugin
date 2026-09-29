#!/usr/bin/env python3
"""Bind one real Codex CLI preflight's native, raw, grade and manifest bytes.

This is a structural host-recorder proof only. It never awards product quality,
desktop acceptance or an independent grader credential.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.codex_cli_rollout import extract_job
from scripts.evaluation_evidence import _strict_json


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Mapping[str, Any]:
    return _strict_json(path.read_bytes())


def verify_cli_preflight(manifest_path: Path, raw_path: Path, grade_path: Path,
                         bundle_path: Path, rollouts: Sequence[Path]) -> dict[str, Any]:
    manifest, raw, grade, bundle = (_load(p) for p in
                                    (manifest_path, raw_path, grade_path, bundle_path))
    audit = extract_job(rollouts)
    errors: list[str] = []
    if manifest.get("preflight_version") != 1 or bundle.get("preflight_version") != 1:
        errors.append("unsupported preflight schema version")
    expected = {"host": "codex-cli", "surface": "codex-cli-local", "host_source": "codex-cli",
                "host_version": audit["host_version"], "model": audit["model"], "reasoning": audit["reasoning"]}
    for field, value in expected.items():
        if manifest.get(field) != value or raw.get(field) != value:
            errors.append(f"{field} does not match exact native CLI observation")
    for field in ("task_id", "subject_archive_sha256", "installed_read_back"):
        if not manifest.get(field) or raw.get(field) != manifest.get(field):
            errors.append(f"{field} identity or installed read-back is missing or changed")
    if raw.get("session_id") != audit["root_session_id"]:
        errors.append("raw root session differs from native CLI")
    if raw.get("terminal_status") != "completed" or audit["terminal_status"] != "completed":
        errors.append("native task terminal completion is missing")
    output = raw.get("output")
    if not isinstance(output, str) or hashlib.sha256(output.encode("utf-8")).hexdigest() != audit["output_sha256"]:
        errors.append("raw output differs from native CLI final answer")
    for field in ("usage", "wall_seconds", "tool_events", "tool_events_complete"):
        if raw.get(field) != audit.get(field):
            errors.append(f"raw {field} differs from native extraction")
    if not isinstance(grade.get("grader_id"), str) or not grade["grader_id"].strip() or grade.get("grader_id") == raw.get("recorder_id"):
        errors.append("separate grader identity is missing")
    if grade.get("task_id") != manifest.get("task_id") or grade.get("raw_sha256") != _sha(raw_path) or grade.get("output_sha256") != audit["output_sha256"]:
        errors.append("grade is not bound to this exact host output and task")
    if grade.get("quality_claim") != "unverified" or bundle.get("quality_claim") != "unverified":
        errors.append("preflight cannot award a quality claim")
    for field, path in (("manifest_sha256", manifest_path), ("raw_sha256", raw_path),
                        ("grade_sha256", grade_path)):
        if bundle.get(field) != _sha(path):
            errors.append(f"bundle {field} differs from retained bytes")
    if bundle.get("task_id") != manifest.get("task_id") or bundle.get("native_rollout_sha256s") != [
            item["native_sha256"] for item in audit["sessions"]]:
        errors.append("bundle task or native rollout identities differ")
    return {"status": "structurally_verified" if not errors else "blocked", "host": "codex-cli",
            "surface": "codex-cli-local", "quality_claim": "unverified", "desktop_acceptance": "unverified",
            "task_id": manifest.get("task_id"), "root_session_id": audit["root_session_id"],
            "whole_job_input_tokens": audit["usage"]["input_tokens"],
            "whole_job_output_tokens": audit["usage"]["output_tokens"],
            "native_rollout_sha256s": [item["native_sha256"] for item in audit["sessions"]],
            "errors": errors}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("manifest", "raw", "grade", "bundle"):
        parser.add_argument("--" + field, required=True, type=Path)
    parser.add_argument("--rollout", action="append", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_cli_preflight(args.manifest, args.raw, args.grade,
                                      args.bundle, args.rollout)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        result = {"status": "blocked", "quality_claim": "unverified", "errors": [str(exc)]}
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result["status"] == "structurally_verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
