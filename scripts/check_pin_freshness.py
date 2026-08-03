#!/usr/bin/env python3
"""Is any service gating against a canonical that has since moved? (Factory#519)

Each consumer's ``verification-core-drift.yml`` answers one question: *does my
vendored copy match my pin?* Nothing anywhere answers the next one: *is my pin
still the current canonical?* A service can sit arbitrarily far behind with a
permanently green gate, because a byte comparison against a stale target is
honestly green — the same shape as Factory#499, a control green against the
wrong thing.

WHY NOT COMPARE THE PINS TO EACH OTHER. That was the obvious reading of #519 and
it is the wrong check: it reports a service as broken for being different, and
being different is frequently correct. CFactory vendors exactly ONE canonical
module; the other three vendor three to six. When a re-vendor moves a file
CFactory does not carry, CFactory's pin legitimately stays put and pin-equality
flags it. Measured on the fleet at the time this was written: CFactory sat two
commits behind, zero of them touching the module it vendors.

The property that actually matters is per-service and answerable from the hub
alone: *for the modules THIS service vendors, has the canonical moved since its
pin?* Behind-but-unaffected is a pass and is reported as such. Behind on a file
you actually carry is a fail, and the commits that did it are named.

That distinction is not academic. It is exactly the history #519 could not
resolve:

    a9f44033..d9bd01de   32 hub commits, 0 touching scripts/ratchet_helpers.py
                         -> CFactory was HONESTLY GREEN when #519 was filed.
    a9f44033..e077134    +1 touching it (Factory#536, two days later)
                         -> the same pin became REAL staleness, silently.

Nobody would have been told. That gap is what this closes.

SERVICE_LAYOUTS is imported, never restated: it is the fleet's map of who
vendors what, and a second copy of it here would be the hand-maintained fork
Factory#483 exists to undo. A service added there is checked here automatically.

Reporting follows docs/dev/gate-honesty.md: every verdict carries the evidence it
was derived from, and the commit list is EMITTED rather than counted — "3 commits
behind" is a number nobody re-derives, and a scope loss hides inside it.

Usage:
    # Fetch every service's live pin and check it (needs network; public repos,
    # no token):
    python3 scripts/check_pin_freshness.py

    # Offline / hypothetical: supply pins explicitly, repeatable.
    python3 scripts/check_pin_freshness.py --pin cfactory=a9f44033 --no-fetch

    # Built-in self-test (no network, no repo state beyond this checkout):
    python3 scripts/check_pin_freshness.py --self-test

Exit codes:
    0 - every service's pin is current for the modules it vendors
    1 - at least one service is gating against a moved canonical (or self-test
        failed)
    2 - bad invocation, or a pin could not be read (never a silent pass: a check
        that cannot see its subject must say so, Factory#500)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_verification_core_drift import SERVICE_LAYOUTS

# Where each service's pin lives. One workflow file per repo, and the pin is a
# SHA embedded in its `env:` block — the very property Factory#514 is about. If
# that ever becomes a pin FILE, only this mapping changes.
_PIN_WORKFLOW = ".github/workflows/verification-core-drift.yml"
_PIN_RE = re.compile(r'^\s*HUB_PIN_SHA:\s*"([0-9a-fA-F]{7,40})"', re.MULTILINE)

# service key in SERVICE_LAYOUTS -> GitHub repo name.
_REPOS: dict[str, str] = {
    "pfactory": "PFactory",
    "aifactory": "AIFactory",
    "tfactory": "TFactory",
    "cfactory": "CFactory",
}

_OWNER = "olafkfreund"
# HEAD resolves to the repo's default branch, so this does not hardcode `dev`.
_RAW = "https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{path}"

_EXIT_BAD_INVOCATION = 2

# How long a moved canonical may sit unpropagated before it counts as staleness.
# 24h matches check_branch_divergence.py's unpromoted budget: both are measuring
# "a change landed and the rest of the fleet has not caught up", and two
# different answers to that question would be a distinction without a reason.
_DEFAULT_BUDGET_HOURS = 24.0


class PinUnavailableError(RuntimeError):
    """A service's pin could not be read. Never downgraded to a pass."""


def fetch_workflow(repo: str, *, timeout: int = 20) -> str:
    """*repo*'s drift workflow as text, from its default branch.

    Raises :class:`PinUnavailableError` rather than returning a sentinel. A gate
    that treats "I could not look" as "nothing wrong" is the Factory#500 shape.
    """
    url = _RAW.format(owner=_OWNER, repo=repo, path=_PIN_WORKFLOW)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            # Bound to a declared str rather than returned straight: urlopen's
            # result is untyped, so returning it directly is `Any` escaping a
            # function annotated -> str, which the mypy ratchet blocks.
            body: str = response.read().decode("utf-8")
            return body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PinUnavailableError(f"{repo}: cannot fetch {url}: {exc}") from exc


