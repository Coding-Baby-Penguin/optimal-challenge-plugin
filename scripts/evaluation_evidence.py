"""Process-local trust boundary for recorded behavioral evaluation evidence.

Hashes bind reviewed local files to one run. They are not signatures and do not
defend against hostile code in this Python process or a hostile trusted caller.
"""
from __future__ import annotations

import hashlib
import json
import math
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from scripts.optimal_challenge.evaluation_contracts import _canonical_acceptance, validate_run_bundle


_ISSUER = object()
_ISSUED: dict[int, weakref.ReferenceType[VerifiedEvaluationContext]] = {}
_REVIEWS: dict[str, tuple[str, str, frozenset[str], Mapping[str, Mapping[str, Any]]]] = {}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _strict_json(data: bytes) -> Mapping[str, Any]:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=unique_pairs,
                       parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON value")))
    json.dumps(value, allow_nan=False)
    if not isinstance(value, Mapping):
        raise ValueError("artifact JSON must be an object")
    return value


@dataclass(frozen=True, slots=True, weakref_slot=True)
class VerifiedEvaluationContext:
    manifest_sha256: str
    receipt_sha256: tuple[str, ...]
    verified_artifact_identities: tuple[tuple[str, str], ...]
    bundle_sha256s: tuple[tuple[str, str], ...]
    provenance: str
    issued_at: datetime
    reviewed_recorder_id: str
    raw_grader_identities: tuple[tuple[str, str, str, str, str, str], ...] = field(default=(), repr=False)
    host_task_sessions: tuple[tuple[str, str, str], ...] = field(default=(), repr=False)
    semantic_required_run_ids: tuple[str, ...] = ()
    semantic_observed_run_ids: tuple[str, ...] = ()
    _attestation: object | None = field(default=None, repr=False, compare=False)


def _issue(context: VerifiedEvaluationContext) -> VerifiedEvaluationContext:
    _ISSUED[id(context)] = weakref.ref(context)
    return context


def _is_issued(context: Any) -> bool:
    return (
        type(context) is VerifiedEvaluationContext
        and context._attestation is _ISSUER
        and id(context) in _ISSUED
        and _ISSUED[id(context)]() is context
    )


def register_recorder_review(
    receipt: Mapping[str, Any], *, reviewer_id: str,
    independent_graders: Sequence[str], native_audit: Mapping[str, Mapping[str, Any]],
) -> str:
    """Bind an independently reviewed receipt to this trusted local process.

    The caller must have inspected the recorder/source and receipt origin outside
    this function. This registry is intentionally not restored from receipt JSON.
    """
    recorder_id = receipt.get("recorder_id")
    source_sha = receipt.get("recorder_source_sha256")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip() or reviewer_id == recorder_id:
        raise ValueError("independent reviewer identity is required")
    graders = frozenset(independent_graders)
    if not graders or any(not isinstance(item, str) or not item.strip() or item == recorder_id for item in graders):
        raise ValueError("audited independent grader identities are required")
    if not isinstance(source_sha, str) or source_sha != hashlib.sha256((Path(__file__).parent / "record_acceptance.py").read_bytes()).hexdigest():
        raise ValueError("reviewed recorder source identity does not match current recorder")
    runs = receipt.get("runs")
    if not isinstance(runs, list) or not isinstance(native_audit, Mapping):
        raise ValueError("native event audit must cover every receipt run")
    run_ids = {entry.get("run_id") for entry in runs if isinstance(entry, Mapping) and isinstance(entry.get("run_id"), str)}
    if len(run_ids) != len(runs) or set(native_audit) != run_ids:
        raise ValueError("native event audit must cover each unique run identity")
    required = {"native_sha256", "native_source", "task_id", "session_id", "host", "host_version", "host_source", "surface", "model", "reasoning", "archive_sha256", "terminal_status", "usage", "wall_seconds", "critical_path_seconds", "tool_events", "tool_events_complete", "output_sha256", "semantic_trace_sha256"}
    expected_native_source = {
        "codex-desktop": "codex-desktop-event-v1",
        "codex-cli": "codex-cli-rollout-v1",
        "claude-code": "claude-code-event-v1",
    }.get(receipt.get("host"))
    if expected_native_source is None:
        raise ValueError("native event source is unsupported for this exact host")
    for entry in runs:
        observed = native_audit[entry["run_id"]]
        if not isinstance(observed, Mapping) or set(observed) != required or observed.get("native_sha256") != (entry.get("native") or {}).get("sha256") or observed.get("native_source") != expected_native_source:
            raise ValueError("native review does not bind the exact retained event bytes and observations")
    digest = _digest(receipt)
    frozen_audit = json.loads(json.dumps(native_audit, sort_keys=True, allow_nan=False))
    _REVIEWS[digest] = (reviewer_id, source_sha, graders, frozen_audit)
    return digest


