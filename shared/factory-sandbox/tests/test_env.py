"""Verdict tables: the shared logic reproduces each service's rules (#3709)."""

from __future__ import annotations

import os
from dataclasses import replace

import pytest
from agent_sandbox import (
    child_env,
    get_agent_env_blanks,
    is_agent_env_allowed,
    is_denied_env_key,
    without_host_secrets,
)
from policies import AIFACTORY, PFACTORY, TFACTORY

NEW_DENIED = ("CFACTORY_READ_KEY", "CFACTORY_GITHUB_TOKEN", "GITLAB_TOKEN")
DENIED = (
    "GITHUB_TOKEN", "gh_token", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "JWT_SECRET",
    "MY_PASSWORD", "SOME_KMS_ID", "TRUSTED_PLAN_KEY_X", "S3_SECRET_KEY",
)  # fmt: skip
ALLOWED = ("PATH", "LANG", "LC_ALL", "CI", "GIT_CONFIG_KEY_3", "HTTPS_PROXY", "https_proxy")
# name -> (aifactory, pfactory, tfactory) allowed verdicts
OTHER = {
    "HOME": (False, True, True),
    "XDG_CONFIG_HOME": (False, True, True),
    "CLAUDE_CODE_OAUTH_TOKEN": (True, False, False),  # keep is allowed only for AIFactory
    "NIX_GITHUB_TOKEN": (True, False, False),  # credential-shaped pattern match
    "PLAIN_VAR": (False, False, False),
    "PFACTORY_MCP_KEY": (False, False, False),
    "NIX_CONFIG": (True, False, False),
    "SOME_SIGNING_KEY": (False, False, False),
}
POLICIES = (AIFACTORY, PFACTORY, TFACTORY)


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("name", DENIED + NEW_DENIED)
def test_denied(policy, name):
    assert is_denied_env_key(policy, name)
    assert not is_agent_env_allowed(policy, name)


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("name", ALLOWED)
def test_allowed(policy, name):
    assert is_agent_env_allowed(policy, name)


@pytest.mark.parametrize("name", OTHER)
def test_service_verdicts(name):
    got = tuple(is_agent_env_allowed(p, name) for p in POLICIES)
    # NIX_CONFIG is denied (not just unallowed) for PF/TF only.
    assert got == OTHER[name]


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("name", NEW_DENIED)
def test_new_names_denied_through_extra_env(policy, name, monkeypatch):
    monkeypatch.setenv(name, "value-12345678")
    monkeypatch.setenv(policy.extra_env, name)
    assert name not in child_env(policy, agent=True)
    assert name not in child_env(policy)
    assert name not in child_env(policy, runner=True)
    assert get_agent_env_blanks(policy)[name] == ""


def test_extra_env_opts_in_but_never_a_denied_name(monkeypatch):
    monkeypatch.setenv("PLAIN_VAR", "x")
    monkeypatch.setenv("APP_API_TOKEN", "y")
    monkeypatch.setenv("AIFACTORY_AGENT_ENV_EXTRA", "PLAIN_VAR, APP_API_TOKEN")
    assert is_agent_env_allowed(AIFACTORY, "PLAIN_VAR")
    assert not is_agent_env_allowed(AIFACTORY, "APP_API_TOKEN")


def test_aifactory_child_env_flags(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("anthropic_api_key", "b")
    monkeypatch.setenv("MCP_TOKEN", "t")
    monkeypatch.setenv("PLAIN_VAR", "p")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "o")
    env = child_env(AIFACTORY)
    assert "ANTHROPIC_API_KEY" not in env and "anthropic_api_key" not in env
    assert "MCP_TOKEN" not in env and env["PLAIN_VAR"] == "p"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert child_env(AIFACTORY, runner=True)["MCP_TOKEN"] == "t"
    assert "PLAIN_VAR" not in child_env(AIFACTORY, agent=True)
    assert child_env(AIFACTORY, keep=("CLAUDE_CODE_OAUTH_TOKEN",))["CLAUDE_CODE_OAUTH_TOKEN"] == "o"
    assert child_env(AIFACTORY, extra={"E": "1"})["E"] == "1"


def test_pin_git_on_and_off(monkeypatch):
    monkeypatch.delenv("GIT_PAGER", raising=False)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/tmp/evil")
    on = child_env(PFACTORY, agent=True)
    assert on["GIT_CONFIG_COUNT"] == "11" and on["GIT_CONFIG_KEY_1"] == "core.hooksPath"
    assert on["GIT_CONFIG_VALUE_1"] == "/dev/null"
    off = child_env(PFACTORY, agent=True, pin_git=False)
    assert off["GIT_CONFIG_COUNT"] == "1" and "GIT_PAGER" not in off


