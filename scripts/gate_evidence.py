#!/usr/bin/env python3
"""Plumbing shared by the hub's gates: verdict citations, and self-test reporting.

Factory#504. A gate that reports a verdict without the thing it read is a claim
nobody can falsify, and the direction that costs most is the confident PASS: a
comparison that matches for the wrong reason prints nothing, so nothing gets
investigated. For a byte-exact gate the "raw fragment" is the file content, and
its citable form is a digest plus a length — anyone can re-run ``sha256sum`` and
check the claim in one command.

One function, in one place, because the three hub drift gates
(``check_verification_core_drift``, ``check_factory_github_drift``,
``check_factory_ui_drift``) all need exactly this and three copies is what the
clone budget in ``scripts/check_jscpd_budget.py`` exists to stop.

Import-safe for the consumers: every service repo runs those gates out of a full
hub checkout (``python factory-hub-main/scripts/check_*.py``), so this sibling
resolves on ``sys.path`` with no workflow change and no pin bump.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

GITHUB_API = "https://api.github.com"


def gate_argparser(description: str | None) -> argparse.ArgumentParser:
    """An ``ArgumentParser`` with the ``--self-test`` flag every gate's CLI carries.

    Factory#720. Six new gates landed the same day and jscpd caught the
    argparse-plus-dispatch boilerplate as net-new duplication within the
    hour — the same clone-budget mechanism this module's docstring already
    describes catching three copies of the reporting tail. Extracted here
    rather than left as a sixth (seventh, ...) copy.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--self-test", action="store_true", help="run the built-in self-test and exit"
    )
    return parser


def dispatch_self_test(argv_self_test: bool, self_test_fn: Callable[[], int]) -> int | None:
    """Return the self-test's exit code if ``--self-test`` was passed, else None.

    The other half of :func:`gate_argparser`. Most callers want
    :func:`parse_or_self_test` instead, which folds this in with
    ``parser.parse_args``; exposed separately for a gate that needs the two
    steps apart.
    """
    if argv_self_test:
        return self_test_fn()
    return None


def parse_or_self_test(
    parser: argparse.ArgumentParser, argv: list[str] | None, self_test_fn: Callable[[], int]
) -> tuple[int | None, argparse.Namespace | None]:
    """Parse *argv*; if ``--self-test`` was passed, run it instead.

    Returns ``(exit_code, None)`` when the self-test ran (the caller returns
    immediately), or ``(None, args)`` to continue with the parsed arguments —
    the standard shape every gate's ``main()`` needs, once, in one place.
    """
    args = parser.parse_args(argv)
    result = dispatch_self_test(args.self_test, self_test_fn)
    if result is not None:
        return result, None
    return None, args


def add_repo_arg(parser: argparse.ArgumentParser) -> None:
    """The ``--repo`` flag every GitHub-API-reading gate's CLI carries."""
    parser.add_argument("--repo", default="olafkfreund/Factory", help="owner/name to inspect")


def run_gate_main(
    description: str,
    self_test_fn: Callable[[], int],
    run_fn: Callable[[argparse.Namespace], int],
    argv: list[str] | None = None,
    configure: Callable[[argparse.ArgumentParser], None] | None = None,
) -> int:
    """The standard CLI wrapper every gate's ``main()`` repeats.

    Factory#774. ``check_gate_liveness.py`` and ``check_codeql_analysis_honesty.py``
    had the identical parse/dispatch/network-error tail, caught as net-new
    duplication the moment the second one landed -- the same shape
    :func:`fetch_github_json` closes for the fetch half. *configure* adds any
    gate-specific arguments beyond the ``--self-test`` flag :func:`gate_argparser`
    already provides; *run_fn* receives the parsed ``Namespace`` and returns the
    gate's exit code, wrapped so an unreachable API returns 2 (unknown), never 0.
    """
    parser = gate_argparser(description)
    if configure is not None:
        configure(parser)
    code, args = parse_or_self_test(parser, argv, self_test_fn)
    if code is not None or args is None:
        return code if code is not None else 2
    try:
        return run_fn(args)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"ERROR: could not reach the GitHub API: {exc}")  # noqa: T201
        # 2, not 0. An unreachable API is an unknown verdict, and an unknown
        # verdict must never be reported as a healthy fleet.
        return 2