def pin_from(repo: str, body: str) -> str:
    """The ``HUB_PIN_SHA`` declared in *body*."""
    match = _PIN_RE.search(body)
    if match is None:
        raise PinUnavailableError(f"{repo}: no HUB_PIN_SHA found in {_PIN_WORKFLOW}")
    return match.group(1)


def fetch_pin(repo: str, *, timeout: int = 20) -> str:
    """The live ``HUB_PIN_SHA`` from *repo*'s drift workflow."""
    return pin_from(repo, fetch_workflow(repo, timeout=timeout))


def trigger_filter_problem(repo: str, body: str) -> str | None:
    """A ``paths:`` filter on the drift gate's ``pull_request`` trigger, if any.

    This job is a REQUIRED status check in all four consumers (Factory#543), and
    a path-filtered workflow does not report a "skipped" context — it reports
    NOTHING. A required context that never reports blocks the pull request
    forever, so re-adding the filter that Factory#525 removed would wedge every
    PR in that repo, not merely skip a check.

    The hub already asserts this about its own workflows offline
    (tests/test_branch_protection_intent.py::test_code_quality_is_not_path_filtered,
    Factory#529 — the same wedge, discovered the hard way). It cannot assert it
    about four other repos, and this watchdog is already fetching exactly those
    files every day, so the claim is checked where the evidence is.

    Deliberately textual rather than a YAML parse: this module is pure stdlib by
    contract (no PyYAML anywhere in the hub's runtime deps), and the question —
    "is there a paths: key inside the pull_request block" — does not need a
    parser. The block is delimited by the next top-level trigger key.
    """
    trigger = body.split("jobs:", 1)[0]
    if "pull_request:" not in trigger:
        return f"{repo}: the drift gate has no pull_request trigger, so it cannot gate a PR"
    section = trigger.split("pull_request:", 1)[1]
    for following in ("\n  push:", "\n  schedule:", "\n  workflow_dispatch:"):
        if following in section:
            section = section.split(following, 1)[0]
    if re.search(r"^\s+paths(-ignore)?:", section, re.MULTILINE):
        return (
            f"{repo}: the drift gate's pull_request trigger is path-filtered again. "
            "It is a REQUIRED check, and a filtered workflow reports nothing rather "
            "than skipped — every PR that does not match is blocked forever "
            "(Factory#525 removed this filter, Factory#543 made it required)"
        )
    return None


def canonical_paths(service: str) -> list[str]:
    """Hub paths of the canonical modules *service* vendors.

    The canonical for every verification-core module is ``scripts/<module>`` in
    the hub; the service-side path in SERVICE_LAYOUTS is where the COPY lives and
    is irrelevant here — this asks what moved upstream.
    """
    return [f"scripts/{module}" for module in sorted(SERVICE_LAYOUTS[service])]


