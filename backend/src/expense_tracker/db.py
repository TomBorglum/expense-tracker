"""PostgreSQL access for the one thing this API serves.

Persistence only: the table, how to read it, and the one exception a caller has to
handle. Nothing here imports fastapi or knows a status code - mapping the failure to a
response is create_app()'s job - and nothing here imports deps.py, which is what keeps
the wiring pointing one way.
"""

from sqlalchemy import Text, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class GreetingUnavailableError(Exception):
    """No greeting could be read. Mapped to 503 by create_app()."""


class Base(DeclarativeBase):
    """Declarative root. It exists to give Greeting a typed metaclass, nothing more."""


class Greeting(Base):
    """The single row `GET /api/greeting` serves.

    Mirrors schema.sql, which is the authoritative definition - this class never
    creates the table, it only reads it.
    """

    # Annotated because recommended mode's reportUnannotatedClassAttribute wants every
    # attribute of a non-final class typed. `str` rather than `Mapped[str]` is what
    # keeps SQLAlchemy treating it as configuration instead of a column.
    __tablename__: str = "greeting"

    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str] = mapped_column(Text)


class GreetingRepository:
    """Reads the greeting. The session is supplied per request by deps.py."""

    # Declared at class level because recommended mode's reportUnannotatedClassAttribute
    # wants every attribute of a non-final class typed - the same rule that annotates
    # Greeting.__tablename__ above.
    _session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_current_greeting(self) -> str:
        """The greeting text, read from PostgreSQL.

        Async because the app runs on uvicorn's event loop: a blocking driver would
        stall every other request while one waited on a socket.
        """
        try:
            # order_by/limit rather than get(1): the singleton CHECK lives in the
            # schema, and this stays correct without it.
            message = await self._session.scalar(
                select(Greeting.message).order_by(Greeting.id).limit(1)
            )
        except (SQLAlchemyError, OSError) as exc:
            # OSError as well as SQLAlchemyError: when nothing is listening, asyncpg
            # lets asyncio's ConnectionRefusedError out, and SQLAlchemy only wraps what
            # its DBAPI shim recognises, so the raw OSError arrives here unconverted.
            raise GreetingUnavailableError("greeting query failed") from exc
        if message is None:
            # Table present, seed row gone. A deployment fault rather than a client
            # one, and the same status a client should retry on.
            raise GreetingUnavailableError("greeting row is missing")
        return message
