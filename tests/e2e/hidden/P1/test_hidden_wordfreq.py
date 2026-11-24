"""Hidden acceptance suite for fixture P1 (wordfreq).

These tests are never pushed to the test repository during a journey; the
harness runs them against the merged commit after TFactory verification.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from wordfreq.cli import count_words, format_table, main


def test_hidden_tokenization_and_alphabetical_tie_break() -> None:
    text = "zebra! 42, Apple--zebra; APPLE... 42? banana_split"
    assert count_words(text) == [
        ("42", 2),
        ("apple", 2),
        ("zebra", 2),
        ("banana", 1),
        ("split", 1),
    ]


def test_hidden_case_sensitive_and_min_len_and_top() -> None:
    text = "aa AA aA bbb BBB ccc"
    assert count_words(text, min_len=2, ignore_case=False) == [
        ("AA", 1),
        ("BBB", 1),
        ("aA", 1),
        ("aa", 1),
        ("bbb", 1),
        ("ccc", 1),
    ]
    assert count_words(text, min_len=3, ignore_case=True, top=1) == [("bbb", 2)]
    assert count_words(text, min_len=3, ignore_case=True, top=0) == []


def test_hidden_invalid_parameters_raise_value_error() -> None:
    with pytest.raises(ValueError):
        count_words("abc", min_len=0)
    with pytest.raises(ValueError):
        count_words("abc", min_len=-3)
    with pytest.raises(ValueError):
        count_words("abc", top=-1)


def test_hidden_format_table_exact() -> None:
    assert format_table([]) == ""
    assert format_table([("alpha", 10), ("beta", 2)]) == "alpha\t10\nbeta\t2"


def test_hidden_cli_default_stdin_and_json_trailing_newline(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("Rust go rust GO python rust"))
    rc = main(["--top", "2", "--json"])
    assert rc == 0
    raw_out = capsys.readouterr().out
    assert raw_out.endswith("\n")
    payload = json.loads(raw_out)
    assert payload == [
        {"word": "rust", "count": 3},
        {"word": "go", "count": 2},
    ]


def test_hidden_cli_case_sensitive_and_tsv_trailing_newline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sample = tmp_path / "case.txt"
    sample.write_text("Go go GO rust", encoding="utf-8")
    rc = main([str(sample), "--case-sensitive"])
    assert rc == 0
    raw_out = capsys.readouterr().out
    assert raw_out == "GO\t1\nGo\t1\ngo\t1\nrust\t1\n"


def test_hidden_cli_empty_input_produces_no_blank_line(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("... !!! ---", encoding="utf-8")
    assert main([str(empty)]) == 0
    assert capsys.readouterr().out == ""


def test_hidden_cli_error_exit_codes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sample = tmp_path / "ok.txt"
    sample.write_text("hello world", encoding="utf-8")

    assert main([str(tmp_path / "does_not_exist.txt")]) == 2
    assert capsys.readouterr().err != ""

    assert main([str(sample), "--min-len", "0"]) == 2
    assert capsys.readouterr().err != ""

    assert main([str(sample), "--top", "-2"]) == 2
    assert capsys.readouterr().err != ""


def test_hidden_module_entrypoint_subprocess(tmp_path: Path) -> None:
    sample = tmp_path / "words.txt"
    sample.write_text("gamma beta alpha beta gamma gamma", encoding="utf-8")
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "wordfreq", str(sample), "--top", "2"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout == "gamma\t3\nbeta\t2\n"
