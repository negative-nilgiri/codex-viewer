import json
from dataclasses import dataclass
from pathlib import Path


class RolloutError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedLine:
    start: int
    end: int
    event: dict | None


def iter_complete_lines(path: Path, offset: int):
    """Yield decoded complete JSONL records, leaving a partial final line unread."""
    with path.open("rb") as source:
        source.seek(offset)
        while True:
            start = source.tell()
            raw = source.readline()
            if not raw:
                return
            if not raw.endswith(b"\n"):
                return
            end = source.tell()
            if not raw.strip():
                yield ParsedLine(start=start, end=end, event=None)
                continue
            try:
                event = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise RolloutError(
                    f"Malformed complete JSONL line at byte {start} in {path}: {error}"
                ) from error
            if not isinstance(event, dict):
                raise RolloutError(
                    f"JSONL value at byte {start} in {path} is not an object"
                )
            yield ParsedLine(start=start, end=end, event=event)


def read_prefix_events(path: Path, byte_limit: int):
    events = []
    try:
        for parsed in iter_complete_lines(path, 0):
            if parsed.end > byte_limit:
                break
            if parsed.event is not None:
                events.append(parsed.event)
    except RolloutError:
        return []
    return events
