#!/usr/bin/env python3
"""Is any service gating against a canonical that has since moved? (Factory#519)

Each consumer's drift workflow answers one question: *does my vendored copy match
my pin?* Nothing anywhere answered the next one: *is my pin still the current
canonical?* A service can sit arbitrarily far behind with a
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

Both file-granular gates are covered - verification-core and factory-ui - and
that is load-bearing rather than tidy. Factory#514 narrowed the fleet's pin rule
so a set vendored as scattered FILES may pin inside its workflow instead of a
`.hub-sha` beside a directory, but ONLY while the hub reads those pins without
opening the workflow. This module is that reading. A gate missing from
:data:`GATES` is a pin nobody outside its own workflow can find, and the rule's
exemption stops covering it. See :class:`Gate`.

The planning-card gate (Factory#554) raises the stakes of that reading rather
than merely joining it. Every other gate here has a vendored copy on the service
side, so a stale pin still leaves SOMETHING compared. That one has none: CFactory
checks the hub out at its pin and compares its pydantic models against
`apis/planning-card.schema.json` in place. A pin left behind means the service is
gated against a contract nobody is writing to any more, and its build stays
green while every consumer reads a schema the hub has since changed. This
watchdog is the only thing positioned to say so.

The layouts are imported from each gate's own checker, never restated: they are
the fleet's map of who vendors what, and a second copy here would be the
hand-maintained fork Factory#483 exists to undo. A service added there is checked
here automatically.

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
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_factory_ui_drift import SERVICE_LAYOUTS as UI_LAYOUTS
from check_verification_core_drift import SERVICE_LAYOUTS
from selftest_report import SelfTest


def _pin_re(var: str) -> re.Pattern[str]:
    """Regex for ``<var>: "<sha>"`` in a workflow's env block.

    Per-gate because the pin variable is not named identically everywhere:
    the two drift workflows use HUB_PIN_SHA, and CFactory's contracts gate lives
    inside code-quality.yml alongside a DIFFERENT pin, so one file would carry
    two variables of the same name (Factory#547).
    """
    return re.compile(rf'^\s*{re.escape(var)}:\s*"([0-9a-fA-F]{{7,40}})"', re.MULTILINE)


# service key -> GitHub repo name. One table, because a service is one repo
# whichever gate is asking.
_REPOS: dict[str, str] = {
    "pfactory": "PFactory",
    "aifactory": "AIFactory",
    "tfactory": "TFactory",
    "cfactory": "CFactory",
}


@dataclass(frozen=True)
class Gate:
    """A file-granular vendored set, its pin, and where its canonical lives.

    Factory#514: the fleet's pin-file convention (``.hub-sha`` beside the
    directory) binds vendored DIRECTORIES, and these sets are not directories —
    verification-core is six files across three roots, and factory-ui is two
    files inside a components directory the portal otherwise owns. Their pins
    live in the gate's workflow, which the standard permits ONLY because the hub
    carries the map and reads the pins fleet-wide. This class is that reading;
    a gate declared here is discoverable by definition, and one that is not
    declared is exactly the pin nobody outside its own workflow can find.
    """

    name: str
    workflow: str
    """Path to the gate's workflow inside each consumer repo."""
    canonical_root: str
    """Hub directory holding the canonical modules."""
    layouts: dict[str, dict[str, str]]
    """service -> {canonical module: path in that service}."""
    pin_var: str = "HUB_PIN_SHA"
    """Name of the workflow variable holding this gate's pin."""
    required_check: bool = False
    """Is this gate's job a REQUIRED status check in its consumers?

    Decides whether a ``paths:`` filter on its pull_request trigger is a defect.
    For a required gate it is fatal — a filtered workflow reports nothing rather
    than skipped, so every non-matching PR is blocked forever (Factory#543 made
    verification-core required, which is what turned that from a gap into an
    outage). For a gate that is NOT required, a filter is a legitimate way to
    keep it quiet, and flagging it would be the noise that gets a real alert
    muted.
    """

    def services(self) -> list[str]:
        return sorted(self.layouts)

    def canonical_paths(self, service: str) -> list[str]:
        """Hub paths of the canonical modules *service* vendors from this gate.

        The service-side path in the layout is where the COPY lives and is
        irrelevant here — this asks what moved upstream.
        """
        return [f"{self.canonical_root}/{m}" for m in sorted(self.layouts[service])]


