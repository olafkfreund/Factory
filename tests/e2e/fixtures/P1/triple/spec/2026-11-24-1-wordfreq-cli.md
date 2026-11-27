---
status: approved
issue: 1
intent: intent/2026-11-24-1-wordfreq-cli.md
---

# Spec: wordfreq deterministic word frequency CLI

## Design

Implement the word frequency engine and command-line interface in `wordfreq/cli.py` (invoked as `python -m wordfreq` via `wordfreq/__main__.py`) using only the Python standard library (`argparse`, `collections.Counter`, `json`, `pathlib`, `re`, `sys`):

1. `count_words(text, *, min_len=1, ignore_case=True, top=None) -> list[tuple[str, int]]`:
   - Tokenize `text` with maximal contiguous ASCII alphanumeric runs (`[A-Za-z0-9]+`).
   - Lowercase tokens when `ignore_case` is `True`; preserve original case when `False`.
   - Keep only tokens with `len(token) >= min_len`.
   - Raise `ValueError("min_len must be >= 1")` if `min_len < 1`, and raise `ValueError("top must be >= 0")` if `top is not None and top < 0`.
   - Sort pairs by `(-count, word)` (descending frequency, then ascending ASCII lexicographical order) and slice to `[:top]` when `top` is provided.
2. `format_table(rows) -> str`:
   - Format `(word, count)` pairs as `f"{word}\t{count}"` joined by `\n` (return `""` for empty `rows`, without a trailing newline).
3. `main(argv=None) -> int` and `python -m wordfreq` CLI invocation:
   - The package is executable as `python -m wordfreq [path] [--top N] [--min-len M] [--case-sensitive] [--json]`, which delegates to `wordfreq.cli.main()`.
   - Positional `path` is optional and defaults to `"-"` when omitted; when `path` is omitted or `"-"`, read UTF-8 text from `sys.stdin`, otherwise read the given file path as UTF-8 text.
   - `--case-sensitive` preserves token case (`ignore_case=False`); when omitted, tokens are lowercased (`ignore_case=True`).
   - `--min-len M` defaults to `1`; `--top N` defaults to `None` (all words).
   - `--top 0` is valid, not an error: it returns `0` and prints no rows (empty stdout in TSV mode, `[]\n` with `--json`). Only `--top` below `0` is invalid.
   - Output format:
     - Default TSV mode: write `format_table(rows)` followed by a single final newline (`\n`) to `sys.stdout` when `rows` is non-empty; write nothing (`""`, no newline) when `rows` is empty.
     - `--json` mode: write a single-line JSON array of `{"word": word, "count": count}` objects (`json.dumps(...)`) followed by a single final newline (`\n`) to `sys.stdout` (including `[]\n` when `rows` is empty).
   - Return `0` on success. On invalid CLI arguments (`--min-len < 1`, `--top < 0`, or `argparse` parse errors) or unreadable file paths, write a non-empty error text to `sys.stderr` and return `2`.

## Alternatives rejected

- Splitting on whitespace only: leaves punctuation attached to words and produces inconsistent counts.
- External CLI libraries (`click`, `typer`): violates the standard-library-only constraint.

## Risks

- Empty input emitting a blank line in TSV mode: avoided by writing a trailing newline only when `format_table(rows)` is non-empty.

## Verification

- `count_words` extracts `[A-Za-z0-9]+` tokens, lowercases by default, preserves case when `ignore_case=False`, filters by `min_len`, sorts by `(-count, word)`, and raises `ValueError("min_len must be >= 1")` when `min_len < 1` or `ValueError("top must be >= 0")` when `top < 0`.
- `format_table` formats `(word, count)` rows as `word\tcount` lines separated by `\n` and returns `""` for empty input.
- `main` and `python -m wordfreq` read from `sys.stdin` by default when no `path` argument is given (or when `path` is `"-"`), honor `--case-sensitive`, `--top`, `--min-len`, and `--json`, terminate non-empty TSV output and `--json` output with a final `\n` (writing nothing for empty TSV output), and return `0` on success or `2` with non-empty `stderr` on invalid arguments or missing files. `--top 0` succeeds with exit `0` and no rows; only a negative `--top` exits `2`.
- `pytest -q` passes across `tests/test_wordfreq.py`.
