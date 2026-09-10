#!/usr/bin/env python3
"""Manage persistent session titles in config/session_metadata.json."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import uuid
from pathlib import Path


DEFAULT_METADATA_FILE = (
    Path(__file__).resolve().parents[1] / "config" / "session_metadata.json"
)


def session_id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "session ID must be a complete UUID; copy it from the session header"
        ) from error


def load_metadata(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"Cannot parse {path}: {error}") from error
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(value, dict)
        for key, value in parsed.items()
    ):
        raise SystemExit(f"{path} must contain an object of session metadata objects")
    return parsed


def save_metadata(path: Path, metadata: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(metadata, output, indent=2, ensure_ascii=False)
            output.write("\n")
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_METADATA_FILE,
        help=f"metadata file (default: {DEFAULT_METADATA_FILE})",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    set_parser = commands.add_parser("set", help="set a session title")
    set_parser.add_argument("session_id", type=session_id)
    set_parser.add_argument("title")

    remove_parser = commands.add_parser("remove", help="remove a custom title")
    remove_parser.add_argument("session_id", type=session_id)

    commands.add_parser("list", help="list custom session titles")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    path = args.file.expanduser().resolve()
    metadata = load_metadata(path)

    if args.command == "list":
        for identifier, values in metadata.items():
            title = values.get("title")
            if isinstance(title, str):
                print(f"{identifier}\t{title}")
        return

    identifier = args.session_id
    if args.command == "set":
        title = args.title.strip()
        if not title:
            raise SystemExit("Title cannot be empty")
        metadata.setdefault(identifier, {})["title"] = title
        save_metadata(path, metadata)
        print(f"Set title for {identifier}: {title}")
        return

    values = metadata.get(identifier)
    if values is None or "title" not in values:
        raise SystemExit(f"No custom title exists for {identifier}")
    del values["title"]
    if not values:
        del metadata[identifier]
    save_metadata(path, metadata)
    print(f"Removed custom title for {identifier}")


if __name__ == "__main__":
    main()