GATES: tuple[Gate, ...] = (
    Gate(
        name="verification-core",
        workflow=".github/workflows/verification-core-drift.yml",
        canonical_root="scripts",
        layouts=SERVICE_LAYOUTS,
        required_check=True,
    ),
    Gate(
        name="factory-ui",
        workflow=".github/workflows/factory-ui-drift.yml",
        canonical_root="shared/factory-ui",
        layouts=UI_LAYOUTS,
        # Path-filtered today, and legitimately so: it is not a required check,
        # so a PR it skips is not blocked. If it is ever made required, the
        # filter has to go first (Factory#525 then #543, in that order).
        required_check=False,
    ),
    Gate(
        name="factory-contracts",
        # NOT a dedicated *-drift.yml: this gate is a `diff` inlined in
        # CFactory's code-quality.yml, which is why its pin needed naming
        # (CFactory#301) before it could be read from here.
        workflow=".github/workflows/code-quality.yml",
        pin_var="CONTRACTS_PIN_SHA",
        canonical_root="shared/factory-contracts/python/factory_contracts",
        # Declared INLINE, unlike the two above, because there is no hub checker
        # for this set to import a layout from — the comparison lives in the
        # service workflow. Extracting that checker is option 1 of Factory#547
        # and is where this probably wants to end up; this is option 2, the
        # smallest change that makes the pin readable fleet-wide. A one-entry
        # map is also the honest shape: CFactory is the only consumer, checked
        # with `git grep` across the other three.
        layouts={
            "cfactory": {
                "__init__.py": "apps/backend/cfactory/_contracts/factory_contracts/__init__.py"
            }
        },
        required_check=False,
    ),
    Gate(
        name="planning-card",
        workflow=".github/workflows/planning-card-conformance.yml",
        canonical_root="apis",
        # THE ONLY GATE HERE WHOSE CANONICAL IS NOT VENDORED ANYWHERE
        # (Factory#554). CFactory holds no copy of the schema: its workflow
        # checks the hub out at the pin and compares its pydantic models against
        # the file in place. That makes this watchdog the ONLY thing that can
        # notice the contract moving — the conformance gate itself is honestly
        # green against a stale pin forever, which is the Factory#499 shape and
        # exactly what #519 was opened about.
        #
        # The layout value would be the vendored path for every other gate.
        # There is none, so it says so: nothing here compares it, and
        # `canonical_paths()` only ever reads the KEY.
        layouts={
            "cfactory": {
                "planning-card.schema.json": "(not vendored — checked out at the pin)",
            }
        },
        # Not a required status check yet. It became blocking in CFactory on the
        # PR that added it; making it REQUIRED in branch protection is a separate,
        # deliberate step, and until it is, a `paths:` filter on it would not wedge
        # a PR. (The workflow carries no filter regardless — see its header.)
        required_check=False,
    ),
    Gate(
        name="security-lint",
        workflow=".github/workflows/security-lint.yml",
        canonical_root="shared/factory-seclint",
        # The whole-repo security-sink gate (Factory#726). Registered only NOW,
        # after all four services merged their copies — a gate declared here
        # before its consumers hold the file makes this watchdog red on a
        # missing path rather than on a stale pin, which is the failure
        # standards/README.md warns about in as many words ("never register a
        # file in a service's gate before that service has the file").
        #
        # ALL FOUR SERVICES, unlike every gate below it. This canonical is not
        # vendored subset-by-subset: each service carries the identical pair,
        # because the rule set is the fleet's security bar and a service running
        # a narrower one would be the exact drift the gate exists to prevent.
        layouts={
            service: {
                "ruff-security.toml": "security-lint/ruff-security.toml",
                "security_lint.py": "security-lint/security_lint.py",
            }
            for service in ("pfactory", "aifactory", "tfactory", "cfactory")
        },
        # Not a REQUIRED status check yet. It is blocking on every PR in all
        # four repos from the day it landed; promoting it in branch protection
        # is a separate, deliberate step. Until then a `paths:` filter on it
        # would not wedge a PR — and it carries none regardless, deliberately:
        # a whole-repo gate that only wakes for .py changes cannot see a finding
        # introduced by a config change.
        required_check=False,
    ),
)

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


