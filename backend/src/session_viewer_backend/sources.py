import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


SOURCE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*$")
SUPPORTED_ADAPTERS = {"claude", "codex"}


class SourceConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class SourceDefinition:
    id: str
    adapter: str
    path: Path


def load_sources(config_path: Path):
    try:
        with config_path.open("rb") as source:
            parsed = tomllib.load(source)
    except OSError as error:
        raise SourceConfigurationError(
            f"Cannot read source configuration {config_path}: {error}"
        ) from error
    except tomllib.TOMLDecodeError as error:
        raise SourceConfigurationError(
            f"Invalid source configuration {config_path}: {error}"
        ) from error

    entries = parsed.get("sources")
    if not isinstance(entries, list) or not entries:
        raise SourceConfigurationError(
            f"{config_path} must contain at least one [[sources]] entry"
        )

    definitions = []
    seen = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise SourceConfigurationError(
                f"sources entry {index} in {config_path} must be a table"
            )
        source_id = entry.get("id")
        adapter = entry.get("adapter")
        raw_path = entry.get("path")
        if not isinstance(source_id, str) or not SOURCE_ID_RE.fullmatch(source_id):
            raise SourceConfigurationError(
                f"sources entry {index} has an invalid id {source_id!r}"
            )
        if source_id in seen:
            raise SourceConfigurationError(f"Duplicate source id {source_id!r}")
        if adapter not in SUPPORTED_ADAPTERS:
            raise SourceConfigurationError(
                f"Source {source_id!r} uses unsupported adapter {adapter!r}"
            )
        if not isinstance(raw_path, str) or not raw_path:
            raise SourceConfigurationError(
                f"Source {source_id!r} must define a non-empty path"
            )
        path = Path(raw_path)
        if not path.is_absolute():
            path = config_path.parent / path
        definitions.append(
            SourceDefinition(id=source_id, adapter=adapter, path=path.resolve())
        )
        seen.add(source_id)
    return tuple(definitions)


def select_sources(sources, requested_id: str | None = None):
    if requested_id is None:
        return tuple(sources)
    selected = tuple(source for source in sources if source.id == requested_id)
    if not selected:
        raise SourceConfigurationError(f"Unknown source {requested_id!r}")
    return selected
