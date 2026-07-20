"""Application configuration objects.

Values are read from the environment so the same image can run in different
contexts without a rebuild. Defaults are development-friendly; anything
security-sensitive must be overridden in production.
"""

import os
from pathlib import Path


class Config:
    """Base configuration shared by every environment."""

    # Overridden in production via the environment. The development default
    # exists so `pixi run serve` works without any setup.
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev")

    # Absolute path to the SQLite file. Set by create_app() to live inside the
    # Flask instance folder unless the environment overrides it.
    DATABASE: str = ""

    @staticmethod
    def database_path(instance_path: str) -> str:
        """Resolve the SQLite path, preferring an explicit DATABASE env var."""
        override = os.environ.get("DATABASE")
        if override:
            return override
        return str(Path(instance_path) / "expense-tracker.sqlite")


class DevelopmentConfig(Config):
    DEBUG: bool = True


class ProductionConfig(Config):
    DEBUG: bool = False
