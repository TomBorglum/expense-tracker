import pytest

from expense_tracker.category_filter import (
    EVERYTHING,
    SLUG_PATH,
    CategoryFilterError,
    CategorySelection,
    CategorySlugError,
    parse_category_selection,
    path_name,
    path_parent,
    slug_level,
    split_path,
    strip_path,
)

# Nothing here touches HTTP or a session: reading query values is string work, which
# is the whole reason it lives in a module of its own.

_FOOD = CategorySelection(
    selected=frozenset({"Food"}), deselected=frozenset(), default=False
)


def test_one_value_selects_that_name_and_nothing_else() -> None:
    """The root goes with it: a request naming a category means that one, which is
    what ?category=Food meant before there was a root to flip."""
    assert parse_category_selection(["Food"], None, None) == _FOOD


def test_two_values_select_both() -> None:
    """Either matches: both are selected flips over a root that is not."""
    assert parse_category_selection(["Food", "Housing"], None, None) == (
        CategorySelection(
            selected=frozenset({"Food", "Housing"}),
            deselected=frozenset(),
            default=False,
        )
    )


def test_no_values_at_all_select_every_category() -> None:
    """EVERYTHING is what the repository reads as "no clause", and what a request made
    before any of the three parameters existed asks for."""
    assert parse_category_selection(None, None, None) == EVERYTHING
    assert EVERYTHING.everything()


def test_a_repeated_value_collapses() -> None:
    assert parse_category_selection(["Food", "Food"], None, None) == _FOOD


def test_a_value_is_stripped_the_way_the_loader_strips_a_field() -> None:
    """A stored category never carries surrounding whitespace, because the loader
    strips every field, so a query value is met on the same terms."""
    assert parse_category_selection([" Food "], None, None) == _FOOD
    assert parse_category_selection([" Food", "Food"], None, None) == _FOOD


def test_a_deselected_value_is_stripped_too() -> None:
    """The same strip on the other key: one parser reads both."""
    assert parse_category_selection(None, [" Food "], None) == CategorySelection(
        selected=frozenset(), deselected=frozenset({"Food"}), default=True
    )


def test_the_case_is_kept() -> None:
    """Stripped and nothing else: the loader stores the case it read."""
    assert parse_category_selection(["food"], None, None) == CategorySelection(
        selected=frozenset({"food"}), deselected=frozenset(), default=False
    )


@pytest.mark.parametrize("values", [[""], [" "], ["Food", ""]])
def test_a_blank_value_is_refused(values: list[str]) -> None:
    """Blank after the strip, as the loader refuses one in a file. An empty value is
    malformed rather than absent, matching ?from_date=."""
    with pytest.raises(CategoryFilterError, match="category must not be blank"):
        _ = parse_category_selection(values, None, None)
    with pytest.raises(CategoryFilterError, match="category must not be blank"):
        _ = parse_category_selection(None, values, None)


def test_a_selection_naming_nothing_selects_everything() -> None:
    """An empty list is the absent key, not "match nothing": FastAPI hands None for an
    absent one, so neither spelling can mean the empty selection - the flag does."""
    assert parse_category_selection([], [], None) == EVERYTHING


def test_deselecting_a_path_leaves_the_rest_selected() -> None:
    """The case the whole feature exists for: one value, and everything else stays."""
    selection = parse_category_selection(None, ["Food:Snacks"], None)
    assert selection == CategorySelection(
        selected=frozenset(), deselected=frozenset({"Food:Snacks"}), default=True
    )
    assert not selection.everything()


def test_the_flag_deselects_the_root() -> None:
    """The empty selection, which is one parameter rather than one per root - so a
    category imported later is deselected too."""
    selection = parse_category_selection(None, None, "none")
    assert selection == CategorySelection(
        selected=frozenset(), deselected=frozenset(), default=False
    )
    assert not selection.everything()
    assert selection.flips() == ()


def test_the_flag_agrees_with_what_a_selected_path_already_implies() -> None:
    """Sent or not, a request naming a path reads the same, so the frontend needs the
    flag for the empty selection alone."""
    assert parse_category_selection(["Food"], None, "none") == _FOOD


