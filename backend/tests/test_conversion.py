import datetime
from decimal import Decimal

import pytest

from expense_tracker.conversion import (
    ConversionError,
    convert_expenses,
    validate_currency_code,
)
from expense_tracker.currency_repository import CurrencyRateRecord
from expense_tracker.expense_repository import ExpenseRecord

# Nothing here touches HTTP or a session: conversion is arithmetic over records, which
# is the whole reason it lives in a module of its own.

_DKK_TO_EUR = CurrencyRateRecord("DKK", "EUR", Decimal("0.134048"))
_DKK_TO_GBP = CurrencyRateRecord("DKK", "GBP", Decimal("0.114900"))


def _expense(amount: str, currency: str = "DKK") -> ExpenseRecord:
    return ExpenseRecord(
        Decimal(amount), currency, datetime.date(2026, 1, 2), "Car", "Fuel"
    )


def test_an_amount_is_multiplied_by_the_rate_for_its_pair() -> None:
    converted = convert_expenses([_expense("775.37")], [_DKK_TO_EUR], "EUR")
    # 775.37 * 0.134048 is 103.93679776 exactly, which rounds to 103.94.
    assert converted == [_expense("103.94", "EUR")]


def test_the_converted_amount_carries_two_decimal_places() -> None:
    """str() of it is what reaches the wire, so a trailing zero has to survive."""
    converted = convert_expenses([_expense("1250.00")], [_DKK_TO_EUR], "EUR")
    assert str(converted[0].amount) == "167.56"


def test_a_half_cent_rounds_up_rather_than_to_even() -> None:
    """Decimal rounds half to even by default, which would give 2.02 here."""
    half = CurrencyRateRecord("DKK", "EUR", Decimal("0.500000"))
    assert convert_expenses([_expense("4.05")], [half], "EUR") == [
        _expense("2.03", "EUR")
    ]


def test_a_negative_amount_keeps_its_sign() -> None:
    """The loader accepts a negative amount, so a refund converts like anything else."""
    converted = convert_expenses([_expense("-100.00")], [_DKK_TO_EUR], "EUR")
    assert converted == [_expense("-13.40", "EUR")]


def test_an_expense_already_in_the_target_currency_is_untouched() -> None:
    """The empty rate list is the assertion: no lookup happened, so the rates file
    needs no DKK -> DKK row."""
    assert convert_expenses([_expense("775.37")], [], "DKK") == [_expense("775.37")]


def test_the_given_order_is_preserved() -> None:
    given = [_expense("1250.00"), _expense("775.37"), _expense("89.50")]
    converted = convert_expenses(given, [_DKK_TO_EUR], "EUR")
    assert [record.amount for record in converted] == [
        Decimal("167.56"),
        Decimal("103.94"),
        Decimal("12.00"),
    ]


def test_no_expenses_needs_no_rates() -> None:
    """An empty expense table is a legitimate state, and stays one under ?currency."""
    assert convert_expenses([], [], "EUR") == []


def test_a_missing_pair_is_refused() -> None:
    expenses = [_expense("775.37")]
    with pytest.raises(ConversionError, match="no exchange rate from DKK to CHF"):
        _ = convert_expenses(expenses, [_DKK_TO_EUR], "CHF")


def test_a_rate_is_not_inverted() -> None:
    """EUR -> DKK is loaded and DKK -> EUR is not, so dividing would answer this."""
    reverse = CurrencyRateRecord("EUR", "DKK", Decimal("7.460000"))
    expenses = [_expense("775.37")]
    with pytest.raises(ConversionError, match="no exchange rate from DKK to EUR"):
        _ = convert_expenses(expenses, [reverse], "EUR")


def test_a_missing_pair_is_not_composed_through_a_third_currency() -> None:
    """DKK -> GBP and DKK -> EUR are both loaded, which is enough to derive GBP -> EUR.
    It is not derived: a composed rate is one the rates file never published."""
    expenses = [_expense("12.00", "GBP")]
    with pytest.raises(ConversionError, match="no exchange rate from GBP to EUR"):
        _ = convert_expenses(expenses, [_DKK_TO_GBP, _DKK_TO_EUR], "EUR")


def test_one_unconvertible_expense_refuses_the_whole_list() -> None:
    """Not a partly converted list: a table mixing currencies reads as a total nobody
    can add up."""
    expenses = [_expense("775.37"), _expense("12.00", "GBP")]
    with pytest.raises(ConversionError, match="no exchange rate from GBP to EUR"):
        _ = convert_expenses(expenses, [_DKK_TO_EUR], "EUR")


def test_a_pair_loaded_twice_is_refused_rather_than_picked_between() -> None:
    """schema.sql lets a pair repeat, so two rows for one pair is data the API can
    receive. Neither of them wins."""
    other = CurrencyRateRecord("DKK", "EUR", Decimal("0.140000"))
    expenses = [_expense("775.37")]
    with pytest.raises(
        ConversionError, match="more than one exchange rate from DKK to EUR"
    ):
        _ = convert_expenses(expenses, [_DKK_TO_EUR, other], "EUR")


def test_a_duplicate_of_an_unused_pair_converts_fine() -> None:
    """The ambiguity is decided at lookup, so a duplicate nobody asks about refuses
    nothing."""
    other = CurrencyRateRecord("DKK", "GBP", Decimal("0.120000"))
    converted = convert_expenses(
        [_expense("775.37")], [_DKK_TO_EUR, _DKK_TO_GBP, other], "EUR"
    )
    assert converted == [_expense("103.94", "EUR")]


def test_no_rates_at_all_refuses_a_conversion() -> None:
    """An empty currency_rate table is a 200 on its own endpoint, but it cannot answer
    a conversion."""
    expenses = [_expense("775.37")]
    with pytest.raises(ConversionError, match="no exchange rate from DKK to EUR"):
        _ = convert_expenses(expenses, [], "EUR")


def test_a_well_formed_code_is_returned_unchanged() -> None:
    assert validate_currency_code("EUR") == "EUR"


@pytest.mark.parametrize(
    "value",
    # "EUR\n" is why the pattern is anchored with \Z: $ would accept it.
    ["eur", "euro", "EU", "E1R", "", " EUR", "EUR ", "EUR\n"],
)
def test_a_code_that_is_not_iso_4217_is_refused(value: str) -> None:
    """Lowercase is refused rather than uppercased, matching both loaders."""
    with pytest.raises(ConversionError, match="currency must be an ISO 4217 code"):
        _ = validate_currency_code(value)
