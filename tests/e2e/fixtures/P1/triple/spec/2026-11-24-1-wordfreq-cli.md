---
status: approved
issue: 1
intent: intent/2026-11-24-1-wordfreq-cli.md
---

# Spec: wordfreq deterministic word frequency CLI

## Design

Implement the word frequency engine and command-line interface in `wordfreq/cli.py` using only the Python standard library (`argparse`, `collections.Counter`, `json`, `pathlib`, `re`, `sys`):

1. `count_words(text, *, min_len=1, ignore_case=True, top=None) -> list[tuple[str, int]]`:
   - Tokenize `text` with maximal contiguous ASCII alphanumeric runs (`[A-Za-z0-9]+`).
   - Lowercase tokens when `ignore_case` is `True`; preserve original case when `False`.
   - Keep only tokens with `len(token) >= min_len`. Raise `ValueError` if `min_len < 1` or if `top is not None and top < 0`.
   - Sort pairs by `(-count, word)` and slice to `[:top]` when `top` is provided.
2. `format_table(rows) -> str`:
   - Format `(word, count)` pairs as `f"{word}\t{count}"` joined by `\n` (empty string for empty input).
3. `main(argv=None) -> int`:
   - Accept optional positional `path` (default `"-"` for `sys.stdin`), `--top N`, `--min-len M` (default `1`), `--case-sensitive`, and `--json`.
   - In default mode, print `format_table(rows)` followed by a trailing newline when non-empty (print nothing for empty results).
   - In `--json` mode, print a JSON array of `{"word": word, "count": count}` objects followed by a newline.
   - Return `0` on success. On invalid arguments (`min_len < 1`, `top < 0`) or unreadable file paths, write an error message to `sys.stderr` and return `2`.

## Alternatives rejected

- Splitting on whitespace only: leaves punctuation attached to words and produces inconsistent counts.
- External CLI libraries (`click`, `typer`): violates the standard-library-only constraint.

## Risks

- Empty input emitting a blank line in TSV mode: avoided by writing a newline only when `format_table(rows)` is non-empty.

## Verification

- `count_words` extracts `[A-Za-z0-9]+` tokens, lowercases by default, filters by `min_len`, sorts by `(-count, word)`, and raises `ValueError` when `min_len < 1` or `top < 0`.
- `format_table` formats `(word, count)` rows as `word\tcount` lines separated by `\n` and returns `""` for empty input.
- `main` supports positional file path or `"-"` (stdin), `--top`, `--min-len`, `--case-sensitive`, and `--json`, returning `0` on success and `2` on invalid flags or missing files.
- `pytest -q` passes across `tests/test_wordfreq.py`.
