"""Command-line entry point and word frequency helpers for wordfreq."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def count_words(
    text: str,
    *,
    min_len: int = 1,
    ignore_case: bool = True,
    top: int | None = None,
) -> list[tuple[str, int]]:
    """Count word occurrences in *text* and return `(word, count)` pairs."""
    if min_len < 1:
        msg = "min_len must be >= 1"
        raise ValueError(msg)
    if top is not None and top < 0:
        msg = "top must be >= 0"
        raise ValueError(msg)

    tokens = _WORD_RE.findall(text)
    if ignore_case:
        tokens = [tok.lower() for tok in tokens]
    filtered = [tok for tok in tokens if len(tok) >= min_len]
    counts = Counter(filtered)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    if top is not None:
        return ranked[:top]
    return ranked


def format_table(rows: Sequence[tuple[str, int]]) -> str:
    """Format `(word, count)` pairs as tab-separated lines."""
    return "\n".join(f"{word}\t{count}" for word, count in rows)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wordfreq", description="Count and rank words in text.")
    parser.add_argument(
        "path",
        nargs="?",
        default="-",
        help="Input file path, or '-' to read from stdin (default: '-')",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Limit output to the top N words",
    )
    parser.add_argument(
        "--min-len",
        type=int,
        default=1,
        help="Minimum word length to include (default: 1)",
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Preserve case instead of lowercasing tokens",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit JSON array of {'word': ..., 'count': ...} objects",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the wordfreq CLI and return the process exit code."""
    parser = _build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 2

    if args.min_len < 1:
        sys.stderr.write("error: --min-len must be >= 1\n")
        return 2
    if args.top is not None and args.top < 0:
        sys.stderr.write("error: --top must be >= 0\n")
        return 2

    if args.path == "-":
        text = sys.stdin.read()
    else:
        try:
            text = Path(args.path).read_text(encoding="utf-8")
        except OSError as exc:
            sys.stderr.write(f"error: cannot read {args.path}: {exc}\n")
            return 2

    rows = count_words(
        text,
        min_len=args.min_len,
        ignore_case=not args.case_sensitive,
        top=args.top,
    )
    if args.as_json:
        payload = [{"word": word, "count": count} for word, count in rows]
        sys.stdout.write(json.dumps(payload) + "\n")
    else:
        table = format_table(rows)
        if table:
            sys.stdout.write(table + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
