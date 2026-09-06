import re
from pathlib import Path

from .base import EventMetadata, SessionInspection


SESSION_ID_RE = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.I)
LOCAL_COMMAND_PREFIXES = (
    "<command-name>",
    "<local-command-caveat>",
    "<local-command-stdout>",
)


def recorded_session_id(event: dict):
    value = event.get("sessionId") or event.get("session_id")
    if not isinstance(value, str) or not SESSION_ID_RE.fullmatch(value):
        return None
    return value.lower()


class ClaudeAdapter:
    name = "claude"

    def accepts_path(self, path: Path):
        return path.name.endswith(".jsonl") and not path.name.startswith("agent-")

    def inspect(self, path: Path, events: list[dict]):
        if not self.accepts_path(path):
            return None
        session_ids = {value for event in events if (value := recorded_session_id(event))}
        if len(session_ids) != 1:
            return None
        if any(event.get("isSidechain") is True for event in events):
            return None
        session_id = session_ids.pop()
        title = None
        first_user = None
        workspace = None
        created_at = None
        for event in events:
            metadata = self.event_metadata(event)
            title = metadata.title or title
            workspace = workspace or metadata.workspace
            created_at = created_at or metadata.created_at
            message = self.visible_message(event)
            if first_user is None and message is not None and message[0] == "user":
                first_user = message[1]
        return SessionInspection(
            session_id=session_id,
            title=title or first_user or f"Session {session_id[:8]}",
            workspace=workspace,
            created_at=created_at,
        )

    def event_metadata(self, event: dict):
        title = event.get("aiTitle") if event.get("type") == "ai-title" else None
        cwd = event.get("cwd")
        return EventMetadata(
            session_id=recorded_session_id(event),
            title=title if isinstance(title, str) and title.strip() else None,
            workspace=Path(str(cwd)).name if cwd else None,
            created_at=self.event_timestamp(event),
        )

    def event_timestamp(self, event: dict):
        value = event.get("timestamp")
        return value if isinstance(value, str) else None

    def visible_message(self, event: dict):
        if event.get("isSidechain") is True:
            return None
        kind = event.get("type")
        message = event.get("message")
        if not isinstance(message, dict):
            return None
        content = message.get("content")
        if kind == "user":
            if event.get("isMeta") is True:
                return None
            if isinstance(content, str):
                markdown = content.strip()
                if not markdown or markdown.startswith(LOCAL_COMMAND_PREFIXES):
                    return None
                return "user", markdown, self.event_timestamp(event)
            if not isinstance(content, list) or any(
                isinstance(block, dict) and block.get("type") == "tool_result"
                for block in content
            ):
                return None
            role = "user"
        elif kind == "assistant":
            if not isinstance(content, list):
                return None
            role = "assistant"
        else:
            return None

        text = [
            block.get("text").strip()
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
            and block.get("text").strip()
        ]
        if not text:
            return None
        return role, "\n\n".join(text), self.event_timestamp(event)
