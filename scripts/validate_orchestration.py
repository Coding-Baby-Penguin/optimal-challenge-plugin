#!/usr/bin/env python3
"""Validate an Optimal Challenge registry/ledger pair."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator

from orchestration_state import validate_orchestration_state


ROOT = Path(__file__).resolve().parents[1]


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("root must be an object")
    return value


def _json_path(root: str, parts: object) -> str:
    path = f"$.{root}"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def _schema_errors(root: str, instance: dict[str, Any], schema_path: Path) -> list[str]:
    schema = _read_object(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    return [f"{_json_path(root, error.absolute_path)}: {error.message}" for error in sorted(validator.iter_errors(instance), key=lambda item: (tuple(str(part) for part in item.absolute_path), item.message))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        registry = _read_object(args.registry)
        ledger = _read_object(args.ledger)
        errors = _schema_errors("registry", registry, ROOT / "config" / "team-registry.schema.json")
        errors.extend(_schema_errors("ledger", ledger, ROOT / "config" / "allocation-ledger.schema.json"))
        if not errors:
            errors = validate_orchestration_state(registry, ledger)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors = [f"input: {exc}"]
    if errors:
        print("ORCHESTRATION STATE VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("ORCHESTRATION STATE VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
