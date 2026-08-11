"""Settings, read from the environment and from backend/.env."""

from pathlib import Path
from typing import ClassVar, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url

# Resolved from this file rather than the working directory, so `uvicorn --factory`
# finds the same two files wherever it is launched from. A deployment installs the
# wheel, whose only contents are src/expense_tracker, so this lands beside
# site-packages and neither file exists - which is what makes a container fall through
# to DATABASE_URL or fail, instead of reading a developer's settings.
_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _env_files() -> tuple[Path, Path]:
    """The dotenv layers, lowest first."""
    return (_BACKEND_DIR / ".env", _BACKEND_DIR / ".env.local")


class DatabaseSettings(BaseSettings):
    """DATABASE_URL, or the four parts a local DSN is composed from."""

    # Environment beats both files and .env.local beats .env, which is
    # pydantic-settings' documented precedence. extra="ignore" because a dotenv file is
    # read whole: an unrelated key in somebody's .env.local must not fail startup.
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str | None = None
    pguser: str | None = None
    pghost: str | None = None
    pgport: int | None = None
    pgdatabase: str | None = None

    @classmethod
    def load(cls, env_files: tuple[Path, ...] | None, **values: str) -> Self:
        """Reads the settings, layering `env_files` under the environment. None skips
        the files entirely."""
        # pydantic synthesizes __init__ from the fields above, which hides the
        # _env_file parameter BaseSettings itself declares.
        return cls(_env_file=env_files, **values)  # pyright: ignore[reportCallIssue]

    @model_validator(mode="after")
    def _needs_a_source(self) -> Self:
        """No fallback: a process that finds neither refuses to start rather than
        dialling its own loopback."""
        if self.database_url:
            return self
        missing = [
            name
            for name, value in (
                ("PGUSER", self.pguser),
                ("PGHOST", self.pghost),
                ("PGPORT", self.pgport),
                ("PGDATABASE", self.pgdatabase),
            )
            if value is None
        ]
        if missing:
            wanted = ", ".join(missing)
            raise ValueError(
                f"set DATABASE_URL, or all of {wanted}; backend/.env has local values"
            )
        return self

    @property
    def dsn(self) -> URL:
        """Built by SQLAlchemy rather than by interpolation, so a part containing @, :
        or / is escaped instead of producing a URL that parses as something else."""
        if self.database_url:
            return make_url(self.database_url)
        return URL.create(
            "postgresql+asyncpg",
            username=self.pguser,
            host=self.pghost,
            port=self.pgport,
            database=self.pgdatabase,
        )


def database_url() -> URL:
    """The DSN to connect with.

    A URL rather than a str, so str() and repr() redact any password - one that reaches
    a log or a traceback cannot leak. DATABASE_URL overrides the four parts wholesale,
    which is how a deployment points the API at somebody else's database.
    """
    return DatabaseSettings.load(_env_files()).dsn
