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


def test_expenses_in_one_month_become_one_total() -> None:
    totals = aggregate(
        [
            _expense("100.00", datetime.date(2026, 3, 4)),
            _expense("25.50", datetime.date(2026, 3, 9)),
        ],
        Period.MONTH,
        None,
    )
    assert totals == [TotalRecord(Decimal("125.50"), "DKK", "2026-03", None)]


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
    assert [total.period for total in totals] == ["2026-03", "2026-02"]


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
    assert totals == [
        TotalRecord(Decimal("100.00"), "DKK", "2026-03", None),
        TotalRecord(Decimal("10.00"), "EUR", "2026-03", None),
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
    assert totals == [TotalRecord(Decimal("125.50"), "DKK", "2026-03", None)]


def test_grouping_by_category_splits_the_same_month() -> None:
    totals = aggregate(
        [
            _expense("100.00", datetime.date(2026, 3, 4), category="Housing"),
            _expense("25.50", datetime.date(2026, 3, 9), category="Food"),
        ],
        Period.MONTH,
        Grouping.CATEGORY,
    )
    assert totals == [
        TotalRecord(Decimal("25.50"), "DKK", "2026-03", "Food"),
        TotalRecord(Decimal("100.00"), "DKK", "2026-03", "Housing"),
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


def test_rows_come_back_newest_period_first_then_category_then_currency() -> None:
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
        ("2026-03", "Food", "DKK"),
        ("2026-03", "Housing", "DKK"),
        ("2026-03", "Housing", "EUR"),
        ("2026-02", "Food", "DKK"),
    ]


def test_nothing_to_total_is_an_empty_list() -> None:
    assert aggregate([], Period.MONTH, Grouping.CATEGORY) == []


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
