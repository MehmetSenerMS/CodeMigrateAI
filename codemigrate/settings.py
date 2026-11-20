"""Shared local configuration for all CodeMigrate AI runners.

API URLs live in the project-root .env file, not in individual scripts.
An explicitly set CODEMIGRATE_API_URL environment variable takes precedence.
This module uses the Python standard library only.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_env_file(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        name, separator, value = line.partition("=")
        if separator and name.strip() == key:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value
    return None


def get_api_url(env_file: Path | None = None) -> str:
    """Return a validated URL shared by /health, /chat and /migrate clients.

    Resolution order: process environment -> project-root .env.
    Read every time so Spyder can pick up a changed .env on the next run.
    """
    variable = "CODEMIGRATE_API_URL"
    raw_url = os.environ.get(variable) or _read_env_file(
        env_file if env_file is not None else PROJECT_ROOT / ".env",
        variable,
    )

    if not raw_url or not raw_url.strip():
        raise RuntimeError(
            "Missing CODEMIGRATE_API_URL. Copy .env.example to .env in "
            "C:\\CodeMigrateAI and set your current inference API URL."
        )

    url = raw_url.strip().rstrip("/")
    parts = urlsplit(url)
    is_local_http = parts.scheme == "http" and parts.hostname in {
        "127.0.0.1", "localhost", "::1",
    }

    if (
        (parts.scheme != "https" and not is_local_http)
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or bool(parts.query)
        or bool(parts.fragment)
    ):
        raise ValueError(
            "CODEMIGRATE_API_URL must be an HTTPS base address "
            "(or local HTTP), without /chat, /migrate, query, or credentials."
        )

    return url
