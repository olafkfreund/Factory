#!/usr/bin/env python3
"""Can a merge on this fleet be attributed to a human or to an agent? (Factory#611)

Agents are told "open PRs, never merge". Every agent drives `gh` with the
operator's own credentials, so `mergedBy` reads `olafkfreund` whether a human or
an agent pressed the button. The instruction is therefore neither blockable
beforehand nor decidable afterwards.

WHAT THIS MEASURES, AND WHY MEASURING IT IS THE POINT. Factory#611's acceptance
criterion 3 is a spot-check: "pick a merged PR and determine, from metadata
alone, whether a human or an agent merged it." Today the answer is no, for every
PR in the fleet. That is a claim, and a claim in a document decays; this turns it
into a reading. It reports, per pull request, the login the merge is recorded
against and whether that login is one whose credentials agents hold.

It goes green on its own the day the operator provisions a separate identity for
agents, with no edit here: a merge recorded against any login outside
``_SHARED_IDENTITIES`` is attributable by construction. Until then it is red, and
red is the correct reading -- the control genuinely does not exist.

DELIBERATELY NOT WIRED INTO CI, and not scheduled. A gate that is red on every
run teaches its audience to ignore red, which is the cry-wolf failure
Factory#538 recorded; and no pull request can turn this one green, because the
missing thing is a GitHub identity, not code. It is an on-demand audit command,
cited from docs/compliance/agent-identity.md. The offline self-test is what keeps
it honest between runs.

WHAT IT CANNOT DO. It reads the merge trail, so it detects the ABSENCE of
attribution, never a violation. If an agent merged a PR today this reports
"indistinguishable" -- exactly as it does when the operator merged it. That is
the finding, not a limitation to be worked around: no analysis of this metadata
can separate the two, which is why the fix is a second identity and not a
cleverer query.

Usage:
    python3 scripts/check_merge_attribution.py                 # whole fleet, needs gh
    python3 scripts/check_merge_attribution.py --repo Factory --limit 50
    python3 scripts/check_merge_attribution.py --stdin < merges.json
    python3 scripts/check_merge_attribution.py --self-test     # offline

Exit codes:
    0 - every merge read is attributable to an identity agents do not hold
    1 - at least one merge is recorded against a shared identity, so who merged
        it cannot be determined from metadata
    2 - nothing could be read (no gh, no repos, a null merge actor). A check that
        cannot see its subject reports that, never green
        (standards/coding-standards.md rule 4.7).
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from selftest_report import SelfTest, gate_argparser

_REPOS = ("Factory", "AIFactory", "PFactory", "TFactory", "CFactory", "factory-gitops")

# Logins whose credentials the fleet's agents hold. A merge recorded against one
# of these could have been performed by the operator or by any agent running in
# any session, and nothing in the GitHub audit trail separates the two.
#
# Measured 2026-08-07: `gh api repos/olafkfreund/<repo>/collaborators` returns
# exactly one entry, `olafkfreund` (User, admin), on all six repos. That single
# account is the root cause, and it is why the issue's cheaper options do not
# work -- see docs/compliance/agent-identity.md.
#
# This set SHRINKS, never grows: when agents get their own identity, that login
# does not belong here, because the operator does not hold it.
_SHARED_IDENTITIES = frozenset({"olafkfreund"})

# Exit codes, named so the self-test can compare against them without ruff
# reading each literal as a magic number.
EXIT_OK = 0
EXIT_INDISTINGUISHABLE = 1
EXIT_UNDETERMINED = 2

ATTRIBUTABLE = "attributable"
INDISTINGUISHABLE = "indistinguishable"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Merge:
    """One merged pull request and the login its merge is recorded against."""

    repo: str
    number: int
    merged_by: str | None


def classify(merge: Merge) -> str:
    """Verdict for one merge.

    Note what is NOT here: no heuristic on merge timing, PR body, or branch name.
    Those correlate with agent activity and would produce a confident guess, which
    for an audit control is worse than a refusal -- Factory#611 exists because a
    confident reconstruction of merge provenance turned out to be wrong.
    """
    if merge.merged_by is None:
        return UNKNOWN
    if merge.merged_by in _SHARED_IDENTITIES:
        return INDISTINGUISHABLE
    return ATTRIBUTABLE


def assess(merges: Sequence[Merge]) -> tuple[int, dict[str, int]]:
    """Return ``(exit_code, counts)`` for a batch of merges."""
    counts = {ATTRIBUTABLE: 0, INDISTINGUISHABLE: 0, UNKNOWN: 0}
    for merge in merges:
        counts[classify(merge)] += 1
    if not merges:
        return EXIT_UNDETERMINED, counts
    if counts[UNKNOWN]:
        return EXIT_UNDETERMINED, counts
    if counts[INDISTINGUISHABLE]:
        return EXIT_INDISTINGUISHABLE, counts
    return EXIT_OK, counts


def parse(repo: str, payload: Sequence[Mapping[str, object]]) -> list[Merge]:
    """Turn one `gh pr list --json number,mergedBy` response into merges.

    Typed against `object` and checked, rather than against `Any` and trusted.
    This is the trust boundary -- everything downstream is an audit verdict, and
    a payload shaped differently from what is assumed here should stop the run
    rather than be coerced into a plausible-looking merge.
    """
    merges = []
    for pull in payload:
        number = pull.get("number")
        if not isinstance(number, int):
            raise TypeError(f"{repo}: pull request number is not an integer: {number!r}")
        actor = pull.get("mergedBy")
        login = actor.get("login") if isinstance(actor, dict) else None
        if login is not None and not isinstance(login, str):
            raise TypeError(f"{repo}#{number}: mergedBy.login is not a string: {login!r}")
        merges.append(Merge(repo, number, login))
    return merges


def fetch(repo: str, limit: int) -> list[Merge]:
    """Read merged pull requests for one repo. Raises on any gh failure."""
    # S603/S607: fixed argv, no shell. `repo` comes from _REPOS or --repo, and is
    # passed as one argv element, so it cannot introduce a second command.
    out = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "gh",
            "pr",
            "list",
            "--repo",
            f"olafkfreund/{repo}",
            "--state",
            "merged",
            "--limit",
            str(limit),
            "--json",
            "number,mergedBy",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return parse(repo, json.loads(out.stdout))


def report(merges: Sequence[Merge]) -> None:
    """Print one line per merge, on the passing path as well as the failing one.

    Both directions are printed on purpose (docs/dev/gate-honesty.md variant 2):
    a reader that prints the source only for what it reports as broken cannot be
    caught reading the wrong field for everything it reports as fine.
    """
    for merge in merges:
        verdict = classify(merge)
        actor = merge.merged_by if merge.merged_by is not None else "<no merge actor>"
        print(f"  {verdict:<18} {merge.repo}#{merge.number}  mergedBy={actor}")  # noqa: T201


def _selftest() -> int:
    check = SelfTest("check_merge_attribution")

    distinct = [Merge("Factory", 1, "factory-agent[bot]")]
    code, counts = assess(distinct)
    check.req(code == EXIT_OK, f"a merge by an identity agents do not hold passes (exit {code})")
    check.req(counts[ATTRIBUTABLE] == 1, "and is counted as attributable")

    # The mutation: same merge, same everything, recorded against the shared
    # account. The gate has to be observed FAILING here or it proves nothing
    # (docs/dev/gate-honesty.md).
    shared = [Merge("Factory", 1, "olafkfreund")]
    code, counts = assess(shared)
    check.req(
        code == EXIT_INDISTINGUISHABLE, f"the same merge under the shared login fails (exit {code})"
    )
    check.req(counts[INDISTINGUISHABLE] == 1, "and is counted as indistinguishable")

    code, _ = assess([Merge("Factory", 1, None)])
    check.req(
        code == EXIT_UNDETERMINED, f"a merge with no recorded actor is undetermined (exit {code})"
    )

    code, _ = assess([])
    check.req(
        code == EXIT_UNDETERMINED, f"reading zero merges is undetermined, not a pass (exit {code})"
    )

    parsed = parse("Factory", [{"number": 7, "mergedBy": {"login": "olafkfreund"}}])
    check.req(parsed == [Merge("Factory", 7, "olafkfreund")], "gh payload parses to a Merge")
    check.req(
        parse("Factory", [{"number": 8, "mergedBy": None}])[0].merged_by is None,
        "a null mergedBy parses to no actor rather than a login",
    )

    return check.finish()


def main(argv: Sequence[str] | None = None) -> int:
    parser = gate_argparser(__doc__)
    parser.add_argument("--repo", help="check one repo instead of the whole fleet")
    parser.add_argument("--limit", type=int, default=30, help="merged PRs per repo (default 30)")
    parser.add_argument(
        "--stdin", action="store_true", help="read a gh pr list JSON array from stdin"
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return _selftest()

    merges: list[Merge] = []
    if args.stdin:
        merges = parse(args.repo or "<stdin>", json.load(sys.stdin))
    else:
        for repo in [args.repo] if args.repo else list(_REPOS):
            try:
                merges.extend(fetch(repo, args.limit))
            except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
                print(f"ERROR: cannot read merged PRs for {repo}: {exc}", file=sys.stderr)  # noqa: T201
                return EXIT_UNDETERMINED

    code, counts = assess(merges)
    report(merges)
    print(  # noqa: T201
        f"\n{len(merges)} merges: {counts[ATTRIBUTABLE]} attributable, "
        f"{counts[INDISTINGUISHABLE]} indistinguishable, {counts[UNKNOWN]} unknown."
    )
    if code == EXIT_INDISTINGUISHABLE:
        print(  # noqa: T201
            "\nFAIL: merges recorded against a login whose credentials the agents also\n"
            "hold. Whether a human or an agent merged these cannot be determined from\n"
            "metadata, in either direction. Needs a separate agent identity -- see\n"
            "docs/compliance/agent-identity.md."
        )
    elif code == EXIT_UNDETERMINED:
        print("\nUNDETERMINED: read nothing conclusive; not reporting green.")  # noqa: T201
    return code


if __name__ == "__main__":
    raise SystemExit(main())
