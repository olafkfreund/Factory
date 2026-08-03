#!/usr/bin/env python3
"""Are the baked agent-CLI pins drifting behind npm? (Factory#459)

The three agent CLIs are pinned in each service's Dockerfile and baked into the
runtime image (TFactory#791). NOTHING proposes bumps for them: the Renovate
GitHub App is not installed on this account — zero Renovate PRs across all five
repos, ever — and Dependabot's docker ecosystem parses only ``FROM`` lines, so it
cannot see an ``npm install -g @pkg@version`` bake step. factory-gitops'
``renovate.json`` records both facts and says so plainly; its own customManager
has matched nothing since the pins moved out of the manifests.

THE FAILURE MODE THIS CONVERTS INTO A SIGNAL. "No bump PRs" and "nothing to
update" look identical from outside, which is why the same gap sat unnoticed for
nine weeks in Factory#436. A freshness assertion cannot be silently not-running:
if it stops, CI goes red. That is the property option 3 of Factory#459 has and
the other two do not, and it is why this exists even though installing the
Renovate App (option 1) would be the fuller fix — they are complementary, and
only one of them can be done without account-level authorisation.

WHY A SCHEDULED HUB WATCHDOG AND NOT A PER-REPO TEST, which is the opposite call
from Factory#552 and deliberately so. A pull request does not make a pin stale;
TIME does. A pre-merge test would fail PRs for something the PR did not cause,
which is the cry-wolf shape that gets a gate muted (Factory#538). Staleness is
watched out of band, on a clock, like every other drift here.

REPORTS DRIFT, DOES NOT FIX IT. Bumping a CLI belongs in the service repo behind
its own canary run — a broken upstream release must not reach the fleet on the
next pod start because a bot merged it unattended.

Usage:
    python3 scripts/check_cli_freshness.py                 # live, needs network
    python3 scripts/check_cli_freshness.py --max-age-days 45
    python3 scripts/check_cli_freshness.py --self-test     # offline

Exit codes:
    0 - every pin is within the window (or ahead of the registry)
    1 - a pin has been behind the registry for longer than the window
    2 - a pin or a registry entry could not be read (never a silent pass:
        a check that cannot see its subject must say so, Factory#500)
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from selftest_report import SelfTest, gate_argparser

_OWNER = "olafkfreund"
_RAW = "https://raw.githubusercontent.com/{owner}/{repo}/HEAD/Dockerfile"
_REGISTRY = "https://registry.npmjs.org/{pkg}"

# Repos that bake the agent CLIs. CFactory is deliberately absent: it is the
# cockpit and runs no agent, so it pins none of these — an absence with a reason,
# which is what Factory#401 removed dead config for stating any other way.
REPOS: tuple[str, ...] = ("AIFactory", "PFactory", "TFactory")

# The pins, as they appear in the bake step:  @scope/name@1.2.3
_PIN_RE = re.compile(r"(@[\w.-]+/[\w.-]+)@(\d+\.\d+\.\d+[^\s\\\"']*)")

# Only these three are tracked. Matching every `@scope/pkg@version` in a
# Dockerfile would sweep in build-time tooling whose version is deliberately
# frozen, and a watchdog that reports things nobody intends to bump is the noise
# that gets a real alert muted.
TRACKED: tuple[str, ...] = (
    "@anthropic-ai/claude-code",
    "@openai/codex",
    "@google/gemini-cli",
)

# How far behind the registry a pin may fall before it is an alert. Generous on
# purpose: these CLIs ship every few days, so a tight window would be red
# permanently and mean nothing (Factory#538). A month behind is neglect; a week
# behind is Tuesday.
_DEFAULT_MAX_AGE_DAYS = 30.0

_EXIT_BAD_INVOCATION = 2


class SourceUnavailableError(RuntimeError):
    """A Dockerfile or registry entry could not be read. Never a pass."""


@dataclass(frozen=True)
class Pin:
    repo: str
    package: str
    version: str


def parse_pins(repo: str, dockerfile: str) -> list[Pin]:
    """The tracked CLI pins declared in *dockerfile*."""
    found = {pkg: ver for pkg, ver in _PIN_RE.findall(dockerfile) if pkg in TRACKED}
    return [Pin(repo, pkg, found[pkg]) for pkg in TRACKED if pkg in found]


def fetch_dockerfile(repo: str, *, timeout: int = 20) -> str:
    url = _RAW.format(owner=_OWNER, repo=repo)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            body: str = response.read().decode("utf-8")
            return body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceUnavailableError(f"{repo}: cannot fetch {url}: {exc}") from exc


def fetch_registry(package: str, *, timeout: int = 30) -> dict[str, Any]:
    url = _REGISTRY.format(pkg=package.replace("/", "%2f"))
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            doc: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            return doc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise SourceUnavailableError(f"{package}: cannot read the npm registry: {exc}") from exc


def _published(doc: dict[str, Any], version: str) -> datetime | None:
    stamp = (doc.get("time") or {}).get(version)
    if not stamp:
        return None
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def assess(
    pin: Pin, doc: dict[str, Any], *, now: datetime, max_age_days: float
) -> tuple[str, str | None]:
    """``(report_line, failure_or_None)`` for one pin against the registry.

    The age measured is of the LATEST release, not of the pinned one: the
    question is "how long has a newer version been available and ignored", which
    is what a missing bot causes. A pin published long ago but still latest is
    not stale — it is simply a package that has not moved.
    """
    latest = (doc.get("dist-tags") or {}).get("latest")
    if not latest:
        raise SourceUnavailableError(f"{pin.package}: registry has no dist-tags.latest")
    if latest == pin.version:
        return f"  {pin.repo}/{pin.package} {pin.version} — current", None
    released = _published(doc, latest)
    if released is None:
        # Newer version exists but the registry gave no date. Report it rather
        # than skip it: an unmeasurable age is not the same as being current.
        return (
            f"  {pin.repo}/{pin.package} {pin.version} — behind {latest} (release date unknown)",
            f"{pin.repo}: {pin.package} pinned {pin.version}, latest {latest}, "
            "publish date unreadable",
        )
    age = (now - released).total_seconds() / 86400.0
    line = f"  {pin.repo}/{pin.package} {pin.version} — behind {latest}, published {age:.0f}d ago"
    if age > max_age_days:
        return line, (
            f"{pin.repo}: {pin.package} pinned {pin.version}; {latest} has been "
            f"available for {age:.0f} days (window {max_age_days:.0f})"
        )
    return line, None


def _selftest() -> int:
    t = SelfTest("cli-freshness")
    now = datetime(2026, 8, 3, tzinfo=UTC)

    dockerfile = (
        "RUN npm install -g \\\n"
        "        @anthropic-ai/claude-code@2.1.215 \\\n"
        "        @openai/codex@0.144.6 \\\n"
        "        @google/gemini-cli@0.51.0\n"
        "RUN npm install -g @some/unrelated-tool@9.9.9\n"
    )
    pins = parse_pins("AIFactory", dockerfile)
    t.req(len(pins) == len(TRACKED), f"all tracked pins parsed (got {len(pins)})")
    t.req(
        all(p.package in TRACKED for p in pins),
        "an untracked package in the same bake step is ignored",
    )

    def doc(latest: str, when: str) -> dict[str, Any]:
        return {"dist-tags": {"latest": latest}, "time": {latest: when}}

    pin = Pin("AIFactory", "@openai/codex", "0.144.6")
    line, fail = assess(pin, doc("0.144.6", "2026-01-01T00:00:00Z"), now=now, max_age_days=30)
    t.req(fail is None, "a pin equal to latest is current, however old the release")

    line, fail = assess(pin, doc("0.146.0", "2026-07-29T00:00:00Z"), now=now, max_age_days=30)
    t.req(fail is None, "5 days behind is within a 30-day window")
    t.req("behind 0.146.0" in line, "the report names the newer version, not just a verdict")

    line, fail = assess(pin, doc("0.146.0", "2026-05-01T00:00:00Z"), now=now, max_age_days=30)
    t.req(fail is not None, "94 days behind is an alert (THE CASE WITH TEETH)")
    t.req(fail is not None and "0.146.0" in fail, "the failure names what to bump to")

    _, fail = assess(pin, doc("0.146.0", "2026-07-29T00:00:00Z"), now=now, max_age_days=0)
    t.req(fail is not None, "window=0 alerts immediately — the window is the only excuse")

    _, fail = assess(
        pin, {"dist-tags": {"latest": "0.146.0"}, "time": {}}, now=now, max_age_days=30
    )
    t.req(fail is not None, "a newer version with no publish date is reported, not skipped")

    t.req(
        set(TRACKED)
        == {
            "@anthropic-ai/claude-code",
            "@openai/codex",
            "@google/gemini-cli",
        },
        "the tracked set is enumerated, so narrowing it is visible",
    )
    t.req("CFactory" not in REPOS, "CFactory bakes no agent CLI and is deliberately absent")
    return t.finish()


def main(argv: list[str] | None = None) -> int:
    ap = gate_argparser(__doc__)
    ap.add_argument(
        "--max-age-days",
        type=float,
        default=_DEFAULT_MAX_AGE_DAYS,
        help=f"how long a newer release may sit unadopted (default {_DEFAULT_MAX_AGE_DAYS:.0f})",
    )
    args = ap.parse_args(argv)

    if args.self_test:
        return _selftest()

    now = datetime.now(UTC)
    report: list[str] = []
    failures: list[str] = []
    try:
        registry = {pkg: fetch_registry(pkg) for pkg in TRACKED}
        for repo in REPOS:
            pins = parse_pins(repo, fetch_dockerfile(repo))
            if not pins:
                failures.append(
                    f"{repo}: no tracked CLI pin found in its Dockerfile. Either the bake "
                    "step moved again (as TFactory#791 moved it out of the manifests) or "
                    "this watchdog is now looking in the wrong place — both mean it is "
                    "checking nothing here."
                )
                continue
            report.append(f"{repo}:")
            for pin in pins:
                line, failure = assess(
                    pin, registry[pin.package], now=now, max_age_days=args.max_age_days
                )
                report.append(line)
                if failure:
                    failures.append(failure)
    except SourceUnavailableError as exc:
        sys.stderr.write(f"cli-freshness: {exc}\n")
        return _EXIT_BAD_INVOCATION

    print("\n".join(report))  # noqa: T201
    print(  # noqa: T201
        f"\nTracked: {', '.join(TRACKED)} across {', '.join(REPOS)}; "
        f"window {args.max_age_days:.0f} days."
    )
    if failures:
        print("\ncli-freshness FAILED:")  # noqa: T201
        for line in failures:
            print(f"  {line}")  # noqa: T201
        print(  # noqa: T201
            "\nBump the pin in that service's Dockerfile and let its cli-canary run "
            "before merging. Nothing proposes these automatically: the Renovate App is "
            "not installed and Dependabot cannot see an `npm install -g` bake step "
            "(Factory#459)."
        )
        return 1
    print("\ncli-freshness PASSED: every pinned agent CLI is within the window.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
