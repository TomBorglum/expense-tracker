"""Restating expenses in a requested currency."""

import re
from collections import defaultdict
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from .currency_repository import CurrencyRateRecord
from .expense_repository import ExpenseRecord

# \A and \Z rather than the loaders' ^ and $: $ also matches before a trailing newline,
# which a query parameter can carry and a TSV cell cannot.
_CURRENCY = re.compile(r"\A[A-Z]{3}\Z")

_CENTS = Decimal("0.01")


class ConversionError(Exception):
    """The expenses cannot be shown in the requested currency."""


def validate_currency_code(value: str) -> str:
    """The value unchanged, or ConversionError. A lowercase code is refused."""
    if _CURRENCY.match(value) is None:
        raise ConversionError("currency must be an ISO 4217 code")
    return value


def convert_expenses(
    expenses: Sequence[ExpenseRecord],
    rates: Sequence[CurrencyRateRecord],
    target: str,
) -> list[ExpenseRecord]:
    """Every expense restated in target, in the order given, or ConversionError."""
    index = _index_rates(rates)
    return [_convert(record, index, target) for record in expenses]


def _index_rates(
    rates: Sequence[CurrencyRateRecord],
) -> dict[tuple[str, str], list[Decimal]]:
    # A list per pair rather than one rate: schema.sql lets a pair repeat, and which
    # of the two applies is decided at lookup.
    index: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    for rate in rates:
        index[(rate.from_currency, rate.to_currency)].append(rate.exchange_rate)
    return index


def _convert(
    record: ExpenseRecord, index: dict[tuple[str, str], list[Decimal]], target: str
) -> ExpenseRecord:
    if record.currency == target:
        return record
    rate = _rate(index, record.currency, target)
    # ROUND_HALF_UP spelled out: Decimal rounds half to even by default.
    return record._replace(
        amount=(record.amount * rate).quantize(_CENTS, rounding=ROUND_HALF_UP),
        currency=target,
    )


def _rate(
    index: dict[tuple[str, str], list[Decimal]], source: str, target: str
) -> Decimal:
    # Only the direction the rates file states: no inverse, no pivot through a third
    # currency.
    found = index.get((source, target), [])
    if not found:
        raise ConversionError(f"no exchange rate from {source} to {target}")
    if len(found) > 1:
        raise ConversionError(f"more than one exchange rate from {source} to {target}")
    return found[0]
