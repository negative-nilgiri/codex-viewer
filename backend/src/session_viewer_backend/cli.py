import argparse
from dataclasses import asdict
import json

from .config import Settings
from .discovery import discover_sessions
from .rollout import RolloutError
from .sources import SourceConfigurationError, load_sources
from .sync import sync_session


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Index local agent session transcripts")
    commands = parser.add_subparsers(dest="command", required=True)
    sync_parser = commands.add_parser("sync", help="Incrementally index one session")
    sync_parser.add_argument("source", help="Configured source, for example codex_2 or claude")
    sync_parser.add_argument("session_id", help="Full session UUID or unique prefix")
    discover_parser = commands.add_parser(
        "discover", help="Catalog mounted transcripts without indexing their messages"
    )
    discover_parser.add_argument(
        "source",
        nargs="?",
        help="Optional configured source; omit to scan every source",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    settings = Settings.from_environment()
    try:
        sources = load_sources(settings.sources_path)
    except SourceConfigurationError as error:
        raise SystemExit(str(error)) from error
    if args.command == "sync":
        try:
            result = sync_session(
                settings.database_path,
                sources,
                args.source,
                args.session_id,
                settings.session_metadata_path,
            )
        except (OSError, RolloutError, ValueError) as error:
            raise SystemExit(str(error)) from error
        print(json.dumps(asdict(result), indent=2))
    elif args.command == "discover":
        try:
            result = discover_sessions(
                settings.database_path,
                sources,
                args.source,
                settings.session_metadata_path,
            )
        except (OSError, RolloutError, ValueError) as error:
            raise SystemExit(str(error)) from error
        print(json.dumps(result.as_dict(), indent=2))
