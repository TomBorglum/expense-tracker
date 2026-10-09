"""The levels of the category tree a request asks for, read off a query string."""

import re
from dataclasses import dataclass

# \A and \Z rather than ^ and $ for the reason date_range gives. The pattern rather than
# int() alone: int() also takes "+2", " 2 " and "1_0", which this API never sends.
_LEVEL = re.compile(r"\A\d+\Z")

# The deepest level a request may ask for. list_categories unions one SELECT per level,
# so an unbounded to_level is an unbounded statement; no real tree goes near this.
MAX_LEVEL = 10


class LevelRangeError(Exception):
    """The categories cannot be listed over the requested range of levels."""


@dataclass(frozen=True)
class LevelRange:
    """Two inclusive depths within 1..MAX_LEVEL that cannot end before they begin."""

    start: int
    end: int

    def __post_init__(self) -> None:
        # Every construction, not only the parsed one: this is what lets a repository
        # take the type and stop trusting its caller to have checked. Bounds first and
        # in order, so ?from_level=20 is refused against the name that was sent rather
        # than against the to_level it defaulted into.
        for level, name in ((self.start, "from_level"), (self.end, "to_level")):
            if level < 1:
                raise LevelRangeError(f"{name} must be 1 or more")
            if level > MAX_LEVEL:
                raise LevelRangeError(f"{name} must not be more than {MAX_LEVEL}")
        if self.start > self.end:
            raise LevelRangeError("from_level must not be after to_level")

    @property
    def levels(self) -> range:
        """Every level in the range, shallowest first."""
        return range(self.start, self.end + 1)


# What list_categories reads as the depth-1 names the endpoint sent before the
# parameters existed.
TOP_LEVEL = LevelRange(1, 1)


def parse_level_range(from_level: str | None, to_level: str | None) -> LevelRange:
    """Both bounds read as levels, or LevelRangeError. An absent from_level is the top
    level, and an absent to_level is whatever from_level is."""
    start = 1 if from_level is None else _parse(from_level, "from_level")
    # Defaulted from start, which is also why start is read first: ?from_level=2 alone
    # is exactly level 2, and a cap it breaks is reported against the name that was
    # actually sent.
    end = start if to_level is None else _parse(to_level, "to_level")
    return LevelRange(start, end)


def _parse(value: str, name: str) -> int:
    if _LEVEL.match(value) is None:
        raise LevelRangeError(f"{name} must be a whole number")
    return int(value)