def test_pf_tf_child_env_has_no_credentials_unless_kept(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "o")
    monkeypatch.setenv("GH_TOKEN", "g")
    monkeypatch.setenv("HOME", "/h")
    env = child_env(PFACTORY, agent=True, pin_git=False)
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env and "GH_TOKEN" not in env
    assert env["HOME"] == "/h"
    kept = child_env(PFACTORY, ("GH_TOKEN",), agent=True, pin_git=False)
    assert kept["GH_TOKEN"] == "g"


def test_blanks(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "o")
    monkeypatch.setenv("PLAIN_VAR", "p")
    monkeypatch.setenv("PATH", os.environ.get("PATH", "/bin"))
    for policy in POLICIES:
        blanks = get_agent_env_blanks(policy)
        assert "CLAUDE_CODE_OAUTH_TOKEN" not in blanks and "PATH" not in blanks
        assert blanks["PLAIN_VAR"] == ""


def test_blank_exempt(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert get_agent_env_blanks(AIFACTORY)["ANTHROPIC_API_KEY"] == ""
    p = replace(AIFACTORY, blank_exempt=lambda n: n == "ANTHROPIC_API_KEY")
    assert "ANTHROPIC_API_KEY" not in get_agent_env_blanks(p)


def test_without_host_secrets(monkeypatch):
    monkeypatch.setenv("APP_API_TOKEN", "host-secret-sentinel")
    src = {"RENAMED": "host-secret-sentinel", "PLAIN": "safe-sentinel", "EMPTY": ""}
    assert without_host_secrets(PFACTORY, src) == {"PLAIN": "safe-sentinel", "EMPTY": ""}


# Factory#3720
@pytest.mark.parametrize("name", ("GL_TOKEN", "gl_token"))
def test_gl_token_denied(name):
    assert is_denied_env_key(AIFACTORY, name)


@pytest.mark.parametrize("name", ("SOME_API_KEY_FILE", "X_TOKEN_FILE", "x_token_file"))
def test_credential_file_names_dropped_from_plain_children(monkeypatch, name):
    monkeypatch.setenv(name, "/run/secret")
    assert name not in child_env(PFACTORY)
    assert name in child_env(PFACTORY, runner=True)


@pytest.mark.parametrize(
    ("raw", "want"),
    (
        ("http://u:p%40w@proxy:3128", "http://proxy:3128"),
        ("u:pw@proxy:3128", "proxy:3128"),
        ("http://proxy:3128", "http://proxy:3128"),
        ("http://u:pw@[::1]:3128", "http://[::1]:3128"),
        ("http://u:pw@proxy/x@y", None),  # an "@" left in the path: fail closed
        ("http://u:pw@", "http://"),
        ("http:/u@proxy", None),  # not a form we parse: fail closed
    ),
)
def test_strip_proxy_userinfo(raw, want):
    from agent_sandbox.env import strip_proxy_userinfo

    assert strip_proxy_userinfo(raw) == want


@pytest.mark.parametrize("policy", POLICIES)
def test_proxy_userinfo_agent_only(monkeypatch, policy):
    monkeypatch.setenv("HTTPS_PROXY", "http://u:pw@proxy:3128")
    monkeypatch.setenv("http_proxy", "http:/u@proxy")
    assert child_env(policy, agent=True)["HTTPS_PROXY"] == "http://proxy:3128"
    assert "http_proxy" not in child_env(policy, agent=True)
    assert child_env(policy)["HTTPS_PROXY"] == "http://u:pw@proxy:3128"
    assert (
        child_env(policy, agent=True, extra={"HTTPS_PROXY": "http://a:b@x"})["HTTPS_PROXY"]
        == "http://a:b@x"
    )
    blanks = get_agent_env_blanks(policy)
    assert blanks["HTTPS_PROXY"] == "http://proxy:3128"
    assert blanks["http_proxy"] == ""


def test_denied_proxy_name_stays_blank(monkeypatch):
    monkeypatch.setenv("FTP_PROXY", "http://u:pw@proxy:3128")  # allow pattern has no FTP
    assert get_agent_env_blanks(PFACTORY)["FTP_PROXY"] == ""


@pytest.mark.parametrize("policy", POLICIES)
def test_git_path_names_not_blanked(monkeypatch, policy):
    monkeypatch.setenv("GIT_DIR", "/x")
    monkeypatch.setenv("GIT_NAMESPACE", "n")
    blanks = get_agent_env_blanks(policy)
    assert "GIT_DIR" not in blanks and "GIT_NAMESPACE" not in blanks
    assert "GIT_DIR" not in child_env(policy, agent=True)


def test_denied_allowed_proxy_name_stays_blank(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://u:pw@proxy:3128")
    policy = replace(PFACTORY, deny_exact=PFACTORY.deny_exact | {"HTTPS_PROXY"})
    assert get_agent_env_blanks(policy)["HTTPS_PROXY"] == ""