def fetch_workflow(repo: str, workflow: str, *, timeout: int = 20) -> str:
    """*repo*'s *workflow* as text, from its default branch.

    Raises :class:`PinUnavailableError` rather than returning a sentinel. A gate
    that treats "I could not look" as "nothing wrong" is the Factory#500 shape.
    """
    # raw.githubusercontent is CDN-cached for a few minutes, so immediately
    # after a workflow lands this can still serve the previous revision. For a
    # DAILY watchdog that is self-healing noise, not a correctness problem -
    # observed once while renaming a pin (Factory#547), gone on the next run.
    # It is a reason not to wire this into a merge gate, where a stale read
    # would block a PR for a change that already landed.
    url = _RAW.format(owner=_OWNER, repo=repo, path=workflow)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            # Bound to a declared str rather than returned straight: urlopen's
            # result is untyped, so returning it directly is `Any` escaping a
            # function annotated -> str, which the mypy ratchet blocks.
            body: str = response.read().decode("utf-8")
            return body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PinUnavailableError(f"{repo}: cannot fetch {url}: {exc}") from exc


def pin_from(repo: str, body: str, workflow: str, pin_var: str = "HUB_PIN_SHA") -> str:
    """The ``HUB_PIN_SHA`` declared in *body*."""
    match = _pin_re(pin_var).search(body)
    if match is None:
        raise PinUnavailableError(f"{repo}: no {pin_var} found in {workflow}")
    return match.group(1)


def fetch_pin(repo: str, workflow: str, *, timeout: int = 20) -> str:
    """The live ``HUB_PIN_SHA`` from *repo*'s *workflow*."""
    return pin_from(repo, fetch_workflow(repo, workflow, timeout=timeout), workflow)


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
    """Hub paths of the verification-core modules *service* vendors.

    Kept as a module-level shim over :data:`GATES`[0] because the tests and the
    self-test name it directly; new code should ask the Gate.
    """
    return GATES[0].canonical_paths(service)


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
    for gate in GATES:
        for service in sorted(set(gate.layouts) - set(_REPOS)):
            problems.append(
                f"{gate.name}: {service} is in the layout but has no repo mapping "
                "here, so its pin is never checked"
            )
    # The reverse direction is per-FLEET, not per-gate: a service may legitimately
    # sit outside one gate's layout (CFactory vendors no factory-ui component). It
    # may not sit outside every gate, which would mean this watchdog knows a repo
    # and reads nothing from it.
    covered = {svc for gate in GATES for svc in gate.layouts}
    for service in sorted(set(_REPOS) - covered):
        problems.append(
            f"{service} has a repo mapping here but appears in no gate's layout, "
            "so there is nothing to check it against"
        )
    # Fleet-wide coverage alone is too weak once there is more than one gate:
    # dropping a service from ONE layout leaves it covered by another and the
    # check above stays quiet, which is the silent scope loss with extra steps.
    # A REQUIRED gate has a stronger invariant available - its job blocks merges
    # in every consumer, so every consumer must be in its layout, and a gap there
    # means a repo whose merges are gated by a check the hub cannot account for.
    for gate in GATES:
        if not gate.required_check:
            continue
        for service in sorted(set(_REPOS) - set(gate.layouts)):
            problems.append(
                f"{gate.name} is a required check but {service} is absent from its "
                "layout, so a repo is gated by a check the hub does not track"
            )
    return problems


