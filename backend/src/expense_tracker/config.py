"""Settings, read from the environment and from backend/.env."""

import os
from functools import cache
from pathlib import Path

from dotenv import dotenv_values

# Resolved from this file rather than the working directory, so `uvicorn --factory`
# finds the same two files wherever it is launched from.
_BACKEND_DIR = Path(__file__).resolve().parents[2]

_CONNECTION_SETTINGS = ("PGUSER", "PGHOST", "PGPORT", "PGDATABASE")


@cache
def _dotenv() -> dict[str, str]:
    """backend/.env with backend/.env.local layered over it; either may be absent."""
    values = {
        **dotenv_values(_BACKEND_DIR / ".env"),
        **dotenv_values(_BACKEND_DIR / ".env.local"),
    }
    return {name: value for name, value in values.items() if value}


def _setting(name: str) -> str:
    """One setting, from the environment if it is there and from the files otherwise.

    Required, with no fallback, so a process that cannot find one refuses to start
    rather than dialling its own loopback."""
    value = os.environ.get(name) or _dotenv().get(name)
    if not value:
        raise RuntimeError(f"{name} is not set; backend/.env supplies the local value")
    return value


def database_url() -> str:
    """The DSN to connect with, composed from the connection settings.

    DATABASE_URL overrides them wholesale, which is how a deployment points the API at a
    database that is nobody's local cluster."""
    url = os.environ.get("DATABASE_URL") or _dotenv().get("DATABASE_URL")
    if url:
        return url
    user, host, port, database = (_setting(name) for name in _CONNECTION_SETTINGS)
    return f"postgresql+asyncpg://{user}@{host}:{port}/{database}"
