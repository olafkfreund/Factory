"""Visible tests for the wordfreq package and CLI."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from wordfreq.cli import count_words, format_table, main

if TYPE_CHECKING:
    from pathlib import Path


def test_count_words_basic_ranking() -> None:
    text = "Apple banana apple, cherry! Banana apple."
    assert count_words(text) == [("apple", 3), ("banana", 2), ("cherry", 1)]


def test_count_words_tie_breaking_and_case() -> None:
    text = "Beta alpha beta ALPHA"
    assert count_words(text) == [("alpha", 2), ("beta", 2)]
    assert count_words(text, ignore_case=False) == [
        ("ALPHA", 1),
        ("Beta", 1),
        ("alpha", 1),
        ("beta", 1),
    ]


def test_count_words_validation() -> None:
    with pytest.raises(ValueError, match="min_len"):
        count_words("hello", min_len=0)
    with pytest.raises(ValueError, match="top"):
        count_words("hello", top=-1)


def test_format_table_tsv() -> None:
    assert format_table([("apple", 3), ("banana", 2)]) == "apple\t3\nbanana\t2"
    assert format_table([]) == ""


def test_cli_top_and_min_len(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("to be or not to be that is the question", encoding="utf-8")
    rc = main([str(sample), "--min-len", "3", "--top", "2"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip().splitlines() == ["not\t1", "question\t1"]


def test_cli_json_and_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("one two two", encoding="utf-8")
    assert main([str(sample), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == [{"word": "two", "count": 2}, {"word": "one", "count": 1}]

    assert main([str(tmp_path / "missing.txt")]) == 2
    assert "error:" in capsys.readouterr().err