def combine_verified_contexts(*contexts: VerifiedEvaluationContext) -> VerifiedEvaluationContext:
    """Combine independently verified arms without accepting caller-made context."""
    if len(contexts) != 2 or any(not _is_issued(item) for item in contexts):
        raise ValueError("two independently verified issued arm contexts are required")
    first, second = contexts
    if first.manifest_sha256 != second.manifest_sha256:
        raise ValueError("verified arm contexts use different manifests")
    if len(first.bundle_sha256s) != 1 or len(second.bundle_sha256s) != 1 or first.bundle_sha256s[0][0] == second.bundle_sha256s[0][0]:
        raise ValueError("verified arm contexts must identify distinct arms")
    if set(first.receipt_sha256) & set(second.receipt_sha256):
        raise ValueError("cross-arm receipt reuse is forbidden")
    for index in (2, 3, 4, 5):
        if {item[index] for item in first.raw_grader_identities} & {item[index] for item in second.raw_grader_identities}:
            raise ValueError("cross-arm raw or grader identity/bytes reuse is forbidden")
    for index in (1, 2):
        if {item[index] for item in first.host_task_sessions} & {item[index] for item in second.host_task_sessions}:
            raise ValueError("cross-arm disposable task or native session reuse is forbidden")
    return _issue(VerifiedEvaluationContext(
        manifest_sha256=first.manifest_sha256,
        receipt_sha256=first.receipt_sha256 + second.receipt_sha256,
        verified_artifact_identities=first.verified_artifact_identities + second.verified_artifact_identities,
        bundle_sha256s=first.bundle_sha256s + second.bundle_sha256s,
        provenance="reviewed-local-host-recording",
        issued_at=datetime.now(timezone.utc),
        reviewed_recorder_id=first.reviewed_recorder_id + ";" + second.reviewed_recorder_id,
        raw_grader_identities=first.raw_grader_identities + second.raw_grader_identities,
        host_task_sessions=first.host_task_sessions + second.host_task_sessions,
        semantic_required_run_ids=first.semantic_required_run_ids + second.semantic_required_run_ids,
        semantic_observed_run_ids=first.semantic_observed_run_ids + second.semantic_observed_run_ids,
        _attestation=_ISSUER,
    ))


