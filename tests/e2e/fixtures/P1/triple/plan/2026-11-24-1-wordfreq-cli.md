---
status: approved
issue: 1
spec: spec/2026-11-24-1-wordfreq-cli.md
---

# Plan: wordfreq deterministic word frequency CLI

Approved decisions: standard-library implementation in `wordfreq/cli.py`; `[A-Za-z0-9]+` tokenization; `(-count, word)` ordering; `ValueError` on `min_len < 1` or `top < 0`; CLI exit code `0` on success and `2` on invalid flags or unreadable files; TSV and `--json` output formats.

## Steps

1. `wordfreq/cli.py`: implement `count_words`, `format_table`, and `main` with `argparse` flags `--top`, `--min-len`, `--case-sensitive`, and `--json` -> verify by `python -m pytest -q`.
   Traps: standard library only; do not print a blank line on empty TSV output; return exit code `2` with a `stderr` message on invalid arguments or missing files.
2. `tests/test_wordfreq.py`: add unit and CLI tests covering tie-breaking, case sensitivity, argument validation, `--json` output, and missing-file exit code `2` -> verify by `python -m pytest -q`.
   Traps: none.

## Tests

`python -m pytest -q` -> all tests in `tests/test_wordfreq.py` pass.

## Rollback

Revert the commits on the task branch to restore the starter stubs.
