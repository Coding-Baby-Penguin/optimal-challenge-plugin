#!/usr/bin/env python3
"""Verify one disposable Codex CLI pilot input and native skill activation.

The resulting receipt is structural host evidence, not an independent grade or
comparative acceptance decision. Every run must have a new prepared home.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.codex_cli_rollout import extract_job
from scripts.verify_subject import _file_under, _sha, _tree_members, verify_codex_registry_read_back, verify_subject


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _no_symlink_components(path: Path, anchor: Path) -> bool:
    current = anchor
    if current.is_symlink():
        return False
    for part in path.relative_to(anchor).parts:
        current = current / part
        if current.is_symlink():
            return False
    return True


def verify_run_scoping(output_root: Path, host_home: Path, installed_root: Path,
                       registry_json: Path, stream: Path, rollouts: Sequence[Path]) -> list[str]:
    """Reject a static Task 7 cache/registry or reused native bytes as run proof."""
    errors = []
    try:
        output = Path(output_root).resolve(strict=True)
        home = Path(host_home).resolve(strict=True)
        installed = Path(installed_root).resolve(strict=True)
        registry = Path(registry_json).resolve(strict=True)
        host_stream = Path(stream).resolve(strict=True)
        native = [Path(path).resolve(strict=True) for path in rollouts]
        if home != output / "host-home" or not _inside(installed, home / "plugins" / "cache"):
            errors.append("installed plugin must be inside this per-run host home")
        if not _inside(registry, output) or not _inside(host_stream, output):
            errors.append("registry and stream evidence must belong to this run directory")
        if not native or any(not _inside(path, home / "sessions") for path in native):
            errors.append("native rollouts must come from this per-run host home")
        for path, anchor in [(Path(host_home), Path(output_root)), (Path(installed_root), Path(host_home)),
                             (Path(registry_json), Path(output_root)), (Path(stream), Path(output_root))]:
            if not _no_symlink_components(path.absolute(), anchor.absolute()):
                errors.append("run path crosses a symlink")
        for path in rollouts:
            if not _no_symlink_components(Path(path).absolute(), Path(host_home).absolute()):
                errors.append("native rollout path crosses a symlink")
    except (OSError, RuntimeError, TypeError, ValueError):
        errors.append("per-run host home or evidence path is unavailable")
    return errors


def _strict_object(data: bytes) -> dict[str, Any]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=unique,
                       parse_constant=lambda item: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def verify_skill_activation(stream: Path, installed_skill: Path, native_audit: dict) -> dict:
    """Bind a completed native CLI file read and final answer to installed SKILL bytes."""
    data = stream.read_bytes()
    if len(data) > 25_000_000:
        raise ValueError("CLI stream exceeds review bound")
    events = [_strict_object(line) for line in data.splitlines() if line.strip()]
    starts = [event.get("thread_id") for event in events if event.get("type") == "thread.started"]
    if len(starts) != 1 or starts[0] != native_audit.get("root_session_id"):
        raise ValueError("CLI stream does not match native root session")
    if sum(event.get("type") == "turn.completed" for event in events) != 1:
        raise ValueError("CLI stream lacks one terminal turn")
    expected = installed_skill.read_bytes()
    command_pattern = re.compile(r"Get-Content\s+-LiteralPath\s+['\"]" + re.escape(str(installed_skill.resolve())) + r"['\"]", re.IGNORECASE)
    matches = []
    for event in events:
        item = event.get("item")
        if event.get("type") != "item.completed" or not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        command = item.get("command")
        output = item.get("aggregated_output")
        # CLI command_execution escapes Windows separators a second time in
        # this observed native stream schema; normalize only that spelling.
        normalized_command = command.replace("\\\\", "\\") if isinstance(command, str) else ""
        if command_pattern.search(normalized_command) and item.get("status") == "completed" and item.get("exit_code") == 0 and isinstance(output, str):
            normalized = output.replace("\r\n", "\n").encode("utf-8")
            if normalized == expected:
                matches.append(item.get("id"))
    if not matches:
        raise ValueError("native CLI stream has no successful read of exact installed skill bytes")
    messages = [item.get("text") for event in events if event.get("type") == "item.completed"
                for item in [event.get("item")] if isinstance(item, dict) and item.get("type") == "agent_message"]
    if not messages or not isinstance(messages[-1], str) or hashlib.sha256(messages[-1].encode("utf-8")).hexdigest() != native_audit.get("output_sha256"):
        raise ValueError("CLI final output differs from native rollout")
    return {"stream_sha256": hashlib.sha256(data).hexdigest(), "session_id": starts[0],
            "skill_read_event_ids": matches, "installed_skill_sha256": hashlib.sha256(expected).hexdigest(),
            "output_sha256": native_audit["output_sha256"]}


def validate_surface_audit(surface: dict, native: dict) -> list[str]:
    if surface.get("surface_version") != 1 or surface.get("native_source") != "codex-cli-rollout-v1":
        return ["CLI pilot surface pin is invalid"]
    for field in ("host", "host_source", "surface", "host_version", "model", "reasoning"):
        if native.get(field) != surface.get(field):
            return [f"native CLI {field} differs from frozen pilot surface"]
    if native.get("usage", {}).get("model_calls") is not None or surface.get("model_calls_observable") is not False:
        return ["unobserved CLI model-call count must remain unavailable"]
    return []


def verify_pilot_run(plan_path: Path, pilot_manifest_path: Path, surface_path: Path, subject_path: Path, source_root: Path, archive: Path,
                     installed_root: Path, registry_json: Path, registry_source: Path,
                     stream: Path, rollouts: Sequence[Path]) -> dict:
    plan_bytes = plan_path.read_bytes()
    plan = _strict_object(plan_bytes)
    pilot_manifest_bytes = pilot_manifest_path.read_bytes()
    pilot_manifest = _strict_object(pilot_manifest_bytes)
    surface_bytes = surface_path.read_bytes()
    surface = _strict_object(surface_bytes)
    subject = _strict_object(subject_path.read_bytes())
    output_root = plan_path.parent.resolve(strict=True)
    home = output_root / "host-home"
    errors = verify_run_scoping(output_root, home, installed_root, registry_json, stream, rollouts)
    matching_cases = [case for case in pilot_manifest.get("cases", [])
                      if isinstance(case, dict) and case.get("id") == plan.get("case_id")]
    if (_sha(pilot_manifest_bytes) != plan.get("manifest_sha256") or
            pilot_manifest.get("pilot_version") != 1 or len(matching_cases) != 1 or
            plan.get("arm_id") not in pilot_manifest.get("arms", [])):
        errors.append("run plan differs from frozen pilot manifest")
    else:
        case = matching_cases[0]
        expected_files = {} if case.get("workspace") is None else pilot_manifest.get("workspace_file_sha256s", {}).get(case["workspace"])
        if (plan.get("prompt") != pilot_manifest.get("task_prompt_prefix", "") + "\n\n" + case.get("prompt", "") or
                plan.get("workspace_file_sha256s") != expected_files or
                plan.get("full_acceptance_credit") is not False):
            errors.append("run prompt or seed inventory differs from frozen pilot case")
    if plan.get("status") != "prepared-unrun" or plan.get("host_home_relpath") != "host-home" or plan.get("host_home_path_sha256") != _sha(str(home.resolve()).encode("utf-8")):
        errors.append("run plan does not bind this fresh host home")
    if plan.get("arm_id") != subject.get("arm_id") or plan.get("host") != "codex-cli" or plan.get("surface") != "codex-cli-local":
        errors.append("run plan and subject identify different arms or surfaces")
    if len(str(plan.get("run_id", ""))) < 3 or not (output_root / "workspace").is_dir():
        errors.append("run identity or disposable workspace is missing")
    if errors:
        return {"status": "blocked", "errors": errors}
    identity, problems = verify_subject(subject, source_root, archive, installed_root)
    errors.extend(problems)
    registry_bytes = registry_json.read_bytes()
    registry = _strict_object(registry_bytes)
    if len(registry.get("installed", [])) != 1:
        errors.append("per-run registry must contain exactly one installed plugin")
    read_back, problems = verify_codex_registry_read_back(
        registry, name=subject["plugin_name"], version=subject["plugin_version"],
        marketplace_name=subject["marketplace_name"], expected_source=registry_source)
    errors.extend(problems)
    members = subject.get("member_sha256s", {})
    try:
        if not _inside(registry_source.resolve(strict=True), output_root):
            errors.append("per-run registry source must belong to this run directory")
        elif _tree_members(registry_source) != set(members) or any(_sha(_file_under(registry_source, name)) != digest for name, digest in members.items()):
            errors.append("per-run registry source bytes differ from exact archive")
    except (OSError, RuntimeError, ValueError):
        errors.append("per-run registry source cannot be verified")
    native = extract_job(rollouts)
    errors.extend(validate_surface_audit(surface, native))
    activation = verify_skill_activation(stream, installed_root / "skills/optimal-challenge/SKILL.md", native)
    if errors:
        return {"status": "blocked", "errors": errors}
    return {
        "status": "identity_activation_verified", "quality_claim": "unverified",
        "full_acceptance_credit": False, "run_id": plan["run_id"], "case_id": plan["case_id"],
        "run_plan_sha256": _sha(plan_bytes), "pilot_manifest_sha256": _sha(pilot_manifest_bytes),
        "surface_manifest_sha256": _sha(surface_bytes),
        "arm_id": plan["arm_id"], "archive_sha256": identity["archive_sha256"],
        "subject_manifest_sha256": _sha(subject_path.read_bytes()),
        "host_home_path_sha256": plan["host_home_path_sha256"],
        "installed_member_count": identity["member_count"],
        "installed_member_map_sha256": _sha(json.dumps(members, sort_keys=True, separators=(",", ":")).encode("utf-8")),
        "registry_json_sha256": _sha(registry_bytes), "registry_identity": read_back,
        "native": native, "activation": activation,
        "outer_whole_job_wall_seconds": None, "independent_grade": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "pilot-manifest", "surface", "subject", "source-root", "archive", "installed-root", "registry-json", "registry-source", "stream", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--rollout", action="append", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite a prior pilot verification")
    try:
        result = verify_pilot_run(args.plan, args.pilot_manifest, args.surface, args.subject, args.source_root, args.archive,
                                  args.installed_root, args.registry_json, args.registry_source,
                                  args.stream, args.rollout)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        result = {"status": "blocked", "errors": [f"pilot evidence invalid: {type(exc).__name__}: {exc}"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "errors": result.get("errors", []), "output": str(args.output)}))
    return 0 if result["status"] == "identity_activation_verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
