"""
Git Provider Abstraction
========================

Abstracts git hosting providers (GitHub, GitLab, Bitbucket) behind a common interface.

Usage:
    from providers import GitProvider, get_provider

    # Get provider based on config
    provider = get_provider(config)

    # Fetch PR data
    pr = await provider.fetch_pr(123)

    # Post review
    await provider.post_review(123, review)
"""

from .azure_devops_provider import AzureDevOpsProvider
from .factory import get_provider, register_provider
from .github_provider import GitHubProvider
from .gitlab_provider import GitLabProvider
from .protocol import (
    GitProvider,
    IssueComment,
    IssueData,
    IssueFilters,
    PRData,
    PRFilters,
    ProviderCommentError,
    ProviderType,
    ReviewData,
    ReviewFinding,
    fanout_comments,
)

__all__ = [
    # Protocol
    "GitProvider",
    "PRData",
    "IssueData",
    "IssueComment",
    "ReviewData",
    "ReviewFinding",
    "IssueFilters",
    "PRFilters",
    "ProviderType",
    "ProviderCommentError",
    "fanout_comments",
    # Implementations
    "GitHubProvider",
    "GitLabProvider",
    "AzureDevOpsProvider",
    # Factory
    "get_provider",
    "register_provider",
]