@pytest.mark.parametrize("value", ["every", "", "None", "root"])
def test_the_flag_refuses_any_other_value(value: str) -> None:
    """Refused rather than read as the default, the way parse_grouping refuses a
    group_by it does not name."""
    with pytest.raises(CategoryFilterError, match="unknown category_default"):
        _ = parse_category_selection(None, None, value)


def test_the_flag_keeps_the_root_selected_beside_a_selected_path() -> None:
    """The state the flag's other value exists for: everything but one subtree, with a
    branch of that subtree kept. Without "all" the selected path would be read as the
    whole request and the deselected root would say nothing."""
    assert parse_category_selection(
        ["Settlement:Alice"], ["Settlement"], "all"
    ) == CategorySelection(
        selected=frozenset({"Settlement:Alice"}),
        deselected=frozenset({"Settlement"}),
        default=True,
    )


def test_a_path_both_selected_and_deselected_is_refused() -> None:
    """The one pair no reading resolves: two flips of the same length over the same
    path, so neither is the longer one."""
    with pytest.raises(
        CategoryFilterError, match="category both selected and deselected: Food"
    ):
        _ = parse_category_selection(["Food"], ["Food"], None)


def test_flips_are_ordered_longest_path_first() -> None:
    """The rule itself: read in this order the first match over a row is the longest
    path above it, which is what makes a child's sign beat its parent's. The path
    breaks a tie, so the order - and the SQL built from it - is deterministic."""
    selection = parse_category_selection(["Food", "A:B"], ["Food:Snacks", "Z"], None)
    assert selection.flips() == (
        ("A:B", True),
        ("Food:Snacks", False),
        ("Food", True),
        ("Z", False),
    )


def test_a_flip_is_measured_in_levels_not_characters() -> None:
    """A long name at depth 1 is still above a short path at depth 2."""
    selection = parse_category_selection(["Travel:Taxi"], ["Entertainment"], None)
    assert selection.flips() == (("Travel:Taxi", True), ("Entertainment", False))


def test_selecting_inside_a_selected_root_is_still_every_category() -> None:
    """Nothing deselected is what makes it everything, so the repository adds no
    clause for a flip that narrows nothing."""
    assert CategorySelection(
        selected=frozenset({"Food"}), deselected=frozenset(), default=True
    ).everything()


def test_the_type_refuses_a_blank_however_it_is_built() -> None:
    """The check lives in __post_init__ rather than in the parser, which is what lets
    list_expenses take the type and stop trusting whoever called it."""
    # Built outside the block, so the only call that can raise inside it is the one
    # being tested.
    blank = frozenset({" "})
    nothing: frozenset[str] = frozenset()
    with pytest.raises(CategoryFilterError, match="category must not be blank"):
        _ = CategorySelection(selected=blank, deselected=nothing, default=False)
    with pytest.raises(CategoryFilterError, match="category must not be blank"):
        _ = CategorySelection(selected=nothing, deselected=blank, default=True)


def test_the_type_refuses_a_contradiction_however_it_is_built() -> None:
    """The other half of the same guarantee, for the same reason."""
    both = frozenset({"Food"})
    with pytest.raises(CategoryFilterError, match="both selected and deselected"):
        _ = CategorySelection(selected=both, deselected=both, default=False)


def test_a_selection_is_frozen() -> None:
    """Immutable, so the validated paths cannot be edited past the check."""
    selection = parse_category_selection(["Food"], None, None)
    with pytest.raises(AttributeError):
        selection.selected = frozenset({""})  # pyright: ignore[reportAttributeAccessIssue]  # the point of the test


def test_a_name_with_no_separator_is_one_level() -> None:
    """The identity every backward-compatibility claim rests on: for a category that
    carries no path, each helper hands back the name itself."""
    assert split_path("Groceries") == ("Groceries",)
    assert path_name("Groceries") == "Groceries"
    assert path_parent("Groceries") is None


def test_a_path_is_taken_apart_at_every_separator() -> None:
    assert split_path("Settlement:Alice:Spain") == ("Settlement", "Alice", "Spain")
    assert path_name("Settlement:Alice:Spain") == "Spain"
    assert path_parent("Settlement:Alice:Spain") == "Settlement:Alice"


def test_a_root_has_no_parent_rather_than_an_empty_one() -> None:
    """None, so the payload drops the key altogether: an empty string would say the
    parent is a category whose name is nothing."""
    assert path_parent("Settlement") is None
    assert path_parent("Settlement:Alice") == "Settlement"


