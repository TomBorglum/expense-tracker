"""PostgreSQL access: the tables, how to read them, and how reading them fails.

Persistence only. A caller supplies a session and handles one exception per repository;
what it does with the failure is its own business.
"""

import datetime
from abc import ABC, abstractmethod
from collections.abc import Sequence
from decimal import Decimal
from typing import NamedTuple, override

from sqlalchemy import Date, DateTime, ForeignKey, Identity, Numeric, Text, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class GreetingUnavailableError(Exception):
    """No greeting could be read.

    One type for every way that happens, so a caller handles this rather than the
    driver exceptions underneath it.
    """


class ExpensesUnavailableError(Exception):
    """The expenses could not be read.

    Deliberately not raised for an empty table: a database nobody has run the loader
    against yet is a legitimate state, and the endpoint answers it with an empty list.
    Only a failure to reach or query PostgreSQL gets here.
    """


class Base(DeclarativeBase):
    """Declarative root. It gives the models below a typed metaclass, nothing more."""


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


class LoadedFile(Base):
    """One row per CSV file the loader has taken in.

    Mirrors schema.sql, which is the authoritative definition. The ledger, and the only
    thing that makes re-running the loader a no-op - see the comment on the table.
    """

    __tablename__: str = "loaded_file"

    # Identity(always=True) rather than an implicit sequence, matching the DDL's
    # GENERATED ALWAYS. SQLAlchemy never emits this table, so the construct is here to
    # keep the two declarations honest with each other rather than to create anything.
    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    filename: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[str] = mapped_column(Text)
    loaded_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    # mapped_column() with no arguments rather than a bare annotation: recommended
    # mode's reportUninitializedInstanceVariable wants a value in the class body, and
    # the descriptor is that value. The column type still comes from the annotation.
    row_count: Mapped[int] = mapped_column()


class Expense(Base):
    """One row per data line of one loaded file. Mirrors schema.sql."""

    __tablename__: str = "expense"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    loaded_file_id: Mapped[int] = mapped_column(ForeignKey("loaded_file.id"))
    # Numeric with asdecimal so asyncpg hands back Decimal rather than float: this is
    # money, and a float round trip is how totals drift.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(Text)
    expense_date: Mapped[datetime.date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text)


class ExpenseRecord(NamedTuple):
    """One expense as a caller sees it: the row without the ORM instance around it.

    A repository returns these rather than Expense objects so nothing outside this
    module holds something attached to a session that is about to close. The surrogate
    id and the ledger reference are not in it: neither means anything to a client.
    """

    amount: Decimal
    currency: str
    expense_date: datetime.date
    category: str
    details: str


class GreetingRepository(ABC):
    """The contract a caller depends on in order to read the greeting.

    Implementations subclass it. Matching the shape is not enough, so the coupling is
    always on the line a reader sees.

    @abstractmethod is what enforces that: without it the `...` below is an ordinary
    method returning None. Ruff's B027 rejects the decorator's removal.
    """

    @abstractmethod
    async def get_current_greeting(self) -> str: ...


class PostgresGreetingRepository(GreetingRepository):
    """Reads the greeting through a session it is given and does not own."""

    # Declared at class level because recommended mode's reportUnannotatedClassAttribute
    # wants every attribute of a non-final class typed - the same rule that annotates
    # Greeting.__tablename__ above.
    _session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
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


class ExpenseRepository(ABC):
    """The contract a caller depends on in order to read expenses.

    Implementations subclass it, for the same reason GreetingRepository's do: matching
    the shape is not enough, so the coupling is always on the line a reader sees, and
    dependency_overrides - an untyped dict - cannot be handed a look-alike.
    """

    @abstractmethod
    async def list_expenses(self) -> Sequence[ExpenseRecord]: ...


class PostgresExpenseRepository(ExpenseRepository):
    """Reads expenses through a session it is given and does not own."""

    _session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def list_expenses(self) -> Sequence[ExpenseRecord]:
        """Every expense, newest first, or ExpensesUnavailableError if the read fails.

        No pagination and no filtering: the endpoint offers neither, and the index in
        schema.sql is built for exactly this ordering. The id tiebreak keeps a page of
        same-day rows in a stable order rather than whatever the scan happens to yield.

        An empty table returns an empty sequence. That is not an error - unlike the
        greeting's missing row - because a freshly initialised database that nobody has
        run the loader against yet is a legitimate state.
        """
        try:
            rows = await self._session.execute(
                select(
                    Expense.amount,
                    Expense.currency,
                    Expense.expense_date,
                    Expense.category,
                    Expense.details,
                ).order_by(Expense.expense_date.desc(), Expense.id.desc())
            )
        except (SQLAlchemyError, OSError) as exc:
            # OSError alongside SQLAlchemyError for the same reason as the greeting
            # above: asyncpg lets asyncio's ConnectionRefusedError out unconverted.
            raise ExpensesUnavailableError("expense query failed") from exc
        # The select names the columns in ExpenseRecord's field order, so each row maps
        # across positionally.
        return [ExpenseRecord(*row) for row in rows.all()]
