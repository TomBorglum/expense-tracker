"""Summing expenses over the period a request asks for."""

import datetime
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum
from typing import NamedTuple

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
    """One summed amount, and the key it was summed under."""

    amount: Decimal
    currency: str
    period: str
    # None when the request did not group by category.
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
    expenses: Sequence[ExpenseRecord], period: Period, grouping: Grouping | None
) -> list[TotalRecord]:
    """One total per key, newest period first, then category, then currency."""
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
    totals = [
        TotalRecord(amount, currency, period_key, category)
        for (period_key, currency, category), amount in sums.items()
    ]
    # Two passes rather than one key: reverse=True on a tuple would reverse the
    # category and currency components too. sort is stable, so the second wins.
    totals.sort(key=lambda total: (total.category or "", total.currency))
    totals.sort(key=lambda total: total.period, reverse=True)
    return totals


def _period_key(day: datetime.date, period: Period) -> str:
    # Fixed width, so ordering the strings orders the periods.
    match period:
        case Period.MONTH:
            return f"{day.year:04d}-{day.month:02d}"
