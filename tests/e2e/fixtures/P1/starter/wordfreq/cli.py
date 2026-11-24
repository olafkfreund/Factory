"""Command-line entry point and word frequency helpers for wordfreq."""

from __future__ import annotations

from collections.abc import Sequence


def count_words(
    text: str,
    *,
    min_len: int = 1,
    ignore_case: bool = True,
    top: int | None = None,
) -> list[tuple[str, int]]:
    """Count word occurrences in *text* and return `(word, count)` pairs."""
    _ = (text, min_len, ignore_case, top)
    msg = "count_words is not implemented yet"
    raise NotImplementedError(msg)


def format_table(rows: Sequence[tuple[str, int]]) -> str:
    """Format `(word, count)` pairs as tab-separated lines."""
    _ = rows
    msg = "format_table is not implemented yet"
    raise NotImplementedError(msg)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the wordfreq CLI and return the process exit code."""
    _ = argv
    msg = "main is not implemented yet"
    raise NotImplementedError(msg)


if __name__ == "__main__":
    raise SystemExit(main())
