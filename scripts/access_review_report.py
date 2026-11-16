#!/usr/bin/env python3
"""Draft the quarterly access review (Factory#312) from read-only exports.

Reads a directory of exports (see docs/compliance/access-review-runbook.md), runs
the runbook's checks and writes a draft ``review.md``. A missing input is a
finding, never a silent pass. If any input holds an ``acw_`` token shape the
script exits 2 and writes nothing, so a key value cannot reach the evidence
store. Stdlib only; the owner reviews and signs the output.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

STALE_DAYS = 90
TOKEN_SHAPE = re.compile(r"acw_[A-Za-z0-9]{8,}")
ROLES = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}
# Highest scope tier a role may hold: viewer reads only; member and above may write.
READ_ONLY_SCOPES = {"mcp:read", "read"}
FILES = (
    "keys.json",
    "cfactory-keys.json",
    "bindings.json",
    "keycloak-users.json",
    "platform-admins.json",
    "legacy-counters.json",
)


def _day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _age(value: str | None, now: date) -> int | None:
    d = _day(value)
    return None if d is None else (now - d).days


def _load(root: Path, name: str, findings: list[str]) -> Any:
    path = root / name
    if not path.is_file():
        findings.append(f"input not provided: {name}")
        return None
    return json.loads(path.read_text())


def _members(root: Path, findings: list[str]) -> list[dict[str, Any]]:
    files = sorted(root.glob("members-*.ndjson"))
    if not files:
        findings.append("input not provided: members-<service>.ndjson")
    out: list[dict[str, Any]] = []
    for f in files:
        for line in f.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                row["_svc"] = f.stem.removeprefix("members-")
                out.append(row)
    return out


def check_members(members: list[dict[str, Any]], now: date) -> list[str]:
    out: list[str] = []
    seen: dict[tuple[str, str, str], list[str]] = {}
    for m in members:
        who = f"{m.get('email')} ({m['_svc']}, org {m.get('org_id', 'n/a')})"
        role = str(m.get("role"))
        seen.setdefault((m["_svc"], str(m.get("org_id")), str(m.get("email"))), []).append(role)
        if ROLES.get(role, 0) > 0:
            age = _age(m.get("last_login_at"), now)
            state = "active" if m.get("active") else "DISABLED"
            if age is None:
                out.append(f"{who}: {role}, {state}, no recorded login")
            elif age > STALE_DAYS:
                out.append(f"{who}: {role}, {state}, last login {age} days ago")
        groups = m.get("tenant_groups")
        if groups is not None and len(groups) != 1:
            out.append(f"{who}: {len(groups)} tenant groups, expected exactly one")
    for (svc, org, email), roles in seen.items():
        if len(roles) > 1:
            out.append(
                f"{email} ({svc}, org {org}): {len(roles)} role rows "
                f"({', '.join(roles)}), expected one"
            )
    if members and not any("tenant_groups" in m for m in members):
        out.append("manual: tenant group not in export")
    return out


def check_keys(keys: list[dict[str, Any]], now: date) -> list[str]:
    out: list[str] = []
    for k in keys:
        who = f"key {k.get('key_id')} ({k.get('service')}, owner {k.get('owner')})"
        role = str(k.get("owner_role"))
        wide = [s for s in k.get("scopes") or [] if s not in READ_ONLY_SCOPES]
        if wide and ROLES.get(role, 0) == 0:
            out.append(f"{who}: owner is {role} but key holds {', '.join(wide)}")
        used = _age(k.get("last_used_at"), now)
        if used is None or used > STALE_DAYS:
            out.append(f"{who}: unused for {'ever' if used is None else f'{used} days'}")
        if not k.get("expires_at"):
            out.append(f"{who}: no expiry")
        if k.get("autonomy_ceiling") is None:
            out.append(f"{who}: null autonomy_ceiling")
    return out


def check_bindings(bindings: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for b in bindings:
        name = f"{b.get('kind')} {b.get('name')}"
        if not str(b.get("justification") or "").strip():
            out.append(f"{name}: no justification recorded")
        for s in b.get("subjects") or []:
            if s.get("kind") == "User":
                out.append(f"{name}: bound to a human ({s.get('name')})")
            elif s.get("kind") == "Group":
                out.append(f"{name}: manual: assess members of group {s.get('name')}")
    return out


def build(root: Path, now: date) -> tuple[str, int]:
    """Return (review.md text, exit code). Exit 2 means a token shape was found."""
    for f in root.iterdir():
        if f.is_file() and TOKEN_SHAPE.search(f.read_text(errors="replace")):
            return f"refused: {f.name} contains an acw_ token shape", 2
    findings: list[str] = []
    findings += check_members(_members(root, findings), now)
    keys = _load(root, "keys.json", findings)
    findings += check_keys(keys or [], now)
    cf = _load(root, "cfactory-keys.json", findings)
    bindings = _load(root, "bindings.json", findings)
    findings += check_bindings(bindings or [])
    kc = _load(root, "keycloak-users.json", findings)
    admins = _load(root, "platform-admins.json", findings)
    counters = _load(root, "legacy-counters.json", findings)
    exc_path = root / "exceptions.json"
    retire = (
        json.loads(exc_path.read_text()).get("wildcard_retirement_date")
        if exc_path.is_file()
        else None
    )
    if not retire:
        findings.append("APP_API_TOKEN / CFACTORY_MCP_SECRET retirement date: date not set")

    lines = [f"# Access review draft ({now.isoformat()})", "", "## Findings", ""]
    lines += [f"- {f}" for f in findings] or ["- none"]
    lines += ["", "## Evidence recorded", ""]
    lines += [
        f"- MFA {u.get('username')}: {u.get('mfa')} (enabled={u.get('enabled')}), record only"
        for u in kc or []
    ]
    lines += [f"- platform-admin {a.get('system')}: {a.get('account')}" for a in admins or []]
    lines += [f"- CFactory key {c.get('actor')}: {c.get('scope')}" for c in cf or []]
    lines += [f"- legacy counter {c.get('name')}: {c.get('count')}" for c in counters or []]
    lines += [
        "",
        "## Actions",
        "",
        "- (owner) one line per finding: revoke, accept with reason, or date.",
        "",
        "## Accepted exceptions",
        "",
        "- AR-004: the owner is sole reviewer and grantor (separation of duties).",
        "- AR-005: `APP_API_TOKEN` and `CFACTORY_MCP_SECRET` standing exception, retirement date: "
        f"{retire or 'not set'}.",
        "- MFA is recorded, not enforced.",
        "",
        "## Signature",
        "",
        "Reviewer / signer: ______________________  Date: __________",
        "",
    ]
    return "\n".join(lines), 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="src", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--now", required=True, help="review date, YYYY-MM-DD")
    args = ap.parse_args(argv)
    text, code = build(args.src, date.fromisoformat(args.now))
    if code:
        sys.stderr.write(text + "\n")
        return code
    args.out.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