def _hours(now: int, epoch: int) -> float:
    return (now - epoch) / 3600.0


def check(
    pins: dict[str, str],
    *,
    now: int,
    budget_hours: float = _DEFAULT_BUDGET_HOURS,
    gate: Gate | None = None,
) -> tuple[list[str], list[str]]:
    """Verdicts for *pins* as ``(failures, report_lines)``.

    *gate* defaults to verification-core, the gate this watchdog was written for
    (Factory#519); factory-ui joined it when Factory#514 narrowed the pin rule
    and made "the hub reads every file-granular pin" the CONDITION of the
    exemption rather than a claim about it.

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
    gate = gate or GATES[0]
    failures: list[str] = []
    report: list[str] = []
    for service in sorted(pins):
        pin = pins[service]
        modules = sorted(gate.layouts[service])
        moved = commits_since(pin, gate.canonical_paths(service))
        behind = total_behind(pin)
        report.append(
            f"{gate.name}/{service}: pin {pin[:8]}, {behind} hub commit(s) behind overall"
        )
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
                f"{gate.name}/{service} is gating against a moved canonical: "
                f"{len(moved)} commit(s) "
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
    t = SelfTest("pin-freshness")
    req = t.req

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

    return t.finish()


def _gather(
    gate: Gate, overrides: dict[str, str], *, no_fetch: bool, on_missing: Callable[[str], object]
) -> tuple[dict[str, str], list[str]]:
    """*gate*'s pin per service, plus any trigger problem, from ONE fetch per repo."""
    pins: dict[str, str] = {}
    problems: list[str] = []
    for service in gate.services():
        repo = _REPOS[service]
        if service in overrides:
            pins[service] = overrides[service]
            continue
        if no_fetch:
            on_missing(f"--no-fetch given but no --pin for {service}")
            continue
        body = fetch_workflow(repo, gate.workflow)
        pins[service] = pin_from(repo, body, gate.workflow, gate.pin_var)
        # Only a REQUIRED gate can wedge a PR by being filtered; see Gate.
        if gate.required_check:
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
        if not sha or service not in _REPOS:
            parser.error(f"--pin expects SERVICE=SHA with a known service, got {item!r}")
        overrides[service] = sha

    now = int(time.time())
    failures: list[str] = []
    report: list[str] = []
    try:
        for gate in GATES:
            pins, trigger_problems = _gather(
                gate, overrides, no_fetch=args.no_fetch, on_missing=parser.error
            )
            gate_failures, gate_report = check(
                pins, now=now, budget_hours=args.grace_hours, gate=gate
            )
            report.extend(gate_report)
            failures.extend(gate_failures)
            failures.extend(trigger_problems)
            if gate.required_check and not args.no_fetch:
                report.append(
                    f"  [{gate.name}] trigger: "
                    + (
                        "unfiltered in every consumer - the required check can report on any PR"
                        if not trigger_problems
                        else "PATH-FILTERED, see below"
                    )
                )
            report.append("")
    except PinUnavailableError as exc:
        sys.stderr.write(f"pin-freshness: {exc}\n")
        return _EXIT_BAD_INVOCATION

    print("\n".join(report).rstrip())  # noqa: T201
    if failures:
        print("\npin-freshness FAILED:")  # noqa: T201
        for line in failures:
            print(f"  {line}")  # noqa: T201
        print(  # noqa: T201
            "\nRe-vendor the affected module(s) into that service and bump its "
            "HUB_PIN_SHA. A byte-exact copy of a stale canonical is a green gate "
            "against the wrong target.\n"
            "For the planning-card gate there is nothing to re-vendor - CFactory "
            "holds no copy of the schema - so the fix is the pin bump alone, plus "
            "whatever model change the moved contract now requires (Factory#554)."
        )
        return 1
    print(  # noqa: T201
        f"\npin-freshness PASSED: every service's pin is current for what it vendors, "
        f"across {len(GATES)} gate(s): {', '.join(g.name for g in GATES)}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
