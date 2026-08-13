"""Tests for the canonical outbound-URL guard (factory_common.url_safety).

Two things are being pinned here, and the second is the unusual one.

1. The guard itself, in both postures. The strict/permissive split exists
   because the fleet legitimately fetches self-hosted services on private
   addresses; a guard that blocks RFC-1918 outright breaks the product, gets
   reverted, and leaves nothing. So the permissive posture keeps only the
   checks that cost no legitimate use -- and the cloud metadata range is
   refused in BOTH.

2. The public NAME. Each consumer's CodeQL barrier
   (``.github/codeql/custom-queries/SsrfBarriers.qll``) registers
   ``assert_safe_outbound_url`` by name. Rename it and the barrier silently
   stops clearing anything: the alerts reopen and nothing in Python fails.
   :func:`test_the_barrier_registered_names_still_exist` is the tripwire.

Lives in the hub's ``tests/`` rather than ``shared/factory-common/tests/``
because CI runs ``pytest tests/`` and nothing runs the latter (Factory#716).

Every case uses an IP literal, so ``getaddrinfo`` never leaves the machine.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PKG_ROOT = Path(__file__).resolve().parents[1] / "shared" / "factory-common"
sys.path.insert(0, str(_PKG_ROOT))

from factory_common import url_safety  # noqa: E402
from factory_common.url_safety import assert_safe_outbound_url  # noqa: E402

# The cloud instance-credentials endpoints. IPv4 is link-local; the IPv6 one is
# UNIQUE-local (fd00::/7), which is why it needs naming explicitly -- neither
# ``is_link_local`` nor ``is_reserved`` catches it.
METADATA = "http://169.254.169.254/latest/meta-data/iam/security-credentials/"
METADATA_V6 = "http://[fd00:ec2::254]/latest/meta-data/"


@pytest.mark.parametrize("url", [METADATA, METADATA_V6])
@pytest.mark.parametrize("allow_private", [False, True])
def test_metadata_is_refused_in_both_postures(url: str, allow_private: bool) -> None:
    with pytest.raises(ValueError, match="link-local/metadata"):
        assert_safe_outbound_url(url, allow_private=allow_private)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://x/", "ftp://h/f"])
@pytest.mark.parametrize("allow_private", [False, True])
def test_non_http_schemes_are_refused_in_both_postures(url: str, allow_private: bool) -> None:
    with pytest.raises(ValueError, match="unsupported URL scheme"):
        assert_safe_outbound_url(url, allow_private=allow_private)


def test_strict_posture_refuses_loopback() -> None:
    with pytest.raises(ValueError, match="non-public address"):
        assert_safe_outbound_url("http://127.0.0.1:1234/v1/models")


def test_permissive_posture_allows_the_self_hosted_case() -> None:
    url = "http://127.0.0.1:1234/v1/models"
    assert assert_safe_outbound_url(url, allow_private=True) == url


def test_a_url_with_no_host_is_refused() -> None:
    with pytest.raises(ValueError, match="no host"):
        assert_safe_outbound_url("http:///v1/models")


def test_the_guard_returns_the_url_so_a_call_site_cannot_check_and_forget() -> None:
    """The return value is load-bearing, not decoration.

    Call sites fetch what the guard RETURNED. If this ever goes back to
    returning ``None`` they break loudly instead of quietly reverting to
    fetching the unchecked string -- and the CodeQL barrier, which clears only
    the value flowing OUT of this call, stops clearing anything.
    """
    url = "http://10.0.0.5:11434/api/tags"
    assert assert_safe_outbound_url(url, allow_private=True) == url


def test_the_barrier_registered_names_still_exist() -> None:
    """A rename here is a silent security regression -- see the module docstring."""
    assert hasattr(url_safety, "assert_safe_outbound_url")
    assert hasattr(url_safety, "build_no_redirect_opener")