def context_covers_comparison(
    context: VerifiedEvaluationContext | None,
    manifest: Mapping[str, Any],
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> bool:
    """Only a separately issued context can upgrade structural comparison."""
    if not _is_issued(context):
        return False
    expected = {
        str(baseline.get("arm_id")): _digest(baseline),
        str(candidate.get("arm_id")): _digest(candidate),
    }
    expected_artifacts = {
        (str(item.get("arm_id")), str(record.get("run_id")),
         str(record.get("raw_evidence_refs", [{}])[0].get("identity_id")),
         str(record.get("grader_evidence_refs", [{}])[0].get("identity_id")))
        for item in (baseline, candidate)
        for record in item.get("runs", [])
    }
    bound_artifacts = {(arm, run, raw_id, grade_id) for arm, run, raw_id, grade_id, _, _ in context.raw_grader_identities}
    return (
        len(expected) == 2
        and context.manifest_sha256 == _digest(manifest)
        and dict(context.bundle_sha256s) == expected
        and len(context.receipt_sha256) == 2
        and len(context.verified_artifact_identities) == 2
        and set(context.verified_artifact_identities) == {
            (str(item.get("arm_id")), str((item.get("subject") or {}).get("archive_sha256")))
            for item in (baseline, candidate)
        }
        and bound_artifacts == expected_artifacts
        and len(context.raw_grader_identities) == sum(len(item.get("runs", [])) for item in (baseline, candidate))
        and len(context.host_task_sessions) == len(context.raw_grader_identities)
        and len({item[4] for item in context.raw_grader_identities}) == len(context.raw_grader_identities)
        and len({item[5] for item in context.raw_grader_identities}) == len(context.raw_grader_identities)
        and context.provenance == "reviewed-local-host-recording"
    )


def verify_run_evidence(
    bundle: Mapping[str, Any],
    manifest: Mapping[str, Any],
    evidence_root: Path,
    recorder_receipt: Mapping[str, Any],
) -> tuple[VerifiedEvaluationContext | None, list[str]]:
    """Bind a canonical scored bundle to reviewed raw and independent grade bytes."""
    try:
        errors = validate_run_bundle(bundle, manifest)
    except (TypeError, ValueError, KeyError, IndexError, OverflowError):
        return None, ["malformed scored bundle or manifest"]
    if errors:
        return None, errors
    receipt = recorder_receipt if isinstance(recorder_receipt, Mapping) else {}
    try:
        receipt_sha = _digest(receipt)
        bundle_sha = _digest(bundle)
        manifest_sha = _digest(manifest)
    except (TypeError, ValueError, OverflowError):
        return None, ["receipt, bundle or manifest contains noncanonical JSON values"]
    try:
        root = Path(evidence_root).resolve(strict=True)
        if not root.is_dir():
            errors.append("evidence root must be a directory")
    except (OSError, RuntimeError, TypeError, ValueError):
        return None, errors + ["evidence root is unavailable"]
    review = _REVIEWS.get(receipt_sha)
    if review is None:
        errors.append("receipt origin and recorder were not independently reviewed in this process")
    if receipt.get("receipt_version") != 1 or receipt.get("manifest_sha256") != manifest_sha or receipt.get("bundle_sha256") != bundle_sha:
        errors.append("receipt version, manifest or scored bundle digest mismatch")
    arm_id = bundle.get("arm_id")
    subject = bundle.get("subject") if isinstance(bundle.get("subject"), Mapping) else {}
    if receipt.get("arm_id") != arm_id or receipt.get("subject_archive_sha256") != subject.get("archive_sha256"):
        errors.append("receipt arm or immutable subject identity mismatch")
    if receipt.get("installed_read_back") != subject.get("installed_plugin_read_back") or receipt.get("isolation") != bundle.get("isolation"):
        errors.append("receipt install read-back or disposable state identity mismatch")
    host_version = receipt.get("host_version")
    host_source = receipt.get("host_source")
    expected_source = {"codex-desktop": "desktop-ui", "codex-cli": "codex-cli", "claude-code": "claude-code-cli"}.get(manifest.get("host"))
    if not isinstance(host_version, str) or not host_version.strip() or "required" in host_version.lower() or "unknown" in host_version.lower():
        errors.append("exact host/CLI version read-back is required")
    if not isinstance(host_source, str) or not host_source.strip() or (expected_source is not None and host_source != expected_source):
        errors.append("host source cannot be relabelled as the manifest surface")
    for field in ("host", "surface", "model", "reasoning"):
        if receipt.get(field) != manifest.get(field) or bundle.get(field) != manifest.get(field):
            errors.append(f"receipt {field} differs from pinned host configuration")
    if receipt.get("recorder_source_sha256") != hashlib.sha256((Path(__file__).parent / "record_acceptance.py").read_bytes()).hexdigest():
        errors.append("recorder source bytes differ from reviewed receipt")
    if not isinstance(receipt.get("recorder_id"), str) or not receipt["recorder_id"].strip():
        errors.append("recorder identity is missing")
    if review is not None and review[1] != receipt.get("recorder_source_sha256"):
        errors.append("reviewed recorder source identity changed")
    verification = bundle.get("identity_verification") if isinstance(bundle.get("identity_verification"), Mapping) else {}
    if any(verification.get(field) != "verified" for field in ("artifact", "installed_read_back", "run_identity", "surface")):
        errors.append("verified artifact, install, run and surface identities are required")
    runs = bundle.get("runs") if isinstance(bundle.get("runs"), list) else []
    receipt_runs = receipt.get("runs") if isinstance(receipt.get("runs"), list) else []
    if len(receipt_runs) != len(runs):
        errors.append("receipt run count differs from scored bundle")
    by_id = {item.get("run_id"): item for item in receipt_runs if isinstance(item, Mapping) and isinstance(item.get("run_id"), str)}
    if len(by_id) != len(receipt_runs):
        errors.append("receipt run identities are missing or duplicated")
    artifact_paths: set[str] = set()
    resolved_paths: set[Path] = set()
    task_ids: set[str] = set()
    session_ids: set[str] = set()
    raw_ids: set[str] = set()
    grade_ids: set[str] = set()
    bound_identities: list[tuple[str, str, str, str, str, str]] = []
    bound_sessions: list[tuple[str, str, str]] = []
    semantic_required: list[str] = []
    semantic_observed: list[str] = []
    cases = {case["id"]: case for case in _canonical_acceptance()["cases"]}
    scored_fields = ("output", "recommendation", "observed_behaviors", "quality", "passed", "safety_authority_pass", "budget_truthfulness_pass", "failure_visibility_pass", "unsafe_failures", "observed_route", "question_result", "rubric_outcome", "proxies", "cost", "latency", "critical_path")
    for record in runs:
        if not isinstance(record, Mapping):
            continue
        run_id = record.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            errors.append("scored run identity must be a non-empty string")
            continue
        case = cases.get(record.get("scenario_id"))
        if case and case.get("arm_expectations", {}).get(arm_id, {}).get("semantic_required") is True:
            semantic_required.append(run_id)
        entry = by_id.get(run_id)
        if entry is None:
            errors.append(f"missing receipt for run {run_id}")
            continue
        raw_refs = record.get("raw_evidence_refs")
        grade_refs = record.get("grader_evidence_refs")
        if not isinstance(raw_refs, list) or len(raw_refs) != 1 or not isinstance(grade_refs, list) or len(grade_refs) != 1:
            errors.append(f"run {run_id} lacks exactly one raw and grader identity")
            continue
        raw_ref = raw_refs[0]
        grade_ref = grade_refs[0]
        if not isinstance(raw_ref, Mapping) or not isinstance(grade_ref, Mapping):
            errors.append(f"run {run_id} lacks structured raw/grader identities")
            continue
        raw_id = raw_ref.get("identity_id")
        grade_id = grade_ref.get("identity_id")
        if not isinstance(raw_id, str) or not raw_id or not isinstance(grade_id, str) or not grade_id:
            errors.append(f"run {run_id} raw and grader identities must be non-empty strings")
            continue
        if raw_id in raw_ids or grade_id in grade_ids:
            errors.append(f"run {run_id} reuses a raw or grader identity")
        raw_ids.add(raw_id); grade_ids.add(grade_id)
        if entry.get("raw_identity_id") != raw_id or entry.get("grader_identity_id") != grade_id:
            errors.append(f"run {run_id} receipt evidence identity mismatch")
        task_id = entry.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip() or task_id in task_ids:
            errors.append(f"run {run_id} lacks a unique disposable host task identity")
        task_ids.add(str(task_id))
        def artifact(kind: str) -> tuple[Mapping[str, Any] | None, str | None]:
            spec = entry.get(kind)
            if not isinstance(spec, Mapping):
                errors.append(f"run {run_id} {kind} artifact descriptor is missing")
                return None, None
            relative = spec.get("path")
            if not isinstance(relative, str) or not relative or "\\" in relative or PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts or ":" in relative or PurePosixPath(relative).as_posix() != relative:
                errors.append(f"run {run_id} {kind} artifact path is unsafe")
                return None, None
            path = root.joinpath(*PurePosixPath(relative).parts)
            try:
                current = root
                for part in PurePosixPath(relative).parts:
                    current = current / part
                    if current.is_symlink():
                        raise ValueError("symlink component")
                resolved = path.resolve(strict=True)
                resolved.relative_to(root)
                if not resolved.is_file() or relative in artifact_paths or resolved in resolved_paths:
                    raise ValueError("artifact is not a unique regular file")
                data = resolved.read_bytes()
                if hashlib.sha256(data).hexdigest() != spec.get("sha256"):
                    raise ValueError("artifact byte digest mismatch")
                value = {} if kind == "native" else _strict_json(data)
                artifact_paths.add(relative)
                resolved_paths.add(resolved)
                return value, spec["sha256"]
            except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
                errors.append(f"run {run_id} {kind} artifact is missing, altered, duplicated or outside evidence root")
                return None, None
        raw, raw_sha = artifact("raw")
        grade, grade_sha = artifact("grade")
        native, native_sha = artifact("native")
        audit = review[3].get(run_id) if review is not None else None
        if native_sha is None or not isinstance(audit, Mapping) or audit.get("native_sha256") != native_sha:
            errors.append(f"run {run_id} lacks reviewed native host event bytes")
        if raw is not None:
            for field, expected in (("run_id", run_id), ("arm_id", arm_id), ("scenario_id", record.get("scenario_id")), ("replicate_id", record.get("replicate_id")), ("task_id", task_id), ("host", manifest.get("host")), ("host_version", host_version), ("host_source", host_source), ("surface", manifest.get("surface")), ("model", manifest.get("model")), ("reasoning", manifest.get("reasoning")), ("archive_sha256", subject.get("archive_sha256")), ("installed_read_back", subject.get("installed_plugin_read_back"))):
                if raw.get(field) != expected:
                    errors.append(f"run {run_id} raw host {field} mismatch")
            if raw.get("terminal_status") != "completed" or not isinstance(raw.get("session_id"), str) or not raw["session_id"].strip():
                errors.append(f"run {run_id} did not record terminal completion and session identity")
            elif raw["session_id"] in session_ids:
                errors.append(f"run {run_id} reuses a native host session")
            else:
                session_ids.add(raw["session_id"])
                bound_sessions.append((str(arm_id), str(task_id), raw["session_id"]))
            if raw.get("output") != record.get("output") or not isinstance(raw.get("output"), str):
                errors.append(f"run {run_id} scored output differs from host output bytes")
            usage = raw.get("usage")
            if not isinstance(usage, Mapping) or usage.get("complete") is not True or not isinstance(usage.get("whole_job_tokens"), int) or isinstance(usage.get("whole_job_tokens"), bool) or usage["whole_job_tokens"] < 0:
                errors.append(f"run {run_id} lacks complete observed whole-job usage")
            elif (record.get("proxies") or {}).get("model_calls") != usage.get("model_calls"):
                errors.append(f"run {run_id} model-call count differs from native usage")
            wall = raw.get("wall_seconds")
            if not isinstance(wall, (int, float)) or isinstance(wall, bool) or not math.isfinite(wall) or wall < 0:
                errors.append(f"run {run_id} lacks observed wall time")
            events = raw.get("tool_events")
            if raw.get("tool_events_complete") is not True or not isinstance(events, list) or any(not isinstance(item, Mapping) or not isinstance(item.get("type"), str) for item in events):
                errors.append(f"run {run_id} lacks complete observed tool events")
            else:
                for proxy, event_type in (("spawn_count", "spawn_agent"), ("tool_calls", "tool_call"), ("question_count", "user_question")):
                    if (record.get("proxies") or {}).get(proxy) != sum(item["type"] == event_type for item in events):
                        errors.append(f"run {run_id} {proxy} differs from host events")
            for metric, expected in (("cost", usage.get("whole_job_tokens") if isinstance(usage, Mapping) else None), ("latency", wall), ("critical_path", raw.get("critical_path_seconds"))):
                measurement = record.get(metric)
                if isinstance(measurement, Mapping) and measurement.get("provenance") == "observed" and measurement.get("value") != expected:
                    errors.append(f"run {run_id} observed {metric} differs from host recording")
            if isinstance(audit, Mapping):
                for field in ("task_id", "session_id", "host", "host_version", "host_source", "surface", "model", "reasoning", "archive_sha256", "terminal_status", "usage", "wall_seconds", "critical_path_seconds", "tool_events", "tool_events_complete"):
                    if audit.get(field) != raw.get(field):
                        errors.append(f"run {run_id} raw {field} differs from independently audited native events")
                if audit.get("output_sha256") != hashlib.sha256(raw.get("output", "").encode("utf-8") if isinstance(raw.get("output"), str) else b"").hexdigest():
                    errors.append(f"run {run_id} output differs from independently audited native events")
                trace = raw.get("semantic_trace")
                if trace is None:
                    if audit.get("semantic_trace_sha256") is not None:
                        errors.append(f"run {run_id} native audit claims a missing semantic trace")
                else:
                    try:
                        trace_sha = _digest(trace)
                    except (TypeError, ValueError, OverflowError):
                        trace_sha = None
                    if trace != record.get("calculation") or audit.get("semantic_trace_sha256") != trace_sha:
                        errors.append(f"run {run_id} semantic trace differs from scored calculation or native audit")
                    elif run_id in semantic_required:
                        semantic_observed.append(run_id)
        if grade is not None:
            if grade.get("run_id") != run_id or grade.get("arm_id") != arm_id or grade.get("raw_identity_id") != raw_id or grade.get("raw_sha256") != raw_sha or grade.get("grader_identity_id") != grade_id or grade.get("independent") is not True or grade.get("grader_id") == receipt.get("recorder_id") or (review is not None and grade.get("grader_id") not in review[2]):
                errors.append(f"run {run_id} independent grader provenance or raw binding mismatch")
            scored = grade.get("scored")
            if not isinstance(scored, Mapping) or any(scored.get(field) != record.get(field) for field in scored_fields):
                errors.append(f"run {run_id} scored fields differ from independent grade bytes")
        if raw_sha is not None and grade_sha is not None and native_sha is not None:
            bound_identities.append((str(arm_id), str(run_id), str(raw_id), str(grade_id), raw_sha, grade_sha))
    if errors:
        return None, errors
    return _issue(VerifiedEvaluationContext(
        manifest_sha256=manifest_sha,
        receipt_sha256=(receipt_sha,),
        verified_artifact_identities=((str(arm_id), str(subject["archive_sha256"])),),
        bundle_sha256s=((str(arm_id), bundle_sha),),
        provenance="reviewed-local-host-recording",
        issued_at=datetime.now(timezone.utc),
        reviewed_recorder_id=review[0],
        raw_grader_identities=tuple(bound_identities),
        host_task_sessions=tuple(bound_sessions),
        semantic_required_run_ids=tuple(semantic_required),
        semantic_observed_run_ids=tuple(semantic_observed),
        _attestation=_ISSUER,
    )), []


def verify_release_evidence(evidence_root: Path) -> dict[str, Any]:
    """Release CLI remains blocked until audited contexts and subjects exist."""
    return {"status": "blocked", "reasons": ["Reviewed current host receipts, artifact bytes and installed subjects are required"]}
