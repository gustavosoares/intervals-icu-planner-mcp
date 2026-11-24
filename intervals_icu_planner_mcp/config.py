"""Find the intervals.icu API key."""

from __future__ import annotations

import os
from typing import Dict, Optional

ENV_VAR = "INTERVALS_API_KEY"


def parse_dotenv(text: str) -> Dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, optional 'export', quotes, # comments."""
    values: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def find_api_key(env: Optional[Dict[str, str]] = None, dotenv_path: str = ".env") -> Optional[str]:
    """Return the key from the environment, else from a .env file, else None."""
    env = os.environ if env is None else env
    if env.get(ENV_VAR):
        return env[ENV_VAR]
    try:
        with open(dotenv_path, encoding="utf-8") as f:
            return parse_dotenv(f.read()).get(ENV_VAR) or None
    except OSError:
        return None
