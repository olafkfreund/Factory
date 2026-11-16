"""The three services' Policies as they define them, for the verdict tables."""

from __future__ import annotations

import re

from agent_sandbox import Policy

_CLAUDE = frozenset({"CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"})
_ALLOW = (
    r"PATH|LANG|LANGUAGE|TZ|TERM|COLORTERM|TMPDIR|USER|LOGNAME|SHELL|CI"
    r"|PYTHONUNBUFFERED|PYTHONIOENCODING|TRACEPARENT"
    r"|SSL_CERT_FILE|SSL_CERT_DIR|NODE_EXTRA_CA_CERTS|REQUESTS_CA_BUNDLE"
    r"|GIT_(?:AUTHOR|COMMITTER)_(?:NAME|EMAIL)"
    r"|GIT_CONFIG_(?:COUNT|KEY_\d+|VALUE_\d+)|GIT_PAGER"
    r"|OPENAI_BASE_URL|GOOGLE_CLOUD_PROJECT|GOOGLE_CLOUD_LOCATION|GOOGLE_GENAI_USE_VERTEXAI"
    r"|LC_\w+|CLAUDE_CODE_\w+|NIX_\w+|(?i:(?:HTTPS?|NO|ALL)_PROXY)"
    r"|PLAYWRIGHT_BROWSERS_PATH|PLAYWRIGHT_SKIP_\w+|FONTCONFIG_FILE"
)
_PATTERN = r"SECRET|PASSWORD|PRIVATE_KEY|CREDENTIAL|(?:^|_)KMS|PASSPHRASE|TRUSTED_PLAN_KEY"
_CONTROL = frozenset(
    {"API_TOKEN", "APP_API_TOKEN", "JWT_SECRET", "APP_JWT_SECRET", "DATABASE_URL",
     "APP_DATABASE_URL", "AIFACTORY_TOKEN", "AIFACTORY_MARKER_NONCE",
     "AIFACTORY_TRUSTED_CONTRACT", "APP_CFACTORY_READ_KEY", "S3_SECRET_KEY"}
)  # fmt: skip


def _pf_tf(prefix: str) -> Policy:
    names = ("MCP_KEY", "API_TOKEN_FILE", "AIFACTORY_API_TOKEN", "BACKSTAGE_TOKEN",
             "CONFLUENCE_TOKEN", "CONTRACT_SIGNING_KEY", "GITBOOK_TOKEN", "MCP_SECRET",
             "NOTION_TOKEN", "RECON_TOKEN")  # fmt: skip
    return Policy(
        extra_env=f"{prefix}_AGENT_ENV_EXTRA",
        deny_exact=_CONTROL
        | {"NIX_CONFIG", "NIX_ACCESS_TOKENS"}
        | {f"{prefix}_{n}" for n in names},
        deny_pattern=re.compile(_PATTERN + "|SIGNING_KEY", re.I),
        allow_pattern=re.compile(_ALLOW + r"|HOME|XDG_\w+_HOME|CODEX_HOME"),
        keep=_CLAUDE,
        credential_blocks_allow=True,
    )


AIFACTORY = Policy(
    extra_env="AIFACTORY_AGENT_ENV_EXTRA",
    deny_exact=_CONTROL | {"AIFACTORY_AGENT_GITHUB_TOKEN"},
    deny_pattern=re.compile(_PATTERN, re.I),
    allow_pattern=re.compile(_ALLOW),
    keep=_CLAUDE,
    keep_is_allowed=True,
    strip_vars=frozenset(
        {"ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_FILE", "AIFACTORY_TRUSTED_CONTRACT"}
    ),
)
PFACTORY = _pf_tf("PFACTORY")
TFACTORY = _pf_tf("TFACTORY")
