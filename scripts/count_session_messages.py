#!/usr/bin/env python3
"""Count the messages the viewer would import from one JSONL transcript."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend" / "src"))

from session_viewer_backend.adapters import get_adapter  # noqa: E402


def detect_adapter(event: dict) -> str:
    if event.get("type") in {"session_meta", "event_msg", "response_item"}:
        return "codex"
    if "sessionId" in event or "message" in event or "isSidechain" in event:
        return "claude"
    raise ValueError("could not detect the transcript adapter; pass --adapter")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count visible conversation messages in a Codex or Claude JSONL file."
    )
    parser.add_argument("path", type=Path, help="path to the session JSONL file")
    parser.add_argument(
        "--adapter",
        choices=("auto", "codex", "claude"),
        default="auto",
        help="transcript format (default: auto-detect)",
    )
    args = parser.parse_args()

    path = args.path.expanduser().resolve()
    adapter_name = None if args.adapter == "auto" else args.adapter
    adapter = get_adapter(adapter_name) if adapter_name else None
    roles: Counter[str] = Counter()
    line_count = 0
    valid_json_count = 0
    malformed_count = 0

    with path.open("r", encoding="utf-8") as transcript:
        for line in transcript:
            line_count += 1
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                malformed_count += 1
                continue
            if not isinstance(event, dict):
                continue
            valid_json_count += 1
            if adapter is None:
                try:
                    adapter_name = detect_adapter(event)
                except ValueError:
                    continue
                adapter = get_adapter(adapter_name)
            message = adapter.visible_message(event)
            if message is not None:
                roles[message[0]] += 1

    if adapter is None:
        parser.error("could not detect the transcript adapter; pass --adapter")

    visible_count = sum(roles.values())
    print(f"path: {path}")
    print(f"adapter: {adapter_name}")
    print(f"bytes: {path.stat().st_size}")
    print(f"jsonl lines: {line_count}")
    print(f"valid JSON records: {valid_json_count}")
    print(f"malformed/incomplete lines: {malformed_count}")
    print(f"visible messages: {visible_count}")
    for role in sorted(roles):
        print(f"  {role}: {roles[role]}")


if __name__ == "__main__":
    main()