def test_every_level_is_stripped_not_just_the_whole_value() -> None:
    """A level keeping its inner spaces would be a node that renders identically to
    the real one - HTML collapses whitespace - and never merges with it."""
    assert strip_path(" Settlement : Alice ") == "Settlement:Alice"
    assert strip_path("Groceries") == "Groceries"


def test_a_level_of_a_selected_value_is_stripped_too() -> None:
    """The loader strips each level, so a query value meets a stored one on the same
    terms however the path was typed."""
    assert parse_category_selection(["Settlement : Alice"], None, None) == (
        CategorySelection(
            selected=frozenset({"Settlement:Alice"}),
            deselected=frozenset(),
            default=False,
        )
    )


@pytest.mark.parametrize("value", ["Food:", ":Food", "Food::Drink"])
def test_a_value_the_column_could_never_hold_is_not_refused(value: str) -> None:
    """Only blank and a contradiction are refused here. A malformed path is an
    unmatchable value, which is what an unknown category already is - and the
    selection is checked against the known list on neither side. `Food:` compiles to
    `= 'Food:' OR LIKE 'Food::%'`, so it matches nothing rather than acting as an
    undocumented "strictly below"."""
    assert parse_category_selection([value], None, None) == CategorySelection(
        selected=frozenset({value}), deselected=frozenset(), default=False
    )


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        # The case the whole feature exists for: a space and a plus in one name, both
        # of which a query string would otherwise percent-encode.
        ("Jalsa+pool", "jalsa-pool"),
        ("Going Out", "going-out"),
        # Already a slug, so it is left as it reads.
        ("groceries", "groceries"),
        ("Car", "car"),
        # A run of anything unusable collapses to one dash rather than one each.
        ("Jalsa & pool", "jalsa-pool"),
        ("Going  Out", "going-out"),
        # Trimmed at both ends, so no slug begins or ends with a dash.
        ("%Fees%", "fees"),
        ("- Car -", "car"),
        # A dash the name itself carries is kept, which is what makes "Going-Out"
        # collide with "Going Out" rather than differ from it.
        ("Going-Out", "going-out"),
        # Digits are usable, and only the % goes.
        ("100%", "100"),
        ("1005", "1005"),
    ],
)
def test_a_name_slugs_to_lower_kebab_case(name: str, slug: str) -> None:
    assert slug_level(name) == slug


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        # ae-ligature, o-slash and a-ring, spelled out rather than dropped. Written as
        # escapes because committed source is ASCII.
        ("Sm\u00f8rrebr\u00f8d", "smoerrebroed"),
        ("\u00c6blekage", "aeblekage"),
        ("Gl\u00f8gg", "gloegg"),
        ("\u00c5rhus", "aarhus"),
        # Not in the table, so NFKD splits the letter from its mark and the mark goes.
        ("Caf\u00e9", "cafe"),
        ("Z\u00fcrich", "zurich"),
        # Reached by neither, so it collapses like any other unusable run. Sharp s is
        # the case str.isalnum() would have let through into a URL.
        ("Stra\u00dfe", "stra-e"),
    ],
)
def test_a_danish_letter_is_transliterated_rather_than_dropped(
    name: str, slug: str
) -> None:
    assert slug_level(name) == slug


@pytest.mark.parametrize("name", ["%", "&&&", "---", " ", "\u2014"])
def test_a_level_with_nothing_to_slug_is_refused(name: str) -> None:
    """There is nothing to fall back on that would still name this category and no
    other, so the loader stops rather than inventing one. An em-dash is the last case:
    usable to a reader, and not a character a URL should carry raw."""
    with pytest.raises(CategorySlugError, match="has no slug"):
        _ = slug_level(name)


@pytest.mark.parametrize(
    "name",
    ["Jalsa+pool", "Going Out", "Caf\u00e9", "100%", "- Car -", "Sm\u00f8rrebr\u00f8d"],
)
def test_every_slug_matches_the_shape_the_column_checks(name: str) -> None:
    """SLUG_PATH is the Python half of schema.sql's CHECK on category.slug, so a slug
    this builds can never be one the column would refuse."""
    assert SLUG_PATH.match(slug_level(name)) is not None
