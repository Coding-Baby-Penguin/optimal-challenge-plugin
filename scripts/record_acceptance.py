#!/usr/bin/env python3
"""Import existing local host/grade artifacts into a hash-bound receipt.

This importer never calls a model, manufactures a host result, grades an answer,
or approves its own receipt. Keep raw inputs in an explicitly chosen local root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _artifact(root: Path, relative: str) -> dict[str, str]:
    pure = PurePosixPath(relative)
    if not relative or pure.as_posix() != relative or pure.is_absolute() or ".." in pure.parts or "\\" in relative or ":" in relative:
        raise ValueError("artifact path must be a canonical relative POSIX path")
    path = root.joinpath(*pure.parts)
    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("artifact path has a symlink component")
    resolved = path.resolve(strict=True)
    resolved.relative_to(root)
    if path.is_symlink() or not resolved.is_file():
        raise ValueError("artifact must be a regular file without a final symlink")
    return {"path": relative, "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest()}


def _raw_header(path: Path) -> tuple[str, str]:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(path.read_bytes(), object_pairs_hook=unique_pairs,
                       parse_constant=lambda item: (_ for _ in ()).throw(ValueError("non-finite JSON value")))
    json.dumps(value, allow_nan=False)
    if not isinstance(value, Mapping):
        raise ValueError("raw host artifact must be a JSON object")
    version, source = value.get("host_version"), value.get("host_source")
    if not isinstance(version, str) or not version.strip() or not isinstance(source, str) or not source.strip():
        raise ValueError("raw artifact lacks exact host version and source")
    return version, source


def build_receipt(
    bundle: Mapping[str, Any], manifest: Mapping[str, Any], evidence_root: Path,
    observations: Sequence[Mapping[str, Any]], *, recorder_id: str,
) -> dict[str, Any]:
    """Describe existing bytes; do not infer missing task outcomes or grades."""
    root = Path(evidence_root).resolve(strict=True)
    if not root.is_dir() or not isinstance(recorder_id, str) or not recorder_id.strip():
        raise ValueError("an explicit local evidence directory and recorder identity are required")
    if not isinstance(bundle.get("runs"), list) or len(observations) != len(bundle["runs"]):
        raise ValueError("one existing host and grade observation is required per scored run")
    by_id = {record.get("run_id"): record for record in bundle["runs"] if isinstance(record, Mapping)}
    if len(by_id) != len(bundle["runs"]):
        raise ValueError("scored run identities must be unique")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    host_headers: set[tuple[str, str]] = set()
    for observation in observations:
        if not isinstance(observation, Mapping):
            raise ValueError("observation must be an object")
        run_id = observation.get("run_id")
        if not isinstance(run_id, str) or run_id not in by_id or run_id in seen:
            raise ValueError("observation run identity is missing, extra or duplicated")
        seen.add(run_id)
        record = by_id[run_id]
        for field in ("raw_path", "grade_path", "native_path", "task_id"):
            if not isinstance(observation.get(field), str) or not observation[field].strip():
                raise ValueError(f"observation {field} is required")
        raw = _artifact(root, observation["raw_path"])
        host_headers.add(_raw_header(root.joinpath(*PurePosixPath(raw["path"]).parts)))
        grade = _artifact(root, observation["grade_path"])
        native = _artifact(root, observation["native_path"])
        if len({raw["path"], grade["path"], native["path"]}) != 3:
            raise ValueError("raw, grade and native artifacts must be distinct")
        entries.append({
            "run_id": run_id,
            "task_id": observation["task_id"],
            "raw_identity_id": record["raw_evidence_refs"][0]["identity_id"],
            "grader_identity_id": record["grader_evidence_refs"][0]["identity_id"],
            "raw": raw,
            "grade": grade,
            "native": native,
        })
    if len(host_headers) != 1:
        raise ValueError("all runs must use one exact host version and source")
    host_version, host_source = next(iter(host_headers))
    subject = bundle.get("subject") if isinstance(bundle.get("subject"), Mapping) else {}
    return {
        "receipt_version": 1,
        "recorder_id": recorder_id,
        "recorder_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "manifest_sha256": _digest(manifest),
        "bundle_sha256": _digest(bundle),
        "arm_id": bundle.get("arm_id"),
        "subject_archive_sha256": subject.get("archive_sha256"),
        "installed_read_back": subject.get("installed_plugin_read_back"),
        "isolation": bundle.get("isolation"),
        "host": bundle.get("host"),
        "host_version": host_version,
        "host_source": host_source,
        "surface": bundle.get("surface"),
        "model": bundle.get("model"),
        "reasoning": bundle.get("reasoning"),
        "runs": entries,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bundle", "manifest", "evidence-root", "observations", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--recorder-id", required=True)
    args = parser.parse_args(argv)
    try:
        root = args.evidence_root.resolve(strict=True)
        output = args.output.resolve()
        output.relative_to(root)
        if output.exists():
            raise ValueError("refusing to overwrite an existing receipt")
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        observations = json.loads(args.observations.read_text(encoding="utf-8"))
        if not isinstance(bundle, Mapping) or not isinstance(manifest, Mapping) or not isinstance(observations, list):
            raise ValueError("bundle, manifest and observations have invalid shapes")
        receipt = build_receipt(bundle, manifest, root, observations, recorder_id=args.recorder_id)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    except (OSError, ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        print(f"RECORDING BLOCKED: {type(exc).__name__}: {exc}")
        return 2
    print(f"RECEIPT RECORDED: {output.name}; independent review and byte verification remain required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
