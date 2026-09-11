"""The expense tables and how to read them."""

import datetime
from abc import ABC, abstractmethod
from collections.abc import Sequence
from decimal import Decimal
from typing import NamedTuple, override

from sqlalchemy import Date, DateTime, ForeignKey, Identity, Numeric, Text, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .category_filter import CategoryFilter
from .date_range import UNBOUNDED, DateRange
from .db import Base


class ExpensesUnavailableError(Exception):
    """The expenses could not be read. Not raised for an empty table."""


class LoadedExpenseFile(Base):
    """One row per expense file the loader has taken in. Mirrors schema.sql."""

    __tablename__: str = "loaded_expense_file"

    # Identity(always=True) mirrors the DDL's GENERATED ALWAYS. SQLAlchemy never emits
    # this table, so it is here to keep the two declarations in step.
    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    filename: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[str] = mapped_column(Text)
    loaded_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    # mapped_column() with no arguments rather than a bare annotation:
    # reportUninitializedInstanceVariable wants a value in the class body. The column
    # type still comes from the annotation.
    row_count: Mapped[int] = mapped_column()


class Expense(Base):
    """One row per data line of one loaded file. Mirrors schema.sql."""

    __tablename__: str = "expense"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    loaded_expense_file_id: Mapped[int] = mapped_column(
        ForeignKey("loaded_expense_file.id")
    )
    # Numeric so asyncpg hands back Decimal rather than float: this is money.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(Text)
    expense_date: Mapped[datetime.date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text)


class ExpenseRecord(NamedTuple):
    """One expense detached from the session that read it."""

    amount: Decimal
    currency: str
    expense_date: datetime.date
    category: str
    details: str


class ExpenseRepository(ABC):
    """The contract a caller depends on in order to read expenses."""

    @abstractmethod
    async def list_expenses(
        self, dates: DateRange = UNBOUNDED, categories: CategoryFilter | None = None
    ) -> Sequence[ExpenseRecord]: ...

    @abstractmethod
    async def list_categories(self) -> Sequence[str]: ...


class PostgresExpenseRepository(ExpenseRepository):
    """Reads expenses through a session it is given and does not own."""

    _session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def list_expenses(
        self, dates: DateRange = UNBOUNDED, categories: CategoryFilter | None = None
    ) -> Sequence[ExpenseRecord]:
        """Every expense within the bounds and categories given, oldest first."""
        statement = select(
            Expense.amount,
            Expense.currency,
            Expense.expense_date,
            Expense.category,
            Expense.details,
        )
        # Both bounds inclusive, and an open one adds no clause at all. That they are
        # the right way round is the type's guarantee, not something checked here.
        if dates.start is not None:
            statement = statement.where(Expense.expense_date >= dates.start)
        if dates.end is not None:
            statement = statement.where(Expense.expense_date <= dates.end)
        # sorted() for a deterministic clause; that no name is blank is the type's
        # guarantee, like the range's ordering above.
        if categories is not None:
            statement = statement.where(Expense.category.in_(sorted(categories.names)))
        try:
            rows = await self._session.execute(
                statement.order_by(Expense.expense_date, Expense.id)
            )
        except (SQLAlchemyError, OSError) as exc:
            # OSError as well: asyncpg lets asyncio's ConnectionRefusedError out
            # unwrapped when nothing is listening.
            raise ExpensesUnavailableError("expense query failed") from exc
        # The select names the columns in ExpenseRecord's field order.
        return [ExpenseRecord(*row) for row in rows.all()]

    @override
    async def list_categories(self) -> Sequence[str]:
        """Every category with an expense in it, once each, in name order."""
        statement = select(Expense.category).distinct().order_by(Expense.category)
        try:
            names = await self._session.scalars(statement)
        except (SQLAlchemyError, OSError) as exc:
            raise ExpensesUnavailableError("category query failed") from exc
        return names.all()
