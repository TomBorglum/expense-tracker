"""The greeting table and how to read it."""

from abc import ABC, abstractmethod
from typing import override

from sqlalchemy import Text, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class GreetingUnavailableError(Exception):
    """The greeting could not be read."""


class Greeting(Base):
    """The greeting table, which holds exactly one row. Mirrors schema.sql, which is
    the authoritative definition; this class never creates the table."""

    # Annotated because reportUnannotatedClassAttribute wants every attribute of a
    # non-final class typed. Plain `str` rather than `Mapped[str]` keeps SQLAlchemy
    # treating it as configuration instead of a column.
    __tablename__: str = "greeting"

    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str] = mapped_column(Text)


class GreetingRepository(ABC):
    """The contract a caller depends on in order to read the greeting."""

    @abstractmethod
    async def get_current_greeting(self) -> str: ...


class PostgresGreetingRepository(GreetingRepository):
    """Reads the greeting through a session it is given and does not own."""

    # Declared at class level for reportUnannotatedClassAttribute, as above.
    _session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def get_current_greeting(self) -> str:
        """The greeting text, or GreetingUnavailableError if there is none."""
        try:
            message = await self._session.scalar(
                select(Greeting.message).order_by(Greeting.id).limit(1)
            )
        except (SQLAlchemyError, OSError) as exc:
            # OSError as well: when nothing is listening, asyncpg lets asyncio's
            # ConnectionRefusedError out unwrapped.
            raise GreetingUnavailableError("greeting query failed") from exc
        if message is None:
            raise GreetingUnavailableError("greeting row is missing")
        return message
