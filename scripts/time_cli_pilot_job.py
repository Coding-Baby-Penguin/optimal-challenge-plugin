#!/usr/bin/env python3
"""Time one complete externally authored CLI pilot job, including installation.

Wrap the same setup/install/host/verification/review command for every arm.
The command is supplied as argv after --. Raw logs stay in the caller's local
run directory; this receipt is a timing observation, not a quality grade.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def time_job(command: list[str], output: Path, *, timeout_seconds: int) -> dict:
    if not command or timeout_seconds <= 0 or output.exists():
        raise ValueError("one command, positive timeout and fresh timing output are required")
    output.parent.mkdir(parents=True, exist_ok=True)
    command_path = output.with_suffix(".argv.json")
    stdout_path = output.with_suffix(".stdout.log")
    stderr_path = output.with_suffix(".stderr.log")
    if command_path.exists() or stdout_path.exists() or stderr_path.exists():
        raise ValueError("pilot timing logs must be fresh")
    command_bytes = (json.dumps(command, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    command_path.write_bytes(command_bytes)
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.monotonic_ns()
    status = "failed"
    returncode = None
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            result = subprocess.run(command, stdout=stdout, stderr=stderr,
                                    check=False, timeout=timeout_seconds)
            returncode = result.returncode
            status = "completed" if returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            status = "timeout-process-tree-unverified"
        except OSError:
            status = "could-not-start"
    ended = time.monotonic_ns()
    receipt = {
        "schema_version": 1, "status": status, "returncode": returncode,
        "started_utc": started_utc, "ended_utc": datetime.now(timezone.utc).isoformat(),
        "outer_whole_job_wall_seconds": (ended - started) / 1_000_000_000,
        "scope_claim": "unreviewed; inspect retained argv and phase logs before whole-job comparison",
        "process_tree_termination": "unverified" if status == "timeout-process-tree-unverified" else "not_applicable",
        "command_argv_sha256": hashlib.sha256(command_bytes).hexdigest(),
        "command_argv_path": command_path.name,
        "stdout_sha256": hashlib.sha256(stdout_path.read_bytes()).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr_path.read_bytes()).hexdigest(),
        "stdout_path": stdout_path.name, "stderr_path": stderr_path.name,
    }
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    try:
        result = time_job(command, args.output, timeout_seconds=args.timeout_seconds)
    except (OSError, ValueError) as exc:
        print(f"pilot timing blocked: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({key: result[key] for key in ("status", "returncode", "outer_whole_job_wall_seconds")}, sort_keys=True))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
