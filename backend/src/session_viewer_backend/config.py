import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    sessions_root: Path

    @classmethod
    def from_environment(cls):
        return cls(
            database_path=Path(
                os.environ.get("VIEWER_DATABASE", "/data/viewer.sqlite3")
            ),
            sessions_root=Path(
                os.environ.get("VIEWER_SESSIONS_ROOT", "/sessions")
            ),
        )
