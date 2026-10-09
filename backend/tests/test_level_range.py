import pytest

from expense_tracker.level_range import (
    MAX_LEVEL,
    TOP_LEVEL,
    LevelRange,
    LevelRangeError,
    parse_level_range,
)

# Nothing here touches HTTP or a session: reading two query values is string work,
# which is the whole reason it lives in a module of its own, like date_range beside it.


def test_both_bounds_come_back_as_levels() -> None:
    assert parse_level_range("2", "4") == LevelRange(2, 4)


def test_neither_bound_given_is_the_top_level() -> None:
    """The request that names no level at all, which is every request made before the
    parameters existed, and what list_categories defaults to."""
    assert parse_level_range(None, None) == TOP_LEVEL
    assert LevelRange(1, 1) == TOP_LEVEL


def test_an_absent_to_level_is_the_from_level() -> None:
    """One generation: ?from_level=2 alone is exactly depth 2, not 1 through 2."""
    assert parse_level_range("2", None) == LevelRange(2, 2)


def test_a_to_level_alone_runs_from_the_top() -> None:
    """The other shorthand, and the one a picker asking for a whole tree sends."""
    assert parse_level_range(None, "3") == LevelRange(1, 3)


def test_the_bounds_may_be_the_same_level() -> None:
    """Both ends are inclusive, so one level is a range and not a refusal."""
    assert parse_level_range("3", "3") == LevelRange(3, 3)


def test_the_levels_are_walked_shallowest_first() -> None:
    """One SELECT per level is built from this, so the order is the clause order."""
    assert list(LevelRange(1, 3).levels) == [1, 2, 3]
    assert list(TOP_LEVEL.levels) == [1]


@pytest.mark.parametrize(
    "value",
    # int() takes "+2", " 2 " and "1_0", and this API sends none of them, which is why
    # the pattern runs first. "1\n" is why it is anchored with \Z rather than $.
    ["", "two", "1.0", "-1", "+2", " 2", "2 ", "1_0", "0x2", "1\n"],
)
def test_a_from_level_that_is_not_a_whole_number_is_refused(value: str) -> None:
    """An empty value is malformed rather than absent, matching ?currency=."""
    with pytest.raises(LevelRangeError, match="from_level must be a whole number"):
        _ = parse_level_range(value, None)


def test_a_to_level_that_is_not_a_whole_number_is_refused() -> None:
    """The message names the parameter, so a client knows which of the two to fix."""
    with pytest.raises(LevelRangeError, match="to_level must be a whole number"):
        _ = parse_level_range(None, "two")


def test_a_malformed_bound_is_refused_before_the_two_are_compared() -> None:
    """Nothing to compare yet, so the message is about the value that cannot be read."""
    with pytest.raises(LevelRangeError, match="from_level must be a whole number"):
        _ = parse_level_range("two", "1")


def test_a_level_below_one_is_refused() -> None:
    """There is no zeroth level: the outermost category is level 1."""
    with pytest.raises(LevelRangeError, match="from_level must be 1 or more"):
        _ = parse_level_range("0", None)


def test_a_level_past_the_cap_is_refused() -> None:
    """to_level multiplies the statement: list_categories unions one SELECT per level,
    so an unbounded value is an unbounded query."""
    with pytest.raises(
        LevelRangeError, match=f"to_level must not be more than {MAX_LEVEL}"
    ):
        _ = parse_level_range(None, str(MAX_LEVEL + 1))


def test_a_from_level_past_the_cap_names_from_level() -> None:
    """to_level defaults from from_level, so a cap checked in the wrong order would
    refuse ?from_level=11 against a parameter the client never sent."""
    with pytest.raises(
        LevelRangeError, match=f"from_level must not be more than {MAX_LEVEL}"
    ):
        _ = parse_level_range(str(MAX_LEVEL + 1), None)


def test_the_cap_itself_is_allowed() -> None:
    """The bound is inclusive, so the negative control is the cap and not one below."""
    assert parse_level_range(None, str(MAX_LEVEL)) == LevelRange(1, MAX_LEVEL)


def test_a_range_that_ends_before_it_begins_is_refused() -> None:
    """Refused rather than answered with an empty list, like an inverted date range:
    the range is a mistake, and a 200 would read as "no categories that deep"."""
    with pytest.raises(LevelRangeError, match="from_level must not be after to_level"):
        _ = parse_level_range("3", "2")


def test_the_type_refuses_an_inverted_range_however_it_is_built() -> None:
    """The check lives in __post_init__ rather than in the parser, which is what lets
    list_categories take the type and stop trusting whoever called it."""
    with pytest.raises(LevelRangeError, match="from_level must not be after to_level"):
        _ = LevelRange(3, 2)


def test_the_type_refuses_a_level_outside_the_bounds_however_it_is_built() -> None:
    with pytest.raises(LevelRangeError, match="from_level must be 1 or more"):
        _ = LevelRange(0, 1)
    with pytest.raises(
        LevelRangeError, match=f"to_level must not be more than {MAX_LEVEL}"
    ):
        _ = LevelRange(1, MAX_LEVEL + 1)


def test_a_range_is_frozen() -> None:
    """Immutable, so the validated bounds cannot be edited past the check."""
    levels = LevelRange(1, 2)
    with pytest.raises(AttributeError):
        levels.start = 2  # pyright: ignore[reportAttributeAccessIssue]  # the point of the test
