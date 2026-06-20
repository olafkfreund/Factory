"""Tests for the canonical secret-pattern table (factory_common.secrets)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PKG_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PKG_ROOT))

from factory_common import secrets  # noqa: E402


@pytest.mark.parametrize(
    ("name", "sample"),
    [
        ("github-pat", "ghp_" + "a" * 36),
        ("github-pat", "gho_" + "B" * 40),
        ("github-fine-grained-pat", "github_pat_" + "a" * 30),
        ("gitlab-pat", "glpat-" + "x" * 20),
        ("slack-token", "xoxb-" + "1" * 12),
        ("aws-access-key-id", "AKIA" + "A" * 16),
        ("aws-access-key-id", "ASIA" + "Z" * 16),
    ],
)
def test_token_shapes_are_detected(name: str, sample: str) -> None:
    findings = secrets.scan(sample)
    assert any(found == name for found, _ in findings), findings
    assert secrets.contains_secret(sample)


def test_private_key_header_detected() -> None:
    text = "-----BEGIN OPENSSH PRIVATE KEY-----\nbody\n"
    assert secrets.contains_secret(text)
    assert "-----BEGIN" not in secrets.redact(text)


def test_redact_replaces_full_token() -> None:
    token = "ghp_" + "a" * 36
    out = secrets.redact(f"using token {token} now")
    assert token not in out
    assert secrets.PLACEHOLDER in out
    assert out == f"using token {secrets.PLACEHOLDER} now"


def test_authorization_bearer_preserves_context() -> None:
    line = "Authorization: Bearer abc123DEF456token"
    out = secrets.redact(line)
    # The secret is gone but the header name + scheme are preserved.
    assert "abc123DEF456token" not in out
    assert "Authorization" in out
    assert "Bearer" in out
    assert secrets.PLACEHOLDER in out


def test_private_token_header_preserves_context() -> None:
    line = "PRIVATE-TOKEN: glpat-secrettokenvalue1"
    out = secrets.redact(line)
    assert "glpat-secrettokenvalue1" not in out
    assert "PRIVATE-TOKEN" in out


def test_url_userinfo_redacted_but_host_kept() -> None:
    url = "https://user:s3cretpw@gitlab.com/api"
    out = secrets.redact(url)
    assert "s3cretpw" not in out
    assert "gitlab.com/api" in out
    assert "https://user:" in out


def test_basic_auth_header_redacted() -> None:
    line = "authorization=Basic dXNlcjpwYXNzd29yZA=="
    out = secrets.redact(line)
    assert "dXNlcjpwYXNzd29yZA==" not in out
    assert secrets.PLACEHOLDER in out


def test_clean_text_is_unchanged() -> None:
    clean = "GET /api/health -> 200 in 12ms"
    assert secrets.redact(clean) == clean
    assert not secrets.contains_secret(clean)
    assert secrets.scan(clean) == []


def test_scan_returns_raw_secret_span() -> None:
    token = "glpat-" + "y" * 24
    findings = secrets.scan(f"PRIVATE-TOKEN: {token}")
    spans = [span for _, span in findings]
    assert token in spans


def test_every_pattern_has_name_and_description() -> None:
    for pattern in secrets.SECRET_PATTERNS:
        assert pattern.name
        assert pattern.description
        assert pattern.regex is not None
