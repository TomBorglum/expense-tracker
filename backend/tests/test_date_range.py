import datetime

import pytest

from expense_tracker.date_range import DateRangeError, parse_date_range

# Nothing here touches HTTP or a session: reading two query values is string work,
# which is the whole reason it lives in a module of its own.

_JANUARY = datetime.date(2026, 1, 2)
_FEBRUARY = datetime.date(2026, 2, 2)


def test_both_bounds_come_back_as_dates() -> None:
    assert parse_date_range("2026-01-02", "2026-02-02") == (_JANUARY, _FEBRUARY)


def test_an_absent_bound_stays_none() -> None:
    """None is what the repository reads as "no clause on this side"."""
    assert parse_date_range("2026-01-02", None) == (_JANUARY, None)
    assert parse_date_range(None, "2026-02-02") == (None, _FEBRUARY)


def test_neither_bound_given_is_the_whole_range() -> None:
    """The request that asks for no range at all, which is every request made before
    the parameters existed."""
    assert parse_date_range(None, None) == (None, None)


def test_the_bounds_may_be_the_same_day() -> None:
    """Both ends are inclusive, so one day is a range and not a refusal."""
    assert parse_date_range("2026-01-02", "2026-01-02") == (_JANUARY, _JANUARY)


@pytest.mark.parametrize(
    "value",
    # "2026-01-02\n" is why the pattern is anchored with \Z: $ would accept it.
    # 20260102 and 2026-W01-1 are forms date.fromisoformat takes and this API never
    # sends; 2026-02-30 has the shape but is not a day.
    [
        "",
        "yesterday",
        "20260102",
        "2026-W01-1",
        "02/01/2026",
        "2026-1-2",
        "2026-02-30",
        "2026-01-02\n",
    ],
)
def test_a_from_date_that_is_not_yyyy_mm_dd_is_refused(value: str) -> None:
    """An empty value is malformed rather than absent, matching ?currency=."""
    with pytest.raises(
        DateRangeError, match="from_date must be a date in YYYY-MM-DD form"
    ):
        _ = parse_date_range(value, None)


def test_a_to_date_that_is_not_yyyy_mm_dd_is_refused() -> None:
    """The message names the parameter, so a client knows which of the two to fix."""
    with pytest.raises(
        DateRangeError, match="to_date must be a date in YYYY-MM-DD form"
    ):
        _ = parse_date_range(None, "yesterday")


def test_a_range_that_ends_before_it_begins_is_refused() -> None:
    """Refused rather than answered with an empty list: the range is a mistake, and a
    200 would read as "no expenses then"."""
    with pytest.raises(DateRangeError, match="from_date must not be after to_date"):
        _ = parse_date_range("2026-02-02", "2026-01-02")


def test_a_malformed_bound_is_refused_before_the_two_are_compared() -> None:
    """Nothing to compare yet, so the message is about the value that cannot be read."""
    with pytest.raises(
        DateRangeError, match="from_date must be a date in YYYY-MM-DD form"
    ):
        _ = parse_date_range("yesterday", "2026-01-02")
