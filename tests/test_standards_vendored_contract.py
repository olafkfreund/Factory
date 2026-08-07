#!/usr/bin/env python3
"""The vendored contract in standards/README.md must name every vendored file.

Factory#605. The README described the contract as "the same four files" and its
re-vendor snippet hardcoded that same list, while `tsconfig.base.json` had
already been added to the directory and adopted by CFactory (CFactory#320,
Factory#546). A service that followed the documented procedure exactly refreshed
four of its five files.

That failed CLOSED -- the drift gate compares the fifth and goes red -- so it
could never ship a silent fork. The cost was a confusing failure: the gate
rejects a re-vendor done exactly as written, with no hint that the loop was
short one file. Prose that is wrong about a set is also what the next service
copies.

WHY A TEST AND NOT A CAREFUL EDIT. The edit fixes today's omission; nothing stops
the sixth file from repeating it, and the failure surfaces one repo away, in
another service's CI, as a diff that looks like drift. The directory listing is
the fact; the README is a claim about it. This asserts the claim against the
fact, which is the only thing that cannot go stale on its own.
"""

from __future__ import annotations

import re
from pathlib import Path

_STANDARDS = Path(__file__).resolve().parents[1] / "standards"
_README = _STANDARDS / "README.md"

# README.md documents the set; .hub-sha is the pin, not a member of it.
_NOT_VENDORED = {"README.md", ".hub-sha"}


def _vendored_files() -> set[str]:
    """The files a service actually copies out of this directory."""
    return {p.name for p in _STANDARDS.iterdir() if p.is_file()} - _NOT_VENDORED


def _revendor_snippet() -> str:
    """The ```sh block under "Re-vendoring after a hub change"."""
    text = _README.read_text()
    section = text.split("### Re-vendoring after a hub change", 1)[1]
    match = re.search(r"```sh\n(.*?)```", section, re.DOTALL)
    assert match is not None, "the re-vendor section no longer contains a shell snippet"
    return match.group(1)


def _contract_table_files() -> set[str]:
    """The filenames in the vendored-contract table's first column."""
    text = _README.read_text()
    section = text.split("### The vendored contract", 1)[1].split("\n### ", 1)[0]
    return set(re.findall(r"^\|\s*`([^`]+)`\s*\|", section, re.MULTILINE))


def test_the_revendor_loop_copies_every_vendored_file() -> None:
    """The documented procedure must leave nothing stale. This is the defect."""
    snippet = _revendor_snippet()
    missing = sorted(f for f in _vendored_files() if f not in snippet)
    assert not missing, (
        f"standards/README.md's re-vendor snippet never names {missing}. A service "
        "following it verbatim leaves those files stale, and its drift gate then "
        "fails on a procedure this repo told it to run (Factory#605)."
    )


def test_the_contract_table_lists_every_vendored_file_and_the_pin() -> None:
    """Teeth the other way too: a phantom row is as wrong as a missing one."""
    assert _contract_table_files() == _vendored_files() | {".hub-sha"}
