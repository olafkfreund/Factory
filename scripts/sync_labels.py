#!/usr/bin/env python3
"""Cross-tracker label sync for the Factory canonical label set (RFC-0011).

GitHub labels are reconciled by .github/workflows/label-sync.yml (an off-the-shelf
action). GitLab and Azure DevOps have no equivalent action, so this script creates
/ updates the same labels there via their REST APIs, behind the same `GitProvider`
abstraction AIFactory uses (`runners/github/providers`, with `GitProvider.create_label`
and `LabelData`).

Design goals:

  - **Self-contained + stdlib only** (urllib) so it runs anywhere, including CI,
    with no third-party deps and no need to import the AIFactory tree.
  - **Dry-run-able by default**: it prints exactly what it WOULD create/update and
    exits 0 without touching anything. `--apply` performs the writes. CI can run
    `--dry-run` (the default) with no credentials at all.
  - **Idempotent**: existing labels are updated to match (color/description),
    missing labels are created; nothing is deleted (pruning is a deliberate,
    out-of-band action).
  - **Single source of truth**: reads .github/labels.yml (the same manifest the
    GitHub action consumes). A tiny stdlib parser handles its simple list-of-maps
    shape so we need no PyYAML.

Provider abstraction
--------------------
`Provider` mirrors the relevant slice of AIFactory's `GitProvider` protocol:
`list_labels()` and `create_label(LabelData)` (plus an `update_label` since the
REST APIs distinguish create vs update). `GitLabProvider` and `AzureDevOpsProvider`
map those to each host's API exactly as the AIFactory providers do.

Usage
-----
  # Show what would change on GitLab (no creds needed; pure dry-run):
  python3 scripts/sync_labels.py --provider gitlab --project mygroup/myrepo

  # Actually create/update on GitLab:
  GITLAB_TOKEN=glpat-... python3 scripts/sync_labels.py \
      --provider gitlab --project mygroup/myrepo --apply

  # Azure DevOps (work-item tags act as labels):
  AZDO_TOKEN=... python3 scripts/sync_labels.py \
      --provider azure_devops \
      --org https://dev.azure.com/myorg --project MyProject --apply

Run the self-tests:  python3 scripts/sync_labels.py --selftest
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# factory-common is the deduped hub utility layer (epic Factory#154, issue
# Factory#161): the urllib JSON helper this script used to hand-roll as
# _http_json() now delegates to the shared HttpClient (the same primitive
# parr_regression.py consumes). The hub's scripts/ dir is flat (not an installed
# package), so the sibling shared/ package is added to the path the same way the
# test-suite imports the hub scripts.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared" / "factory-common"))

from factory_common.http import HttpClient, is_success

DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent / ".github" / "labels.yml"


# ---------------------------------------------------------------------------
# Data model (mirrors AIFactory providers/protocol.py::LabelData)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LabelData:
    name: str
    color: str  # 6-hex, no leading '#'
    description: str = ""

    def hex_color(self) -> str:
        """Return color as '#rrggbb' (GitLab wants the '#', GitHub does not)."""
        c = self.color.lstrip("#")
        return f"#{c}"


# ---------------------------------------------------------------------------
# Manifest parsing (minimal, stdlib-only — labels.yml is a simple list of maps)
# ---------------------------------------------------------------------------
def parse_manifest(text: str) -> list[LabelData]:
    """Parse the labels.yml subset we emit: a top-level list of
    {name, color, description} maps. Quotes optional; comments/blank lines skipped.

    This intentionally does NOT implement general YAML — it accepts exactly the
    shape this repo writes so the script has zero third-party dependencies.
    """
    labels: list[LabelData] = []
    cur: dict[str, str] = {}

    def _flush() -> None:
        if cur:
            labels.append(
                LabelData(
                    name=cur.get("name", ""),
                    color=cur.get("color", ""),
                    description=cur.get("description", ""),
                )
            )
            cur.clear()

    def _unquote(v: str) -> str:
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            return v[1:-1]
        return v

    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            # Start of a new list item; flush the previous one.
            _flush()
            stripped = stripped[2:].strip()
            if not stripped:
                continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            if key in ("name", "color", "description"):
                cur[key] = _unquote(val)
    _flush()
    return [lb for lb in labels if lb.name]


def load_manifest(path: Path = DEFAULT_MANIFEST) -> list[LabelData]:
    return parse_manifest(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Providers (slice of GitProvider: list_labels / create_label / update_label)
# ---------------------------------------------------------------------------
def _http_json(method: str, url: str, headers: dict, data: dict | None = None):
    """JSON request via the shared :class:`factory_common.http.HttpClient`.

    Behaviour-preserving wrapper over the deduped hub HTTP helper (epic
    Factory#154, issue Factory#161). As before: 30s timeout, the auth header the
    caller supplies (PRIVATE-TOKEN / Basic), Content-Type set automatically when a
    body is present, and the parsed JSON returned (or None for an empty body). The
    one difference from raw urllib is the Cloudflare-friendly default User-Agent
    the shared client adds, which is strictly additive for these API hosts.

    Failures raise: the original urlopen raised on any non-2xx / network error and
    these providers do not catch it (a sync error must fail loudly). The shared
    client returns a status instead of raising, so a non-2xx status (or the
    status-0 network failure) is re-raised here as a RuntimeError to keep the
    "fail loudly" contract.
    """
    client = HttpClient(auth=lambda: dict(headers), max_attempts=1, timeout=30)
    resp = client.request(method, url, body=data)
    if not is_success(resp.status):
        detail = resp.json.get("error") or resp.json
        raise RuntimeError(f"{method} {url} -> HTTP {resp.status}: {detail}")
    # A JSON array response (e.g. GitLab's list_labels) is wrapped as {"items": ...}
    # by the shared client; the providers expect the bare list back.
    if "items" in resp.json:
        return resp.json["items"]
    return resp.json


class Provider:
    """Abstract slice of AIFactory's GitProvider for label ops."""

    name = "abstract"

    def list_labels(self) -> list[LabelData]:  # pragma: no cover - interface
        raise NotImplementedError

    def create_label(self, label: LabelData) -> None:  # pragma: no cover
        raise NotImplementedError

    def update_label(self, label: LabelData) -> None:  # pragma: no cover
        raise NotImplementedError


class GitLabProvider(Provider):
    """Maps to GitLab Labels API (POST/PUT /projects/:id/labels).

    Mirrors AIFactory's GitLabProvider.create_label.
    """

    name = "gitlab"

    def __init__(self, project: str, token: str, base_url: str = "https://gitlab.com"):
        self.project = urllib.parse.quote(project, safe="")
        self.token = token
        self.base = base_url.rstrip("/")

    def _headers(self) -> dict:
        return {"PRIVATE-TOKEN": self.token}

    def _url(self, suffix: str = "") -> str:
        return f"{self.base}/api/v4/projects/{self.project}/labels{suffix}"

    def list_labels(self) -> list[LabelData]:
        out: list[LabelData] = []
        page = 1
        while True:
            url = self._url(f"?per_page=100&page={page}")
            rows = _http_json("GET", url, self._headers()) or []
            for r in rows:
                out.append(
                    LabelData(
                        name=r.get("name", ""),
                        color=(r.get("color") or "").lstrip("#"),
                        description=r.get("description") or "",
                    )
                )
            if len(rows) < 100:
                break
            page += 1
        return out

    def create_label(self, label: LabelData) -> None:
        _http_json(
            "POST",
            self._url(),
            self._headers(),
            {
                "name": label.name,
                "color": label.hex_color(),
                "description": label.description,
            },
        )

    def update_label(self, label: LabelData) -> None:
        # GitLab updates by name via query param.
        url = self._url(f"/{urllib.parse.quote(label.name, safe='')}")
        _http_json(
            "PUT",
            url,
            self._headers(),
            {"new_color": label.hex_color(), "description": label.description},
        )


class AzureDevOpsProvider(Provider):
    """Azure DevOps has no first-class repo labels; work-item *tags* are the
    equivalent (and AIFactory's AzureDevOpsProvider treats them as labels).

    Tags are created lazily when first applied to a work item, so there is no
    bulk "create label" endpoint. This provider documents/creates them via the
    tagging API where supported and otherwise reports them as "ensure-on-apply".
    """

    name = "azure_devops"

    def __init__(self, org: str, project: str, token: str):
        self.org = org.rstrip("/")
        self.project = project
        self.token = token

    def _headers(self) -> dict:
        # ADO uses Basic auth with an empty username + PAT.
        pat = base64.b64encode(f":{self.token}".encode()).decode()
        return {"Authorization": f"Basic {pat}"}

    def _url(self, suffix: str) -> str:
        return f"{self.org}/{self.project}/_apis/{suffix}"

    def list_labels(self) -> list[LabelData]:
        # Work Item Tags - List (api-version 7.1-preview.1).
        url = self._url("wit/tags?api-version=7.1-preview.1")
        rows = (_http_json("GET", url, self._headers()) or {}).get("value", [])
        return [LabelData(name=r.get("name", ""), color="ededed") for r in rows]

    def create_label(self, label: LabelData) -> None:
        # Work Item Tags - Create.
        url = self._url("wit/tags?api-version=7.1-preview.1")
        _http_json("POST", url, self._headers(), {"name": label.name})

    def update_label(self, label: LabelData) -> None:
        # Tags carry no color/description in ADO; nothing to update.
        return None


# ---------------------------------------------------------------------------
# Sync engine
# ---------------------------------------------------------------------------
@dataclass
class Plan:
    create: list[LabelData]
    update: list[LabelData]
    unchanged: list[LabelData]


def diff_labels(desired: Iterable[LabelData], existing: Iterable[LabelData]) -> Plan:
    by_name = {lb.name: lb for lb in existing}
    create, update, unchanged = [], [], []
    for want in desired:
        have = by_name.get(want.name)
        if have is None:
            create.append(want)
        elif (have.color.lstrip("#").lower() != want.color.lstrip("#").lower()) or (
            (have.description or "") != (want.description or "")
        ):
            update.append(want)
        else:
            unchanged.append(want)
    return Plan(create=create, update=update, unchanged=unchanged)


def render_plan(plan: Plan, provider_name: str, apply: bool) -> str:
    verb = "APPLYING" if apply else "DRY-RUN (no changes)"
    lines = [f"[{provider_name}] {verb}"]
    for lb in plan.create:
        lines.append(f"  + create  {lb.name:<22} #{lb.color}  {lb.description}")
    for lb in plan.update:
        lines.append(f"  ~ update  {lb.name:<22} #{lb.color}  {lb.description}")
    for lb in plan.unchanged:
        lines.append(f"  = ok      {lb.name}")
    lines.append(
        f"  -> {len(plan.create)} to create, {len(plan.update)} to update, "
        f"{len(plan.unchanged)} unchanged"
    )
    return "\n".join(lines)


def sync(provider: Provider, desired: list[LabelData], apply: bool) -> Plan:
    existing = provider.list_labels() if apply else []
    # In dry-run with no creds we cannot read existing labels; treat all as "create"
    # so the operator sees the full intended set. With --apply we diff for real.
    plan = diff_labels(desired, existing)
    if apply:
        for lb in plan.create:
            provider.create_label(lb)
        for lb in plan.update:
            provider.update_label(lb)
    return plan


def build_provider(args) -> Provider:
    if args.provider == "gitlab":
        token = os.environ.get("GITLAB_TOKEN", "")
        if args.apply and not token:
            sys.exit("error: --apply on gitlab requires GITLAB_TOKEN")
        return GitLabProvider(
            project=_require(args, "project"),
            token=token,
            base_url=args.base_url or "https://gitlab.com",
        )
    if args.provider == "azure_devops":
        token = os.environ.get("AZDO_TOKEN", "")
        if args.apply and not token:
            sys.exit("error: --apply on azure_devops requires AZDO_TOKEN")
        return AzureDevOpsProvider(
            org=_require(args, "org"),
            project=_require(args, "project"),
            token=token,
        )
    sys.exit(f"error: unknown provider {args.provider!r}")


def _require(args, field: str):
    val = getattr(args, field, None)
    if not val:
        sys.exit(f"error: --{field} is required for provider {args.provider}")
    return val


# ---------------------------------------------------------------------------
# Self-tests (no network)
# ---------------------------------------------------------------------------
def _selftest() -> int:
    labels = load_manifest()
    names = {lb.name for lb in labels}
    for required in (
        "factory:low",
        "factory:medium",
        "factory:hard",
        "factory:queued",
        "factory:failed",
    ):
        assert required in names, f"manifest missing {required}"
    low = next(lb for lb in labels if lb.name == "factory:low")
    assert low.color and low.description, "factory:low must have color + description"
    assert low.hex_color().startswith("#"), "hex_color must add '#'"

    # diff: create when absent, update on color change, ok when identical.
    desired = [LabelData("a", "ff0000", "x"), LabelData("b", "00ff00", "y")]
    existing = [LabelData("a", "0000ff", "x")]  # 'a' differs by color, 'b' missing
    plan = diff_labels(desired, existing)
    assert [lb.name for lb in plan.create] == ["b"], plan.create
    assert [lb.name for lb in plan.update] == ["a"], plan.update
    assert not plan.unchanged

    plan2 = diff_labels([LabelData("a", "0000ff", "x")], existing)
    assert plan2.unchanged and not plan2.create and not plan2.update

    print(f"selftest OK ({len(labels)} labels parsed, diff logic verified)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Sync Factory labels to GitLab / Azure DevOps (RFC-0011)."
    )
    ap.add_argument("--provider", choices=["gitlab", "azure_devops"])
    ap.add_argument("--project", help="GitLab project path or ADO project name")
    ap.add_argument("--org", help="ADO org URL, e.g. https://dev.azure.com/myorg")
    ap.add_argument("--base-url", help="GitLab base URL (default https://gitlab.com)")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Perform writes (default is dry-run)")
    group.add_argument(
        "--dry-run", action="store_true", help="Print intended changes only (default)"
    )
    ap.add_argument("--selftest", action="store_true", help="Run offline self-tests and exit")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.provider:
        ap.error("--provider is required (or use --selftest)")

    desired = load_manifest(Path(args.manifest))
    provider = build_provider(args)
    plan = sync(provider, desired, apply=args.apply)
    print(render_plan(plan, provider.name, apply=args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
