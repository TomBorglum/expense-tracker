"""Summing expenses over the period a request asks for."""

import calendar
import datetime
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum
from typing import NamedTuple

from .date_range import UNBOUNDED, DateRange
from .expense_repository import ExpenseRecord


class AggregationError(Exception):
    """The expenses cannot be totalled the way the request asks for."""


class Period(StrEnum):
    """The span one total covers."""

    MONTH = "month"


class Grouping(StrEnum):
    """The dimension rows are split by beyond the period and the currency."""

    CATEGORY = "category"


class TotalRecord(NamedTuple):
    """One summed amount, the span it covers, and the key it was summed under."""

    period: str
    from_date: datetime.date
    to_date: datetime.date
    # None together, and only when the period holds no expenses at all.
    amount: Decimal | None
    currency: str | None
    # Also None when the request did not group by category.
    category: str | None


def parse_period(value: str | None) -> Period:
    """The requested period, or AggregationError. An absent value is refused."""
    if value is None:
        raise AggregationError("period is required")
    try:
        return Period(value)
    except ValueError as exc:
        raise AggregationError(f"unknown period: {value}") from exc


def parse_grouping(value: str | None) -> Grouping | None:
    """The requested grouping, or None for an absent one, or AggregationError."""
    if value is None:
        return None
    try:
        return Grouping(value)
    except ValueError as exc:
        raise AggregationError(f"unknown group_by: {value}") from exc


def aggregate(
    expenses: Sequence[ExpenseRecord],
    period: Period,
    grouping: Grouping | None,
    dates: DateRange = UNBOUNDED,
) -> list[TotalRecord]:
    """Every period from the oldest expense to the newest, oldest first."""
    sums: defaultdict[tuple[str, str, str | None], Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    for record in expenses:
        # currency is in the key whatever was asked for: two currencies added together
        # are a number that means nothing.
        key = (
            _period_key(record.expense_date, period),
            record.currency,
            record.category if grouping is Grouping.CATEGORY else None,
        )
        sums[key] += record.amount
    grouped: defaultdict[str, list[tuple[str, str | None, Decimal]]] = defaultdict(list)
    for (period_key, currency, category), amount in sums.items():
        grouped[period_key].append((currency, category, amount))
    totals: list[TotalRecord] = []
    # The walk supplies the period order, so only the rows within one are sorted here.
    for period_key in _period_keys(expenses, period):
        start, end = _clamp(_period_bounds(period_key, period), dates)
        rows = sorted(grouped[period_key], key=lambda row: (row[1] or "", row[0]))
        if not rows:
            # A period nobody spent in is still a row, carrying the span and nothing
            # else: absent says "none recorded" where 0.00 would say "these cancelled
            # out", which a month of refunds can genuinely do.
            totals.append(TotalRecord(period_key, start, end, None, None, None))
        totals.extend(
            TotalRecord(period_key, start, end, amount, currency, category)
            for currency, category, amount in rows
        )
    return totals


def _period_key(day: datetime.date, period: Period) -> str:
    # Fixed width, so ordering the strings orders the periods.
    match period:
        case Period.MONTH:
            return f"{day.year:04d}-{day.month:02d}"


def _period_keys(expenses: Sequence[ExpenseRecord], period: Period) -> list[str]:
    """Every key from the oldest expense's period to the newest's, oldest first."""
    # min and max rather than the ends of the sequence: the repository's order is not
    # this module's to rely on. No expenses is no extent to walk, which is the empty
    # response with no branch of its own.
    if not expenses:
        return []
    days = [record.expense_date for record in expenses]
    match period:
        case Period.MONTH:
            oldest = _month_index(min(days))
            newest = _month_index(max(days))
            return [
                f"{index // 12:04d}-{index % 12 + 1:02d}"
                for index in range(oldest, newest + 1)
            ]


def _month_index(day: datetime.date) -> int:
    # Months counted from year zero, so stepping one is adding one.
    return day.year * 12 + day.month - 1


def _period_bounds(
    period_key: str, period: Period
) -> tuple[datetime.date, datetime.date]:
    """The whole calendar span the key names, both ends inclusive."""
    match period:
        case Period.MONTH:
            year, month = int(period_key[:4]), int(period_key[5:])
            _, last = calendar.monthrange(year, month)
            return datetime.date(year, month, 1), datetime.date(year, month, last)


def _clamp(
    bounds: tuple[datetime.date, datetime.date], dates: DateRange
) -> tuple[datetime.date, datetime.date]:
    # A requested bound narrows a period only when it falls inside it. One outside
    # cannot narrow this period at all, and moving the span to it would invert it. The
    # second test reads the start the first may already have moved.
    start, end = bounds
    if dates.start is not None and start < dates.start <= end:
        start = dates.start
    if dates.end is not None and start <= dates.end < end:
        end = dates.end
    return start, end
