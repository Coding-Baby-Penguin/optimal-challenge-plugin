#!/usr/bin/env python3
"""Create an arm-blind internal pilot grading packet after host verification."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.bind_cli_pilot_grade import _load, make_blind_packet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("identity", "plan", "manifest", "output-text", "workspace", "packet"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--blind-id", required=True)
    args = parser.parse_args()
    if args.packet.exists():
        parser.error("refusing to overwrite a grading packet")
    try:
        identity, _ = _load(args.identity)
        plan, _ = _load(args.plan)
        manifest, manifest_bytes = _load(args.manifest)
        packet = make_blind_packet(identity, plan, manifest,
                                   hashlib.sha256(manifest_bytes).hexdigest(),
                                   args.output_text.read_bytes(), args.workspace,
                                   args.blind_id)
        args.packet.write_text(json.dumps(packet, sort_keys=True, indent=2,
                                         ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError, KeyError, OverflowError, json.JSONDecodeError) as exc:
        parser.error(f"pilot grading packet blocked: {type(exc).__name__}: {exc}")
    print(json.dumps({"status": "blind_packet_prepared", "packet_sha256": hashlib.sha256(args.packet.read_bytes()).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
