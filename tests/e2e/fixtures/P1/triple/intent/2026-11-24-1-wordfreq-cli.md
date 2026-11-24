---
status: approved
issue: 1
author: factory-e2e
---

# Intent: wordfreq deterministic word frequency CLI

## Problem

The starter `wordfreq` package only contains stubs that raise `NotImplementedError`, so users cannot count or rank word frequencies from files or standard input.

## Proposed outcome

`wordfreq` provides a deterministic Python standard-library CLI and library functions (`count_words`, `format_table`, `main`) that tokenize ASCII alphanumeric words, filter by minimum length, rank by descending frequency with alphabetical tie-breaking, and emit either tab-separated lines or JSON.

## Affected users and systems

- `wordfreq/cli.py` and `tests/test_wordfreq.py` in the P1 fixture repository.

## Constraints

- Use the Python standard library only; do not add third-party runtime dependencies.
- Invalid arguments or missing input files must exit with code `2` and write an error text to `stderr`.

## Open questions

None.
