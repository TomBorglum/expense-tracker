import datetime
from decimal import Decimal

import pytest

from expense_tracker.aggregation import (
    AggregationError,
    Grouping,
    Period,
    TotalRecord,
    aggregate,
    parse_grouping,
    parse_period,
)
from expense_tracker.date_range import DateRange
from expense_tracker.expense_repository import ExpenseRecord

# Nothing here touches HTTP or a session: aggregation is arithmetic over records, the
# same reason conversion lives in a module of its own.


def _expense(
    amount: str,
    day: datetime.date,
    currency: str = "DKK",
    category: str = "Housing",
) -> ExpenseRecord:
    return ExpenseRecord(Decimal(amount), currency, day, category, "Rent")


def _spans(totals: list[TotalRecord]) -> list[tuple[str, str, str]]:
    """Each row as (period, from_date, to_date), which is what every row carries."""
    return [
        (total.period, total.from_date.isoformat(), total.to_date.isoformat())
        for total in totals
    ]


def test_expenses_in_one_month_become_one_total() -> None:
    totals = aggregate(
        [
            _expense("100.00", datetime.date(2026, 3, 4)),
            _expense("25.50", datetime.date(2026, 3, 9)),
        ],
        Period.MONTH,
        None,
    )
    assert totals == [
        TotalRecord(
            "2026-03",
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 31),
            Decimal("125.50"),
            "DKK",
            None,
        )
    ]


def test_a_month_boundary_splits_a_total() -> None:
    """The last day of February and the first of March are different periods."""
    totals = aggregate(
        [
            _expense("1.00", datetime.date(2026, 3, 1)),
            _expense("2.00", datetime.date(2026, 2, 28)),
        ],
        Period.MONTH,
        None,
    )
    assert [total.period for total in totals] == ["2026-02", "2026-03"]


def test_a_single_digit_month_is_zero_padded() -> None:
    """Fixed width is what makes ordering the strings order the periods."""
    totals = aggregate(
        [_expense("1.00", datetime.date(2026, 9, 30))], Period.MONTH, None
    )
    assert totals[0].period == "2026-09"


def test_two_currencies_in_one_month_stay_two_totals() -> None:
    """Adding DKK to EUR is the error conversion refuses; the key prevents it here."""
    totals = aggregate(
        [
            _expense("100.00", datetime.date(2026, 3, 4)),
            _expense("10.00", datetime.date(2026, 3, 9), currency="EUR"),
        ],
        Period.MONTH,
        None,
    )
    assert [(total.amount, total.currency) for total in totals] == [
        (Decimal("100.00"), "DKK"),
        (Decimal("10.00"), "EUR"),
    ]


def test_categories_are_summed_together_when_they_are_not_grouped_by() -> None:
    totals = aggregate(
        [
            _expense("100.00", datetime.date(2026, 3, 4), category="Housing"),
            _expense("25.50", datetime.date(2026, 3, 9), category="Food"),
        ],
        Period.MONTH,
        None,
    )
    assert [(total.amount, total.category) for total in totals] == [
        (Decimal("125.50"), None)
    ]


def test_grouping_by_category_splits_the_same_month() -> None:
    totals = aggregate(
        [
            _expense("100.00", datetime.date(2026, 3, 4), category="Housing"),
            _expense("25.50", datetime.date(2026, 3, 9), category="Food"),
        ],
        Period.MONTH,
        Grouping.CATEGORY,
    )
    assert [(total.amount, total.category) for total in totals] == [
        (Decimal("25.50"), "Food"),
        (Decimal("100.00"), "Housing"),
    ]


def test_a_total_carries_two_decimal_places() -> None:
    """str() of it is what reaches the wire, so a trailing zero has to survive."""
    totals = aggregate(
        [
            _expense("1250.00", datetime.date(2026, 3, 4)),
            _expense("0.50", datetime.date(2026, 3, 9)),
        ],
        Period.MONTH,
        None,
    )
    assert str(totals[0].amount) == "1250.50"


