"""Guard: GitProvider is exactly WorkItemProvider + CodeProvider (no raw HTTP).

Factory#392 / RFC-0022 section 2.1. The split is type-level: the three full
providers satisfy both halves unchanged, and the halves share nothing but
``provider_type``. ``isinstance`` on a runtime Protocol checks that members
exist, not that they work, so the HTTP-only provider is pinned separately.
"""

from __future__ import annotations

import pytest

pytest.importorskip("httpx", reason="provider modules import httpx at module scope")

from providers import (
    AzureDevOpsProvider,
    CodeProvider,
    GitHubProvider,
    GitLabProvider,
    GitProvider,
    HttpGitHubProvider,
    WorkItemProvider,
)


def _members(proto: type) -> set[str]:
    return {n for n in vars(proto) if not n.startswith("_")}


def test_halves_share_only_provider_type() -> None:
    wi = {n for n in vars(WorkItemProvider) if not n.startswith("_")}
    code = {n for n in vars(CodeProvider) if not n.startswith("_")}
    assert wi & code == {"provider_type"}
    assert len(wi) == 13  # 12 work-item members + provider_type
    assert len(code) == 13  # 10 code members + repo, get_repository_info, provider_type


def test_git_provider_is_exactly_the_union() -> None:
    own = {n for n in vars(GitProvider) if not n.startswith("_")}
    assert own == set(), "GitProvider adds nothing of its own (Factory#3772)"
    assert WorkItemProvider in GitProvider.__mro__
    assert CodeProvider in GitProvider.__mro__


@pytest.mark.parametrize("cls", [GitHubProvider, GitLabProvider, AzureDevOpsProvider])
def test_full_providers_satisfy_both_halves(cls: type) -> None:
    for proto in (WorkItemProvider, CodeProvider):
        missing = [m for m in _members(proto) if not hasattr(cls, m)]
        assert not missing, f"{cls.__name__} lacks {missing} for {proto.__name__}"


def test_http_provider_is_not_a_code_provider() -> None:
    missing = [m for m in _members(CodeProvider) if not hasattr(HttpGitHubProvider, m)]
    assert missing, "HttpGitHubProvider unexpectedly satisfies CodeProvider"


@pytest.mark.parametrize("proto", [WorkItemProvider, CodeProvider, GitProvider])
@pytest.mark.parametrize("name", ["api_get", "api_post"])
def test_raw_http_is_in_no_protocol(proto: type, name: str) -> None:
    """RFC-0022 section 2.2: a raw HTTP method on a provider-agnostic interface is a hole."""
    assert not hasattr(proto, name)


@pytest.mark.parametrize("cls", [GitHubProvider, GitLabProvider, AzureDevOpsProvider])
@pytest.mark.parametrize("name", ["api_get", "api_post"])
def test_concrete_providers_keep_raw_http(cls: type, name: str) -> None:
    """GitHub-specific callers keep working because they hold the concrete type."""
    assert hasattr(cls, name)
