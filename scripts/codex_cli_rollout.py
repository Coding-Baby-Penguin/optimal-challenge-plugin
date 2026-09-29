#!/usr/bin/env python3
"""Extract auditable Codex CLI metadata from retained native JSONL rollouts.

This preflight extractor makes no quality or desktop-host claim. Keep the
original rollouts: its compact report is a digest-bound index, not a substitute.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key in native rollout")
        result[key] = value
    return result


def _records(path: Path) -> list[dict[str, Any]]:
    lines = path.read_bytes().splitlines()
    if not lines:
        raise ValueError("empty native rollout")
    result = []
    for line in lines:
        item = json.loads(line, object_pairs_hook=_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite native JSON")))
        if not isinstance(item, dict) or not isinstance(item.get("payload"), dict):
            raise ValueError("malformed native rollout record")
        result.append(item)
    return result


def _tool_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair native tool attempts with their outputs without exposing payloads."""
    calls: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    for record in records:
        if record.get("type") != "response_item":
            continue
        item = record["payload"]
        kind = item.get("type")
        if kind not in {"function_call", "custom_tool_call", "function_call_output", "custom_tool_call_output"}:
            continue
        call_id = item.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            raise ValueError("native tool event lacks a call identity")
        if kind in {"function_call", "custom_tool_call"}:
            name = item.get("name")
            namespace = item.get("namespace")
            if (call_id in calls or not isinstance(name, str) or not name or
                    (namespace is not None and not isinstance(namespace, str))):
                raise ValueError("duplicate or malformed native tool call")
            event = {"type": "spawn_agent" if namespace == "collaboration" and name == "spawn_agent" else "tool_call",
                     "namespace": namespace, "name": name, "call_id": call_id,
                     "outcome": "unknown", "output_present": False}
            calls[call_id] = event
            events.append(event)
        else:
            event = calls.get(call_id)
            if event is None or event["output_present"]:
                raise ValueError("orphan or duplicate native tool output")
            event["output_present"] = True
    if any(not event["output_present"] for event in events):
        raise ValueError("native tool call is missing its output")
    return events


