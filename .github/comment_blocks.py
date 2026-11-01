"""Fail when a workflow carries a comment block longer than MAX_LINES."""

import pathlib
import sys

MAX_LINES = 8
WORKFLOWS = pathlib.Path(__file__).parent / "workflows"


def longest_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """Every run of comment lines, as (start line number, length), longest first."""
    blocks: list[tuple[int, int]] = []
    start = length = 0
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            if length == 0:
                start = number
            length += 1
        elif stripped:
            # A blank line does not reset the count, so padding a long block with
            # bare `#` or empty lines cannot split it into two passing halves.
            if length:
                blocks.append((start, length))
            start = length = 0
    if length:
        blocks.append((start, length))
    return sorted(blocks, key=lambda block: -block[1])


def main() -> int:
    failed = False
    for path in sorted(WORKFLOWS.glob("*.yml")):
        blocks = longest_blocks(path.read_text().splitlines())
        over = [block for block in blocks if block[1] > MAX_LINES]
        for start, length in over:
            print(
                f"{path.as_posix()}:{start}: comment block of {length} lines "
                f"exceeds the {MAX_LINES}-line cap"
            )
            failed = True
        if not over:
            longest = blocks[0][1] if blocks else 0
            print(f"{path.as_posix()}: longest comment block {longest} lines")
    if failed:
        print(
            "\nRationale belongs in CLAUDE.md or README.md, not in a workflow. "
            "Shorten the block or move it there and point at it."
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