@contextmanager
def temp_repo() -> Iterator[Path]:
    """A throwaway directory for a gate's self-test fixtures.

    Every hub gate's self-test builds a synthetic repo tree in a tmp dir so
    its logic is verified without touching any real repo; this was the same
    two lines (``with tempfile.TemporaryDirectory() as tmp: root = Path(tmp)``)
    in enough gates to trip the clone budget.
    """
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@contextmanager
def gate_fixture() -> Iterator[tuple[Path, list[str]]]:
    """``temp_repo`` plus the ``failures`` list every ``_self_test`` collects into.

    ``with gate_fixture() as (repo, failures): ...`` replaces the
    standard four-line ``_self_test`` header — one more piece of the same
    argparse/self-test boilerplate jscpd caught duplicated across the six
    gates that landed in one PR (Factory#720).
    """
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp), []


def fetch_github_json(url: str, *, timeout: int = 20) -> object:
    """GET *url* and parse JSON, authenticated via GITHUB_TOKEN/GH_TOKEN when present.

    Factory#774. Shared by every gate that reads the GitHub REST API directly
    (``check_gate_liveness.py``, ``check_codeql_analysis_honesty.py``, ...) --
    the URL-scheme guard and auth header existed once per gate before this,
    caught as net-new duplication by ``scripts/check_jscpd_budget.py`` the
    moment a second copy landed, which is what that budget is for.
    """
    # Enforced rather than suppressed. Every caller builds *url* from its own
    # API-base constant (normally GITHUB_API), so this can only fire if
    # someone later threads a caller-supplied URL through -- at which point
    # `file:///etc/shadow` would be a readable local file, not a failed HTTP
    # request.
    if not url.startswith(f"{GITHUB_API}/"):
        raise ValueError(f"refusing to fetch a URL outside {GITHUB_API}: {url!r}")
    request = urllib.request.Request(  # noqa: S310 - scheme enforced immediately above
        url, headers={"Accept": "application/vnd.github+json"}
    )
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def digest(path: Path) -> str:
    """A short, re-derivable citation of the bytes at *path*.

    Truncated to 12 hex characters: this is a human-readable citation printed
    next to a verdict, not the comparison itself. The gates compare full byte
    strings; nothing decides anything on this value.
    """
    if not path.is_file():
        return "absent"
    data = path.read_bytes()
    return f"sha256:{sha256(data).hexdigest()[:12]} {len(data)}B"


def expect(failures: list[str], condition: bool, label: str) -> None:
    """Record a self-test failure instead of raising on the first one.

    The other half of ``report_self_test``: collecting lets one run report every
    broken case, and it survives ``python -O``, which strips bare asserts and
    would silently turn a gate's self-test into a no-op. It lived twice before
    the clone budget caught the second copy going in -- which is what the budget
    is for, and the same reason the reporting tail below was extracted.
    """
    if not condition:
        failures.append(label)


def report_self_test(failures: list[str]) -> int:
    """Print a gate's own self-test outcome and return its exit code.

    Every hub gate carries a dependency-free ``--self-test`` that its scheduled
    workflow runs BEFORE believing the gate's verdict, and each one collects
    failures into a list rather than tripping on the first bare assert (so one run
    reports every broken case, and ``python -O`` cannot silence it). The reporting
    tail of that pattern was literally identical in three scripts and the clone
    budget caught the third copy going in -- which is what the budget is for.
    """
    for label in failures:
        print(f"self-test FAILED: {label}")  # noqa: T201
    if failures:
        return 1
    print("self-test OK")  # noqa: T201
    return 0
