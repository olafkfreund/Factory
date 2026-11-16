"""Access-review report generator (Factory#312)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import access_review_report as ar

NOW = date(2027, 1, 10)


def _w(root: Path, name: str, data: object) -> None:
    (root / name).write_text(json.dumps(data))


def _clean(root: Path) -> None:
    (root / "members-aifactory.ndjson").write_text(
        json.dumps(
            {
                "email": "a@x",
                "role": "admin",
                "active": True,
                "last_login_at": "2027-01-01T00:00:00Z",
                "org_id": "o",
                "tenant_groups": ["t"],
            }
        )
        + "\n"
    )
    _w(
        root,
        "keys.json",
        [
            {
                "key_id": "k1",
                "owner": "a@x",
                "owner_role": "member",
                "scopes": ["mcp:write"],
                "autonomy_ceiling": "hard",
                "last_used_at": "2027-01-05",
                "expires_at": "2027-06-01",
                "service": "aifactory",
            }
        ],
    )
    _w(root, "cfactory-keys.json", [{"actor": "unattributed:key-abc", "scope": "read"}])
    _w(
        root,
        "bindings.json",
        [
            {
                "name": "r",
                "kind": "RoleBinding",
                "subjects": [{"kind": "ServiceAccount", "name": "s"}],
                "justification": "needed",
            }
        ],
    )
    _w(root, "keycloak-users.json", [{"username": "a", "enabled": True, "mfa": "totp"}])
    _w(root, "platform-admins.json", [{"system": "argocd", "account": "owner"}])
    _w(root, "legacy-counters.json", [{"name": "wildcard", "count": 0}])
    _w(root, "exceptions.json", {"wildcard_retirement_date": "2027-03-01"})


def _findings(root: Path) -> str:
    text, code = ar.build(root, NOW)
    assert code == 0
    return text.split("## Findings")[1].split("## Evidence")[0]


def test_clean_input_has_no_findings(tmp_path: Path) -> None:
    _clean(tmp_path)
    assert _findings(tmp_path).strip() == "- none"


def test_missing_inputs_are_findings(tmp_path: Path) -> None:
    f = _findings(tmp_path)
    for name in ar.FILES:
        assert f"input not provided: {name}" in f
    assert "members-<service>.ndjson" in f
    assert "date not set" in f


def test_each_check_fires(tmp_path: Path) -> None:
    _clean(tmp_path)
    (tmp_path / "members-aifactory.ndjson").write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {
                    "email": "gone@x",
                    "role": "admin",
                    "active": False,
                    "last_login_at": None,
                    "org_id": "o",
                    "tenant_groups": [],
                },
                {
                    "email": "old@x",
                    "role": "member",
                    "active": True,
                    "last_login_at": "2026-01-01",
                    "org_id": "o",
                    "tenant_groups": ["t"],
                },
                {
                    "email": "dup@x",
                    "role": "viewer",
                    "active": True,
                    "last_login_at": "2027-01-01",
                    "org_id": "o",
                    "tenant_groups": ["t"],
                },
                {
                    "email": "dup@x",
                    "role": "admin",
                    "active": True,
                    "last_login_at": "2027-01-01",
                    "org_id": "o",
                    "tenant_groups": ["t"],
                },
            ]
        )
        + "\n"
    )
    _w(
        tmp_path,
        "keys.json",
        [
            {
                "key_id": "k2",
                "owner": "v@x",
                "owner_role": "viewer",
                "scopes": ["mcp:write"],
                "autonomy_ceiling": None,
                "last_used_at": None,
                "expires_at": None,
                "service": "pfactory",
            }
        ],
    )
    _w(
        tmp_path,
        "bindings.json",
        [
            {
                "name": "a",
                "kind": "ClusterRoleBinding",
                "subjects": [{"kind": "User", "name": "bob"}],
                "justification": "",
            },
            {
                "name": "b",
                "kind": "RoleBinding",
                "subjects": [{"kind": "Group", "name": "devs"}],
                "justification": "x",
            },
        ],
    )
    (tmp_path / "exceptions.json").unlink()
    f = _findings(tmp_path)
    for needle in (
        "gone@x",
        "DISABLED, no recorded login",
        "old@x",
        "dup@x (aifactory, org o): 2 role rows",
        "0 tenant groups",
        "owner is viewer but key holds mcp:write",
        "unused for ever",
        "no expiry",
        "null autonomy_ceiling",
        "no justification",
        "bound to a human (bob)",
        "assess members of group devs",
        "date not set",
    ):
        assert needle in f, needle


def test_token_shaped_input_is_refused(tmp_path: Path) -> None:
    _clean(tmp_path)
    (tmp_path / "keys.json").write_text('[{"note": "acw_ABCDEFGH12345678"}]')
    out = tmp_path / "review.md"
    assert ar.main(["--in", str(tmp_path), "--out", str(out), "--now", "2027-01-10"]) == 2
    assert not out.exists()


def test_escaped_token_is_refused(tmp_path: Path) -> None:
    _clean(tmp_path)
    (tmp_path / "keys.json").write_text('[{"note": "\\u0061cw_ABCDEFGH12345678"}]')
    (tmp_path / "members-pf.ndjson").write_text('{"email": "\\u0061cw_ABCDEFGH12345678"}\n')
    assert ar.build(tmp_path, NOW)[1] == 2
    (tmp_path / "keys.json").write_text("[]")
    assert ar.build(tmp_path, NOW)[1] == 2


def test_bare_read_scope_and_missing_groups_are_findings(tmp_path: Path) -> None:
    _clean(tmp_path)
    (tmp_path / "members-pfactory.ndjson").write_text(
        json.dumps({"email": "p@x", "role": "viewer", "active": True, "org_id": "o"}) + "\n"
    )
    _w(
        tmp_path,
        "keys.json",
        [
            {
                "key_id": "k3",
                "owner": "v@x",
                "owner_role": "viewer",
                "scopes": ["read"],
                "autonomy_ceiling": "low",
                "last_used_at": "2027-01-05",
                "expires_at": "2027-06-01",
                "service": "tf",
            }
        ],
    )
    f = _findings(tmp_path)
    assert "p@x (pfactory, org o): manual: tenant group not in export" in f
    assert "owner is viewer but key holds read" in f


def test_main_writes_review(tmp_path: Path) -> None:
    src = tmp_path / "in"
    src.mkdir()
    _clean(src)
    out = tmp_path / "review.md"
    assert ar.main(["--in", str(src), "--out", str(out), "--now", "2027-01-10"]) == 0
    text = out.read_text()
    assert "AR-005" in text and "2027-03-01" in text and "## Signature" in text
