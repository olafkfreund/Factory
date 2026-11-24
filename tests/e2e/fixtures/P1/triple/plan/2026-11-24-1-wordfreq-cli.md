---
status: approved
issue: 1
spec: spec/2026-11-24-1-wordfreq-cli.md
---

# Plan: wordfreq deterministic word frequency CLI

Approved decisions: standard-library implementation in `wordfreq/cli.py` invoked via `python -m wordfreq`; `[A-Za-z0-9]+` tokenization; `(-count, word)` ordering; `ValueError("min_len must be >= 1")` on `min_len < 1` and `ValueError("top must be >= 0")` on `top < 0`; `sys.stdin` as default input when `path` is omitted or `"-"`; `--case-sensitive` passing `ignore_case=False`; TSV and `--json` output formats terminated with a final `\n` (and `""` on empty TSV output); CLI exit code `0` on success and `2` on invalid flags or unreadable files.

## Steps

1. `wordfreq/cli.py`: implement `count_words`, `format_table`, and `main` supporting default `stdin`, positional `path`, `--top`, `--min-len`, `--case-sensitive`, and `--json` -> verify by `python -m pytest -q`.
   Traps: standard library only; terminate non-empty TSV and all `--json` output with `\n` but print nothing on empty TSV output; return exit code `2` with a `stderr` text on invalid arguments or missing files.
2. `tests/test_wordfreq.py`: add unit and CLI tests covering tie-breaking, `--case-sensitive`, default `stdin`, argument validation, trailing newlines on TSV and `--json` output, `python -m wordfreq`, and missing-file exit code `2` -> verify by `python -m pytest -q`.
   Traps: none.

## Tests

`python -m pytest -q` -> all tests in `tests/test_wordfreq.py` pass.

## Rollback

Revert the commits on the task branch to restore the starter stubs.
