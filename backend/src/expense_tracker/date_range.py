"""Reading the date range a request asks for."""

import datetime
import re

# The form GET /api/expenses sends dates back in, and the only one it takes. \A and \Z
# rather than ^ and $: $ also matches before a trailing newline, which a query
# parameter can carry.
_DATE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")


class DateRangeError(Exception):
    """The expenses cannot be read over the requested range of dates."""


def parse_date_range(
    from_date: str | None, to_date: str | None
) -> tuple[datetime.date | None, datetime.date | None]:
    """Both bounds as dates, or DateRangeError. An absent bound stays None."""
    start = _parse(from_date, "from_date")
    end = _parse(to_date, "to_date")
    if start is not None and end is not None and start > end:
        raise DateRangeError("from_date must not be after to_date")
    return start, end


def _parse(value: str | None, name: str) -> datetime.date | None:
    if value is None:
        return None
    if _DATE.match(value) is None:
        raise DateRangeError(f"{name} must be a date in YYYY-MM-DD form")
    try:
        # Matching the pattern says nothing about 2026-02-30 being a day.
        return datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise DateRangeError(f"{name} must be a date in YYYY-MM-DD form") from exc
