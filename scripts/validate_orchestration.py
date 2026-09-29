#!/usr/bin/env python3
"""Validate an Optimal Challenge registry/ledger pair."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orchestration_state import validate_orchestration_state


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("root must be an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        registry = _read_object(args.registry)
        ledger = _read_object(args.ledger)
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
