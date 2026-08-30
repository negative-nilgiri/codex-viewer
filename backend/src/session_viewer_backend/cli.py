import argparse
from dataclasses import asdict
import json

from .config import Settings
from .rollout import RolloutError
from .sync import sync_session


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Index Codex session rollouts")
    commands = parser.add_subparsers(dest="command", required=True)
    sync_parser = commands.add_parser("sync", help="Incrementally index one session")
    sync_parser.add_argument("profile", help="Mounted Codex profile, for example codex_2")
    sync_parser.add_argument("session_id", help="Full session UUID or unique prefix")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    settings = Settings.from_environment()
    if args.command == "sync":
        try:
            result = sync_session(
                settings.database_path,
                settings.sessions_root,
                args.profile,
                args.session_id,
            )
        except (OSError, RolloutError, ValueError) as error:
            raise SystemExit(str(error)) from error
        print(json.dumps(asdict(result), indent=2))