def _git(*args: str) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )
    if result.returncode != 0:
        raise PinUnavailableError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def commits_since(pin: str, paths: list[str], until: str = "HEAD") -> list[tuple[str, int]]:
    """Hub commits after *pin* touching any of *paths*, as ``(subject, epoch)``.

    Newest first. The commit time comes back with the subject because the verdict
    needs the AGE, not just the count — see :func:`check`.

    *until* exists so the same question can be asked of a past state, which is
    the only way to express "was this pin honest AT THE TIME" — the fact #519
    could not settle. Production always asks it of ``HEAD``.
    """
    out = _git("log", "--pretty=format:%h %ct %s", "--no-decorate", f"{pin}..{until}", "--", *paths)
    rows: list[tuple[str, int]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, _, rest = line.partition(" ")
        epoch, _, subject = rest.partition(" ")
        rows.append((f"{sha} {subject}", int(epoch)))
    return rows


def total_behind(pin: str) -> int:
    """How many hub commits *pin* is behind overall (context, not a verdict)."""
    return len([ln for ln in _git("rev-list", f"{pin}..HEAD").splitlines() if ln.strip()])


def scope_problems() -> list[str]:
    """Ways this gate could quietly stop covering a service.

    Checked BEFORE any pin is read, because the failure it guards against is
    silent scope loss (docs/dev/gate-honesty.md variant 3): a service dropped
    from :data:`SERVICE_LAYOUTS` would otherwise just stop being examined, and
    fewer services checked reads exactly like nothing wrong. Factory#523 is the
    same shape one level down — a MODULE dropped from a layout — and is caught by
    the stray-copy scan in check_verification_core_drift.py.

    Reported as a list rather than raising, so every problem surfaces at once and
    the reader can falsify it at a glance.
    """
    problems: list[str] = []
    for service in sorted(set(SERVICE_LAYOUTS) - set(_REPOS)):
        problems.append(
            f"{service} is in SERVICE_LAYOUTS but has no repo mapping here, "
            "so its pin is never checked"
        )
    for service in sorted(set(_REPOS) - set(SERVICE_LAYOUTS)):
        problems.append(
            f"{service} has a repo mapping here but is absent from SERVICE_LAYOUTS, "
            "so there is nothing to check it against"
        )
    return problems


def _hours(now: int, epoch: int) -> float:
    return (now - epoch) / 3600.0


def check(
    pins: dict[str, str], *, now: int, budget_hours: float = _DEFAULT_BUDGET_HOURS
) -> tuple[list[str], list[str]]:
    """Verdicts for *pins* as ``(failures, report_lines)``.

    Every service produces report lines whether it passes or fails, and a failing
    service names the commits that moved its canonical. Per
    docs/dev/gate-honesty.md the modules are ENUMERATED rather than counted: a
    reader can falsify a list at a glance and cannot falsify a number at all.

    WHY A TIME BUDGET. A canonical change lands in the hub before any consumer
    can possibly have re-vendored it — the re-vendor PR needs a merged hub commit
    to pin. Without a grace window this watchdog is red by construction for
    however long propagation takes, every single time, which is precisely the
    train-people-to-ignore-it failure Factory#538 was about. A module that moved
    within *budget_hours* is reported as PROPAGATING and does not fail; past that
    it is staleness that nobody is acting on.
    """
    failures: list[str] = []
    report: list[str] = []
    for service in sorted(pins):
        pin = pins[service]
        modules = sorted(SERVICE_LAYOUTS[service])
        moved = commits_since(pin, canonical_paths(service))
        behind = total_behind(pin)
        report.append(f"{service}: pin {pin[:8]}, {behind} hub commit(s) behind overall")
        report.append(f"  vendors: {', '.join(modules)}")
        if not moved:
            # The behind-but-honest case, stated positively so a reader can see
            # the gate looked and why it passed.
            report.append("  none of those commits touch a module it vendors - honestly green")
            continue
        # Oldest unpropagated commit decides: one file left behind for a week is
        # not excused by a fresh one landing today.
        oldest = min(epoch for _, epoch in moved)
        age = _hours(now, oldest)
        report.append("  MOVED SINCE THE PIN:")
        report.extend(f"    {_hours(now, epoch):6.1f}h  {subject}" for subject, epoch in moved)
        if age > budget_hours:
            failures.append(
                f"{service} is gating against a moved canonical: {len(moved)} commit(s) "
                f"since pin {pin[:8]} touch its modules, oldest {age:.0f}h "
                f"(budget {budget_hours:.0f}h)"
            )
        else:
            report.append(
                f"  PROPAGATING: oldest is {age:.1f}h old, within the "
                f"{budget_hours:.0f}h budget - not yet an alert"
            )
    return failures, report


def _selftest() -> int:
    """Historical pins with known answers, so the check is observed FAILING.

    Every case is a real hub commit and a real service layout, so these assert
    the verdict rather than the plumbing. The first is the one with teeth: a pin
    that is far behind and STILL correct must not be reported as stale, because
    a check that flags every difference is the pin-equality check this file
    exists instead of.
    """
    failed = 0

    def req(ok: bool, label: str) -> None:
        nonlocal failed
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")  # noqa: T201
        failed += not ok

    # Scope FIRST. Everything below indexes SERVICE_LAYOUTS, so a scope loss
    # would otherwise surface as a KeyError traceback from a later case rather
    # than as the thing that is actually wrong.
    problems = scope_problems()
    req(not problems, f"every service is covered ({'; '.join(problems) or 'no gaps'})")
    if problems:
        print("pin-freshness self-test: FAILED (scope)")  # noqa: T201
        return 1

    # 32 commits behind, none touching scripts/ratchet_helpers.py: the exact
    # state Factory#519 reported and could not resolve. Must be a PASS.
    old = "a9f44033dbb041d8a1468226c6325ea1f175a264"
    then = "d9bd01de01c357886234dd5f23a546d5799e4e97"
    behind_then = _git("log", "--oneline", f"{old}..{then}", "--", "scripts/ratchet_helpers.py")
    req(
        behind_then.strip() == "", "far behind but untouched module reads as fresh (#519 at filing)"
    )

    # The same pin AFTER Factory#536 moved that module: must now be a failure.
    # `now` is fixed far in the future so the budget cannot mask the verdict.
    far_future = int(_git("log", "-1", "--pretty=format:%ct").strip()) + 10 * 86400
    fails, _ = check({"cfactory": old}, now=far_future)
    req(bool(fails), "the same pin is stale once the canonical moves (teeth)")

    # ...and the budget must actually hold it back while it is fresh. Without
    # this case a budget of infinity would pass every other test here.
    moved_at = min(e for _, e in commits_since(old, canonical_paths("cfactory")))
    fails, report = check({"cfactory": old}, now=moved_at + 3600)
    req(not fails, "a canonical that moved an hour ago is PROPAGATING, not stale")
    req(
        any("PROPAGATING" in line for line in report),
        "the propagating state is reported, not silent",
    )
    fails, _ = check({"cfactory": old}, now=moved_at + 3600, budget_hours=0)
    req(bool(fails), "budget=0 fails immediately (the budget is the only thing excusing it)")

    # A current pin must be clean, and the report must ENUMERATE the modules
    # rather than count them (docs/dev/gate-honesty.md).
    head = _git("rev-parse", "HEAD").strip()
    fails, report = check({"cfactory": head}, now=far_future)
    req(not fails, "a pin at HEAD is fresh")
    req(
        any("ratchet_helpers.py" in line for line in report), "report names the module, not a count"
    )

    print("pin-freshness self-test: " + ("PASSED" if not failed else f"FAILED ({failed})"))  # noqa: T201
    return 1 if failed else 0


def _gather(
    overrides: dict[str, str], *, no_fetch: bool, on_missing: Callable[[str], object]
) -> tuple[dict[str, str], list[str]]:
    """Each service's pin, plus any trigger problem, from ONE fetch per repo."""
    pins: dict[str, str] = {}
    problems: list[str] = []
    for service, repo in _REPOS.items():
        if service in overrides:
            pins[service] = overrides[service]
            continue
        if no_fetch:
            on_missing(f"--no-fetch given but no --pin for {service}")
            continue
        body = fetch_workflow(repo)
        pins[service] = pin_from(repo, body)
        problem = trigger_filter_problem(repo, body)
        if problem is not None:
            problems.append(problem)
    return pins, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run the built-in self-test and exit"
    )
    parser.add_argument(
        "--pin",
        action="append",
        default=[],
        metavar="SERVICE=SHA",
        help="override a service's pin (repeatable); implies that service is not fetched",
    )
    parser.add_argument(
        "--grace-hours",
        type=float,
        default=_DEFAULT_BUDGET_HOURS,
        help=f"hours a moved canonical may sit unpropagated (default {_DEFAULT_BUDGET_HOURS:.0f})",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="do not reach the network; every service must then be given a --pin",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return _selftest()

    # Before anything else: is this gate still covering everyone it should?
    problems = scope_problems()
    if problems:
        sys.stderr.write("pin-freshness: the gate's own scope is broken:\n")
        for line in problems:
            sys.stderr.write(f"  {line}\n")
        return _EXIT_BAD_INVOCATION

    overrides: dict[str, str] = {}
    for item in args.pin:
        service, _, sha = item.partition("=")
        if not sha or service not in SERVICE_LAYOUTS:
            parser.error(f"--pin expects SERVICE=SHA with a known service, got {item!r}")
        overrides[service] = sha

    try:
        pins, trigger_problems = _gather(overrides, no_fetch=args.no_fetch, on_missing=parser.error)
    except PinUnavailableError as exc:
        sys.stderr.write(f"pin-freshness: {exc}\n")
        return _EXIT_BAD_INVOCATION

    failures, report = check(pins, now=int(time.time()), budget_hours=args.grace_hours)
    if not args.no_fetch:
        report.append("")
        report.append(
            "drift-gate triggers: "
            + (
                "unfiltered in every consumer - the required check can report on any PR"
                if not trigger_problems
                else "PATH-FILTERED, see below"
            )
        )
    failures = failures + trigger_problems
    print("\n".join(report))  # noqa: T201
    if failures:
        print("\npin-freshness FAILED:")  # noqa: T201
        for line in failures:
            print(f"  {line}")  # noqa: T201
        print(  # noqa: T201
            "\nRe-vendor the affected module(s) into that service and bump its "
            "HUB_PIN_SHA. A byte-exact copy of a stale canonical is a green gate "
            "against the wrong target."
        )
        return 1
    print("\npin-freshness PASSED: every service's pin is current for what it vendors.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
