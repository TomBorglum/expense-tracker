"""Guards the hand-maintained @source list in tailwind.css.

Tailwind only scans what tailwind.css names. A template that is not listed
compiles without error and without its classes, so the page renders unstyled and
nothing warns you. This test makes that a failure instead.
"""

import re
from pathlib import Path

import expense_tracker

PACKAGE_ROOT = Path(expense_tracker.__file__).parent
INPUT_CSS = PACKAGE_ROOT / "tailwind.css"
TEMPLATES = PACKAGE_ROOT / "templates"

# /* ... */ is the only comment form Tailwind's CSS accepts; strip it so prose
# mentioning the directive is never mistaken for one.
_COMMENTS = re.compile(r"/\*.*?\*/", re.DOTALL)
_SOURCE = re.compile(r'@source\s+"([^"]+)"')


def _declared_sources() -> set[Path]:
    css = _COMMENTS.sub("", INPUT_CSS.read_text())
    return {(INPUT_CSS.parent / m).resolve() for m in _SOURCE.findall(css)}


def test_every_template_is_declared_in_input_css() -> None:
    on_disk = {p.resolve() for p in TEMPLATES.rglob("*.html")}
    declared = _declared_sources()

    missing = sorted(p.relative_to(PACKAGE_ROOT) for p in on_disk - declared)
    assert not missing, (
        f"template(s) not listed in {INPUT_CSS.name}, so their classes would be "
        f"dropped from the compiled CSS: {missing}"
    )


def test_declared_sources_all_exist() -> None:
    stale = sorted(p for p in _declared_sources() if not p.exists())
    assert not stale, f"@source path(s) in {INPUT_CSS.name} no longer exist: {stale}"
