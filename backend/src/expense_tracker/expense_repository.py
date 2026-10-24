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
    case,
    false,
    func,
    select,
    true,
    union,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import ColumnElement, Select

from .category_filter import EVERYTHING, SEPARATOR, CategorySelection
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
    key: Mapped[str] = mapped_column(Text)


class ExpenseRecord(NamedTuple):
    """One expense detached from the session that read it."""

    amount: Decimal
    currency: str
    expense_date: datetime.date
    category: str
    key: str


def _under(path: str) -> ColumnElement[bool]:
    """Matches the path itself and every path below it."""
    # The separator in the LIKE is what makes this a prefix of levels rather than one
    # of characters: without it, Food would match Foodstuffs. autoescape because a level
    # may hold % or _, which the path CHECK does not forbid and a bare LIKE would read
    # as a wildcard.
    return (Expense.category == path) | Expense.category.startswith(
        path + SEPARATOR, autoescape=True
    )


def _sign(selected: bool) -> ColumnElement[bool]:
    """A flip's sign as SQL, spelled out rather than bound: a parameter in every arm of
    a CASE leaves PostgreSQL unable to type the expression."""
    return true() if selected else false()


def _selects(selection: CategorySelection) -> ColumnElement[bool] | None:
    """Whether a row's category is selected, or None when every row's is.

    The arms are read in flip order, so the first one matching a row is the longest path
    over it - which is what makes a child's own sign beat the parent it sits under.
    """
    if selection.everything():
        return None
    flips = selection.flips()
    if not flips:
        # Nothing flips and the root is not selected, so no row is. An empty selection
        # is a request in its own right rather than the unfiltered one.
        return false()
    return case(
        *((_under(path), _sign(selected)) for path, selected in flips),
        else_=_sign(selection.default),
    ).is_(True)


def _at_level(depth: int) -> Select[str]:
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
        self, dates: DateRange = UNBOUNDED, categories: CategorySelection = EVERYTHING
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
        self, dates: DateRange = UNBOUNDED, categories: CategorySelection = EVERYTHING
    ) -> Sequence[ExpenseRecord]:
        """Every expense within the bounds and selected categories, oldest first."""
        statement = select(
            Expense.amount,
            Expense.currency,
            Expense.expense_date,
            Expense.category,
            Expense.key,
        )
        # Both bounds inclusive, and an open one adds no clause at all. That they are
        # the right way round is the type's guarantee, not something checked here.
        if dates.start is not None:
            statement = statement.where(Expense.expense_date >= dates.start)
        if dates.end is not None:
            statement = statement.where(Expense.expense_date <= dates.end)
        # The order the arms are read in is the type's, like the range's ordering
        # above, and that no name is blank is its guarantee too. A selection covering
        # everything adds no clause at all, so a request naming no category reaches the
        # same statement it reached before one could be deselected.
        if (selects := _selects(categories)) is not None:
            statement = statement.where(selects)
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