def extract_rollout(path: Path) -> dict[str, Any]:
    """Read one session's own events, excluding inherited fork history."""
    path = Path(path)
    records = _records(path)
    if records[0].get("type") != "session_meta":
        raise ValueError("first native record must identify the owning session")
    meta = records[0]["payload"]
    own_id = meta.get("id")
    if not isinstance(own_id, str) or not own_id or not isinstance(meta.get("cli_version"), str) or not meta["cli_version"].strip():
        raise ValueError("native session identity or CLI version is missing")
    parent = meta.get("parent_thread_id")
    if parent is not None and (not isinstance(parent, str) or not parent):
        raise ValueError("malformed parent session identity")
    source = meta.get("source")
    if (parent is None and source != "exec") or (parent is not None and
            (not isinstance(source, dict) or not isinstance(source.get("subagent"), dict))):
        raise ValueError("native session is not a Codex CLI exec source")
    starts = [(index, record["payload"].get("turn_id")) for index, record in enumerate(records)
              if record.get("type") == "event_msg" and record["payload"].get("type") == "task_started"]
    contexts = {record["payload"].get("turn_id"): record["payload"] for record in records
                if record.get("type") == "turn_context"}
    if not starts:
        raise ValueError("native session has no task start")
    # A forked rollout starts with inherited parent records. Its own task start
    # is the last distinct start in this single-turn host task.
    start_index, turn_id = starts[-1] if parent else starts[0]
    if not isinstance(turn_id, str) or turn_id not in contexts:
        raise ValueError("native task has no matching model context")
    context = contexts[turn_id]
    if any(not isinstance(context.get(field), str) or not context[field].strip() for field in ("model", "effort")):
        raise ValueError("native model or reasoning effort is missing")
    own = records[start_index:]
    completion = [r["payload"] for r in own if r.get("type") == "event_msg"
                  and r["payload"].get("type") == "task_complete"
                  and r["payload"].get("turn_id") == turn_id]
    if len(completion) != 1:
        raise ValueError("native task did not complete exactly once")
    token_events = [r["payload"].get("info", {}).get("total_token_usage") for r in own
                    if r.get("type") == "event_msg" and r["payload"].get("type") == "token_count"]
    if not token_events or not isinstance(token_events[-1], dict):
        raise ValueError("native task has no final cumulative usage")
    usage = token_events[-1]
    fields = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
              "output_tokens", "reasoning_output_tokens", "total_tokens")
    if any(not isinstance(usage.get(k), int) or isinstance(usage.get(k), bool) or usage[k] < 0 for k in fields):
        raise ValueError("native usage is incomplete or malformed")
    if usage["cached_input_tokens"] > usage["input_tokens"] or usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
        raise ValueError("native usage totals are inconsistent")
    tool_events = _tool_events(own)
    finals = [r["payload"] for r in own if r.get("type") == "response_item"
              and r["payload"].get("type") == "message"
              and r["payload"].get("role") == "assistant"
              and r["payload"].get("phase") == "final_answer"]
    if len(finals) != 1:
        raise ValueError("native task lacks one final answer")
    parts = finals[0].get("content")
    if not isinstance(parts, list) or any(not isinstance(p, dict) or p.get("type") != "output_text" or not isinstance(p.get("text"), str) for p in parts):
        raise ValueError("native final answer shape is unsupported")
    output = "".join(p["text"] for p in parts)
    duration_ms = completion[0].get("duration_ms")
    if not isinstance(duration_ms, (int, float)) or isinstance(duration_ms, bool) or not math.isfinite(duration_ms) or duration_ms < 0:
        raise ValueError("native task duration is missing")
    return {
        "native_source": "codex-cli-rollout-v1",
        "native_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "session_id": own_id,
        "parent_session_id": parent,
        "turn_id": turn_id,
        "host": "codex-cli",
        "host_source": "codex-cli",
        "host_version": meta["cli_version"],
        "model": context.get("model"),
        "reasoning": context.get("effort"),
        "terminal_status": "completed",
        "usage": {key: usage[key] for key in fields},
        "wall_seconds": duration_ms / 1000,
        "tool_events": tool_events,
        "tool_events_complete": True,
        "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
    }


def extract_job(paths: Sequence[Path]) -> dict[str, Any]:
    sessions = [extract_rollout(path) for path in paths]
    if len({item["session_id"] for item in sessions}) != len(sessions):
        raise ValueError("duplicate native session")
    roots = [item for item in sessions if item["parent_session_id"] is None]
    if len(roots) != 1:
        raise ValueError("one root Codex CLI session is required")
    root = roots[0]
    ids = {item["session_id"] for item in sessions}
    if any(item["parent_session_id"] not in ids for item in sessions if item is not root):
        raise ValueError("missing child-parent native session")
    if any((item["host_version"], item["model"], item["reasoning"]) !=
           (root["host_version"], root["model"], root["reasoning"]) for item in sessions):
        raise ValueError("native sessions differ in exact host/model configuration")
    return {
        "preflight_only": True,
        "quality_claim": "unverified",
        "host": "codex-cli",
        "surface": "codex-cli-local",
        "host_source": "codex-cli",
        "host_version": root["host_version"],
        "model": root["model"],
        "reasoning": root["reasoning"],
        "root_session_id": root["session_id"],
        "terminal_status": "completed",
        "wall_seconds": root["wall_seconds"],
        "output_sha256": root["output_sha256"],
        "usage": {
            "complete": True,
            "whole_job_tokens": sum(item["usage"]["input_tokens"] + item["usage"]["output_tokens"] for item in sessions),
            "session_count": len(sessions),
            "model_calls": None,
            "input_tokens": sum(item["usage"]["input_tokens"] for item in sessions),
            "output_tokens": sum(item["usage"]["output_tokens"] for item in sessions),
        },
        "tool_events": [event for item in sessions for event in item["tool_events"]],
        "tool_events_complete": True,
        "sessions": sessions,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollout", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("refusing to overwrite an existing audit")
    try:
        report = extract_job(args.rollout)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