def test_cents_are_exact_over_many_rows() -> None:
    """Decimal addition, never float: 0.1 + 0.2 in binary is not 0.3."""
    totals = aggregate(
        [_expense("0.10", datetime.date(2026, 3, day)) for day in range(1, 11)],
        Period.MONTH,
        None,
    )
    assert totals[0].amount == Decimal("1.00")


def test_rows_come_back_oldest_period_first_then_category_then_currency() -> None:
    totals = aggregate(
        [
            _expense("1.00", datetime.date(2026, 2, 1), category="Food"),
            _expense("2.00", datetime.date(2026, 3, 1), "EUR", "Housing"),
            _expense("3.00", datetime.date(2026, 3, 1), "DKK", "Housing"),
            _expense("4.00", datetime.date(2026, 3, 1), "DKK", "Food"),
        ],
        Period.MONTH,
        Grouping.CATEGORY,
    )
    assert [(t.period, t.category, t.currency) for t in totals] == [
        ("2026-02", "Food", "DKK"),
        ("2026-03", "Food", "DKK"),
        ("2026-03", "Housing", "DKK"),
        ("2026-03", "Housing", "EUR"),
    ]


def test_nothing_to_total_is_an_empty_list() -> None:
    assert aggregate([], Period.MONTH, Grouping.CATEGORY) == []


def test_nothing_to_total_is_an_empty_list_whatever_the_range_was() -> None:
    """No expenses is no extent to walk, so there is no calendar to fill either."""
    assert (
        aggregate(
            [],
            Period.MONTH,
            None,
            DateRange(datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)),
        )
        == []
    )


def test_a_period_spans_its_whole_calendar_month() -> None:
    """Both ends inclusive, matching what ?from_date= and ?to_date= already mean."""
    totals = aggregate(
        [_expense("1.00", datetime.date(2026, 3, 15))], Period.MONTH, None
    )
    assert _spans(totals) == [("2026-03", "2026-03-01", "2026-03-31")]


def test_a_thirty_day_month_ends_on_the_thirtieth() -> None:
    totals = aggregate(
        [_expense("1.00", datetime.date(2026, 4, 15))], Period.MONTH, None
    )
    assert _spans(totals) == [("2026-04", "2026-04-01", "2026-04-30")]


def test_a_leap_february_ends_on_the_twenty_ninth() -> None:
    """The last day is read from the calendar, not from a table of 31s."""
    totals = aggregate(
        [_expense("1.00", datetime.date(2028, 2, 10))], Period.MONTH, None
    )
    assert _spans(totals) == [("2028-02", "2028-02-01", "2028-02-29")]


def test_a_month_nobody_spent_in_is_still_a_row() -> None:
    """The gap carries its span and nothing else.

    Not a zero, which would say the month's expenses cancelled out.
    """
    totals = aggregate(
        [
            _expense("300.00", datetime.date(2026, 3, 20)),
            _expense("100.00", datetime.date(2026, 1, 5)),
        ],
        Period.MONTH,
        Grouping.CATEGORY,
    )
    assert totals[1] == TotalRecord(
        "2026-02",
        datetime.date(2026, 2, 1),
        datetime.date(2026, 2, 28),
        None,
        None,
        None,
    )


def test_a_gap_of_several_months_is_filled_contiguously() -> None:
    totals = aggregate(
        [
            _expense("1.00", datetime.date(2026, 5, 2)),
            _expense("1.00", datetime.date(2025, 12, 30)),
        ],
        Period.MONTH,
        None,
    )
    assert [total.period for total in totals] == [
        "2025-12",
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
    ]


def test_a_bound_inside_a_period_narrows_it() -> None:
    totals = aggregate(
        [_expense("1.00", datetime.date(2026, 3, 20))],
        Period.MONTH,
        None,
        DateRange(datetime.date(2026, 3, 12), datetime.date(2026, 3, 14)),
    )
    assert _spans(totals) == [("2026-03", "2026-03-12", "2026-03-14")]


