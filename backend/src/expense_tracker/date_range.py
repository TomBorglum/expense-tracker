"""The range of dates a request asks for, and reading one off a query string."""

import datetime
import re
from dataclasses import dataclass

# The form GET /api/expenses sends dates back in, and the only one it takes. \A and \Z
# rather than ^ and $: $ also matches before a trailing newline, which a query
# parameter can carry.
_DATE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")


class DateRangeError(Exception):
    """The expenses cannot be read over the requested range of dates."""


@dataclass(frozen=True)
class DateRange:
    """Two inclusive bounds, either of them open, that cannot end before they begin."""

    start: datetime.date | None
    end: datetime.date | None

    def __post_init__(self) -> None:
        # Every construction, not only the parsed one: this is what lets a repository
        # take the type and stop trusting its caller to have checked.
        if self.start is not None and self.end is not None and self.start > self.end:
            raise DateRangeError("from_date must not be after to_date")


# What list_expenses reads as every expense there is.
UNBOUNDED = DateRange(None, None)


def parse_date_range(from_date: str | None, to_date: str | None) -> DateRange:
    """Both bounds read as dates, or DateRangeError. An absent bound stays open."""
    # Both parsed before either is compared, so a value that cannot be read is refused
    # as itself rather than as half of a range.
    return DateRange(_parse(from_date, "from_date"), _parse(to_date, "to_date"))


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
