import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    sources_path: Path
    session_metadata_path: Path
    bookmarks_path: Path = Path("/data/bookmarks")
    archives_path: Path = Path("/data/archives")
    documents_path: Path = Path("/documents")

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
                    "/metadata/session_metadata.json",
                )
            ),
            bookmarks_path=Path(
                os.environ.get("VIEWER_BOOKMARKS_DIRECTORY", "/data/bookmarks")
            ),
            archives_path=Path(
                os.environ.get("VIEWER_ARCHIVES_DIRECTORY", "/data/archives")
            ),
            documents_path=Path(
                os.environ.get("VIEWER_DOCUMENTS_DIRECTORY", "/documents")
            ),
        )
