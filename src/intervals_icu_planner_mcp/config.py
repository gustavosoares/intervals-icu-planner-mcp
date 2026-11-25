"""Find the intervals.icu API key. The key itself is never printed or logged."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping

ENV_VAR = "INTERVALS_ICU_API_KEY"
LEGACY_ENV_VAR = "INTERVALS_API_KEY"  # used by 0.0.x; still read, with a warning
PLANS_DIR_ENV_VAR = "INTERVALS_ICU_PLANS_DIR"


def parse_dotenv(text: str) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, optional 'export', quotes, # comments."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def find_api_key(
    env: Mapping[str, str] | None = None,
    dotenv_path: str = ".env",
    warn: Callable[[str], None] = _warn,
) -> str | None:
    """Return the key from the environment, else from a .env file, else None.

    ``INTERVALS_ICU_API_KEY`` wins. The old ``INTERVALS_API_KEY`` name is accepted
    as a fallback and triggers a deprecation warning (which never includes the key).
    """
    env = os.environ if env is None else env
    try:
        with open(dotenv_path, encoding="utf-8") as f:
            dotenv = parse_dotenv(f.read())
    except OSError:
        dotenv = {}

    for name in (ENV_VAR, LEGACY_ENV_VAR):
        value = env.get(name) or dotenv.get(name)
        if value:
            if name == LEGACY_ENV_VAR:
                warn(f"warning: {LEGACY_ENV_VAR} is deprecated, rename it to {ENV_VAR}")
            return value
    return None


def find_plans_dir(env: Mapping[str, str] | None = None) -> str | None:
    """The folder plans must live in, from ``INTERVALS_ICU_PLANS_DIR``; None means anywhere.

    An empty value, or a ``${user_config...}`` placeholder that Claude Desktop
    left unfilled because the optional setting is blank, means unset.
    """
    env = os.environ if env is None else env
    value = env.get(PLANS_DIR_ENV_VAR, "").strip()
    if not value or value.startswith("${"):
        return None
    return os.path.expanduser(value)
