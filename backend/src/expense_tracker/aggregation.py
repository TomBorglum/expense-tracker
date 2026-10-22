"""Summing expenses over the period a request asks for."""

import calendar
import datetime
from collections import defaultdict
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import NamedTuple

from .date_range import DateRange
from .expense_repository import ExpenseRecord

_CENTS = Decimal("0.01")


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
    # The record's own path, or None when the request did not group at all.
    category: str | None
    # The mean of this currency's totals over the periods so far, or None on a grouped
    # row.
    running_average: Decimal | None


class RangeAverage(NamedTuple):
    """One currency's mean period total over the whole calendar the rows span."""

    currency: str
    average: Decimal


class Aggregation(NamedTuple):
    """The rows a request answers with, and the range figures beside them."""

    totals: list[TotalRecord]
    # One per currency, sorted, and empty only when there are no expenses at all.
    averages: list[RangeAverage]


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


def _group(category: str, grouping: Grouping | None) -> str | None:
    """The path a record is summed under, or None when nothing was grouped by."""
    if grouping is not Grouping.CATEGORY:
        return None
    return category


def aggregate(
    expenses: Sequence[ExpenseRecord],
    period: Period,
    grouping: Grouping | None,
    # Not defaulted, for the reason grouping is not: it changes what a row means rather
    # than only which rows there are. UNBOUNDED is what a caller asking for no range
    # passes.
    dates: DateRange,
) -> Aggregation:
    """Every period from the oldest expense to the newest, and the range means."""
    sums: defaultdict[tuple[str, str, str | None], Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    for record in expenses:
        # currency is in the key whatever was asked for: two currencies added together
        # are a number that means nothing.
        key = (
            _period_key(record.expense_date, period),
            record.currency,
            _group(record.category, grouping),
        )
        sums[key] += record.amount
    grouped: defaultdict[str, list[tuple[str, str | None, Decimal]]] = defaultdict(list)
    for (period_key, currency, category), amount in sums.items():
        grouped[period_key].append((currency, category, amount))
    totals: list[TotalRecord] = []
    # Carried across the walk, so a period's average covers every period before it, and
    # holding each currency's whole-calendar total once the walk has ended.
    running: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    period_keys = _period_keys(expenses, period)
    # The walk supplies the period order, so only the rows within one are sorted here.
    for periods, period_key in enumerate(period_keys, start=1):
        start, end = _clamp(_period_bounds(period_key, period), dates)
        rows = sorted(grouped[period_key], key=lambda row: (row[1] or "", row[0]))
        for currency, _category, amount in rows:
            running[currency] += amount
        # Rebuilt each period, the divisor being how many have passed: an average moves
        # even where the total behind it does not. Empty when the request grouped, which
        # is what leaves a grouped row and a grouped gap row carrying none.
        averages: dict[str, Decimal] = (
            {}
            if grouping is not None
            else {
                currency: _mean(total, periods) for currency, total in running.items()
            }
        )
        if not rows:
            totals.extend(_gap(period_key, start, end, averages))
        totals.extend(
            TotalRecord(
                period_key,
                start,
                end,
                amount,
                currency,
                category,
                averages.get(currency),
            )
            for currency, category, amount in rows
        )
    # One per currency, over the whole calendar rather than that currency's own series.
    return Aggregation(
        totals,
        [
            RangeAverage(currency, _mean(total, len(period_keys)))
            for currency, total in sorted(running.items())
        ],
    )


def _gap(
    period_key: str,
    start: datetime.date,
    end: datetime.date,
    averages: dict[str, Decimal],
) -> list[TotalRecord]:
    """What a period nobody spent in sends: one row per average, or one bare row."""
    # A period nobody spent in is still a row, carrying the span: absent says "none
    # recorded" where 0.00 would say "these cancelled out", which a month of credits can
    # genuinely do. Ungrouped it names the average of every currency seen so far, which
    # is the one figure an empty period does have.
    if not averages:
        return [TotalRecord(period_key, start, end, None, None, None, None)]
    return [
        TotalRecord(period_key, start, end, None, currency, None, average)
        for currency, average in sorted(averages.items())
    ]


def _mean(total: Decimal, periods: int) -> Decimal:
    """The total spread over the periods it covers, at two places."""
    # ROUND_HALF_UP spelled out: Decimal rounds half to even by default.
    mean = (total / periods).quantize(_CENTS, rounding=ROUND_HALF_UP)
    # A cumulative credit too small to show at this scale quantizes to -0.00, which a
    # sum cannot reach and a division can.
    if mean == 0:
        mean = abs(mean)
    return mean


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