def test_a_bound_outside_a_period_leaves_it_whole() -> None:
    """January is asked for from the 12th; February and March are not narrowed by it."""
    totals = aggregate(
        [
            _expense("1.00", datetime.date(2026, 3, 20)),
            _expense("1.00", datetime.date(2026, 1, 20)),
        ],
        Period.MONTH,
        None,
        DateRange(datetime.date(2026, 1, 12), datetime.date(2026, 3, 14)),
    )
    assert _spans(totals) == [
        ("2026-01", "2026-01-12", "2026-01-31"),
        ("2026-02", "2026-02-01", "2026-02-28"),
        ("2026-03", "2026-03-01", "2026-03-14"),
    ]


def test_a_bound_on_a_period_edge_narrows_nothing() -> None:
    """The 1st and the 31st are the span already, so neither test fires."""
    totals = aggregate(
        [_expense("1.00", datetime.date(2026, 3, 20))],
        Period.MONTH,
        None,
        DateRange(datetime.date(2026, 3, 1), datetime.date(2026, 3, 31)),
    )
    assert _spans(totals) == [("2026-03", "2026-03-01", "2026-03-31")]


def test_a_range_that_cannot_touch_a_period_leaves_it_whole() -> None:
    """A caller that filtered nothing cannot be handed an inverted span.

    The repository filters, so a real one never returns a March row for a January
    range - but the fake in conftest.py does, and clamping to a bound that falls
    outside the period would end it before it began.
    """
    totals = aggregate(
        [_expense("1.00", datetime.date(2026, 3, 20))],
        Period.MONTH,
        None,
        DateRange(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31)),
    )
    assert _spans(totals) == [("2026-03", "2026-03-01", "2026-03-31")]


def test_an_unbounded_range_clamps_nothing() -> None:
    totals = aggregate(
        [_expense("1.00", datetime.date(2026, 3, 20))],
        Period.MONTH,
        None,
        DateRange(None, None),
    )
    assert _spans(totals) == [("2026-03", "2026-03-01", "2026-03-31")]


def test_one_open_bound_clamps_only_the_other_end() -> None:
    totals = aggregate(
        [_expense("1.00", datetime.date(2026, 3, 20))],
        Period.MONTH,
        None,
        DateRange(datetime.date(2026, 3, 9), None),
    )
    assert _spans(totals) == [("2026-03", "2026-03-09", "2026-03-31")]


def test_an_absent_period_is_refused_rather_than_defaulted() -> None:
    with pytest.raises(AggregationError, match="period is required"):
        _ = parse_period(None)


def test_a_period_that_is_not_a_known_grain_is_refused() -> None:
    """year is the next grain to arrive, and refuses loudly until it does."""
    with pytest.raises(AggregationError, match="unknown period: year"):
        _ = parse_period("year")


def test_an_empty_period_is_a_value_and_not_an_absence() -> None:
    with pytest.raises(AggregationError, match="unknown period: "):
        _ = parse_period("")


def test_the_month_grain_is_read_from_its_own_spelling() -> None:
    assert parse_period("month") is Period.MONTH


def test_an_absent_grouping_is_no_grouping() -> None:
    assert parse_grouping(None) is None


def test_a_grouping_that_is_not_a_known_dimension_is_refused() -> None:
    with pytest.raises(AggregationError, match="unknown group_by: currency"):
        _ = parse_grouping("currency")


def test_a_list_of_groupings_is_refused_rather_than_split() -> None:
    """One dimension today; accepting a list later widens nothing a client relies on."""
    with pytest.raises(AggregationError, match="unknown group_by: category,currency"):
        _ = parse_grouping("category,currency")


def test_the_category_grouping_is_read_from_its_own_spelling() -> None:
    assert parse_grouping("category") is Grouping.CATEGORY
