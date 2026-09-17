from pathlib import Path

from .base import EventMetadata, SessionInspection


class CodexAdapter:
    name = "codex"

    def accepts_path(self, _path: Path):
        return True

    def inspect(self, _path: Path, events: list[dict]):
        session_id = None
        title = None
        workspace = None
        created_at = None
        for event in events:
            metadata = self.event_metadata(event)
            if metadata.session_id and session_id is None:
                session_id = metadata.session_id
                workspace = metadata.workspace or workspace
                created_at = metadata.created_at or created_at
            message = self.visible_message(event)
            if title is None and message is not None and message[0] == "user":
                title = message[1]
            if session_id and title:
                break
        if session_id is None:
            return None
        return SessionInspection(
            session_id=session_id,
            title=title or f"Session {session_id[:8]}",
            workspace=workspace,
            created_at=created_at,
        )

    def event_metadata(self, event: dict):
        if event.get("type") != "session_meta":
            return EventMetadata()
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        recorded_id = payload.get("id") or payload.get("session_id")
        cwd = payload.get("cwd")
        return EventMetadata(
            session_id=str(recorded_id).lower() if recorded_id else None,
            workspace=Path(str(cwd)).name if cwd else None,
            created_at=str(payload.get("timestamp") or "") or None,
        )

    def event_timestamp(self, event: dict):
        value = event.get("timestamp")
        return value if isinstance(value, str) else None

    def visible_message(self, event: dict):
        if event.get("type") != "event_msg":
            return None
        payload = event.get("payload") or {}
        kind = payload.get("type")
        if kind == "user_message":
            role = "user"
        elif kind == "agent_message":
            role = "assistant"
        elif kind == "item_completed":
            item = payload.get("item")
            if not isinstance(item, dict):
                return None
            item_kind = item.get("type")
            if item_kind == "UserMessage":
                role = "user"
            elif item_kind == "AgentMessage":
                role = "assistant"
            else:
                return None
            content = item.get("content")
            if not isinstance(content, list):
                return None
            text = [
                block["text"]
                for block in content
                if isinstance(block, dict)
                and isinstance(block.get("text"), str)
                and block["text"].strip()
            ]
            if not text:
                return None
            return role, "\n\n".join(text), self.event_timestamp(event)
        else:
            return None
        markdown = payload.get("message")
        if not isinstance(markdown, str) or not markdown:
            return None
        return role, markdown, self.event_timestamp(event)
