"""Tests for the canonical log-value sanitizer (factory_common.logsafe).

The load-bearing test is :func:`test_forged_log_line_does_not_appear`: it runs a
real ``logging`` pipeline and asserts the attacker's second record is not there.
Break :func:`sanitize_log` (let a raw newline through) and that test goes red.
"""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PKG_ROOT))

from factory_common.logsafe import DEFAULT_MAX_LENGTH, sanitize_log  # noqa: E402

FORGERY = "abc\nERROR: fake entry"


def _capture(record_value: str) -> list[str]:
    """Log ``record_value`` through a real handler; return the emitted lines."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
    logger = logging.getLogger("factory_common.tests.logsafe")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.info("Starting task %s", record_value)
    handler.flush()
    return stream.getvalue().splitlines()


def test_forged_log_line_does_not_appear() -> None:
    """The attacker's injected record must not become a record of its own."""
    unsanitized = _capture(FORGERY)
    assert len(unsanitized) == 2, "precondition: the raw value forges a line"
    assert "ERROR: fake entry" in unsanitized[1]

    sanitized = _capture(sanitize_log(FORGERY))
    assert len(sanitized) == 1
    assert not any(line.startswith("ERROR: fake entry") for line in sanitized)
    # ...and the payload is still visible for debugging, just inert.
    assert sanitized[0] == "INFO:Starting task abc\\nERROR: fake entry"


def test_carriage_return_and_crlf_are_escaped() -> None:
    assert sanitize_log("a\rb") == "a\\rb"
    assert sanitize_log("a\r\nb") == "a\\nb"
    assert "\n" not in sanitize_log("a\nb")
    assert "\r" not in sanitize_log("a\rb")


def test_control_characters_are_escaped_but_tab_survives() -> None:
    assert sanitize_log("a\x00b\x1bc") == "a\\x00b\\x1bc"
    assert sanitize_log("a\tb") == "a\tb"


def test_ordinary_values_are_untouched() -> None:
    """Debuggability: the sanitizer must not mangle normal log values."""
    for value in (
        "spec-042-add-login",
        "/home/user/projects/api/src/main.py",
        "C:\\Users\\dev\\repo",
        "traceback: ValueError('bad id')",
        "commit møte-fix passerte",
    ):
        assert sanitize_log(value) == value


def test_non_strings_are_stringified() -> None:
    assert sanitize_log(42) == "42"
    assert sanitize_log(None) == "None"
    assert sanitize_log(Path("/var/data/x")) == "/var/data/x"


def test_length_cap() -> None:
    out = sanitize_log("x" * (DEFAULT_MAX_LENGTH + 10))
    assert out.startswith("x" * DEFAULT_MAX_LENGTH)
    assert out.endswith("...[truncated 10 chars]")
    assert sanitize_log("x" * 5000, max_length=None) == "x" * 5000


def test_escaping_is_counted_before_truncation() -> None:
    """A payload of newlines cannot smuggle bytes past the cap."""
    out = sanitize_log("\n" * DEFAULT_MAX_LENGTH, max_length=10)
    assert out == "\\n" * 5 + "...[truncated 3990 chars]"
