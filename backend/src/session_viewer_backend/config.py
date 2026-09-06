import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    sources_path: Path
    session_metadata_path: Path

    @classmethod
    def from_environment(cls):
        return cls(
            database_path=Path(
                os.environ.get("VIEWER_DATABASE", "/data/viewer.sqlite3")
            ),
            sources_path=Path(
                os.environ.get("VIEWER_SOURCES_FILE", "/config/sources.toml")
            ),
            session_metadata_path=Path(
                os.environ.get(
                    "VIEWER_SESSION_METADATA_FILE",
                    "/config/session_metadata.json",
                )
            ),
        )
