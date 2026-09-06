from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SessionInspection:
    session_id: str
    title: str
    workspace: str | None
    created_at: str | None


@dataclass(frozen=True)
class EventMetadata:
    session_id: str | None = None
    title: str | None = None
    workspace: str | None = None
    created_at: str | None = None


class SessionAdapter(Protocol):
    name: str

    def accepts_path(self, path: Path) -> bool: ...

    def inspect(self, path: Path, events: list[dict]) -> SessionInspection | None: ...

    def event_metadata(self, event: dict) -> EventMetadata: ...

    def event_timestamp(self, event: dict) -> str | None: ...

    def visible_message(self, event: dict) -> tuple[str, str, str | None] | None: ...
