"""The expense tables and how to read them."""

import datetime
from abc import ABC, abstractmethod
from collections.abc import Sequence
from decimal import Decimal
from typing import NamedTuple, override

from sqlalchemy import (
    ARRAY,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    Text,
    func,
    or_,
    select,
    union,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import ColumnElement, Select

from .category_filter import SEPARATOR, CategoryFilter
from .date_range import UNBOUNDED, DateRange
from .db import Base
from .level_range import TOP_LEVEL, LevelRange


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
    """One row per imported record of one loaded file. Mirrors schema.sql."""

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


def _under(path: str) -> ColumnElement[bool]:
    """Matches the path itself and every path below it."""
    # The separator in the LIKE is what makes this a prefix of levels rather than one
    # of characters: without it, Food would match Foodstuffs. autoescape because a level
    # may hold % or _, which the path CHECK does not forbid and a bare LIKE would read
    # as a wildcard.
    return (Expense.category == path) | Expense.category.startswith(
        path + SEPARATOR, autoescape=True
    )


def _at_level(depth: int) -> Select[tuple[str]]:
    """Every stored category cut to `depth` levels, over the rows that go that deep."""
    levels = func.string_to_array(Expense.category, SEPARATOR, type_=ARRAY(Text))
    return (
        select(
            func.array_to_string(levels[1:depth], SEPARATOR, type_=Text).label(
                "category"
            )
        )
        # What makes a level exact: an array slice past the end returns the array, so
        # without this a depth-1 row would be listed again at level 2.
        .where(func.array_length(levels, 1, type_=Integer) >= depth)
        # Not redundant beside the UNION below: union() over a single select compiles to
        # a bare SELECT, and one level is what the default request asks for.
        .distinct()
    )


class ExpenseRepository(ABC):
    """The contract a caller depends on in order to read expenses."""

    @abstractmethod
    async def list_expenses(
        self, dates: DateRange = UNBOUNDED, categories: CategoryFilter | None = None
    ) -> Sequence[ExpenseRecord]: ...

    @abstractmethod
    async def list_categories(
        self, levels: LevelRange = TOP_LEVEL
    ) -> Sequence[str]: ...


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
        # A name matches itself and every path below it, which over a corpus of depth-1
        # categories is plain equality - so this reads the same as the IN clause it
        # replaces until a path actually has levels.
        if categories is not None:
            statement = statement.where(
                or_(*(_under(name) for name in sorted(categories.names)))
            )
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
    async def list_categories(self, levels: LevelRange = TOP_LEVEL) -> Sequence[str]:
        """Every category path at the levels given, once each, in path order.

        A path is listed whether or not an expense sits at exactly it, so an ancestor
        nothing is filed directly under is still a node a client can ask for.
        """
        paths = union(*(_at_level(depth) for depth in levels.levels))
        try:
            names = await self._session.scalars(
                paths.order_by(paths.selected_columns.category)
            )
        except (SQLAlchemyError, OSError) as exc:
            raise ExpensesUnavailableError("category query failed") from exc
        return names.all()
