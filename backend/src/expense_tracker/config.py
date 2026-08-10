"""Settings, read from the environment."""

import os


def database_url() -> str:
    """The DSN to connect with. Required, with no fallback, so a process that cannot
    find the setting refuses to start rather than dialling its own loopback."""
    url = os.environ.get("DATABASE_URL")
    if url is None:
        raise RuntimeError(
            "DATABASE_URL is not set; `pixi run` supplies the development value"
        )
    return url
