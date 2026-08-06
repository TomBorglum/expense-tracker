"""PostgreSQL access: the greeting table, how to read it, and how reading it fails.

Persistence only. A caller supplies a session and handles one exception; what it does
with the failure is its own business.
"""

from typing import Protocol

from sqlalchemy import Text, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class GreetingUnavailableError(Exception):
    """No greeting could be read.

    One type for every way that happens, so a caller handles this rather than the
    driver exceptions underneath it.
    """


class Base(DeclarativeBase):
    """Declarative root. It exists to give Greeting a typed metaclass, nothing more."""


class Greeting(Base):
    """The greeting table, which holds exactly one row.

    Mirrors schema.sql, which is the authoritative definition - this class never
    creates the table, it only reads it.
    """

    # Annotated because recommended mode's reportUnannotatedClassAttribute wants every
    # attribute of a non-final class typed. `str` rather than `Mapped[str]` is what
    # keeps SQLAlchemy treating it as configuration instead of a column.
    __tablename__: str = "greeting"

    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str] = mapped_column(Text)


class GreetingRepository(Protocol):
    """What a caller needs in order to read the greeting.

    A Protocol rather than a base class: an implementation satisfies this by shape, so
    the test double is checked against it without inheriting from anything. Not
    @runtime_checkable - nothing isinstance-checks it, and static checking needs no
    decorator.
    """

    async def get_current_greeting(self) -> str: ...


class PostgresGreetingRepository:
    """Reads the greeting through a session it is given and does not own."""

    # Declared at class level because recommended mode's reportUnannotatedClassAttribute
    # wants every attribute of a non-final class typed - the same rule that annotates
    # Greeting.__tablename__ above.
    _session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_current_greeting(self) -> str:
        """The greeting text, or GreetingUnavailableError if there is none to give.

        Async because asyncpg is: a blocking driver would hold the event loop for the
        length of a round trip.
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
            # Table present, seed row gone: schema.sql ran but its INSERT did not, or
            # something deleted the row afterwards. Not a value the caller can use, so
            # it raises rather than returning None and widening the return type.
            raise GreetingUnavailableError("greeting row is missing")
        return message
