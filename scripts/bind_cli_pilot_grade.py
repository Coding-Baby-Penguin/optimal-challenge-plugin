#!/usr/bin/env python3
"""Bind a blinded internal pilot grade to retained CLI identity and timing.

This is an internal pilot receipt, never full behavioral acceptance. The
independent reviewer must audit the grader and timed controller outside this
module; hashes alone do not establish that independence or phase execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.codex_cli_rollout import _records, extract_job


MASK = ("task_quality", "safety_authority", "budget_truthfulness", "failure_visibility")
PHASES = ("setup_started", "install_verified", "prelaunch_snapshotted", "host_completed",
          "identity_verified", "independent_grade_completed")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _object(data: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate pilot JSON key")
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite pilot JSON")))
    _canonical(value)
    if not isinstance(value, dict):
        raise ValueError("pilot artifact must be an object")
    return value


def _load(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    if len(data) > 8_000_000:
        raise ValueError("pilot artifact exceeds review bound")
    return _object(data), data


def _grader_native_judgment(paths: Sequence[Path], root_session_id: str) -> dict:
    for path in paths:
        records = _records(path)
        if records[0]["payload"].get("id") != root_session_id:
            continue
        finals = [record["payload"] for record in records if record.get("type") == "response_item"
                  and record["payload"].get("type") == "message"
                  and record["payload"].get("role") == "assistant"
                  and record["payload"].get("phase") == "final_answer"]
        if len(finals) != 1 or not isinstance(finals[0].get("content"), list):
            raise ValueError("independent grader native final answer is unavailable")
        parts = finals[0]["content"]
        if any(not isinstance(part, dict) or part.get("type") != "output_text" or
               not isinstance(part.get("text"), str) for part in parts):
            raise ValueError("independent grader native final answer is malformed")
        return _object("".join(part["text"] for part in parts).encode("utf-8"))
    raise ValueError("independent grader root rollout is missing")


def _workspace(root: Path) -> dict[str, dict[str, str | None]]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("post-run workspace is missing or linked")
    files: dict[str, dict[str, str | None]] = {}
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("post-run workspace contains a symlink")
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        data = path.read_bytes()
        total += len(data)
        if len(files) >= 500 or total > 8_000_000:
            raise ValueError("post-run workspace exceeds review bound")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            content = None
        files[name] = {"sha256": _sha(data), "text_utf8": content}
    return dict(sorted(files.items()))


def make_blind_packet(identity: Mapping[str, Any], plan: Mapping[str, Any],
                      manifest: Mapping[str, Any], manifest_sha: str,
                      output: bytes, workspace: Path, blind_id: str) -> dict:
    if (identity.get("status") != "identity_activation_verified" or
            identity.get("quality_claim") != "unverified" or
            identity.get("full_acceptance_credit") is not False or
            any(identity.get(field) != plan.get(field) for field in ("run_id", "case_id", "arm_id")) or
            identity.get("pilot_manifest_sha256") != manifest_sha or
            plan.get("manifest_sha256") != manifest_sha or
            manifest.get("pilot_version") != 1 or
            manifest.get("shared_grading_mask") != list(MASK) or
            not isinstance(blind_id, str) or len(blind_id) < 12 or
            any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in blind_id)):
        raise ValueError("blind packet inputs do not bind one frozen pilot run")
    cases = [case for case in manifest.get("cases", []) if isinstance(case, dict)
             and case.get("id") == plan["case_id"]]
    if len(cases) != 1 or not isinstance(cases[0].get("oracle"), str):
        raise ValueError("frozen pilot case or oracle is missing")
    try:
        answer = output.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("native answer must be UTF-8") from exc
    if _sha(output) != identity.get("native", {}).get("output_sha256"):
        raise ValueError("answer differs from exact native output")
    return {"packet_version": 1, "blind_id": blind_id, "case_id": plan["case_id"],
            "prompt": plan["prompt"], "oracle": cases[0]["oracle"],
            "shared_grading_mask": list(MASK), "output": answer,
            "post_workspace": _workspace(workspace), "full_acceptance_credit": False}


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("pilot phase timestamp is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("pilot phase timestamp needs a timezone")
    return parsed


def bind_grade(*, identity_path: Path, plan_path: Path, manifest_path: Path,
               output_path: Path, workspace: Path, packet_path: Path,
               grade_path: Path, timing_path: Path, phases_path: Path,
               audit_path: Path, grader_rollouts: Sequence[Path] = ()) -> dict:
    identity, identity_bytes = _load(identity_path)
    plan, _ = _load(plan_path)
    manifest, manifest_bytes = _load(manifest_path)
    packet, packet_bytes = _load(packet_path)
    grade, grade_bytes = _load(grade_path)
    timing, timing_bytes = _load(timing_path)
    phases, phases_bytes = _load(phases_path)
    audit, _ = _load(audit_path)
    expected_packet = make_blind_packet(identity, plan, manifest, _sha(manifest_bytes),
                                        output_path.read_bytes(), workspace,
                                        packet.get("blind_id"))
    if packet != expected_packet:
        raise ValueError("blind packet differs from native answer, workspace or frozen task")
    if (grade.get("grade_version") != 1 or grade.get("blind_id") != packet["blind_id"] or
            grade.get("packet_sha256") != _sha(packet_bytes) or
            not isinstance(grade.get("grader_id"), str) or not grade["grader_id"].strip() or
            grade.get("full_acceptance_credit") is not False):
        raise ValueError("independent grade does not bind the blind packet")
    quality = grade.get("task_quality")
    if (not isinstance(quality, (int, float)) or isinstance(quality, bool) or
            not math.isfinite(quality) or not 0 <= quality <= 4 or
            any(type(grade.get(field + "_pass")) is not bool for field in MASK[1:])):
        raise ValueError("pilot grade is missing a shared quality or safety judgment")
    rationale = grade.get("rationale")
    if not isinstance(rationale, dict) or any(not isinstance(rationale.get(field), str)
                                              or not rationale[field].strip() for field in MASK):
        raise ValueError("pilot grade needs rationale for every shared dimension")
    usage = grade.get("grader_usage")
    if not isinstance(usage, dict) or usage.get("provenance") not in {"observed", "human", "unavailable"}:
        raise ValueError("grader usage provenance is missing")
    if usage["provenance"] == "observed":
        if not grader_rollouts:
            raise ValueError("observed grader usage needs retained native rollouts")
        grader_native = extract_job(grader_rollouts)
        if (usage.get("native_sha256s") != [item["native_sha256"] for item in grader_native["sessions"]] or
                any(usage.get(field) != grader_native["usage"][field] for field in
                    ("input_tokens", "output_tokens")) or
                _grader_native_judgment(grader_rollouts, grader_native["root_session_id"]) !=
                {key: value for key, value in grade.items() if key != "grader_usage"} or
                grader_native["root_session_id"] == identity.get("native", {}).get("root_session_id")):
            raise ValueError("observed grader usage differs from independent native trace")
    elif usage["provenance"] == "human":
        attention = usage.get("attention_seconds")
        if (grader_rollouts or not isinstance(attention, (int, float)) or isinstance(attention, bool) or
                not math.isfinite(attention) or attention < 0):
            raise ValueError("human grader needs reviewed attention time and no model rollout")
    elif grader_rollouts:
        raise ValueError("unclaimed grader native rollouts cannot be ignored")
    if (timing.get("status") != "completed" or timing.get("returncode") != 0 or
            not isinstance(timing.get("outer_whole_job_wall_seconds"), (int, float)) or
            not math.isfinite(timing["outer_whole_job_wall_seconds"]) or
            timing["outer_whole_job_wall_seconds"] < 0):
        raise ValueError("whole-job controller did not complete inside the timer")
    phase_entries = phases.get("events")
    if not isinstance(phase_entries, list) or [entry.get("phase") for entry in phase_entries
                                                if isinstance(entry, dict)] != list(PHASES) or len(phase_entries) != len(PHASES):
        raise ValueError("timed controller phase log is incomplete or out of order")
    start, end = _time(timing.get("started_utc")), _time(timing.get("ended_utc"))
    stamps = [_time(entry.get("utc")) for entry in phase_entries]
    if not (start <= stamps[0] <= stamps[-1] <= end) or stamps != sorted(stamps):
        raise ValueError("pilot phases fall outside the retained whole-job timer")
    elapsed_utc = (end - start).total_seconds()
    if abs(elapsed_utc - timing["outer_whole_job_wall_seconds"]) > max(2.0, elapsed_utc * 0.05):
        raise ValueError("monotonic duration differs materially from controller UTC interval")
    argv_path = timing_path.with_suffix(".argv.json")
    if _sha(argv_path.read_bytes()) != timing.get("command_argv_sha256"):
        raise ValueError("timed controller argv differs from its receipt")
    for label in ("stdout", "stderr"):
        name = timing.get(label + "_path")
        if not isinstance(name, str) or Path(name).name != name or not name:
            raise ValueError("timed controller log path is unsafe")
        log_path = timing_path.parent / name
        if log_path.is_symlink() or _sha(log_path.read_bytes()) != timing.get(label + "_sha256"):
            raise ValueError("timed controller log differs from its receipt")
    required_audit = {"audit_version": 1, "identity_sha256": _sha(identity_bytes),
                      "packet_sha256": _sha(packet_bytes), "grade_sha256": _sha(grade_bytes),
                      "timing_sha256": _sha(timing_bytes), "phase_log_sha256": _sha(phases_bytes),
                      "command_argv_sha256": timing["command_argv_sha256"]}
    if any(audit.get(key) != value for key, value in required_audit.items()):
        raise ValueError("independent review audit differs from retained artifact bytes")
    if (not isinstance(audit.get("reviewer_id"), str) or not audit["reviewer_id"].strip() or
            audit["reviewer_id"] == grade["grader_id"] or
            audit.get("grader_id") != grade["grader_id"] or
            not isinstance(audit.get("review_note"), str) or not audit["review_note"].strip()):
        raise ValueError("independent controller and grader review is unverified")
    review_scope = audit.get("review_scope")
    if review_scope not in {"mechanical_evidence_audit_after_timed_grade", "substantive_review_after_timer"}:
        raise ValueError("post-timer review scope is unverified")
    native_tokens = identity["native"]["usage"]["whole_job_tokens"]
    ambient_sha = identity["registry_inventory"]["ambient_plugin_inventory_sha256"]
    if (type(native_tokens) is not int or native_tokens < 0 or
            not isinstance(ambient_sha, str) or len(ambient_sha) != 64 or
            any(char not in "0123456789abcdef" for char in ambient_sha)):
        raise ValueError("native usage or ambient plugin identity is malformed")
    total_tokens = (native_tokens + usage["input_tokens"] + usage["output_tokens"]
                    if usage["provenance"] == "observed" else native_tokens
                    if usage["provenance"] == "human" else None)
    timed_review_complete = review_scope == "mechanical_evidence_audit_after_timed_grade"
    return {"status": "pilot_grade_structurally_bound", "review_provenance": "trusted-caller-attestation-requires-human-audit",
            "full_acceptance_credit": False, "run_id": plan["run_id"], "case_id": plan["case_id"],
            "arm_id": plan["arm_id"], "blind_id": packet["blind_id"],
            "registry_ambient_sha256": ambient_sha,
            "grade_sha256": _sha(grade_bytes), "task_quality": quality,
            **{field + "_pass": grade[field + "_pass"] for field in MASK[1:]},
            "native_job_tokens": native_tokens,
            "whole_job_tokens": total_tokens,
            "whole_job_tokens_status": "observed" if total_tokens is not None else "incomplete_grader_usage",
            "grader_attention_seconds": usage.get("attention_seconds") if usage["provenance"] == "human" else None,
            "raw_outer_timer_seconds": timing["outer_whole_job_wall_seconds"],
            "outer_whole_job_wall_seconds": timing["outer_whole_job_wall_seconds"] if timed_review_complete else None,
            "timing_scope": "timed_grade_with_post_timer_mechanical_audit" if timed_review_complete else
                            "incomplete_post_timer_substantive_review"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("identity", "plan", "manifest", "output-text", "workspace", "packet", "grade",
                 "timing", "phases", "audit", "receipt"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--grader-rollout", action="append", type=Path, default=[])
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error("refusing to overwrite a pilot grade receipt")
    try:
        result = bind_grade(identity_path=args.identity, plan_path=args.plan,
                            manifest_path=args.manifest, output_path=args.output_text,
                            workspace=args.workspace, packet_path=args.packet,
                            grade_path=args.grade, timing_path=args.timing,
                            phases_path=args.phases, audit_path=args.audit,
                            grader_rollouts=args.grader_rollout)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, json.JSONDecodeError) as exc:
        result = {"status": "blocked", "errors": [f"pilot grade evidence invalid: {type(exc).__name__}: {exc}"]}
    args.receipt.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "errors": result.get("errors", [])}))
    return 0 if result["status"] == "pilot_grade_structurally_bound" else 1


if __name__ == "__main__":
    raise SystemExit(main())
