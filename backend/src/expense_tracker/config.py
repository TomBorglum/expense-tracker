"""Settings, read from the environment."""

from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings
from sqlalchemy import URL, make_url


class DatabaseSettings(BaseSettings):
    """DATABASE_URL, or the four parts a local DSN is composed from.

    Reads the environment and nothing else. Putting backend/.env into it is direnv's job
    and poe's, so no path is resolved here and none needs to be.
    """

    database_url: str | None = None
    pguser: str | None = None
    pghost: str | None = None
    pgport: int | None = None
    pgdatabase: str | None = None

    @model_validator(mode="after")
    def _needs_a_source(self) -> Self:
        """No fallback: a process handed neither DATABASE_URL nor all four parts refuses
        to start rather than dialling its own loopback."""
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
                f"set DATABASE_URL, or all of {wanted}."
                + " backend/.env holds the local values; `direnv allow` or `pixi run`"
                + " is what puts them in the environment."
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
    return DatabaseSettings().dsn
