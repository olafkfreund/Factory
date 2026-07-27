"""GitHub JSON shapes shared by both GitHub providers (Factory#370).

The fleet has two GitHub providers — :class:`~providers.github_provider.GitHubProvider`
over the ``gh`` CLI, and :class:`~providers.http_github_provider.HttpGitHubProvider`
over REST with an explicit token. This module holds the parsing they genuinely
share, so adding the second one did not paste the first one's helpers.

**What is shared, and why only this much.** Comments are identical between the
two because the gh provider reads them with ``gh api``, which returns the REST
payload verbatim — same ``user``/``created_at``/``html_url`` keys. So the comment
parser, the issue-number-from-URL helper and the timestamp parser are one
implementation.

**What is deliberately NOT shared: the issue parser.** The two wire formats
differ, and they differ silently:

======================  =========================  ==========================
field                   ``gh`` CLI JSON            REST JSON
======================  =========================  ==========================
author                  ``author``                 ``user``
created / updated       ``createdAt``/``updatedAt``  ``created_at``/``updated_at``
web link                ``url``                    ``html_url``
======================  =========================  ==========================

A single "unified" issue parser would therefore read ``None`` for half its
fields against whichever format it was not written for, and still return a
populated-looking ``IssueData``. That is a data-loss bug that no type checker
catches, so the two parsers stay separate on purpose. **Do not merge them
because a clone detector says they look alike** — the similarity is structural,
not semantic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .protocol import IssueComment, ProviderType

# GitHub caps both the issue and the comment endpoints at 100 per page.
PAGE_SIZE = 100

# The page cap bounds a repository-wide comment fetch (50 x 100 = 5000 comments)
# rather than paging forever against an unknown history size. Hitting it is an
# error, never a silent truncation.
COMMENT_MAX_PAGES = 50


def parse_datetime(value: Any) -> datetime:
    """Tolerant ISO parse: a missing or malformed timestamp is not worth failing
    a sync over, since neither provider treats timestamps as authoritative."""
    if not isinstance(value, str) or not value:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(UTC)


def issue_number_from_url(url: str) -> int | None:
    """Recover the issue number from a comment's ``issue_url``.

    The repository-wide comments endpoint does not carry the issue number as a
    field; the only link back is the URL the comment was made against.
    """
    tail = (url or "").rstrip("/").rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else None


def parse_comment(data: dict[str, Any], issue_number: int) -> IssueComment:
    """A GitHub comment payload as the provider-neutral :class:`IssueComment`.

    Shared by both providers because ``gh api`` returns the REST payload
    unchanged — unlike the issue endpoints, where the CLI reshapes the keys.
    """
    user = data.get("user") or {}
    author = user.get("login", "") if isinstance(user, dict) else str(user)
    created = data.get("created_at")
    return IssueComment(
        id=str(data.get("id", "")),
        issue_number=issue_number,
        author=author,
        body=data.get("body") or "",
        created_at=parse_datetime(created),
        updated_at=parse_datetime(data.get("updated_at") or created),
        url=data.get("html_url") or "",
        provider=ProviderType.GITHUB,
        raw_data=data,
    )


def milestone_title(milestone: Any) -> str | None:
    """GitHub's milestone object as the plain title a caller stores."""
    if isinstance(milestone, dict):
        title = milestone.get("title")
        return title if isinstance(title, str) else None
    return milestone if isinstance(milestone, str) else None
