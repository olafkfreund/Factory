#!/usr/bin/env python3
"""Assert that a Fides change-gate verdict actually compared two identities.

Factory#618. `fides change-gate` exits 2 when the gate's `approved` is false and
0 otherwise, and `approved` is computed server-side as::

    approved := len(failed) == 0 && len(missing) == 0 && humanApprovers >= 1

The segregation-of-duties verdict is NOT an input to it. The server evaluates
SoD as a side effect of the same request and returns it under
`segregation_of_duties`, but the exit code ignores it. Measured against a real
Fides server (build of evidance-vault @1fc2aa6), all three of these exit 0:

  * committer unknown          -> SoD compliant=false -> exit 0
  * committer IS the approver  -> SoD compliant=false -> exit 0   <- four-eyes breach
  * committer != approver      -> SoD compliant=true  -> exit 0

So exit 0 is the same code for "compared nobody", "compared and FAILED", and
"compared and passed". This script is the missing post-condition: it reads the
gate's own JSON and requires that a named committer was compared against a named
approver, and that they are different people.

What it deliberately does NOT require: a deployer. The server marks SoD
non-compliant until a deployer identity is recorded, and at pull-request time
nobody has deployed. `no deployer recorded` is therefore expected here and is
the one violation this script tolerates -- the deployer leg belongs to the
deploy gate, not the PR gate. Every other violation is fatal.

Usage:  fides change-gate --trail "$TRAIL_ID" > gate.json
        scripts/fides_gate_verdict.py --committer "$COMMITTER" gate.json

Exit:   0 the gate passed AND the separation it claims was actually compared
        1 anything else, including "the check could not be performed"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NoReturn

# The server marks SoD incomplete until a deployer is recorded. At PR time there
# is no deployer, so this violation alone does not sink the PR gate.
_DEFERRED_TO_DEPLOY_GATE = "no deployer recorded"

# A GitHub privacy-masked commit address can never equal a Fides SSO identity, so
# "committer != approver" would be true no matter who did what -- unfalsifiable,
# which is not the same claim as separated. See docs/compliance/.
_UNFALSIFIABLE_SUFFIX = "@users.noreply.github.com"


def _say(line: str) -> None:
    """This script's only report sink: the CI step log, on stderr."""
    print(line, file=sys.stderr)  # noqa: T201 - CI step report sink


def _fail(reason: str) -> NoReturn:
    _say(f"fides-gate verdict FAILED: {reason}")
    raise SystemExit(1)


def check(gate: dict[str, Any], expected_committer: str = "") -> list[str]:
    """Return the lines describing what was compared, or raise SystemExit(1).

    Split out from main() so the mutation table can drive it directly.
    """
    sod = gate.get("segregation_of_duties")
    if not isinstance(sod, dict):
        _fail(
            "not_checked: the gate returned no segregation_of_duties payload, so "
            "nothing proves a second human was involved. Exit 0 from `fides "
            "change-gate` alone does not carry that claim (Factory#618)."
        )

    committer = str(sod.get("committer") or "").strip()
    approvers = [str(a).strip() for a in (sod.get("approvers") or []) if str(a).strip()]
    deployers = [str(d).strip() for d in (sod.get("deployers") or []) if str(d).strip()]

    if not committer:
        _fail(
            "not_checked: committer identity unknown. Pass "
            "`fides trail start --committer <email>`; without it "
            "`committer != approver` is trivially true and the gate compares nobody."
        )
    if expected_committer and committer.lower() != expected_committer.strip().lower():
        _fail(
            f"the gate compared committer {committer!r}, but this run supplied "
            f"{expected_committer!r}. The identity on the trail is not the one under test."
        )
    if committer.lower().endswith(_UNFALSIFIABLE_SUFFIX):
        _fail(
            f"not_checked: committer {committer!r} is a GitHub privacy-masked address. "
            "It cannot equal a Fides approver identity under any circumstances, so "
            "`committer != approver` here is unfalsifiable rather than proven. "
            "Turn off email privacy for the committing account, or record the "
            "committer's Fides identity explicitly."
        )
    if not approvers:
        _fail("no approver recorded: there is no second identity to compare against.")

    # The server compares identities with exact string equality, so a difference
    # of case alone reads to it as two distinct people. Compare case-insensitively.
    folded = {a.lower() for a in approvers}
    if committer.lower() in folded:
        _fail(f"committer {committer!r} is also an approver -- this is not four-eyes.")
    if committer.lower() in {d.lower() for d in deployers}:
        _fail(f"committer {committer!r} is also the deployer -- this is not four-eyes.")

    fatal = [v for v in (sod.get("violations") or []) if v != _DEFERRED_TO_DEPLOY_GATE]
    if fatal:
        _fail("segregation-of-duties violations: " + "; ".join(fatal))

    # A verdict over zero controls is the same vacuum in a different place: no
    # control was evaluated, so the risk score is a number nobody could falsify.
    evaluated = (
        len(gate.get("passed") or [])
        + len(gate.get("failed") or [])
        + len(gate.get("missing_evidence") or [])
        + len(gate.get("waived") or [])
    )
    if evaluated == 0:
        _fail(
            "not_checked: the gate evaluated zero controls, so `approved` reflects "
            "no policy at all. Enforce at least one control on this Flow "
            "(`fides control enforce ...`)."
        )

    if gate.get("approved") is not True:
        _fail(
            f"gate verdict is {gate.get('recommendation', 'hold')!r} "
            f"(risk {gate.get('risk_score')}): {gate.get('summary', '')}"
        )

    return [
        f"  committer          {committer}",
        f"  approvers          {', '.join(approvers)}",
        f"  deployers          {', '.join(deployers) or '(none yet -- deploy gate)'}",
        f"  controls evaluated {evaluated}",
        f"  risk               {gate.get('risk_score')} ({gate.get('risk_level')})",
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("gate_json", type=Path, help="file holding `fides change-gate` output")
    ap.add_argument(
        "--committer",
        default="",
        help="the committer identity this run supplied to `fides trail start`",
    )
    args = ap.parse_args(argv)

    try:
        raw = args.gate_json.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(f"cannot read the change-gate output: {exc}")
    if not raw.strip():
        _fail("the change-gate output is empty -- the gate produced no verdict to check.")
    try:
        gate = json.loads(raw)
    except json.JSONDecodeError as exc:
        _fail(f"the change-gate output is not JSON ({exc}); no verdict could be read.")
    if not isinstance(gate, dict):
        _fail("the change-gate output is not a verdict object.")

    # Check first, announce after: a header printed before the check runs would
    # claim "OK" on the failure path too, which is the shape of defect this
    # script exists to remove. Enumerate what was compared on the pass path as
    # well as the fail path -- a gate that prints only its failures leaves
    # "reported present while absent" invisible.
    lines = check(gate, args.committer)
    _say("fides-gate verdict OK -- separation of duties was compared:")
    for line in lines:
        _say(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
