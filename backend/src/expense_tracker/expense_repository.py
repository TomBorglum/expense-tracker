"""The expense tables and how to read them."""

import datetime
from abc import ABC, abstractmethod
from collections.abc import Sequence
from decimal import Decimal
from typing import NamedTuple, override

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Numeric,
    Text,
    case,
    false,
    select,
    true,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import ColumnElement

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


class Category(Base):
    """One row per node of the category tree. Mirrors schema.sql."""

    __tablename__: str = "category"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    category: Mapped[str] = mapped_column(Text, unique=True)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    level: Mapped[int] = mapped_column()
    first_filename: Mapped[str] = mapped_column(Text)


class ExpenseRecord(NamedTuple):
    """One expense detached from the session that read it."""

    amount: Decimal
    currency: str
    expense_date: datetime.date
    category: str
    key: str


class CategoryRecord(NamedTuple):
    """One category node detached from the session that read it.

    The real path and its slug only. `name`, `parent` and `parent_slug` are each the
    path helpers applied to one of these, so storing them would give one fact two homes.
    """

    category: str
    slug: str


def _under(slug: str) -> ColumnElement[bool]:
    """Matches the slug itself and every slug below it."""
    # The separator in the LIKE is what makes this a prefix of levels rather than one
    # of characters: without it, food would match foodstuffs. autoescape is kept though
    # a slug holds neither % nor _ - dropping it would lean on the slug alphabet for
    # nothing, and this is the same clause the real path was matched by.
    return (Category.slug == slug) | Category.slug.startswith(
        slug + SEPARATOR, autoescape=True
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


class ExpenseRepository(ABC):
    """The contract a caller depends on in order to read expenses."""

    @abstractmethod
    async def list_expenses(
        self, dates: DateRange = UNBOUNDED, categories: CategorySelection = EVERYTHING
    ) -> Sequence[ExpenseRecord]: ...

    @abstractmethod
    async def list_categories(
        self, levels: LevelRange = TOP_LEVEL
    ) -> Sequence[CategoryRecord]: ...


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
        # everything adds no clause at all - not even the join - so a request naming no
        # category reaches the same statement it reached before one could be deselected.
        #
        # The join is what turns a slug the request sent into the path a row carries.
        # Every stored category is a category row, so it drops nothing.
        if (selects := _selects(categories)) is not None:
            statement = statement.join(
                Category, Category.category == Expense.category
            ).where(selects)
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
    async def list_categories(
        self, levels: LevelRange = TOP_LEVEL
    ) -> Sequence[CategoryRecord]:
        """Every category node at the levels given, with its slug, in path order.

        A node is listed whether or not an expense sits at exactly it, so an ancestor
        nothing is filed directly under is still one a client can ask for. That holds
        because the loader writes every ancestor as a row, rather than because this
        truncates a longer path.
        """
        statement = (
            select(Category.category, Category.slug)
            .where(Category.level.in_(list(levels.levels)))
            .order_by(Category.category)
        )
        try:
            rows = await self._session.execute(statement)
        except (SQLAlchemyError, OSError) as exc:
            raise ExpensesUnavailableError("category query failed") from exc
        # The select names the columns in CategoryRecord's field order.
        return [CategoryRecord(*row) for row in rows.all()]
