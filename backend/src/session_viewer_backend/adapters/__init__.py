from .claude import ClaudeAdapter
from .codex import CodexAdapter


ADAPTERS = {
    "claude": ClaudeAdapter(),
    "codex": CodexAdapter(),
}


def get_adapter(name: str):
    try:
        return ADAPTERS[name]
    except KeyError as error:
        raise ValueError(f"Unsupported session adapter {name!r}") from error
